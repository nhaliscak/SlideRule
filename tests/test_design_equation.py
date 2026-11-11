"""Saving a System Design as an equation of its own."""

import copy

import pytest

from sliderule import api, design, design_equation, usercalcs
from sliderule.core import solve
from sliderule.core.catalog import default_catalog


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def wind():
    return copy.deepcopy(design.examples()[0]["graph"])


def w(i, sb, sk, db, dk):
    return {"id": i, "from": {"block": sb, "key": sk}, "to": {"block": db, "key": dk}}


def system_value(graph, bid, key):
    r = design.solve_system(graph)
    return next(o["si_value"] for o in r["blocks"][bid]["outputs"] if o["key"] == key)


def test_the_saved_equation_reproduces_the_system_and_can_be_solved_for_any_variable():
    g = wind()
    draft = design_equation.system_to_equation(g, name="Wind to hydrogen")
    assert draft["ok"] and not draft["warnings"] and draft["summary"] == {"variables": 19, "equations": 8, "blocks": 2}
    assert {"mH", "Pe", "Ar"} <= set(draft["calculation"]["outputs"])                                      # every computed quantity is an output by default
    saved = api.custom_save(draft["calculation"])
    cid = saved["id"]
    assert cid.startswith("custom.wind_to_hydrogen")
    c = default_catalog().get(cid)
    sol = solve(c, dict(c.example), solve_for=["mH"])
    assert sol.ok and sol.outputs[0]["si_value"] == pytest.approx(system_value(g, "b2", "mH"), rel=1e-9)
    # the other direction: which wind speed gives that daily hydrogen mass?
    ex = {k: v for k, v in c.example.items() if k != "v"}
    back = solve(c, {**ex, "mH": f"{system_value(g, 'b2', 'mH')} kg"}, solve_for=["v"])
    assert back.ok and back.outputs[0]["si_value"] == pytest.approx(10.0, rel=1e-3)


def test_wires_become_shared_variables_and_outputs_can_be_chosen():
    g = wind()
    draft = design_equation.system_to_equation(g, outputs=["b2.mH", "b1.Pw"])
    assert sorted(draft["calculation"]["outputs"]) == ["Pw", "mH"]
    left_out = next(v for v in draft["calculation"]["variables"] if v["key"] == "Pe")                        # computed but not chosen: becomes an input with its system value
    assert "example" in left_out and left_out["example"].endswith("kW")
    assert api.custom_save(draft["calculation"])["ok"]
    keys = [v["key"] for v in draft["calculation"]["variables"]]
    assert keys.count("Pe") == 1 and "P" not in keys                              # the electrolyzer's P input is the turbine's Pe
    assert all(("example" in v) or ("constant" in v) for v in draft["calculation"]["variables"] if v["key"] in {"rho", "Dr", "v", "eta", "t"})
    candidates = {c["ref"]: c for c in draft["candidates"]}
    assert not candidates["b1.Pe"]["final"] and candidates["b2.mH"]["final"] and set(draft["selected"]) == {"b2.mH", "b1.Pw"}


def test_a_saved_system_is_usable_as_a_block_and_carries_comments_and_math_blocks():
    g = wind()
    g["blocks"][0]["comment"] = "Site survey values"
    g["blocks"].append({"id": "m1", "kind": "math", "op": "add", "values": {"x2": "500 kW"}})
    g["wires"] = [w("w1", "b1", "Pe", "m1", "x1"), w("w2", "m1", "y", "b2", "P")]
    draft = design_equation.system_to_equation(g)
    assert draft["ok"], draft
    assert any("Site survey values" in a for a in draft["calculation"]["assumptions"])
    cid = api.custom_save(draft["calculation"])["id"]
    outer = {"version": 1, "blocks": [{"id": "s1", "calc": cid, "values": dict(default_catalog().get(cid).example)}], "wires": []}
    r = design.solve_system(outer)
    assert r["ok"], r["diagnostics"]
    assert next(o["si_value"] for o in r["blocks"]["s1"]["outputs"] if o["key"] == "mH") == pytest.approx(system_value(g, "b2", "mH"), rel=1e-9)


