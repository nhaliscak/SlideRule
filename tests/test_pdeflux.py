import math

import numpy as np
import pytest
from scipy.optimize import brentq

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


IC = "u = Piecewise((ul, x < L/4), (ur, True))"


def burgers(ic, bc, cells=400, extra=None):
    return Calculation(id="custom.bg", name="b", disciplines=["mechanical"], description="", custom=True, outputs=["u"], equations=[],
                       variables=[V("u", "u", "m/s", signed=True), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("ul", "ul", "m/s", signed=True), V("ur", "ur", "m/s", signed=True)],
                       odes=[{"independent": "x", "start": "0", "end": "L", "time": "t", "scheme": "conservative", "nodes": cells, "equations": ["diff(u, t) + diff(u**2/2, x) = 0"],
                              "boundary": bc, "initial": [ic], **(extra or {})}])


def u_at(c, x, t="4 s", **g):
    s = solve(c, {"L": "10 m", "ul": "2 m/s", "ur": "0 m/s", "t": t, "x": f"{x} m", **g}, ["u"])
    assert s.ok, [d.message for d in s.diagnostics]
    return s.to_dict()["outputs"][0]["si_value"], s


def test_burgers_shock_moves_at_the_rankine_hugoniot_speed():
    c = burgers(IC, ["start: u = ul", "end: diff(u, x) = 0"])
    # u_l = 2, u_r = 0: the shock speed is (2 + 0)/2 = 1, so it is at 2.5 + 4 = 6.5 m at t = 4 s
    assert u_at(c, 6.0)[0] == pytest.approx(2.0, abs=1e-3)
    assert u_at(c, 7.0)[0] == pytest.approx(0.0, abs=1e-3)
    mid = u_at(c, 6.5)[0]
    assert 0.2 < mid < 1.8                                                                # inside the (two-cell wide) shock
    assert not any("above 1 %" in d.message for d in u_at(c, 6.0)[1].diagnostics)


def test_burgers_rarefaction_fan_is_exact():
    c = burgers(IC, ["start: u = ul", "end: diff(u, x) = 0"])
    # u_l = 0, u_r = 2: the fan u = (x - x0)/t fills 0 < x - x0 < 2 t
    for x, tt in ((3.5, 2), (4.0, 2)):
        got, _ = u_at(c, x, f"{tt} s", ul="0 m/s", ur="2 m/s")
        assert got == pytest.approx((x - 2.5) / tt, abs=0.02)


def test_periodic_advection_conserves_the_total_and_makes_no_new_extrema():
    c = Calculation(id="custom.adv", name="a", disciplines=["mechanical"], description="", custom=True, outputs=["u"], equations=[],
                    variables=[V("u", "u", "1", signed=True), V("x", "x", "m"), V("t", "t", "s"), V("L", "L", "m"), V("c", "c", "m/s"), V("xa", "xa", "m"), V("xb", "xb", "m")],
                    odes=[{"independent": "x", "start": "0", "end": "L", "time": "t", "scheme": "conservative", "nodes": 200, "periodic": ["x"], "equations": ["diff(u, t) + diff(c*u, x) = 0"],
                           "boundary": [], "initial": ["u = Piecewise((1, (x > xa) & (x < xb)), (0, True))"]}])
    s = solve(c, {"L": "10 m", "c": "1 m/s", "t": "10 s", "x": "3 m", "xa": "2 m", "xb": "4 m"}, ["u"])        # one full lap: the box is back
    assert s.ok
    prof = next(q for q in s.series if "profile" in q["title"])
    start, end = prof["series"][0]["values"], prof["series"][-1]["values"]
    assert sum(end) == pytest.approx(sum(start), rel=1e-9)                              # finite volumes conserve exactly
    assert max(end) <= 1.0 + 1e-9 and min(end) >= -1e-9                                 # the limiter creates no new extrema
    assert sum(abs(a - b) for a, b in zip(start, end)) / len(start) < 0.06              # the box has come back (smeared at its edges)


def test_dam_break_matches_the_riemann_solution():
    c = _ALL["civil.hydraulics.dam_break_shallow_water"]
    g, hl, hr = 9.80665, 2.0, 1.0
    f = lambda hs: 2 * math.sqrt(g) * (math.sqrt(hl) - math.sqrt(hs)) - (hs - hr) * math.sqrt(g * (hs + hr) / (2 * hs * hr))        # noqa: E731
    hs = brentq(f, hr, hl)
    us = 2 * math.sqrt(g) * (math.sqrt(hl) - math.sqrt(hs))
    s = solve(c, c.example, ["h", "q"])
    got = {o["key"]: o["si_value"] for o in s.to_dict()["outputs"]}
    assert got["h"] == pytest.approx(hs, rel=3e-3)
    assert got["q"] == pytest.approx(hs * us, rel=3e-3)
    assert not [d for d in s.diagnostics if d.level != "info"]


def test_traffic_queue_tail_moves_upstream_at_the_shock_speed():
    c = _ALL["civil.transportation.traffic_queue_at_a_red_light"]
    qa = 40 * 100 * (1 - 40 / 150)
    tail = 5 - qa / (150 - 40) * 0.1                                                    # km: 2.333
    def rho(x):
        return solve(c, {**c.example, "x": f"{x} km"}, ["rho"]).to_dict()["outputs"][0]["si_value"]
    assert rho(tail - 0.15) == pytest.approx(40e-3, rel=1e-3)                           # SI: per metre
    assert rho(tail + 0.15) == pytest.approx(150e-3, rel=1e-3)


