import math

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


def calc(variables, spec, outputs=("u",)):
    return Calculation(id="custom.plate", name="p", disciplines=["mechanical"], description="", variables=variables, equations=[], outputs=list(outputs), custom=True, odes=[spec])


PV = [V("T", "Temperature", "K"), V("T0", "Cold edges", "K"), V("dT", "Extra", "K"), V("x", "x", "m"), V("y", "y", "m"), V("a", "Width", "m"), V("b", "Height", "m")]
PLATE = {"independent": "x", "start": "0", "end": "a", "second": "y", "second_start": "0", "second_end": "b", "equations": ["diff(T, x, 2) + diff(T, y, 2) = 0"],
         "boundary": ["left: T = T0", "right: T = T0", "bottom: T = T0", "top: T = T0 + dT"]}
PIN = {"T0": "300 K", "dT": "100 K", "x": "50 mm", "y": "80 mm", "a": "100 mm", "b": "100 mm"}


def laplace(xr, yr, terms=60):
    return sum(4 / ((2 * k - 1) * math.pi) * math.sin((2 * k - 1) * math.pi * xr) * math.exp((2 * k - 1) * math.pi * (yr - 1)) * (1 - math.exp(-2 * (2 * k - 1) * math.pi * yr)) / (1 - math.exp(-2 * (2 * k - 1) * math.pi))
               for k in range(1, terms))


def test_laplace_on_a_plate_matches_the_series_solution():
    sol = solve(calc(PV, PLATE, ["T"]), PIN)
    assert out(sol, "T") == pytest.approx(300 + 100 * laplace(0.5, 0.8), rel=2e-4)
    d = sol.to_dict()
    assert [x["code"] for x in d["diagnostics"]] == []
    assert any("estimated discretisation error" in n for n in d["series"][0]["method"]["notes"])


def test_poisson_with_a_source_and_zero_boundaries():
    v = [V("u", "u", "1", signed=True), V("x", "x", "1"), V("y", "y", "1")]
    spec = {"independent": "x", "start": "0", "end": "1", "second": "y", "second_start": "0", "second_end": "1",
            "equations": ["diff(u, x, 2) + diff(u, y, 2) = -2*pi**2*sin(pi*x)*sin(pi*y)"], "boundary": ["left: u = 0", "right: u = 0", "bottom: u = 0", "top: u = 0"]}
    assert out(solve(calc(v, spec), {"x": "0.3", "y": "0.6"}), "u") == pytest.approx(math.sin(0.3 * math.pi) * math.sin(0.6 * math.pi), rel=2e-3)


def test_slope_conditions_with_an_exactly_representable_solution():
    v = [V("u", "u", "1", signed=True), V("x", "x", "1"), V("y", "y", "1")]
    spec = {"independent": "x", "start": "0", "end": "1", "second": "y", "second_start": "0", "second_end": "1", "equations": ["diff(u, x, 2) + diff(u, y, 2) = 4"],
            "boundary": ["left: diff(u, x) = 0", "right: u = 1 + y**2", "bottom: diff(u, y) = 0", "top: u = x**2 + 1"]}
    got = out(solve(calc(v, spec), {"x": "0.37", "y": "0.52"}), "u")
    assert got == pytest.approx(0.37 ** 2 + 0.52 ** 2, rel=1e-6)                          # u = x^2 + y^2 is reproduced exactly by second-order differences


