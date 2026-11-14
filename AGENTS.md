# AGENTS.md

Security and contribution rules for frr-sidecar (FRR OSPF sidecar image + library chart).

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
The library chart remains published for backwards compatibility for existing consumers; it is no longer the primary consumption mechanism.

## Runtime maintenance

Follow the [organization coding rules](https://github.com/GFN-CIS/coding-agent-public-rules).
The [runtime guide](image/README.md) is shared by maintainers and agents and
links the deployed Python package. Keep `/readyz` separate from the
loopback command bridge, and do not gate readiness on OSPF Full adjacency.

Verify image changes against the package installed by `image/Dockerfile`.
The old standalone scripts under `image/` are not the deployed entrypoints.
