import contextlib
import io
import math

import pytest
from fastapi.testclient import TestClient

from sliderule import api, design, design_export, settings, usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import CustomError, calc_from_dict, calc_to_dict
from sliderule.core.numeric_ode import OdeError, rk45, solve_ivp, stiff
from sliderule.server import create_app

client = TestClient(create_app(serve_frontend=False))


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


# ---------------------------------------------------------------- the numerical solvers

def test_rk45_matches_known_solutions():
    r = solve_ivp(lambda t, y: [-y[0]], 0, [1.0], 5, outputs=[1, 2, 3])
    assert r.final[0] == pytest.approx(math.exp(-5), rel=1e-6) and r.ts == [0, 1, 2, 3, 5]
    assert r.ys[2][0] == pytest.approx(math.exp(-2), rel=1e-6)                       # outputs are hit exactly
    w = 2.0
    r = rk45(lambda t, y: [y[1], -w * w * y[0]], 0, [1.0, 0.0], 10)
    assert r.final[0] == pytest.approx(math.cos(w * 10), abs=1e-6)
    r = rk45(lambda t, y: [-y[0]], 5, [math.exp(-5)], 0)                              # backwards in time
    assert r.final[0] == pytest.approx(1.0, rel=1e-6)


def test_stiff_problems_fall_back_to_the_implicit_method():
    def robertson(t, y):
        a, b, c = y
        return [-0.04 * a + 1e4 * b * c, 0.04 * a - 1e4 * b * c - 3e7 * b * b, 3e7 * b * b]
    r = solve_ivp(robertson, 0, [1, 0, 0], 40)
    assert "stiff" in r.method and r.notes
    assert r.final == pytest.approx([0.7158, 9.185e-6, 0.2842], rel=2e-3)             # published reference values at t = 40
    f = lambda t, y: [-1000 * (y[0] - math.cos(t))]   # noqa: E731
    assert stiff(f, 0, [1.0], 10).final[0] == pytest.approx(solve_ivp(f, 0, [1.0], 10).final[0], rel=1e-5)


def test_blow_up_and_domain_errors_are_reported():
    with pytest.raises(OdeError, match="not finite"):
        solve_ivp(lambda t, y: [y[0] ** 2], 0, [1.0], 2)
    with pytest.raises(OdeError, match="could not be evaluated"):
        solve_ivp(lambda t, y: [math.log(y[0])], 0, [-1.0], 1)


# ---------------------------------------------------------------- building a calculation from an ODE

COOL_VARS = [V("T", "Temperature at time t", "K"), V("T0", "Initial temperature", "K"), V("Ta", "Ambient", "K"), V("k", "Rate", "1/s"), V("t", "Time", "s")]
COOL = {"title": "Newton cooling", "independent": "t", "equations": ["diff(T, t) = -k*(T - Ta)"], "initial": ["T = T0"]}
EX = {"T0": "363.15 K", "Ta": "293.15 K", "k": "0.01 1/s", "t": "120 s"}


def cool(**changes):
    return Calculation(id="custom.cool", name="c", disciplines=["mechanical"], description="", variables=list(COOL_VARS), equations=[], outputs=["T"],
                       custom=True, odes=[{**COOL, **changes}])


def out(sol, key):
    return next(o["si_value"] for o in sol.to_dict()["outputs"] if o["key"] == key)


def test_closed_form_is_found_and_can_be_rearranged_in_any_direction():
    c = cool()
    assert not c.parsed_odes[0].numeric and str(c.parsed[0].rhs) == "Ta + (T0 - Ta)*exp(-k*t)"
    T = 293.15 + 70 * math.exp(-1.2)
    assert out(solve(c, EX), "T") == pytest.approx(T)
    assert out(solve(c, {"T": f"{T} K", "T0": "363.15 K", "Ta": "293.15 K", "k": "0.01 1/s"}, ["t"]), "t") == pytest.approx(120.0, rel=1e-9)
    assert out(solve(c, {"T": f"{T} K", "T0": "363.15 K", "Ta": "293.15 K", "t": "120 s"}, ["k"]), "k") == pytest.approx(0.01, rel=1e-9)
    assert out(solve(c, {"T": f"{T} K", "Ta": "293.15 K", "k": "0.01 1/s", "t": "120 s"}, ["T0"]), "T0") == pytest.approx(363.15, rel=1e-9)


