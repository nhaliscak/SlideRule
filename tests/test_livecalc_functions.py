"""LiveCalc: the function catalogue (every example is run) and plotting the functions defined in the history."""

import math

import pytest

from sliderule import api, livecalc, livecalc_help


def test_every_function_and_constant_is_in_the_catalogue_with_working_examples():
    cat = livecalc_help.functions_catalog()
    names = {i["name"] for i in cat["items"]}
    assert set(livecalc.FUNCTIONS) <= names and set(livecalc.CONSTANTS) <= names and set(livecalc.QCONSTANTS) <= names
    for item in cat["items"]:
        assert item["examples"] and item["summary"] and item["signature"], item["name"]
        for ex in item["examples"]:
            assert ex["ok"], (item["name"], ex["text"], ex.get("error"))
            assert ex["result_text"]
    assert "Commands and syntax" in cat["categories"] and "Trigonometry" in cat["categories"]


def test_examples_show_the_values_the_engine_computes():
    by = {(i["name"], e["text"]): e["result_text"] for i in livecalc_help.functions_catalog()["items"] for e in i["examples"]}
    assert by[("sqrt", "sqrt(16 m^2)")] == "4 m"
    assert by[("sin", "sin(30 deg)")] == "0.5"
    assert by[("to", "120 km/h to m/s")] == "33.3333 m/s"
    assert by[("f(x) =", "f(x) = 3*x^2 - 2\nf(4)")] == "46"
    assert by[("plot", "plot sin(x), cos(x) from 0 to 2*pi")] == "a graph of 2 curves"


def test_the_catalogue_is_reachable_through_the_api():
    res = api.handle("livecalc_functions", {})
    assert res["ok"] and len(res["result"]["items"]) >= 30


def test_search_words_find_functions_by_what_they_do():
    items = livecalc_help.functions_catalog()["items"]

    def find(q):
        words = q.lower().split()
        return {i["name"] for i in items if all(w in f"{i['name']} {i['signature']} {i['summary']} {i['keywords']} {i['category']}".lower() for w in words)}

    assert {"sin", "cos", "tan", "asin", "acos", "atan", "atan2"} <= find("angle")
    assert "sqrt" in find("square root") and "log10" in find("logarithm") and "to" in find("convert")


def plot(entries, functions, x=None, y=None):
    return livecalc.livecalc_plot(entries, functions, x, y)


def test_functions_of_one_value_become_curves_sharing_the_axis_and_split_by_unit():
    r = plot(["f(x) = 3*x^2 - 2", "g(x) = sin(x)*5", "F(t) = 0.5*9.81 m/s^2*t^2"], ["f", "g", "F"], ["-3", "3"])
    assert r["errors"] == [] and r["surfaces"] == []
    assert len(r["curves"]) == 2                                              # F has a unit, f and g do not
    plain = next(c for c in r["curves"] if not c["y_unit"])
    assert [s["name"] for s in plain["series"]] == ["f", "g"] and len(plain["x"]) == livecalc.PLOT_POINTS
    assert plain["x"][0] == -3 and plain["x"][-1] == 3
    assert plain["series"][0]["y"][0] == pytest.approx(3 * 9 - 2)
    assert plain["series"][1]["y"][-1] == pytest.approx(5 * math.sin(3), rel=1e-5)


def test_functions_of_two_values_become_surfaces_with_units_from_the_ranges():
    r = plot(["h(a, b) = a*b - a^2/4", "A(w, l) = w*l", "u(p, q) = p/q"], ["h", "A", "u"], ["1 m", "4 m"], ["1 m", "2 m"])
    assert r["curves"] == [] and r["errors"] == []
    assert len(r["surfaces"]) == 2                                            # h and A are areas and share a scene; u is dimensionless
    area = next(s for s in r["surfaces"] if s["z_unit"] == "m^2")
    assert [x["name"] for x in area["surfaces"]] == ["h", "A"]
    z = next(x["z"] for x in area["surfaces"] if x["name"] == "A")
    n = livecalc.GRID_3D
    assert len(z) == n and len(z[0]) == n
    assert area["x"][0] == 1 and area["x"][-1] == 4 and area["y"][-1] == 2 and area["x_unit"] == "m"
    assert z[-1][-1] == pytest.approx(8) and z[0][0] == pytest.approx(1) and area["zmax"] >= 8 - 1e-9 and area["zmin"] <= 1 + 1e-9
    ratio = next(s for s in r["surfaces"] if s["z_unit"] == "")
    assert ratio["surfaces"][0]["z"][0][0] == pytest.approx(1.0) and (ratio["x_var"], ratio["y_var"]) == ("p", "q")


def test_a_function_that_cannot_be_plotted_is_reported_and_does_not_stop_the_others():
    r = plot(["f(x) = x^2", "q(x) = sqrt(x)", "t(x, y, z) = x + y + z", "k(x) = x + undefined_thing"], ["f", "q", "t", "k", "missing"], ["-2", "2"])
    names = {e["name"]: e["message"] for e in r["errors"]}
    assert set(names) == {"q", "t", "k", "missing"}
    assert "not real" in names["q"] and "one value" in names["t"] and "undefined_thing" in names["k"] and "no longer defined" in names["missing"]
    assert [s["name"] for c in r["curves"] for s in c["series"]] == ["f"]


def test_bad_ranges_are_explained():
    for x, msg in ((["5", "1"], "smaller to a larger"), (["0 m", "3 s"], "same units"), (["", "3"], "start of the x range"), (["0 degC", "30 degC"], "K")):
        r = plot(["f(x) = x"], ["f"], x)
        assert r["curves"] == [] and msg in r["errors"][0]["message"], (x, r["errors"])


def test_functions_use_values_defined_earlier_and_the_last_definition_wins():
    r = plot(["k = 3", "f(x) = k*x", "f(x) = 2*k*x"], ["f"], ["0", "1"])
    assert r["curves"][0]["series"][0]["y"][-1] == pytest.approx(6)


def test_at_most_six_functions_and_the_api_wrapper():
    entries = [f"f{i}(x) = x + {i}" for i in range(8)]
    r = plot(entries, [f"f{i}" for i in range(8)])
    assert len(r["curves"][0]["series"]) == livecalc.MAX_PLOTTED
    res = api.handle("livecalc_plot", {"entries": ["f(x) = x"], "functions": ["f"], "x": ["0", "1"]})
    assert res["ok"] and res["result"]["curves"]
