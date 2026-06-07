"""HTTP bridge exposing FRR vtysh to sister containers.

Runs inside the OSPF sidecar (where vtysh has native unix-socket access to
FRR daemons). Sister containers sharing the network namespace POST vtysh
commands here instead of needing vtysh access themselves.

Multi-threaded via waitress so concurrent calls don't serialize.

Protocol:
    POST /vtysh
        body: raw command string, e.g. "show ip ospf route json"
        200 + application/json: vtysh stdout as-is (clients expecting JSON
            should request a `json` variant of the command).
        400 + application/json: vtysh retcode != 0. Body is
            {"retcode": N, "raw": "<stderr+stdout>"}.
        504 + application/json: vtysh timeout.
"""

from __future__ import annotations

import logging
import subprocess

from flask import Flask, Response, jsonify, request
from waitress import serve

from vtysh_client import vtysh_run

_PORT = 7890
_BIND = "127.0.0.1"
_VTYSH_TIMEOUT = 5
_THREADS = 4

logger = logging.getLogger("vty_bridge")
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


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s vty_bridge %(message)s",
    )
    logger.info("listening on %s:%d", _BIND, _PORT)
    serve(app, host=_BIND, port=_PORT, threads=_THREADS)


if __name__ == "__main__":
    main()
