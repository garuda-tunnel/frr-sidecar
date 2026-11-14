# FRR unit tests

Tests exercise the packaged runtime in `image/src/garuda_frr`, including
rendered OSPF configuration, supervisor shutdown and transit route changes.
The HTTP tests cover the separate command and readiness endpoints. They do
not prove kernel capabilities or live OSPF convergence.

The FRR configuration parser used by tests is local to this directory:
[_frr_config_parser.py](_frr_config_parser.py).

From the repository root, install the test dependencies declared by the
repository's CI workflow into an isolated environment, then run:

```sh
pytest -c image/pyproject.toml tests/pyunit/ -v
```

The pytest configuration supplies the package source path. Test descriptions
should explain the protected behavior and its consequence; short tests may
use a concise docstring without repeating their assertions. Follow the
[organization testing rules](https://github.com/GFN-CIS/coding-agent-public-rules/tree/main/gfn-testing).
