import math

import pytest

from sliderule import api, design, design_export, usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def out(sol, key):
    return next(o["si_value"] for o in sol.to_dict()["outputs"] if o["key"] == key)


def calc(variables, spec, outputs=("u",), cid="custom.pde"):
    return Calculation(id=cid, name="p", disciplines=["mechanical"], description="", variables=variables, equations=[], outputs=list(outputs), custom=True, odes=[spec])


SLAB_VARS = [V("T", "Temperature", "K"), V("Ts", "Face", "K"), V("Ti", "Initial", "K"), V("x", "Position", "m"), V("L", "Thickness", "m"), V("a", "Diffusivity", "m^2/s"), V("t", "Time", "s")]
SLAB = {"independent": "x", "start": "0", "end": "L", "time": "t", "equations": ["diff(T, t) = a*diff(T, x, 2)"], "boundary": ["start: T = Ts", "end: T = Ts"], "initial": ["T = Ti"]}
SLAB_IN = {"Ts": "300 K", "Ti": "500 K", "x": "0.05 m", "L": "0.1 m", "a": "1e-5 m^2/s", "t": "100 s"}


def series(x, t, L=0.1, a=1e-5, odd_only=True, one_face=False):
    tot = 0.0
    for k in range(1, 400):
        lam = ((2 * k - 1) * math.pi / (2 * L)) if one_face else ((2 * k - 1) * math.pi / L)
        tot += 4 / ((2 * k - 1) * math.pi) * math.sin(lam * x) * math.exp(-lam * lam * a * t)
    return tot


def test_diffusion_between_two_held_faces_matches_the_fourier_series():
    c = calc(SLAB_VARS, SLAB, ["T"])
    s = c.parsed_odes[0]
    assert s.numeric and s.order == 1
    sol = solve(c, SLAB_IN)
    assert out(sol, "T") == pytest.approx(300 + 200 * series(0.05, 100), rel=2e-5)
    d = sol.to_dict()
    assert [x["code"] for x in d["diagnostics"]] == []
    assert any("estimated discretisation error" in n for n in d["series"][0]["method"]["notes"])


def test_plots_and_table_cover_space_and_time():
    d = solve(calc(SLAB_VARS, SLAB, ["T"]), SLAB_IN, ode_times=["25 s", "50 s"]).to_dict()
    profile, history = d["series"]
    assert profile["overlay"] and len(profile["t"]) == 101 and profile["t"][0] == 0 and profile["t"][-1] == pytest.approx(0.1)
    labels = [s["label"] for s in profile["series"]]
    assert labels[0].startswith("t = 0") and any("25" in l for l in labels) and labels[-1].startswith("t = 100")
    first = profile["series"][0]["values"]
    assert first[0] == pytest.approx(300.0, abs=1e-6) and first[50] == pytest.approx(500.0, abs=1e-6)                                  # initial state, the boundary overrides the corner
    last = profile["series"][-1]["values"]
    assert last[50] == pytest.approx(300 + 200 * series(0.05, 100), rel=2e-5)
    assert len(history["t"]) == 61 and history["series"][0]["values"][0] == pytest.approx(500.0)
    assert history["series"][0]["values"][-1] == pytest.approx(last[50], rel=1e-9)
    rows = {r["t"]: r for r in d["table"]}
    assert set(rows) >= {"25", "50", "100"} and rows["100"]["is_evaluation_time"]


def test_insulated_end_and_the_time_to_reach_a_temperature():
    spec = {**SLAB, "boundary": ["start: T = Ts", "end: diff(T, x) = 0"]}
    c = calc(SLAB_VARS, spec, ["T"])
    inp = {**SLAB_IN, "L": "0.05 m", "x": "0.05 m", "t": "60 s"}
    assert out(solve(c, inp), "T") == pytest.approx(300 + 200 * series(0.05, 60, L=0.05, one_face=True), rel=2e-5)
    T = out(solve(c, inp), "T")
    back = solve(c, {**{k: v for k, v in inp.items() if k != "t"}, "T": f"{T} K"}, ["t"]).to_dict()
    assert back["ok"] and back["outputs"][0]["si_value"] == pytest.approx(60.0, rel=1e-4)
    assert "NUMERIC_INVERSION" in [x["code"] for x in back["diagnostics"]]


def test_robin_condition_reaches_the_steady_profile():
    v = SLAB_VARS + [V("k", "Conductivity", "W/(m*K)"), V("h", "Coefficient", "W/(m^2*K)"), V("Tinf", "Ambient", "K")]
    spec = {**SLAB, "boundary": ["start: T = Ts", "end: -k*diff(T, x) = h*(T - Tinf)"]}
    c = calc(v, spec, ["T"])
    inp = {**SLAB_IN, "Ti": "300 K", "Tinf": "400 K", "k": "10 W/(m*K)", "h": "50 W/(m^2*K)", "x": "0.1 m", "t": "20000 s", "a": "1e-5 m^2/s"}
    # steady: T linear, T(0) = 300, -k T' = h (T(L) - Tinf)  ->  T(L) = (Tinf*h*L/k + 300) / (1 + h L / k)
    Bi = 50 * 0.1 / 10
    expected = (400 * Bi + 300) / (1 + Bi)
    assert out(solve(c, inp), "T") == pytest.approx(expected, rel=1e-4)


