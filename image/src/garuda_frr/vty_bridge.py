"""HTTP bridge exposing FRR vtysh to sister containers.

Runs inside the OSPF sidecar (where vtysh has native unix-socket access to
FRR daemons). Sister containers sharing the network namespace POST vtysh
commands here instead of needing vtysh access themselves.

Multi-threaded via waitress so concurrent calls don't serialize.

Security boundary — two Flask apps, intentional design
-------------------------------------------------------
This module runs TWO separate Flask apps on different bind addresses. This is
a deliberate security boundary and MUST NOT be collapsed into a single app:

  ``app`` (127.0.0.1:7890) — vtysh bridge, loopback-only.
      /vtysh accepts arbitrary FRR commands. vtysh runs as root with
      NET_ADMIN/SYS_ADMIN capabilities and has full control over FRR daemon
      state. Binding to loopback means only processes sharing the pod network
      namespace (i.e., sister containers in the same pod) can reach it. The
      host network namespace (where kubelet runs) cannot reach 127.0.0.1:7890
      across namespaces, so the kubelet and any host-level attacker cannot
      issue vtysh commands.

  ``readyz_app`` (0.0.0.0:9179) — kubelet readiness probe, host-reachable.
      /readyz performs only a read-only liveness check (vtysh show version)
      and returns HTTP 200/503. It binds 0.0.0.0 so the kubelet, which runs
      in the host network namespace, can reach the pod on port 9179 via the
      pod IP. This is the ONLY surface exposed to the host. It accepts no
      writes and carries no privileged capability.

Consolidating both routes onto a single 0.0.0.0 server would expose /vtysh
to the host network namespace, violating the security boundary. Do not do
this even if it appears simpler.

Protocol (main server — 127.0.0.1:7890):
    POST /vtysh
        body: raw command string, e.g. "show ip ospf route json"
        200 + application/json: vtysh stdout as-is (clients expecting JSON
            should request a `json` variant of the command).
        400 + application/json: vtysh retcode != 0. Body is
            {"retcode": N, "raw": "<stderr+stdout>"}.
        504 + application/json: vtysh timeout.

    GET /health
        200 + application/json: {"ok": true} — loopback-only local diagnostics.
        NOT a valid kubelet readinessProbe target (loopback-only, port 7890).

Readiness server (0.0.0.0:9179):
    GET /readyz
        200 + application/json: {"ok": true} — FRR process up, vtysh responds.
        503 + application/json: {"ok": false} — FRR not yet up or vtysh fails.
        This is the kubelet readinessProbe target (spec §7.4).
        Binds 0.0.0.0 so kubelet can reach it from the host network namespace.
"""

from __future__ import annotations

import logging
import subprocess
import threading

import click
from flask import Flask, Response, jsonify, request
from waitress import serve

from garuda_frr.vtysh_client import vtysh_run

# ---------------------------------------------------------------------------
# Main server (loopback — for sister container vtysh access)
# ---------------------------------------------------------------------------
_PORT = 7890
_BIND = "127.0.0.1"
_VTYSH_TIMEOUT = 5
_THREADS = 4

# ---------------------------------------------------------------------------
# Readiness server constants (0.0.0.0 — for kubelet probe)
# ---------------------------------------------------------------------------
_READYZ_PORT = 9179
_READYZ_BIND = "0.0.0.0"
_READYZ_THREADS = 2
_READYZ_VTYSH_TIMEOUT = 3

logger = logging.getLogger("vty_bridge")

# ---------------------------------------------------------------------------
# Main Flask app (127.0.0.1:7890)
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.post("/vtysh")
def vtysh():
    command = request.get_data(as_text=True).strip()
    if not command:
        return jsonify({"retcode": -1, "raw": "empty command"}), 400

    try:
        result = vtysh_run(command, timeout=_VTYSH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return jsonify({"retcode": -1, "raw": "vtysh timeout"}), 504
    except OSError as exc:
        return jsonify({"retcode": -1, "raw": f"vtysh exec failed: {exc}"}), 500

    if result.returncode != 0:
        raw = (result.stderr or "") + (result.stdout or "")
        return jsonify({"retcode": result.returncode, "raw": raw}), 400

    return Response(result.stdout, status=200, mimetype="application/json")


# ---------------------------------------------------------------------------
# Readiness Flask app (0.0.0.0:9179)
# ---------------------------------------------------------------------------
readyz_app = Flask("readyz")


@readyz_app.get("/readyz")
def readyz():
    """Probe: returns 200 when FRR is up and vtysh responds, 503 otherwise.

    Executes `vtysh -c 'show version'` to verify the FRR daemon unix socket is
    responsive. Does NOT check OSPF adjacency state (spec §7.4).
    """
    try:
        result = vtysh_run("show version", timeout=_READYZ_VTYSH_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning("readyz: vtysh timeout")
        return jsonify({"ok": False}), 503
    except OSError as exc:
        logger.warning("readyz: vtysh OSError: %s", exc)
        return jsonify({"ok": False}), 503

    if result.returncode != 0:
        logger.warning("readyz: vtysh returncode=%d", result.returncode)
        return jsonify({"ok": False}), 503

    return jsonify({"ok": True}), 200


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------


def _serve_readyz() -> None:
    """Run the readyz server in a daemon thread."""
    logger.info("readyz listening on %s:%d", _READYZ_BIND, _READYZ_PORT)
    serve(readyz_app, host=_READYZ_BIND, port=_READYZ_PORT, threads=_READYZ_THREADS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s vty_bridge %(message)s",
    )
    # Start readyz server in a daemon thread (dies with main thread)
    t = threading.Thread(target=_serve_readyz, daemon=True, name="readyz-server")
    t.start()
    logger.info("main bridge listening on %s:%d", _BIND, _PORT)
    serve(app, host=_BIND, port=_PORT, threads=_THREADS)


@click.command()
@click.option(
    "--host",
    default=_BIND,
    show_default=True,
    help="Bind address for the vtysh bridge.",
)
@click.option(
    "--port",
    default=_PORT,
    show_default=True,
    type=int,
    help="Port for the vtysh bridge.",
)
def cli(host: str, port: int) -> None:
    """garuda-vty-bridge: HTTP bridge exposing vtysh to sister containers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s vty_bridge %(message)s",
    )
    t = threading.Thread(target=_serve_readyz, daemon=True, name="readyz-server")
    t.start()
    logger.info("main bridge listening on %s:%d", host, port)
    serve(app, host=host, port=port, threads=_THREADS)


if __name__ == "__main__":
    main()
