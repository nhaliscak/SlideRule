import math

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


def ball(e="0.8", t="2 s", h0="1 m"):
    c = _ALL["mechanical.dynamics.bouncing_ball_impacts"]
    return solve(c, {"h0": h0, "e": e, "t": t}, ["h", "tb"])


def test_bouncing_ball_matches_the_exact_impact_sequence():
    g, e, h0 = 9.80665, 0.8, 1.0
    t1 = math.sqrt(2 * h0 / g)
    v = g * t1
    times = [t1]
    for k in range(1, 6):
        times.append(times[-1] + 2 * e**k * v / g)
    for tt in (0.3, 1.0, 2.0, 2.15):
        k = sum(1 for x in times if x < tt)
        if k == 0:
            want = h0 - 0.5 * g * tt * tt
        else:
            speed, tau = e**k * v, tt - times[k - 1]
            want = speed * tau - 0.5 * g * tau * tau
        c = _ALL["mechanical.dynamics.bouncing_ball_impacts"]
        got = vals(solve(c, {"h0": "1 m", "e": "0.8", "t": f"{tt} s"}, ["h"]))["h"]          # (tb is only defined once the first impact has happened)
        assert got == pytest.approx(want, abs=1e-6), tt
    assert vals(ball())["tb"] == pytest.approx(t1, rel=1e-9)


def test_zeno_behaviour_is_reported():
    s = ball(e="0.5", t="60 s")
    assert not s.ok and any("Zeno" in d.message or "impulsive events" in d.message for d in s.diagnostics)


def test_thermostat_cycles_inside_its_band():
    c = _ALL["mechanical.hvac.thermostat_hysteresis_room_temperature"]
    ref = {}
    Q, UA, C, To, lo, hi = 3000.0, 150.0, 5e6, 273.15, 292.15, 295.15
    T, u, t = 290.15, 1, 0.0
    out = {}
    while t < 20 * 3600:
        T += (u * Q - UA * (T - To)) / C
        t += 1.0
        if u == 1 and T >= hi:
            u = 0
        elif u == 0 and T <= lo:
            u = 1
        if t in (3600 * 3, 3600 * 10, 3600 * 20):
            out[t] = T
    for hours, want in ((3, out[3600 * 3]), (10, out[3600 * 10]), (20, out[3600 * 20])):
        got = vals(solve(c, {**c.example, "t": f"{hours} h"}, ["T"]))["T"]
        assert got == pytest.approx(want, abs=0.02), hours
        if hours >= 10:
            assert lo - 0.05 <= got <= hi + 0.05                                  # after the warm-up the temperature stays inside the band
    del ref


def test_reset_is_validated():
    def mk(reset, terminal=False, derivs="diff(x, t, 2) = -x"):
        return Calculation(id="custom.r", name="r", disciplines=["mechanical"], description="", custom=True, outputs=["x"],
                           variables=[V("x", "x", "m", signed=True), V("t", "t", "s"), V("k", "k", "1/s^2"), V("x0", "x0", "m"), V("c", "c", "1")], equations=[],
                           odes=[{"independent": "t", "start": "0", "method": "numeric", "equations": [derivs.replace("-x", "-k*x")], "initial": ["x = x0", "diff(x, t) = 0"],
                                  "events": [{"when": "x = 0", "direction": "falling", "terminal": terminal, "reset": reset}]}])
    mk({"diff(x, t)": "-c*diff(x, t)"})
    with pytest.raises(ValueError, match="dimension"):
        mk({"diff(x, t)": "x"})
    with pytest.raises(ValueError, match="not a state"):
        mk({"diff(x, t, 2)": "0"})
    with pytest.raises(ValueError, match="terminal|jump"):
        mk({"diff(x, t)": "0"}, terminal=True)


def test_hybrid_calculation_round_trips():
    c = _ALL["mechanical.hvac.thermostat_hysteresis_room_temperature"]
    back = calc_from_dict({**calc_to_dict(c), "id": "custom.rt"})
    got = vals(solve(back, {**back.example, "t": "5 h"}, ["T"]))["T"]
    assert got == pytest.approx(vals(solve(c, {**c.example, "t": "5 h"}, ["T"]))["T"], rel=1e-9)


def test_algebraic_constraint_is_eliminated():
    def rc(spec):
        return Calculation(id="custom.rc", name="rc", disciplines=["electrical"], description="", custom=True, outputs=["Vc"], equations=[],
                           variables=[V("Vc", "Vc", "V", signed=True), V("t", "t", "s"), V("Vs", "Vs", "V"), V("R", "R", "ohm"), V("C", "C", "uF"), V("i", "i", "A", signed=True), V("V0", "V0", "V", signed=True)],
                           odes=[{"independent": "t", "start": "0", "initial": ["Vc = V0"], **spec}])
    c = rc({"equations": ["C*diff(Vc, t) = i", "i*R = Vs - Vc"], "algebraic": ["i"]})
    v = vals(solve(c, {"Vs": "10 V", "R": "1 kohm", "C": "100 uF", "t": "0.1 s", "V0": "0 V"}, ["Vc"]))["Vc"]
    assert v == pytest.approx(10 * (1 - math.exp(-1)), rel=1e-6)
    with pytest.raises(ValueError, match="algebraic"):
        rc({"equations": ["C*diff(Vc, t) = i", "i*R = Vs - Vc"]})                 # the constraint's variable must be declared
    with pytest.raises(ValueError, match="algebraic"):
        rc({"equations": ["C*diff(Vc, t) = i", "i*R = Vs - Vc"], "algebraic": ["Vs", "R"]})


def test_larger_systems_are_accepted():
    n = 10
    names = [f"y{k}" for k in range(n)]
    c = Calculation(id="custom.chain", name="chain", disciplines=["mechanical"], description="", custom=True, outputs=[names[-1]], equations=[],
                    variables=[*[V(x, x, "1", signed=True) for x in names], V("t", "t", "s"), V("a", "a", "1/s")],
                    odes=[{"independent": "t", "start": "0", "equations": [f"diff({names[0]}, t) = -a*{names[0]}", *[f"diff({names[k]}, t) = a*({names[k - 1]} - {names[k]})" for k in range(1, n)]],
                           "initial": [f"{x} = {1 if k == 0 else 0}" for k, x in enumerate(names)], "method": "numeric"}])
    # a chain of first-order lags: y_k(t) = (a t)^k e^{-a t} / k!
    got = vals(solve(c, {"a": "1 1/s", "t": "5 s"}, [names[-1]]))[names[-1]]
    assert got == pytest.approx(5**9 * math.exp(-5) / math.factorial(9), rel=1e-5)
