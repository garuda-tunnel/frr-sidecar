# FRR sidecar runtime

[Dockerfile](Dockerfile) installs `garuda_frr` from [src/](src/garuda_frr)
using [pyproject.toml](pyproject.toml). Its entrypoint is
`garuda-frr-entrypoint`. The standalone Python files directly under `image/`
are not copied into the image.

## Startup and rendering

[entrypoint.py](src/garuda_frr/entrypoint.py) resolves the `backbone` address,
renders `/etc/frr/frr.conf` and validates it with `vtysh -CC`. It copies
`daemons` from the profile mount when present, then starts the HTTP bridge
and FRR supervisor. `PBR_TRANSIT_TAG` additionally enables the transit watcher.
Missing backbone data or invalid FRR configuration fails startup.

[render.py](src/garuda_frr/render.py) reads a profile template from
`PROFILE_MOUNT/frr.conf.tmpl` (default `/etc/garuda/profile`). Non-empty intent
annotations from `INTENT_MOUNT/annotations` (default `/etc/garuda/intent`)
override environment values. Passive interfaces are excluded from the active
interface list. `EXTRA_MOUNT` snippets extend the rendered configuration;
`frr-mode=raw` requires `RAW_MOUNT/frr.conf` and bypasses template rendering.
See the renderer's module documentation for the supported fields and paths.

SIGTERM and SIGINT terminate managed child processes in reverse spawn order
and exit successfully. Unexpected FRR supervisor exit propagates its exit
status after child cleanup. Readiness does not monitor every child process.

## HTTP endpoints

[vty_bridge.py](src/garuda_frr/vty_bridge.py) binds the command bridge to
`127.0.0.1:7890` by default. `POST /vtysh` runs FRR commands; keep it within
the pod network namespace. `GET /health` only checks that the bridge serves
requests.

The separate `0.0.0.0:9179/readyz` endpoint returns 200 when `vtysh show version`
succeeds and 503 on failure. It does not require OSPF Full adjacency or prove
that the transit watcher is healthy. Use this endpoint for kubelet readiness.

## Transit routing

[transit_watcher.py](src/garuda_frr/transit_watcher.py) follows tagged OSPF
default LSAs and reconciles Linux routes through `pyroute2.IPRoute`.

| Environment variable | Meaning | Default |
|---|---|---|
| `PBR_TRANSIT_TAG` | Required external LSA tag | none |
| `PBR_TABLE` | Kernel routing table | `201` |
| `POLL_INTERVAL` | Seconds between polls | `5` |
| `PBR_TRANSIT_INTERFACES` | Comma-separated ingress interfaces | empty |

The watcher first resolves tagged advertising routers through the neighbor
table. If providers exist but have no direct neighbor match, it tries the
selected OSPF default route, then provider routes through `backbone`.
That fallback can select a default next hop without checking its LSA tag.
Without any tagged provider it does not enter that fallback.

A non-empty desired next-hop set replaces a differing table default and
installs ingress rules at priority 29000. An empty set removes the configured
ingress rules but retains the previous table route. Poll errors are logged
and retried, including a broad exception handler; existing routes and rules
can therefore remain after a failed cycle. This is the current failure
behavior, not a fail-closed guarantee.

## Privileges

The [library container template](../charts/frr-sidecar/templates/_container.tpl)
drops all capabilities and adds `NET_ADMIN`, `NET_RAW` and `SYS_ADMIN`.
`NET_ADMIN` supports route/rule changes and `NET_RAW` supports OSPF sockets.
The template records FRR startup capability checks as the reason for retaining
`SYS_ADMIN`. The watcher does not perform IPVS or netfilter operations; it is
not evidence that `SYS_ADMIN` is needed. Validate any capability reduction
against the selected FRR image before changing the runtime policy.

See [unit tests](../tests/pyunit/README.md) for local verification.
