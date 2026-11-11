import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import CustomError, calc_from_dict
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def make(eq, variables=None, out=("y",)):
    return Calculation(id="custom.inf", name="s", disciplines=["mechanical"], description="", custom=True,
                       variables=variables or [V("y", "y", "1", signed=True)], equations=[eq], outputs=list(out))


def value(c, given=None, key="y"):
    s = solve(c, given or {}, [key])
    assert s.ok, [d.message for d in s.diagnostics]
    return next(o["si_value"] for o in s.to_dict()["outputs"] if o["key"] == key)


@pytest.mark.parametrize("term,start,exact", [
    ("1/n**2", 1, math.pi**2 / 6),                                   # algebraic tail: needs acceleration, not just 20 000 terms
    ("(-1)**n/n", 1, -math.log(2)),                                  # conditionally convergent
    ("sin(2*n - 1)/(2*n - 1)", 1, math.pi / 4),                      # the Fourier square wave at x = 1
    ("1/factorial(n)", 0, math.e),
    ("n*0.5**n", 1, 2.0),
    ("1/(n**2 + 1)", 1, (math.pi / math.tanh(math.pi) - 1) / 2),
])
def test_known_series_are_summed_accurately(term, start, exact):
    assert value(make(f"y = summation({term}, (n, {start}, oo))")) == pytest.approx(exact, rel=1e-8)


def test_parameters_and_inversion_through_an_infinite_sum():
    c = make("y = summation(x**n/n**2, (n, 1, oo))", [V("y", "y", "1"), V("x", "x", "1", min=0, max=1)])
    assert value(c, {"x": "0.5"}) == pytest.approx(0.5822405264650125, rel=1e-9)          # the dilogarithm Li2(1/2)
    assert value(c, {"y": "0.5822405264650125"}, "x") == pytest.approx(0.5, rel=1e-6)


@pytest.mark.parametrize("term", ["1/n", "2**n", "n", "(-1)**n*n", "n**(-1.5)"])
def test_divergent_or_unprovable_series_are_refused(term):
    s = solve(make(f"y = summation({term}, (n, 1, oo))"), {}, ["y"])
    assert not s.ok
    assert any("series" in d.message for d in s.diagnostics)


def test_library_series_agree_with_independent_values():
    c = _ALL["mechanical.heat.plate_centreline_temperature_infinite_series"]
    fo = 1.2e-5 * 30 / 0.02**2
    th = sum(4 * (-1) ** n / ((2 * n + 1) * math.pi) * math.exp(-((2 * n + 1) ** 2) * math.pi**2 * fo / 4) for n in range(500))
    assert value(c, c.example, "Tc") == pytest.approx(300 + 200 * th, rel=1e-10)
    q = _ALL["industrial.queueing.mm1_mean_number_in_system_series"]
    assert value(q, {"rho": "0.8"}, "L") == pytest.approx(4.0, rel=1e-9) and value(q, {"L": "9"}, "rho") == pytest.approx(0.9, rel=1e-6)


def test_syntax_limits():
    with pytest.raises(CustomError):
        calc_from_dict({"id": "custom.bad", "name": "b", "disciplines": ["mechanical"], "variables": [{"key": "y", "label": "y"}],
                        "equations": [{"text": "y = summation(1/n, (n, 1, 2.5))"}], "outputs": ["y"]})
    ok = calc_from_dict({"id": "custom.ok", "name": "b", "disciplines": ["mechanical"], "variables": [{"key": "y", "label": "y"}],
                         "equations": [{"text": "y = summation(0.5**n, (n, 0, oo))"}], "outputs": ["y"]})
    assert value(ok) == pytest.approx(2.0)
