"""LiveCalc: complex numbers (3 + 4i, phasors, impedances) and what happens when a function cannot take them."""

import cmath
import math

import numpy as np
import pytest

from sliderule.livecalc import Session


def run(*lines):
    s = Session(6)
    out = [s.run_line(ln, i + 1) for i, ln in enumerate(lines)]
    return out[-1]


def z_of(r):
    assert r["kind"] in ("value", "assign"), r
    if r.get("is_list"):
        return np.array(r["value"]) + 1j * np.array(r.get("value_im", [0.0] * len(r["value"])))
    return complex(r["value"], r.get("value_im", 0.0))


def err(*lines):
    r = run(*lines)
    assert r["kind"] == "error", r
    return r["error"]["message"]


def test_literals_arithmetic_and_display():
    r = run("3 + 4i")
    assert r["complex"] and z_of(r) == 3 + 4j and r["value_text"] == "3 + 4i" and "Polar form: 5 ∠ 53.1301°" in r["notes"]
    assert z_of(run("3 + 4j")) == 3 + 4j and z_of(run("2j")) == 2j and z_of(run("z = 1 + 2i", "z*z")) == (1 + 2j) ** 2
    assert z_of(run("(3 + 4i)/(1 - 2i)")) == pytest.approx((3 + 4j) / (1 - 2j)) and z_of(run("(1+2i)^2")) == (-3 + 4j) and z_of(run("-i")) == -1j
    assert run("(1+2i)*(1-2i)")["value"] == 5 and not run("(1+2i)*(1-2i)").get("complex")             # a product that comes out exactly real is a real number again
    assert run("(2i)^2")["value"] == -4 and run("max((1+2i)*(1-2i), 1)")["value"] == 5
    assert run("[1+2i, 3-1i]")["value_text"] == "[1 + 2i, 3 - i]" and run("3i")["value_text"] == "3i" and run("-2i")["value_text"] == "-2i"
    assert "exp(" not in run("exp(i*pi)")["value_text"] and run("exp(i*pi)")["value"] == -1 and run("exp(i*pi)")["value_text"] == "-1"       # rounding noise in the imaginary part is dropped


def test_i_and_j_are_variables_when_you_define_them():
    assert run("i = 3", "i*2")["value"] == 6 and run("j = 4 A", "j*2")["unit"] == "A"
    assert z_of(run("2 + 3j")) == 2 + 3j and run("2 m")["unit"] == "m"            # units are not confused with the imaginary unit


def test_functions_of_complex_numbers_match_cmath():
    for text, f in (("sqrt(-4 + 0i)", lambda: cmath.sqrt(-4)), ("exp(1 + 2i)", lambda: cmath.exp(1 + 2j)), ("ln(1 + 1i)", lambda: cmath.log(1 + 1j)), ("sin(1 + 1i)", lambda: cmath.sin(1 + 1j)),
                    ("cos(1 + 1i)", lambda: cmath.cos(1 + 1j)), ("tanh(0.5 + 0.2i)", lambda: cmath.tanh(0.5 + 0.2j))):
        assert z_of(run(text)) == pytest.approx(f(), rel=1e-5), text
    assert run("abs(3 + 4i)")["value"] == 5 and run("real(3 + 4i)")["value"] == 3 and run("imag(3 + 4i)")["value"] == 4 and z_of(run("conj(3 + 4i)")) == 3 - 4j
    r = run("arg(3 + 4i) to deg")
    assert r["value"] == pytest.approx(math.degrees(math.atan2(4, 3))) and r["unit"] == "deg"
    assert z_of(run("polar(5, 53.13010235 deg)")) == pytest.approx(3 + 4j, rel=1e-6) and z_of(run("polar(2 V, 90 deg)")) == pytest.approx(2j, abs=1e-12)
    assert z_of(run("(1+1i)^(1+1i)")) == pytest.approx((1 + 1j) ** (1 + 1j), rel=1e-6)
    assert "not real" in err("sqrt(-4)")                                                    # real input keeps its error


