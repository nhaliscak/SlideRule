import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def vals(sol):
    return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}


def test_drag_fall_time_and_speed_match_the_closed_form():
    c = _ALL["mechanical.dynamics.fall_time_with_drag_free_end"]
    g, vt, h = 9.80665, 55.0, 500.0
    s = solve(c, c.example, ["T", "v"])
    assert s.ok, [d.message for d in s.diagnostics]
    v = vals(s)
    assert v["T"] == pytest.approx(vt / g * math.acosh(math.exp(g * h / vt**2)), rel=1e-8)
    assert v["v"] == pytest.approx(vt * math.tanh(g * 5 / vt), rel=1e-7)
    # the positions asked for must lie inside the interval that was found
    late = solve(c, {**c.example, "t": "30 s"}, ["v"])
    assert not late.ok and any("outside the interval" in d.message for d in late.diagnostics)


def test_column_length_and_mode_shape():
    c = _ALL["civil.structures.pinned_column_euler_length_free_boundary"]
    k = math.sqrt(100e3 / 1.6e6)
    v = vals(solve(c, c.example, ["L", "w"]))
    assert v["L"] == pytest.approx(math.pi / k, rel=1e-8)
    assert v["w"] == pytest.approx(0.001 / k * math.sin(k * 6), rel=1e-6)
    second = vals(solve(c, {**c.example, "L0": "20 m"}, ["L"]))["L"]                  # a guess near the second mode finds it
    assert second == pytest.approx(2 * math.pi / k, rel=1e-6)


def test_the_extra_condition_is_required_and_positions_are_limited():
    def mk(bnd, guess=("L = L0", "diff(T, x) = 1")):
        return Calculation(id="custom.fb", name="f", disciplines=["mechanical"], description="", custom=True, outputs=["L"], equations=[],
                           variables=[V("T", "T", "m", signed=True), V("x", "x", "m"), V("L", "L", "m"), V("L0", "L0", "m"), V("k", "k", "1/m^2")],
                           odes=[{"independent": "x", "start": "0", "end": "L", "equations": ["diff(T, x, 2) = -k*T"], "boundary": bnd, "unknowns": ["L"], "guess": list(guess)}])
    mk(["start: T = 0", "start: diff(T, x) = 1", "end: T = 0"])
    with pytest.raises(ValueError, match="boundary condition"):
        mk(["start: T = 0", "end: T = 0"])                                              # one condition short for the unknown end
    with pytest.raises(ValueError, match="only at 'start' and 'end'"):
        mk(["start: T = 0", "start: diff(T, x) = 1", "L/2: T = 0"])


def test_free_boundary_calcs_round_trip():
    c = _ALL["mechanical.dynamics.fall_time_with_drag_free_end"]
    back = calc_from_dict({**calc_to_dict(c), "id": "custom.rt"})
    assert vals(solve(back, back.example, ["T"]))["T"] == pytest.approx(vals(solve(c, c.example, ["T"]))["T"], rel=1e-9)


def test_event_in_a_boundary_value_problem_locates_the_maximum_deflection():
    c = _ALL["civil.beam.triangular_load_maximum_deflection_position"]
    got = vals(solve(c, c.example, ["xm", "wm"]))
    ei, w0, big_l = 2e7, 10e3, 6.0
    xm = big_l * math.sqrt(1 - math.sqrt(8 / 15))                                 # where w' = 0 for a triangular load
    wmax = w0 * xm * (big_l**2 * (7 * big_l**2 - 10 * xm**2) + 3 * xm**4) / (360 * ei * big_l)
    assert got["xm"] == pytest.approx(xm, rel=1e-6)
    assert got["wm"] == pytest.approx(wmax, rel=1e-6)
    with pytest.raises(ValueError, match="cannot stop"):
        Calculation(id="custom.bev", name="b", disciplines=["civil"], description="", custom=True, outputs=["xm"], equations=[],
                    variables=[V("w", "w", "mm", signed=True), V("x", "x", "m"), V("L", "L", "m"), V("EI", "EI", "N*m^2"), V("w0", "w0", "kN/m"), V("xm", "xm", "m")],
                    odes=[{"independent": "x", "start": "0", "end": "L", "equations": ["EI*diff(w, x, 4) = w0*x/L"], "boundary": ["start: w = 0", "end: w = 0", "start: diff(w, x, 2) = 0", "end: diff(w, x, 2) = 0"],
                           "events": [{"when": "diff(w, x) = 0", "terminal": True, "time": "xm"}]}])
