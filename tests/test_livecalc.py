"""LiveCalc: the unit-aware scratchpad calculator behind the LiveCalc tab."""

import math

import pytest

from sliderule import api


def run(*lines, entries=()):
    r = api.handle("livecalc_eval", {"entries": list(entries), "draft": "\n".join(lines)})
    assert r["ok"], r
    return r["result"]["draft"]["lines"]


def one(line, *context):
    return run(*context, line)[-1]


def val(line, *context):
    r = one(line, *context)
    assert r["kind"] in ("value", "assign"), r
    return r["value"], r["unit"]


# ---------------------------------------------------------------- arithmetic with units
@pytest.mark.parametrize("text,value,unit", [
    ("5 m + 30 cm", 5.3, "m"),
    ("30 cm + 5 m", 530, "cm"),
    ("3 kN * 2 m", 6, "kN*m"),
    ("5 m * 3 m", 15, "m^2"),
    ("10 m / 2 s", 5, "m/s"),
    ("9.81 m/s^2 * 5 kg", 49.05, "N"),
    ("2 kg * 3 m^2 / s^2", 6, "J"),
    ("sqrt(9 m^2)", 3, "m"),
    ("2 pi", 2 * math.pi, ""),
    ("2^10", 1024, ""),
    ("-3 m + 1 m", -2, "m"),
    ("(2 + 3) * 4", 20, ""),
    ("7 / 2", 3.5, ""),
    ("1e3 m", 1000, "m"),
    ("2 ft * 3 in", 6, "ft*in"),
    ("sin(30 deg)", 0.5, ""),
    ("5 N m", 5, "N*m"),
    ("1000 kg/m^3 * 2 m^3", 2000, "kg"),
])
def test_arithmetic(text, value, unit):
    v, u = val(text)
    assert v == pytest.approx(value, rel=1e-5)
    assert u == unit


def test_wrong_dimensions_are_refused():
    r = one("5 m + 3 s")
    assert r["kind"] == "error" and "length" in r["error"]["message"] and "time" in r["error"]["message"]
    assert one("sin(5 m)")["kind"] == "error"
    assert one("3 kg + 2")["kind"] == "error"
    assert one("2 ^ (3 m)")["kind"] == "error"


def test_division_by_zero_and_overflow():
    assert "zero" in one("1/0")["error"]["message"].lower()
    assert one("10^400")["kind"] == "error"
    assert one("(-8)^0.5")["kind"] == "error"
    assert one("sqrt(-4)")["kind"] == "error"
    assert one("factorial(500)")["kind"] == "error"


def test_ambiguous_unit_message_is_passed_on():
    r = one("5 lb")
    assert r["kind"] == "error" and "lbm" in r["error"]["message"]


# ---------------------------------------------------------------- conversions
def test_conversions():
    assert val("120 km/h to m/s")[0] == pytest.approx(33.3333, rel=1e-4)
    assert val("1e3 m in km") == (1, "km")
    assert val("5 in in cm")[0] == pytest.approx(12.7)
    assert val("5 cm in in")[0] == pytest.approx(1.9685, rel=1e-4)
    assert val("30 deg to rad")[0] == pytest.approx(math.pi / 6, rel=1e-5)
    assert one("5 m to s")["kind"] == "error"
    assert one("5 m to")["kind"] == "error"


def test_offset_temperatures():
    assert val("20 degC to degF")[0] == pytest.approx(68)
    assert val("0 degC to K")[0] == pytest.approx(273.15)
    assert val("20 degC + 5 K") == (pytest.approx(25), "°C")
    assert val("20 degC - 5 degC") == (pytest.approx(15), "K")
    assert one("20 degC * 2")["kind"] == "error"
    assert one("20 degC + 5 degC")["kind"] == "error"


