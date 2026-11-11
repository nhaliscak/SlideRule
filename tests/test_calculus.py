import contextlib
import io
import math
import sys
import time

import pytest
import sympy

from sliderule import api, design_export, usercalcs
from sliderule import settings
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import CustomError, calc_from_dict, calc_to_dict
from sliderule.core.safeparse import UnsafeExpression, bound_names, check_expression

NS = {"F0": 0, "L": 1, "d": 1, "t": 1, "diff": len, "integrate": len, "exp": len}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def make(eqs, variables, outputs, **kw):
    return Calculation(id="custom.t", name="t", disciplines=["mechanical"], description="", variables=variables,
                       equations=eqs, outputs=outputs, custom=True, **kw)


def value(calc_id, inputs=None, solve_for=None):
    c = api.get_calculation(calc_id)
    r = api.solve(calc_id, inputs or {k: v for k, v in c["example"].items()}, solve_for)
    assert not [d for d in r["diagnostics"] if d["level"] != "info"], r["diagnostics"]
    return {o["key"]: o["si_value"] for o in r["outputs"]}


# ---------------------------------------------------------------- library calculations agree with hand calculations

def test_library_calculations_with_calculus_match_hand_results():
    assert value("mechanical.work_energy.variable_force_work")["W"] == pytest.approx(100 * (1 - 1 / 4))
    assert value("chemical.fluids.laminar_pipe_flow_rate_from_profile")["Q"] == pytest.approx(math.pi * 0.025**2 * 0.4 / 2)
    assert value("mechanical.thermo.heat_with_linear_specific_heat")["Q"] == pytest.approx(2 * (380 * 200 + 0.2 / 2 * (500**2 - 300**2)))
    assert value("electrical.circuits.rc_charging_current_from_voltage")["i"] == pytest.approx(12 / 2000 * math.exp(-0.3 / (2000 * 100e-6)))
    out = value("mechanical.kinematics.constant_jerk_velocity_acceleration")
    assert out["v"] == pytest.approx(5 + 2 * 4 + 0.5 * 16 / 2) and out["ac"] == pytest.approx(2 + 0.5 * 4)


def test_calculus_equations_can_be_solved_for_other_variables():
    cid = "mechanical.work_energy.variable_force_work"
    assert value(cid, {"W": "75 J", "F0": "100 N", "L": "2 m"}, ["d"])["d"] == pytest.approx(1.0)
    assert value(cid, {"W": "75 J", "d": "1 m", "L": "2 m"}, ["F0"])["F0"] == pytest.approx(100.0)
    assert value("electrical.circuits.rc_charging_current_from_voltage", {"i": "1.3388 mA", "C": "100 uF", "V": "12 V", "R": "2 kohm"}, ["t"])["t"] == pytest.approx(0.3, rel=1e-3)


def test_steps_and_detail_show_the_equation_as_written_then_evaluated():
    cid = "mechanical.work_energy.variable_force_work"
    eq = api.get_calculation(cid)["equations"][0]
    assert r"\int" in eq["latex"] and r"\int" not in eq["evaluated"] and eq["text"].startswith("W = integrate(")
    sol = api.solve(cid, {"F0": "100 N", "L": "2 m", "d": "1 m"})
    lines = [ln for st in sol["steps"]["symbolic"] for ln in st["lines"]]
    notes = [ln["note"] for ln in lines]
    assert "governing equation, as written" in notes and "derivatives and integrals evaluated symbolically" in notes
    assert any(r"\int" in ln["latex"] for ln in lines)
    assert not any(r"\int" in ln["latex"] for st in sol["steps"]["numeric"] for ln in st["lines"] if ln["note"] == "substitute SI values with units")


# ---------------------------------------------------------------- what the parser accepts and refuses

@pytest.mark.parametrize("text", [
    "integrate(F0*(1 - x/L), (x, 0, d))", "diff(F0*t**2, t)", "diff(F0*t**3, t, 2)", "integrate(integrate(x*y, (x, 0, d)), (y, 0, L))",
    "integrate(exp(-x/L), (x, 0, d))",
])
def test_calculus_syntax_accepted(text):
    check_expression(text, NS)