def test_robin_side_and_conduction_with_generation():
    v = [V("T", "T", "K"), V("x", "x", "m"), V("y", "y", "m"), V("L", "L", "m"), V("T1", "T1", "K"), V("Tinf", "Tinf", "K"), V("k", "k", "W/(m*K)"), V("h", "h", "W/(m^2*K)")]
    spec = {"independent": "x", "start": "0", "end": "L", "second": "y", "second_start": "0", "second_end": "L", "equations": ["diff(T, x, 2) + diff(T, y, 2) = 0"],
            "boundary": ["left: diff(T, x) = 0", "right: diff(T, x) = 0", "bottom: T = T1", "top: -k*diff(T, y) = h*(T - Tinf)"]}
    inp = {"L": "0.1 m", "T1": "400 K", "Tinf": "300 K", "k": "10 W/(m*K)", "h": "50 W/(m^2*K)", "x": "0.03 m", "y": "0.1 m"}
    Bi = 50 * 0.1 / 10
    expected = 400 - (400 - 300) * Bi / (1 + Bi)                                           # one-dimensional fin-free slab between a fixed and a convecting face
    assert out(solve(calc(v, spec, ["T"]), inp), "T") == pytest.approx(expected, rel=1e-6)
    v2 = [V("T", "T", "K"), V("x", "x", "m"), V("y", "y", "m"), V("L", "L", "m"), V("T1", "T1", "K"), V("k", "k", "W/(m*K)"), V("q", "q", "W/m^3")]
    gen = {**spec, "equations": ["k*(diff(T, x, 2) + diff(T, y, 2)) + q = 0"], "boundary": ["left: T = T1", "right: T = T1", "bottom: T = T1", "top: T = T1"]}
    centre = out(solve(calc(v2, gen, ["T"]), {"L": "0.1 m", "T1": "300 K", "k": "10 W/(m*K)", "q": "50 kW/m^3", "x": "0.05 m", "y": "0.05 m"}), "T")
    assert centre == pytest.approx(300 + 0.0737 * 5e4 * 0.1 ** 2 / 10, rel=3e-3)         # the textbook value 0.0737 q a^2 / k for the centre of a square


def test_nonlinear_equation_by_a_manufactured_solution():
    v = [V("u", "u", "1", signed=True), V("x", "x", "1"), V("y", "y", "1")]
    spec = {"independent": "x", "start": "0", "end": "1", "second": "y", "second_start": "0", "second_end": "1",
            "equations": ["diff(u, x, 2) + diff(u, y, 2) = u**2 - pi**2*sin(pi*x)*sin(pi*y) - (0.5*sin(pi*x)*sin(pi*y))**2"],
            "boundary": ["left: u = 0", "right: u = 0", "bottom: u = 0", "top: u = 0"], "guess": ["u = 0.1"]}
    got = out(solve(calc(v, spec), {"x": "0.3", "y": "0.6"}), "u")
    assert got == pytest.approx(0.5 * math.sin(0.3 * math.pi) * math.sin(0.6 * math.pi), rel=3e-3)


def test_plots_cover_the_rectangle():
    d = solve(calc(PV, PLATE, ["T"]), PIN).to_dict()
    field, along_x, along_y = d["series"]
    hm = field["heatmap"]
    assert len(hm["x"]) == 41 and len(hm["y"]) == 41 and len(hm["z"]) == 41 and len(hm["z"][0]) == 41
    assert hm["zmin"] == pytest.approx(300.0) and hm["zmax"] == pytest.approx(400.0, abs=1e-6)
    assert hm["z"][-1][20] == pytest.approx(400.0)                                           # the top edge is the hot one
    assert along_x["series"][0]["values"][0] == pytest.approx(300.0) and along_y["series"][0]["values"][-1] == pytest.approx(400.0)


def test_inverse_solve_for_the_edge_temperature():
    c = calc(PV, PLATE, ["T"])
    T = out(solve(c, PIN), "T")
    back = solve(c, {**{k: v for k, v in PIN.items() if k != "dT"}, "T": f"{T} K"}, ["dT"]).to_dict()
    assert back["ok"] and back["outputs"][0]["si_value"] == pytest.approx(100.0, rel=1e-6)


