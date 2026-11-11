"""LiveCalc: lists and vectors, units that are also function names, and library calculations called from LiveCalc."""

import numpy as np
import pytest

from sliderule import api
from sliderule.core import solve
from sliderule.core.catalog import default_catalog
from sliderule.livecalc import Session, library_example, livecalc_eval, livecalc_library

WIND = 'calc("energy.wind.turbine_power", "Pe", rho = 1.225 kg/m^3, Dr = 100 m, v = {v}, Cp = 0.45, eg = 0.94)'


def run(*lines):
    s = Session(8)
    out = [s.run_line(ln, i + 1) for i, ln in enumerate(lines)]
    return out[-1]


def vals(*lines):
    r = run(*lines)
    assert r["kind"] in ("value", "assign"), r
    return r["value"]


def err(*lines):
    r = run(*lines)
    assert r["kind"] == "error", r
    return r["error"]["message"]


# ---------------------------------------------------------------- lists

def test_lists_carry_units_and_do_arithmetic_value_by_value():
    r = run("v = [1, 2, 3] m")
    assert r["value"] == [1, 2, 3] and r["unit"] == "m" and r["is_list"] and r["length"] == 3
    assert vals("v = [1, 2, 3] m", "v*2") == [2, 4, 6]
    assert vals("[1, 2, 3] m + [10, 20, 30] cm") == pytest.approx([1.1, 2.2, 3.3])
    assert vals("[1 m, 200 cm, 3 m]") == [1, 2, 3]
    assert vals("[1, 2, 3] m to cm") == [100, 200, 300]
    assert vals("v = [1, 4, 9]", "sqrt(v)") == [1, 2, 3]
    assert vals("v = [3, 4] m", "v/2 m") == pytest.approx([1.5, 2])
    assert run("-5 m + [1, 2] m")["value"] == [-4, -3]


def test_indexing_counts_from_one_and_reports_mistakes():
    assert vals("v = [10, 20, 30] kg", "v[2]") == 20 and run("v = [10, 20, 30] kg", "v[2]")["unit"] == "kg"
    assert vals("[5, 6, 7][-1]") == 7 and vals("v = [1, 2, 3]", "v[1] + v[3]") == 4
    assert "outside the list" in err("v = [1, 2]", "v[0]") and "outside the list" in err("v = [1, 2]", "v[3]")
    assert "whole number" in err("v = [1, 2]", "v[1.5]") and "Only a list" in err("x = 5", "x[1]")


def test_list_errors():
    assert "same units" in err("[1 m, 2 s]")
    assert "Cannot add" in err("[1, 2] m + [1, 2] s")
    assert "matrix needs rows" in err("[[1, 2], 3]")
    assert "different lengths" in err("[1, 2, 3] + [1, 2]") and "different lengths" in err("[1, 2, 3] * [1, 2]") and "different lengths" in err("atan2([1, 2, 3], [1, 2])")


def test_reductions_and_list_functions():
    assert vals("sum([1, 2, 3, 4])") == 10 and vals("mean([2, 4, 9])") == 5 and vals("median([5, 1, 3])") == 3
    assert vals("stdev([2, 4, 4, 4, 5, 5, 7, 9])") == pytest.approx(2.13808994)
    assert vals("min([4, 2, 9])") == 2 and vals("max([4, 2, 9] m)") == 9 and vals("hypot([3, 4] m)") == 5
    assert vals("len([4, 5, 6])") == 3 and vals("sort([3, 1, 2])") == [1, 2, 3] and vals("reverse([1, 2, 3])") == [3, 2, 1]
    assert vals("cumsum([1, 2, 3, 4])") == [1, 3, 6, 10] and vals("diff([1, 4, 9, 16])") == [3, 5, 7] and vals("prod([2, 3, 4])") == 24
    assert vals("range(5)") == [0, 1, 2, 3, 4] and vals("range(2, 10, 3)") == [2, 5, 8] and vals("range(0 m, 10 m, 4 m)") == [0, 4, 8]
    assert vals("linspace(0 s, 1 s, 5)") == pytest.approx([0, 0.25, 0.5, 0.75, 1])
    assert vals("v = [1, 2, 3]", "sum(v*v)") == 14                                    # sum of squares
    assert "at least" in err("stdev([3])") and "whole number of points" in err("linspace(0, 1, 1)") and "no values or more" in err("range(5, 1)")