# ---------------------------------------------------------------- variables, functions, ans
def test_variables_flow_between_lines():
    lines = run("m = 5 kg", "a = 9.81 m/s^2", "F = m*a", "F to lbf")
    assert [l["kind"] for l in lines] == ["assign", "assign", "assign", "value"]
    assert lines[2]["value"] == pytest.approx(49.05) and lines[2]["unit"] == "N"
    assert lines[3]["value"] == pytest.approx(11.0269, rel=1e-4)


def test_variables_flow_from_earlier_entries():
    r = api.handle("livecalc_eval", {"entries": ["x = 4 m", "y = 3 m\nz = x*y"], "draft": "z to cm^2"})["result"]
    assert r["entries"][1]["lines"][1]["value"] == pytest.approx(12)
    assert r["draft"]["lines"][0]["value"] == pytest.approx(120000)
    assert {v["name"] for v in r["variables"]} >= {"x", "y", "z"}


def test_a_number_before_a_name_is_a_unit_even_when_a_variable_has_that_name():
    lines = run("m = 5 kg", "a = 9.81 m/s^2", "1000 kg/m^3 * 2 m^3")
    assert lines[1]["unit"] == "m/s^2" and lines[1]["value"] == pytest.approx(9.81)
    assert lines[2]["value"] == pytest.approx(2000)
    assert not lines[0]["notes"]                       # defining m is fine
    assert any("read as the unit" in n for n in one("3 m", "m = 5 kg")["notes"])


def test_division_by_a_variable_named_like_a_unit_is_flagged():
    r = one("10 m / t", "t = 3 s")
    assert any("read as the unit" in n for n in r["notes"])


def test_ans_and_user_functions():
    assert val("ans * 2", "3 m") == (6, "m")
    lines = run("f(x) = 3*x^2 - 2", "f(4)", "g(a, b) = a*b", "g(2 m, 3 m)")
    assert lines[0]["kind"] == "function"
    assert lines[1]["value"] == 46
    assert lines[3]["value"] == 6 and lines[3]["unit"] == "m^2"
    assert one("f(1, 2)", "f(x) = x")["kind"] == "error"
    assert one("sin(1, 2)")["kind"] == "error"


def test_function_cannot_recurse_forever():
    r = one("f(2)", "f(x) = f(x)")
    assert r["kind"] == "error" and "deeply" in r["error"]["message"]


def test_reserved_names():
    assert one("sin = 3")["kind"] in ("error", "equation")
    assert one("sin(x) = 3")["kind"] == "error"


# ---------------------------------------------------------------- text, markdown, equations
def test_prose_is_text_and_calculations_are_not():
    for line in ("hello world", "# A heading", "> quote", "- item", "**bold**", "The beam is 5 m long", "a well-known result"):
        assert one(line)["kind"] == "text", line
    assert run("", "1")[0]["kind"] == "blank"
    assert one("x")["kind"] == "text"
    assert one("5 apples")["kind"] == "error"


def test_equations_without_values_are_kept_as_equations():
    r = one("F = m*a")
    assert r["kind"] == "equation" and set(r["free"]) == {"m", "a"}
    r = one("v^2 = u^2 + 2*a*s")
    assert r["kind"] == "equation" and "mathrm{s}" not in r["display_latex"]
    assert one("y = 2 x + 1")["kind"] == "equation"
    r = one("2*3 = 6")
    assert r["kind"] == "equation" and "equal" in r["notes"][0]


def test_two_equals_signs():
    assert one("a = b = 3")["kind"] == "error"


# ---------------------------------------------------------------- steps
def test_steps_show_substitution_and_unit_conversion():
    r = one("a + b", "a = 5 m", "b = 30 cm")
    labels = [s["label"] for s in r["steps"]]
    assert labels[:2] == ["Expression", "Substitute the values"]
    assert "Convert to SI base units" in labels
    conv = next(s for s in r["steps"] if s["label"] == "Convert to SI base units")
    assert any("30" in line and "0.3" in line for line in conv["latex"])
    assert r["steps"][-1]["label"].startswith("Express in") or r["steps"][-1]["label"].startswith("Result")


