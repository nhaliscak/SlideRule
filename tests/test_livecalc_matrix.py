"""LiveCalc: slices, matrices, plot options (equal, twin), and library calculations with differential equations or user equations."""

import numpy as np
import pytest

from sliderule import usercalcs
from sliderule.core.catalog import default_catalog
from sliderule.livecalc import Session


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


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


# ---------------------------------------------------------------- slices

def test_slices_count_from_one_and_include_both_ends():
    v = "v = [10, 20, 30, 40, 50] m"
    assert val(v, "v[2:4]") == [20, 30, 40] and run(v, "v[2:4]")["unit"] == "m"
    assert val(v, "v[:2]") == [10, 20] and val(v, "v[4:]") == [40, 50] and val(v, "v[-2:]") == [40, 50] and val(v, "v[:]") == [10, 20, 30, 40, 50]
    assert val(v, "sum(v[2:3])") == 50 and val(v, "v[1:2] + v[4:5]") == [50, 70]
    assert "empty" in err(v, "v[4:2]") and "outside" in err(v, "v[1:9]")


# ---------------------------------------------------------------- matrices

def test_matrix_literals_indexing_and_display():
    r = run("A = [[1, 2, 3], [4, 5, 6]]")
    assert r["value"] == [[1, 2, 3], [4, 5, 6]] and r["shape"] == [2, 3] and r["value_text"] == "[[1, 2, 3], [4, 5, 6]]" and "bmatrix" in r["result_latex"]
    A = "A = [[1, 2, 3], [4, 5, 6]]"
    assert val(A, "A[2, 3]") == 6 and val(A, "A[1]") == [1, 2, 3] and val(A, "A[:, 2]") == [2, 5] and val(A, "A[2, :]") == [4, 5, 6] and val(A, "A[1:2, 2:3]") == [[2, 3], [5, 6]]
    assert val(A, "A*2") == [[2, 4, 6], [8, 10, 12]] and val(A, "len(A)") == 2 and val(A, "rows(A)") == 2 and val(A, "cols(A)") == 3
    assert run("[[1, 2], [3, 4]] m")["unit"] == "m"
    assert "rows that are lists of the same length" in err("[[1, 2], [3]]") and "outside the rows" in err(A, "A[3, 1]") and "outside the columns" in err(A, "A[1, 4]")
    assert "one index" in err("v = [1, 2]", "v[1, 1]") and "has two indices" in err(A, "A[1, 2, 3]")
    assert "8 × 8" not in run("range(3)")["value_text"] and "10 × 10 matrix" in run("identity(10)")["value_text"]


def test_linear_algebra_matches_numpy_and_follows_units():
    a, b = [[2.0, 1.0], [1.0, 3.0]], [3.0, 5.0]
    A, B = "A = [[2, 1], [1, 3]]", "b = [3, 5]"
    assert val(A, B, "solve(A, b)") == pytest.approx(np.linalg.solve(a, b).tolist())
    assert val(A, "det(A)") == pytest.approx(5) and np.allclose(val(A, "inv(A)"), np.linalg.inv(a)) and val(A, "trace(A)") == 5
    assert val(A, "matmul(A, inv(A))") == [[1, 0], [0, 1]]                                           # rounding noise is shown as zero
    assert val("matmul([[1, 2], [3, 4]], [1, 1])") == [3, 7] and val("transpose([[1, 2, 3], [4, 5, 6]])") == [[1, 4], [2, 5], [3, 6]] and val("identity(3)")[2] == [0, 0, 1]
    # a spring system: stiffness in kN/m, force in kN gives displacement in m
    K, F = "K = [[200, -100], [-100, 100]] kN/m", "F = [10, 0] kN"
    r = run(K, F, "solve(K, F)")
    assert r["value"] == pytest.approx([0.1, 0.1]) and r["unit"] == "m"
    assert run(K, "det(K)")["unit"] == "kN^2/m^2" and run(K, "inv(K)")["unit"] == "m/kN"
    assert run("matmul([[2, 0], [0, 2]] m, [1, 3] N)")["unit"] == "m*N" and val("matmul([[2, 0], [0, 2]] m, [1, 3] N)") == [2, 6]


def test_matrix_errors():
    assert "singular" in err("solve([[1, 2], [2, 4]], [1, 2])") and "singular" in err("inv([[1, 2], [2, 4]])")
    assert "square" in err("det([[1, 2, 3], [4, 5, 6]])") and "needs a matrix" in err("det([1, 2])")
    assert "inner sizes differ" in err("matmul([[1, 2]], [[1, 2]])") and "rows, the size of A" in err("solve([[1, 0], [0, 1]], [1, 2, 3])")
    assert "whole number of rows" in err("identity(0)")


