"""LiveCalc: least squares, rank, condition number, pseudo-inverse, singular values, outer product, variance, percentiles."""

import numpy as np
import pytest

from sliderule.livecalc import Session


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


def text(m):
    return "[" + ", ".join("[" + ", ".join(str(float(x)) for x in row) + "]" for row in m) + "]"


def test_lstsq_matches_numpy_and_follows_units():
    a = np.array([[1.0, 1], [1, 2], [1, 3], [1, 4]])
    b = np.array([6.0, 5, 7, 10])
    assert val(f"lstsq({text(a)}, [6, 5, 7, 10])") == pytest.approx(np.linalg.lstsq(a, b, rcond=None)[0].tolist())
    r = run(f"A = {text(a)} m", "b = [6, 5, 7, 10] N", "lstsq(A, b)")
    assert r["unit"] == "N/m" and r["value"] == pytest.approx([3.5, 1.4])
    rng = np.random.default_rng(11)
    for rows, cols in ((5, 2), (7, 3), (9, 3)):                                # short numbers: a LiveCalc line has at most 400 characters
        m = np.round(rng.normal(size=(rows, cols)), 2)
        y = np.round(rng.normal(size=rows), 2)
        got = val(f"lstsq({text(m)}, [{', '.join(str(float(v)) for v in y)}])")
        assert got == pytest.approx(np.linalg.lstsq(m, y, rcond=None)[0].tolist(), rel=1e-5, abs=1e-8)
    assert "independent" in err("lstsq([[1, 2], [2, 4], [3, 6]], [1, 2, 3])") and "at least as many equations" in err("lstsq([[1, 2, 3]], [1])")
    assert "rows" in err("lstsq([[1, 1], [1, 2]], [1, 2, 3])")


def test_rank_cond_pinv_svdvals_outer():
    assert val("rank([[1, 2], [2, 4]])") == 1 and val("rank([[1, 2], [3, 4]])") == 2
    assert val("cond([[1, 0], [0, 1]])") == pytest.approx(1) and val("cond([[1, 2], [3, 4]])") == pytest.approx(np.linalg.cond([[1, 2], [3, 4]]), rel=1e-6)
    assert "singular" in err("cond([[0, 0], [0, 0]])") and val("cond([[1, 2], [2, 4]])") > 1e15                  # an exactly singular matrix has no finite condition number; a rounding-level one has a huge one
    a = np.array([[1.0, 1], [1, 2], [1, 3]])
    assert np.allclose(val(f"pinv({text(a)})"), np.linalg.pinv(a), atol=1e-5)
    assert run("pinv([[2, 0], [0, 4]] N/m)")["unit"] == "m/N"
    assert val("svdvals([[3, 0], [0, 4]])") == pytest.approx([4, 3]) and run("svdvals([[3, 0], [0, 4]] kN/m)")["unit"] == "kN/m"
    r = run("outer([1, 2], [3, 4] m)")
    assert r["value"] == [[3, 4], [6, 8]] and r["unit"] == "m"
    assert "needs a matrix" in err("rank([1, 2])") and "square" in err("cond([[1, 2, 3], [4, 5, 6]])")


def test_variance_and_percentiles_match_numpy():
    data = [2, 4, 4, 4, 5, 5, 7, 9]
    assert val("var([2, 4, 4, 4, 5, 5, 7, 9])") == pytest.approx(np.var(data, ddof=1)) and run("var([1, 2, 4] m)")["unit"] == "m^2"
    assert val("percentile([1, 2, 3, 4, 5], 50)") == 3 and val("percentile([1, 2, 3, 4, 5], [25, 75])") == [2, 4]
    x = [round(float(v), 3) for v in np.random.default_rng(2).normal(size=15)]
    lx = "[" + ", ".join(str(v) for v in x) + "]"
    assert val(f"percentile({lx}, 90)") == pytest.approx(float(np.percentile(x, 90)), rel=1e-5, abs=1e-8)
    assert run("percentile([1, 2, 3] m, 50)")["unit"] == "m"
    assert "0 to 100" in err("percentile([1, 2, 3], 101)") and "at least two" in err("var([1])") and "complex" in err("var([1+1i, 2])")
