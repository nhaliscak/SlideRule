import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


VARS = [V("u", "u", "1"), V("x", "x", "1"), V("y", "y", "1"), V("t", "t", "1")]
OUTER = ["left: u = y**2", "right: u = 1 + y**2", "bottom: u = x**2", "top: u = 1 + x**2"]


def lshape(cuts, steady=True, nodes=20, outer=None, equation=None):
    spec = {"independent": "x", "start": "0", "end": "1", "second": "y", "second_start": "0", "second_end": "1", "nodes": nodes, "cutouts": cuts,
            "equations": [equation or ("diff(u, x, 2) + diff(u, y, 2) = 4" if steady else "diff(u, t) = diff(u, x, 2) + diff(u, y, 2)")],
            "boundary": outer or (OUTER if steady else [b.replace("y**2", "y**2 + 4*t").replace("x**2", "x**2 + 4*t") if "1 +" not in b else b.replace("1 + y**2", "1 + y**2 + 4*t").replace("1 + x**2", "1 + x**2 + 4*t") for b in OUTER])}
    if not steady:
        spec["time"] = "t"
        spec["initial"] = ["u = x**2 + y**2"]
    return Calculation(id="custom.cut", name="c", disciplines=["mechanical"], description="", custom=True, outputs=["u"], equations=[], variables=VARS if not steady else VARS[:3], odes=[spec])


def val(c, **g):
    s = solve(c, {k: str(v) for k, v in g.items()}, ["u"])
    assert s.ok, [d.message for d in s.diagnostics]
    return s.to_dict()["outputs"][0]["si_value"], s


NOTCH = {"x0": "0.5", "x1": "1", "y0": "0.5", "y1": "1", "boundary": ["left: diff(u, x) = 1", "bottom: diff(u, y) = 1"]}


def test_steady_l_shape_reproduces_a_quadratic_exactly_with_slope_conditions_on_the_notch():
    # u = x^2 + y^2 has second differences that are exact, so the discrete solution must equal it at every node of the L-shaped region
    c = lshape([NOTCH])
    for x, y in ((0.25, 0.75), (0.75, 0.25), (0.5, 0.5), (0.25, 0.25), (0.5, 0.75)):
        got, s = val(c, x=x, y=y)
        assert got == pytest.approx(x * x + y * y, abs=1e-6)
    assert any("field" in q["title"] for q in s.series)
    hm = next(q["heatmap"] for q in s.series if "heatmap" in q)
    assert any(v is None for row in hm["z"] for v in row) and any(v is not None for row in hm["z"] for v in row)          # the notch is blank in the map
    s = solve(c, {"x": "0.75", "y": "0.75"}, ["u"])
    assert not s.ok and any("cutout" in d.message for d in s.diagnostics)


def test_value_conditions_on_the_notch_and_a_plate_with_a_hole():
    dirichlet = {**NOTCH, "boundary": ["left: u = 0.25 + y**2", "bottom: u = x**2 + 0.25"]}
    got, _ = val(lshape([dirichlet]), x=0.25, y=0.75)
    assert got == pytest.approx(0.625, abs=1e-6)
    hole = {"x0": "0.25", "x1": "0.75", "y0": "0.25", "y1": "0.75",
            "boundary": ["left: diff(u, x) = 2*0.25", "right: diff(u, x) = 2*0.75", "bottom: diff(u, y) = 2*0.25", "top: diff(u, y) = 2*0.75"]}
    got, _ = val(lshape([hole], nodes=24), x=0.1, y=0.9)
    assert got == pytest.approx(0.82, abs=1e-6)
    got, _ = val(lshape([hole], nodes=24), x=0.25, y=0.5)                      # on the face of the hole
    assert got == pytest.approx(0.3125, abs=1e-6)


def test_transient_l_shape_against_the_exact_solution():
    c = lshape([NOTCH], steady=False, nodes=16)
    got, _ = val(c, x=0.25, y=0.75, t=0.5)                                       # u = x^2 + y^2 + 4 t
    assert got == pytest.approx(0.625 + 2.0, abs=2e-4)
    got, _ = val(c, x=0.75, y=0.25, t=0.5)
    assert got == pytest.approx(0.625 + 2.0, abs=2e-4)


def test_cutout_validation_and_round_trip():
    with pytest.raises(ValueError, match="needs x0"):
        Calculation(id="custom.cut2", name="c", disciplines=["mechanical"], description="", custom=True, outputs=["u"], equations=[], variables=VARS[:3],
                    odes=[{"independent": "x", "start": "0", "end": "1", "second": "y", "second_start": "0", "second_end": "1", "equations": ["diff(u, x, 2) + diff(u, y, 2) = 4"], "boundary": OUTER,
                           "cutouts": [{"x0": "0.5"}]}])
    c = lshape([{**NOTCH, "boundary": ["left: diff(u, x) = 1"]}])
    s = solve(c, {"x": "0.25", "y": "0.25"}, ["u"])
    assert not s.ok and any("bottom side of cutout 1" in d.message for d in s.diagnostics)             # an exposed side without a condition
    c = lshape([NOTCH, {**NOTCH, "x0": "0.6", "boundary": ["left: diff(u, x) = 1.2", "bottom: diff(u, y) = 1"]}])
    s = solve(c, {"x": "0.25", "y": "0.25"}, ["u"])
    assert not s.ok and any("overlap" in d.message for d in s.diagnostics)
    with pytest.raises(ValueError, match="dimension"):
        Calculation(id="custom.cut3", name="c", disciplines=["mechanical"], description="", custom=True, outputs=["u"], equations=[],
                    variables=[V("u", "u", "K"), V("x", "x", "m"), V("y", "y", "m"), V("L", "L", "m")],
                    odes=[{"independent": "x", "start": "0", "end": "L", "second": "y", "second_start": "0", "second_end": "L", "equations": ["diff(u, x, 2) + diff(u, y, 2) = 0"],
                           "boundary": ["left: u = 0*L", "right: u = 0*L", "bottom: u = 0*L", "top: u = 0*L"], "cutouts": [{"x0": "0.5", "x1": "L", "y0": "L/2", "y1": "L", "boundary": ["left: u = 0", "bottom: u = 0"]}]}])
    ok = lshape([NOTCH])
    back = calc_from_dict({**calc_to_dict(ok), "id": "custom.rt"})
    got, _ = val(back, x=0.25, y=0.75)
    assert got == pytest.approx(0.625, abs=1e-6)