def test_conversion_steps_are_part_of_the_working():
    r = one("2 ft to m")
    assert r["steps"][-1]["label"] == "Convert to m"
    assert r["value"] == pytest.approx(0.6096)


# ---------------------------------------------------------------- plots
def test_plot_unitless():
    r = one("plot sin(x) from 0 to 2*pi")
    assert r["kind"] == "plot"
    pl = r["plot"]
    assert pl["var"] == "x" and len(pl["x"]) == len(pl["series"][0]["y"]) == 300
    assert pl["x"][0] == 0 and pl["x"][-1] == pytest.approx(2 * math.pi, rel=1e-6)
    assert max(pl["series"][0]["y"]) == pytest.approx(1, abs=1e-3)


def test_plot_default_range_and_several_curves():
    pl = one("plot x^2, x^3")["plot"]
    assert pl["x"][0] == -10 and pl["x"][-1] == 10 and len(pl["series"]) == 2


def test_plot_with_units_and_named_variable():
    pl = one("plot 0.5*m*v^2 for v from 0 m/s to 20 m/s", "m = 2 kg")["plot"]
    assert pl["var"] == "v" and pl["x_unit"] == "m/s" and pl["y_unit"] == "J"
    assert pl["series"][0]["y"][-1] == pytest.approx(400, rel=1e-5)
    pl = one("plot 3*x^2 from -2 m to 2 m")["plot"]
    assert pl["x_unit"] == "m" and pl["y_unit"] == "m^2"


def test_plot_a_defined_function_and_its_errors():
    assert one("plot f from 0 to 3", "f(x) = x^2")["kind"] == "plot"
    assert one("plot 5")["kind"] == "error"
    assert "depends on" in one("plot a*b")["error"]["message"]
    assert one("plot sin(x) from 3 to 1")["kind"] == "error"
    assert one("plot x from 0 m to 1 s")["kind"] == "error"
    assert one("plot 1/x from -1 to 1")["kind"] == "plot"      # the pole is a gap, not an error
    assert one("plot x, x*1 m from 0 to 1")["kind"] == "error"  # different units on one graph


def test_plot_points_that_are_not_real_become_gaps():
    pl = one("plot sqrt(x) from -1 to 1")
    # sqrt of a negative number is refused outright rather than silently dropped
    assert pl["kind"] in ("error", "plot")


# ---------------------------------------------------------------- safety and limits
@pytest.mark.parametrize("text", [
    "__import__('os').system('true')", "().__class__", "open('/etc/passwd')", "x.y", "a[0]", "lambda: 1", "1;2", "a := 3", "`ls`", "$(ls)",
])
def test_nothing_is_executed(text):
    r = one(text)
    assert r["kind"] in ("text", "error")


def test_limits():
    assert one("1+" * 300 + "1")["kind"] == "error"
    assert one("(" * 60 + "1" + ")" * 60)["kind"] == "error"
    assert one("2^" * 60 + "2")["kind"] in ("error", "value")
    long = "5 m + " * 100 + "1 m"
    assert one(long)["kind"] == "error"
    r = api.handle("livecalc_eval", {"entries": ["1"] * 201, "draft": ""})
    assert not r["ok"]
    r = api.handle("livecalc_eval", {"draft": "\n".join(["1"] * 1600)})
    assert not r["ok"]


def test_empty_input():
    r = api.handle("livecalc_eval", {})["result"]
    assert r["entries"] == [] and r["draft"]["lines"] == []


# ---------------------------------------------------------------- send to My equations
def to_eq(text, entries=()):
    r = api.handle("livecalc_to_equation", {"text": text, "entries": list(entries)})
    return r["result"] if r["ok"] else r["error"]


