# AGENTS.md

Security and contribution rules for garuda-frr-sidecar (FRR OSPF sidecar image + library chart).

## Security

- Never commit or use real public IP addresses. Use RFC5737 (TEST-NET) / RFC1918 / CGNAT ranges only.
- Never commit or use domains other than well-known examples or `example.net`.
- Never commit secrets, tokens, private keys, or customer data.

## Garuda platform rules

This repo is part of garuda-tunnel. Platform rules (annotation-layer design, MAP/VAP
injection engine, `garuda_guest` contract, sidecar contract, bootstrap timing, Multus
attach-race fix, CEL guard invariants, anti-patterns):

**See: https://github.com/garuda-tunnel/garuda/blob/main/docs/AGENTS-platform.md**
Local path: `../garuda/docs/AGENTS-platform.md`

## Publishing model

This repo publishes:
- An image: `ghcr.io/garuda-tunnel/garuda-frr-sidecar`
- A library Helm chart: `oci://ghcr.io/garuda-tunnel/charts/frr-sidecar`

The chart `version` in `charts/frr-sidecar/Chart.yaml` MUST equal the git tag
(`vX.Y.Z` ↔ `X.Y.Z`). release-please manages version bumps.

The image is injected by garuda's `MutatingAdmissionPolicy` (see platform rules above).
The library chart remains published for backwards compatibility during the Phase 5
cutover transition; it is no longer the primary consumption mechanism.

## Image build obligations (this repo owns the implementation)

These are build-time obligations for maintainers of this image. Rationale is in the
platform rules doc linked above.

- **`/readyz` on `0.0.0.0:9179`**: the image MUST expose this endpoint. HTTP 200 when
  FRR is running and `vtysh` responds. HTTP 503 otherwise. The loopback-only `/health`
  on `127.0.0.1:7890` is NOT a valid kubelet readinessProbe target — do not use it as a
  replacement.
- **`render_frr.py` at `/usr/lib/frr/render_frr.py`**: Python stdlib only (no Jinja2,
  no `gomplate`, no `envsubst`). Reads env vars (`OSPF_INTERFACES`, `REDISTRIBUTE`,
  `OSPF_ROUTER_ID`, `PROFILE`, `BACKBONE_IP`, `PBR_TRANSIT_TAG`,
  `PBR_TRANSIT_INTERFACES`), CSV-splits list vars, and renders multi-line FRR blocks.
- **Single toolchain — `python3`**: no `jq`, no `envsubst`, no shell substring hacks.
  BACKBONE_IP extraction:
  ```sh
  BACKBONE_IP=$(ip -j addr show backbone | python3 -c \
    'import json,sys; print(json.load(sys.stdin)[0]["addr_info"][0]["local"])')
  ```
  If `backbone` interface is absent at startup, the entrypoint MUST exit non-zero so
  kubelet retries the container.
- **SIGTERM handling**: entrypoint MUST trap SIGTERM, stop FRR daemons gracefully
  (`killall watchfrr` or equivalent), and exit with code 0.
- **Do NOT gate readiness on OSPF Full** — probe gates on FRR process liveness only.
  See platform rules for rationale.