def test_shared_constants_and_clashing_names_stay_distinct_variables():
    g = {"version": 1, "blocks": [
        {"id": "b1", "calc": "aerospace.atmosphere.isa_troposphere", "values": {"h": "3000 m"}},
        {"id": "b2", "calc": "aerospace.atmosphere.isa_troposphere", "values": {"h": "6000 m"}}], "wires": []}
    draft = design_equation.system_to_equation(g)
    assert draft["ok"], draft
    keys = [v["key"] for v in draft["calculation"]["variables"]]
    assert len(keys) == len(set(keys))
    assert keys.count("g") == 1 and keys.count("T") == 1 and "T_b2" in keys          # constants merge; clashing names are qualified by block
    labels = [v["label"] for v in draft["calculation"]["variables"]]
    assert len(labels) == len(set(labels))


def test_refusals_are_explained_and_nothing_is_saved():
    assert design_equation.system_to_equation({"version": 1, "blocks": [], "wires": []})["ok"] is False
    bad = wind()
    bad["wires"].append(w("w9", "b1", "Ar", "b2", "eta"))                        # area into an efficiency
    r = design_equation.system_to_equation(bad)
    assert not r["ok"] and r["errors"]
    ode_id = _first_ode_calc()
    ode = {"version": 1, "blocks": [{"id": "b1", "calc": ode_id, "values": dict(default_catalog().get(ode_id).example)}], "wires": []}
    r = design_equation.system_to_equation(ode)
    assert not r["ok"] and "differential equation" in " ".join(r["errors"])
    assert usercalcs.listing() == []


def _first_ode_calc():
    return "mechanical.dynamics.damped_oscillator_response"                     # solved numerically: no closed form to save


def test_rpc_returns_the_draft():
    res = api.handle("design_to_equation", {"graph": wind(), "name": "My system", "outputs": "b2.mH"})
    assert res["ok"] and res["result"]["calculation"]["name"] == "My system" and res["result"]["calculation"]["outputs"] == ["mH"]


def _one_block(cid, **values):
    c = default_catalog().get(cid)
    return {"version": 1, "blocks": [{"id": "b1", "calc": cid, "values": {**c.example, **values}}], "wires": []}


def test_validity_limits_of_the_blocks_are_carried_over_and_still_flag_bad_inputs():
    cid = next(c.id for c in default_catalog() if c.id.endswith("ab_test_sample_size"))     # validity: the two rates must differ
    r = design_equation.system_to_equation(_one_block(cid))
    assert r["ok"] and r["warnings"] == []
    limits = r["calculation"]["validity"]
    assert [v["condition"] for v in limits] == ["p1 != p2"] and "must differ" in limits[0]["message"]
    from sliderule.core.custom import calc_from_dict
    calc = calc_from_dict({**r["calculation"], "id": "custom.ab_copy"})
    bad = solve(calc, {**calc.example, "p2": calc.example["p1"]})
    assert any("must differ" in d.message for d in bad.diagnostics)             # the limit is enforced on the saved equation
    # every validity limit in the library survives the round trip, or is reported in the assumptions
    n = 0
    for c in default_catalog():
        if c.custom or not c.parsed_validity or c.parsed_odes or c.tables or n >= 40:
            continue
        r = design_equation.system_to_equation(_one_block(c.id))
        if r["ok"]:
            n += 1
            kept, dropped = len(r["calculation"]["validity"]), sum("not carried over" in a for a in r["calculation"]["assumptions"])
            assert kept + dropped >= 1, c.id
    assert n > 20


def test_a_differential_equation_with_a_closed_form_solution_is_saved_as_that_solution():
    cid = "chemical.reactors.mixing_tank_transient"
    g = _one_block(cid)
    r = design_equation.system_to_equation(g)
    assert r["ok"] and r["warnings"] == [] and "exp(" in r["calculation"]["equations"][0]["text"]
    from sliderule.core.custom import calc_from_dict
    calc = calc_from_dict({**r["calculation"], "id": "custom.tank_copy"})
    got = {o["key"]: o["si_value"] for o in solve(calc, dict(calc.example)).outputs}
    assert got["C"] == pytest.approx(system_value(g, "b1", "C"), rel=1e-9)
    back = solve(calc, {**{k: v for k, v in calc.example.items() if k != "t"}, "C": "0.0197 mol/L"}, solve_for=["t"])                # the saved equation can be solved for time, which the differential equation cannot
    assert back.ok
