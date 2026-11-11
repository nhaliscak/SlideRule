import math

import numpy as np
import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}

M = math.pi


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def mk(variables, odes, outs):
    return Calculation(id="custom.pm", name="pm", disciplines=["mechanical"], description="", custom=True, variables=variables, equations=[], outputs=outs, odes=odes)


def val(c, given, key):
    s = solve(c, given, [key])
    assert s.ok, [d.message for d in s.diagnostics]
    return next(o["si_value"] for o in s.to_dict()["outputs"] if o["key"] == key), s


def test_coupled_fields_against_an_exact_solution():
    c = mk([V("u", "u", "1", signed=True), V("v", "v", "1", signed=True), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("D", "D", "m^2/s"), V("k", "k", "1/s")],
           [{"independent": "x", "start": "0", "end": "L", "time": "t", "nodes": 100, "equations": ["diff(u, t) = D*diff(u, x, 2)", "diff(v, t) = D*diff(v, x, 2) + k*u"],
             "boundary": ["start: u = 0", "end: u = 0", "start: v = 0", "end: v = 0"], "initial": ["u = sin(pi*x/L)", "v = 0*sin(pi*x/L)"]}], ["u", "v"])
    g = {"L": "1 m", "D": "1 m^2/s", "k": "1 1/s", "x": "0.5 m", "t": "0.1 s"}
    u, _ = val(c, g, "u")
    v, s = val(c, g, "v")
    assert u == pytest.approx(math.exp(-M * M * 0.1), rel=2e-3)
    assert v == pytest.approx(0.1 * math.exp(-M * M * 0.1), rel=2e-3)             # v = t e^{-pi^2 t} sin(pi x)
    assert len(s.series) >= 4 and any("history" in q["title"] for q in s.series)    # profile and history plots for each field


def test_two_dimensional_transient_plate_against_the_separable_solution():
    c = mk([V("T", "T", "K"), V("x", "x", "m"), V("y", "y", "m"), V("t", "t", "s"), V("a", "a", "m"), V("b", "b", "m"), V("al", "al", "m^2/s"), V("Ti", "Ti", "K"), V("Ts", "Ts", "K")],
           [{"independent": "x", "start": "0", "end": "a", "second": "y", "second_start": "0", "second_end": "b", "time": "t", "nodes": 40,
             "equations": ["diff(T, t) = al*(diff(T, x, 2) + diff(T, y, 2))"], "boundary": ["left: T = Ts", "right: T = Ts", "bottom: T = Ts", "top: T = Ts"], "initial": ["T = Ti"]}], ["T"])
    g = {"a": "1 m", "b": "1 m", "al": "0.1 m^2/s", "Ti": "400 K", "Ts": "300 K", "x": "0.5 m", "y": "0.5 m", "t": "0.5 s"}
    got, s = val(c, g, "T")
    exact = 0.0
    for m in range(0, 40, 1):
        for n in range(0, 40, 1):
            i, j = 2 * m + 1, 2 * n + 1
            exact += 16 / (M * M * i * j) * math.sin(i * M * 0.5) * math.sin(j * M * 0.5) * math.exp(-0.1 * M * M * (i * i + j * j) * 0.5)
    assert got == pytest.approx(300 + 100 * exact, rel=1e-3)
    assert any("heat map" in str(q.keys()) or "heatmap" in q for q in s.series)