def test_vector_products_follow_units():
    r = run("dot([10, 0] N, [3, 4] m)")
    assert r["value"] == 30 and r["unit"] == "N*m"
    r = run("cross([1, 0, 0] m, [0, 2, 0] N)")
    assert r["value"] == [0, 0, 2] and r["unit"] == "m*N"
    assert vals("norm([3, 4] m)") == 5 and vals("dot([1, 2, 3], [4, 5, 6])") == 32
    assert "same length" in err("dot([1, 2], [1, 2, 3])") and "three values" in err("cross([1, 2], [3, 4])")


def test_long_lists_are_shortened_in_the_display_but_not_in_the_value():
    r = run("range(100)")
    assert r["length"] == 100 and len(r["value"]) == 100 and "more" in r["value_text"] and r["value_text"].startswith("[0, 1, 2, 3, 4,")
    assert "at most" in err("range(1000)") or "more than" in err("range(1000)")


def test_functions_of_a_list_stay_elementwise_while_plotting():
    s = Session(6)
    s.run_line("f(x) = sum(x, 1)", 1)
    r = s.run_line("plot f from 0 to 3", 2)                              # plotting arrays are samples, so sum(x, 1) is x + 1 at every point
    assert r["kind"] == "plot" and r["plot"]["series"][0]["y"][0] == pytest.approx(1)
    s.run_line("g(x) = mean(x)", 3)
    assert s.run_line("plot g from 0 to 3", 4)["plot"]["series"][0]["y"][-1] == pytest.approx(3)       # mean of one value is the value
    assert s.run_line("g([1, 2, 6])", 5)["value"] == 3                                                   # outside a plot the same function averages the list


# ---------------------------------------------------------------- units that are also function names

def test_min_and_max_work_as_units_unless_called():
    assert run("20 L/min to m^3/s")["value"] == pytest.approx(20e-3 / 60)
    assert run("5 min to s")["value"] == 300 and run("3 min + 2 min")["value"] == 5
    assert run("min(4, 2, 9)")["value"] == 2 and run("max(1 min, 30 s) to s")["value"] == 60


def test_unit_groups_in_a_denominator_and_negative_offset_temperatures():
    assert run("0.2 L/(mg*min) * 3 mg/L * 5 min")["value"] == pytest.approx(3)
    assert run("5 m/(2 s)")["value"] == 2.5 and run("6 m/(2 m)")["value"] == 3                     # a number in the brackets is a number, not a unit
    assert run("-56.5 degC to K")["value"] == pytest.approx(216.65)
    assert run("-5 m + 2 m")["value"] == -3 and run("-2^2")["value"] == -4


# ---------------------------------------------------------------- library calculations

def test_calc_solves_a_library_calculation_and_matches_the_engine():
    r = run(WIND.format(v="10 m/s"))
    assert r["kind"] == "value" and r["unit"] == "kW"
    c = default_catalog().get("energy.wind.turbine_power")
    ex = solve(c, {"rho": "1.225 kg/m^3", "Dr": "100 m", "v": "10 m/s", "Cp": "0.45", "eg": "94 %"}, solve_for=["Pe"])   # LiveCalc has no %: 0.94 is the same efficiency
    assert r["si_value"] == pytest.approx(next(o["si_value"] for o in ex.outputs if o["key"] == "Pe"), rel=1e-9)
    assert run(WIND.format(v="10 m/s").replace('"energy.wind.turbine_power"', '"turbine_power"'))["si_value"] == pytest.approx(r["si_value"])    # the end of the id is enough
    assert run(WIND.format(v="10 m/s").replace('"Pe"', '"Ar"').replace(", Cp = 0.45, eg = 0.94", ""))["kind"] == "value"          # another output, fewer inputs
    assert run(WIND.format(v="10 m/s").replace("energy.wind.turbine_power", "turbine_power").replace('"turbine_power"', "turbine_power").replace('"Pe"', "Pe"))["kind"] == "value"   # bare names work too


