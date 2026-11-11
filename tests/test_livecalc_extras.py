"""LiveCalc: QR, LU and Cholesky factors, 3-D lists, and the Argand and Nyquist plots."""

import numpy as np
import pytest
from scipy.linalg import lu as scipy_lu

from sliderule import api, livecalc


def run(*entries):
    res = livecalc.livecalc_eval(entries=list(entries))
    return [ln for e in res["entries"] for ln in e["lines"]]


def last(*entries):
    return run(*entries)[-1]


def arr(line):
    return np.array(line["value"], dtype=float)


A = [[4.0, 3.0], [6.0, 3.0]]
M = "[[2, -1, 0], [1, 3, 2], [0, 5, 1], [4, 1, 1]]"


def test_qr_factors_multiply_back_and_match_numpy():
    q, r = arr(last(f"qr_q({M})")), arr(last(f"qr_r({M})"))
    assert np.allclose(q @ r, np.array(eval(M), dtype=float)) and np.allclose(q.T @ q, np.eye(3)) and np.allclose(np.tril(r, -1), 0)
    assert np.allclose(np.abs(r), np.abs(np.linalg.qr(np.array(eval(M), dtype=float))[1]))
    assert last("qr_r([[3 m, 1 m], [4 m, 2 m]])")["unit"] == "m" and last("qr_q([[3 m, 1 m], [4 m, 2 m]])")["unit"] == ""            # R keeps the unit, Q has none


def test_lu_factors_follow_scipy_and_multiply_back():
    for text in ("[[4, 3], [6, 3]]", "[[2, 1, 1], [4, 3, 3], [8, 7, 9]]", "[[0, 2, 1], [1, 1, 0], [3, 0, 2]]"):
        a = np.array(eval(text), dtype=float)
        p, l, u = (arr(last(f"lu_{k}({text})")) for k in "plu")
        sp, sl, su = scipy_lu(a)
        assert np.allclose(p, sp) and np.allclose(l, sl) and np.allclose(u, su) and np.allclose(p @ l @ u, a)
        assert np.allclose(np.diag(l), 1) and np.allclose(np.triu(l, 1), 0) and np.allclose(np.tril(u, -1), 0)
    assert last("lu_u([[4 N, 3 N], [6 N, 3 N]])")["unit"] == "N" and last("lu_l([[4 N, 3 N], [6 N, 3 N]])")["unit"] == ""


def test_cholesky_and_its_refusals():
    s = [[4.0, 2.0], [2.0, 3.0]]
    low = arr(last("chol([[4, 2], [2, 3]])"))
    assert np.allclose(low @ low.T, s) and np.allclose(low, np.linalg.cholesky(s))
    assert last("chol([[4 m^2, 2 m^2], [2 m^2, 3 m^2]])")["unit"] == "m"                    # the unit of A is the square of the unit of L
    assert "symmetric" in last("chol([[4, 3], [6, 3]])")["error"]["message"]
    assert "positive-definite" in last("chol([[1, 2], [2, 1]])")["error"]["message"]


def test_three_dimensional_lists_index_combine_and_show():
    pre = "B = [[[1, 2], [3, 4]], [[5, 6], [7, 8]]]"
    assert last(pre, "B[2, 1, 2]")["value"] == 6 and arr(last(pre, "B[2]")).tolist() == [[5, 6], [7, 8]] and arr(last(pre, "B[:, 1, 1]")).tolist() == [1, 5]
    assert arr(last(pre, "B*2 + B")).tolist() == (np.array([[[1, 2], [3, 4]], [[5, 6], [7, 8]]]) * 3).tolist()
    assert arr(last(pre, "shape(B)")).tolist() == [2, 2, 2] and arr(last("shape([[1, 2, 3], [4, 5, 6]])")).tolist() == [2, 3]
    shown = last(pre, "B")
    assert shown["value_text"] == "[[[1, 2], [3, 4]], [[5, 6], [7, 8]]]" and shown["shape"] == [2, 2, 2] and shown["result_latex"].count("bmatrix") == 4
    big = last("C = [[[1,2,3,4,5,6],[1,2,3,4,5,6]],[[1,2,3,4,5,6],[1,2,3,4,5,6]]]", "C")
    assert big["value_text"] == "[2 × 2 × 6 array]"
    assert last("[[[1, 2], [3, 4]], [[5, 6]]]")["error"]["message"].startswith("A matrix needs")
    assert "three indices" in last(pre, "B[1, 1, 1, 1]")["error"]["message"]
    assert last(pre, "B[1, 3, 1]")["error"]["message"].startswith("Index 3 is outside the rows")
    assert last("[[[1 m, 2 m]], [[3 s, 4 s]]]")["kind"] == "error"                               # layers must share a unit
    assert arr(last(pre, "B*1 m")).shape == (2, 2, 2) and last(pre, "B*1 m")["unit"] == "m"


