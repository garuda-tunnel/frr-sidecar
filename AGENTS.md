# AGENTS.md

Security and contribution rules for garuda-frr-sidecar (FRR OSPF library chart + image).

- Never commit or use real public IP addresses. Use RFC5737 (TEST-NET) / RFC1918 / CGNAT ranges only.
- Never commit or use domains other than well-known examples or `example.net`.
- Never commit secrets, tokens, private keys, or customer data.
- This repo publishes a library Helm chart (`oci://ghcr.io/garuda-tunnel/charts/frr-sidecar`) and an image (`ghcr.io/garuda-tunnel/garuda-frr-sidecar`). The chart is consumed by other components via `dependencies:` with `repository: oci://ghcr.io/garuda-tunnel/charts` and `dependency_update = true`. The chart `version` in `charts/frr-sidecar/Chart.yaml` MUST equal the git tag (`vX.Y.Z` ↔ `X.Y.Z`).