def test_numeric_method_agrees_and_can_also_be_inverted_by_root_finding():
    c = cool(method="numeric")
    assert c.parsed_odes[0].numeric
    assert out(solve(c, EX), "T") == pytest.approx(293.15 + 70 * math.exp(-1.2), rel=1e-7)
    T = 293.15 + 70 * math.exp(-1.2)
    back = solve(c, {"T": f"{T} K", "T0": "363.15 K", "Ta": "293.15 K", "t": "120 s"}, ["k"]).to_dict()      # no closed form was used: k is found numerically
    assert back["ok"] and back["outputs"][0]["si_value"] == pytest.approx(0.01, rel=1e-6)
    assert "NUMERIC_INVERSION" in [d["code"] for d in back["diagnostics"]]


def test_second_order_and_systems_closed_form():
    v = [V("x", "Displacement", "m", signed=True), V("x0", "x0", "m", signed=True), V("v0", "v0", "m/s", signed=True), V("w", "Angular frequency", "1/s"), V("t", "Time", "s")]
    c = Calculation(id="custom.sho", name="s", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["x"], custom=True,
                    odes=[{"independent": "t", "equations": ["diff(x, t, 2) = -w**2*x"], "initial": ["x = x0", "diff(x, t) = v0"]}])
    assert not c.parsed_odes[0].numeric
    got = out(solve(c, {"x0": "1 m", "v0": "0.5 m/s", "w": "2 1/s", "t": "1.3 s"}), "x")
    assert got == pytest.approx(math.cos(2.6) + 0.25 * math.sin(2.6), rel=1e-9)
    sysv = [V("A", "Amount in A", "mol", signed=True), V("B", "Amount in B", "mol", signed=True), V("A0", "A0", "mol"), V("B0", "B0", "mol"), V("kf", "kf", "1/s"), V("kr", "kr", "1/s"), V("t", "t", "s")]
    c2 = Calculation(id="custom.eq", name="s", disciplines=["chemical"], description="", variables=sysv, equations=[], outputs=["A", "B"], custom=True,
                     odes=[{"independent": "t", "equations": ["diff(A, t) = -kf*A + kr*B", "diff(B, t) = kf*A - kr*B"], "initial": ["A = A0", "B = B0"]}])
    s = solve(c2, {"A0": "1 mol", "B0": "0 mol", "kf": "0.3 1/s", "kr": "0.1 1/s", "t": "5 s"}).to_dict()
    A = {o["key"]: o["si_value"] for o in s["outputs"]}
    k = 0.4
    assert A["A"] == pytest.approx(0.25 + 0.75 * math.exp(-k * 5), rel=1e-9) and A["A"] + A["B"] == pytest.approx(1.0)


def test_underdamped_closed_form_with_complex_intermediates_gives_a_real_answer():
    v = [V("x", "Displacement", "m", signed=True), V("x0", "x0", "m", signed=True), V("v0", "v0", "m/s", signed=True), V("m", "m", "kg"), V("c", "c", "N*s/m"), V("k", "k", "N/m"), V("t", "t", "s")]
    c = Calculation(id="custom.dho", name="s", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["x"], custom=True,
                    odes=[{"independent": "t", "equations": ["m*diff(x, t, 2) + c*diff(x, t) + k*x = 0"], "initial": ["x = x0", "diff(x, t) = v0"]}])
    got = out(solve(c, {"x0": "0.02 m", "v0": "0 m/s", "m": "2 kg", "c": "6 N*s/m", "k": "800 N/m", "t": "1.5 s"}), "x")
    w, z = math.sqrt(400), 6 / (2 * math.sqrt(1600))
    wd = w * math.sqrt(1 - z * z)
    assert got == pytest.approx(0.02 * math.exp(-z * w * 1.5) * (math.cos(wd * 1.5) + z * w / wd * math.sin(wd * 1.5)), rel=1e-9)


