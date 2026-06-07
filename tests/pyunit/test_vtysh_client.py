"""Unit tests for modules/frr-sidecar/image/vtysh_client.py.

The module is loaded from its filesystem path because frr_sidecar is not
a Python package (its files are copied into /usr/lib/frr inside the
container image). Tests patch subprocess.run to avoid needing vtysh on
the test host.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "image/vtysh_client.py"
)

_spec = importlib.util.spec_from_file_location("vtysh_client", _MODULE_PATH)
vtysh_client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vtysh_client)


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["vtysh", "-c", "anything"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestVtyshRun:
    def test_returns_completed_process(self):
        with patch(
            "vtysh_client.subprocess.run",
            return_value=_completed(stdout="ok\n"),
        ) as runner:
            result = vtysh_client.vtysh_run("show version")
        runner.assert_called_once()
        assert result.returncode == 0
        assert result.stdout == "ok\n"

    def test_passes_timeout(self):
        with patch("vtysh_client.subprocess.run", return_value=_completed()) as runner:
            vtysh_client.vtysh_run("show version", timeout=12)
        kwargs = runner.call_args.kwargs
        assert kwargs["timeout"] == 12

    def test_propagates_timeout_expired(self):
        with patch(
            "vtysh_client.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="vtysh", timeout=5),
        ):
            with pytest.raises(subprocess.TimeoutExpired):
                vtysh_client.vtysh_run("show version")


class TestVtyshJson:
    def test_parses_json_on_success(self):
        payload = {"ospf": {"router-id": "10.0.0.1"}}
        with patch(
            "vtysh_client.subprocess.run",
            return_value=_completed(stdout=json.dumps(payload)),
        ):
            result = vtysh_client.vtysh_json("show ip ospf json")
        assert result == payload

    def test_raises_vtysh_error_on_non_zero(self):
        with patch(
            "vtysh_client.subprocess.run",
            return_value=_completed(returncode=1, stdout="", stderr="nope"),
        ):
            with pytest.raises(vtysh_client.VtyshError) as exc:
                vtysh_client.vtysh_json("bad command")
        assert "retcode=1" in str(exc.value) or "returncode=1" in str(exc.value)

    def test_raises_vtysh_error_on_invalid_json(self):
        with patch(
            "vtysh_client.subprocess.run",
            return_value=_completed(stdout="not json"),
        ):
            with pytest.raises(vtysh_client.VtyshError):
                vtysh_client.vtysh_json("show version")
