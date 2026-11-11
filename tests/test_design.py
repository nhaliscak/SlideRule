import copy

import pytest
from fastapi.testclient import TestClient

from sliderule import api, design
from sliderule.core.catalog import default_catalog
from sliderule.server import create_app

CAT = default_catalog()
client = TestClient(create_app(serve_frontend=False))


def graph(blocks, wires):
    return {"version": 1, "blocks": blocks, "wires": wires}


def w(i, sb, sk, db, dk):
    return {"id": i, "from": {"block": sb, "key": sk}, "to": {"block": db, "key": dk}}


def codes(g):
    return [e["code"] for e in design.validate_graph(g)]


def test_examples_solve_cleanly_and_pass_units_through_wires():
    for ex in design.examples():
        r = design.solve_system(ex["graph"])
        assert r["ok"] and not [d for d in r["diagnostics"] if d["level"] == "error"], ex["id"]
    r = design.solve_system(design.examples()[0]["graph"])
    pe = next(o for o in r["blocks"]["b1"]["outputs"] if o["key"] == "Pe")["si_value"]
    mh = next(o for o in r["blocks"]["b2"]["outputs"] if o["key"] == "mH")["si_value"]
    assert mh == pytest.approx(0.70 * pe * 24 * 3600 / 141.8e6, rel=1e-9)   # kW → MW happened on the wire


def test_wire_type_rules():
    isa, lift = CAT.get("aerospace.atmosphere.isa_troposphere"), CAT.get("aerospace.aerodynamics.lift_drag")
    assert design.wire_problem(isa, "rho", lift, "rho") is None          # density → density
    assert "pressure" in design.wire_problem(isa, "p", lift, "rho")      # pressure ↛ density
    assert "force" in design.wire_problem(lift, "Lf", lift, "S") or "area" in design.wire_problem(lift, "Lf", lift, "S")
    # absolute temperature and temperature difference are different data types
    hx, cond = CAT.get("chemical.heat.lmtd_heat_exchanger"), CAT.get("mechanical.thermo.ideal_gas_law")
    assert design.wire_problem(isa, "T", cond, "T") is None
    assert design.wire_problem(isa, "T", hx, "dT1") is not None


def test_graph_validation_catches_each_rule():
    b = lambda i, c, **kw: {"id": i, "calc": c, **kw}  # noqa: E731
    isa, lift = "aerospace.atmosphere.isa_troposphere", "aerospace.aerodynamics.lift_drag"
    ok = graph([b("a", isa), b("b", lift)], [w("1", "a", "rho", "b", "rho")])
    assert codes(ok) == []
    assert codes(graph([b("a", isa), b("b", lift)], [w("1", "a", "p", "b", "rho")])) == ["TYPE_MISMATCH"]
    assert codes(graph([b("a", isa), b("b", lift)], [w("1", "b", "rho", "a", "rho")])) == ["NOT_AN_OUTPUT"]
    assert codes(graph([b("a", isa), b("b", lift)], [w("1", "a", "h", "b", "rho")])) == ["NOT_AN_OUTPUT"]
    assert codes(graph([b("a", isa), b("b", lift)], [w("1", "a", "rho", "b", "Lf")])) == ["NOT_AN_INPUT"]
    assert codes(graph([b("a", isa)], [w("1", "a", "rho", "a", "h")])) == ["SELF_LOOP"]
    assert codes(graph([b("a", isa), b("c", isa), b("b", lift)], [w("1", "a", "rho", "b", "rho"), w("2", "c", "rho", "b", "rho")])) == ["MULTIPLE_DRIVERS"]
    assert codes(graph([b("a", isa)], [w("1", "zz", "rho", "a", "h")])) == ["BAD_WIRE"]
    assert codes(graph([b("a", "nope.nope")], [])) == ["UNKNOWN_CALC"]


def test_cycles_are_rejected():
    gm = "mechanical.gears.simple_gear_pair"
    # two gear pairs feeding each other's input torque (T2 → T1 and back) form a genuine loop
    g = graph([{"id": "a", "calc": gm}, {"id": "b", "calc": gm}],
              [w("1", "a", "T2", "b", "T1"), w("2", "b", "T2", "a", "T1")])
    assert codes(g) == ["CYCLE"]


def test_roles_can_be_changed_and_are_checked_structurally():
    c = CAT.get("mechanical.materials.axial_member")      # sigma = F/A, eps = sigma/E, dL = eps*L
    assert design.check_block(c)["ok"]
    # solve for the force instead: sigma, A, E, L known; F and dL outputs
    flipped = design.check_block(c, {"F": "output", "sigma": "input"})
    assert flipped["ok"], flipped
    # two unknowns in one equation: F and A both outputs with sigma not given
    bad = design.check_block(c, {"F": "output", "A": "output"})
    assert not bad["ok"] and bad["errors"]
    assert not design.check_block(c, {"sigma": "input", "eps": "input", "dL": "input", "F": "input"})["ok"]    # no outputs
    # physical constants are locked
    pump = CAT.get("mechanical.pumps.hydraulic_power")
    assert not design.check_block(pump, {"g": "input"})["ok"]
    # unused inputs and over-specification surface as warnings, not errors
    w_ = design.check_block(c, {"sigma": "input"})
    assert w_["ok"] and w_["warnings"]


