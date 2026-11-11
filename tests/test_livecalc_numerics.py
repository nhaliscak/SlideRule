"""LiveCalc: physical constants, statistics, and calculus on functions you define."""

import math

import pytest

from sliderule.livecalc import QCONSTANTS, Session, livecalc_eval, livecalc_to_equation


def run(*lines):
    s = Session(8)
    out = [s.run_line(ln, i + 1) for i, ln in enumerate(lines)]
    return out[-1]


def val(*lines):
    r = run(*lines)
    assert r["kind"] in ("value", "assign"), r
    return float(r["value_text"].replace(" ", "")) if r.get("value_text") else None


def err(*lines):
    r = run(*lines)
    assert r["kind"] == "error", r
    return r["error"]["message"]


# ---------------------------------------------------------------- constants

def test_constants_have_units_and_codata_values():
    assert val("c0") == pytest.approx(299792458, rel=1e-6)           # shown to 8 significant figures
    r = run("hP*c0/(500 nm) to eV")
    assert float(r["value_text"]) == pytest.approx(2.4796, abs=1e-3) and r["unit"] == "eV"        # a 500 nm photon
    assert run("kBoltz*300 K to eV")["unit"] == "eV"
    assert val("sigmaSB*(5772 K)^4") == pytest.approx(6.2938e7, rel=1e-3)                           # the Sun's surface flux, W/m^2
    assert val("NA*2 mol") == pytest.approx(1.2044281e24, rel=1e-6)
    # the values are the exact SI 2019 ones and agree with each other
    h, c, e, k, na, rgas = (QCONSTANTS[n][0] for n in ("hP", "c0", "qe", "kBoltz", "NA", "Rgas"))
    assert rgas == pytest.approx(na * k, rel=1e-9) and QCONSTANTS["hbar"][0] == pytest.approx(h / (2 * math.pi), rel=1e-9)
    assert QCONSTANTS["mu0"][0] * QCONSTANTS["eps0"][0] * c**2 == pytest.approx(1, rel=1e-9)
    assert QCONSTANTS["sigmaSB"][0] == pytest.approx(2 * math.pi**5 * k**4 / (15 * h**3 * c**2), rel=1e-8)


def test_a_constant_name_can_still_be_used_as_a_variable_and_kb_stays_the_kilobyte():
    assert val("me = 5 kg", "me*2") == 10
    assert run("5 kB to bit")["value_text"] == "40000"


# ---------------------------------------------------------------- statistics

def test_statistics_keep_units_and_refuse_mixed_ones():
    assert val("mean(2 m, 4 m, 9 m)") == 5 and run("mean(2 m, 4 m, 9 m)")["unit"] == "m"
    assert val("sum(2 m, 30 cm, 1 m)") == pytest.approx(3.3)
    assert val("median(5 kg, 1 kg, 9 kg, 2 kg)") == pytest.approx(3.5)
    assert val("stdev(2,4,4,4,5,5,7,9)") == pytest.approx(math.sqrt(32 / 7))                         # sample standard deviation
    assert val("hypot(3 m, 4 m)") == 5 and val("hypot(1, 2, 2)") == 3
    assert val("sign(-3 m)") == -1 and val("mod(17 m, 5 m)") == 2 and val("mod(-1, 7)") == 6
    assert "cannot combine" in err("sum(1 m, 2 s)")
    assert "at least 2" in err("stdev(3)")
    assert "zero" in err("mod(3, 0)")
    assert run("mean(20 degC, 30 degC)")["value_text"] == "25"
    assert "offset" in err("sum(20 degC, 30 degC)") or "temperature" in err("sum(20 degC, 30 degC)")


# ---------------------------------------------------------------- calculus