def test_validation_and_errors():
    def bad(match, **changes):
        with pytest.raises(ValueError, match=match):
            calc(PV, {**PLATE, **changes}, ["T"])
    bad("exactly four", boundary=["left: T = T0"])
    bad("one of each", boundary=["left: T = T0", "left: T = T0", "bottom: T = T0", "top: T = T0"])
    bad("at least one side", boundary=["left: diff(T, x) = 0", "right: diff(T, x) = 0", "bottom: diff(T, y) = 0", "top: diff(T, y) = 0"])
    bad("dimension", equations=["diff(T, x, 2) + diff(T, y) = 0"])
    bad("mixed derivatives", equations=["diff(T, x, 2) + diff(diff(T, x), y) = 0"])
    bad("second_end", second_end="")
    bad("must differ", second="x")
    bad("neither 'initial'", initial=["T = 0"])
    bad("cannot involve", boundary=["left: T = x", "right: T = T0", "bottom: T = T0", "top: T = T0"])
    d = solve(calc(PV, PLATE, ["T"]), {**PIN, "x": "0.2 m"}).to_dict()
    assert not d["ok"] and "outside the rectangle" in str(d["diagnostics"])


def test_file_round_trip_system_design_and_exports():
    c = calc(PV, PLATE, ["T"])
    again = calc_from_dict(calc_to_dict(c))
    assert out(solve(again, PIN), "T") == pytest.approx(out(solve(c, PIN), "T"))
    doc = {"id": "custom.plate", "name": "Plate", "disciplines": ["mechanical"], "outputs": ["T"], "odes": [PLATE],
           "variables": [{"key": v.key, "label": v.label, "unit": v.unit, **({"example": PIN[v.key]} if v.key in PIN else {})} for v in PV]}
    api.custom_save(doc)
    g = {"version": 1, "blocks": [{"id": "b", "calc": "custom.plate", "x": 0, "y": 0, "values": dict(PIN)}], "wires": []}
    r = design.solve_system(g)
    assert r["ok"]
    e = design_export.export_system(g, "latex")
    assert e["ok"] and "side" in e["content"]
    py = design_export.export_system(g, "python")
    assert py["ok"]                                           # the grid is solved again by the script (same finite differences, SciPy time integration)
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(py["content"], "s.py", "exec"), {"__name__": "__main__"})
    assert "matches the SlideRule reference values" in buf.getvalue()


def test_library_steady_fields_match_references():
    from sliderule.core.catalog import default_catalog

    cat = default_catalog()

    def run(cid, key, inputs):
        return out(solve(cat.get(cid), inputs), key)

    assert run("mechanical.heat.square_bar_internal_generation", "T", {"Tw": "300 K", "q": "50 kW/m^3", "k": "10 W/(m*K)", "x": "50 mm", "y": "50 mm", "a": "100 mm"}) == pytest.approx(300 + 0.0737 * 5e4 * 0.01 / 10, rel=3e-3)
    assert run("electrical.rf.potential_in_rectangular_trough", "Vp", {"V0": "100 V", "x": "50 mm", "y": "80 mm", "a": "100 mm", "b": "100 mm"}) == pytest.approx(100 * laplace(0.5, 0.8), rel=1e-3)
    # the plate with an insulated right edge, equal edges and a convecting top: with h -> very large the top edge behaves like a fixed temperature, so T tends to T0 = Tinf
    flat = run("mechanical.heat.rectangular_plate_steady_field", "T", {"T0": "350 K", "Tinf": "350 K", "x": "50 mm", "y": "50 mm", "a": "100 mm", "b": "100 mm", "k": "20 W/(m*K)", "h": "100 W/(m^2*K)"})
    assert flat == pytest.approx(350.0, abs=1e-6)
    cooled = run("mechanical.heat.rectangular_plate_steady_field", "T", {"T0": "400 K", "Tinf": "300 K", "x": "50 mm", "y": "50 mm", "a": "100 mm", "b": "100 mm", "k": "20 W/(m*K)", "h": "100 W/(m^2*K)"})
    assert 300 < cooled < 400
