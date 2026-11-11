
import pytest

from sliderule.core import solve
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


def vals(sol):
    return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}


def test_gauge_pressure_in_and_out():
    c = _ALL["civil.hydraulics.hydrostatic_absolute_gauge"]
    given = {"rho": "1000 kg/m^3", "h": "30 m", "patm": "101.325 kPa"}
    sol = solve(c, given, ["p"], output_units={"p": "psig"})
    assert sol.to_dict()["outputs"][0]["value"] == pytest.approx(1000 * 9.80665 * 30 / 6894.757293168361, rel=1e-9)
    # a gauge reading as the input: 5 barg is 6.01325 bar absolute, so the depth follows
    sol = solve(c, {"rho": "1000 kg/m^3", "p": "5 barg", "patm": "101.325 kPa"}, ["h"])
    assert vals(sol)["h"] == pytest.approx(5e5 / (1000 * 9.80665), rel=1e-9)


def test_dbm_level_and_link_budget_in_both_directions():
    c = _ALL["electrical.rf.dbm_power_level"]
    g = {"Gt": "12 dB", "Gr": "3 dB", "Lp": "110 dB", "Lm": "4 dB"}
    v = vals(solve(c, {"Ptx": "100 mW", **g}, ["Ltx", "Lrx", "Prx"]))
    assert v["Ltx"] == pytest.approx(20) and v["Lrx"] == pytest.approx(-79)
    assert v["Prx"] == pytest.approx(10 ** (-7.9) * 1e-3, rel=1e-9)
    back = vals(solve(c, {"Prx": "1 uW", **g}, ["Ptx"]))
    assert back["Ptx"] == pytest.approx(10 ** (69 / 10) * 1e-3, rel=1e-9)


def test_log10_can_be_rearranged_for_its_argument():
    from sliderule.core import Calculation, V

    c = Calculation(id="custom.lg", name="l", disciplines=["electrical"], description="", custom=True,
                    variables=[V("x", "x", "W"), V("L", "L", "dB", signed=True, units=["dB"]), V("x0", "x0", "W")],
                    equations=["L = 10*log10(x/x0)"], outputs=["x"])
    assert vals(solve(c, {"L": "30 dB", "x0": "1 mW"}, ["x"]))["x"] == pytest.approx(1.0)
