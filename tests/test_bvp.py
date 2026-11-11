import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import CustomError, calc_from_dict, calc_to_dict


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def out(sol, key):
    return next(o["si_value"] for o in sol.to_dict()["outputs"] if o["key"] == key)


# a simply supported beam under uniform load: E I y'' = -w x (L - x) / 2, y(0) = y(L) = 0
BEAM_VARS = [V("y", "Deflection", "m", signed=True), V("x", "Position", "m"), V("L", "Span", "m"), V("w", "Load per length", "N/m"),
             V("E", "Modulus", "Pa"), V("I", "Second moment", "m^4")]
BEAM = {"independent": "x", "start": "0", "end": "L", "equations": ["E*I*diff(y, x, 2) = -w*x*(L - x)/2"], "boundary": ["start: y = 0", "end: y = 0"]}
BEAM_EX = {"w": "5 kN/m", "L": "6 m", "E": "200 GPa", "I": "8e-5 m^4", "x": "3 m"}


def beam(**changes):
    return Calculation(id="custom.beam", name="b", disciplines=["mechanical"], description="", variables=list(BEAM_VARS), equations=[], outputs=["y"],
                       custom=True, odes=[{**BEAM, **changes}])


def test_closed_form_beam_matches_the_textbook_formula():
    c = beam()
    s = c.parsed_odes[0]
    assert s.bvp is not None and not s.numeric
    w, L, E, I = 5e3, 6.0, 200e9, 8e-5
    mid = 5 * w * L ** 4 / (384 * E * I)                                    # 5 w L^4 / 384 E I (y is measured in the direction of the load)
    assert out(solve(c, BEAM_EX), "y") == pytest.approx(mid, rel=1e-12)


def test_it_can_be_solved_backwards_for_the_load_or_the_position():
    c = beam()
    w, L, E, I = 5e3, 6.0, 200e9, 8e-5
    y = 5 * w * L ** 4 / (384 * E * I)
    got = solve(c, {"y": f"{y} m", "L": "6 m", "E": "200 GPa", "I": "8e-5 m^4", "x": "3 m"}, ["w"])
    assert out(got, "w") == pytest.approx(w, rel=1e-9)


def test_numeric_method_agrees_with_the_closed_form_and_explains_itself():
    c = beam(method="numeric")
    assert c.parsed_odes[0].numeric
    sol = solve(c, BEAM_EX)
    w, L, E, I = 5e3, 6.0, 200e9, 8e-5
    assert out(sol, "y") == pytest.approx(5 * w * L ** 4 / (384 * E * I), rel=1e-7)
    d = sol.to_dict()
    text = str(d["steps"])
    assert "multiple shooting" in text and "boundary condition" in text
    series = d["series"][0]
    assert series["t"][0] == 0 and series["t"][-1] == pytest.approx(6.0)               # the plot covers the whole span, not just up to x
    assert max(series["series"][0]["values"]) == pytest.approx(out(sol, "y"), rel=1e-6)


def test_cantilever_with_a_slope_condition_and_a_free_end():
    # fixed at x = 0 (y = y' = 0), free at x = L (M = V = 0): E I y'''' = -w; the tip deflection is -w L^4 / 8 E I
    v = [V("y", "Deflection", "m", signed=True), V("x", "Position", "m"), V("L", "Length", "m"), V("w", "Load", "N/m"), V("E", "E", "Pa"), V("I", "I", "m^4")]
    spec = {"independent": "x", "end": "L", "equations": ["E*I*diff(y, x, 4) = -w"],
            "boundary": ["start: y = 0", "start: diff(y, x) = 0", "end: diff(y, x, 2) = 0", "end: diff(y, x, 3) = 0"]}
    for method in ("auto", "numeric"):
        c = Calculation(id="custom.cant", name="c", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["y"], custom=True,
                        odes=[{**spec, "method": method}])
        got = out(solve(c, {"w": "2 kN/m", "L": "3 m", "E": "200 GPa", "I": "1e-5 m^4", "x": "3 m"}), "y")
        assert got == pytest.approx(-2e3 * 3 ** 4 / (8 * 200e9 * 1e-5), rel=1e-7)


def test_robin_condition_on_a_fin():
    # fin: T'' = m^2 (T - Tinf); T(0) = Tb; -k T'(L) = h (T(L) - Tinf)
    v = [V("T", "Temperature", "K"), V("x", "Position", "m"), V("L", "Length", "m"), V("Tb", "Base", "K"), V("Ti", "Ambient", "K"), V("m", "Fin parameter", "1/m"),
         V("k", "Conductivity", "W/(m*K)"), V("h", "Coefficient", "W/(m^2*K)")]
    spec = {"independent": "x", "end": "L", "equations": ["diff(T, x, 2) = m**2*(T - Ti)"], "boundary": ["start: T = Tb", "end: -k*diff(T, x) = h*(T - Ti)"]}
    ex = {"Tb": "100 degC", "Ti": "20 degC", "m": "10 1/m", "k": "200 W/(m*K)", "h": "25 W/(m^2*K)", "L": "0.1 m", "x": "0.1 m"}
    mm, L, kk, hh = 10.0, 0.1, 200.0, 25.0
    th = lambda xx: (math.cosh(mm * (L - xx)) + hh / (mm * kk) * math.sinh(mm * (L - xx))) / (math.cosh(mm * L) + hh / (mm * kk) * math.sinh(mm * L))   # noqa: E731
    expected = 293.15 + 80 * th(L)
    for method in ("auto", "numeric"):
        c = Calculation(id="custom.fin", name="f", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["T"], custom=True, odes=[{**spec, "method": method}])
        assert out(solve(c, ex), "T") == pytest.approx(expected, rel=1e-7)


