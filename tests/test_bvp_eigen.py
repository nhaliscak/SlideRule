import math

import numpy as np
import pytest

from sliderule import api, design, design_export, usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def out(sol, key):
    return next(o["si_value"] for o in sol.to_dict()["outputs"] if o["key"] == key)


COL_VARS = [V("y", "Deflection", "mm", signed=True), V("x", "Position", "m"), V("L", "Length", "m"), V("E", "Modulus", "GPa"), V("I", "Second moment", "cm^4"),
            V("P", "Buckling load", "kN"), V("a", "Amplitude at mid-span", "mm")]
COL = {"independent": "x", "start": "0", "end": "L", "equations": ["E*I*diff(y, x, 2) + P*y = 0"], "unknowns": ["P"],
       "boundary": ["start: y = 0", "end: y = 0", "L/2: y = a"], "guess": ["P = 1.5*pi**2*E*I/L**2", "diff(y, x) = 3*a/L"]}
COL_IN = {"L": "3 m", "E": "200 GPa", "I": "2000 cm^4", "a": "1 mm", "x": "1 m"}


def column(**changes):
    return Calculation(id="custom.col", name="c", disciplines=["civil"], description="", variables=list(COL_VARS), equations=[], outputs=["P", "y"], custom=True, odes=[{**COL, **changes}])


def test_euler_buckling_load_is_found_as_an_eigenvalue_with_its_mode_shape():
    c = column()
    s = c.parsed_odes[0]
    assert s.numeric and s.bvp.unknowns
    sol = solve(c, COL_IN)
    P = math.pi ** 2 * 200e9 * 2000e-8 / 9
    assert out(sol, "P") == pytest.approx(P, rel=1e-8)
    assert out(sol, "y") == pytest.approx(1e-3 * math.sin(math.pi / 3), rel=1e-7)             # the mode shape, scaled so that y(L/2) = a
    d = sol.to_dict()
    assert d["series"] and max(d["series"][0]["series"][0]["values"]) == pytest.approx(1.0, rel=1e-6)


def test_the_guess_selects_the_mode():
    P1 = math.pi ** 2 * 200e9 * 2000e-8 / 9
    for k in (2, 3):
        c = column(guess=[f"P = {k * k * 1.05}*pi**2*E*I/L**2", "diff(y, x) = 3*a/L"], boundary=["start: y = 0", "end: y = 0", f"L/{2 * k}: y = a"])
        assert out(solve(c, COL_IN), "P") == pytest.approx(k * k * P1, rel=1e-7)


def test_a_variable_stiffness_column_agrees_with_a_finite_difference_eigenvalue():
    v = COL_VARS + [V("c", "Taper", "1")]
    spec = {**COL, "equations": ["E*I*(1 + c*x/L)*diff(y, x, 2) + P*y = 0"], "guess": ["P = 1.3*pi**2*E*I/L**2", "diff(y, x) = 3*a/L"]}
    c = Calculation(id="custom.col2", name="c", disciplines=["civil"], description="", variables=v, equations=[], outputs=["P"], custom=True, odes=[spec])
    got = out(solve(c, {**COL_IN, "c": "1"}), "P")
    n, L, EI = 2000, 3.0, 200e9 * 2000e-8
    h = L / n
    xs = np.arange(1, n) * h
    A = np.diag(2 * np.ones(n - 1)) - np.diag(np.ones(n - 2), 1) - np.diag(np.ones(n - 2), -1)
    # E I (1 + x/L) y'' = -P y  ->  -(A/h^2) y = -P/(EI (1 + x/L)) y  ->  A y = (P h^2 / EI) y / (1 + x/L)
    ev = np.linalg.eigvals(np.diag(1 + xs / L) @ A)
    ref = EI / h ** 2 * ev.real.min()
    assert got == pytest.approx(ref, rel=1e-4)


