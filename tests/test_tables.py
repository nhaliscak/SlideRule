
import numpy as np
import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import CustomError, calc_from_dict, calc_to_dict
from sliderule.core.tables import TableError, check_data, interpolator
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def vals(sol):
    return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}


def test_interpolation_methods_and_derivatives():
    xs, ys = [0.0, 1.0, 2.0, 4.0], [1.0, 3.0, 4.0, 10.0]
    f, df = interpolator(xs, ys, "linear", "error")
    assert f(0.5) == pytest.approx(2.0) and df(0.5) == pytest.approx(2.0) and f(3) == pytest.approx(7.0) and df(3) == pytest.approx(3.0)
    g, dg = interpolator(xs, ys, "pchip", "error")
    assert g(2.0) == pytest.approx(4.0) and 3.0 <= g(1.5) <= 4.0                     # monotone data stay monotone: no overshoot
    h = 1e-6
    assert dg(1.5) == pytest.approx((g(1.5 + h) - g(1.5 - h)) / (2 * h), rel=1e-5)
    lx, ly = [1.0, 10.0, 100.0], [100.0, 10.0, 1.0]
    p, dp = interpolator(lx, ly, "loglog", "error")
    assert p(3.0) == pytest.approx(100 / 3.0) and dp(3.0) == pytest.approx(-100 / 9.0)   # y = 100/x is exactly a straight line on log-log axes


def test_outside_the_range():
    xs, ys = [0.0, 1.0, 2.0], [0.0, 1.0, 4.0]
    with pytest.raises(ArithmeticError, match="outside the tabulated range"):
        interpolator(xs, ys, "linear", "error")[0](2.5)
    assert interpolator(xs, ys, "linear", "clamp")[0](9) == 4.0
    assert interpolator(xs, ys, "linear", "extrapolate")[0](3) == pytest.approx(7.0)


def test_bad_tables_are_rejected():
    for args in [([1, 1], [1, 2], "linear", "error"), ([1], [1], "linear", "error"), ([1, 2], [1], "linear", "error"), ([0, 1], [1, 2], "loglog", "error"),
                 ([1, 2], [1, float("nan")], "linear", "error"), ([1, 2], [1, 2], "spline", "error")]:
        with pytest.raises(TableError):
            check_data(*args)


def test_pump_operating_point_matches_an_independent_solution():
    c = _ALL["mechanical.fluids.pump_operating_point_from_curve"]
    v = vals(solve(c, c.example, ["Q", "H"]))
    from scipy.interpolate import PchipInterpolator
    from scipy.optimize import brentq

    pump = PchipInterpolator(np.array([0, 10, 20, 30, 40, 50]) / 1000, [52, 50, 45, 36, 22, 4])
    q = brentq(lambda q: float(pump(q)) - (10 + 8000 * q * q), 0, 0.05)
    assert v["Q"] == pytest.approx(q, rel=1e-9) and v["H"] == pytest.approx(10 + 8000 * q * q, rel=1e-9)
    # the other direction: which static head puts the operating point at 25 L/s?
    inv = vals(solve(c, {"K": "8000 s^2/m^5", "Q": "25 L/s"}, ["Hs"]))
    assert inv["Hs"] == pytest.approx(float(pump(0.025)) - 8000 * 0.025**2, rel=1e-9)


def test_offset_units_and_inversion_of_a_steam_table():
    c = _ALL["mechanical.thermo.saturation_temperature_steam_table"]
    assert vals(solve(c, {"P": "100 kPa"}, ["Tsat"]))["Tsat"] == pytest.approx(99.61 + 273.15)
    assert vals(solve(c, {"Tsat": "179.88 degC"}, ["P"]))["P"] == pytest.approx(1e6, rel=1e-9)
    s = solve(c, {"P": "1 kPa"}, ["Tsat"])
    assert not s.ok and "outside the tabulated range" in " ".join(d.message for d in s.diagnostics)


def test_argument_dimension_is_checked_and_names_cannot_clash():
    tab = {"name": "f", "x_unit": "m", "y_unit": "s", "x": [0, 1], "y": [0, 1]}
    mk = lambda **kw: Calculation(id="custom.t", name="t", disciplines=["mechanical"], description="", custom=True, tables=[tab], outputs=["y"],
                                  variables=[V("x", "x", kw.get("xu", "m")), V("y", "y", "s")], equations=["y = f(x)"])
    mk()
    with pytest.raises(ValueError, match="argument"):
        mk(xu="kg")
    with pytest.raises(ValueError, match="already used"):
        Calculation(id="custom.t2", name="t", disciplines=["mechanical"], description="", custom=True, tables=[{**tab, "name": "sin"}], outputs=["y"],
                    variables=[V("x", "x", "m"), V("y", "y", "s")], equations=["y = sin(x)"])


def test_tables_round_trip_and_validate_in_the_custom_format():
    c = _ALL["mechanical.fatigue.cycles_to_failure_from_sn_table"]
    doc = calc_to_dict(c)
    assert doc["tables"][0]["name"] == "sn_curve" and doc["tables"][0]["method"] == "loglog"
    back = calc_from_dict({**doc, "id": "custom.sn"})
    assert vals(solve(back, back.example, ["N"]))["N"] == pytest.approx(vals(solve(c, c.example, ["N"]))["N"])
    bad = {**doc, "id": "custom.bad", "tables": [{**doc["tables"][0], "x": [3, 2, 1, 0, -1]}]}
    with pytest.raises(CustomError, match="increase"):
        calc_from_dict(bad)
