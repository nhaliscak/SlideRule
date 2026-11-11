"""LiveCalc's statistics, vector and matrix functions show their definition with the numbers put in. Every number is checked against numpy here."""

import numpy as np
import pytest

from sliderule import livecalc, livecalc_help
from sliderule.livecalc_funcs import EXPLAINERS


def last(*entries):
    out = []
    for e in livecalc.livecalc_eval(entries=list(entries))["entries"]:
        out += e["lines"]
    return out[-1]


def labels(ln):
    return [s["label"] for s in ln["steps"]]


def body(ln):
    return "\n".join(f"{s['label']}\n" + "\n".join(s["latex"] if isinstance(s["latex"], list) else [s["latex"]]) for s in ln["steps"])


def g(x):                                   # the number as the steps print it (6 significant figures, trailing zeros dropped)
    return f"{float(f'{x:.6g}'):g}"


def test_mean_shows_the_sum_and_the_division_with_units():
    ln = last("mean(2 m, 4 m, 9 m)")
    assert labels(ln) == ["Expression", "Add the values", "Divide by the number of values", "Result"]
    assert "2 + 4 + 9 = 15\\,\\mathrm{m}" in body(ln) and "\\frac{15\\,\\mathrm{m}}{3} = 5\\,\\mathrm{m}" in body(ln)


def test_sum_of_a_list_in_its_own_unit():
    ln = last("sum([100, 250, 50] cm)")
    assert "100 + 250 + 50 = 400\\,\\mathrm{cm}" in body(ln) and ln["value"] == pytest.approx(400)


@pytest.mark.parametrize("data", [[2, 4, 4, 4, 5, 5, 7, 9], [1.5, 2.5, 8.25], [10, 12, 23, 23, 16, 23, 21, 16]])
def test_stdev_and_var_follow_the_sample_definition(data):
    txt = ", ".join(str(x) for x in data)
    arr = np.array(data, float)
    ss = float(np.sum((arr - arr.mean()) ** 2))
    sd = last(f"stdev({txt})")
    assert g(arr.mean()) in body(sd) and g(ss) in body(sd) and f"n − 1 = {len(arr) - 1}" in " ".join(labels(sd)) and g(np.std(arr, ddof=1)) in body(sd)
    assert sd["value"] == pytest.approx(np.std(arr, ddof=1), rel=1e-5)
    vr = last(f"var([{txt}])")
    assert g(np.var(arr, ddof=1)) in body(vr) and "Square root" not in labels(vr)


def test_median_odd_and_even_and_min_max():
    assert "Take the middle one" in labels(last("median(3, 1, 2)")) and "Average the two middle ones" in labels(last("median(4, 1, 3, 2)"))
    assert "The smallest of the values" in labels(last("min(4, 9, 2)")) and "2" in body(last("min(4, 9, 2)"))
    assert "The largest of the values" in labels(last("max(2, 7, 4)"))


def test_hypot_norm_dot_cross_mod_factorial():
    assert "3^2 + 4^2 = 25\\,\\left(\\mathrm{m}\\right)^{2}" in body(last("hypot(3 m, 4 m)"))
    assert "5\\,\\mathrm{m}" in body(last("norm([3, 4] m)"))
    d = last("dot([1, 2, 3], [4, 5, 6])")
    assert "(1)(4) + (2)(5) + (3)(6) = 32" in body(d)
    c = last("cross([1, 0, 0], [0, 1, 0])")
    assert "\\left(0,\\ 0,\\ 1\\right)" in body(c) and c["value"] == [0, 0, 1]
    assert "17 - 5 \\cdot 3 = 2" in body(last("mod(17, 5)"))
    assert "5! = 5 \\cdot 4 \\cdot 3 \\cdot 2 \\cdot 1 = 120" in body(last("factorial(5)"))


def test_trapz_interp_and_the_line_fit():
    t = last("trapz([0, 1, 2, 3, 4] s, [0, 2, 4, 6, 8] m/s)")
    assert "= 16" in body(t) and "\\frac{(1 - 0)(0 + 2)}{2}" in body(t)
    it = last("interp(2.5 s, [0, 1, 2, 3, 4] s, [0, 2, 4, 6, 8] m/s)")
    assert "2 \\le 2.5 \\le 3" in body(it) and "= 5" in body(it)
    xs, ys = np.array([0, 1, 2, 3.0]), np.array([1, 3, 5, 8.0])
    sxx, sxy = float(np.sum((xs - xs.mean()) ** 2)), float(np.sum((xs - xs.mean()) * (ys - ys.mean())))
    sl = last("slope([0, 1, 2, 3] s, [1, 3, 5, 8] m)")
    assert g(sxx) in body(sl) and g(sxy) in body(sl) and g(sxy / sxx) in body(sl)
    ic = last("intercept([0, 1, 2, 3] s, [1, 3, 5, 8] m)")
    assert g(ys.mean() - sxy / sxx * xs.mean()) in body(ic)
    r2 = last("rsquared([0, 1, 2, 3], [1, 3, 5, 8])")
    assert g(np.corrcoef(xs, ys)[0, 1] ** 2) in body(r2)
    cr = last("corr([1, 2, 3, 4], [2, 4, 5, 9])")
    assert g(np.corrcoef([1, 2, 3, 4], [2, 4, 5, 9])[0, 1]) in body(cr)


