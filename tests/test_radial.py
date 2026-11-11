import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def out(sol, key):
    return next(o["si_value"] for o in sol.to_dict()["outputs"] if o["key"] == key)


def calc(variables, spec, outputs):
    return Calculation(id="custom.rad", name="r", disciplines=["mechanical"], description="", variables=variables, equations=[], outputs=outputs, custom=True, odes=[spec])


GEN_VARS = [V("T", "T", "K"), V("r", "r", "m"), V("R", "R", "m"), V("q", "q", "W/m^3"), V("k", "k", "W/(m*K)"), V("h", "h", "W/(m^2*K)"), V("Tinf", "Tinf", "K")]
GEN_IN = {"q": "5e6 W/m^3", "k": "20 W/(m*K)", "h": "500 W/(m^2*K)", "Tinf": "300 K", "R": "10 mm"}


def gen_spec(n, **extra):
    lap = "diff(T, r, 2) + diff(T, r)/r" if n == 1 else "diff(T, r, 2) + 2*diff(T, r)/r"
    return {"independent": "r", "start": "0", "end": "R", "equations": [f"k*({lap}) + q = 0"], "boundary": ["start: diff(T, r) = 0", "end: -k*diff(T, r) = h*(T - Tinf)"], **extra}


def steady(n, r, q=5e6, k=20.0, h=500.0, Tinf=300.0, R=0.01):
    d = 2 * n + 2                                                         # cylinder (n = 1): 4, sphere (n = 2): 6
    return Tinf + q * R / ((n + 1) * h) + q * (R * R - r * r) / (d * k)


@pytest.mark.parametrize("n", [1, 2])
def test_radial_boundary_value_problems_at_the_axis_or_centre(n):
    for method in ("auto", "numeric"):
        c = calc(GEN_VARS, gen_spec(n, method=method), ["T"])
        assert c.parsed_odes[0].numeric == (method == "numeric")                                  # SymPy finds the closed form once the singular terms are removed
        for r in (0.0, 0.004, 0.01):
            got = out(solve(c, {**GEN_IN, "r": f"{r} m"}), "T")
            assert got == pytest.approx(steady(n, r), rel=1e-9)
    c = calc(GEN_VARS, gen_spec(n), ["T"])
    centre = steady(n, 0.0)
    back = solve(c, {"T": f"{centre} K", "k": "20 W/(m*K)", "h": "500 W/(m^2*K)", "Tinf": "300 K", "R": "10 mm", "r": "0 mm"}, ["q"])
    assert out(back, "q") == pytest.approx(5e6, rel=1e-9)


def test_axis_values_appear_in_the_plot():
    d = solve(calc(GEN_VARS, gen_spec(1, method="numeric"), ["T"]), {**GEN_IN, "r": "5 mm"}).to_dict()
    s = d["series"][0]
    assert s["t"][0] == 0 and s["series"][0]["values"][0] == pytest.approx(steady(1, 0.0), rel=1e-9)


T_VARS = GEN_VARS + [V("T0", "T0", "K"), V("a", "a", "m^2/s"), V("t", "t", "s")]


@pytest.mark.parametrize("n", [1, 2])
def test_radial_transient_problems_reach_the_steady_profile(n):
    lap = "diff(T, r, 2) + diff(T, r)/r" if n == 1 else "diff(T, r, 2) + 2*diff(T, r)/r"
    spec = {"independent": "r", "start": "0", "end": "R", "time": "t", "equations": [f"diff(T, t) = a*({lap}) + a*q/k"], "boundary": ["start: diff(T, r) = 0", "end: -k*diff(T, r) = h*(T - Tinf)"], "initial": ["T = T0"]}
    c = calc(T_VARS, spec, ["T"])
    inp = {**GEN_IN, "T0": "300 K", "a": "5e-6 m^2/s", "t": "600 s"}
    for r in (0.0, 0.006):
        assert out(solve(c, {**inp, "r": f"{r} m"}), "T") == pytest.approx(steady(n, r), rel=1e-4)
    early = out(solve(c, {**inp, "r": "0 m", "t": "2 s"}), "T")
    assert 300 < early < steady(n, 0.0)                                                        # still warming at the centre


