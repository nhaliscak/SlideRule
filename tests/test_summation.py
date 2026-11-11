import math

import pytest

from sliderule.core import Calculation, V, solve
from sliderule.core.model import _FUNCS
from sliderule.core.safeparse import UnsafeExpression, check_expression


def out(sol, key):
    return next(o["si_value"] for o in sol.to_dict()["outputs"] if o["key"] == key)


# slab, uniform initial temperature, both faces held: theta(x, t) = sum_{k} 4/((2k-1) pi) sin((2k-1) pi x/L) exp(-(2k-1)^2 pi^2 a t / L^2)
SLAB = [V("T", "Temperature", "K"), V("Ts", "Surface temperature", "K"), V("Ti", "Initial temperature", "K"), V("x", "Position", "m"), V("L", "Thickness", "m"),
        V("a", "Diffusivity", "m^2/s"), V("t", "Time", "s")]
SLAB_EQ = "T = Ts + (Ti - Ts)*summation(4/((2*k - 1)*pi)*sin((2*k - 1)*pi*x/L)*exp(-(2*k - 1)**2*pi**2*a*t/L**2), (k, 1, 80))"
SLAB_IN = {"Ts": "300 K", "Ti": "500 K", "x": "0.05 m", "L": "0.1 m", "a": "1e-5 m^2/s", "t": "100 s"}


def slab():
    return Calculation(id="custom.slab", name="s", disciplines=["mechanical"], description="", variables=list(SLAB), equations=[("series", SLAB_EQ)], outputs=["T"], custom=True)


def reference(x=0.05, L=0.1, a=1e-5, t=100.0):
    return sum(4 / ((2 * k - 1) * math.pi) * math.sin((2 * k - 1) * math.pi * x / L) * math.exp(-((2 * k - 1) ** 2) * math.pi ** 2 * a * t / L ** 2) for k in range(1, 81))


def test_a_series_evaluates_term_by_term_and_is_unit_checked():
    c = slab()
    assert out(solve(c, SLAB_IN), "T") == pytest.approx(300 + 200 * reference(), rel=1e-12)
    d = solve(c, SLAB_IN).to_dict()
    assert "\\sum" in str(d["steps"])                                                         # the sum is shown as written, not as eighty terms
    assert len(str(d["steps"])) < 20000


def test_any_other_quantity_is_found_by_root_finding():
    c = slab()
    T = 300 + 200 * reference()
    back = solve(c, {**{k: v for k, v in SLAB_IN.items() if k != "t"}, "T": f"{T} K"}, ["t"]).to_dict()
    assert back["ok"] and back["outputs"][0]["si_value"] == pytest.approx(100.0, rel=1e-6)
    assert "NUMERIC_INVERSION" in [x["code"] for x in back["diagnostics"]]
    # a quantity outside the sum is rearranged symbolically
    d = solve(c, {k: v for k, v in SLAB_IN.items() if k != "Ti"} | {"T": f"{T} K"}, ["Ti"]).to_dict()
    assert d["ok"] and d["outputs"][0]["si_value"] == pytest.approx(500.0, rel=1e-9)


def test_dimensions_inside_the_sum_are_checked():
    bad = SLAB_EQ.replace("exp(-(2*k - 1)**2*pi**2*a*t/L**2)", "exp(-(2*k - 1)**2*pi**2*a*t/L)")
    with pytest.raises(ValueError, match="dimension"):
        Calculation(id="custom.bad", name="s", disciplines=["mechanical"], description="", variables=list(SLAB), equations=[("series", bad)], outputs=["T"], custom=True)


def test_the_syntax_is_restricted():
    names = {**_FUNCS, "x": 1}
    for text in ("summation(n*x, (n, 1, 50))", "summation(n, (n, -3, 3))"):
        check_expression(text, names)
    for text, msg in (("summation(x, (n, 1, 1000))", "at most 500"), ("summation(x, (n, 1, x))", "whole-number literals"), ("summation(x, (n, 5, 1))", "last >= first"),
                      ("summation(x)", "is written summation"), ("summation(x, (n, 1, 3), (m, 1, 3))", "is written summation")):
        with pytest.raises(UnsafeExpression, match=msg):
            check_expression(text, names)