def test_nonlinear_problem_uses_the_guess_and_reports_the_iteration():
    # Bratu: y'' + lam exp(y) = 0, y(0) = y(1) = 0 (lam = 1 has two solutions; the lower one has y(1/2) = 0.140539...)
    v = [V("y", "Profile", "1", signed=True), V("x", "Position", "1"), V("lam", "Parameter", "1")]
    spec = {"independent": "x", "end": "1", "equations": ["diff(y, x, 2) = -lam*exp(y)"], "boundary": ["start: y = 0", "end: y = 0"]}
    c = Calculation(id="custom.bratu", name="b", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["y"], custom=True, odes=[spec])
    s = c.parsed_odes[0]
    assert s.numeric and s.bvp is not None
    assert out(solve(c, {"lam": "1", "x": "0.5"}), "y") == pytest.approx(0.1405392, rel=1e-5)
    c2 = Calculation(id="custom.bratu2", name="b", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["y"], custom=True,
                     odes=[{**spec, "guess": ["y = 3", "diff(y, x) = 0"]}])
    other = out(solve(c2, {"lam": "1", "x": "0.5"}), "y")
    assert other == pytest.approx(0.1405392, rel=1e-5) or other > 2                      # a guess may select the other branch or converge to the same one


def test_no_unique_solution_is_explained():
    v = [V("y", "y", "1", signed=True), V("x", "x", "1")]
    c = Calculation(id="custom.eig", name="e", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["y"], custom=True,
                    odes=[{"independent": "x", "end": "pi", "method": "numeric", "equations": ["diff(y, x, 2) = -y"], "boundary": ["start: y = 0", "end: y = 0"]}])
    d = solve(c, {"x": "1"}).to_dict()
    assert not d["ok"] and "no unique solution" in str(d["diagnostics"])


def test_position_outside_the_interval_is_an_error_for_the_numerical_solution():
    d = solve(beam(method="numeric"), {**BEAM_EX, "x": "7 m"}).to_dict()
    assert not d["ok"] and "outside the interval" in str(d["diagnostics"])
    w = solve(beam(), {**BEAM_EX, "x": "7 m"}).to_dict()
    assert w["ok"] and "OUTSIDE_INTERVAL" in [x["code"] for x in w["diagnostics"]]


def test_conditions_are_validated():
    with pytest.raises(ValueError, match="2 boundary conditions needed"):
        beam(boundary=["start: y = 0"])
    with pytest.raises(ValueError, match="takes no 'initial'"):
        beam(initial=["y = 0"])
    with pytest.raises(ValueError, match="needs an 'end'"):
        beam(end="")
    with pytest.raises(ValueError, match="dimension"):
        beam(boundary=["start: y = 0", "end: diff(y, x) = L"])
    with pytest.raises(ValueError, match="itself"):
        beam(boundary=["start: y = x", "end: y = 0"])
    with pytest.raises(ValueError, match="where: condition"):
        beam(boundary=["y = 0", "end: y = 0"])


def test_interior_point_conditions():
    # a beam with an extra support at mid-span: y(0) = y(L/2) = y(L) = 0 needs three conditions for a 4th... use second order with an interior value instead
    v = [V("y", "y", "m", signed=True), V("x", "x", "m"), V("L", "L", "m"), V("Y", "Value at mid-span", "m")]
    spec = {"independent": "x", "end": "L", "method": "numeric", "equations": ["diff(y, x, 2) = 2*Y/L**2"], "boundary": ["start: y = 0", "L/2: y = Y"]}
    c = Calculation(id="custom.mid", name="m", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["y"], custom=True,
                    odes=[{**spec}])
    # y = (Y/L^2) x^2 + b x with y(L/2) = Y  ->  b = (Y - Y/4) / (L/2)
    L, Y = 2.0, 1.0
    got = out(solve(c, {"L": "2 m", "x": "2 m", "Y": "1 m"}), "y")
    b = (Y - Y / 4) / (L / 2)
    assert got == pytest.approx(Y + b * L, rel=1e-8)


def test_integral_inside_a_boundary_value_problem():
    v = [V("y", "y", "1", signed=True), V("x", "x", "1")]
    spec = {"independent": "x", "end": "1", "equations": ["diff(y, x, 2) = -integrate(y, (s, 0, x))"], "boundary": ["start: y = 0", "end: y = 1"]}
    c = Calculation(id="custom.int", name="i", disciplines=["mechanical"], description="", variables=v, equations=[], outputs=["y"], custom=True, odes=[spec])
    got = out(solve(c, {"x": "1"}), "y")
    assert got == pytest.approx(1.0, abs=1e-8)


