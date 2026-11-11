"""LiveCalc worked steps for lines that do their own work (calc(...), calculus functions, your own functions): they must show the working, not the call."""

import math
import re

import pytest

from sliderule import api, livecalc

TURBINE = 'calc("turbine_power", "Pe", rho = 1.225 kg/m^3, Dr = 100 m, v = 10 m/s, Cp = 0.4, eg = 0.95)'
GEAR = 'calc("mechanical.design.gear_tooth_bending", "sb", P = 11 kW, n = 1450 rpm, Nt = 24, m = 4 mm, Fw = 40 mm, Y = 0.337, Sa = 200 MPa) to MPa'
CALLS = re.compile(r"\\mathrm\{(calc|integrate|derivative|findroot|sumover)\}")


def run(*entries, angle="rad"):
    out = []
    for e in livecalc.livecalc_eval(entries=list(entries), angle=angle)["entries"]:
        out += e["lines"]
    return out


def last(*entries, **kw):
    return run(*entries, **kw)[-1]


def lines_of(step):
    return step["latex"] if isinstance(step["latex"], list) else [step["latex"]]


def text_of(line):
    return "\n".join(f"{s['label']}\n" + "\n".join(lines_of(s)) for s in line["steps"])


def labels(line):
    return [s["label"] for s in line["steps"]]


def test_a_library_call_shows_the_calculations_own_working_and_the_same_value():
    ln = last(GEAR)
    assert ln["kind"] == "value" and ln["value"] == pytest.approx(61.4337, rel=1e-5) and ln["unit"] == "MPa"
    lab = labels(ln)
    assert lab[0] == "Expression" and "Library calculation" in lab and "Calculate Pitch diameter" in lab and "Calculate Bending stress" in lab
    body = text_of(ln)
    assert r"d = \left(24\right) \cdot \left(0.004\,\mathrm{m}\right)" in body        # the numbers are put in, with units
    assert r"\sigma = 6.1434\times10^{7}\,\mathrm{Pa}" in body and r"\left[\sigma\right]" in body
    assert "In symbols, in the given quantities" in lab and lab[-1].startswith("Convert to MPa")
    # the call is shown once, as the line the user typed, and nowhere else
    assert [i for i, s in enumerate(ln["steps"]) if CALLS.search("".join(lines_of(s)))] == [0]
    # same number as solving the library calculation directly
    direct = api.solve("mechanical.design.gear_tooth_bending", {"P": "11 kW", "n": "1450 rpm", "Nt": "24", "m": "4 mm", "Fw": "40 mm", "Y": "0.337", "Sa": "200 MPa"},
                       solve_for=["sb"], output_units={"sb": "MPa"})
    assert next(o for o in direct["outputs"] if o["key"] == "sb")["value"] == pytest.approx(ln["value"], rel=1e-5)


def test_a_library_call_inside_an_expression_is_worked_through_and_substituted():
    ln = last(f"2 * {TURBINE} + 100 kW")
    assert ln["value"] == pytest.approx(2 * 1828.0132 + 100, rel=1e-4)
    lab = labels(ln)
    assert "With the library results in place of the calls" in lab and "Substitute the values" in lab and "Calculate Electrical power" in lab
    sub = lines_of(next(s for s in ln["steps"] if s["label"] == "Substitute the values"))[0]
    assert r"2 \cdot 1828.01\,\mathrm{kW} + 100\,\mathrm{kW}" in sub                 # a product of a number and a value is not run together
    assert not CALLS.search(text_of(ln).split("With the library results")[1])


def test_two_library_calls_in_one_line_are_numbered():
    ln = last(f"{TURBINE} + " + TURBINE.replace("Dr = 100 m", "Dr = 80 m"))
    lab = labels(ln)
    assert any(x.startswith("calc1: ") for x in lab) and any(x.startswith("calc2: ") for x in lab)
    assert ln["value"] == pytest.approx(1828.0132 + 1169.9285, rel=1e-4)


