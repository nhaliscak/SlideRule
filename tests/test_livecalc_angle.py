"""LiveCalc: the radians / degrees switch."""

import math

import pytest

from sliderule import api
from sliderule.livecalc import Session, livecalc_eval, livecalc_export, livecalc_plot, livecalc_to_equation


def run(mode, *lines):
    s = Session(8, mode)
    out = [s.run_line(ln, i + 1) for i, ln in enumerate(lines)]
    return out[-1]


def test_radians_is_the_default_and_unchanged():
    assert run("rad", "sin(30)")["value"] == pytest.approx(math.sin(30)) and run("rad", "asin(0.5)")["value"] == pytest.approx(math.asin(0.5)) and run("rad", "asin(0.5)")["unit"] == ""
    assert Session(6).run_line("sin(30)", 1)["value"] == pytest.approx(math.sin(30))


def test_degree_mode_reads_bare_numbers_as_degrees_and_answers_in_degrees():
    for text, want in (("sin(30)", 0.5), ("cos(60)", 0.5), ("tan(45)", 1.0), ("sin(90)", 1.0)):
        assert run("deg", text)["value"] == pytest.approx(want), text
    for text, want in (("asin(0.5)", 30), ("acos(0.5)", 60), ("atan(1)", 45), ("atan2(1, 1)", 45), ("atan2(-1, -1)", -135), ("arg(1+1i)", 45)):
        r = run("deg", text)
        assert r["value"] == pytest.approx(want) and r["unit"] == "deg", text
    assert run("deg", "polar(2, 90)")["value_text"] == "2i"                                     # a bare angle in polar() is degrees too


def test_angles_with_a_unit_are_never_changed_by_the_mode():
    for mode in ("rad", "deg"):
        assert run(mode, "sin(30 deg)")["value"] == pytest.approx(0.5)
        assert run(mode, "sin(0.5235987756 rad)")["value"] == pytest.approx(0.5)
        assert run(mode, "x = 90 deg", "cos(x)")["value"] == pytest.approx(0, abs=1e-12)
        assert run(mode, "asin(1) to deg")["value"] == pytest.approx(90) and run(mode, "asin(1) to rad")["value"] == pytest.approx(math.pi / 2)
    assert run("deg", "sin(pi/6)")["value"] == pytest.approx(math.sin(math.radians(math.pi / 6)))   # a number is a number: pi/6 degrees is a tiny angle


def test_degree_mode_in_user_functions_lists_and_plots():
    s = Session(6, "deg")
    s.run_line("f(x) = sin(x)", 1)
    assert s.run_line("f(30)", 2)["value"] == pytest.approx(0.5)
    assert s.run_line("sin([0, 30, 90])", 3)["value"] == pytest.approx([0, 0.5, 1])
    r = livecalc_plot(entries=["f(x) = sin(x)"], functions=["f"], x=["0", "360"], angle="deg")
    ys = r["curves"][0]["series"][0]["y"]
    xs = r["curves"][0]["x"]
    assert max(ys) == pytest.approx(1, abs=1e-3) and min(ys) == pytest.approx(-1, abs=1e-3) and xs[-1] == pytest.approx(360)      # one full period over 0 to 360
    r = livecalc_plot(entries=["f(x) = sin(x)"], functions=["f"], x=["0", "360"])                # radians: 360 rad is 57 periods
    assert len(r["curves"][0]["x"]) == len(xs)


def test_the_mode_reaches_every_entry_point():
    out = livecalc_eval(entries=["asin(1)"], draft="cos(0)", angle="deg")
    assert out["entries"][0]["lines"][0]["unit"] == "deg" and out["entries"][0]["lines"][0]["value"] == pytest.approx(90)
    via = api.handle("livecalc_eval", {"entries": ["asin(1)"], "draft": "", "angle": "deg"})["result"]
    assert via["entries"][0]["lines"][0]["value"] == pytest.approx(90)
    assert "degrees" in livecalc_export(["sin(30)"], "markdown", angle="deg")["content"] and "0.5" in livecalc_export(["sin(30)"], "markdown", angle="deg")["content"]
    assert "degrees" not in livecalc_export(["sin(30)"], "markdown")["content"]
    d = livecalc_to_equation("y = sin(a)", entries=["a = 30 deg"], angle="deg")
    assert any("degree mode" in w for w in d["warnings"]) and not any("degree mode" in w for w in livecalc_to_equation("y = sin(a)", entries=["a = 30 deg"])["warnings"])
    assert not any("degree mode" in w for w in livecalc_to_equation("y = a*b", entries=["a = 2", "b = 3"], angle="deg")["warnings"])        # only equations with angle functions are flagged


def test_junk_values_for_the_mode_mean_radians():
    assert run("degrees!", "sin(30)")["value"] == pytest.approx(math.sin(30))
