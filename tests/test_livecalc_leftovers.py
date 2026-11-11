"""LiveCalc leftovers: element-wise list arithmetic, elementary functions, complex numbers, exact roots and sums; and two inverse-solve cases (roots closer together
than the scan spacing, a polynomial inside an exp that SymPy cannot finish)."""

import math
import time

import numpy as np
import pytest

from sliderule import api, livecalc
from sliderule.core import solve
from sliderule.core.custom import calc_from_dict


def last(*entries, angle="rad"):
    out = []
    for e in livecalc.livecalc_eval(entries=list(entries), angle=angle)["entries"]:
        out += e["lines"]
    return out[-1]


def labels(ln):
    return [s["label"] for s in ln["steps"]]


def body(ln):
    return "\n".join(f"{s['label']}\n" + "\n".join(s["latex"] if isinstance(s["latex"], list) else [s["latex"]]) for s in ln["steps"])


def test_list_arithmetic_is_shown_entry_by_entry_with_units():
    ln = last("[1, 2, 3] m * 2")
    assert labels(ln) == ["Expression", "The same arithmetic on every entry", "Result"]
    assert "\\text{entry 2: }\\ 2\\,\\mathrm{m} \\cdot 2 = 4\\,\\mathrm{m}" in body(ln) and ln["value"] == [2, 4, 6]
    ln = last("v = [10, 20, 30] kg", "v*2 + 5 kg")
    assert "10\\,\\mathrm{kg} \\cdot 2 + 5\\,\\mathrm{kg} = 25\\,\\mathrm{kg}" in body(ln) and ln["value"] == [25, 45, 65]


def test_a_long_list_shows_the_first_entries_and_the_last():
    ln = last("[1, 4, 9, 16, 25, 36] ^ 0.5")
    b = body(ln)
    assert "entry 1" in b and "entry 3" in b and "entry 4" not in b and "\\cdots" in b and "entry 6: }\\ 36^{0.5} = 6" in b
    arr = np.array([1, 4, 9, 16, 25, 36.0]) ** 0.5
    assert ln["value"] == list(arr)


def test_list_arithmetic_with_a_function_and_cases_it_cannot_expand():
    ln = last("sin([0, 1, 2])")
    assert "The same arithmetic on every entry" in labels(ln) and r"\sin\left(1\right) = 0.841471" in body(ln)
    assert labels(last("[[1, 2], [3, 4]] * 2")) == ["Expression", "Result"]                 # a matrix is not expanded entry by entry
    assert labels(last("cumsum([1, 2, 3])"))[1] == "Running totals"                       # a function that has its own explanation keeps it


@pytest.mark.parametrize("text, name, value", [("sqrt(16 m^2)", "sqrt", 4), ("exp(1)", "exp", math.e), ("ln(10)", "ln", math.log(10)), ("log10(1000)", "log10", 3),
                                               ("abs(-5 m)", "abs", 5), ("floor(2.7)", "floor", 2), ("tanh(2)", "tanh", math.tanh(2))])
def test_elementary_functions_show_what_they_are_and_the_evaluation(text, name, value):
    ln = last(text)
    assert labels(ln)[:2] == ["Expression", "The function"] and "Evaluate" in labels(ln) and labels(ln)[-1] == "Result"
    assert ln["value"] == pytest.approx(value)


def test_trigonometric_arguments_show_the_conversion_to_radians():
    ln = last("sin(30 deg)")
    assert "x = 30\\,\\mathrm{deg} = 0.523599\\ \\mathrm{rad}" in body(ln) and "\\sin\\left(0.523599\\right) = 0.5" in body(ln)
    ln = last("sin(30)", angle="deg")
    assert "30^\\circ = 30 \\cdot \\frac{\\pi}{180} = 0.523599\\ \\mathrm{rad}" in body(ln) and ln["value"] == pytest.approx(0.5)
    assert "\\frac{e^{x} + e^{-x}}{2}" in body(last("cosh(1)"))


def test_an_elementary_function_inside_a_longer_expression_keeps_the_plain_steps():
    assert "The function" not in labels(last("2*sin(1) + 1"))


