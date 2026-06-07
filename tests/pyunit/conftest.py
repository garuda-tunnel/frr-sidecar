"""Local conftest for frr-sidecar pyunit tests.

Inserts the relocated frr-sidecar image source tree into sys.path so that the
live modules (transit_watcher, vty_bridge, vtysh_client) are importable without
needing the repo-root tests/conftest.py.
"""

from pathlib import Path
import sys

# The frr-sidecar image source lives at modules/frr-sidecar/image relative to
# the repo root.  Compute as two parents up from this conftest
# (pyunit/ -> tests/ -> frr-sidecar/) then down into image/.
_FRR_IMAGE_SRC = Path(__file__).resolve().parents[2] / "image"
_frr_image_src_str = str(_FRR_IMAGE_SRC)
if _frr_image_src_str not in sys.path:
    sys.path.insert(0, _frr_image_src_str)