def test_large_arguments_fall_back_to_arbitrary_precision():
    # sinh of a huge argument overflows a float but not SymPy's number type
    v = [V("u", "u", "1"), V("b", "b", "1")]
    c = Calculation(id="custom.big", name="s", disciplines=["mechanical"], description="", variables=v, outputs=["u"], custom=True,
                    equations=[("e", "u = summation(sinh(n*b)/sinh(n*b + 1), (n, 1, 20))")])
    assert out(solve(c, {"b": "1000"}), "u") == pytest.approx(sum(math.exp(-1) for _ in range(20)), rel=1e-9)


def test_exports_and_round_trip():
    from sliderule.core.custom import calc_from_dict, calc_to_dict

    c = slab()
    again = calc_from_dict(calc_to_dict(c))
    assert out(solve(again, SLAB_IN), "T") == pytest.approx(out(solve(c, SLAB_IN), "T"))


def test_library_series_calculations_match_independent_references():
    from sliderule.core.catalog import default_catalog

    cat = default_catalog()

    def run(cid, key, inputs):
        return out(solve(cat.get(cid), inputs), key)

    assert run("mechanical.heat.slab_transient_conduction_series", "T", {"Ts": "300 K", "Ti": "500 K", "x": "50 mm", "L": "100 mm", "a": "10 mm^2/s", "t": "100 s"}) == pytest.approx(300 + 200 * reference(), rel=1e-12)
    # t -> large: the slab reaches the face temperature; the series at t = 0.1 L^2/a (Fo = 0.1) has the known centre value 1 - ... compare with a 200-term sum
    x, L, h, T, mu, tt = 0.3, 0.65, 3e-3, 70.0, 0.4e-3, 0.7e-3
    c = math.sqrt(T / mu)
    y = h * sum(8 / (n * n * math.pi ** 2) * math.sin(n * math.pi / 2) * math.sin(n * math.pi * x / L) * math.cos(n * math.pi * c * tt / L) for n in range(1, 61))
    assert run("mechanical.acoustics.plucked_string_displacement_series", "y", {"h": "3 mm", "x": "0.3 m", "L": "0.65 m", "Tn": "70 N", "mu": "0.4 g/m", "t": "0.7 ms"}) == pytest.approx(y, rel=1e-12)
    at_zero = run("mechanical.acoustics.plucked_string_displacement_series", "y", {"h": "3 mm", "x": "0.325 m", "L": "0.65 m", "Tn": "70 N", "mu": "0.4 g/m", "t": "0 ms"})
    assert at_zero == pytest.approx(3e-3, rel=1e-2)                                         # at t = 0 the pluck point is at its full height
    u = sum(4 / ((2 * k - 1) * math.pi) * math.sin((2 * k - 1) * math.pi * 0.5) * math.sinh((2 * k - 1) * math.pi * 0.8) / math.sinh((2 * k - 1) * math.pi) for k in range(1, 61))
    assert run("mechanical.heat.rectangular_plate_steady_series", "T", {"Tr": "300 K", "dT": "100 K", "x": "50 mm", "y": "80 mm", "a": "100 mm", "b": "100 mm"}) == pytest.approx(300 + 100 * u, rel=1e-12)
    assert run("mechanical.heat.rectangular_plate_steady_series", "T", {"Tr": "300 K", "dT": "100 K", "x": "50 mm", "y": "100 mm", "a": "100 mm", "b": "100 mm"}) == pytest.approx(400, abs=1.0)   # on the hot edge
    w = 2 * math.pi * 1000 * 0.1e-3
    assert run("electrical.signal.square_wave_fourier_partial_sum", "v", {"Vp": "5 V", "f": "1 kHz", "t": "0.1 ms"}) == pytest.approx(4 * 5 / math.pi * sum(math.sin((2 * k - 1) * w) / (2 * k - 1) for k in range(1, 21)), rel=1e-12)