def test_lane_emden_initial_value_problem_with_a_centre_singularity():
    v = [V("y", "y", "1", signed=True), V("x", "x", "1"), V("n", "n", "1")]
    spec = {"independent": "x", "start": "0", "method": "numeric", "equations": ["diff(y, x, 2) + 2*diff(y, x)/x + y**n = 0"], "initial": ["y = 1", "diff(y, x) = 0"]}
    c = calc(v, spec, ["y"])
    for n, exact in ((0, lambda x: 1 - x * x / 6), (1, lambda x: math.sin(x) / x), (5, lambda x: 1 / math.sqrt(1 + x * x / 3))):
        for x in (0.5, 2.0):
            assert out(solve(c, {"n": str(n), "x": str(x)}), "y") == pytest.approx(exact(x), rel=1e-8)
    d = solve(c, {"n": "1", "x": "3"}).to_dict()
    assert d["series"][0]["t"][0] == 0.0 and d["series"][0]["series"][0]["values"][0] == pytest.approx(1.0)


def test_closed_and_numerical_solutions_agree_for_singular_starts():
    v = [V("y", "y", "1", signed=True), V("x", "x", "1")]
    for eq in ("diff(y, x, 2) + diff(y, x)/x = -x**2", "diff(y, x, 2) + 2*diff(y, x)/x = -1"):
        got = {}
        for method in ("auto", "numeric"):
            spec = {"independent": "x", "start": "0", "method": method, "equations": [eq], "initial": ["y = 1", "diff(y, x) = 0"]}
            got[method] = out(solve(calc(v, spec, ["y"]), {"x": "1.5"}), "y")
        assert got["auto"] == pytest.approx(got["numeric"], rel=1e-8)


def test_axisymmetric_two_dimensional_problem():
    v = [V("T", "T", "K"), V("Tw", "Tw", "K"), V("r", "r", "m"), V("z", "z", "m"), V("R", "R", "m"), V("H", "H", "m"), V("q", "q", "W/m^3"), V("k", "k", "W/(m*K)")]
    spec = {"independent": "r", "start": "0", "end": "R", "second": "z", "second_start": "0", "second_end": "H",
            "equations": ["k*(diff(T, r, 2) + diff(T, r)/r + diff(T, z, 2)) + q = 0"], "boundary": ["left: diff(T, r) = 0", "right: T = Tw", "bottom: diff(T, z) = 0", "top: diff(T, z) = 0"]}
    c = calc(v, spec, ["T"])
    inp = {"Tw": "300 K", "R": "0.05 m", "H": "0.1 m", "q": "1e6 W/m^3", "k": "20 W/(m*K)", "z": "0.03 m"}
    for r in (0.0, 0.02):
        assert out(solve(c, {**inp, "r": f"{r} m"}), "T") == pytest.approx(300 + 1e6 * (0.05 ** 2 - r * r) / (4 * 20), rel=1e-6)


def test_library_radial_calculations():
    from sliderule.core.catalog import default_catalog

    cat = default_catalog()

    def run(cid, **over):
        calc_ = cat.get(cid)
        return {o["key"]: o["si_value"] for o in solve(calc_, {**calc_.example, **over}).to_dict()["outputs"]}

    assert run("mechanical.heat.cylinder_generation_radial_profile")["T"] == pytest.approx(steady(1, 0.0, q=5e6, k=20, h=500, Tinf=300, R=0.01), rel=1e-9)
    assert run("mechanical.heat.sphere_generation_radial_profile")["T"] == pytest.approx(steady(2, 0.0, q=2e7, k=10, h=2000, Tinf=350, R=0.005), rel=1e-9)
    assert run("mechanical.fluids.pipe_laminar_velocity_profile", r="0 mm")["u"] == pytest.approx(20 * 0.025 ** 2 / (4 * 1e-3), rel=1e-9)
    assert run("mechanical.fluids.pipe_laminar_velocity_profile", r="25 mm")["u"] == pytest.approx(0.0, abs=1e-10)
    late = run("mechanical.heat.cylinder_transient_cooling", t="3000 s")["T"]
    assert late == pytest.approx(steady(1, 0.0, q=5e6, k=20, h=500, Tinf=300, R=0.01), rel=1e-4)
    th = run("space.stellar.lane_emden_polytrope", n="1", xi="2")["th"]
    assert th == pytest.approx(math.sin(2) / 2, rel=1e-8)