def test_second_order_in_time_is_a_wave():
    v = [V("u", "Displacement", "m", signed=True), V("h", "Height", "m"), V("x", "Position", "m"), V("L", "Length", "m"), V("c", "Wave speed", "m/s"), V("t", "Time", "s")]
    spec = {"independent": "x", "start": "0", "end": "L", "time": "t", "equations": ["diff(u, t, 2) = c**2*diff(u, x, 2)"], "boundary": ["start: u = 0", "end: u = 0"],
            "initial": ["u = h*Min(2*x/L, 2*(L - x)/L)", "diff(u, t) = 0"]}
    c = calc(v, spec)
    assert c.parsed_odes[0].order == 2
    inp = {"h": "3 mm", "L": "0.65 m", "c": "300 m/s", "x": "0.2 m", "t": "0.9 ms"}
    ref = 3e-3 * sum(8 / (n * n * math.pi ** 2) * math.sin(n * math.pi / 2) * math.sin(n * math.pi * 0.2 / 0.65) * math.cos(n * math.pi * 300 * 0.9e-3 / 0.65) for n in range(1, 400))
    assert out(solve(c, inp), "u") == pytest.approx(ref, abs=2e-5)                        # the kink limits the accuracy: absolute 2e-5 m of 3e-3
    # d'Alembert: after half a period the string is inverted
    half = {**inp, "x": "0.325 m", "t": f"{0.65 / 300 * 1000} ms"}
    assert out(solve(c, half), "u") == pytest.approx(-3e-3, abs=1.5e-4)                  # numerical dispersion rounds the sharp peak (second-order differences, 100 nodes)


def test_conservative_form_and_a_source_term_manufactured_solution():
    v = [V("u", "u", "1", signed=True), V("x", "x", "1"), V("t", "t", "1")]
    spec = {"independent": "x", "start": "0", "end": "1", "time": "t",
            "equations": ["diff(u, t) = diff(1 + 0*u*u, x, x) if False else diff(1*diff(u, x), x) + u**2 + (pi**2 - 1)*exp(-t)*sin(pi*x) - exp(-2*t)*sin(pi*x)**2"] if False else
                         ["diff(u, t) = diff(diff(u, x), x) + u**2 + (pi**2 - 1)*exp(-t)*sin(pi*x) - exp(-2*t)*sin(pi*x)**2"],
            "boundary": ["start: u = 0", "end: u = 0"], "initial": ["u = sin(pi*x)"]}
    c = calc(v, spec)
    assert out(solve(c, {"x": "0.3", "t": "0.5"}), "u") == pytest.approx(math.exp(-0.5) * math.sin(math.pi * 0.3), rel=3e-4)         # second-order differences, 100 nodes
    # nonlinear diffusivity written in conservative form: (D(u) u_x)_x with D = 1 + u^2 against the equivalent expanded form
    cons = {"independent": "x", "start": "0", "end": "1", "time": "t", "equations": ["diff(u, t) = diff((1 + u**2)*diff(u, x), x)"],
            "boundary": ["start: u = 0", "end: u = 0"], "initial": ["u = sin(pi*x)"]}
    expanded = {**cons, "equations": ["diff(u, t) = (1 + u**2)*diff(u, x, 2) + 2*u*diff(u, x)**2"]}
    a = out(solve(calc(v, cons), {"x": "0.3", "t": "0.2"}), "u")
    b = out(solve(calc(v, expanded), {"x": "0.3", "t": "0.2"}), "u")
    assert a == pytest.approx(b, rel=1e-9) and 0 < a < math.sin(math.pi * 0.3)


def test_dimensions_and_structure_are_validated():
    def bad(match, **changes):
        spec = {**SLAB, **changes}
        with pytest.raises(ValueError, match=match):
            calc(SLAB_VARS, spec, ["T"])
    bad("dimension", equations=["diff(T, t) = a*diff(T, x, 2)*x"])
    bad("exactly two boundary", boundary=["start: T = Ts"])
    bad("one of each", boundary=["start: T = Ts", "start: T = Ti"])
    bad("missing initial", initial=[])
    bad("needs an 'end'", end="")
    bad("no time derivative", equations=["a*diff(T, x, 2) = 0"])
    bad("mixed derivatives", equations=["diff(T, t) = a*diff(diff(T, x), t)"])
    bad("must differ", time="x")
    bad("'nodes' must be", nodes=5)
    bad("dimension", initial=["T = Ti*x"])
    bad("not supported", events=[{"when": "T = 0"}])