@pytest.mark.parametrize("text", [
    "integrate(F0*x, x)", "integrate(F0*x, (x, 0))", "integrate(F0*x, (x, 0, x))", "integrate(F0)", "diff(F0*t)", "diff(F0*t, y)", "diff(F0*t, exp)",
    "diff(F0*t, t, 9)", "diff(F0*t, t, exp)", "integrate(F0*x, (x, 0, d, 1))", "integrate(F0*x, (1, 0, d))",
    "diff(diff(diff(diff(diff(F0*t, t), t), t), t), t)", "integrate(F0*x, (x, 0, __import__('os')))", "diff(F0*t, t.real)",
])
def test_calculus_syntax_refused(text):
    with pytest.raises(UnsafeExpression):
        check_expression(text, NS)


def test_bound_names_are_found():
    assert bound_names("integrate(integrate(x*y, (x, 0, d)), (y, 0, L)) + diff(F0*t, t)") == {"x", "y", "t"}


def test_integration_variable_needs_no_declaration_but_everything_else_does():
    ok = make(["W = integrate(F0*(1 - x/L), (x, 0, d))"], [V("W", "W", "J"), V("F0", "F", "N"), V("L", "L", "m"), V("d", "d", "m")], ["W"])
    assert "x" not in {str(s) for s in ok.parsed[0].symbols}          # the dummy disappears with the definite limits
    with pytest.raises(Exception, match="unknown name 'q'"):
        make(["W = integrate(F0*q, (x, 0, d))"], [V("W", "W", "J"), V("F0", "F", "N"), V("d", "d", "m")], ["W"])


def test_dimension_errors_are_caught_in_the_equation_as_written():
    v = [V("W", "W", "J"), V("F0", "F", "N"), V("L", "L", "m"), V("d", "d", "m"), V("A", "A", "m^2")]
    for eq, msg in [("W = integrate(F0*(1 + x), (x, 0, d))", "different dimensions"),             # 1 + length inside the integrand
                    ("W = F0*diff(d + L**2, d)", "different dimensions"),                       # hidden by evaluation: d/dd (d + L^2) = 1
                    ("W = integrate(F0, (x, 0, A))", "not dimensionally homogeneous"),           # limits are an area, so W would be N·m²
                    ("W = integrate(F0, (x, 0, d)) + F0", "different dimensions")]:
        with pytest.raises(Exception, match=msg):
            make([eq], v, ["W"])


def test_derivative_of_something_that_does_not_depend_on_the_variable_is_an_error():
    with pytest.raises(Exception, match="does not depend on d"):
        make(["W = diff(F0, d)*d*L"], [V("W", "W", "N*m"), V("F0", "F", "N"), V("d", "d", "m"), V("L", "L", "m")], ["W"])


def test_undefined_integrals_are_reported():
    with pytest.raises(Exception, match="undefined or infinite"):
        make(["Q = integrate(1/x, (x, 0, d))"], [V("Q", "Q", "1"), V("d", "d", "1")], ["Q"])


def test_integrals_without_a_closed_form_are_integrated_numerically():
    c = make(["Q = a + integrate(x**x, (x, 0, d))"], [V("Q", "Q", "1"), V("d", "d", "1"), V("a", "a", "1")], ["Q"])
    assert c.parsed[0].numeric_integral
    q = solve(c, {"d": "1", "a": "2"}).to_dict()
    assert q["outputs"][0]["si_value"] == pytest.approx(2.7834305107121344, rel=1e-12)
    assert solve(c, {"Q": "2.5", "d": "1"}, ["a"]).to_dict()["outputs"][0]["si_value"] == pytest.approx(1.7165694892878656, rel=1e-12)   # solving for a quantity outside the integral works
    inside = solve(c, {"Q": "2.5", "a": "1"}, ["d"]).to_dict()               # for one inside it (here the upper limit) the value is found by numerical root-finding
    assert inside["ok"] and inside["outputs"][0]["si_value"] == pytest.approx(1.52129049131746, rel=1e-8) and "NUMERIC_INVERSION" in [d["code"] for d in inside["diagnostics"]]
    notes = [ln.note for st in solve(c, {"d": "1", "a": "2"}).steps["numeric"] for ln in st.lines]
    assert "integral evaluated numerically (adaptive quadrature), in SI" in notes


