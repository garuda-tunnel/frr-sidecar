# FRR Sidecar Runtime

This directory contains the FRR sidecar image entrypoint and the transit
watcher used by transit consumers.

## Components

### `transit_watcher.py`

`transit_watcher.py` is a background reconciler that runs inside transit
consumer FRR sidecars.

Problem it solves:

- transit consumers must route marked traffic into a dedicated kernel table
  toward the current transit provider
- the provider next hop is not stable enough to hardcode because OSPF can
  re-converge and move the best path to another neighbor
- FRR itself does not own the consumer-side kernel PBR table, so a separate
  reconciler is needed to keep Linux routing aligned with the live OSPF state

What it does:

1. polls FRR via `vtysh` for OSPF external LSAs
2. selects only default LSAs with the configured transit tag
3. resolves the advertising routers into backbone neighbor addresses
4. reconciles the consumer kernel default route in the dedicated transit table
5. adds or removes `ip rule` entries for the configured ingress interfaces

The watcher is intentionally consumer-side only. It does not advertise OSPF
state, does not own FRR configuration rendering, and does not create Docker
networks.

## Runtime Contract

`entrypoint.sh` starts the watcher only when `PBR_TRANSIT_TAG` is present.

Inputs:

- `PBR_TRANSIT_TAG` (required) — OSPF external route tag to match
- `PBR_TABLE` (optional, default `10000`) — kernel routing table number
- `POLL_INTERVAL` (optional, default `5`) — poll interval in seconds
- `PBR_TRANSIT_INTERFACES` (optional) — comma-separated ingress interfaces that
  should gain `ip rule` entries while a transit next hop exists

Side effects:

- replaces the default route in the configured kernel table when the desired
  transit next hops change
- installs or removes `ip rule iif <iface> lookup <table>` entries to gate
  transit steering on next-hop availability
- logs every reconcile decision through the standard Python logger

Failure model:

- if OSPF data is temporarily unavailable, the watcher logs and retries on the
  next poll cycle
- if no tagged provider is currently visible, it leaves the transit table route
  untouched and removes interface rules when `PBR_TRANSIT_INTERFACES` is set
- the broad `except Exception` in the main loop is deliberate for a long-lived
  daemon: one bad poll cycle must not kill the sidecar process

## Who Uses It

`transit_watcher.py` is used by workloads that consume transit routing through
FRR, for example components whose FRR sidecar renders transit consumer labels
and needs Linux PBR state to follow live OSPF convergence.

It is not used by the transit provider itself. The provider advertises the
tagged default route; consumers run the watcher to follow that advertisement.

## Relationship To Other Docs

- [Dynamic PBR transit watcher design](../../../../docs/superpowers/specs/2026-04-06-dynamic-pbr-transit-watcher-design.md)
- [Smoke testing runbook](../../../../docs/operations/smoke-testing.md)

## Key Code Entry Points

- [Transit watcher](transit_watcher.py)

Read those documents for design history. This README documents the current
runtime contract of the sidecar component.
