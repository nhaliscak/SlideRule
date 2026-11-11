"""The Python script export for events, delays, boundary-value problems and partial differential equations: the script re-solves each with SciPy and must agree with the
analytic answer (where there is one) and with SlideRule's own solver."""
import math
import re

import pytest
import sympy as sp

from sliderule import design_export
from sliderule.core import solve
from sliderule.core.catalog import default_catalog

from test_design_export import _run_script, _single_block

CAT = default_catalog()


def script(cid, **override):
    c = CAT.get(cid)
    g = _single_block(c)
    g["blocks"][0]["values"].update({k: str(v) for k, v in override.items()})
    r = design_export.export_system(g, "python")
    assert r["ok"], r["diagnostics"]
    return r["content"]


def printed(src):
    """label -> SI value from the script's output."""
    out = _run_script(src)
    assert "matches the SlideRule reference values" in out, out
    return {m.group(1).strip(): float(m.group(2)) for m in re.finditer(r"^b1: (.+?)\s+\S+ .*?\(SI (\S+)\)$", out, re.M)}


def test_terminal_and_reset_events():
    v = printed(script("civil.hydraulics.tank_drain_time_to_level"))
    tf = next(val for k, val in v.items() if "time" in k.lower())
    assert tf == pytest.approx(1000 * math.sqrt(2 / 9.80665) * (math.sqrt(3) - math.sqrt(0.5)), rel=2e-5)          # t = (A/a) sqrt(2/g) (sqrt(h0) - sqrt(hf))
    v = printed(script("mechanical.dynamics.bouncing_ball_impacts"))
    tb = next(val for k, val in v.items() if "impact" in k.lower() or "time" in k.lower())
    assert tb == pytest.approx(math.sqrt(2 * 1.0 / 9.80665), rel=2e-5)                                         # first impact of a ball dropped from 1 m


def test_delay_equation_script_is_exact_and_so_is_the_solver():
    v = printed(script("mechanical.control.delayed_feedback_sensor_lag"))
    assert next(iter(v.values())) == pytest.approx(10493 / 518400, rel=2e-5)                                    # y' = -y(t - 1), y = 1 before 0: method of steps, y(10)
    c = CAT.get("mechanical.control.delayed_feedback_sensor_lag")
    s = solve(c, c.example, list(c.outputs))
    assert s.to_dict()["outputs"][0]["si_value"] == pytest.approx(10493 / 518400, rel=1e-5)


def test_boundary_value_problems_with_events_interior_conditions_and_free_ends():
    # simply supported beam, load w0 x / L: the maximum deflection is where w' = 0
    x, L, c1, c3 = sp.symbols("x L c1 c3")
    w = x**5 / (120 * L) + c3 * x**3 + c1 * x
    sol = sp.solve([w.subs(x, L), sp.diff(w, x, 2).subs(x, L)], [c1, c3], dict=True)[0]
    xm = float(min(r for r in sp.solve(sp.diff(w.subs(sol), x).subs(L, 6), x) if r.is_real and 0 < r < 6))
    v = printed(script("civil.beam.triangular_load_maximum_deflection_position"))
    assert next(val for k, val in v.items() if "position" in k.lower() or "location" in k.lower()) == pytest.approx(xm, rel=2e-5)
    printed(script("civil.column.buckling_load_tapered_stiffness"))                  # a condition at the middle of the span: the interval is split there
    printed(script("civil.structures.pinned_column_euler_length_free_boundary"))      # the end of the interval is an unknown
    printed(script("mechanical.dynamics.cantilever_frequency_eigenproblem"))          # an eigenvalue found with the solution


def test_every_pde_class_has_a_script():
    for cid in ("mechanical.heat.slab_transient_convective_cooling", "mechanical.acoustics.damped_string_displacement", "mechanical.heat.rectangular_plate_steady_field",
                "chemical.reaction.reactive_slab_two_species", "mechanical.heat.box_steady_generation_3d", "civil.environmental.tracer_wave_in_a_closed_loop",
                "civil.hydraulics.dam_break_dry_bed", "mechanical.heat.melting_front_stefan_problem", "mechanical.heat.l_shaped_section_steady_conduction"):
        src = script(cid)
        assert "_run_" in src and "scipy" in src.split("\n", 12)[1] + src[:600]
        printed(src)


def test_singular_start_and_unsupported_cases():
    printed(script("space.stellar.lane_emden_polytrope"))                              # u'/r at r = 0 starts from a series
    for cid in ("materials.viscoelastic.fractional_kelvin_voigt_creep", "mechanical.hvac.room_temperature_noise_statistics"):
        r = design_export.export_system(_single_block(CAT.get(cid)), "python")
        assert not r["ok"] and r["diagnostics"][0]["code"] == "NUMERIC_ODE"