def test_integrate_and_derivative_follow_the_units():
    assert val("f(x) = 3*x^2", "integrate(f, 0, 2)") == pytest.approx(8, rel=1e-9)
    r = run("v(t) = 9.81 m/s^2*t", "integrate(v, 0 s, 4 s)")
    assert float(r["value_text"]) == pytest.approx(78.48, rel=1e-9) and r["unit"] == "m"
    assert val("f(x) = x^3", "derivative(f, 2)") == pytest.approx(12, rel=1e-6)
    r = run("s(t) = 0.5*9.81 m/s^2*t^2", "derivative(s, 3 s)")
    assert float(r["value_text"]) == pytest.approx(29.43, rel=1e-6) and r["unit"] == "m/s"
    assert val("g(x) = sin(x)", "integrate(g, 0, pi)") == pytest.approx(2, rel=1e-6)
    assert val("g(x) = exp(-x^2)", "integrate(g, -6, 6)") == pytest.approx(math.sqrt(math.pi), rel=1e-6)


def test_findroot_and_sumover():
    assert val("h(x) = x^2 - 2", "findroot(h, 0, 2)") == pytest.approx(math.sqrt(2), rel=1e-6)
    r = run("p(x) = cos(x) - x", "findroot(p, 0, 1)")
    assert float(r["value_text"]) == pytest.approx(0.7390851332, abs=1e-8)
    assert val("f(k) = 1/k^2", "sumover(f, 1, 1000)") == pytest.approx(math.pi**2 / 6 - 1 / 1000.5, abs=1e-6)
    assert val("t(n) = n", "sumover(t, 1, 10)") == 55
    r = run("d(x) = 2 m*x", "sumover(d, 1, 3)")
    assert r["unit"] == "m" and float(r["value_text"]) == 12


def test_calculus_errors_explain_themselves():
    assert "same sign" in err("h(x) = x^2 + 1", "findroot(h, 0, 2)")
    assert "defined" in err("integrate(q, 0, 1)")
    assert "takes 3 values" in err("f(x) = x", "integrate(f, 0)")
    assert "one value" in err("f(a, b) = a*b", "derivative(f, 1)")
    assert "same units" in err("f(x) = x", "integrate(f, 0 m, 1 s)")
    assert "whole numbers" in err("f(k) = k", "sumover(f, 1.5, 4)")
    assert "defined" in err("integrate(5, 0, 1)")


def test_calculus_names_are_not_taken_for_unknown_variables():
    # integrate(f, 0, 2) is a calculation, not an equation with an unknown 'f'
    r = run("f(x) = x", "F = integrate(f, 0, 2)")
    assert r["kind"] == "assign" and r["value_text"] == "2"
    out = livecalc_eval(entries=["f(x) = x^2"], draft="integrate(f, 0, 3)")
    assert out["draft"]["lines"][-1]["kind"] == "value" and out["draft"]["lines"][-1]["value_text"] == "9"


def test_my_equations_drafts_warn_about_the_new_functions():
    d = livecalc_to_equation("y = hypot(a, b)", entries=["a = 3 m", "b = 4 m"])
    assert any("hypot() is not available" in w for w in d["warnings"])
    assert not livecalc_to_equation("y = sqrt(a^2 + b^2)", entries=["a = 3 m", "b = 4 m"])["warnings"]


def test_calculus_can_be_plotted_as_a_function_of_a_limit():
    s = Session(6)
    s.run_line("f(x) = x^2", 1)
    r = s.run_line("plot integrate(f, 0, x), derivative(f, x) from 0 to 3", 2)
    assert r["kind"] == "plot" and len(r["plot"]["series"]) == 2
    area, slope = r["plot"]["series"]
    xs = r["plot"]["series"][0]["x"] if "x" in area else None
    ys_area, ys_slope = area["y"], slope["y"]
    assert ys_area[-1] == pytest.approx(9, rel=1e-6) and ys_slope[-1] == pytest.approx(6, rel=1e-6)          # x^3/3 and 2x at x = 3
    assert xs is None or len(xs) == len(ys_area)
