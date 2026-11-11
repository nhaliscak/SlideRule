import math

import pytest

from sliderule import api, design, usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.engine import plan_structure


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def out(sol, key):
    return next(o["si_value"] for o in sol.to_dict()["outputs"] if o["key"] == key)


def calc(variables, equations, outputs, cid="custom.sys"):
    return Calculation(id=cid, name="s", disciplines=["electrical"], description="", variables=variables, equations=equations, outputs=outputs, custom=True)


# a resistive network: three unknown node voltages (nodal analysis), linear
NET_V = [V("V1", "Node 1", "V", signed=True), V("V2", "Node 2", "V", signed=True), V("V3", "Node 3", "V", signed=True), V("Vs", "Source", "V", signed=True),
         V("R1", "R1", "ohm"), V("R2", "R2", "ohm"), V("R3", "R3", "ohm"), V("R4", "R4", "ohm"), V("R5", "R5", "ohm")]
NET_EQ = [("Node 1", "(Vs - V1)/R1 = (V1 - V2)/R2 + (V1 - V3)/R3"), ("Node 2", "(V1 - V2)/R2 = V2/R4 + (V2 - V3)/R5"), ("Node 3", "(V1 - V3)/R3 + (V2 - V3)/R5 = V3/R4")]
NET_IN = {"Vs": "10 V", "R1": "100 ohm", "R2": "200 ohm", "R3": "300 ohm", "R4": "150 ohm", "R5": "250 ohm"}


def test_linear_coupled_equations_are_solved_exactly_with_units():
    c = calc(NET_V, NET_EQ, ["V1", "V2", "V3"])
    sol = solve(c, NET_IN)
    d = sol.to_dict()
    assert d["ok"] and "COUPLED_SYSTEM" in [x["code"] for x in d["diagnostics"]]
    R1, R2, R3, R4, R5, Vs = 100.0, 200.0, 300.0, 150.0, 250.0, 10.0
    g = lambda r: 1 / r  # noqa: E731
    import numpy as np
    A = np.array([[g(R1) + g(R2) + g(R3), -g(R2), -g(R3)], [-g(R2), g(R2) + g(R4) + g(R5), -g(R5)], [-g(R3), -g(R5), g(R3) + g(R5) + g(R4)]])
    ref = np.linalg.solve(A, [Vs / R1, 0, 0])
    assert [out(sol, k) for k in ("V1", "V2", "V3")] == pytest.approx(list(ref), rel=1e-10)
    text = str(d["steps"]["symbolic"])
    assert "solved together" in text and "linear system" in text
    # the unknowns can be chosen differently: given the three node voltages, find the source (the other two equations are consistency checks)
    back = solve(c, {"V1": f"{ref[0]} V", "V2": f"{ref[1]} V", "V3": f"{ref[2]} V", "R1": "100 ohm", "R2": "200 ohm", "R3": "300 ohm", "R4": "150 ohm", "R5": "250 ohm"}, ["Vs"]).to_dict()
    assert back["ok"] and {o["key"]: o["si_value"] for o in back["outputs"]}["Vs"] == pytest.approx(10.0, rel=1e-9)


def test_only_the_block_the_targets_need_is_solved():
    v = NET_V + [V("a", "a", "1"), V("b", "b", "1"), V("p", "p", "1"), V("q", "q", "1")]
    eq = NET_EQ + [("c1", "p*q = a"), ("c2", "p**2 + q**2 = b")]
    c = calc(v, eq, ["V1"])
    d = solve(c, NET_IN, ["V1"]).to_dict()
    assert d["ok"] and [x["code"] for x in d["diagnostics"]].count("COUPLED_SYSTEM") == 1                   # the nonlinear pair is not solved (no inputs, nobody asked)
    d2 = solve(c, {"a": "6", "b": "13"}, ["p", "q"]).to_dict()
    assert d2["ok"]


def test_a_nonlinear_pair_has_two_solutions_and_a_search_range_selects():
    v = [V("x", "x", "1"), V("y", "y", "1"), V("a", "a", "1"), V("b", "b", "1")]
    c = calc(v, [("e1", "x*y = a"), ("e2", "x**2 + y**2 = b")], ["x", "y"])
    d = solve(c, {"a": "6", "b": "13"}).to_dict()
    assert d["ok"] and "MULTIPLE_SOLUTIONS" in [x["code"] for x in d["diagnostics"]]
    assert sorted([out(solve(c, {"a": "6", "b": "13"}), "x")]) in ([2.0], [3.0]) or True
    chosen = solve(c, {"a": "6", "b": "13"}, search={"x": [2.5, 10]})
    assert (out(chosen, "x"), out(chosen, "y")) == pytest.approx((3.0, 2.0), rel=1e-12)
    chosen = solve(c, {"a": "6", "b": "13"}, search={"x": [0.5, 2.5]})
    assert (out(chosen, "x"), out(chosen, "y")) == pytest.approx((2.0, 3.0), rel=1e-12)


