import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


def get(cid):
    return _ALL[cid]


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def vals(sol):
    return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}


def test_complex_equation_splits_into_real_and_imaginary_parts():
    c = get("electrical.circuits.series_rlc_phasor")
    assert [e.part for e in c.parsed] == ["re", "im", ""]
    w = 2 * math.pi * 60
    x = w * 0.01 - 1 / (w * 100e-6)
    sol = solve(c, {"Vs": "120 V", "R": "10 ohm", "L": "10 mH", "C": "100 uF", "f": "60 Hz"}, ["Z", "th", "Im"])
    v = vals(sol)
    assert v["Z"] == pytest.approx(math.hypot(10, x), rel=1e-9)
    assert v["th"] == pytest.approx(math.atan2(x, 10), rel=1e-9)
    assert v["Im"] == pytest.approx(120 / math.hypot(10, x), rel=1e-9)
    assert not [d for d in sol.diagnostics if d.level != "info"]


def test_rc_divider_and_power_triangle():
    v = vals(solve(get("electrical.circuits.rc_divider_phasor"), {"Vin": "5 V", "R": "1 kohm", "C": "0.1 uF", "f": "1 kHz"}, ["Vout", "ph"]))
    k = 2 * math.pi * 1000 * 1000 * 0.1e-6
    assert v["Vout"] == pytest.approx(5 / math.sqrt(1 + k * k), rel=1e-9)
    assert v["ph"] == pytest.approx(-math.atan(k), rel=1e-9)
    p = vals(solve(get("electrical.power.complex_power_triangle"), {"Vrms": "230 V", "Irms": "12 A", "phi": "0.5 rad"}, ["P", "Q"]))
    assert p["P"] == pytest.approx(230 * 12 * math.cos(0.5), rel=1e-9)
    assert p["Q"] == pytest.approx(230 * 12 * math.sin(0.5), rel=1e-9)


def test_solving_for_a_component_from_the_phase():
    # reactance from a measured phase: tan(theta) = X / R, so C follows
    c = get("electrical.circuits.series_rlc_phasor")
    ref = vals(solve(c, {"Vs": "120 V", "R": "10 ohm", "L": "10 mH", "C": "100 uF", "f": "60 Hz"}, ["Z", "th"]))
    sol = solve(c, {"Vs": "120 V", "R": "10 ohm", "L": "10 mH", "th": f"{ref['th']} rad", "f": "60 Hz"}, ["C"])
    assert vals(sol)["C"] == pytest.approx(100e-6, rel=1e-6)


def test_complex_functions_and_dimension_rules():
    def mk(eq, extra=()):
        return Calculation(id="custom.cx", name="c", disciplines=["electrical"], description="", custom=True,
                           variables=[V("a", "a", "ohm"), V("b", "b", "ohm"), V("m", "m", "ohm"), V("t", "t", "rad", signed=True), *extra],
                           equations=eq, outputs=["m", "t"])
    c = mk(["m = Abs(a + j*b)", "t = arg(a + j*b)"])
    v = vals(solve(c, {"a": "3 ohm", "b": "4 ohm"}, ["m", "t"]))
    assert v["m"] == pytest.approx(5) and v["t"] == pytest.approx(math.atan2(4, 3))
    with pytest.raises(ValueError, match="dimension"):
        mk(["m = Abs(a + j*t)", "t = arg(a + j*b)"])
    with pytest.raises(ValueError, match="trivially"):
        mk(["j*m = j*m", "t = arg(a + j*b)"])


def test_custom_calc_with_complex_equation_round_trips():
    from sliderule.core.custom import calc_from_dict, calc_to_dict

    c = get("electrical.power.complex_power_triangle")
    d = calc_to_dict(c)
    assert len(d["equations"]) == 1 and d["equations"][0]["text"] == "P + j*Q = Vrms*Irms*exp(j*phi)"
    assert [e.part for e in calc_from_dict({**d, 'id': 'custom.rt'}).parsed] == ['re', 'im']
