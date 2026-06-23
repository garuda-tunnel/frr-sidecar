"""Unit tests for garuda_frr.vtysh_client.

Tests patch subprocess.run to avoid needing vtysh on the test host.

The ``completed_process`` fixture (from conftest.py) is used to build
subprocess.CompletedProcess stubs shared with other test modules.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

import garuda_frr.vtysh_client as vtysh_client


class TestVtyshRun:
    def test_returns_completed_process(self, completed_process):
        with patch(
            "garuda_frr.vtysh_client.subprocess.run",
            return_value=completed_process(stdout="ok\n"),
        ) as runner:
            result = vtysh_client.vtysh_run("show version")
        runner.assert_called_once()
        assert result.returncode == 0
        assert result.stdout == "ok\n"

    def test_passes_timeout(self, completed_process):
        with patch(
            "garuda_frr.vtysh_client.subprocess.run", return_value=completed_process()
        ) as runner:
            vtysh_client.vtysh_run("show version", timeout=12)
        kwargs = runner.call_args.kwargs
        assert kwargs["timeout"] == 12

    def test_propagates_timeout_expired(self):
        with patch(
            "garuda_frr.vtysh_client.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="vtysh", timeout=5),
        ):
            with pytest.raises(subprocess.TimeoutExpired):
                vtysh_client.vtysh_run("show version")


class TestVtyshJson:
    def test_parses_json_on_success(self, completed_process):
        payload = {"ospf": {"router-id": "10.0.0.1"}}
        with patch(
            "garuda_frr.vtysh_client.subprocess.run",
            return_value=completed_process(stdout=json.dumps(payload)),
        ):
            result = vtysh_client.vtysh_json("show ip ospf json")
        assert result == payload

    def test_raises_vtysh_error_on_non_zero(self, completed_process):
        with patch(
            "garuda_frr.vtysh_client.subprocess.run",
            return_value=completed_process(returncode=1, stdout="", stderr="nope"),
        ):
            with pytest.raises(vtysh_client.VtyshError) as exc:
                vtysh_client.vtysh_json("bad command")
        assert "retcode=1" in str(exc.value) or "returncode=1" in str(exc.value)

    def test_raises_vtysh_error_on_invalid_json(self, completed_process):
        with patch(
            "garuda_frr.vtysh_client.subprocess.run",
            return_value=completed_process(stdout="not json"),
        ):
            with pytest.raises(vtysh_client.VtyshError):
                vtysh_client.vtysh_json("show version")
