"""Inverse solves that used to fail: a root outside 1e-9..1e9 (atomic lengths, astronomical masses), a pole in front of the root, a root that only
touches zero, inverse error functions, runtime ODE functions inside a coupled solve, and a PDE solver that gives up at a trial value."""

import pytest

from sliderule import api, settings
from sliderule.core import engine, solve
from sliderule.core.custom import calc_from_dict


def inverse(cid, key, **extra):
    c = api.get_calculation(cid)
    base = api.solve(cid, dict(c["example"]), sig_figs=10)
    givens = dict(c["example"])
    for o in base["outputs"]:
        if o["key"] != key and o["key"] not in givens:
            givens[o["key"]] = f'{o["value"]} {o["unit"]}'.strip() if o["unit"] not in (None, "") else str(o["value"])
    givens.pop(key, None)
    return api.solve(cid, givens, solve_for=[key], sig_figs=10, **extra), c["example"].get(key)


@pytest.mark.parametrize("cid, key, want, rel", [
    ("physics.gravitation.sphere_and_shell_potential_field", "M", 5.972e24, 1e-6),            # kilograms: above 1e9
    ("physics.modern.hydrogen_ground_state", "Rin", 52.9, 1e-6),                              # picometres: below 1e-9 in SI
    ("physics.thermodynamics.van_der_waals_maxwell_jt", "Vm", 1.0, 1e-6),
    ("physics.electromagnetism.larmor_dipole_thomson_cherenkov", "om", 3e15, 1e-6),
    ("chemistry.polymer.chain_dimensions", "Lp", 0.9, 1e-6),
    ("materials.computational.vacancy_metropolis", "dE", 0.05, 1e-6),
])
def test_roots_outside_the_old_automatic_range_are_found(cid, key, want, rel, monkeypatch):
    # the wide scan is slow on a busy CI runner; this test is about the root, not the speed, so lift both the watchdog and the scan's own budget
    settings.update(timeout_seconds=120)
    monkeypatch.setattr(engine, "_WIDE_SECONDS", 100.0)
    r, _ = inverse(cid, key)
    assert r["ok"], r["diagnostics"]
    got = next(o for o in r["outputs"] if o["key"] == key)["value"]
    assert got == pytest.approx(want, rel=rel)
    assert any(d["code"] == "NUMERIC_INVERSION" for d in r["diagnostics"])


def custom(text, y_example, x_example):
    return calc_from_dict({"id": "custom.t", "name": "T", "description": text, "disciplines": ["mechanical"],
                           "variables": [{"key": "y", "label": "y", "unit": "1", "signed": True, "example": y_example}, {"key": "x", "label": "x", "unit": "1", "example": x_example}],
                           "equations": [{"title": "f", "text": text}], "outputs": ["y"]})


def test_a_pole_before_the_root_is_skipped():
    """tan(x) + x/1000 = -1 for x > 0 (SymPy cannot rearrange it): the scan first meets the sign change at the pole x = pi/2, which is no root, then the root near 3 pi/4."""
    import math

    r = solve(custom("y = tan(x) + x/1000", "1", "0.7854"), {"y": "-1"}, solve_for=["x"])
    x = r.outputs[0]["value"]
    assert r.ok and 2.3 < x < 2.4 and math.tan(x) + x / 1000 == pytest.approx(-1.0, abs=1e-9)


def test_a_root_that_only_touches_zero_is_found_and_said_so():
    """x^3/(exp(x) - 1) peaks at x = 2.8214; asked for the peak value itself, the equation touches zero and does not cross it."""
    from scipy.optimize import minimize_scalar

    peak = minimize_scalar(lambda x: -(x ** 3 / (2.718281828459045 ** x - 1)), bounds=(1, 5), method="bounded", options={"xatol": 1e-13})
    ymax = repr(float(-peak.fun))
    r = solve(custom("y = x^3/(exp(x) - 1)", "1", "1"), {"y": ymax}, solve_for=["x"])
    assert r.ok and r.outputs[0]["value"] == pytest.approx(peak.x, rel=1e-5)


def test_a_value_the_equation_never_reaches_is_still_refused_with_the_advice():
    r = solve(custom("y = exp(x) + sin(x)^2 + 1", "2", "0.1"), {"y": "0.5"}, solve_for=["x"])
    assert not r.ok and any("no sign change found" in d.message and "search range" in d.message for d in r.diagnostics)


def test_inverse_error_function_values_are_evaluated():
    r, want = inverse("electrical.comms.ber_digital_modulation", "EbN0")
    assert r["ok"] and next(o for o in r["outputs"] if o["key"] == "EbN0")["value"] == pytest.approx(8.0, rel=1e-8)


def test_a_numerical_ode_function_works_in_a_coupled_solve(monkeypatch):
    from sliderule import settings

    monkeypatch.setattr(settings, "limit", lambda: 120.0)
    r, want = inverse("mechanical.heat.melting_front_stefan_problem", "rho")
    assert r["ok"] and next(o for o in r["outputs"] if o["key"] == "rho")["value"] == pytest.approx(1000.0, rel=1e-6)


def test_a_pde_solver_failing_at_a_trial_value_is_not_fatal():
    r, _ = inverse("civil.environmental.tracer_wave_in_a_closed_loop", "L")
    assert r["ok"]
    got = next(o for o in r["outputs"] if o["key"] == "L")
    forward = api.solve("civil.environmental.tracer_wave_in_a_closed_loop", {**api.get_calculation("civil.environmental.tracer_wave_in_a_closed_loop")["example"], "L": f"{got['value']} {got['unit']}"}, sig_figs=10)
    assert forward["ok"]                                                                     # the value that was found can be used to run the calculation forward
