"""Local conftest for frr-sidecar pyunit tests.

The garuda_frr package source tree is added to sys.path via the
[tool.pytest.ini_options] pythonpath setting in image/pyproject.toml
(pythonpath = ["src"]). When running pytest from repo root without
-c image/pyproject.toml, the manual path insertion below is the fallback.

Shared fixtures
---------------
completed_process  — factory for subprocess.CompletedProcess stubs (vtysh tests).
profile_dir_builder — factory for profile/intent/raw tmpdir structures (render_frr tests).
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Fallback: insert image/src into sys.path for invocations that don't use
# image/pyproject.toml (e.g. plain `pytest tests/pyunit/` from repo root).
# When pyproject.toml's pythonpath is active this is a no-op.
_FRR_IMAGE_SRC = Path(__file__).resolve().parents[2] / "image" / "src"
_frr_image_src_str = str(_FRR_IMAGE_SRC)
if _frr_image_src_str not in sys.path:
    sys.path.insert(0, _frr_image_src_str)


# ---------------------------------------------------------------------------
# Shared fixture: subprocess.CompletedProcess factory
# ---------------------------------------------------------------------------


@pytest.fixture
def completed_process():
    """Return a factory that builds subprocess.CompletedProcess stubs.

    Usage::

        def test_something(completed_process):
            fake = completed_process(returncode=0, stdout="FRR 10.6.0", stderr="")
            monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: fake)
    """

    def _make(
        returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["vtysh", "-c", "anything"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    return _make


# ---------------------------------------------------------------------------
# Shared fixture: profile/intent/raw tmpdir builder for render tests
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_dir_builder(tmp_path):
    """Return a factory that creates garuda mount point directories under tmp_path.

    Usage::

        def test_main(profile_dir_builder, monkeypatch, capsys):
            dirs = profile_dir_builder(
                template="frr defaults traditional\\n...",
                annotations='net.garuda-tunnel/router-id="10.0.0.1"\\n',
                raw_conf=None,   # omit to skip RAW_MOUNT creation
            )
            monkeypatch.setattr(os, "environ", {**os.environ, **dirs["env"]})

    Returns a dict with keys:
        profile_dir, intent_dir, raw_dir (Path | None), env (dict of *_MOUNT vars)
    """

    def _make(
        template: str,
        annotations: str = "",
        raw_conf: str | None = None,
        extra_snippets: dict[str, str] | None = None,
    ) -> dict:
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()
        (profile_dir / "frr.conf.tmpl").write_text(template)

        intent_dir = tmp_path / "intent"
        intent_dir.mkdir()
        (intent_dir / "annotations").write_text(annotations)

        raw_dir = None
        if raw_conf is not None:
            raw_dir = tmp_path / "raw"
            raw_dir.mkdir()
            (raw_dir / "frr.conf").write_text(raw_conf)

        extra_dir = None
        if extra_snippets:
            extra_dir = tmp_path / "extra"
            extra_dir.mkdir()
            for name, content in extra_snippets.items():
                (extra_dir / name).write_text(content)

        env: dict[str, str] = {
            "PROFILE_MOUNT": str(profile_dir),
            "INTENT_MOUNT": str(intent_dir),
        }
        if raw_dir is not None:
            env["RAW_MOUNT"] = str(raw_dir)
        if extra_dir is not None:
            env["EXTRA_MOUNT"] = str(extra_dir)

        return {
            "profile_dir": profile_dir,
            "intent_dir": intent_dir,
            "raw_dir": raw_dir,
            "extra_dir": extra_dir,
            "env": env,
        }

    return _make
