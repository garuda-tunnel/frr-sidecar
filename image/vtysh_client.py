"""Local vtysh subprocess wrapper for FRR sidecar processes.

Runs inside the FRR sidecar container where vtysh has unix-socket access
to zebra/ospfd. Used by transit_watcher (internal poll loop) and
vty_bridge (exposing the same surface over HTTP to sister containers).
"""

from __future__ import annotations

import json
import subprocess

_DEFAULT_TIMEOUT = 5.0


class VtyshError(RuntimeError):
    """Raised when vtysh exits non-zero or its output is not parseable JSON."""


def vtysh_run(
    command: str, timeout: float = _DEFAULT_TIMEOUT
) -> subprocess.CompletedProcess:
    """Run a vtysh command, return the completed process verbatim.

    Raises OSError when vtysh cannot be executed, subprocess.TimeoutExpired
    when the command does not complete within ``timeout`` seconds.
    """
    return subprocess.run(
        ["vtysh", "-c", command],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def vtysh_json(command: str, timeout: float = _DEFAULT_TIMEOUT) -> dict:
    """Run a vtysh command and parse its stdout as JSON.

    Raises:
        VtyshError: vtysh exited non-zero or stdout was not valid JSON.
        subprocess.TimeoutExpired: command timed out (propagated).
    """
    result = vtysh_run(command, timeout=timeout)
    if result.returncode != 0:
        raise VtyshError(
            f"vtysh returncode={result.returncode} command={command!r} "
            f"stderr={result.stderr!r}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VtyshError(
            f"vtysh returned non-JSON output for command={command!r}: {exc}"
        ) from exc