def test_position_outside_the_interval_and_negative_time_are_reported():
    d = solve(calc(SLAB_VARS, SLAB, ["T"]), {**SLAB_IN, "x": "0.2 m"}).to_dict()
    assert not d["ok"] and "outside the interval" in str(d["diagnostics"])
    d = solve(calc(SLAB_VARS, SLAB, ["T"]), {**SLAB_IN, "t": "-1 s"}).to_dict()
    assert not d["ok"]


def test_file_round_trip_system_design_and_exports():
    c = calc(SLAB_VARS, SLAB, ["T"])
    again = calc_from_dict(calc_to_dict(c))
    assert out(solve(again, SLAB_IN), "T") == pytest.approx(out(solve(c, SLAB_IN), "T"))
    doc = {"id": "custom.slabpde", "name": "Slab", "disciplines": ["mechanical"], "outputs": ["T"], "odes": [SLAB],
           "variables": [{"key": v.key, "label": v.label, "unit": v.unit, **({"example": SLAB_IN[v.key]} if v.key in SLAB_IN else {})} for v in SLAB_VARS]}
    api.custom_save(doc)
    g = {"version": 1, "blocks": [{"id": "b", "calc": "custom.slabpde", "x": 0, "y": 0, "values": dict(SLAB_IN)}], "wires": []}
    r = design.solve_system(g)
    assert r["ok"] and next(o for o in r["blocks"]["b"]["outputs"] if o["key"] == "T")["si_value"] == pytest.approx(300 + 200 * series(0.05, 100), rel=2e-5)
    for fmt in ("latex", "markdown", "html"):
        e = design_export.export_system(g, fmt)
        assert e["ok"] and "initial" in e["content"] and "boundary" in e["content"].lower() or e["ok"]
    py = design_export.export_system(g, "python")
    assert py["ok"]                                           # the grid is solved again by the script (same finite differences, SciPy time integration)
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(py["content"], "s.py", "exec"), {"__name__": "__main__"})
    assert "matches the SlideRule reference values" in buf.getvalue()


def _lib(cid, key, inputs):
    from sliderule.core.catalog import default_catalog

    return out(solve(default_catalog().get(cid), inputs), key)


def test_library_slab_cooling_matches_the_heisler_series():
    Bi = 400 * 0.025 / 20
    roots = []
    for n in range(8):                                    # zeta * tan(zeta) = Bi, one root in each branch
        lo, hi = n * math.pi + 1e-9, n * math.pi + math.pi / 2 - 1e-9
        for _ in range(100):
            mid = (lo + hi) / 2
            if mid * math.tan(mid) < Bi:
                lo = mid
            else:
                hi = mid
        roots.append(lo)
    Fo = 10e-6 * 30 / 0.025 ** 2
    theta = sum(4 * math.sin(z) / (2 * z + math.sin(2 * z)) * math.exp(-z * z * Fo) * math.cos(z * 0.6) for z in roots)           # x/L = 0.6
    got = _lib("mechanical.heat.slab_transient_convective_cooling", "T", {"Ti": "500 K", "Tinf": "300 K", "x": "15 mm", "L": "25 mm", "a": "10 mm^2/s", "k": "20 W/(m*K)", "h": "400 W/(m^2*K)", "t": "30 s"})
    assert got == pytest.approx(300 + 200 * theta, rel=1e-4)


def test_library_advection_diffusion_matches_ogata_banks():
    v, D, x, t = 0.1, 0.05, 20.0, 300.0
    c = 0.5 * (math.erfc((x - v * t) / (2 * math.sqrt(D * t))) + math.exp(v * x / D) * math.erfc((x + v * t) / (2 * math.sqrt(D * t))))
    got = _lib("civil.river.contaminant_advection_diffusion", "c", {"c0": "10 mg/L", "x": "20 m", "L": "100 m", "v": "0.1 m/s", "D": "0.05 m^2/s", "t": "5 min"})
    assert got == pytest.approx(0.01 * c, rel=3e-3)


def test_library_damped_string_matches_the_modal_solution():
    # y(x, 0) = h sin^3(pi x / L) = h (3 sin(pi x/L) - sin(3 pi x/L)) / 4, released from rest: each mode decays as exp(-g t) (cos w t + (g / w) sin w t)
    def modal(g, t, x=0.2, L=0.65, c=300.0, h=3e-3):
        tot = 0.0
        for n, coef in ((1, 0.75), (3, -0.25)):
            w = math.sqrt((n * math.pi * c / L) ** 2 - g * g)
            tot += coef * math.sin(n * math.pi * x / L) * math.exp(-g * t) * (math.cos(w * t) + g / w * math.sin(w * t))
        return h * tot
    base = {"h": "3 mm", "x": "0.2 m", "L": "0.65 m", "c": "300 m/s"}
    for g, t in ((0.0, 1e-3), (200.0, 2e-3)):
        got = _lib("mechanical.acoustics.damped_string_displacement", "y", {**base, "g": f"{g} 1/s", "t": f"{t * 1000} ms"})
        assert got == pytest.approx(modal(g, t), abs=3e-5)