def test_units_with_complex_numbers_ac_circuit():
    # a series RLC branch at 50 Hz: R = 10 ohm, L = 0.1 H, C = 100 uF
    r = run("Z = 10 ohm + 1j*2*pi*50 Hz*0.1 H + 1/(1j*2*pi*50 Hz*100 uF)", "Z to ohm")
    w = 2 * math.pi * 50
    want = 10 + 1j * w * 0.1 + 1 / (1j * w * 100e-6)
    assert z_of(r) == pytest.approx(want, rel=1e-6) and r["unit"] == "ohm"
    mag = run("Z = 10 ohm + 5j ohm", "abs(Z)")
    assert mag["value"] == pytest.approx(math.hypot(10, 5)) and mag["unit"] == "ohm"
    v = run("Z = 10 ohm + 5j ohm", "I = 2 A", "V = Z*I to V")
    assert z_of(v) == pytest.approx(20 + 10j) and v["unit"] == "V" and "Polar form: 22.3607 V ∠ 26.5651°" in v["notes"]
    assert run("Z = 10 ohm + 5j ohm", "Z to kohm")["value_text"] == "(0.01 + 0.005i)" or z_of(run("Z = 10 ohm + 5j ohm", "Z to kohm")) == pytest.approx(0.01 + 0.005j)
    assert "offset" in err("(1+1i)*20 degC + 5 degC")


def test_complex_lists_and_matrices_nodal_analysis():
    assert z_of(run("sum([1+2i, 3-1i])")) == 4 + 1j and z_of(run("mean([1+1i, 3+3i])")) == 2 + 2j and z_of(run("w = [1+1i, 2]", "w[1]")) == 1 + 1j
    A = np.array([[2 + 1j, 1], [1, 3]])
    b = np.array([1, 1j])
    text = "[[2+1i, 1], [1, 3]]"
    assert z_of(run(f"A = {text}", "b = [1, 1i]", "solve(A, b)")) == pytest.approx(np.linalg.solve(A, b), rel=1e-6)
    assert z_of(run(f"A = {text}", "det(A)")) == pytest.approx(np.linalg.det(A), rel=1e-6)
    assert z_of(run(f"A = {text}", "inv(A)")) == pytest.approx(np.linalg.inv(A), rel=1e-5)
    assert z_of(run(f"matmul({text}, [1, 1i])")) == pytest.approx(A @ np.array([1, 1j]))
    # a two-node network: admittances in siemens, injected currents in amperes
    r = run("Y = [[0.2 - 0.1i, -0.1 + 0.05i], [-0.1 + 0.05i, 0.3 - 0.2i]] S", "I = [1, 0] A", "solve(Y, I)")
    Y = np.array([[0.2 - 0.1j, -0.1 + 0.05j], [-0.1 + 0.05j, 0.3 - 0.2j]])
    assert z_of(r) == pytest.approx(np.linalg.solve(Y, [1, 0]), rel=1e-6) and r["unit"] == "A/S"
    ev = z_of(run("eigvals([[0, 1], [-1, 0]])"))
    assert sorted(ev.imag) == pytest.approx([-1, 1]) and np.allclose(ev.real, 0)
    assert z_of(run("eigvals([[1, 2], [3, 4]])")).imag.tolist() == [0, 0]


def test_functions_that_cannot_take_complex_numbers_say_so():
    for text in ("max(1+2i, 3)", "min([1+1i, 2])", "median([1+1i, 2])", "sort([1+1i, 2])", "floor(1.5 + 1i)", "factorial(1+1i)", "mod(1+1i, 2)", "cbrt(1+1i)", "stdev([1+1i, 2])"):
        assert "complex" in err(text), text
    assert "real numbers" in err("plot exp(j*x) from 0 to 1") and "real numbers" in err("plot data [1+1i, 2], [1, 2]")
    assert "complex" in err('calc("turbine_power", "Pe", rho = 1.2 kg/m^3, Dr = 100 m, v = (1+2i) m/s, Cp = 0.4, eg = 0.9)')
    assert "offset" in err("(1+1i)*1 K + 20 degC") or "temperature" in err("(1+1i)*1 K + 20 degC")


def test_frequency_response_can_be_plotted_through_abs_and_arg():
    s = Session(6)
    s.run_line("f(w) = 1/(1 + 1j*w)", 1)
    assert "is a function" in s.run_line("plot abs(f) from 0 to 5", 2)["error"]["message"]           # f alone would silently be taken as the plot variable
    r = s.run_line("plot abs(f(x)), arg(f(x)) from 0 to 5", 3)
    assert r["kind"] == "plot"
    gain = r["plot"]["series"][0]["y"]
    x = r["plot"]["x"]
    assert gain[-1] == pytest.approx(1 / math.sqrt(1 + x[-1] ** 2), rel=1e-5) and gain[0] == pytest.approx(1)