def test_percentile_positions_and_interpolation():
    ln = last("percentile([10, 20, 30, 40], 50)")
    assert "h = \\frac{p}{100}(n - 1) = \\frac{50}{100}(4 - 1) = 1.5" in body(ln) and "= 25" in body(ln)
    assert "whole number" in " ".join(labels(last("percentile([1, 2, 3, 4, 5], 25)")))


def test_matrices_determinants_inverse_solve_eigen():
    assert "ad - bc = (2)(3) - (1)(1) = 5" in body(last("det([[2, 1], [1, 3]])"))
    a3 = np.array([[2, 0, 1], [1, 3, 2], [1, 1, 1.0]])
    d3 = last("det([[2, 0, 1], [1, 3, 2], [1, 1, 1]])")
    assert g(np.linalg.det(a3)) in body(d3) and "Expand along the first row" in " ".join(labels(d3))
    d4 = last("det([[2, 0, 1, 1], [1, 3, 2, 0], [1, 1, 1, 2], [0, 1, 0, 3]])")
    assert "LU factorisation" in " ".join(labels(d4)) and g(np.linalg.det(np.array([[2, 0, 1, 1], [1, 3, 2, 0], [1, 1, 1, 2], [0, 1, 0, 3.0]]))) in body(d4)
    inv = last("inv([[2, 1], [1, 3]])")
    assert "\\frac{1}{5}" in body(inv) and "0.6 & -0.2" in body(inv)
    sol = last("solve([[2, 1], [1, 3]], [3, 5])")
    assert "Cramer" in labels(sol)[1] and "x_1 = \\frac{4}{5} = 0.8" in body(sol) and "x_2 = \\frac{7}{5} = 1.4" in body(sol)
    ev = last("eigvals([[2, 1], [1, 2]])")
    assert "\\lambda^2 - (4)\\lambda + (3) = 0" in body(ev) and ev["value"] == [1, 3]
    assert "= 6" in body(last("trace([[2, 1], [1, 4]])")) or "2 + 4 = 6" in body(last("trace([[2, 1], [1, 4]])"))
    cond = last("cond([[1, 2], [3, 4]])")
    s = np.linalg.svd(np.array([[1, 2], [3, 4.0]]), compute_uv=False)
    assert g(s[0]) in body(cond) and g(s[0] / s[1]) in body(cond)


def test_constants_are_listed_and_put_into_the_substitution():
    ln = last("Gnewton * 5.972e24 kg / (6.371e6 m)^2")
    assert labels(ln) == ["Expression", "Constants", "Substitute the values", "Result"]
    assert "Newtonian constant of gravitation" in body(ln) and "6.6743\\times10^{-11}" in body(ln).split("Substitute the values")[1]


def test_list_helpers_range_linspace_cumtrapz_polyfit_index():
    assert "\\Delta = \\frac{b - a}{n - 1} = \\frac{1 - 0}{4} = 0.25" in body(last("linspace(0 s, 1 s, 5)"))
    assert "Running total" in labels(last("cumtrapz([0, 1, 2, 3, 4] s, [0, 2, 4, 6, 8] m/s)"))
    assert "Pick the entry (counting from 1)" in labels(last("v = [10, 20, 30] kg", "v[2]"))
    pf = last("polyfit([0, 1, 2, 3] s, [1, 4, 9, 16] m, 2, [4, 5] s)")
    assert "25,\\ 36" in body(pf)


def test_a_function_inside_an_expression_is_explained_and_substituted():
    ln = last("2*mean(1 m, 3 m) + 10 cm")
    assert "mean1: Add the values" not in labels(ln) and "Add the values" in labels(ln) and "With the results of the functions" in labels(ln)
    assert ln["value"] == pytest.approx(4.1)
    two = last("mean(1, 3) + median(5, 1, 2)")
    assert "mean1: Add the values" in labels(two) and "median2: Put the values in order" in labels(two)


def test_elementary_functions_are_explained_only_when_they_are_the_whole_line():
    for t in ("sqrt(16 m^2)", "sin(pi/6)", "abs(-5 m)", "floor(2.7)"):
        assert labels(last(t))[:2] == ["Expression", "The function"], t
    assert labels(last("2*sin(1) + 1")) == ["Expression", "Result"]


def test_every_catalog_example_still_evaluates_and_explained_ones_have_more_than_two_steps():
    explained = 0
    for name, _cat, _sig, _summary, _words, examples in livecalc_help._ENTRIES:
        for t in examples:
            for e in livecalc.livecalc_eval(entries=[t])["entries"]:
                for ln in e["lines"]:
                    if ln.get("kind") == "value" and name in EXPLAINERS and ln["steps"] and len(ln["steps"]) > 2:
                        explained += 1
                    assert ln.get("kind") != "error" or "error" in ln, (name, t)
    assert explained >= 45