def test_matrix_results_agree_with_numpy_on_random_systems():
    rng = np.random.default_rng(7)
    for n in (2, 3, 5):
        m = np.round(rng.normal(size=(n, n)) + 4 * np.eye(n), 3)          # short numbers: a LiveCalc line has at most 400 characters
        b = np.round(rng.normal(size=n), 3)
        text = "[" + ", ".join("[" + ", ".join(str(float(x)) for x in row) + "]" for row in m) + "]"
        got = val(f"A = {text}", f"b = [{', '.join(str(float(x)) for x in b)}]", "solve(A, b)")
        assert got == pytest.approx(np.linalg.solve(m, b).tolist(), rel=1e-6, abs=1e-8)
        assert val(f"A = {text}", "det(A)") == pytest.approx(np.linalg.det(m), rel=1e-6)


# ---------------------------------------------------------------- plot options

def test_equal_scale_and_second_axis():
    r = run("plot parametric 2*cos(t), 3*sin(t) for t from 0 to 2*pi equal")
    assert r["kind"] == "plot" and r["plot"]["equal"]
    assert "same unit" in err("plot parametric 2 m*cos(t), 3 s*sin(t) for t from 0 to 6 equal")
    assert "logarithmic" in err("plot x^2, x^3 from 1 to 10 loglog equal")
    r = run("plot 5 m*x, 3 s*x^2 from 0 to 4 twin")
    p = r["plot"]
    assert p["twin"] and p["y_unit"] == "m" and p["y2_unit"] == "s" and [s.get("axis") for s in p["series"]] == [None, "right"]
    assert "twin" in err("plot 5 m*x, 3 s*x from 0 to 4") and "at least two" in err("plot x from 0 to 4 twin")
    assert "second axis" in err("plot x, x^2 from 0 to 4 twin equal")
    assert run("plot x, x^2 from 1 to 4 logy twin")["plot"]["logy"]                                  # options in any order
    assert run("plot x, x^2 from 1 to 4 twin logy")["plot"]["logy"]


# ---------------------------------------------------------------- units and library calculations

def test_a_bare_min_is_the_minute_unit():
    assert val("0.1/min * 5 min") == 0.5 and val("min(2, 3)") == 2 and run("3 min")["unit"] == "min" and val("x = min(4, 2)") == 2


def test_calc_runs_differential_equation_calculations_and_sweeps_over_time():
    cid = "mechanical.thermo.newton_cooling_transient"
    c = default_catalog().get(cid)
    one = run(f'calc("{cid}", "T", T0 = 90 degC, Ta = 20 degC, k = 0.1/min, t = 10 min)')
    assert one["kind"] == "value" and one["si_value"] - 273.15 == pytest.approx(20 + 70 * np.exp(-1), abs=0.05)
    sweep = run(f'calc("{cid}", "T", T0 = 90 degC, Ta = 20 degC, k = 0.1/min, t = linspace(0 min, 20 min, 5))')
    assert sweep["is_list"] and sweep["length"] == 5 and c.parsed_odes
    T = np.asarray(sweep["si_value"]) - 273.15
    assert T == pytest.approx(20 + 70 * np.exp(-0.1 * np.linspace(0, 20, 5)), abs=0.05)             # Newton cooling, computed independently
    d = run('calc("mechanical.dynamics.damped_oscillator_response", "x", m = 2 kg, c = 6 N*s/m, k = 800 N/m, x0 = 20 mm, v0 = 0 mm/s, t = 1.5 s)')
    assert d["kind"] == "value" and d["unit"] == "mm"


def test_calc_runs_a_table_calculation_and_the_users_own_equations():
    r = run('calc("mechanical.thermo.saturation_temperature_steam_table", "Tsat", P = 100 kPa)')
    assert r["kind"] == "value" and r["value"] == pytest.approx(99.61, abs=0.05)
    usercalcs.save({"name": "Double it", "description": "y is twice x", "disciplines": ["civil"], "variables": [{"key": "x", "label": "Input", "unit": "m"}, {"key": "y", "label": "Output", "unit": "m"}],
                    "equations": [{"title": "double", "text": "y = 2*x"}], "outputs": ["y"], "assumptions": [], "references": [], "validity": []})
    mine = [c.id for c in default_catalog() if c.custom][0]
    assert mine.startswith("custom.")
    r = run(f'calc("{mine}", "y", x = [1, 2, 3] m)')
    assert r["value"] == [2, 4, 6] and r["unit"] == "m"
    assert run('calc("double_it", "y", x = 4 m)')["value"] == 8                                      # by the end of its id, like any library calculation