def test_periodic_advection_diffusion_and_a_mixed_derivative():
    c = mk([V("u", "u", "1", signed=True), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("c", "c", "m/s"), V("D", "D", "m^2/s")],
           [{"independent": "x", "start": "0", "end": "L", "time": "t", "nodes": 200, "periodic": ["x"], "equations": ["diff(u, t) = -c*diff(u, x) + D*diff(u, x, 2)"],
             "boundary": [], "initial": ["u = sin(2*pi*x/L)"]}], ["u"])
    k = 2 * M
    got, _ = val(c, {"L": "1 m", "c": "0.3 m/s", "D": "0.01 m^2/s", "x": "0.4 m", "t": "1 s"}, "u")
    assert got == pytest.approx(math.exp(-0.01 * k * k) * math.sin(k * (0.4 - 0.3)), abs=2e-3)
    d = mk([V("u", "u", "1", signed=True), V("x", "x", "m"), V("y", "y", "m"), V("t", "t", "s"), V("L", "L", "m"), V("D", "D", "m^2/s"), V("m", "m", "m^2/s")],
           [{"independent": "x", "start": "0", "end": "L", "second": "y", "second_start": "0", "second_end": "L", "time": "t", "nodes": 48, "periodic": ["x", "y"],
             "equations": ["diff(u, t) = D*(diff(u, x, 2) + diff(u, y, 2)) + m*diff(u, x, y)"], "boundary": [], "initial": ["u = sin(2*pi*x/L + 2*pi*y/L)"]}], ["u"])
    lam = -0.01 * 2 * k * k - 0.005 * k * k
    got, _ = val(d, {"L": "1 m", "D": "0.01 m^2/s", "m": "0.005 m^2/s", "x": "0.2 m", "y": "0.3 m", "t": "1 s"}, "u")
    assert got == pytest.approx(math.exp(lam) * math.sin(k * 0.5), abs=3e-3)


def test_a_concentrated_source_conserves_the_total():
    c = mk([V("u", "u", "K"), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("al", "al", "m^2/s"), V("S", "S", "K*m/s"), V("x0", "x0", "m")],
           [{"independent": "x", "start": "0", "end": "L", "time": "t", "nodes": 100, "equations": ["diff(u, t) = al*diff(u, x, 2)"], "boundary": ["start: diff(u, x) = 0", "end: diff(u, x) = 0"],
             "initial": ["u = 0*x"], "sources": [{"field": "u", "at": "x0", "rate": "S"}]}], ["u"])
    s = solve(c, {"L": "1 m", "al": "0.01 m^2/s", "S": "2 K*m/s", "x0": "0.3 m", "x": "0.9 m", "t": "5 s"}, ["u"])
    assert s.ok
    prof = next(q for q in s.series if "profile" in q["title"])
    final = prof["series"][-1]["values"]
    xs = prof["t"]
    assert (getattr(np, "trapezoid", None) or np.trapz)(final, xs) == pytest.approx(2.0 * 5.0, rel=1e-6)           # the integral of u grows by rate * time


def test_validation():
    base = dict(independent="x", start="0", end="L", time="t", nodes=40)
    vs = [V("u", "u", "1", signed=True), V("v", "v", "1", signed=True), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("D", "D", "m^2/s")]
    two = ["diff(u, t) = D*diff(u, x, 2)", "diff(v, t) = D*diff(v, x, 2)"]
    with pytest.raises(ValueError, match="boundary condition"):
        mk(vs, [{**base, "equations": two, "boundary": ["start: u = 0", "end: u = 0"], "initial": ["u = 0*x", "v = 0*x"]}], ["u"])
    with pytest.raises(ValueError, match="slope of more than one field"):
        mk(vs, [{**base, "equations": two, "boundary": ["start: diff(u, x) = diff(v, x)", "end: u = 0", "start: v = 0", "end: v = 0"], "initial": ["u = 0*x", "v = 0*x"]}], ["u"])
    with pytest.raises(ValueError, match="circular"):
        mk(vs, [{**base, "equations": two, "boundary": ["start: u = v", "end: u = 0", "start: v = u", "end: v = 0"], "initial": ["u = 0*x", "v = 0*x"]}], ["u"])
    with pytest.raises(ValueError, match="alone on the left"):
        mk(vs, [{**base, "equations": two, "boundary": ["start: u + v = 1", "end: u = 0", "start: v = 0", "end: v = 0"], "initial": ["u = 0*x", "v = 0*x"]}], ["u"])
    with pytest.raises(ValueError, match="missing initial"):
        mk(vs, [{**base, "equations": two, "boundary": ["start: u = 0", "end: u = 0", "start: v = 0", "end: v = 0"], "initial": ["u = 0*x"]}], ["u"])
    with pytest.raises(ValueError, match="dimension"):
        mk(vs, [{**base, "equations": ["diff(u, t) = D*diff(u, x)", two[1]], "boundary": ["start: u = 0", "end: u = 0", "start: v = 0", "end: v = 0"], "initial": ["u = 0*x", "v = 0*x"]}], ["u"])