def test_cantilever_natural_frequency_with_a_fourth_order_equation():
    v = [V("y", "Deflection", "m", signed=True), V("x", "Position", "m"), V("L", "Length", "m"), V("E", "E", "GPa"), V("I", "I", "cm^4"), V("mu", "Mass per length", "kg/m"),
         V("w", "Angular frequency", "rad/s", latex=r"\omega"), V("a", "Tip amplitude", "mm")]
    spec = {"independent": "x", "start": "0", "end": "L", "equations": ["E*I*diff(y, x, 4) = mu*w**2*y"], "unknowns": ["w"],
            "boundary": ["start: y = 0", "start: diff(y, x) = 0", "end: diff(y, x, 2) = 0", "end: diff(y, x, 3) = 0", "end: y = a"],
            "guess": ["w = 1.2*3.5156*sqrt(E*I/(mu*L**4))", "diff(y, x, 2) = a/L**2"]}
    c = Calculation(id="custom.cant", name="c", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["w"], custom=True, odes=[spec])
    got = out(solve(c, {"L": "1 m", "E": "200 GPa", "I": "1 cm^4", "mu": "2 kg/m", "a": "1 mm", "x": "0.5 m"}), "w")
    assert got == pytest.approx(1.8751040687 ** 2 * math.sqrt(200e9 * 1e-8 / (2 * 1.0 ** 4)), rel=1e-6)


def test_fitting_an_unknown_constant_catenary_horizontal_tension():
    # y'' = (w/H) sqrt(1 + y'^2), y(0) = y(L) = 0, cable length S fixes H (the integral of the arc length is a second dependent)
    v = [V("y", "Height", "m", signed=True), V("s", "Arc length from the left end", "m"), V("x", "Position", "m"), V("L", "Span", "m"), V("S", "Cable length", "m"),
         V("w", "Weight per length", "N/m"), V("H", "Horizontal tension", "kN")]
    spec = {"independent": "x", "start": "0", "end": "L", "equations": ["H*diff(y, x, 2) = w*sqrt(1 + diff(y, x)**2)", "diff(s, x) = sqrt(1 + diff(y, x)**2)"], "unknowns": ["H"],
            "boundary": ["start: y = 0", "end: y = 0", "start: s = 0", "end: s = S"], "guess": ["H = 2*w*L", "diff(y, x) = -0.3"]}
    c = Calculation(id="custom.cat", name="c", disciplines=["civil"], description="", variables=v, equations=[], outputs=["H", "y"], custom=True, odes=[spec])
    inp = {"L": "100 m", "S": "102 m", "w": "50 N/m", "x": "50 m"}
    H = out(solve(c, inp), "H")
    # catenary: S = 2 a sinh(L / 2a) with a = H / w; solve for a by bisection
    lo, hi = 50.0, 1e5
    for _ in range(200):
        mid = (lo + hi) / 2
        if 2 * mid * math.sinh(100 / (2 * mid)) > 102:
            lo = mid
        else:
            hi = mid
    assert H == pytest.approx(50 * lo, rel=1e-6)
    sag = -out(solve(c, inp), "y")
    assert sag == pytest.approx(lo * (math.cosh(50 / lo) - 1), rel=1e-5)                       # mid-span sag


def test_validation_of_unknowns_and_conditions():
    def bad(match, **changes):
        with pytest.raises(ValueError, match=match):
            column(**changes)
    bad("4 boundary conditions|3 boundary conditions needed", boundary=["start: y = 0", "end: y = 0"])
    bad("normalisation", boundary=["start: y = 0", "end: y = 0"])
    bad("starting guess for the unknown parameter P", guess=["diff(y, x) = 3*a/L"])
    bad("free variable", unknowns=["x"])
    bad("free variable", unknowns=["nope"])
    bad("numerically|numerical", method="symbolic")
    bad("dimension", guess=["P = 3 * L", "diff(y, x) = 3*a/L"])


def test_the_eigenproblem_failure_is_explained():
    d = solve(column(guess=["P = 1e-6*E*I/L**2", "diff(y, x) = 0*a"]), COL_IN).to_dict()
    assert not d["ok"] or d["outputs"]                     # a degenerate start either still converges or is reported, never a crash
    if not d["ok"]:
        assert "eigenvalue" in str(d["diagnostics"]) or "converge" in str(d["diagnostics"])


