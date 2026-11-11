import json

import pytest
from fastapi.testclient import TestClient

from sliderule import api
from sliderule.server import create_app

client = TestClient(create_app(serve_frontend=False))


def test_meta_and_search():
    m = client.get("/api/meta").json()
    assert m["calculation_count"] >= 300 and {d["id"] for d in m["disciplines"]} >= {"civil", "systems", "quantum", "nuclear"}
    r = client.get("/api/calculations", params={"q": "beam", "discipline": "civil"}).json()
    ids = {x["id"] for x in r["results"]}
    assert {"civil.beam.cantilever_point", "civil.beam.simply_supported_udl"} <= ids and r["facets"]["disciplines"] and r["facets"]["subdisciplines"]
    r = client.get("/api/calculations", params=[("variable", "permeability"), ("variable", "viscosity")]).json()
    got = {x["id"] for x in r["results"]}
    assert "petroleum.reservoir.radial_darcy_inflow" in got and "petroleum.production.gas_well_inflow" in got


def test_detail_has_everything_the_ui_needs():
    d = client.get("/api/calculations/civil.beam.simply_supported_udl").json()
    assert d["equations"][0]["latex"] and d["example"] and d["references"]
    v = {x["key"]: x for x in d["variables"]}
    assert v["E"]["unit"] == "GPa" and "psi" in v["E"]["units"] and v["E"]["kind"] == "pressure"
    assert client.get("/api/calculations/nope").status_code == 404


def test_solve_roundtrip_with_both_input_styles():
    body = {"inputs": {"F": "250 kN", "A": {"value": 3000, "unit": "mm^2"}}, "output_units": {"sigma": "ksi"}}
    r = client.post("/api/calculations/mechanical.materials.axial_member/solve", json={**body, "solve_for": ["sigma"],
                    "inputs": {**body["inputs"], "E": "200 GPa", "L": "2 m"}}).json()
    assert r["ok"] and r["outputs"][0]["unit"] == "ksi" and r["outputs"][0]["value"] == pytest.approx(12.088, rel=1e-3)
    assert r["steps"]["symbolic"] and r["steps"]["numeric"]


def test_solve_reports_user_errors_in_band():
    r = client.post("/api/calculations/mechanical.materials.axial_member/solve", json={"inputs": {"F": "5 m"}}).json()
    assert r["ok"] is False and r["diagnostics"][0]["level"] == "error"


def test_convert_endpoint_and_errors():
    r = client.get("/api/convert", params={"value": 100, "from": "degC", "to": "degF"}).json()
    assert r["value"] == pytest.approx(212) and r["steps"]
    assert client.get("/api/convert", params={"value": 1, "from": "psi", "to": "N"}).status_code == 422
    assert client.get("/api/unit", params={"expr": "kN*m"}).json()["kind"] == "energy"


def test_rpc_envelope_matches_direct_calls():
    """The browser (Pyodide) build calls `handle_json`; the server mirrors it at /api/rpc."""
    via_http = client.post("/api/rpc", json={"method": "meta", "params": {}}).json()
    direct = json.loads(api.handle_json("meta", "{}"))
    assert via_http == direct and direct["ok"]
    bad = json.loads(api.handle_json("get_calculation", json.dumps({"calc_id": "nope"})))
    assert bad == {"ok": False, "error": {"code": "NOT_FOUND", "message": "no calculation with id 'nope'", "status": 404}}


def test_kinds_and_vocabulary():
    k = client.get("/api/kinds").json()["kinds"]
    assert any(x["kind"] == "pressure" and "psi" in x["units"] for x in k)
    v = client.get("/api/vocabulary").json()
    assert "pressure" in v["kinds"] and any(s["key"] == "Re" for s in v["symbols"])


def test_subdiscipline_filter_over_http_and_in_detail():
    r = client.get("/api/calculations", params={"subdiscipline": "Coastal"}).json()
    assert r["count"] >= 2 and all("Coastal Engineering" in x["subdisciplines"] for x in r["results"])
    d = client.get("/api/calculations/civil.coastal.hudson_armor").json()
    assert "Coastal Engineering" in d["subdisciplines"]
    m = client.get("/api/meta").json()
    assert any(s["name"] == "Coastal Engineering" and s["count"] >= 2 for s in m["subdisciplines"])
    assert {d["group"] for d in m["disciplines"]} == {"core", "emerging"}


def test_restricted_units_are_the_only_choices_offered():
    d = client.get("/api/calculations/mechanical.acoustics.spl_from_pressure").json()
    assert next(v for v in d["variables"] if v["key"] == "Lp")["units"] == ["dB"]