def test_argand_plot_puts_real_across_and_imaginary_up():
    ln = last("z = [1 + 2i, -1 + 0.5i, 2 - 1i]", "plot argand z")
    pl = ln["plot"]
    assert ln["kind"] == "plot" and pl["x"] == [1, -1, 2] and pl["series"][0]["y"] == [2, 0.5, -1] and pl["points"] and pl["equal"] and pl["y_label"] == "Im"
    assert last("plot argand 3 + 4i")["plot"]["x"] == [3]
    m = last("plot argand [1 m + 2i m, 2 m]")["plot"]
    assert m["x_unit"] == "m" and m["y_unit"] == "m" and m["series"][0]["y"] == [2, 0]
    assert last("plot argand")["kind"] == "error"
    assert last("plot argand [1 K + 2i K]")["kind"] == "plot"


def test_nyquist_of_a_first_order_lag_is_a_semicircle_and_mirrored():
    pl = run("H(s) = 1/(1 + s)", "plot nyquist H(i*w) for w from 0.01 to 100")[-1]["plot"]
    x, y = np.array(pl["x"], dtype=float), np.array(pl["series"][0]["y"], dtype=float)
    assert np.allclose(np.hypot(x - 0.5, y), 0.5, atol=2e-6)                             # |H - 1/2| = 1/2 for H = 1/(1 + jw)
    half = len(x) // 2
    assert np.allclose(x[:half], x[half:][::-1]) and np.allclose(y[:half], -y[half:][::-1])    # the negative frequencies mirror the positive ones
    assert np.all(y[:half] <= 1e-12) and np.all(y[half:] >= -1e-12)
    w = run("H(s) = 1/(1 + s)", "plot nyquist H(i*w)")[-1]["plot"]                      # no range: 0.01 to 100
    assert w["x"][0] == pytest.approx(1 / (1 + 0.01**2), rel=1e-4) and w["equal"]
    assert run("H(s) = 1/(1 + s)", "plot nyquist H(i*w), 2")[-1]["kind"] == "error"
    second = np.array(run("G(s) = 10/(s*(1 + s))", "plot nyquist G(i*w) for w from 0.1 to 10")[-1]["plot"]["series"][0]["y"], dtype=float)
    assert second[0] < -5                                                                  # a pole at the origin: the curve starts far down the imaginary axis


def test_the_new_functions_and_commands_are_in_the_catalogue():
    cat = {i["name"] for i in api.handle("livecalc_functions", {})["result"]["items"]}
    assert {"qr_q", "qr_r", "lu_l", "lu_u", "lu_p", "chol", "shape", "plot nyquist", "plot argand"} <= cat


ENTRIES = ["# Beam notes\nA plain note.", "m = 5 kg\nF = m*9.81 m/s^2", "f(x) = x^2\nf(3)\nplot sin(x)", "1 m + 3 s", "```\nnot = a calc\n```", "a = 2 m/s^2\nt = 4 s\nv = a*t"]


