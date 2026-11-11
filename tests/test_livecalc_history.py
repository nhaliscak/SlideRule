"""LiveCalc history: the larger limits and the Markdown / text export."""

import pytest

from sliderule import api
from sliderule.livecalc import MAX_ENTRIES, livecalc_eval, livecalc_export


def test_two_hundred_entries_are_evaluated_and_more_are_refused():
    ents = [f"x{i} = {i} m + 30 cm" for i in range(MAX_ENTRIES)]
    out = livecalc_eval(entries=ents, draft="x5 + x199")
    assert len(out["entries"]) == MAX_ENTRIES and out["draft"]["lines"][0]["value_text"] == "204.6"
    with pytest.raises(api.ApiError):
        livecalc_eval(entries=[*ents, "y = 1"], draft="")
    assert api.handle("livecalc_eval", {"entries": [f"a{i} = {i}" for i in range(MAX_ENTRIES + 1)], "draft": ""})["ok"] is False


def test_markdown_export_has_text_equations_results_and_marks_errors():
    entries = ["# Beam check\nSpan 6 m, load in kN/m", "m = 80 kg\na = 9.81 m/s^2\nF = m*a", "plot sin(x) from 0 to 1", "5 m + 3 s"]
    r = livecalc_export(entries, "markdown", title="My notes")
    doc = r["content"]
    assert r["filename"].endswith(".md") and doc.startswith("# My notes\n")
    assert "# Beam check" in doc and "$$ F = m \\cdot a = 784.8\\,\\mathrm{N} $$" in doc
    assert "`plot sin(x) from 0 to 1` (a graph" in doc and "`5 m + 3 s` — **Cannot add length (m) and time (s)**" in doc
    assert "\n\n\n" not in doc


def test_text_export_round_trips_through_the_importer():
    entries = ["a = 1 m", "b = 2 m\nc = a + b", "f(x) = x^2"]
    r = livecalc_export(entries, "text")
    assert r["content"] == "a = 1 m\n\nb = 2 m\nc = a + b\n\nf(x) = x^2\n"
    back = [e.strip() for e in r["content"].split("\n\n") if e.strip()]            # what the front end does when it imports a .txt file
    assert back == entries


def test_export_through_the_rpc_and_unknown_formats():
    ok = api.handle("livecalc_export", {"entries": ["a = 2"], "fmt": "markdown"})
    assert ok["ok"] and "$$ a = 2 $$" in ok["result"]["content"]
    assert api.handle("livecalc_export", {"entries": ["a = 2"], "fmt": "docx"})["ok"] is False
    assert livecalc_export([], "text")["content"] == ""


# ---------------------------------------------------------------- plots: logarithmic axes and parametric curves

def _plot(line, *before):
    from sliderule.livecalc import Session

    s = Session(6)
    for i, b in enumerate(before):
        s.run_line(b, i + 1)
    return s.run_line(line, len(before) + 1)


def test_log_axes_sample_geometrically_and_drop_non_positive_values():
    r = _plot("plot x^2, x^3 from 1 to 1000 loglog")
    p = r["plot"]
    assert r["kind"] == "plot" and p["logx"] and p["logy"]
    ratios = [p["x"][i + 1] / p["x"][i] for i in range(len(p["x"]) - 1)]
    assert max(ratios) - min(ratios) < 1e-4 and p["x"][0] == 1 and p["x"][-1] == pytest.approx(1000)       # equal steps in log x
    assert p["series"][1]["y"][-1] == pytest.approx(1e9, rel=1e-5)
    r = _plot("plot sin(x) from 1 to 10 logy")
    ys = r["plot"]["series"][0]["y"]
    assert any(v is None for v in ys) and all(v is None or v > 0 for v in ys) and r["plot"]["logy"] and not r["plot"]["logx"]
    assert not _plot("plot x from 1 to 10")["plot"]["logx"]


def test_log_axis_errors():
    assert "above zero" in _plot("plot x from 0 to 10 logx")["error"]["message"]
    assert "positive values" in _plot("plot -x^2 - 1 from 1 to 10 logy")["error"]["message"]
    assert _plot("plot x from 1 to 10 logx")["kind"] == "plot"
    assert "logx" not in str(_plot("plot x from 1 to 10 logx")["display_latex"])


def test_parametric_plot_draws_one_curve_with_units():
    import math

    r = _plot("plot parametric 2 m*cos(t), 3 m*sin(t) for t from 0 to 2*pi")
    p = r["plot"]
    assert r["kind"] == "plot" and p["param"] == "t" and p["x_unit"] == "m" and p["y_unit"] == "m" and len(p["series"]) == 1
    for x, y in zip(p["x"], p["series"][0]["y"]):
        assert (x / 2) ** 2 + (y / 3) ** 2 == pytest.approx(1, abs=1e-5)                                       # an ellipse
    assert max(p["x"]) == pytest.approx(2, abs=1e-3) and max(p["series"][0]["y"]) == pytest.approx(3, abs=1e-3) and math.isfinite(sum(p["x"]))
    assert "two expressions" in _plot("plot parametric t for t from 0 to 1")["error"]["message"]
    assert "two expressions" in _plot("plot parametric t, t^2, t^3 for t from 0 to 1")["error"]["message"]
    assert _plot("plot parametric t, t^2 for t from 0 to 1", "parametric = 3")["kind"] == "error"            # a variable of that name: parsed as an ordinary plot
