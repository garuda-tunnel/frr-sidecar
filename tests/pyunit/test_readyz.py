"""Tests for the /readyz endpoint in garuda_frr.vty_bridge.

/readyz must:
  - bind on 0.0.0.0:9179 (tested structurally via constants, not a live socket)
  - return HTTP 200 when vtysh responds successfully
  - return HTTP 503 when vtysh fails (non-zero returncode, timeout, or OSError)
  - be reachable via a Flask test client on the READYZ_APP (distinct from the
    main vty_bridge app which binds 127.0.0.1:7890)

This test file imports vty_bridge and checks the READYZ_APP Flask app.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

import garuda_frr.vty_bridge as vty_bridge
import garuda_frr.vtysh_client as vtysh_client_mod


@pytest.fixture
def readyz_client():
    vty_bridge.readyz_app.testing = True
    return vty_bridge.readyz_app.test_client()


def test_readyz_constants():
    """readyz server must bind 0.0.0.0:9179 — verify module constants."""
    assert vty_bridge._READYZ_PORT == 9179
    assert vty_bridge._READYZ_BIND == "0.0.0.0"


def test_readyz_returns_200_when_vtysh_ok(readyz_client, monkeypatch):
    """GET /readyz returns 200 when vtysh show version succeeds."""
    fake = MagicMock(returncode=0, stdout="FRR 10.6.0 ...", stderr="")
    monkeypatch.setattr(vtysh_client_mod.subprocess, "run", lambda *a, **k: fake)
    resp = readyz_client.get("/readyz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_readyz_returns_503_when_vtysh_fails(readyz_client, monkeypatch):
    """GET /readyz returns 503 when vtysh exits non-zero."""
    fake = MagicMock(returncode=1, stdout="", stderr="connection refused")
    monkeypatch.setattr(vtysh_client_mod.subprocess, "run", lambda *a, **k: fake)
    resp = readyz_client.get("/readyz")
    assert resp.status_code == 503
    assert resp.get_json()["ok"] is False


def test_readyz_returns_503_when_vtysh_timeout(readyz_client, monkeypatch):
    """GET /readyz returns 503 when vtysh times out."""

    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="vtysh", timeout=5)

    monkeypatch.setattr(vtysh_client_mod.subprocess, "run", raise_timeout)
    resp = readyz_client.get("/readyz")
    assert resp.status_code == 503
    assert resp.get_json()["ok"] is False


def test_readyz_returns_503_when_vtysh_oserror(readyz_client, monkeypatch):
    """GET /readyz returns 503 when vtysh binary is missing (OSError)."""

    def raise_oserror(*a, **k):
        raise OSError("vtysh not found")

    monkeypatch.setattr(vtysh_client_mod.subprocess, "run", raise_oserror)
    resp = readyz_client.get("/readyz")
    assert resp.status_code == 503
    assert resp.get_json()["ok"] is False


def test_existing_health_endpoint_unaffected(monkeypatch):
    """Existing /health endpoint on the original app still returns 200."""
    vty_bridge.app.testing = True
    client = vty_bridge.app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
