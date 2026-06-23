# frr-sidecar pyunit tests

## Docstring convention

This project uses **short one-line docstrings** for test functions rather than
the Validates/Code/Assertion/Method template prescribed in testing.md.

### Rationale

`testing.md` multi-line template adds value when tests are ambiguous or when the
assertion logic is separated from its intent. In this module:

- Each test function name already encodes the scenario (`test_csv_split_empty_string`,
  `test_readyz_returns_503_when_vtysh_timeout`, etc.).
- Test bodies are 3–10 lines. The intent is unambiguous without a separate
  "Assertion" or "Method" block.
- Existing pre-Phase-2 tests in `test_transit_watcher.py` and `test_vtysh_client.py`
  use the same one-liner style — consistency with the existing corpus matters more
  than conforming to the generic template.

The short form is **intentional and preferred** for this repo. Any future test
additions should follow the same style unless a specific test is genuinely complex
enough to warrant the full template (e.g., multi-step state-machine tests in
`test_transit_watcher.py`).

### Files

| File | Module under test | Notes |
|------|------------------|-------|
| `test_render_frr.py` | `image/render_frr.py` | FRR config rendering, annotation parsing |
| `test_readyz.py` | `image/vty_bridge.py` (`readyz_app`) | Kubelet readiness probe |
| `test_vty_bridge.py` | `image/vty_bridge.py` (`app`) | vtysh HTTP bridge |
| `test_vtysh_client.py` | `image/vtysh_client.py` | vtysh subprocess wrapper |
| `test_transit_watcher.py` | `image/transit_watcher.py` | OSPF LSDB watcher / PBR reconciler |
| `test_frr_config_parser.py` | `image/_frr_config_parser.py` | FRR config parser |

### Running tests

```sh
# From repo root:
pytest tests/pyunit/ -v

# Or via pyproject.toml (sets pythonpath automatically):
pytest -c image/pyproject.toml tests/pyunit/ -v
```