def test_calc_over_a_list_is_a_sweep_and_can_be_plotted_and_converted():
    r = run("w = [5, 10, 15] m/s", WIND.format(v="w"))
    assert r["is_list"] and r["length"] == 3 and r["unit"] == "kW"
    one = [run(WIND.format(v=f"{v} m/s"))["si_value"] for v in (5, 10, 15)]
    assert r["si_value"] == pytest.approx(one, rel=1e-9)
    assert r["si_value"][2] / r["si_value"][1] == pytest.approx(27 / 8, rel=1e-6)                     # power goes as the cube of the speed
    assert run("w = [5, 10, 15] m/s", "P = " + WIND.format(v="w"), "P to MW")["value"] == pytest.approx([x / 1e6 for x in one])
    s = Session(6)
    s.run_line("f(v) = " + WIND.format(v="v"), 1)
    pl = s.run_line("plot f from 3 m/s to 20 m/s", 2)
    assert pl["kind"] == "plot" and len(pl["plot"]["series"][0]["y"]) == 300 and pl["plot"]["y_unit"] == "kW"
    assert s.run_line("f(7 m/s)", 3)["value"] == pytest.approx(run(WIND.format(v="7 m/s"))["value"])


def test_calc_errors_explain_themselves():
    assert "No library calculation matches" in err('calc("zzzzzz")')
    assert "matches" in err('calc("wind")') and "full id" in err('calc("wind")')
    assert "has no input" in err('calc("turbine_power", "Pe", bogus = 1)')
    assert "no output" in err('calc("turbine_power", "bogus")')
    assert "cannot be negative" in err(WIND.format(v="-3 m/s"))
    assert "also need values" in err('calc("turbine_power", "Pe", v = 5 m/s)')
    assert "same length" in err("a = [1, 2, 3] m/s", "b = [1, 2] m", WIND.format(v="a").replace("Dr = 100 m", "Dr = b"))
    assert "text in quotes" in err("x = 5", 'calc(x)')


def test_calc_names_are_not_taken_for_unknown_variables():
    s = Session(6)
    r = s.run_line("P = " + WIND.format(v="10 m/s"), 1)
    assert r["kind"] == "assign" and not r["formula"]            # a calculation, not an equation with unknowns named turbine_power, Pe, rho ...


def test_library_examples_run_in_livecalc():
    cat = default_catalog()
    sample = [c for c in cat if not c.custom and not c.parsed_odes and not c.tables][::11]
    bad = []
    for c in sample:
        r = Session(6).run_line(library_example(c), 1)
        if r["kind"] != "value":
            bad.append((c.id, r.get("error", {}).get("message", "")[:80]))
    assert len(bad) <= len(sample) * 0.03, bad                                  # a few calculations use units LiveCalc cannot write (fractional powers)


def test_library_search_rpc():
    out = livecalc_library("wind turbine power")
    assert out["total"] >= 1 and out["items"][0]["id"] == "energy.wind.turbine_power" and out["items"][0]["ok"]
    assert out["items"][0]["example"].startswith('calc("energy.wind.turbine_power"') and {i["key"] for i in out["items"][0]["inputs"]} >= {"rho", "Dr", "v"}
    assert livecalc_library("x")["items"] == [] and livecalc_library("")["total"] == 0
    via = api.handle("livecalc_library", {"query": "wind turbine power", "limit": 3})
    assert via["ok"] and len(via["result"]["items"]) <= 3


def test_lines_with_lists_do_not_break_markdown_and_prose():
    out = livecalc_eval(entries=["[a link](https://example.com)", "- [x] done", "[1, 2, 3] m"], draft="")
    kinds = [e["lines"][0]["kind"] for e in out["entries"]]
    assert kinds == ["text", "text", "value"]
    assert np.isclose(out["entries"][2]["lines"][0]["value"], [1, 2, 3]).all()