def test_a_library_call_over_a_list_keeps_the_plain_steps():
    ln = last(TURBINE.replace("Dr = 100 m", "Dr = [80, 100] m"))
    assert labels(ln) == ["Expression", "Result"] and ln["kind"] == "value"


def test_your_own_function_shows_definition_arguments_and_the_body_with_values():
    ln = last("f(x) = 3*x^2 - 2", "f(4)")
    assert ln["value"] == 46
    assert labels(ln) == ["Expression", "Definition of f", "Arguments", "Substitute the values", "Result"]
    assert lines_of(ln["steps"][1]) == [r"f\left(x\right) = 3 \cdot x^{2} - 2"] and lines_of(ln["steps"][3]) == [r"3 \cdot \left(4\right)^{2} - 2"]


def test_your_own_function_with_units_and_a_conversion():
    ln = last("v(t) = 3 m/s^2 * t", "v(2 min) to km/h")
    assert ln["value"] == pytest.approx(3 * 120 * 3.6) and ln["unit"] == "km/h"
    lab = labels(ln)
    assert lab[:3] == ["Expression", "Definition of v", "Arguments"] and any(x.startswith("Convert to km/h") for x in lab)


def test_a_function_that_calls_the_library_is_opened_up_too():
    ln = last('p(D) = ' + TURBINE.replace("Dr = 100 m", "Dr = D"), "p(100 m)")
    assert ln["value"] == pytest.approx(1828.0132, rel=1e-4)
    assert "Definition of p" in labels(ln) and "Library calculation" in labels(ln) and "Calculate Swept area" in labels(ln)


def test_integral_of_a_plain_formula_is_done_by_hand_and_agrees():
    ln = last("f(x) = 3*x^2 - 2", "integrate(f, 0, 2)")
    assert ln["value"] == pytest.approx(4.0)
    assert labels(ln) == ["Expression", "The function", "What is asked", "Antiderivative", "Evaluate between the limits", "Result"]
    assert "x^{3} - 2 x" in text_of(ln) and r"F\left(2\right) - F\left(0\right)" in text_of(ln)


def test_derivative_of_a_plain_formula_is_done_by_hand_and_agrees():
    ln = last("f(x) = 3*x^2 - 2", "derivative(f, 2)")
    assert ln["value"] == pytest.approx(12.0)
    assert labels(ln)[3:5] == ["Differentiate", "Evaluate"] and r"f'\left(x\right) = 6 x" in text_of(ln)


def test_symbolic_path_handles_special_functions_and_other_variables_and_checks_itself():
    ln = last("c = 2", "f(x) = c*exp(-x) + sin(x)", "integrate(f, 0, pi)")
    assert ln["value"] == pytest.approx(2 * (1 - math.exp(-math.pi)) + 2)
    assert "Antiderivative" in labels(ln)
    ln = last("f(x) = x^3", "derivative(f, 2)")
    assert "Differentiate" in labels(ln) and ln["value"] == pytest.approx(12.0, rel=1e-6)


def test_functions_with_units_or_in_degrees_show_the_numerical_method_instead_of_a_wrong_symbolic_answer():
    ln = last("g(t) = 3 m/s^2 * t", "integrate(g, 0 s, 10 s)")
    assert ln["value"] == pytest.approx(150.0) and "Antiderivative" not in labels(ln)
    assert "carries units" in text_of(ln) and "Gauss–Kronrod" in text_of(ln) and r"= 150\,\mathrm{m}" in text_of(ln)
    ln = last("s(x) = sin(x)", "derivative(s, 0)", angle="deg")
    assert "Differentiate" not in labels(ln) and "Method: five-point central difference" in labels(ln)


def test_derivative_numerical_working_uses_its_own_values():
    ln = last("g(t) = 3 m/s^2 * t", "derivative(g, 5 s)")
    body = text_of(ln)
    h = 5e-4
    for k, v in [("- 2h", 3 * (5 - 2 * h)), ("- h", 3 * (5 - h)), ("+ h", 3 * (5 + h)), ("+ 2h", 3 * (5 + 2 * h))]:
        assert rf"g\left(t_0 {k}\right) = {v:.8g}" in body or rf"g\left(t_0 {k}\right) = {v:.6g}" in body
    assert ln["value"] == pytest.approx(3.0) and ln["unit"] == "m/s^2"