def test_role_flip_changes_the_computation():
    g = graph([{"id": "a", "calc": "mechanical.materials.axial_member", "roles": {"F": "output", "sigma": "input"},
                "values": {"sigma": "83.3333333 MPa", "A": "3000 mm^2", "E": "200 GPa", "L": "2 m"}}], [])
    r = design.solve_system(g)
    assert r["ok"]
    f = next(o for o in r["blocks"]["a"]["outputs"] if o["key"] == "F")
    assert f["si_value"] == pytest.approx(250e3, rel=1e-6)


def test_missing_values_and_upstream_failures_are_reported_per_block():
    g = copy.deepcopy(design.examples()[1]["graph"])
    del g["blocks"][0]["values"]["h"]
    r = design.solve_system(g)
    got = {(d["block"], d["code"]) for d in r["diagnostics"]}
    assert not r["ok"] and ("b1", "MISSING_VALUE") in got and ("b2", "UPSTREAM_FAILED") in got


def test_constants_role_supplies_a_fixed_value():
    g = copy.deepcopy(design.examples()[1]["graph"])
    g["blocks"][1]["roles"] = {"CD": "constant"}
    assert design.solve_system(g)["ok"]


def test_api_and_http_surface():
    d = client.get("/api/calculations/aerospace.atmosphere.isa_troposphere").json()
    assert d["default_roles"]["h"] == "input" and d["default_roles"]["rho"] == "output" and d["default_roles"]["g"] == "constant"
    types = {v["key"]: v["type"] for v in d["variables"]}
    assert types["rho"]["kind"] == "density" and types["rho"]["key"] != types["p"]["key"]
    ex = client.get("/api/design/examples").json()["examples"]
    assert len(ex) >= 2
    r = client.post("/api/design/solve", json={"graph": ex[0]["graph"]}).json()
    assert r["ok"] and set(r["blocks"]) == {"b1", "b2"}
    chk = client.post("/api/design/check", json={"calc_id": "mechanical.materials.axial_member", "roles": {"F": "output", "A": "output"}}).json()
    assert chk["ok"] is False
    assert client.post("/api/design/check", json={"calc_id": "nope"}).status_code == 404
    bad = client.post("/api/design/validate", json={"graph": graph([{"id": "a", "calc": "aerospace.atmosphere.isa_troposphere"}, {"id": "b", "calc": "aerospace.aerodynamics.lift_drag"}], [w("1", "a", "p", "b", "rho")])}).json()
    assert bad["ok"] is False and bad["diagnostics"][0]["code"] == "TYPE_MISMATCH"
    # same envelope as the in-browser engine
    assert api.handle("design_examples")["ok"]


def test_block_comments_are_ignored_by_solving_validated_and_exported():
    g = copy.deepcopy(design.examples()[0]["graph"])
    base = design.solve_system(g)
    g["blocks"][0]["comment"] = "Rotor 100 m & hub height from the site survey (50 % uncertain)"
    again = design.solve_system(g)
    assert again["ok"] and again["blocks"]["b2"]["outputs"] == base["blocks"]["b2"]["outputs"]
    from sliderule import design_export

    for fmt in ("latex", "markdown", "html"):
        res = design_export.export_system(g, fmt, "both", 5, True)
        assert res["ok"] and "site survey" in res["content"], fmt
    assert "Comment:" in design_export.export_system(g, "markdown", "both", 5, True)["content"]
    assert design_export.export_system(g, "python", "both", 5, True)["ok"]
    g["blocks"][0]["comment"] = 5
    assert "BAD_BLOCK" in codes(g)
    g["blocks"][0]["comment"] = "x" * (design.MAX_COMMENT + 1)
    assert "BAD_BLOCK" in codes(g)


def test_block_comments_appear_as_comments_in_the_python_script_and_cannot_break_it():
    from sliderule import design_export

    g = copy.deepcopy(design.examples()[0]["graph"])
    g["blocks"][0]["comment"] = "Line one: from the survey\r\n\nline three \x0b   import os; os.system('x')\n\n"
    res = design_export.export_system(g, "python", "both", 5, True)
    assert res["ok"]
    src = res["content"]
    eqs = src[src.index("# ---- the equations of every block"):]
    block = eqs[eqs.index("# block b1"):eqs.index("# block b2")]
    assert "#   Line one: from the survey" in block and "#   line three" in block and "import os" in block.replace("\n", " ")
    assert all(ln.lstrip().startswith("#") for ln in block.splitlines() if "import os" in ln or "line three" in ln or "Line one" in ln)
    compile(src, "<exported>", "exec")                                   # still valid Python
    namespace: dict = {"__name__": "exported"}
    exec(src, namespace)                                                  # and still reproduces the reference values
    got = namespace["evaluate"]()
    assert all(abs(got[name] - ref) <= 1e-6 * abs(ref) for name, _l, _u, _f, _s, ref in namespace["OUTPUTS"])
