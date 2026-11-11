import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import CustomError, calc_from_dict, calc_to_dict
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def vals(sol):
    return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}


def mk(equations, functions, variables=None, out=("A",), custom=True):
    return Calculation(id="custom.f", name="f", disciplines=["mechanical"], description="", custom=custom, functions=functions, equations=equations, outputs=list(out),
                       variables=variables or [V("a", "a", "m"), V("b", "b", "m"), V("A", "A", "m^2")])


def test_function_is_expanded_where_called_and_everything_can_be_solved_for():
    c = mk(["A = rect(a, b)"], [{"name": "rect", "args": ["w", "h"], "body": "w*h"}])
    assert vals(solve(c, {"a": "3 m", "b": "4 m"}, ["A"]))["A"] == pytest.approx(12)
    assert vals(solve(c, {"A": "12 m^2", "b": "4 m"}, ["a"]))["a"] == pytest.approx(3)


def test_functions_are_dimension_checked_through_the_call():
    c = mk(["A = rect(a, b)"], [{"name": "rect", "args": ["w", "h"], "body": "w*h"}])
    assert c.parsed[0].rhs.free_symbols == {c.by_key["a"].symbol, c.by_key["b"].symbol}
    with pytest.raises(ValueError, match="dimension|homogeneous"):
        mk(["A = rect(a, b) + a"], [{"name": "rect", "args": ["w", "h"], "body": "w*h"}])


def test_functions_may_use_earlier_functions_variables_and_constants_but_not_themselves():
    fs = [{"name": "sq", "args": ["x"], "body": "x**2"}, {"name": "area", "args": ["w", "h"], "body": "sq(w) + w*h"}]
    c = mk(["A = area(a, b)"], fs)
    assert vals(solve(c, {"a": "3 m", "b": "4 m"}, ["A"]))["A"] == pytest.approx(21)
    with pytest.raises(Exception):
        mk(["A = loop(a)"], [{"name": "loop", "args": ["x"], "body": "loop(x)"}])


@pytest.mark.parametrize("bad,match", [
    ({"name": "sin", "args": ["x"], "body": "x"}, "already used"),
    ({"name": "a", "args": ["x"], "body": "x"}, "already used"),
    ({"name": "g", "args": [], "body": "1"}, "argument"),
    ({"name": "g", "args": ["x", "x"], "body": "x"}, "argument"),
    ({"name": "g", "args": ["x"], "body": "y = x"}, "expression"),
])
def test_bad_function_definitions(bad, match):
    with pytest.raises(ValueError, match=match):
        mk(["A = a*b"], [bad])


def test_call_arity_is_checked():
    with pytest.raises(Exception, match="argument"):
        mk(["A = rect(a)"], [{"name": "rect", "args": ["w", "h"], "body": "w*h"}])


def test_product_of_factors():
    c = Calculation(id="custom.p", name="p", disciplines=["industrial"], description="", custom=True, outputs=["Y"],
                    variables=[V("Y", "Y", "1"), V("d", "d", "1")], equations=["Y = product(1 - d*i, (i, 1, 4))"])
    assert vals(solve(c, {"d": "0.1"}, ["Y"]))["Y"] == pytest.approx(0.9 * 0.8 * 0.7 * 0.6)
    with pytest.raises(Exception, match="product|factors"):
        Calculation(id="custom.p2", name="p", disciplines=["industrial"], description="", custom=True, outputs=["Y"],
                    variables=[V("Y", "Y", "1"), V("d", "d", "1")], equations=["Y = product(1 - d*i, (i, 1, 80))"])


def test_library_function_calcs_and_round_trip():
    c = _ALL["civil.hydraulics.two_pipe_sections_swamee_jain"]
    assert vals(solve(c, c.example, ["dp"]))["dp"] == pytest.approx(94.142e3, rel=1e-5)
    doc = calc_to_dict(c)
    assert doc["functions"][0]["name"] == "fsj"
    back = calc_from_dict({**doc, "id": "custom.rt"})
    assert vals(solve(back, back.example, ["dp"]))["dp"] == pytest.approx(vals(solve(c, c.example, ["dp"]))["dp"])
    with pytest.raises(CustomError):
        calc_from_dict({**doc, "id": "custom.bad", "functions": [{"name": "f", "args": "", "body": "1"}]})
    y = _ALL["industrial.manufacturing.rolled_throughput_yield_product"]
    got = vals(solve(y, {"Y": "0.8", "d": "0.01"}, ["y1"]))["y1"]
    assert math.prod(got - 0.01 * i for i in range(6)) == pytest.approx(0.8) and 0 < got < 1      # the root inside the allowed range, not an algebraic one


def test_high_degree_polynomial_unknowns_use_the_allowed_range():
    c = Calculation(id="custom.poly", name="p", disciplines=["mechanical"], description="", custom=True, outputs=["x"],
                    variables=[V("x", "x", "1", min=0, max=2), V("y", "y", "1")], equations=["y = x**3 - 3*x**2 + 2*x + 1"])
    s = solve(c, {"y": "0.8"}, ["x"])           # two roots lie in [0, 2] (and one outside it): any returned root must be a genuine one inside the range
    x = vals(s)["x"]
    assert s.ok and 0 <= x <= 2 and x**3 - 3 * x**2 + 2 * x + 1 == pytest.approx(0.8)
