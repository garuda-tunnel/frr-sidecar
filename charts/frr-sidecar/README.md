# frr-sidecar library chart

Helm named templates for embedding an FRR container and its configuration.
Published at `oci://ghcr.io/garuda-tunnel/charts/frr-sidecar`; the version is
in [Chart.yaml](Chart.yaml). This library has no standalone Deployment.

## Template contract

| Template | Inputs and result |
|---|---|
| `frr-sidecar.container` | `image`, `ospf`, optional `transit` and `injected`; emits one container when `ospf` is set |
| `frr-sidecar.configmap` | `name`, `namespace`, `ospf`; emits the FRR ConfigMap |
| `frr-sidecar.volume` | `name`, `ospf`; emits the `frr-source` volume |
| `frr-sidecar.frrConf` | OSPF fields documented in [the template](templates/_frrconf.tpl) |
| `frr-sidecar.initContainer` | Currently emits nothing |

Call `frr-sidecar.container` unconditionally: it handles an absent `ospf`
value itself. A transit provider cannot also specify consumer interfaces.
The transit constants live in the FRR template; the default image comes from
[the image template](templates/_image.tpl).

## Runtime integration

`injected=true` adds profile and intent mounts. The caller must provide the
matching `garuda-profile` and `garuda-intent` volumes as well as `frr-source`.
The current image requires a profile template; the legacy `frr-source` mount
alone is insufficient. See the [runtime guide](../../image/README.md).

Garuda's current platform injects the image through admission policies.
Do not infer that a guest chart should depend on this library merely because
it uses the FRR image. Check the consumer's actual `Chart.yaml` and platform
policy before adding a dependency.