def test_validation_and_round_trip():
    ok = burgers(IC, ["start: u = ul", "end: diff(u, x) = 0"])
    assert ok.parsed_odes[0].numeric
    with pytest.raises(ValueError, match="conservation form|divergence"):
        burgers(IC, ["start: u = ul", "end: diff(u, x) = 0"], extra={"equations": ["diff(u, t) = u*diff(u, x, 3)"]})
    with pytest.raises(ValueError, match="outflow condition"):
        burgers(IC, ["start: u = ul", "end: diff(u, x) = 1"])
    with pytest.raises(ValueError, match="boundary condition"):
        burgers(IC, ["start: u = ul"])
    c = _ALL["civil.transportation.traffic_queue_at_a_red_light"]
    doc = calc_to_dict(c)
    assert doc["odes"][0]["scheme"] == "conservative"
    back = calc_from_dict({**doc, "id": "custom.rt"})
    a = solve(c, c.example, ["rho"]).to_dict()["outputs"][0]["si_value"]
    b = solve(back, back.example, ["rho"]).to_dict()["outputs"][0]["si_value"]
    assert a == pytest.approx(b)
    assert np.isfinite(a)


def ritter(extra=None, cells=400, source=None, extra_vars=()):
    eq = ["diff(h, t) + diff(q, x) = 0", "diff(q, t) + diff(q**2/h + g*h**2/2, x) = " + (source or "0")]
    return Calculation(id="custom.dry", name="d", disciplines=["civil"], description="", custom=True, outputs=["h", "q"], equations=[],
                       variables=[V("h", "h", "m"), V("q", "q", "m^2/s", signed=True), V("x", "x", "m", signed=True), V("t", "t", "s"), V("L", "L", "m"), V("h0", "h0", "m"), V("g", "g", "m/s^2"), *extra_vars],
                       odes=[{"independent": "x", "start": "-L", "end": "L", "time": "t", "scheme": "conservative", "nodes": cells, "equations": eq,
                              "boundary": ["start: diff(h, x) = 0", "end: diff(h, x) = 0", "start: diff(q, x) = 0", "end: diff(q, x) = 0"],
                              "initial": ["h = Piecewise((h0, x < 0), (0*h0, True))", "q = 0*h0*sqrt(g*h0)"], **(extra or {})}])


def test_dam_break_over_a_dry_bed_matches_ritters_solution():
    g, h0, tt = 9.81, 1.0, 1.0
    c = ritter({"dry": {"depth": "h", "zero": ["q"]}})
    given = {"L": "10 m", "h0": "1 m", "g": "9.81 m/s^2", "t": f"{tt} s"}
    got = {}
    for xx in (-2.0, 0.0, 2.0, 5.0):
        s = solve(c, {**given, "x": f"{xx} m"}, ["h", "q"])
        assert s.ok, [d.message for d in s.diagnostics]
        got[xx] = {o["key"]: o["si_value"] for o in s.to_dict()["outputs"]}
    c0 = math.sqrt(g * h0)
    for xx, v in got.items():                                        # Ritter: h = (2 c0 - x/t)^2 / (9 g), u = (2/3)(c0 + x/t) inside the rarefaction fan
        h_ex = (2 * c0 - xx / tt) ** 2 / (9 * g)
        assert v["h"] == pytest.approx(h_ex, abs=0.03)
        assert v["q"] == pytest.approx(h_ex * (2 / 3) * (c0 + xx / tt), abs=0.08)
    s = solve(c, {**given, "x": "0 m"}, ["h"])
    prof = next(q for q in s.series if "profile" in q["title"])
    h = np.array(prof["series"][-1]["values"])
    xs = np.array(prof["t"])
    assert h.min() >= 0 and np.all(np.isfinite(h))
    assert float(h.sum() * (xs[1] - xs[0])) == pytest.approx(10.0, rel=2e-3)      # the sum of the cell contents: mass is conserved (10 m of 1 m depth)
    ex = np.where(xs < -c0, h0, np.where(xs < 2 * c0, (2 * c0 - xs) ** 2 / (9 * g), 0.0))
    assert float(np.abs(h - ex).sum() * (xs[1] - xs[0])) < 0.05                   # L1 error: first order at the front (0.069, 0.035, 0.018 for 200, 400, 800 cells)
    front = xs[h > 1e-2].max()
    assert front == pytest.approx(2 * c0 - 3 * math.sqrt(g * 1e-2), abs=0.35)      # the wet front (depth 1 cm) advances at about 2 sqrt(g h0)


def test_dry_bed_option_validation_and_friction_stays_finite():
    with pytest.raises(ValueError, match="depth"):
        ritter({"dry": {"depth": "zz"}})
    with pytest.raises(ValueError, match="zero"):
        ritter({"dry": {"depth": "h", "zero": ["h"]}})
    with pytest.raises(ValueError, match="tol"):
        ritter({"dry": {"depth": "h", "zero": ["q"], "tol": "5"}})
    c = ritter({"dry": {"depth": "h", "zero": ["q"], "tol": "1e-3"}}, cells=200, source="-cf*q*Abs(q)/h**2", extra_vars=[V("cf", "cf", "1")])
    s = solve(c, {"L": "10 m", "h0": "1 m", "g": "9.81 m/s^2", "cf": "0.01", "t": "1 s", "x": "0 m"}, ["h", "q"])
    assert s.ok, [d.message for d in s.diagnostics]                                # q|q|/h**2 would be 0/0 on the dry side: it is evaluated with the floored depth
    assert all(np.isfinite(o["si_value"]) for o in s.to_dict()["outputs"])
    back = calc_from_dict({**calc_to_dict(ritter({"dry": {"depth": "h", "zero": ["q"]}})), "id": "custom.rtdry"})
    assert back.odes[0]["dry"]["depth"] == "h"