# ---------------------------------------------------------------- what is refused, and how it is explained

def test_errors_are_specific_and_use_the_users_names():
    with pytest.raises(Exception, match="missing initial value for T"):
        cool(initial=[])
    with pytest.raises(Exception) as e:
        cool(equations=["diff(T, t) = -k*(T - t)"])                       # K/s vs K vs s
    assert "T__0" not in str(e.value) and "different dimensions" in str(e.value)
    with pytest.raises(Exception, match="initial value of T"):
        cool(initial=["T = k"])                                           # wrong dimension
    with pytest.raises(Exception, match="independent"):
        cool(independent="nope")
    with pytest.raises(Exception, match="no derivative of the form"):
        cool(equations=["T = k*t"])
    with pytest.raises(Exception, match="one equation per unknown"):
        cool(equations=["diff(T, t) = -k*T", "T = Ta"])
    with pytest.raises(Exception, match="must run from the start"):
        cool(equations=["diff(T, t) = -k*integrate(T, (s, 1, t))"])                 # an integral of the unknown must start at the start
    with pytest.raises(Exception, match="no closed-form"):
        Calculation(id="custom.q", name="q", disciplines=["mechanical"], description="", custom=True, equations=[], outputs=["v"],
                    variables=[V("v", "v", "m/s"), V("v0", "v0", "m/s"), V("c", "c", "1/m"), V("g", "g", "m/s^2"), V("t", "t", "s")],
                    odes=[{"independent": "t", "method": "symbolic", "equations": ["diff(v, t) = g - c*v**2"], "initial": ["v = v0"]}])
    assert cool(initial=["T = T0"], start="0").parsed_odes                # a literal zero start is valid whatever the dimension
    zero = Calculation(id="custom.z", name="z", disciplines=["electrical"], description="", custom=True, equations=[], outputs=["vc"],
                       variables=[V("vc", "Voltage", "V"), V("Vs", "Source", "V"), V("t", "Time", "s"), V("tau", "Time constant", "s")],
                       odes=[{"independent": "t", "equations": ["diff(vc, t) = (Vs - vc)/tau"], "initial": ["vc = 0"]}])    # a literal zero initial value too
    assert out(solve(zero, {"Vs": "10 V", "tau": "2 s", "t": "2 s"}), "vc") == pytest.approx(10 * (1 - math.exp(-1)))


def test_unsafe_ode_text_never_runs(tmp_path):
    marker = tmp_path / "pwned"
    doc = {"id": "custom.evil", "name": "e", "disciplines": ["mechanical"],
           "variables": [{"key": "T", "label": "T", "unit": "K"}, {"key": "T0", "label": "T0", "unit": "K"}, {"key": "k", "label": "k", "unit": "1/s"}, {"key": "t", "label": "t", "unit": "s"}],
           "odes": [{"independent": "t", "equations": [f"diff(T, t) = -k*T + __import__('os').system('touch {marker}')"], "initial": ["T = T0"]}], "outputs": ["T"]}
    with pytest.raises(CustomError):
        calc_from_dict(doc)
    doc["odes"][0] = {"independent": "t", "equations": ["diff(T, t) = -k*T"], "initial": [f"T = __import__('os').system('touch {marker}')"]}
    with pytest.raises(CustomError):
        calc_from_dict(doc)
    assert not marker.exists()


# ---------------------------------------------------------------- steps, plot data and tables

def test_steps_show_the_equation_conditions_and_method():
    s = solve(cool(), EX)
    sym = [(st.title, [(ln.latex, ln.note) for ln in st.lines]) for st in s.steps["symbolic"]]
    flat = [n for _t, lines in sym for _l, n in lines]
    assert "governing differential equation, as written" in flat and "initial condition" in flat
    assert any("closed-form solution of the differential equation" in n for n in flat)
    assert any(r"\frac{d}{d t} T" in latex for _t, lines in sym for latex, _n in lines)
    num = solve(cool(method="numeric"), EX)
    notes = [ln.note for st in num.steps["numeric"] for ln in st.lines]
    assert any("numerical integration of the differential equation" in n for n in notes)
    assert any("RK45" in ln.latex for st in num.steps["numeric"] for ln in st.lines)


