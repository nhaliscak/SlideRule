"""The guard around the API that `sliderule app --api` offers to other programs: loopback Host, no foreign web-page Origin, optional bearer token, opt-in CORS."""

import pytest
from fastapi.testclient import TestClient

from sliderule.server import ApiGuard, create_app

RPC = {"method": "settings_get", "params": {}}


def client(**guard):
    return TestClient(create_app(serve_frontend=False, guard=ApiGuard(**guard)), base_url="http://127.0.0.1:8765")


def test_a_program_with_the_token_can_run_functions():
    c = client(token="s3cret")
    r = c.post("/api/rpc", json=RPC, headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and r.json()["ok"] and "timeout_seconds" in r.json()["result"]
    r = c.get("/api/convert", params={"value": 1, "from": "km", "to": "m"}, headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and "1000" in r.text


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "s3cret"}, {"Authorization": "bearer s3cret"}])
def test_missing_or_wrong_tokens_are_refused(headers):
    r = client(token="s3cret").post("/api/rpc", json=RPC, headers=headers)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "UNAUTHORIZED" and r.headers["www-authenticate"] == "Bearer"


def test_the_api_description_stays_public_but_nothing_else():
    c = client(token="s3cret")
    assert c.get("/api/openapi.json").status_code == 200 and c.get("/api/docs").status_code == 200
    assert c.get("/api/settings").status_code == 401


def test_without_a_token_local_programs_are_served():
    assert client().post("/api/rpc", json=RPC).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8765", "127.0.0.1.evil.example", "192.168.1.5:8765"])
def test_a_foreign_host_name_is_refused_so_dns_rebinding_fails(host):
    r = client(token="s3cret").post("/api/rpc", json=RPC, headers={"Host": host, "Authorization": "Bearer s3cret"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "BAD_HOST"


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1", "[::1]:8765"])
def test_loopback_names_are_accepted(host):
    assert client().get("/api/settings", headers={"Host": host}).status_code == 200


def test_a_web_page_on_another_site_cannot_make_the_browser_call_it():
    c = client()                                                                           # even with no token: a cross-site request is refused
    r = c.post("/api/rpc", content='{"method": "settings_get", "params": {}}', headers={"Origin": "https://evil.example", "Content-Type": "text/plain"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "BAD_ORIGIN"
    assert "access-control-allow-origin" not in r.headers


def test_a_listed_origin_is_served_with_cors_headers_and_its_preflight_is_answered():
    c = client(token="s3cret", origins=("http://localhost:3000",))
    pre = c.options("/api/rpc", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"})
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == "http://localhost:3000" and "authorization" in pre.headers["access-control-allow-headers"].lower()
    r = c.post("/api/rpc", json=RPC, headers={"Origin": "http://localhost:3000", "Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:3000"
    bad = c.options("/api/rpc", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers
    assert c.post("/api/rpc", json=RPC, headers={"Origin": "https://evil.example", "Authorization": "Bearer s3cret"}).status_code == 403


def test_the_servers_own_page_may_post_to_it():
    r = client().post("/api/rpc", json=RPC, headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code == 200


def test_the_normal_app_is_unchanged_without_a_guard():
    c = TestClient(create_app(serve_frontend=False))
    assert c.post("/api/rpc", json=RPC, headers={"Origin": "https://anywhere.example"}).status_code == 200
