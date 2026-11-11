import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict
from sliderule.core.numeric_ode import dde
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def vals(sol):
    return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}


def exact(t):
    """y' = -y(t - 1), y = 1 for t <= 0: the method of steps by hand (piecewise polynomials)."""
    if t <= 1:
        return 1 - t
    if t <= 2:
        return -(2 * t - t * t / 2 - 1.5)
    if t <= 3:
        c2 = lambda u: -(2 * u - u * u / 2 - 1.5)                        # y on [1, 2]
        f = lambda s: c2(s - 1)                                           # y' = -y(s - 1) on [2, 3]  ->  y(t) = y(2) - int_2^t y(s-1) ds
        n = 2000
        h = (t - 2) / n
        integral = sum(c2(1 + (k + 0.5) * h) for k in range(n)) * h
        return c2(2) - integral if f else 0.0
    raise ValueError


def test_method_of_steps_against_hand_solution():
    y, _ = None, None
    for t in (0.5, 1.0, 1.7, 2.0, 2.6, 3.0):
        res = dde(lambda tt, yy, lg: [-lg[0]], 0.0, [1.0], t, [(0, 1.0)])
        assert res.final[0] == pytest.approx(exact(t), abs=1e-7), t


def test_calculation_level_delay_and_dimension_rules():
    def mk(eq, tau_unit="s", extra=None):
        return Calculation(id="custom.d", name="d", disciplines=["mechanical"], description="", custom=True, outputs=["y"], equations=[],
                           variables=[V("y", "y", "1", signed=True), V("t", "t", "s"), V("a", "a", "1/s"), V("tau", "tau", tau_unit), V("y0", "y0", "1")],
                           odes=[{"independent": "t", "start": "0", "equations": [eq], "initial": ["y = y0"], **(extra or {})}])
    c = mk("diff(y, t) = -a*delay(y, tau)")
    assert vals(solve(c, {"a": "1 1/s", "tau": "1 s", "y0": "1", "t": "2 s"}, ["y"]))["y"] == pytest.approx(-0.5, abs=1e-7)
    with pytest.raises(ValueError, match="delay"):
        mk("diff(y, t) = -a*delay(y, tau)", tau_unit="kg")
    with pytest.raises(ValueError, match="constant"):
        mk("diff(y, t) = -a*delay(y, y)")
    with pytest.raises(ValueError, match="delay"):
        mk("diff(y, t) = -a*delay(tau, tau)")
    with pytest.raises(ValueError, match="delays|events"):
        mk("diff(y, t) = -a*delay(y, tau)", extra={"events": [{"when": "y = 0", "direction": "falling"}]})


def test_two_delays_and_a_system():
    c = Calculation(id="custom.two", name="d", disciplines=["mechanical"], description="", custom=True, outputs=["x"], equations=[],
                    variables=[V("x", "x", "1", signed=True), V("z", "z", "1", signed=True), V("t", "t", "s"), V("a", "a", "1/s"), V("t1", "t1", "s"), V("t2", "t2", "s")],
                    odes=[{"independent": "t", "start": "0", "equations": ["diff(x, t) = -a*delay(x, t1) - a*delay(z, t2)", "diff(z, t) = a*x"], "initial": ["x = 1", "z = 0"]}])
    s = solve(c, {"a": "0.5 1/s", "t1": "1 s", "t2": "2 s", "t": "6 s"}, ["x"])
    assert s.ok and math.isfinite(vals(s)["x"])


def test_library_delay_calcs():
    d = _ALL["civil.environmental.delayed_logistic_population"]
    r, K, tau, N0, h = 0.5, 100.0, 2.0, 10.0, 1e-4
    lag, N = int(tau / h), [N0]
    for i in range(int(40 / h)):
        N.append(N[i] + h * r * N[i] * (1 - (N[i - lag] if i >= lag else N0) / K))
    assert vals(solve(d, d.example, ["N"]))["N"] == pytest.approx(N[-1], rel=2e-3)             # (the reference is first order: 1e-4 steps)
    back = calc_from_dict({**calc_to_dict(d), "id": "custom.rt"})
    assert vals(solve(back, back.example, ["N"]))["N"] == pytest.approx(vals(solve(d, d.example, ["N"]))["N"])
    # a delay beyond the stability limit a*theta = pi/2 makes the deviation grow
    c = _ALL["mechanical.control.delayed_feedback_sensor_lag"]
    big = solve(c, {"a": "1 1/s", "theta": "2 s", "y0": "1", "t": "60 s"}, ["y"])
    assert abs(vals(big)["y"]) > 10 and any("unstable" in d.message for d in big.diagnostics)


def test_sliding_window_integrals():
    c = Calculation(id="custom.win", name="w", disciplines=["mechanical"], description="", custom=True, outputs=["y"], equations=[],
                    variables=[V("y", "y", "1", signed=True), V("t", "t", "s"), V("k", "k", "1/s^2"), V("w", "w", "s"), V("y0", "y0", "1")],
                    odes=[{"independent": "t", "start": "0", "equations": ["diff(y, t) = -k*integrate(y, (s, t - w, t))"], "initial": ["y = y0"]}])
    k, w, h = 2.0, 0.8, 1e-4
    lag, y, cum = int(round(w / h)), [1.0], [0.0]
    for i in range(int(2 / h)):
        win = cum[i] - (cum[i - lag] if i >= lag else 0.0)
        y.append(y[i] + h * (-k * win))
        cum.append(cum[i] + h * y[i])
    got = vals(solve(c, {"k": "2 1/s^2", "w": "0.8 s", "y0": "1", "t": "2 s"}, ["y"]))["y"]
    assert got == pytest.approx(y[-1], abs=2e-4)
    with pytest.raises(ValueError, match="sliding window|start to"):
        Calculation(id="custom.win2", name="w", disciplines=["mechanical"], description="", custom=True, outputs=["y"], equations=[],
                    variables=[V("y", "y", "1", signed=True), V("t", "t", "s"), V("k", "k", "1/s^2"), V("y0", "y0", "1")],
                    odes=[{"independent": "t", "start": "0", "equations": ["diff(y, t) = -k*integrate(y, (s, t/2, t))"], "initial": ["y = y0"]}])
    avg = _ALL["systems.control.moving_average_feedback"]
    s = solve(avg, avg.example, ["y"])
    assert s.ok and abs(vals(s)["y"]) < 1.0
