import math
import time

import pytest
from fastapi.testclient import TestClient

from sliderule import api, cli, design, settings, usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.rootfind import NoBracket, brent, find_bracket, grid
from sliderule.server import create_app

client = TestClient(create_app(serve_frontend=False))


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def calc(eqs, variables, outputs, **kw):
    return Calculation(id="custom.inv", name="inv", disciplines=["mechanical"], description="", custom=True, equations=eqs, outputs=outputs, variables=variables, **kw)


def value(c, inputs, target, **kw):
    r = solve(c, inputs, [target], **kw).to_dict()
    assert r["ok"], r["diagnostics"]
    return r["outputs"][0]["si_value"], r


# ---------------------------------------------------------------- the root finder

def test_brent_and_bracket_scan():
    assert brent(lambda x: math.cos(x) - x, 0, 1).x == pytest.approx(0.7390851332151607, rel=1e-12)
    assert brent(lambda x: x ** 3 - 2, 0, 5).x == pytest.approx(2 ** (1 / 3), rel=1e-12)
    a, b, fa, fb, n = find_bracket(lambda x: math.log(x) - 3, grid(1e-6, 1e6, 50))
    assert a < math.exp(3) < b and brent(lambda x: math.log(x) - 3, a, b, fa, fb).x == pytest.approx(math.exp(3), rel=1e-12)
    with pytest.raises(NoBracket):
        brent(lambda x: x * x + 1, -1, 1)
    with pytest.raises(NoBracket):
        find_bracket(lambda x: x * x + 1, grid(-3, 3, 20))
    xs = grid(1e-3, 1e3, 7)
    assert xs[0] == pytest.approx(1e-3) and xs[-1] == pytest.approx(1e3) and xs[1] / xs[0] == pytest.approx(xs[2] / xs[1])          # geometric
    assert grid(0, 1, 5) == [0, 0.25, 0.5, 0.75, 1.0]
    # undefined points are skipped, not fatal
    a, b, *_ = find_bracket(lambda x: math.sqrt(x - 1) - 1, [0.0, 0.5, 1.5, 3.0])
    assert (a, b) == (1.5, 3.0)


# ---------------------------------------------------------------- implicit equations are solved numerically

def colebrook():
    return calc(["1/sqrt(f) = -2*log10(eps/(3.7*D) + 2.51/(Re*sqrt(f)))"],
                [V("f", "Friction factor", "1"), V("Re", "Reynolds number", "1"), V("eps", "Roughness", "mm"), V("D", "Diameter", "mm")], ["f"])


def test_colebrook_friction_factor_is_found_without_a_closed_form():
    c = colebrook()
    f, r = value(c, {"Re": "1e5", "eps": "0.05 mm", "D": "100 mm"}, "f")
    x = 0.02
    for _ in range(60):                                                  # fixed-point iteration as the independent reference
        x = 1 / (-2 * math.log10(0.0005 / 3.7 + 2.51 / (1e5 * math.sqrt(x)))) ** 2
    assert f == pytest.approx(x, rel=1e-9)
    assert "NUMERIC_INVERSION" in [d["code"] for d in r["diagnostics"]]


def test_the_other_unknowns_of_an_implicit_equation_are_found_too():
    c = colebrook()
    re_, _ = value(c, {"f": "0.0185", "eps": "0.05 mm", "D": "100 mm"}, "Re")        # explicit in Re
    f, _ = value(c, {"Re": f"{re_}", "eps": "0.05 mm", "D": "100 mm"}, "f")
    assert f == pytest.approx(0.0185, rel=1e-9)


def test_values_needed_for_the_target_are_found_numerically_first():
    c = calc(["x + exp(x) = a", "z = 2*x"], [V("x", "x", "1", signed=True), V("a", "a", "1"), V("z", "z", "1", signed=True)], ["z"])
    z, _ = value(c, {"a": "5"}, "z")
    x = brent(lambda v: v + math.exp(v) - 5, 0, 5).x
    assert z == pytest.approx(2 * x, rel=1e-10)


# ---------------------------------------------------------------- brackets, ranges, signs

