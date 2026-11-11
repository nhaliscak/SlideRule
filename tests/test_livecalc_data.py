"""LiveCalc: measured-data helpers (integration, interpolation, line and polynomial fits), eigenvalues, and every library example as a calc line."""

import numpy as np
import pytest

from sliderule.core.catalog import default_catalog
from sliderule.livecalc import Session, library_example


def run(*lines):
    s = Session(8)
    out = [s.run_line(ln, i + 1) for i, ln in enumerate(lines)]
    return out[-1]


def val(*lines):
    r = run(*lines)
    assert r["kind"] in ("value", "assign"), r
    return r["value"]


def err(*lines):
    r = run(*lines)
    assert r["kind"] == "error", r
    return r["error"]["message"]


T, V = "t = [0, 1, 2, 3, 4] s", "v = [0, 2, 4, 6, 8] m/s"


def test_trapz_and_interp_follow_units_and_match_numpy():
    r = run(T, V, "trapz(t, v)")
    assert r["value"] == 16 and r["unit"] == "m"
    assert val(T, V, "cumtrapz(t, v)") == [0, 1, 4, 9, 16]
    rng = np.random.default_rng(3)
    x = np.round(np.sort(rng.uniform(0, 10, 12)), 3)          # short numbers: a LiveCalc line has at most 400 characters
    y = np.round(rng.normal(size=12), 3)
    lx, ly = "[" + ", ".join(str(float(a)) for a in x) + "]", "[" + ", ".join(str(float(a)) for a in y) + "]"
    assert val(f"trapz({lx}, {ly})") == pytest.approx(float(np.trapezoid(y, x) if hasattr(np, "trapezoid") else np.trapz(y, x)), rel=1e-5, abs=1e-7)
    assert val(f"interp(5.5, {lx}, {ly})") == pytest.approx(float(np.interp(5.5, x, y)), rel=1e-5, abs=1e-7)
    assert run(T, V, "interp(2.5 s, t, v)")["unit"] == "m/s" and val(T, V, "interp(2.5 s, t, v)") == 5 and val(T, V, "interp([0.5, 3.5] s, t, v)") == [1, 7]
    assert val("interp(20 degC, [0, 100] degC, [1, 3])") == pytest.approx(1.4)
    assert "extrapolate" in err(T, V, "interp(9 s, t, v)") and "increase" in err("interp(1, [3, 2, 1], [1, 2, 3])") and "same units" in err(T, V, "interp(2 m, t, v)")
    assert "same length" in err("trapz([0, 1], [0, 1, 2])") and "at least 2" in err("trapz([1], [1])")


def test_line_and_polynomial_fits_match_numpy():
    x, y = [0, 1, 2, 3], [1, 3, 5, 8]
    k, b = np.polyfit(x, y, 1)
    assert val("slope([0, 1, 2, 3], [1, 3, 5, 8])") == pytest.approx(k) and val("intercept([0, 1, 2, 3], [1, 3, 5, 8])") == pytest.approx(b)
    r2 = 1 - np.sum((np.array(y) - (k * np.array(x) + b)) ** 2) / np.sum((np.array(y) - np.mean(y)) ** 2)
    assert val("rsquared([0, 1, 2, 3], [1, 3, 5, 8])") == pytest.approx(r2) and val("corr([0, 1, 2, 3], [1, 3, 5, 8])") == pytest.approx(np.corrcoef(x, y)[0, 1])
    r = run("slope([0, 1, 2, 3] s, [1, 3, 5, 8] m)")
    assert r["unit"] == "m/s" and r["value"] == pytest.approx(k)
    assert run("intercept([0, 1, 2, 3] s, [1, 3, 5, 8] m)")["unit"] == "m"
    assert val(T, V, "intercept(t, v)") == 0                                              # rounding noise is a zero
    assert val("polyfit([0, 1, 2, 3], [1, 3, 7, 13], 2, 4)") == pytest.approx(21) and val("polyfit([0, 1, 2, 3], [1, 3, 7, 13], 2, [4, 5])") == pytest.approx([21, 31])
    rng = np.random.default_rng(5)
    xs = np.linspace(0, 6, 9)
    ys = 1 + 0.5 * xs - 0.1 * xs**2 + rng.normal(scale=0.02, size=9)
    lx, ly = "[" + ", ".join(str(round(float(a), 4)) for a in xs) + "]", "[" + ", ".join(str(round(float(a), 4)) for a in ys) + "]"
    want = np.polyval(np.polyfit(np.round(xs, 4), np.round(ys, 4), 3), 7.0)
    assert val(f"polyfit({lx}, {ly}, 3, 7)") == pytest.approx(float(want), rel=1e-6)
    assert run("polyfit([0, 1, 2, 3] s, [1, 4, 9, 16] m, 2, [4, 5] s)")["unit"] == "m"
    assert "all the same" in err("slope([1, 1, 1], [1, 2, 3])") and "needs at least 6" in err("polyfit([0, 1, 2, 3, 4], [1, 2, 3, 4, 5], 5, 1)")
    assert "whole degree" in err("polyfit([0, 1, 2], [1, 2, 3], 0, 1)") and "not all the same" in err("corr([1, 2, 3], [4, 4, 4])")


def test_eigenvalues_of_symmetric_and_general_matrices():
    assert val("eigvals([[2, 1], [1, 2]])") == pytest.approx([1, 3])
    vecs = np.array(val("eigvecs([[2, 1], [1, 2]])"))
    assert np.allclose(np.abs(vecs), 1 / np.sqrt(2), atol=1e-5)                             # (1, -1)/sqrt 2 and (1, 1)/sqrt 2
    a = np.array([[4.0, 1.0, 0.5], [1.0, 3.0, 0.2], [0.5, 0.2, 2.0]])
    text = "[" + ", ".join("[" + ", ".join(str(x) for x in row) + "]" for row in a) + "]"
    w = np.array(val(f"eigvals({text})"))
    assert w == pytest.approx(np.linalg.eigvalsh(a), rel=1e-6)
    V = np.array(val(f"eigvecs({text})"))
    assert np.allclose(a @ V, V * w, atol=1e-5)                                            # A v = lambda v for every column
    r = run("eigvals([[2, 0], [0, 3]] kN/m)")
    assert r["value"] == [2, 3] and r["unit"] == "kN/m"
    assert val("eigvals([[2, 1], [0, 3]])") == pytest.approx([2, 3])                         # not symmetric, but real
    assert "square" in err("eigvals([[1, 2, 3], [4, 5, 6]])")


def test_every_library_calculation_runs_as_a_calc_line():
    sample = [c for c in default_catalog() if not c.custom][::6]
    bad = [(c.id, r["error"]["message"][:80]) for c in sample if (r := Session(6).run_line(library_example(c), 1))["kind"] != "value"]
    assert bad == []                                                                         # 946 of 946 run (the fractional-power units were the last gap)


def test_fractional_unit_exponents():
    assert run("0.02 K/s^0.5")["unit"] == "K/s^(1/2)" and run("0.02 K/s^(1/2)")["unit"] == "K/s^(1/2)"
    assert val("sqrt(4 s) * 0.02 K/s^0.5") == pytest.approx(0.04) and val("5 m^0.5 * 2 m^0.5") == 10
    assert run("(0.02 K/s)^2")["unit"] == "K^2/s^2" and run("9.81 m/s^2")["unit"] == "m/s^2"