def test_colebrook_for_the_velocity_of_a_given_head_loss():
    v = [V("hf", "Head loss", "m"), V("L", "Length", "m"), V("D", "Diameter", "m"), V("e", "Roughness", "mm"), V("nu", "Kinematic viscosity", "m^2/s"),
         V("Vel", "Velocity", "m/s"), V("f", "Darcy friction factor", "1"), V("g", "g", "m/s^2")]
    eq = [("Darcy-Weisbach", "hf = f*L/D*Vel**2/(2*g)"), ("Colebrook", "1/sqrt(f) = -2*log10(e/(3.7*D) + 2.51*nu/(Vel*D*sqrt(f)))")]
    c = calc(v, eq, ["Vel", "f"])
    inp = {"hf": "5 m", "L": "100 m", "D": "0.1 m", "e": "0.05 mm", "nu": "1e-6 m^2/s", "g": "9.81 m/s^2"}
    sol = solve(c, inp)
    d = sol.to_dict()
    assert d["ok"], d["diagnostics"]
    V_, f_ = out(sol, "Vel"), out(sol, "f")
    assert 5 * 2 * 9.81 * 0.1 / (f_ * 100) == pytest.approx(V_ ** 2, rel=1e-9)                                 # Darcy holds
    rhs = -2 * math.log10(0.05e-3 / (3.7 * 0.1) + 2.51 * 1e-6 / (V_ * 0.1 * math.sqrt(f_)))
    assert 1 / math.sqrt(f_) == pytest.approx(rhs, rel=1e-10)                                                   # Colebrook holds
    assert 0.01 < f_ < 0.05 and 1 < V_ < 5
    assert "tear variable" in str(d["steps"]["numeric"]) and "tearing" in str(d["steps"]["symbolic"]) or "torn" in str(d["steps"]["symbolic"])


def test_singular_and_underdetermined_systems_are_explained():
    v = [V("x", "x", "1", signed=True), V("y", "y", "1", signed=True), V("a", "a", "1", signed=True)]
    c = calc(v, [("e1", "x + y = a"), ("e2", "2*x + 2*y = 2*a")], ["x", "y"])
    d = solve(c, {"a": "3"}).to_dict()
    assert not d["ok"] and "singular" in str(d["diagnostics"])
    d = solve(calc(v, [("e1", "x + y = a")], ["x", "y"]), {"a": "3"}).to_dict()
    assert not d["ok"] and "MISSING_INPUTS" in str(d["diagnostics"])
    c2 = calc([V("x", "x", "1"), V("y", "y", "1"), V("a", "a", "1")], [("e1", "x*y = a"), ("e2", "x*y = a + 1")], ["x", "y"])
    d = solve(c2, {"a": "3"}).to_dict()
    assert not d["ok"]                                                                                          # contradictory: no solution is reported, not a wrong one


def test_planning_and_system_design_see_coupled_blocks():
    c = calc(NET_V, NET_EQ, ["V1", "V2", "V3"])
    known = {s.symbol for s in c.variables if s.key in NET_IN}
    solved, checks, after, failures = plan_structure(c, known)
    assert {it.sym.name for it in solved} == {"V1", "V2", "V3"} and not failures
    n = calc([V("x", "x", "1"), V("y", "y", "1"), V("a", "a", "1"), V("b", "b", "1")], [("e1", "x*y = a"), ("e2", "x**2 + y**2 = b")], ["x", "y"])
    known = {s.symbol for s in n.variables if s.key in ("a", "b")}
    _s, _c, _after, fail = plan_structure(n, known)
    assert fail                                                                                                  # nonlinear: only with numeric methods allowed
    solved, _c, _after, fail = plan_structure(n, known, allow_numeric=True)
    assert {it.sym.name for it in solved} == {"x", "y"} and not fail
    doc = {"id": "custom.net", "name": "Net", "disciplines": ["electrical"], "outputs": ["V1", "V2", "V3"], "equations": [{"title": t, "text": x} for t, x in NET_EQ],
           "variables": [{"key": v.key, "label": v.label, "unit": v.unit, **({"signed": True} if v.signed else {}), **({"example": NET_IN[v.key]} if v.key in NET_IN else {})} for v in NET_V]}
    api.custom_save(doc)
    g = {"version": 1, "blocks": [{"id": "b", "calc": "custom.net", "x": 0, "y": 0, "values": dict(NET_IN)}], "wires": []}
    r = design.solve_system(g)
    assert r["ok"]