def poly():
    return calc(["y = x*(x - 3)*(x - 6)"], [V("y", "y", "1", signed=True), V("x", "x", "1", signed=True)], ["x"])


def test_automatic_scan_prefers_small_magnitudes_and_a_range_selects_another_root():
    c = poly()
    first, r = value(c, {"y": "0"}, "x")
    assert first == pytest.approx(3.0, abs=1e-9)                                  # the root at 0 is touched exactly at the grid origin, 3 is the first sign change
    assert "give a search range" in [d["message"] for d in r["diagnostics"] if d["code"] == "NUMERIC_INVERSION"][0]
    second, r2 = value(c, {"y": "0"}, "x", search={"x": [5, 7]})
    assert second == pytest.approx(6.0, abs=1e-9) and "give a search range" not in r2["diagnostics"][0]["message"]
    neg, _ = value(calc(["y = x**3 + x"], [V("y", "y", "1", signed=True), V("x", "x", "1", signed=True)], ["x"]), {"y": "-10"}, "x")     # a negative root: signed variables scan both signs
    assert neg == pytest.approx(brent(lambda v: v ** 3 + v + 10, -5, 0).x, rel=1e-10)


def test_search_ranges_take_units_and_are_validated():
    c = calc(["T = T0*exp(-k*t)"], [V("T", "T", "K"), V("T0", "T0", "K"), V("k", "k", "1/s"), V("t", "t", "s")], ["k"])
    # exp(-k t) = T/T0: with strings the range carries its unit
    k, _ = value(c, {"T": "150 K", "T0": "300 K", "t": "10 s"}, "k", search={"k": ["0.001 1/min", "10 1/min"]})
    assert k == pytest.approx(math.log(2) / 10, rel=1e-9)
    for bad in ({"k": [1]}, {"k": [5, 1]}, {"nope": [1, 2]}, {"k": ["1 m", "2 m"]}):
        r = solve(c, {"T": "150 K", "T0": "300 K", "t": "10 s"}, ["k"], search=bad).to_dict()
        assert not r["ok"] and r["diagnostics"][0]["code"] == "BAD_SEARCH"


def test_no_root_is_explained_and_a_discontinuity_is_not_mistaken_for_one():
    c = calc(["y = x**2 + 1"], [V("y", "y", "1"), V("x", "x", "1", signed=True)], ["x"])
    r = solve(c, {"y": "0.5"}, ["x"]).to_dict()
    assert not r["ok"] and "no sign change" in r["diagnostics"][0]["message"] and "search range" in r["diagnostics"][0]["message"]
    pole = calc(["y = 1/(x - 2)"], [V("y", "y", "1", signed=True), V("x", "x", "1")], ["x"])
    r2 = solve(pole, {"y": "0"}, ["x"]).to_dict()
    assert not r2["ok"] and "discontinuity" in r2["diagnostics"][0]["message"]


def test_steps_describe_the_root_finding():
    s = solve(colebrook(), {"Re": "1e5", "eps": "0.05 mm", "D": "100 mm"}, ["f"])
    sym = [ln for st in s.steps["symbolic"] for ln in st.lines]
    num = [ln for st in s.steps["numeric"] for ln in st.lines]
    assert any("root of F" in ln.note or "root of F" in ln.latex or "bracketing and Brent" in ln.note for ln in sym)
    assert any("Brent's method" in ln.note for ln in num) and any("bracket" in ln.latex for ln in num)


# ---------------------------------------------------------------- everywhere it matters

def test_library_calculations_are_unaffected_when_the_symbolic_route_works():
    cid = next(c["id"] for c in api.list_calculations("ohm")["results"])
    d = api.get_calculation(cid)
    r = api.solve(cid, dict(d["example"]))
    assert "NUMERIC_INVERSION" not in [x["code"] for x in r["diagnostics"]]