def test_series_and_table_agree_between_closed_form_and_numeric():
    closed, numeric = solve(cool(), EX, ode_times=["0 s", "30 s", "1 min", "500 s"]), solve(cool(method="numeric"), EX, ode_times=["0 s", "30 s", "1 min", "500 s"])
    for sol in (closed, numeric):
        assert len(sol.series) == 1 and len(sol.series[0]["t"]) == 201
        assert sol.series[0]["independent"]["unit"] == "s" and sol.series[0]["series"][0]["key"] == "T"
        assert [r["t"] for r in sol.table] == ["0", "30", "60", "120"] and sol.table[-1]["is_evaluation_time"]
        assert any(d.code == "TIME_OUTSIDE" for d in sol.diagnostics)
    a, b = closed.series[0]["series"][0]["values"], numeric.series[0]["series"][0]["values"]
    assert max(abs(x - y) for x, y in zip(a, b)) < 1e-5
    assert closed.series[0]["method"]["method"].startswith("closed form") and numeric.series[0]["method"]["method"].startswith("RK45")


def test_table_and_series_use_the_chosen_units():
    s = solve(cool(), {**EX, "t": "2 min"}, output_units={"T": "degC"}, ode_times=["1 min"])
    assert s.series[0]["independent"]["unit"] == "min" and s.series[0]["series"][0]["unit"] == "°C"
    assert s.series[0]["t"][-1] == pytest.approx(2.0) and s.series[0]["series"][0]["values"][0] == pytest.approx(90.0)
    assert [r["t"] for r in s.table] == ["1", "2"] and s.table[0]["units"]["T"] == "°C"


# ---------------------------------------------------------------- library, API, files, System Design

def test_library_differential_equations_match_hand_calculations():
    def val(cid, key, **kw):
        c = api.get_calculation(cid)
        r = api.solve(cid, dict(c["example"]), **kw)
        assert not [d for d in r["diagnostics"] if d["level"] != "info"], r["diagnostics"]
        return {o["key"]: o["si_value"] for o in r["outputs"]}[key]
    assert val("chemical.reactors.mixing_tank_transient", "C") == pytest.approx(0.5 * (1 - math.exp(-2)) * 1000)       # mol/m^3
    assert val("mechanical.thermo.newton_cooling_transient", "T") == pytest.approx(293.15 + 70 * math.exp(-3), rel=1e-9)
    assert val("mechanical.dynamics.fall_with_quadratic_drag", "v") == pytest.approx(math.sqrt(80 * 9.80665 / 0.25) * math.tanh(math.sqrt(9.80665 * 0.25 / 80) * 10), rel=1e-6)
    assert val("electrical.circuits.series_rlc_step_response", "vc") == pytest.approx(10 * (1 - 3 * math.exp(-2)), rel=1e-6)     # critically damped
    w, z = math.sqrt(400), 6 / (2 * math.sqrt(1600))
    wd = w * math.sqrt(1 - z * z)
    assert val("mechanical.dynamics.damped_oscillator_response", "x") == pytest.approx(0.02 * math.exp(-z * w * 1.5) * (math.cos(wd * 1.5) + z * w / wd * math.sin(wd * 1.5)), abs=1e-9)    # SI metres; the value is near a zero crossing


def test_api_exposes_the_differential_equations_and_accepts_times():
    cid = "mechanical.dynamics.damped_oscillator_response"
    d = api.get_calculation(cid)
    o = d["odes"][0]
    assert o["kind"] == "numeric" and o["independent"] == "t" and o["dependents"] == ["x", "v"] and o["latex"] and o["conditions"]
    assert all(e["title"] for e in d["equations"]) and d["equations"] == []               # the pseudo-equations of the solver are not listed
    r = api.solve(cid, dict(d["example"]), ode_times=["0.5 s", "1 s"])
    assert [row["t"] for row in r["table"]] == ["0.5", "1", "1.5"] and len(r["series"][0]["series"]) == 2
    http = client.post(f"/api/calculations/{cid}/solve", json={"inputs": d["example"], "ode_times": ["0.5 s"]}).json()
    assert [row["t"] for row in http["table"]] == ["0.5", "1.5"]
    assert api.get_calculation("mechanical.thermo.newton_cooling_transient")["odes"][0]["kind"] == "closed"