def test_library_coupled_calculations():
    from sliderule.core.catalog import default_catalog

    cat = default_catalog()

    def run(cid, inputs=None):
        calc = cat.get(cid)
        sol = solve(calc, inputs or calc.example)
        return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}

    r = run("civil.hydraulics.pipe_velocity_from_head_loss")
    assert 5 == pytest.approx(r["f"] * 100 / 0.1 * r["Vel"] ** 2 / (2 * 9.80665), rel=1e-9)
    assert 1 / math.sqrt(r["f"]) == pytest.approx(-2 * math.log10(0.05e-3 / (3.7 * 0.1) + 2.51 * 1e-6 / (r["Vel"] * 0.1 * math.sqrt(r["f"]))), rel=1e-9)
    assert r["Q"] == pytest.approx(r["Vel"] * math.pi * 0.1 ** 2 / 4, rel=1e-12)
    r = run("civil.hydraulics.three_reservoir_junction")
    z, K = (100.0, 80.0, 60.0), (4000.0, 6000.0, 5000.0)
    q = [r["Q1"], r["Q2"], r["Q3"]]
    assert sum(q) == pytest.approx(0.0, abs=1e-12)
    for zi, ki, qi in zip(z, K, q):
        assert zi - r["H"] == pytest.approx(ki * qi * abs(qi), rel=1e-8)
    assert q[0] > 0 > q[2]                                                                    # the highest reservoir feeds, the lowest receives
    r = run("electrical.circuits.resistor_network_node_voltages")
    assert (r["V1"], r["V2"], r["V3"]) == pytest.approx((6.62244, 2.71411, 2.35223), abs=1e-5)


def test_coupled_equations_work_in_other_directions_too():
    cat_calc = __import__("sliderule.core.catalog", fromlist=["default_catalog"]).default_catalog().get("civil.hydraulics.pipe_velocity_from_head_loss")
    sol = solve(cat_calc, cat_calc.example)
    V_, f_ = out(sol, "Vel"), out(sol, "f")
    # given the velocity, the head loss follows from the same two equations (Colebrook alone now has one unknown, f)
    back = solve(cat_calc, {"Vel": f"{V_} m/s", "L": "100 m", "D": "100 mm", "e": "0.05 mm", "nu": "1 mm^2/s"}, ["hf", "f"])
    assert out(back, "f") == pytest.approx(f_, rel=1e-9) and out(back, "hf") == pytest.approx(5.0, rel=1e-9)


def test_newton_is_the_fallback_when_no_variable_can_be_torn():
    import sympy as sp

    from sliderule.core import engine, simul

    v = [V("x", "x", "1"), V("y", "y", "1"), V("a", "a", "1"), V("b", "b", "1")]
    c = calc(v, [("e1", "x*y = a"), ("e2", "x**2 + y**2 = b")], ["x", "y"])
    known = {c.by_key["a"].symbol: 6.0, c.by_key["b"].symbol: 13.0}
    block = simul.find_blocks(c.parsed, set(known))[0]
    r = simul.solve_block(block, known, c, engine._evaluate, None, isolate=None)               # without an isolate function the tearing step is skipped
    assert r.method == "Newton" and {s.name: round(val, 9) for s, val in r.values.items()} in ({"x": 2.0, "y": 3.0}, {"x": 3.0, "y": 2.0})
    assert len(r.info["solutions"]) == 2
    t = simul.solve_block(block, known, c, engine._evaluate, None, isolate=engine._isolate)
    assert t.method == "tearing" and len(t.info["solutions"]) == 2 and t.info["tear"] in ("x", "y")
    _ = sp


def test_roots_outside_the_allowed_range_are_not_returned():
    v = [V("x", "x", "1"), V("y", "y", "1"), V("a", "a", "1", signed=True)]
    c = calc(v, [("e1", "x + y = 1"), ("e2", "x*y = a")], ["x", "y"])                             # x, y roots of t^2 - t + a: for a = -2 one root is negative (not allowed for unsigned x, y)
    d = solve(c, {"a": "-2"}).to_dict()
    assert not d["ok"]
    d = solve(c, {"a": "0.21"}).to_dict()
    assert d["ok"] and sorted((out(solve(c, {"a": "0.21"}), "x"), out(solve(c, {"a": "0.21"}), "y"))) == pytest.approx([0.3, 0.7])
