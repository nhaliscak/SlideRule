import math

import mpmath as mp
import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def vals(sol):
    return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}


def mittag_leffler(a, z):
    return float(mp.nsum(lambda k: z**k / mp.gamma(a * k + 1), [0, mp.inf]))


def mk(eq, units=("1/s^0.6", "1"), nodes=800, extra=None):
    return Calculation(id="custom.fr", name="f", disciplines=["mechanical"], description="", custom=True, outputs=["y"], equations=[],
                       variables=[V("y", "y", "1", signed=True), V("t", "t", "s"), V("k", units[0]) if False else V("k", "k", units[0]), V("y0", "y0", "1")],
                       odes=[{"independent": "t", "start": "0", "equations": [eq], "initial": ["y = y0"], "nodes": nodes, **(extra or {})}])


def test_relaxation_matches_the_mittag_leffler_function():
    c = mk("fdiff(y, t, 0.6) = -k*y")
    for tt in (0.5, 2.0, 10.0):
        s = solve(c, {"k": "1 1/s^0.6", "y0": "1", "t": f"{tt} s"}, ["y"])
        assert s.ok, [d.message for d in s.diagnostics]
        assert vals(s)["y"] == pytest.approx(mittag_leffler(0.6, -(tt**0.6)), abs=3e-4)


def test_constant_rate_and_order_one_limits():
    c = Calculation(id="custom.fr2", name="f", disciplines=["mechanical"], description="", custom=True, outputs=["y"], equations=[],
                    variables=[V("y", "y", "m"), V("t", "t", "s"), V("r", "r", "m/s^0.5"), V("y0", "y0", "m")], odes=[{"independent": "t", "start": "0", "equations": ["fdiff(y, t, 1/2) = r"], "initial": ["y = y0"]}])
    got = vals(solve(c, {"r": "2 m/s^0.5", "y0": "1 m", "t": "4 s"}, ["y"]))["y"]
    assert got == pytest.approx(1 + 2 * 4**0.5 / math.gamma(1.5), rel=2e-3)                 # D^a y = r  ->  y = y0 + r t^a / Gamma(a + 1)
    d = Calculation(id="custom.fr3", name="f", disciplines=["mechanical"], description="", custom=True, outputs=["y"], equations=[],
                    variables=[V("y", "y", "1", signed=True), V("t", "t", "s"), V("k", "k", "1/s"), V("y0", "y0", "1")], odes=[{"independent": "t", "start": "0", "equations": ["fdiff(y, t, 1) = -k*y"], "initial": ["y = y0"]}])
    assert vals(solve(d, {"k": "1 1/s", "y0": "1", "t": "2 s"}, ["y"]))["y"] == pytest.approx(math.exp(-2), abs=2e-3)       # order 1 is the ordinary derivative


def test_library_creep_and_round_trip_and_inversion():
    c = _ALL["materials.viscoelastic.fractional_kelvin_voigt_creep"]
    got = vals(solve(c, c.example, ["eps"]))["eps"]
    assert got == pytest.approx(0.02 * (1 - mittag_leffler(0.4, -((20 / 5) ** 0.4))), abs=1e-4)
    back = calc_from_dict({**calc_to_dict(c), "id": "custom.rt"})
    assert vals(solve(back, back.example, ["eps"]))["eps"] == pytest.approx(got, rel=1e-12)
    # the elastic modulus that gives a target strain is found by root-finding on the whole fractional solution
    e = vals(solve(c, {"sigma0": "2 MPa", "tau": "5 s", "eps0": "0", "t": "20 s", "eps": str(got)}, ["E"]))["E"]
    assert e == pytest.approx(100e6, rel=2e-3)


def test_error_estimate_is_reported_and_validation():
    c = mk("fdiff(y, t, 0.6) = -k*y")
    s = solve(c, {"k": "1 1/s^0.6", "y0": "1", "t": "3 s"}, ["y"])
    series = next(q for q in s.to_dict()["series"])
    assert any("estimated error" in n for n in series["method"].get("notes", []))
    with pytest.raises(ValueError, match="initial value of diff"):
        mk("fdiff(y, t, 1.5) = -k*y")                                    # an order above 1 needs the initial slope as well
    with pytest.raises(ValueError, match="dimension"):
        mk("fdiff(y, t, 0.6) = -k*y", units=("1/s", "1"))
    with pytest.raises(ValueError, match="two different orders"):
        mk("fdiff(y, t, 0.6) + diff(y, t) = -k*y")
    with pytest.raises(ValueError, match="initial-value"):
        mk("fdiff(y, t, 0.6) = -k*y", extra={"boundary": ["start: y = 0"]})