def test_axisymmetric_finite_cylinder_matches_newmans_product_solution():
    from scipy.special import j1, jn_zeros

    c = _ALL["mechanical.heat.finite_cylinder_quench_axisymmetric"]
    s = solve(c, c.example, ["T"])
    assert s.ok, [d.message for d in s.diagnostics]
    got = s.to_dict()["outputs"][0]["si_value"]
    r_, b_, al, t = 0.05, 0.08, 1e-5, 60.0
    cyl = sum(2 / (l * j1(l)) * math.exp(-l * l * al * t / r_**2) for l in jn_zeros(0, 60))
    slab = sum((-1) ** n * 2 / ((n + 0.5) * M) * math.exp(-(((n + 0.5) * M) ** 2) * al * t / b_**2) for n in range(200))
    assert got == pytest.approx(300 + 200 * cyl * slab, abs=0.05)
    off_axis = solve(c, {**c.example, "r": "25 mm", "z": "40 mm"}, ["T"])
    assert off_axis.ok and off_axis.to_dict()["outputs"][0]["si_value"] < got


def test_spherical_centre_in_a_coupled_system():
    c = mk([V("u", "u", "K"), V("w", "w", "1", signed=True), V("r", "r", "m"), V("t", "t", "s"), V("R", "R", "m"), V("al", "al", "m^2/s"), V("Ti", "Ti", "K"), V("Ts", "Ts", "K"), V("k", "k", "1/s")],
           [{"independent": "r", "start": "0", "end": "R", "time": "t", "nodes": 100,
             "equations": ["diff(u, t) = al*(diff(u, r, 2) + 2*diff(u, r)/r)", "diff(w, t) = -k*w"],
             "boundary": ["start: diff(u, r) = 0", "end: u = Ts", "start: diff(w, r) = 0", "end: diff(w, r) = 0"], "initial": ["u = Ti", "w = 1 + 0*r"]}], ["u"])
    got, _ = val(c, {"R": "0.02 m", "al": "1e-5 m^2/s", "Ti": "500 K", "Ts": "300 K", "k": "0.1 1/s", "r": "0 m", "t": "10 s"}, "u")
    exact = 300 + 200 * 2 * sum((-1) ** (n + 1) * math.exp(-(n * M) ** 2 * 1e-5 * 10 / 0.02**2) for n in range(1, 200))      # centre of a sphere with a fixed surface temperature
    assert got == pytest.approx(exact, abs=0.1)


def test_three_dimensional_cube_against_the_separable_solution():
    c = mk([V("T", "T", "K"), V("x", "x", "m"), V("y", "y", "m"), V("z", "z", "m"), V("t", "t", "s"), V("L", "L", "m"), V("al", "al", "m^2/s"), V("Ti", "Ti", "K"), V("Ts", "Ts", "K")],
           [{"independent": "x", "start": "0", "end": "L", "second": "y", "second_start": "0", "second_end": "L", "third": "z", "third_start": "0", "third_end": "L", "time": "t", "nodes": 20,
             "equations": ["diff(T, t) = al*(diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2))"],
             "boundary": ["left: T = Ts", "right: T = Ts", "bottom: T = Ts", "top: T = Ts", "front: T = Ts", "back: T = Ts"], "initial": ["T = Ti"]}], ["T"])
    g = {"L": "1 m", "al": "0.1 m^2/s", "Ti": "400 K", "Ts": "300 K", "x": "0.5 m", "y": "0.5 m", "z": "0.5 m", "t": "0.3 s"}
    got, s = val(c, g, "T")
    exact = 0.0
    for m in range(6):
        for n in range(6):
            for p in range(6):
                i, j, k = 2 * m + 1, 2 * n + 1, 2 * p + 1
                exact += 64 / (M ** 3 * i * j * k) * (-1) ** (m + n + p) * math.exp(-0.1 * M * M * (i * i + j * j + k * k) * 0.3)
    assert got == pytest.approx(300 + 100 * exact, rel=3e-3)
    assert any("history" in q["title"] for q in s.series)


