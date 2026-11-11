import math

import pytest
from scipy.optimize import brentq
from scipy.special import erf

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


def stefan(nodes=100, extra=None, rate="-k*diff(T, x)/(rho*Lf)", end_cond="end: T = Tm", extra_vars=()):
    spec = {"independent": "x", "start": "0", "end": "2*lam*sqrt(al*t0)", "time": "t", "nodes": nodes, "moving": {"front": "s", "rate": rate},
            "equations": ["diff(T, t) = al*diff(T, x, 2)"], "boundary": ["start: T = Tw", end_cond],
            "initial": ["T = Tw - (Tw - Tm)*erf(x/(2*sqrt(al*t0)))/erf(lam)"], **(extra or {})}
    return Calculation(id="custom.st", name="s", disciplines=["mechanical"], description="", custom=True, outputs=["s", "T"], equations=[],
                       variables=[V("T", "T", "K"), V("x", "x", "m"), V("t", "t", "s"), V("s", "s", "m"), V("al", "al", "m^2/s"), V("k", "k", "W/(m*K)"), V("rho", "rho", "kg/m^3"),
                                  V("Lf", "Lf", "J/kg"), V("Tw", "Tw", "K"), V("Tm", "Tm", "K"), V("t0", "t0", "s"), V("lam", "lam", "1"), *extra_vars],
                       odes=[spec])


def neumann_lambda(st):
    return brentq(lambda l: l * math.exp(l * l) * math.erf(l) - st / math.sqrt(math.pi), 1e-6, 5)


def given(t):
    k, rho, cp, Lf = 2.0, 1000.0, 4000.0, 3.0e5
    al = k / (rho * cp)
    st = cp * 20.0 / Lf
    lam = neumann_lambda(st)
    return {"al": f"{al} m^2/s", "k": "2 W/(m*K)", "rho": "1000 kg/m^3", "Lf": "3e5 J/kg", "Tw": "320 K", "Tm": "300 K", "t0": "100 s", "lam": str(lam), "t": f"{t} s", "x": "0.001 m"}, al, lam


def test_one_phase_stefan_problem_matches_the_neumann_solution():
    c = stefan()
    for tt in (400.0, 1500.0):
        g, al, lam = given(tt)
        s = solve(c, g, ["s"])
        assert s.ok, [d.message for d in s.diagnostics]
        got = next(o["si_value"] for o in s.to_dict()["outputs"] if o["key"] == "s")
        assert got == pytest.approx(2 * lam * math.sqrt(al * (tt + 100.0)), rel=2e-3)          # s = 2 lambda sqrt(alpha (t0 + t)): the run starts from the exact solution at t0 = 100 s
    g, al, lam = given(1500.0)
    g["x"] = "0.004 m"
    out = solve(c, g, ["T"])
    assert out.ok, [d.message for d in out.diagnostics]
    T = next(o["si_value"] for o in out.to_dict()["outputs"] if o["key"] == "T")
    assert T == pytest.approx(320 - 20 * erf(0.004 / (2 * math.sqrt(al * 1600.0))) / erf(lam), abs=0.05)
    titles = " ".join(q["title"] for q in out.series)
    assert "moving boundary" in titles and "profile" in titles


def test_moving_boundary_validation_and_round_trip():
    with pytest.raises(ValueError, match="dimension"):
        stefan(rate="-k*diff(T, x)/(rho*Lf)*t")
    with pytest.raises(ValueError, match="front variable"):
        stefan(extra={"moving": {"front": "T", "rate": "0"}})
    with pytest.raises(ValueError, match="moving"):
        stefan(extra={"periodic": ["x"]})
    c = stefan()
    back = calc_from_dict({**calc_to_dict(c), "id": "custom.rt"})
    g, _al, _lam = given(400.0)
    a = solve(c, g, ["s"]).to_dict()["outputs"][0]["si_value"]
    b = solve(back, g, ["s"]).to_dict()["outputs"][0]["si_value"]
    assert a == pytest.approx(b, rel=1e-12)
    # the region must stay positive: a front receding to the fixed end stops with a message
    receding = stefan(rate="-k*diff(T, x)/(rho*Lf) - vr", extra_vars=[V("vr", "vr", "m/s")])
    s = solve(receding, {**g, "vr": "1e3 m/s", "t": "5000 s"}, ["s"])
    assert not s.ok and any("vanished" in d.message or "reached" in d.message for d in s.diagnostics)