def mk2(eq, initial, units=("1/s^1.5", "1"), nodes=800, extra=None):
    return Calculation(id="custom.fr5", name="f", disciplines=["mechanical"], description="", custom=True, outputs=["y"], equations=[],
                       variables=[V("y", "y", "1", signed=True), V("t", "t", "s"), V("k", "k", units[0]), V("y0", "y0", "1"), *[V(n, n, u) for n, u in (("v0", "1/s"), ("a0", "1/s^2")) if any(n in q for q in initial)]],
                       odes=[{"independent": "t", "start": "0", "equations": [eq], "initial": initial, "nodes": nodes, **(extra or {})}])


def test_orders_between_one_and_two_oscillate_and_match_mittag_leffler():
    c = mk2("fdiff(y, t, 1.5) = -k*y", ["y = y0", "diff(y, t) = v0"])
    for tt in (1.0, 3.0, 6.0):
        s = solve(c, {"k": "1 1/s^1.5", "y0": "1", "v0": "0 1/s", "t": f"{tt} s"}, ["y"])
        assert s.ok, [d.message for d in s.diagnostics]
        assert vals(s)["y"] == pytest.approx(mittag_leffler(1.5, -(tt**1.5)), abs=2e-3)       # y = E_{1.5}(-k t^1.5) for y'(0) = 0


def test_order_two_is_the_ordinary_oscillator_and_the_initial_velocity_counts():
    c = mk2("fdiff(y, t, 2) = -k*y", ["y = y0", "diff(y, t) = v0"], units=("1/s^2", "1"))
    got = vals(solve(c, {"k": "4 1/s^2", "y0": "1", "v0": "3 1/s", "t": "2 s"}, ["y"]))["y"]
    assert got == pytest.approx(math.cos(4) + 1.5 * math.sin(4), abs=3e-3)                  # y'' = -4y: cos 2t + (v0/2) sin 2t
    d = mk2("fdiff(y, t, 2.5) = k", ["y = y0", "diff(y, t) = v0", "diff(y, t, 2) = a0"], units=("1/s^2.5", "1"))
    got = vals(solve(d, {"k": "2 1/s^2.5", "y0": "1", "v0": "3 1/s", "a0": "0 1/s^2", "t": "2 s"}, ["y"]))["y"]
    assert got == pytest.approx(1 + 3 * 2 + 2 * 2**2.5 / math.gamma(3.5), rel=2e-3)          # D^a y = k  ->  y = y0 + v0 t + k t^a / Gamma(a + 1)


def test_higher_order_initial_values_are_required_and_checked():
    with pytest.raises(ValueError, match="initial value of diff"):
        mk2("fdiff(y, t, 1.5) = -k*y", ["y = y0"])
    with pytest.raises(ValueError, match="only|up to the derivative"):
        mk2("fdiff(y, t, 0.5) = -k*y", ["y = y0", "diff(y, t) = v0"], units=("1/s^0.5", "1"))
    with pytest.raises(ValueError, match="dimension"):
        mk2("fdiff(y, t, 1.5) = -k*y", ["y = y0", "diff(y, t) = y0"])
    with pytest.raises(ValueError, match="0 < alpha"):
        mk2("fdiff(y, t, 3.5) = -k*y", ["y = y0", "diff(y, t) = v0", "diff(y, t, 2) = v0"])
    c = mk2("fdiff(y, t, 1.5) = -k*y", ["y = y0", "diff(y, t) = v0"])
    back = calc_from_dict({**calc_to_dict(c), "id": "custom.rt5"})
    g = {"k": "1 1/s^1.5", "y0": "1", "v0": "0 1/s", "t": "2 s"}
    assert vals(solve(back, g, ["y"]))["y"] == pytest.approx(vals(solve(c, g, ["y"]))["y"], rel=1e-12)