def test_three_dimensional_needs_a_second_variable():
    vs = [V("T", "T", "K"), V("x", "x", "m"), V("z", "z", "m"), V("t", "t", "s"), V("L", "L", "m")]
    with pytest.raises(ValueError, match="second"):
        mk(vs, [{"independent": "x", "start": "0", "end": "L", "third": "z", "third_start": "0", "third_end": "L", "time": "t",
                 "equations": ["diff(T, t) = diff(T, x, 2)"], "boundary": ["start: T = 0", "end: T = 0"], "initial": ["T = 0*x"]}], ["T"])


def test_conditions_that_read_another_field_at_the_boundary():
    # v is insulated at both ends and starts uniform, so it stays at c. u is held equal to v at x = 0 and to zero at x = L: u -> c (1 - x/L)
    c = mk([V("u", "u", "K", signed=True), V("v", "v", "K", signed=True), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("D", "D", "m^2/s"), V("c", "c", "K")],
           [{"independent": "x", "start": "0", "end": "L", "time": "t", "nodes": 50, "equations": ["diff(u, t) = D*diff(u, x, 2)", "diff(v, t) = D*diff(v, x, 2)"],
             "boundary": ["start: u = v", "end: u = 0*c", "start: diff(v, x) = 0", "end: diff(v, x) = 0"], "initial": ["u = 0*c", "v = c"]}], ["u"])
    got, _ = val(c, {"L": "1 m", "D": "1 m^2/s", "c": "10 K", "x": "0.25 m", "t": "3 s"}, "u")
    assert got == pytest.approx(10 * 0.75, rel=2e-3)
    # a slope condition with the other field's value: -k u_x = h (v - u) at x = 0, u = 0 at x = L: steady u = A (1 - x/L), A = h v / (k/L + h)
    d = mk([V("u", "u", "K", signed=True), V("v", "v", "K", signed=True), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("D", "D", "m^2/s"), V("k", "k", "W/(m*K)"),
            V("h", "h", "W/(m^2*K)"), V("c", "c", "K")],
           [{"independent": "x", "start": "0", "end": "L", "time": "t", "nodes": 50, "equations": ["diff(u, t) = D*diff(u, x, 2)", "diff(v, t) = D*diff(v, x, 2)"],
             "boundary": ["start: -k*diff(u, x) = h*(v - u)", "end: u = 0*c", "start: diff(v, x) = 0", "end: diff(v, x) = 0"], "initial": ["u = 0*c", "v = c"]}], ["u"])
    got, _ = val(d, {"L": "1 m", "D": "1 m^2/s", "k": "2 W/(m*K)", "h": "6 W/(m^2*K)", "c": "10 K", "x": "0 m", "t": "3 s"}, "u")
    A = 6 * 10 / (2 / 1 + 6)
    assert got == pytest.approx(A, rel=2e-3)
    mid, _ = val(d, {"L": "1 m", "D": "1 m^2/s", "k": "2 W/(m*K)", "h": "6 W/(m^2*K)", "c": "10 K", "x": "0.5 m", "t": "3 s"}, "u")
    assert mid == pytest.approx(A / 2, rel=2e-3)
    with pytest.raises(ValueError, match="dimension"):
        mk([V("u", "u", "K", signed=True), V("v", "v", "m", signed=True), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("D", "D", "m^2/s")],
           [{"independent": "x", "start": "0", "end": "L", "time": "t", "equations": ["diff(u, t) = D*diff(u, x, 2)", "diff(v, t) = D*diff(v, x, 2)"],
             "boundary": ["start: u = v", "end: u = 0", "start: diff(v, x) = 0", "end: diff(v, x) = 0"], "initial": ["u = 0*x", "v = 0*x"]}], ["u"])