def test_the_exported_script_and_notebook_reproduce_the_session():
    import contextlib
    import io
    import json

    script = livecalc.livecalc_export(entries=ENTRIES, fmt="python")
    assert script["filename"].endswith(".py") and "from sliderule.livecalc import Session" in script["content"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(script["content"], "session.py", "exec"), {})
    printed = buf.getvalue().splitlines()
    assert "F = 49.05 N" in printed and "f(3)  =  9" in printed and "v = 8 m/s" in printed
    assert any(l.startswith("1 m + 3 s") and "error: Cannot add length (m) and time (s)" in l for l in printed)
    nb = json.loads(livecalc.livecalc_export(entries=ENTRIES, fmt="notebook")["content"])
    assert nb["nbformat"] == 4 and nb["cells"][0]["cell_type"] == "markdown" and nb["cells"][1]["cell_type"] == "code"
    stored = [t.rstrip("\n") for c in nb["cells"] if c["cell_type"] == "code" for o in c["outputs"] for t in o["text"]]
    assert stored == printed                                                       # the outputs saved in the notebook are exactly what the script prints
    assert [c["cell_type"] for c in nb["cells"]].count("markdown") == 3             # the title, the note and the fenced text; the calculations are code cells
    shared = {}                                                                     # running the code cells in order, in one namespace, gives the same again
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        for c in nb["cells"]:
            if c["cell_type"] == "code":
                exec(compile("".join(c["source"]), "cell", "exec"), shared)
    assert out.getvalue().splitlines() == printed


def test_degrees_are_carried_into_the_export_and_unknown_formats_are_refused():
    script = livecalc.livecalc_export(entries=["sin(30)"], fmt="python", angle="deg")["content"]
    assert 'Session(6, "deg")' in script
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(script, "s.py", "exec"), {})
    assert "0.5" in buf.getvalue()
    assert api.handle("livecalc_export", {"entries": ["1 + 1"], "fmt": "notebook"})["ok"]
    assert not api.handle("livecalc_export", {"entries": ["1 + 1"], "fmt": "docx"})["ok"]


def test_nyquist_margins_match_the_hand_calculation():
    # G = K / (s (s + 1)(s + 2)): the phase crossover is at w = sqrt(2), where |G| = K/6, so the gain margin is 6/K
    for k, gm in ((2, 3.0), (10, 0.6)):
        ln = last(f"G(s) = {k}/(s*(s + 1)*(s + 2))", "plot nyquist G(i*w) for w from 0.05 to 20")
        gain = next(n for n in ln["notes"] if n.startswith("Gain margin"))
        assert f"{gm:g} " in gain and "at w = 1.414" in gain
        assert ln["plot"]["marks"] == [{"x": -1.0, "y": 0.0, "label": "−1"}]
    ok = last("G(s) = 2/(s*(s + 1)*(s + 2))", "plot nyquist G(i*w) for w from 0.05 to 20")["notes"]
    # phase margin: at the unit-gain frequency w, 180 - 90 - atan(w) - atan(w/2)
    from scipy.optimize import brentq

    w = brentq(lambda x: 2 / (x * np.hypot(1, x) * np.hypot(2, x)) - 1, 0.1, 5)
    pm = 90 - np.degrees(np.arctan(w)) - np.degrees(np.arctan(w / 2))
    assert any(n.startswith("Phase margin") and f"{pm:.4g}" in n for n in ok)
    assert "unstable" in last("G(s) = 10/(s*(s + 1)*(s + 2))", "plot nyquist G(i*w) for w from 0.05 to 20")["notes"][0]
    assert last("G(s) = 1/(1 + s)", "plot nyquist G(i*w)")["notes"] == []                  # never crosses the negative real axis: no margin to report
    assert last("Z(s) = 5 m/(1 + s)", "plot nyquist Z(i*w)")["plot"].get("marks") is None   # a value with a unit has no critical point


def test_matrix_functions_apply_to_each_layer_of_a_3d_list():
    pre = "B = [[[1, 2], [3, 4]], [[2, 0], [0, 5]]]"
    assert np.allclose(arr(last(pre, "det(B)")), [-2, 10]) and arr(last(pre, "trace(B)")).tolist() == [5, 7] and arr(last(pre, "rank(B)")).tolist() == [2, 2]
    assert np.allclose(arr(last(pre, "inv(B)")), np.linalg.inv(np.array([[[1, 2], [3, 4]], [[2, 0], [0, 5]]], dtype=float)))
    assert arr(last(pre, "transpose(B)")).tolist() == [[[1, 3], [2, 4]], [[2, 0], [0, 5]]]
    assert np.allclose(arr(last(pre, "eigvals(B)"))[1], [2, 5])
    assert last("det([[1 m, 2 m], [3 m, 4 m]])")["unit"] == "m^2" and last(pre, "det(B*1 m)")["unit"] == "m^2"
    assert last("det([[1, 2], [3, 4]])")["value"] == pytest.approx(-2)                                  # a matrix still gives one number
