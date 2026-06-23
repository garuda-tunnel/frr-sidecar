"""Behavioral tests for the garuda_frr.vty_bridge Flask app."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

import garuda_frr.vty_bridge as vty_bridge
import garuda_frr.vtysh_client as vtysh_client_mod


@pytest.fixture
def client():
    vty_bridge.app.testing = True
    return vty_bridge.app.test_client()


def test_health_endpoint_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_vtysh_happy_path(client, monkeypatch):
    fake = MagicMock(returncode=0, stdout='{"neighbors": []}', stderr="")
    monkeypatch.setattr(vtysh_client_mod.subprocess, "run", lambda *a, **k: fake)
    resp = client.post("/vtysh", data="show ip ospf neighbor json")
    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    assert resp.get_data(as_text=True) == '{"neighbors": []}'


def test_vtysh_empty_body_returns_400(client):
    resp = client.post("/vtysh", data="")
    assert resp.status_code == 400
    assert resp.get_json() == {"retcode": -1, "raw": "empty command"}


def test_vtysh_nonzero_returncode_returns_400(client, monkeypatch):
    fake = MagicMock(returncode=1, stdout="oops", stderr="err: ")
    monkeypatch.setattr(vtysh_client_mod.subprocess, "run", lambda *a, **k: fake)
    resp = client.post("/vtysh", data="bogus command")
    assert resp.status_code == 400
    assert resp.get_json() == {"retcode": 1, "raw": "err: oops"}


def test_vtysh_timeout_returns_504(client, monkeypatch):
    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="vtysh", timeout=5)

    monkeypatch.setattr(vtysh_client_mod.subprocess, "run", raise_timeout)
    resp = client.post("/vtysh", data="show running-config")
    assert resp.status_code == 504
    assert resp.get_json() == {"retcode": -1, "raw": "vtysh timeout"}


def test_vtysh_oserror_returns_500(client, monkeypatch):
    def raise_oserror(*a, **k):
        raise OSError("vtysh binary missing")

    monkeypatch.setattr(vtysh_client_mod.subprocess, "run", raise_oserror)
    resp = client.post("/vtysh", data="show version")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["retcode"] == -1
    assert "vtysh binary missing" in body["raw"]