def test_custom_validate_save_and_file_round_trip_with_odes():
    doc = {"id": "custom.cool", "name": "Cooling", "disciplines": ["mechanical"], "odes": [COOL],
           "variables": [{"key": v.key, "label": v.label, "unit": v.unit, **({"example": EX[v.key]} if v.key in EX else {})} for v in COOL_VARS], "outputs": ["T"]}
    v = api.custom_validate(doc)
    assert v["ok"] and v["odes"][0]["kind"] == "closed" and v["example_result"]["outputs"][0]["text"].startswith("314.2")
    saved = api.custom_save(doc)["calculation"]
    assert saved["odes"][0]["equations"] == COOL["equations"] and saved["equations"] == []
    back = calc_to_dict(calc_from_dict(saved))
    assert back == saved
    bad = api.custom_validate({**doc, "odes": [{**COOL, "initial": []}]})
    assert not bad["ok"] and bad["errors"][0]["field"] == "odes" and "missing initial value" in bad["errors"][0]["message"]


def test_system_design_runs_blocks_with_differential_equations_and_exports_them():
    doc = {"id": "custom.cool", "name": "Cooling", "disciplines": ["mechanical"], "odes": [COOL],
           "variables": [{"key": v.key, "label": v.label, "unit": v.unit, **({"example": EX[v.key]} if v.key in EX else {})} for v in COOL_VARS], "outputs": ["T"]}
    api.custom_save(doc)
    api.custom_save({**doc, "id": "custom.cool_num", "odes": [{**COOL, "method": "numeric"}]})
    for cid, numeric in (("custom.cool", False), ("custom.cool_num", True)):
        g = {"version": 1, "blocks": [{"id": "b", "calc": cid, "x": 0, "y": 0, "values": dict(EX)}], "wires": []}
        r = design.solve_system(g)
        assert r["ok"] and next(o for o in r["blocks"]["b"]["outputs"] if o["key"] == "T")["si_value"] == pytest.approx(293.15 + 70 * math.exp(-1.2), rel=1e-6)
        for fmt in ("latex", "markdown", "html"):
            c = design_export.export_system(g, fmt)
            assert c["ok"] and ("differential equation, as written" in c["content"] or "as written" in c["content"])
        py = design_export.export_system(g, "python")
        assert py["ok"], py["diagnostics"]                  # a numerically solved initial-value problem is integrated again by the script
        assert ("scipy" in py["content"]) == numeric
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(compile(py["content"], "s.py", "exec"), {"__name__": "__main__"})
        assert "matches the SlideRule reference values" in buf.getvalue()


def test_long_integrations_obey_the_time_limit():
    import time

    doc = {"id": "custom.long", "name": "l", "disciplines": ["mechanical"], "outputs": ["x", "w"],
           "variables": [{"key": "x", "label": "x", "unit": "m", "signed": True}, {"key": "w", "label": "w", "unit": "m/s", "signed": True},
                         {"key": "x0", "label": "x0", "unit": "m", "signed": True}, {"key": "om", "label": "om", "unit": "1/s"}, {"key": "t", "label": "t", "unit": "s"}],
           "odes": [{"independent": "t", "method": "numeric", "equations": ["diff(x, t) = w", "diff(w, t) = -om**2*x"], "initial": ["x = x0", "w = 0"]}]}
    api.custom_save(doc)
    settings.update(timeout_seconds=1)
    t0 = time.monotonic()
    r = api.handle("solve", {"calc_id": "custom.long", "inputs": {"x0": "1 m", "om": "1000 1/s", "t": "1000000 s"}})
    assert not r["ok"] and r["error"]["code"] == "TIMEOUT" and time.monotonic() - t0 < 4