def test_custom_files_round_trip_and_validate():
    c = beam()
    d = calc_to_dict(c)
    assert d["odes"][0]["boundary"] == BEAM["boundary"] and d["odes"][0]["end"] == "L"
    again = calc_from_dict(d)
    assert out(solve(again, BEAM_EX), "y") == pytest.approx(out(solve(c, BEAM_EX), "y"))
    bad = dict(d, odes=[{**d["odes"][0], "end": ""}])
    with pytest.raises(CustomError):
        calc_from_dict(bad)


def test_system_design_and_exports_handle_boundary_value_problems():
    import contextlib
    import io

    from sliderule import api, design, design_export

    doc = {"id": "custom.beam", "name": "Beam", "disciplines": ["mechanical"], "outputs": ["y"], "odes": [BEAM],
           "variables": [{"key": v.key, "label": v.label, "unit": v.unit, **({"signed": True} if v.signed else {}), **({"example": BEAM_EX[v.key]} if v.key in BEAM_EX else {})} for v in BEAM_VARS]}
    api.custom_save(doc)
    api.custom_save({**doc, "id": "custom.beam_num", "odes": [{**BEAM, "method": "numeric"}]})
    expected = 5 * 5e3 * 6.0 ** 4 / (384 * 200e9 * 8e-5)
    for cid, numeric in (("custom.beam", False), ("custom.beam_num", True)):
        g = {"version": 1, "blocks": [{"id": "b", "calc": cid, "x": 0, "y": 0, "values": dict(BEAM_EX)}], "wires": []}
        r = design.solve_system(g)
        assert r["ok"] and next(o for o in r["blocks"]["b"]["outputs"] if o["key"] == "y")["si_value"] == pytest.approx(expected, rel=1e-6)
        for fmt in ("latex", "markdown", "html"):
            c = design_export.export_system(g, fmt)
            assert c["ok"] and "boundary condition" in c["content"]
        py = design_export.export_system(g, "python")
        if numeric:
            assert py["ok"]                                   # a numerically solved boundary-value problem is re-solved by the script with SciPy
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(py["content"], "s.py", "exec"), {"__name__": "__main__"})
            assert "matches the SlideRule reference values" in buf.getvalue()
        else:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(compile(py["content"], "s.py", "exec"), {"__name__": "__main__"})
            assert "matches the SlideRule reference values" in buf.getvalue()


def _lib(cid, inputs, key):
    from sliderule.core.catalog import default_catalog

    return out(solve(default_catalog().get(cid), inputs), key)


def test_library_boundary_value_calculations_match_textbook_results():
    w, L, E, I = 5e3, 6.0, 200e9, 8e-5
    assert _lib("civil.beam.simply_supported_uniform_deflection_profile", {"w": "5 kN/m", "L": "6 m", "E": "200 GPa", "I": "8000 cm^4", "x": "3 m"}, "y") == pytest.approx(5 * w * L ** 4 / (384 * E * I), rel=1e-9)
    P, L2, I2 = 10e3, 2.5, 5e-5
    assert _lib("civil.beam.cantilever_tip_load_deflection_profile", {"P": "10 kN", "L": "2.5 m", "E": "200 GPa", "I": "5000 cm^4", "x": "2.5 m"}, "y") == pytest.approx(P * L2 ** 3 / (3 * E * I2), rel=1e-9)
    mm, Lf, kk, hh = 12.0, 0.1, 200.0, 25.0
    th = (math.cosh(mm * 0) * 0 + (math.cosh(mm * 0) + hh / (mm * kk) * math.sinh(mm * 0))) / (math.cosh(mm * Lf) + hh / (mm * kk) * math.sinh(mm * Lf))
    assert _lib("mechanical.heat.fin_temperature_profile_convective_tip", {"Tb": "100 degC", "Ti": "20 degC", "m": "12 1/m", "k": "200 W/(m*K)", "h": "25 W/(m^2*K)", "L": "100 mm", "x": "100 mm"}, "T") == pytest.approx(293.15 + 80 * th, rel=1e-9)
    mu, G, H = 1e-3, -50.0, 0.01
    assert _lib("mechanical.fluids.channel_pressure_driven_velocity_profile", {"mu": "1 mPa*s", "G": "-50 Pa/m", "H": "10 mm", "y": "5 mm"}, "u") == pytest.approx(-G * (H / 2) * (H / 2) / (2 * mu), rel=1e-9)
    be, T1, T2, Tr = 0.002, 600.0, 300.0, 300.0
    u1, u2 = 1 + be * (T1 - Tr), 1 + be * (T2 - Tr)
    exact = Tr - 1 / be + math.sqrt(u1 ** 2 + (u2 ** 2 - u1 ** 2) * 0.5) / be
    assert _lib("mechanical.heat.slab_variable_conductivity_profile", {"T1": "600 K", "T2": "300 K", "Tr": "300 K", "be": "0.002 1/K", "L": "50 mm", "x": "25 mm"}, "T") == pytest.approx(exact, rel=1e-7)
