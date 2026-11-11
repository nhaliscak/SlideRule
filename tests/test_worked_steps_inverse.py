"""Solving for a different variable than the example does must still give a worked solution: the unit-check step used to raise (HTTP 500) when the
rearranged form had a symbolic exponent, a log of a dimensioned ratio or an undefined (nan) Piecewise branch."""

import pytest

from sliderule import api

CASES = [("chemistry.surface.freundlich_langmuir_isotherms", "c"), ("materials.ceramics.weibull_strength_thermal_shock", "s"),
         ("electrical.energy.battery_peukert_runtime", "Id"), ("civil.wind.mean_wind_profile", "zr"), ("civil.survey.polygon_area_coordinates", "x1"),
         ("civil.geotech.liquefaction_csr", "z"), ("computer.security.token_bucket_rate_limit", "rt"), ("civil.groundwater.thiem_well", "r1"),
         ("chemical.fluids.pipe_flow_darcy_weisbach", "eps"), ("architectural.energy.degree_days_annual_heating_demand", "Ns"),
         ("industrial.ergonomics.niosh_lifting", "Vh"), ("environmental.air.briggs_plume_rise", "u")]


def inverse(cid, key):
    c = api.get_calculation(cid)
    base = api.solve(cid, dict(c["example"]), sig_figs=8)
    givens = dict(c["example"])
    for o in base["outputs"]:
        if o["key"] != key and o["key"] not in givens:
            givens[o["key"]] = f'{o["value"]} {o["unit"]}'.strip() if o["unit"] not in (None, "") else str(o["value"])
    want = c["example"].get(key)
    givens.pop(key, None)
    return api.solve(cid, givens, solve_for=[key], sig_figs=8), want, base


@pytest.mark.parametrize("cid, key", CASES)
def test_inverse_solves_give_a_worked_solution_not_an_exception(cid, key):
    r, _, _ = inverse(cid, key)
    assert r["ok"], r["diagnostics"]
    titles = [s["title"] for s in r["steps"]["symbolic"]]
    assert "Dimensional (unit) check" in titles and any(s["title"].startswith("Calculate") for s in r["steps"]["numeric"])
    assert r["steps"]["numeric"][-1]["title"] == "Result"
    for kind in ("symbolic", "numeric"):
        for st in r["steps"][kind]:
            for ln in st["lines"]:
                assert "None" not in ln["latex"] and "nan" not in ln["latex"].split() and "zoo" not in ln["latex"]


def test_the_inverse_of_freundlich_recovers_the_example_value_and_shows_a_unit_reduction():
    r, want, base = inverse("chemistry.surface.freundlich_langmuir_isotherms", "c")
    got = next(o for o in r["outputs"] if o["key"] == "c")
    assert got["value"] == pytest.approx(20.0, rel=1e-5) and want == "20 mg/L"
    lines = [ln for st in r["steps"]["symbolic"] if st["title"] == "Dimensional (unit) check" for ln in st["lines"]]
    assert any(r"\mathrm{kg}" in ln["latex"] for ln in lines)               # reduced to kg/m^3 once the exponent 1/nf is given its value


def test_when_the_units_cannot_be_reduced_the_line_says_so_instead_of_failing():
    r, _, _ = inverse("civil.groundwater.thiem_well", "r1")
    lines = [ln for st in r["steps"]["symbolic"] if st["title"] == "Dimensional (unit) check" for ln in st["lines"]]
    assert any("not reduced symbolically" in ln["latex"] and "could not be tracked symbolically" in ln["note"] for ln in lines)
    assert not any("reduce to the expected SI unit" in ln["note"] for ln in lines if "not reduced symbolically" in ln["latex"])
    assert any(ln["note"] == "unit of the result (not reduced symbolically)" for st in r["steps"]["numeric"] for ln in st["lines"])


def test_an_engine_fault_reaches_the_caller_as_a_message(monkeypatch):
    monkeypatch.setitem(api._METHODS, "boom", lambda: (_ for _ in ()).throw(RuntimeError("kaput")))
    r = api.handle("boom")
    assert r["ok"] is False and r["error"]["code"] == "INTERNAL_ERROR" and "kaput" in r["error"]["message"] and r["error"]["status"] == 500
