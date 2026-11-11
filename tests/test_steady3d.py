import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}
SIDES6 = ["left: {f} = {v}", "right: {f} = {v}", "bottom: {f} = {v}", "top: {f} = {v}", "front: {f} = {v}", "back: {f} = {v}"]


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def box(equations, boundary, variables, outputs, nodes=16, extra=None):
    spec = {"independent": "x", "start": "0", "end": "L", "second": "y", "second_start": "0", "second_end": "L", "third": "z", "third_start": "0", "third_end": "L",
            "nodes": nodes, "equations": equations, "boundary": boundary, **(extra or {})}
    return Calculation(id="custom.s3", name="s", disciplines=["mechanical"], description="", custom=True, outputs=outputs, equations=[], variables=variables, odes=[spec])


def val(c, given, key="T"):
    s = solve(c, given, [key])
    assert s.ok, [d.message for d in s.diagnostics]
    return next(o["si_value"] for o in s.to_dict()["outputs"] if o["key"] == key), s


def test_poisson_in_a_cube_against_the_triple_sine_series():
    c = box(["k*(diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2)) + q = 0"], [f.format(f="T", v="T0") for f in SIDES6],
            [V("T", "T", "K"), V("x", "x", "m"), V("y", "y", "m"), V("z", "z", "m"), V("L", "L", "m"), V("k", "k", "W/(m*K)"), V("q", "q", "W/m^3"), V("T0", "T0", "K")], ["T"], nodes=20)
    got, s = val(c, {"L": "1 m", "k": "2 W/(m*K)", "q": "100 W/m^3", "T0": "300 K", "x": "0.5 m", "y": "0.5 m", "z": "0.5 m"})
    u = 0.0
    for i in range(1, 40, 2):
        for j in range(1, 40, 2):
            for k in range(1, 40, 2):
                u += 64 / (math.pi**5 * i * j * k * (i * i + j * j + k * k)) * (-1) ** ((i + j + k - 3) // 2)
    assert got == pytest.approx(300 + 50 * u, abs=0.02)                       # lap(u) = -1 in the unit cube, u = 0 on the faces: u(centre) = 0.0562...
    assert any("field" in q["title"] for q in s.series) and any("Newton" in q["method"]["method"] for q in s.series)


def test_nonlinear_problem_has_the_manufactured_solution_exactly():
    # T = x(1-x) y(1-y) z(1-z): second differences are exact for these quadratics, so Newton must reproduce the nodal values
    lap = "-2*(y*(1-y)*z*(1-z) + x*(1-x)*z*(1-z) + x*(1-x)*y*(1-y))"
    c = box([f"diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2) + T**2 = {lap} + (x*(1-x)*y*(1-y)*z*(1-z))**2"], [f.format(f="T", v="0") for f in SIDES6],
            [V("T", "T", "1", signed=True), V("x", "x", "1"), V("y", "y", "1"), V("z", "z", "1"), V("L", "L", "1")], ["T"], nodes=12)
    got, _ = val(c, {"L": "1", "x": "0.5", "y": "0.5", "z": "0.5"})
    assert got == pytest.approx(0.5**6, rel=1e-6)
    got2, _ = val(c, {"L": "1", "x": "0.25", "y": "0.75", "z": "0.5"})
    assert got2 == pytest.approx(0.25 * 0.75 * 0.75 * 0.25 * 0.5 * 0.5, rel=2e-3)             # between nodes: cubic interpolation


def test_slope_conditions_two_fields_and_validation():
    # insulated on five faces, T = T0 on the sixth: uniform T = T0 whatever the source is zero
    c = box(["diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2) = 0"], ["left: diff(T, x) = 0", "right: diff(T, x) = 0", "bottom: diff(T, y) = 0", "top: diff(T, y) = 0", "front: diff(T, z) = 0", "back: T = T0"],
            [V("T", "T", "K"), V("x", "x", "m"), V("y", "y", "m"), V("z", "z", "m"), V("L", "L", "m"), V("T0", "T0", "K")], ["T"], nodes=8)
    got, _ = val(c, {"L": "1 m", "T0": "300 K", "x": "0.3 m", "y": "0.2 m", "z": "0.9 m"})
    assert got == pytest.approx(300.0, abs=1e-6)
    sing = box(["diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2) = 0"], ["left: diff(T, x) = 0", "right: diff(T, x) = 0", "bottom: diff(T, y) = 0", "top: diff(T, y) = 0", "front: diff(T, z) = 0", "back: diff(T, z) = 0"],
               [V("T", "T", "K"), V("x", "x", "m"), V("y", "y", "m"), V("z", "z", "m"), V("L", "L", "m")], ["T"], nodes=8)
    s = solve(sing, {"L": "1 m", "x": "0.3 m", "y": "0.2 m", "z": "0.9 m"}, ["T"])
    assert not s.ok and any("singular" in d.message for d in s.diagnostics)
    vs = [V("T", "T", "K"), V("x", "x", "m"), V("y", "y", "m"), V("z", "z", "m"), V("L", "L", "m"), V("T0", "T0", "K")]
    with pytest.raises(ValueError, match="dimension"):
        box(["diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2) = T"], [f.format(f="T", v="T0") for f in SIDES6], vs, ["T"])
    with pytest.raises(ValueError, match="boundary condition"):
        box(["diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2) = 0"], ["left: T = T0"], vs, ["T"])
    with pytest.raises(ValueError, match="time derivative"):
        box(["diff(T, t) = diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2)"], [f.format(f="T", v="T0") for f in SIDES6], vs + [V("t", "t", "s")], ["T"])


def test_two_coupled_fields_and_the_round_trip():
    vs = [V("a", "a", "1"), V("b", "b", "1"), V("x", "x", "1"), V("y", "y", "1"), V("z", "z", "1"), V("L", "L", "1")]
    c = box(["diff(a, x, 2) + diff(a, y, 2) + diff(a, z, 2) = -1", "diff(b, x, 2) + diff(b, y, 2) + diff(b, z, 2) = a"], [f.format(f="a", v="0") for f in SIDES6] + [f.format(f="b", v="0") for f in SIDES6],
            vs, ["a", "b"], nodes=12)
    ga, _ = val(c, {"L": "1", "x": "0.5", "y": "0.5", "z": "0.5"}, "a")
    gb, _ = val(c, {"L": "1", "x": "0.5", "y": "0.5", "z": "0.5"}, "b")
    assert ga == pytest.approx(0.05626, abs=1e-3) and -0.01 < gb < 0                 # lap(b) = a > 0 with b = 0 on the faces: b is negative inside
    back = calc_from_dict({**calc_to_dict(c), "id": "custom.rt3"})
    g, _ = val(back, {"L": "1", "x": "0.5", "y": "0.5", "z": "0.5"}, "a")
    assert g == pytest.approx(ga, rel=1e-12)