def test_findroot_shows_the_bracket_the_method_and_a_check():
    ln = last("g(x) = cos(x) - x", "findroot(g, 0, 1)")                              # no exact root: the method and its numbers
    body_ = text_of(ln)
    assert ln["value"] == pytest.approx(0.7390851332) and "The root is bracketed" in labels(ln) and "Method: Brent's method" in labels(ln)
    assert r"g\left(0\right) = 1" in body_ and "iterations" in body_ and "at the root" in body_


def test_sumover_lists_the_terms_and_the_total():
    ln = last("k(n) = 1/n^2", "sumover(k, 1, 4)")
    body = text_of(ln)
    assert ln["value"] == pytest.approx(1 + 1 / 4 + 1 / 9 + 1 / 16) and "The 4 terms" in labels(ln)
    assert r"k\left(2\right) = 0.25" in body and r"k\left(4\right) = 0.0625" in body
    long = last("k(n) = 1/n^2", "sumover(k, 1, 100)")
    assert r"\cdots" in text_of(long) and r"k\left(100\right) = 1\times10^{-4}" in text_of(long) and "The 100 terms" in labels(long)


def test_no_worked_step_outside_the_expression_names_the_function_it_opened():
    for entries in (["f(x) = 3*x^2 - 2", "integrate(f, 0, 2)"], ["f(x) = 3*x^2 - 2", "derivative(f, 2)"], ["h(x) = x^2 - 2", "findroot(h, 0, 2)"],
                    ["k(n) = 1/n^2", "sumover(k, 1, 4)"], [GEAR], [f"2 * {TURBINE} + 100 kW"]):
        ln = last(*entries)
        for s in ln["steps"][1:]:
            assert not CALLS.search("".join(lines_of(s))), (entries, s["label"])


def test_unit_in_front_of_a_value_product_is_not_run_together_in_plain_steps_either():
    ln = last("x = 3 m", "2 * x")
    assert lines_of(next(s for s in ln["steps"] if s["label"] == "Substitute the values")) == [r"2 \cdot 3\,\mathrm{m}"]


def test_a_line_whose_working_cannot_be_built_still_gives_its_result(monkeypatch):
    from sliderule import livecalc_work

    monkeypatch.setattr(livecalc_work, "_library_block", lambda *a, **k: (_ for _ in ()).throw(KeyError("boom")))
    ln = last(TURBINE)
    assert ln["kind"] == "value" and ln["value"] == pytest.approx(1828.0132, rel=1e-4) and labels(ln) == ["Expression", "Result"]


def test_markdown_export_can_include_the_worked_steps():
    entries = ["f(x) = 3*x^2 - 2\nintegrate(f, 0, 2)", "mean(2 m, 4 m, 9 m)", "just a note", GEAR]
    plain = livecalc.livecalc_export(entries=entries, fmt="markdown")["content"]
    full = livecalc.livecalc_export(entries=entries, fmt="markdown", steps=True)["content"]
    assert "**Working**" not in plain and "Antiderivative" not in plain
    assert full.count("**Working**") == 3 and full.startswith(plain.split("$$")[0])           # the function definition and the note have no working
    assert "1. *Expression*" in full and "*Antiderivative*" in full and "   $$ F\\left(x\\right) = \\int 3 x^{2} - 2\\,dx = x^{3} - 2 x $$" in full
    assert "*Calculate Bending stress*" in full and "*Add the values*" in full and "just a note" in full
    assert full.index("*Antiderivative*") < full.index("$$ \\mathrm{mean}") < full.index("*Add the values*") < full.index("just a note")
    for fmt in ("text", "python", "notebook"):                                               # the other formats do not change
        assert livecalc.livecalc_export(entries=entries, fmt=fmt, steps=True) == livecalc.livecalc_export(entries=entries, fmt=fmt)
