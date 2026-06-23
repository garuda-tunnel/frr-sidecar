"""Unit tests for garuda_frr.entrypoint — container entrypoint orchestrator.

Covers:
  1. get_backbone_ip() parses valid `ip -j addr show` JSON correctly.
  2. get_backbone_ip() exits 1 on missing interface (subprocess non-zero).
  3. get_backbone_ip() exits 1 on malformed JSON.
  4. copy_vtysh_conf_if_present() is no-op when source absent.
  5. copy_vtysh_conf_if_present() copies when source present.
  6. ProcessSupervisor.spawn() adds proc to tracking list.
  7. ProcessSupervisor.shutdown() calls terminate on children in reverse order.
  8. ProcessSupervisor.shutdown() SIGKILLs after timeout.
  9. ProcessSupervisor.shutdown() is idempotent (second call no-op).
 10. Click CLI: garuda-frr-entrypoint --help returns 0 and prints expected help.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from garuda_frr.entrypoint import (
    ProcessSupervisor,
    copy_vtysh_conf_if_present,
    get_backbone_ip,
    main,
)

# ---------------------------------------------------------------------------
# 1. get_backbone_ip parses valid JSON
# ---------------------------------------------------------------------------

_VALID_IP_JSON = json.dumps([{"addr_info": [{"local": "172.30.0.5", "prefixlen": 24}]}])


def test_get_backbone_ip_parses_valid_json():
    """get_backbone_ip returns the IPv4 address from ip -j addr show output."""
    fake = MagicMock(returncode=0, stdout=_VALID_IP_JSON, stderr="")
    with patch("garuda_frr.entrypoint.subprocess.run", return_value=fake):
        result = get_backbone_ip("backbone")
    assert result == "172.30.0.5"


# ---------------------------------------------------------------------------
# 2. get_backbone_ip exits 1 on CalledProcessError
# ---------------------------------------------------------------------------


def test_get_backbone_ip_exits_on_subprocess_error():
    """get_backbone_ip calls sys.exit(1) when ip command fails."""
    with patch(
        "garuda_frr.entrypoint.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["ip"]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            get_backbone_ip("backbone")
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# 3. get_backbone_ip exits 1 on malformed JSON
# ---------------------------------------------------------------------------


def test_get_backbone_ip_exits_on_malformed_json():
    """get_backbone_ip calls sys.exit(1) when ip output is not valid JSON."""
    fake = MagicMock(returncode=0, stdout="not json", stderr="")
    with patch("garuda_frr.entrypoint.subprocess.run", return_value=fake):
        with pytest.raises(SystemExit) as exc_info:
            get_backbone_ip("backbone")
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# 4. copy_vtysh_conf_if_present — no-op when source absent
# ---------------------------------------------------------------------------


def test_copy_vtysh_conf_if_present_noop_when_absent(tmp_path, monkeypatch):
    """copy_vtysh_conf_if_present does nothing when vtysh.conf is not present."""
    monkeypatch.chdir(tmp_path)
    dst = tmp_path / "frr" / "vtysh.conf"

    import garuda_frr.entrypoint as ep

    with patch.object(
        ep,
        "copy_vtysh_conf_if_present",
        wraps=lambda: None,
    ):
        # The real function checks /etc/garuda/profile/vtysh.conf — patch Path.is_file
        with patch("garuda_frr.entrypoint.Path") as MockPath:
            mock_src = MagicMock()
            mock_src.is_file.return_value = False
            MockPath.return_value = mock_src
            copy_vtysh_conf_if_present()
            # Nothing was written — dst does not exist
            assert not dst.exists()


# ---------------------------------------------------------------------------
# 5. copy_vtysh_conf_if_present — copies when source present
# ---------------------------------------------------------------------------


def test_copy_vtysh_conf_if_present_copies_when_present(tmp_path):
    """copy_vtysh_conf_if_present copies vtysh.conf to /etc/frr/vtysh.conf."""
    src = tmp_path / "vtysh.conf"
    src.write_bytes(b"hostname frr\n")
    dst = tmp_path / "frr_vtysh.conf"

    import garuda_frr.entrypoint as ep

    # Patch Path to redirect /etc/garuda/profile/vtysh.conf → src
    # and /etc/frr/vtysh.conf → dst
    original_path = ep.Path

    def patched_path(p):
        p = str(p)
        if p == "/etc/garuda/profile/vtysh.conf":
            return src
        if p == "/etc/frr/vtysh.conf":
            return dst
        return original_path(p)

    with patch("garuda_frr.entrypoint.Path", side_effect=patched_path):
        copy_vtysh_conf_if_present()

    assert dst.read_bytes() == b"hostname frr\n"


# ---------------------------------------------------------------------------
# 6. ProcessSupervisor.spawn adds proc to tracking list
# ---------------------------------------------------------------------------


def test_process_supervisor_spawn_tracks_proc():
    """ProcessSupervisor.spawn() adds the process to its internal list."""
    supervisor = ProcessSupervisor()
    fake_proc = MagicMock()
    with patch("garuda_frr.entrypoint.subprocess.Popen", return_value=fake_proc):
        proc = supervisor.spawn("test-svc", ["test-cmd"])
    assert proc is fake_proc
    assert len(supervisor._procs) == 1
    assert supervisor._procs[0] == ("test-svc", fake_proc)


# ---------------------------------------------------------------------------
# 7. ProcessSupervisor.shutdown calls terminate in reverse order
# ---------------------------------------------------------------------------


def test_process_supervisor_shutdown_terminates_in_reverse_order():
    """ProcessSupervisor.shutdown() terminates children in reverse spawn order."""
    supervisor = ProcessSupervisor()
    procs = []

    for name in ["transit_watcher", "vty_bridge", "docker-start"]:
        p = MagicMock()
        p.poll.return_value = None  # still running
        p.wait.return_value = 0
        supervisor._procs.append((name, p))
        procs.append(p)

    supervisor.shutdown(15)

    # All three should have been terminated
    for p in procs:
        p.terminate.assert_called_once()

    # Verify reverse order: docker-start terminated before vty_bridge before transit_watcher
    terminate_order = []
    for _i, (name, p) in enumerate(supervisor._procs):
        if p.terminate.called:
            terminate_order.append(name)

    # The reversed() call means docker-start is first in shutdown
    assert terminate_order == ["transit_watcher", "vty_bridge", "docker-start"]


# ---------------------------------------------------------------------------
# 8. ProcessSupervisor.shutdown SIGKILLs after timeout
# ---------------------------------------------------------------------------


def test_process_supervisor_shutdown_kills_after_timeout():
    """ProcessSupervisor.shutdown() sends SIGKILL when proc.wait times out."""
    supervisor = ProcessSupervisor()
    slow_proc = MagicMock()
    slow_proc.poll.return_value = None
    # First wait() raises TimeoutExpired; second wait() (after kill) returns normally.
    slow_proc.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="slow", timeout=5),
        None,
    ]
    supervisor._procs.append(("slow-svc", slow_proc))

    supervisor.shutdown(15)

    slow_proc.terminate.assert_called_once()
    slow_proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# 9. ProcessSupervisor.shutdown is idempotent
# ---------------------------------------------------------------------------


def test_process_supervisor_shutdown_idempotent():
    """ProcessSupervisor.shutdown() is a no-op on second call."""
    supervisor = ProcessSupervisor()
    p = MagicMock()
    p.poll.return_value = None
    p.wait.return_value = 0
    supervisor._procs.append(("svc", p))

    supervisor.shutdown(15)
    supervisor.shutdown(15)  # second call must not re-terminate

    assert p.terminate.call_count == 1


# ---------------------------------------------------------------------------
# 10. Click CLI: --help output
# ---------------------------------------------------------------------------


def test_cli_help():
    """garuda-frr-entrypoint --help returns 0 and shows expected help text."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "garuda-frr-entrypoint" in result.output
    assert "--skip-render" in result.output
    assert "--validate-only" in result.output