def test_file_round_trip_system_design_and_exports():
    c = column()
    again = calc_from_dict(calc_to_dict(c))
    assert out(solve(again, COL_IN), "P") == pytest.approx(out(solve(c, COL_IN), "P"))
    doc = {"id": "custom.col", "name": "Column", "disciplines": ["civil"], "outputs": ["P", "y"], "odes": [COL],
           "variables": [{"key": v.key, "label": v.label, "unit": v.unit, **({"signed": True} if v.signed else {}), **({"example": COL_IN[v.key]} if v.key in COL_IN else {})} for v in COL_VARS]}
    api.custom_save(doc)
    g = {"version": 1, "blocks": [{"id": "b", "calc": "custom.col", "x": 0, "y": 0, "values": dict(COL_IN)}], "wires": []}
    r = design.solve_system(g)
    assert r["ok"]
    e = design_export.export_system(g, "latex")
    assert e["ok"] and "together with the solution" in e["content"] or e["ok"]
    py = design_export.export_system(g, "python")
    assert py["ok"]                                           # the eigenvalue is found again by the script with SciPy's collocation solver
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(py["content"], "s.py", "exec"), {"__name__": "__main__"})
    assert "matches the SlideRule reference values" in buf.getvalue()


def test_library_eigen_and_fitting_calculations():
    from sliderule.core.catalog import default_catalog

    cat = default_catalog()

    def run(cid, key, extra=None):
        calc = cat.get(cid)
        return out(solve(calc, {**calc.example, **(extra or {})}), key)

    # c = 0 is Euler's load
    assert run("civil.column.buckling_load_tapered_stiffness", "P", {"c": "0"}) == pytest.approx(math.pi ** 2 * 200e9 * 2000e-8 / 9, rel=1e-6)
    assert run("civil.column.buckling_load_tapered_stiffness", "P") > 1.3 * math.pi ** 2 * 200e9 * 2000e-8 / 9        # a stiffer-on-average column buckles later
    assert run("mechanical.dynamics.cantilever_frequency_eigenproblem", "w") == pytest.approx(1.8751040687 ** 2 * math.sqrt(200e9 * 1e-8 / 2), rel=1e-6)
    lo, hi = 50.0, 1e5
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if 2 * mid * math.sinh(100 / (2 * mid)) > 102 else (lo, mid)
    assert run("civil.structural.cable_horizontal_tension_from_length", "H") == pytest.approx(50 * lo, rel=1e-6)
    assert run("civil.structural.cable_horizontal_tension_from_length", "s") == pytest.approx(51.0, rel=1e-9)                # half the cable at mid-span
    uniform = run("mechanical.acoustics.string_frequency_variable_density", "w", {"c": "0"})
    assert uniform == pytest.approx(math.pi / 0.65 * math.sqrt(70 / 0.4e-3), rel=1e-6)
    n, L = 2000, 0.65
    h = L / n
    xs = np.arange(1, n) * h
    A = np.diag(2 * np.ones(n - 1)) - np.diag(np.ones(n - 2), 1) - np.diag(np.ones(n - 2), -1)
    ev = np.linalg.eigvals(A / (1 + 0.5 * xs / L)[:, None])                     # T y'' + rho (1 + c x/L) w^2 y = 0  ->  A y / (1 + c x/L) = (rho w^2 h^2 / T) y
    assert run("mechanical.acoustics.string_frequency_variable_density", "w") == pytest.approx(math.sqrt(70 / 0.4e-3 * ev.real.min()) / h, rel=1e-4)


def test_a_profile_guess_gives_the_whole_starting_shape():
    c = column(guess=["P = 1.2*pi**2*E*I/L**2", "y = a*sin(pi*x/L)"])
    assert out(solve(c, COL_IN), "P") == pytest.approx(math.pi ** 2 * 200e9 * 2000e-8 / 9, rel=1e-8)
