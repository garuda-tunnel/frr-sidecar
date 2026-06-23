"""garuda-frr-entrypoint — container entrypoint orchestrator.

Replaces the legacy bash entrypoint.sh. Responsibilities:
  1. Read BACKBONE_IP from the backbone interface (Python parse of `ip -j addr show`).
  2. Render frr.conf via garuda_frr.render (function call, no subprocess hop).
  3. Validate via `vtysh -CC` subprocess.
  4. Spawn transit_watcher and vty_bridge as managed child processes (Popen).
  5. Run FRR daemon supervisor (`/usr/lib/frr/docker-start`) as a managed child.
  6. Install SIGTERM/SIGINT handlers that terminate children in deterministic order
     (transit_watcher, vty_bridge, watchfrr) and wait for clean exit.
  7. Exit with watchfrr's exit code.

Why Python (vs the previous bash entrypoint.sh):
  - bash trap discarded by `exec`; replacing with `& wait $!` worked but is fragile.
  - subprocess.Popen + signal.signal gives deterministic, testable signal handling.
  - render() callable directly instead of subprocess + stdout redirect.
  - single Python toolchain in the image (parity with render, vty_bridge, transit_watcher).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click

from garuda_frr import render


def get_backbone_ip(iface: str = "backbone") -> str:
    """Parse `ip -j addr show <iface>` JSON for the first IPv4 address.

    Exits with code 1 on failure so kubelet retries the container
    (per AGENTS.md: if backbone interface is absent, entrypoint MUST exit non-zero).
    """
    try:
        result = subprocess.run(
            ["ip", "-j", "addr", "show", iface],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        data = json.loads(result.stdout)
        return data[0]["addr_info"][0]["local"]
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        IndexError,
        KeyError,
    ) as e:
        click.echo(f"FATAL: cannot resolve {iface} IP: {e}", err=True)
        sys.exit(1)


def render_and_write_frr_conf() -> None:
    """Render frr.conf via garuda_frr.render and write to /etc/frr/frr.conf."""
    conf = render.render_all_from_env()
    Path("/etc/frr").mkdir(parents=True, exist_ok=True)
    Path("/etc/frr/frr.conf").write_text(conf)


def validate_frr_conf() -> None:
    """Run `vtysh -CC /etc/frr/frr.conf`. Exit 1 on failure."""
    try:
        subprocess.run(["vtysh", "-CC", "/etc/frr/frr.conf"], check=True, timeout=10)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        click.echo(f"FATAL: vtysh -CC failed: {e}", err=True)
        sys.exit(1)


def copy_vtysh_conf_if_present() -> None:
    """Copy /etc/garuda/profile/vtysh.conf to /etc/frr/vtysh.conf if present."""
    src = Path("/etc/garuda/profile/vtysh.conf")
    if src.is_file():
        Path("/etc/frr/vtysh.conf").write_bytes(src.read_bytes())


class ProcessSupervisor:
    """Track child processes and shut them down in reverse spawn order on signal."""

    def __init__(self) -> None:
        self._procs: list[tuple[str, subprocess.Popen]] = []
        self._shutting_down = False

    def spawn(self, name: str, argv: list[str]) -> subprocess.Popen:
        proc = subprocess.Popen(argv)
        self._procs.append((name, proc))
        return proc

    def shutdown(self, signum: int) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        click.echo(
            f"frr-sidecar: signal {signum} received, terminating children", err=True
        )
        # Terminate in reverse spawn order: docker-start (watchfrr) last,
        # vty_bridge before, transit_watcher before that.
        for name, proc in reversed(self._procs):
            if proc.poll() is None:
                click.echo(f"frr-sidecar: terminating {name} pid={proc.pid}", err=True)
                proc.terminate()
        # Wait up to 5s for each, then SIGKILL.
        deadline = time.time() + 5.0
        for name, proc in reversed(self._procs):
            timeout = max(0.1, deadline - time.time())
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                click.echo(
                    f"frr-sidecar: {name} did not exit in time, sending SIGKILL",
                    err=True,
                )
                proc.kill()
                proc.wait(timeout=2.0)


@click.command()
@click.option(
    "--skip-render",
    is_flag=True,
    help="Skip render and validation; assume /etc/frr/frr.conf is ready.",
)
@click.option(
    "--validate-only",
    is_flag=True,
    help="Render and validate, but do not start FRR.",
)
def main(skip_render: bool, validate_only: bool) -> None:
    """garuda-frr-entrypoint: container entry orchestrator."""
    # Stage 1: BACKBONE_IP discovery + export for downstream.
    backbone_ip = get_backbone_ip()
    os.environ["BACKBONE_IP"] = backbone_ip
    click.echo(f"frr-sidecar: BACKBONE_IP={backbone_ip}", err=True)

    # Stage 2: Render + validate.
    if not skip_render:
        render_and_write_frr_conf()
        copy_vtysh_conf_if_present()
        validate_frr_conf()

    if validate_only:
        click.echo(
            "frr-sidecar: validate-only mode, exiting after validation", err=True
        )
        sys.exit(0)

    # Stage 3: Process supervisor + signal handlers.
    supervisor = ProcessSupervisor()

    def handle_signal(signum: int, _frame: object) -> None:
        supervisor.shutdown(signum)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Stage 4: Spawn children in order: transit_watcher (if PBR enabled),
    # vty_bridge, docker-start.
    if os.environ.get("PBR_TRANSIT_TAG"):
        supervisor.spawn("transit_watcher", ["garuda-transit-watcher"])
    supervisor.spawn("vty_bridge", ["garuda-vty-bridge"])
    docker_start = supervisor.spawn("docker-start", ["/usr/lib/frr/docker-start"])

    # Stage 5: Wait for docker-start (watchfrr supervises FRR daemons).
    # Other children should outlive only as long as docker-start does;
    # if docker-start exits, we shut down.
    docker_start.wait()
    rc = docker_start.returncode
    click.echo(
        f"frr-sidecar: docker-start exited with code {rc}; shutting down children",
        err=True,
    )
    supervisor.shutdown(signal.SIGTERM)
    sys.exit(rc if rc >= 0 else 128 - rc)
