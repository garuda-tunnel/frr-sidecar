# Changelog

## [0.3.3](https://github.com/garuda-tunnel/frr-sidecar-internal/compare/v0.3.2...v0.3.3) (2026-06-25)


### Bug Fixes

* render prod-parity OSPF (timers, redistribute indent, passive interfaces) ([#17](https://github.com/garuda-tunnel/frr-sidecar-internal/issues/17)) ([c5bdfbc](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/c5bdfbcdab0adff36f7935cbe4a6d9e1032f19d3))

## [0.3.2](https://github.com/garuda-tunnel/frr-sidecar-internal/compare/v0.3.1...v0.3.2) (2026-06-24)


### Bug Fixes

* restore profile daemons copy; revert /etc/frr chown ([#15](https://github.com/garuda-tunnel/frr-sidecar-internal/issues/15)) ([adac6c0](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/adac6c017bc352f5dca47d15793d9fd5b561e2a2))

## [0.3.1](https://github.com/garuda-tunnel/frr-sidecar-internal/compare/v0.3.0...v0.3.1) (2026-06-24)


### Bug Fixes

* **frr-sidecar:** bump appVersion to 0.3.1; /etc/frr chowned root:root ([011d07c](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/011d07c2fd7fcc09dda8b6e7b66a15f62dea90fd))
* **frr-sidecar:** bump appVersion to 0.3.1; /etc/frr chowned root:root ([846a0b9](https://github.com/garuda-tunnel/frr-sidecar-internal/commit/846a0b9611d09d31f880908e4dfb576cf1b16c4c))

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