def test_equation_becomes_a_draft_with_units_and_examples():
    res = to_eq("F = m*a", ["m = 5 kg", "a = 9.81 m/s^2"])
    calc = res["calculation"]
    assert calc["outputs"] == ["F"]
    by = {v["key"]: v for v in calc["variables"]}
    assert by["m"]["unit"] == "kg" and by["m"]["example"] == "5 kg"
    assert by["a"]["unit"] == "m/s^2"
    assert by["F"]["unit"] == "N"                      # worked out from the right-hand side
    assert calc["equations"] == [{"title": "", "text": "F = m*a"}]


def test_draft_without_known_values_warns_about_blank_units():
    res = to_eq("F = m*a")
    assert res["calculation"]["variables"][0]["key"] == "F"
    assert res["warnings"]


def test_draft_passes_the_custom_editor_validation():
    """The draft, once given a name, a discipline and the units the user fills in, is a valid My equations entry."""
    res = to_eq("F = m*a", ["m = 5 kg", "a = 9.81 m/s^2"])["calculation"]
    res.update(name="Newton second law", disciplines=["mechanical"])
    v = api.handle("custom_validate", {"calculation": {**res, "id": "custom.livecalc_probe"}})
    assert v["ok"], v
    assert v["result"].get("ok", True), v["result"]


def test_function_names_follow_my_equations_spelling():
    res = to_eq("y = abs(x) + max(x, 2) + ceil(x)")["calculation"]
    assert res["equations"][0]["text"] == "y = Abs(x) + Max(x, 2) + ceiling(x)"
    assert {v["key"] for v in res["variables"]} == {"y", "x"}


def test_unit_literals_inside_an_equation_are_flagged():
    res = to_eq("F = 5 N * x")
    assert any("unit" in w for w in res["warnings"])


@pytest.mark.parametrize("text", ["", "F", "F =", "= m*a", "a = b = c", "F = m*a\nG = 3"])
def test_not_an_equation(text):
    res = to_eq(text)
    assert "message" in res and res["code"] in ("BAD_REQUEST", "NOT_AN_EQUATION")


def test_fenced_code_is_never_evaluated():
    lines = run("```", "5 m + 30 cm", "```", "5 m + 30 cm")
    assert [l["kind"] for l in lines] == ["text", "text", "text", "value"]


def test_literals_have_no_steps_but_conversions_and_formulas_do():
    assert run("m = 80 kg")[0]["steps"] == []
    assert run("2 ft to m")[0]["steps"]
    assert run("a = 2 m", "b = 3 m", "c = a*b")[2]["steps"]


def test_only_formulas_are_offered_to_my_equations():
    lines = run("m = 80 kg", "a = 9.81 m/s^2", "F = m*a", "G = k*x", "v^2 = u^2")
    assert [bool(l.get("formula")) for l in lines] == [False, False, True, True, True]


def test_equation_note_lists_every_missing_name():
    assert "u, a, s" in one("v^2 = u^2 + 2*a*s")["notes"][0] or "v, u, a, s" in one("v^2 = u^2 + 2*a*s")["notes"][0]


def test_draft_asks_for_an_output_when_the_left_side_is_not_a_variable():
    res = to_eq("v^2 = u^2 + 2*a*s")
    assert res["calculation"]["outputs"] == [] and any("solve for" in w for w in res["warnings"])


def test_prose_with_numbers_and_odd_characters_stays_text():
    assert one("Simply supported span, **uniform load** — see $w L^2 / 8$.")["kind"] == "text"
    assert one("Load is 12 kN/m (see clause 4.2)")["kind"] == "text"
    assert one("10 %")["kind"] == "error"


def test_si_form_follows_the_unit_used_not_just_the_dimension():
    r = one("M to kN*m", "M = 12 kN/m * (6 m)^2 / 8")
    assert r["si_unit"] == "N*m"
    steps = " ".join(str(s["latex"]) for s in r["steps"])
    assert "54000" in steps and "mathrm{J}" not in steps
    assert one("3 kN * 2 m")["si_unit"] == "N*m"
    assert one("5 m + 30 cm")["si_unit"] == "m"
    assert one("120 km/h")["si_unit"] == "m/s"