def test_api_http_and_cli_accept_a_search_range(tmp_path, capsys):
    doc = {"id": "custom.cool", "name": "Cooling", "disciplines": ["mechanical"], "outputs": ["T"],
           "variables": [{"key": "T", "label": "T", "unit": "K"}, {"key": "T0", "label": "T0", "unit": "K"}, {"key": "Ta", "label": "Ta", "unit": "K"},
                         {"key": "k", "label": "k", "unit": "1/s"}, {"key": "t", "label": "t", "unit": "s"}],
           "odes": [{"independent": "t", "method": "numeric", "equations": ["diff(T, t) = -k*(T - Ta)"], "initial": ["T = T0"]}]}
    api.custom_save(doc)
    T = 293.15 + 70 * math.exp(-1.2)
    inputs = {"T": f"{T} K", "T0": "363.15 K", "Ta": "293.15 K", "t": "120 s"}
    r = api.solve("custom.cool", inputs, ["k"], search={"k": ["0.001 1/s", "1 1/s"]})
    assert r["ok"] and r["outputs"][0]["si_value"] == pytest.approx(0.01, rel=1e-6)
    h = client.post("/api/calculations/custom.cool/solve", json={"inputs": inputs, "solve_for": ["k"], "search": {"k": ["0.001 1/s", "1 1/s"]}}).json()
    assert h["ok"] and h["outputs"][0]["si_value"] == pytest.approx(0.01, rel=1e-6)
    assert cli.main(["--equations-dir", str(tmp_path), "solve", "custom.cool", *[f"{k}={v}" for k, v in inputs.items()], "--for", "k", "--search", "k=0.001 1/s:1 1/s"]) in (0, 2)


def test_system_design_blocks_can_be_solved_for_values_that_need_numerical_inversion():
    doc = {"id": "custom.cool", "name": "Cooling", "disciplines": ["mechanical"], "outputs": ["T"],
           "variables": [{"key": "T", "label": "T", "unit": "K"}, {"key": "T0", "label": "T0", "unit": "K"}, {"key": "Ta", "label": "Ta", "unit": "K"},
                         {"key": "k", "label": "k", "unit": "1/s"}, {"key": "t", "label": "t", "unit": "s"}],
           "odes": [{"independent": "t", "method": "numeric", "equations": ["diff(T, t) = -k*(T - Ta)"], "initial": ["T = T0"]}]}
    api.custom_save(doc)
    T = 293.15 + 70 * math.exp(-1.2)
    assert design.check_block(api.default_catalog().get("custom.cool"), {"k": "output", "T": "input"})["ok"]
    g = {"version": 1, "blocks": [{"id": "b", "calc": "custom.cool", "x": 0, "y": 0, "roles": {"k": "output", "T": "input"},
                                   "values": {"T": f"{T} K", "T0": "363.15 K", "Ta": "293.15 K", "t": "120 s"}}], "wires": []}
    r = design.solve_system(g)
    assert r["ok"] and next(o for o in r["blocks"]["b"]["outputs"] if o["key"] == "k")["si_value"] == pytest.approx(0.01, rel=1e-6)


def test_the_time_limit_applies_to_numerical_inversion():
    doc = {"id": "custom.long", "name": "l", "disciplines": ["mechanical"], "outputs": ["x", "w"],
           "variables": [{"key": "x", "label": "x", "unit": "m", "signed": True}, {"key": "w", "label": "w", "unit": "m/s", "signed": True},
                         {"key": "x0", "label": "x0", "unit": "m", "signed": True}, {"key": "om", "label": "om", "unit": "1/s"}, {"key": "t", "label": "t", "unit": "s"}],
           "odes": [{"independent": "t", "method": "numeric", "equations": ["diff(x, t) = w", "diff(w, t) = -om**2*x"], "initial": ["x = x0", "w = 0"]}]}
    api.custom_save(doc)
    settings.update(timeout_seconds=1)
    t0 = time.monotonic()
    r = api.handle("solve", {"calc_id": "custom.long", "inputs": {"x": "0.5 m", "x0": "1 m", "t": "1000 s"}, "solve_for": ["om"], "search": {"om": [100, 1000]}})
    assert not r["ok"] and r["error"]["code"] == "TIMEOUT" and time.monotonic() - t0 < 4
