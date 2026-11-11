"""`sliderule serve` carries the same guard as the API port: loopback Host and no foreign Origin, so a web page cannot drive the local server."""

import pytest
import uvicorn
from fastapi.testclient import TestClient

from sliderule import cli
from sliderule.server import ApiGuard, bound_to_loopback, create_app

RPC = {"method": "settings_get", "params": {}}


@pytest.fixture
def served(monkeypatch):
    """Run ``cli._serve`` with uvicorn replaced by a recorder; returns a function giving the app it would have served."""
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.delenv("SLIDERULE_SERVE_HOST", raising=False)

    def start(host="127.0.0.1", **kw):
        cli._serve(host, 8765, False, **kw)
        return calls[-1]

    return start


def test_serve_on_the_loopback_address_is_guarded(served):
    app, kw = served()
    c = TestClient(app, base_url="http://127.0.0.1:8765")
    assert kw["host"] == "127.0.0.1" and c.post("/api/rpc", json=RPC).status_code == 200
    assert c.post("/api/rpc", json=RPC, headers={"Host": "evil.example:8765"}).json()["detail"]["code"] == "BAD_HOST"           # DNS rebinding
    r = c.post("/api/rpc", content='{"method": "custom_delete", "params": {}}', headers={"Origin": "https://evil.example", "Content-Type": "text/plain"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "BAD_ORIGIN"                                                     # a cross-site request


def test_the_pages_own_requests_still_work(served):
    app, _ = served()
    for host in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765"):
        c = TestClient(app, base_url=f"http://{host}")
        assert c.get("/").status_code == 200                                                                                          # the bundled page
        assert c.post("/api/rpc", json=RPC, headers={"Origin": f"http://{host}"}).status_code == 200                                 # its own fetch() calls carry its own origin
        assert c.put("/api/settings", json={"timeout_seconds": 10}, headers={"Origin": f"http://{host}"}).status_code == 200


def test_serving_to_the_network_warns_and_skips_only_the_host_check(served, capsys):
    app, kw = served("0.0.0.0")
    c = TestClient(app, base_url="http://192.168.1.5:8765")
    assert "reachable from other computers" in capsys.readouterr().err and kw["host"] == "0.0.0.0"
    assert c.post("/api/rpc", json=RPC, headers={"Origin": "http://192.168.1.5:8765"}).status_code == 200                           # reached under its LAN name
    assert c.post("/api/rpc", json=RPC, headers={"Origin": "https://evil.example"}).status_code == 403                               # cross-site requests are still refused


def test_a_loopback_server_does_not_warn(served, capsys):
    served("localhost")
    assert capsys.readouterr().err == ""


def test_the_reload_factory_builds_the_same_guarded_app(monkeypatch):
    monkeypatch.setattr(cli.settings, "configure", lambda *a, **k: None)
    monkeypatch.setattr(cli.userlists, "configure", lambda *a, **k: None)
    monkeypatch.setattr(cli.usercalcs, "configure", lambda *a, **k: [])
    monkeypatch.delenv("SLIDERULE_SERVE_HOST", raising=False)
    c = TestClient(cli._reload_app(), base_url="http://127.0.0.1:8765")
    assert c.post("/api/rpc", json=RPC, headers={"Host": "evil.example"}).status_code == 403
    monkeypatch.setenv("SLIDERULE_SERVE_HOST", "0.0.0.0")
    c = TestClient(cli._reload_app(), base_url="http://192.168.1.5:8765")
    assert c.post("/api/rpc", json=RPC).status_code == 200


def test_any_host_keeps_the_token_and_origin_rules():
    c = TestClient(create_app(serve_frontend=False, guard=ApiGuard(token="t", any_host=True)), base_url="http://10.0.0.7:8765")
    assert c.post("/api/rpc", json=RPC).status_code == 401
    assert c.post("/api/rpc", json=RPC, headers={"Authorization": "Bearer t"}).status_code == 200
    assert c.post("/api/rpc", json=RPC, headers={"Authorization": "Bearer t", "Origin": "https://evil.example"}).status_code == 403


@pytest.mark.parametrize("host, expected", [("127.0.0.1", True), ("localhost", True), ("::1", True), ("0.0.0.0", False), ("192.168.1.5", False), ("example.com", False)])
def test_which_hosts_count_as_loopback(host, expected):
    assert bound_to_loopback(host) is expected
