import math

import pytest

from sliderule import api, settings
from sliderule.core import Calculation, V, solve


def mk(eq, extra=(), init=("y = y0",), method="auto"):
    return Calculation(id="custom.i", name="i", disciplines=["mechanical"], description="", custom=True, equations=[], outputs=["y"],
                       variables=[V("y", "y", "m", signed=True), V("y0", "y0", "m", signed=True), V("k", "k", "1/s"), V("t", "t", "s"), *extra],
                       odes=[{"independent": "t", "method": method, "equations": [eq], "initial": list(init)}])


def y_at(c, **vals):
    base = {"y0": "1 m", "k": "2 1/s", "t": "1.5 s"}
    r = solve(c, {**base, **vals}).to_dict()
    assert r["ok"], r["diagnostics"]
    return r["outputs"][0]["si_value"]


def test_an_integral_that_does_not_involve_the_unknown_is_evaluated_first():
    # y' = -k y + ∫0^2 x0 s ds = -k y + 2 x0   ->   y = 2 x0 / k + (y0 - 2 x0 / k) e^(-k t)
    c = mk("diff(y, t) = -k*y + integrate(x0*s, (s, 0, 2))", [V("x0", "x0", "m/s")])
    assert not c.parsed_odes[0].numeric and not c.parsed_odes[0].pre
    assert y_at(c, x0="3 m/s") == pytest.approx(3.0 + (1 - 3.0) * math.exp(-3.0), rel=1e-9)


def test_an_integral_from_the_start_to_t_with_a_closed_form_is_substituted():
    # y' = -k y + g ∫0^t e^(-s/tau) ds = -k y + g tau (1 - e^(-t/tau))
    c = mk("diff(y, t) = -k*y + integrate(exp(-s/tau), (s, 0, t))*g", [V("tau", "tau", "s"), V("g", "g", "m/s^2")])
    assert c.parsed_odes[0].aux_count == 0 and not c.parsed_odes[0].numeric
    got = y_at(c, tau="1 s", g="2 m/s^2")
    # reference by fine RK4
    y, h = 1.0, 1e-4
    f = lambda t, y: -2 * y + 2 * (1 - math.exp(-t))     # noqa: E731
    for i in range(int(1.5 / h)):
        t = i * h
        k1 = f(t, y); k2 = f(t + h / 2, y + h / 2 * k1); k3 = f(t + h / 2, y + h / 2 * k2); k4 = f(t + h, y + h * k3)
        y += h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
    assert got == pytest.approx(y, rel=1e-8)


def test_an_integral_of_the_unknown_becomes_a_hidden_state_and_can_still_have_a_closed_form():
    # y' = -k y - ki ∫0^t y ds with k = 3, ki = 1: y(t) = ... (distinct real roots), y0 = 1
    c = mk("diff(y, t) = -k*y - ki*integrate(y, (s, 0, t))", [V("ki", "ki", "1/s^2")])
    sysm = c.parsed_odes[0]
    assert sysm.aux_count == 1 and not sysm.numeric
    r1, r2 = (-3 + math.sqrt(5)) / 2, (-3 - math.sqrt(5)) / 2          # roots of m^2 + 3m + 1 = 0;  y(0) = 1, y'(0) = -3
    A = (-3 - r2) / (r1 - r2)
    B = 1 - A
    assert y_at(c, k="3 1/s", ki="1 1/s^2") == pytest.approx(A * math.exp(r1 * 1.5) + B * math.exp(r2 * 1.5), rel=1e-9)


def test_a_singular_closed_form_falls_back_to_numerical_integration():
    c = mk("diff(y, t) = -k*y - ki*integrate(y, (s, 0, t))", [V("ki", "ki", "1/s^2")])
    r = solve(c, {"y0": "1 m", "k": "2 1/s", "ki": "1 1/s^2", "t": "1.5 s"}, ode_times=["0.5 s"]).to_dict()      # k^2 = 4 ki: critical damping, 0/0 in the formula
    assert r["ok"] and [d["code"] for d in r["diagnostics"]] == ["ODE_NUMERIC_FALLBACK"]
    assert r["outputs"][0]["si_value"] == pytest.approx((1 - 1.5) * math.exp(-1.5), rel=1e-6)                       # y = (1 - t) e^(-t)
    assert r["series"][0]["method"]["method"].startswith("RK45") and [row["t"] for row in r["table"]] == ["0.5", "1.5"]
    steps = [ln.note for st in solve(c, {"y0": "1 m", "k": "2 1/s", "ki": "1 1/s^2", "t": "1.5 s"}).steps["numeric"] for ln in st.lines]
    assert any("numerical integration of the differential equation" in n for n in steps)


def test_an_integral_without_a_closed_form_that_does_not_involve_the_unknown_is_integrated_numerically_once():
    c = mk("diff(y, t) = -k*y + integrate(x0*s**s, (s, 0, 1))", [V("x0", "x0", "m/s")])
    assert c.parsed_odes[0].pre and c.parsed_odes[0].numeric
    I = 0.7834305107121344
    assert y_at(c, x0="1 m/s", t="1 s") == pytest.approx(I / 2 + (1 - I / 2) * math.exp(-2), rel=1e-6)


def test_hard_cases_are_refused_with_a_reason():
    with pytest.raises(Exception, match="must run from the start"):
        mk("diff(y, t) = -k*integrate(y, (s, 1, t))")
    with pytest.raises(Exception, match="sliding window|delay has dimension"):
        mk("diff(y, t) = -k*integrate(y, (s, t/2, t))")             # a variable limit that is not "t minus a constant"
    with pytest.raises(Exception, match="must be definite"):
        mk("diff(y, t) = -k*integrate(y, s)")
    with pytest.raises(Exception, match="nested"):
        mk("diff(y, t) = -k*integrate(integrate(y, (u, 0, t)), (s, 0, t))")
    with pytest.raises(Exception, match="different dimensions"):
        mk("diff(y, t) = -k*y - integrate(y, (s, 0, t))")           # k y is m/s but ∫y ds is m s


def test_the_pi_controller_library_calculation_matches_an_independent_integration():
    cid = "systems.control.pi_control_first_order"
    c = api.get_calculation(cid)
    r = api.solve(cid, dict(c["example"]))
    assert not [d for d in r["diagnostics"] if d["level"] != "info"]
    y, z, h = 20.0, 0.0, 0.0005
    f = lambda y, z: ((-y + 1 * (2 * (50 - y) + 0.15 * z)) / 30, 50 - y)   # noqa: E731
    for _ in range(int(60 / h)):
        k1 = f(y, z); k2 = f(y + h / 2 * k1[0], z + h / 2 * k1[1]); k3 = f(y + h / 2 * k2[0], z + h / 2 * k2[1]); k4 = f(y + h * k3[0], z + h * k3[1])
        y += h / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]); z += h / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
    assert r["outputs"][0]["si_value"] == pytest.approx(y, rel=1e-6)
    assert r["series"] and len(r["series"][0]["t"]) == 201


def test_time_limit_still_applies_to_numerical_integrals_in_the_equation():
    settings.update(timeout_seconds=1)
    c = mk("diff(y, t) = -k*y + integrate(x0*s**s, (s, 0, 1))", [V("x0", "x0", "m/s")])
    assert c.parsed_odes[0].pre            # building is quick; the integral itself is evaluated at run time under the limit
