# Changelog

## [0.3.0](https://github.com/garuda-tunnel/frr-sidecar-internal/compare/v0.2.0...v0.3.0) (2026-06-23)


### Features

* phase 2 — frr-sidecar image annotation-layer rewrite ([c25e3bd](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/c25e3bd047238d144de36197ef6a207dd2c1b8d4))
* update _container.tpl readinessProbe to /readyz:9179 and add render_frr env vars ([52096b5](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/52096b5247004a81514cc3144f967170318e84cd))


### Bug Fixes

* add capabilities drop ALL before add in securityContext; document root rationale ([741f639](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/741f639851676cfb06dc1ecc6311ef0bbc9b8a1c))
* gate garuda-profile/garuda-intent volumeMounts on injected=true flag ([e356156](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/e35615687c034dcf30a5aa6ac8d8bc8c604e7226))

## [0.2.0](https://github.com/garuda-tunnel/frr-sidecar-internal/compare/v0.1.0...v0.2.0) (2026-06-16)


### Features

* frr-sidecar library default image digest (Variant B) + CI template-pin caller ([e9cd9a1](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/e9cd9a16b8bc228b3f72a39add658331ffe5b256))
* frr-sidecar library default image digest, Variant B (Phase 1) ([99b3dd8](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/99b3dd8f2410480337be38f226744cd01d85d349))
* frr-sidecar literal semver tag (release-please extra-files) + nil-safe container image; tag-model publish ([0cb05b4](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/0cb05b45405c0e568d94a55da7f0f5ce06d0b045))
* frr-sidecar literal-tag library default + release-please extra-files (sub-project A) ([7c03b57](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/7c03b5762a8e39880e9d30ffc1747de121cfff35))