def test_slow_integrals_are_cut_off_and_tracing_is_restored(monkeypatch):
    def slow(self, **kw):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            math.sqrt(2.0)
    monkeypatch.setattr(sympy.Integral, "doit", slow)      # stands in for an integrand SymPy chews on for a long time
    settings.update(timeout_seconds=1.0)
    before = sys.getprofile()
    with pytest.raises(Exception, match="took longer than"):
        make(["Q = integrate(exp(-x**2)*sin(x)/(1 + x**4), (x, 0, d))"], [V("Q", "Q", "1"), V("d", "d", "1")], ["Q"])
    assert sys.getprofile() is before


def test_calculus_is_not_allowed_in_validity_checks():
    with pytest.raises(Exception, match="validity checks cannot contain"):
        make(["W = F0*d"], [V("W", "W", "J"), V("F0", "F", "N"), V("d", "d", "m")], ["W"], validity=[("diff(F0*d, d) > 0", "no")])


# ---------------------------------------------------------------- user equations, files, System Design, exports

def test_user_equation_with_calculus_round_trips_through_the_file_format():
    doc = {"id": "custom.rc", "name": "RC current", "disciplines": ["electrical"],
           "variables": [{"key": "i", "label": "Current", "unit": "A"}, {"key": "C", "label": "Capacitance", "unit": "F", "example": "100 uF"},
                         {"key": "V", "label": "Voltage", "unit": "V", "example": "12 V"}, {"key": "R", "label": "Resistance", "unit": "ohm", "example": "2 kohm"},
                         {"key": "t", "label": "Time", "unit": "s", "example": "0.3 s"}],
           "equations": [{"text": "i = C*diff(V*(1 - exp(-t/(R*C))), t)"}], "outputs": ["i"]}
    c = calc_from_dict(doc)
    assert calc_to_dict(c)["equations"][0]["text"] == "i = C*diff(V*(1 - exp(-t/(R*C))), t)"
    saved = api.custom_save(doc)
    assert api.get_calculation(saved["id"])["equations"][0]["evaluated"]
    again = api.custom_validate(doc)
    assert again["ok"] and again["equations"][0]["evaluated"] and again["example_result"]["outputs"][0]["text"].startswith("0.0013388")


def test_calculus_from_a_shared_file_is_still_checked_for_safety():
    bad = {"id": "custom.evil", "name": "x", "disciplines": ["mechanical"],
           "variables": [{"key": "W", "label": "W", "unit": "J"}, {"key": "d", "label": "d", "unit": "m"}, {"key": "F0", "label": "F", "unit": "N"}],
           "equations": [{"text": "W = integrate(F0, (x, 0, d)) + __import__('os').getcwd()"}], "outputs": ["W"]}
    with pytest.raises(CustomError):
        calc_from_dict(bad)


def test_calculus_blocks_work_in_system_design_and_all_exports():
    g = {"version": 1, "blocks": [
        {"id": "w", "calc": "mechanical.work_energy.variable_force_work", "x": 0, "y": 0, "values": {"F0": "100 N", "L": "2 m", "d": "1 m"}}], "wires": []}
    for fmt in ("latex", "markdown", "html"):
        out = design_export.export_system(g, fmt)
        assert out["ok"], fmt
    tex = design_export.export_system(g, "latex")["content"]
    assert "as written" in tex and r"\int" in tex
    py = design_export.export_system(g, "python")["content"]
    assert "(written: W = integrate(" in py
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(py, "s.py", "exec"), {"__name__": "__main__"})
    assert "matches the SlideRule reference values" in buf.getvalue()


def test_nested_integrals_and_units():
    c = make(["A = integrate(integrate(1, (x, 0, a)), (y, 0, b))"], [V("A", "A", "m^2"), V("a", "a", "m"), V("b", "b", "m")], ["A"])
    assert solve(c, {"a": "3 m", "b": "200 cm"}).to_dict()["outputs"][0]["si_value"] == pytest.approx(6.0)