def test_complex_functions_and_values():
    z = complex(3, 4)
    assert "\\operatorname{Re}\\,z = 3" in body(last("real(3 + 4i)")) and "\\operatorname{Im}\\,z = 4" in body(last("imag(3 + 4i)"))
    assert "= \\sqrt{25} = 5" in body(last("abs(3 + 4i)")) and "3 - 4\\,i" in body(last("conj(3 + 4i)"))
    ar = last("arg(3 + 4i)")
    assert f"{np.angle(z):.6g}" in body(ar) and f"{np.degrees(np.angle(z)):.6g}" in body(ar)
    pl = last("polar(5, 53.13 deg)")
    assert "r\\cos\\theta" in body(pl) and pl["value"] == pytest.approx(5 * np.exp(1j * np.radians(53.13)).real, rel=1e-4)
    cv = last("3 + 4i")
    assert labels(cv) == ["Expression", "Rectangular form", "Magnitude and angle (polar form)", "Result"] and "= 5,\\quad \\theta = 0.927295" in body(cv)
    prod = last("(1 + 2i) * (3 - i)")
    assert "Rectangular form" in labels(prod) and "5 + 5\\,i" in body(prod)


def test_findroot_gives_the_exact_root_when_there_is_one_and_checks_itself():
    ln = last("h(x) = x^2 - 2", "findroot(h, 0, 2)")
    assert "Solve exactly" in labels(ln) and "x = \\sqrt{2} = 1.41421" in body(ln) and ln["value"] == pytest.approx(math.sqrt(2))
    ln = last("e2(x) = exp(x) - 3", "findroot(e2, 0, 3)")
    assert "x = \\log{\\left(3 \\right)} = 1.09861" in body(ln)
    ln = last("g(x) = cos(x) - x", "findroot(g, 0, 1)")
    assert "Solve exactly" not in labels(ln) and "Method: Brent's method" in labels(ln) and ln["value"] == pytest.approx(0.7390851332)


def test_sumover_gives_a_closed_form_or_the_exact_sum():
    ln = last("q(n) = n^2", "sumover(q, 1, 10)")
    assert "\\frac{N \\left(2 N^{2} + 3 N + 1\\right)}{6}" in body(ln) and "= 385" in body(ln)
    ln = last("k(n) = 1/n^2", "sumover(k, 1, 4)")
    assert "\\frac{205}{144}" in body(ln) and ln["value"] == pytest.approx(205 / 144)
    ln = last("k(n) = 1/n^2", "sumover(k, 1, 1000)")                    # too many terms for the exact sum: the terms and the total only
    assert "Closed form of the sum" not in labels(ln) and ln["value"] == pytest.approx(sum(1 / n**2 for n in range(1, 1001)))


def test_two_roots_closer_together_than_the_scan_spacing_are_found():
    r = api.solve("chemical.molecular.lennard_jones", {"eps": "10.3 meV", "r": "0.4 nm", "U": "-9.711550934366862 meV"}, solve_for=["sg"], sig_figs=8)
    assert r["ok"] and next(o for o in r["outputs"] if o["key"] == "sg")["value"] == pytest.approx(0.3405, rel=1e-6)
    assert any("two roots lay close together" in d["message"] for d in r["diagnostics"])


def test_a_polynomial_inside_an_exp_goes_straight_to_numerical_inversion():
    t = time.monotonic()
    c = api.get_calculation("architectural.comfort.mean_radiant_operative_ppd_draught")
    base = api.solve("architectural.comfort.mean_radiant_operative_ppd_draught", dict(c["example"]), sig_figs=10)
    givens = {k: v for k, v in c["example"].items() if k != "PMV"}
    givens["PPD"] = f'{next(o for o in base["outputs"] if o["key"] == "PPD")["value"]} %'
    r = api.solve("architectural.comfort.mean_radiant_operative_ppd_draught", givens, solve_for=["PMV"], sig_figs=8)
    assert r["ok"] and next(o for o in r["outputs"] if o["key"] == "PMV")["value"] == pytest.approx(0.5, rel=1e-6)
    assert time.monotonic() - t < 8                                         # SymPy used to spend minutes (uninterruptibly) on this one


def test_a_value_just_beyond_a_peak_is_refused_with_a_hint_about_the_peak():
    d = {"id": "custom.pk", "name": "Peak", "description": "y = x exp(-x) peaks at 1/e", "disciplines": ["mechanical"],
         "variables": [{"key": "y", "label": "y", "unit": "1", "example": "0.3"}, {"key": "x", "label": "x", "unit": "1", "example": "1"}],
         "equations": [{"title": "f", "text": "y = x*exp(-x)"}], "outputs": ["y"]}
    r = solve(calc_from_dict(d), {"y": "0.36788"}, solve_for=["x"])               # 1/e = 0.367879441...: 0.36788 is a hair above the maximum
    assert not r.ok
    msg = " ".join(x.message for x in r.diagnostics)
    assert "comes closest to zero" in msg and "near x = 1" in msg and "just miss" in msg
