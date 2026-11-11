
import pytest

from sliderule.core import C, Calculation, V, solve

STRESS = Calculation(
    id="t.stress", name="Axial stress", disciplines=["mechanical"], description="",
    variables=[V("sigma", "Stress", "MPa", r"\sigma"), V("F", "Force", "kN"), V("A", "Area", "mm^2")],
    equations=["sigma = F/A"], outputs=["sigma"],
)


def codes(sol, level=None):
    return [d.code for d in sol.diagnostics if level in (None, d.level)]


def test_forward_solution_matches_hand_calc():
    s = solve(STRESS, {"F": "250 kN", "A": "3000 mm^2"})
    assert s.ok and s.outputs[0]["value"] == pytest.approx(83.3333333)
    assert s.outputs[0]["unit"] == "MPa" and s.outputs[0]["si_value"] == pytest.approx(83.3333333e6)


def test_solve_for_an_input_by_rearranging():
    s = solve(STRESS, {"sigma": "83.3333333 MPa", "F": "250 kN"}, solve_for=["A"], output_units={"A": "in^2"})
    assert s.ok
    assert s.outputs[0]["value"] == pytest.approx(3000 / 645.16, rel=1e-6)
    sym = [l.latex for st in s.steps["symbolic"] for l in st.lines]
    assert any(r"A = \frac{F}{\sigma}" == x for x in sym)


def test_mixed_units_in_one_calculation_are_consistent():
    a = solve(STRESS, {"F": "250 kN", "A": "3000 mm^2"}).outputs[0]["si_value"]
    b = solve(STRESS, {"F": "56202.2 lbf", "A": "4.65 in^2"}).outputs[0]["si_value"]
    assert b == pytest.approx(a, rel=2e-3)


def test_dimension_mismatch_is_an_error_with_names():
    s = solve(STRESS, {"F": "250 psi", "A": "3000 mm^2"})
    assert not s.ok and codes(s, "error") == ["DIM_MISMATCH"]
    assert "force" in s.diagnostics[0].message and "pressure" in s.diagnostics[0].message


def test_mixed_system_warning_but_correct_result():
    s = solve(STRESS, {"F": "250 lbf", "A": "3000 mm^2"})
    assert s.ok and "MIXED_UNIT_SYSTEMS" in codes(s, "warning")


def test_errors_are_collected_not_first_only():
    s = solve(STRESS, {"F": "-5 kN", "A": "3000 foo"})
    assert not s.ok and sorted(codes(s, "error")) == ["NEGATIVE_VALUE", "UNIT_UNKNOWN"]


def test_missing_inputs_named():
    s = solve(STRESS, {"F": "1 kN"})
    assert not s.ok and "A" in s.diagnostics[0].message and s.diagnostics[0].code == "MISSING_INPUTS"


def test_target_cannot_also_be_input_and_constants_are_fixed():
    assert codes(solve(STRESS, {"F": "1 kN", "A": "1 mm^2", "sigma": "1 MPa"}, solve_for=["sigma"]), "error") == ["TARGET_GIVEN"]
    g = Calculation(id="t.g", name="g", disciplines=["mechanical"], description="",
                    variables=[C("g", "gravity", 9.80665, "m/s^2"), V("m", "mass", "kg"), V("W", "weight", "N")],
                    equations=["W = m*g"], outputs=["W"])
    assert codes(solve(g, {"m": "2 kg", "g": "1 m/s^2"}), "error") == ["CONSTANT_OVERRIDE"]
    assert solve(g, {"m": "2 kg"}).outputs[0]["value"] == pytest.approx(19.6133)


def test_divide_by_zero_is_reported():
    s = solve(STRESS, {"sigma": "0 MPa", "F": "1 kN"}, solve_for=["A"])
    assert not s.ok and s.diagnostics[0].code == "EVAL_ERROR"


def test_bounds_enforced():
    c = Calculation(id="t.b", name="b", disciplines=["industrial"], description="",
                    variables=[V("x", "frac", "1", min=0, max=1), V("y", "out", "1")], equations=["y = 2*x"], outputs=["y"])
    assert codes(solve(c, {"x": "1.5"}), "error") == ["OUT_OF_RANGE"]
    assert solve(c, {"x": "50 %"}).outputs[0]["value"] == pytest.approx(1.0)


def test_temperature_inputs_and_outputs_use_offsets():
    from sliderule.library import mechanical

    gas = next(c for c in mechanical.CALCS if c.id.endswith("ideal_gas_law"))
    s = solve(gas, {"P": "1 atm", "n": "1 mol", "T": "0 degC"}, output_units={"V": "L"})
    assert s.outputs[0]["value"] == pytest.approx(22.414, rel=1e-4)
    s = solve(gas, {"P": "101.325 kPa", "n": "1 mol", "V": "24.465 L"}, solve_for=["T"], output_units={"T": "degC"})
    assert s.outputs[0]["value"] == pytest.approx(25.0, abs=0.02)
    # absolute temperature cannot be negative once converted
    assert codes(solve(gas, {"P": "1 atm", "n": "1 mol", "T": "-300 degC"}), "error") == ["NEGATIVE_VALUE"]


def test_causal_ordering_solves_chains_in_any_input_direction():
    from sliderule.library import electrical

    ohm = next(c for c in electrical.CALCS if c.id.endswith("ohms_law_power"))
    for given in ({"V": "12 V", "R": "47 ohm"}, {"P": "3.0638 W", "R": "47 ohm"}, {"I": "0.25532 A", "R": "47 ohm"},
                  {"P": "3.0638 W", "V": "12 V"}):
        s = solve(ohm, given, solve_for=[k for k in "VIRP" if k not in given])
        assert s.ok, (given, [d.message for d in s.diagnostics])
        vals = {o["key"]: o["si_value"] for o in s.outputs}
        vals.update({k: v for k, v in zip(given, [float(x.split()[0]) for x in given.values()])})
        assert vals["V"] == pytest.approx(12, rel=1e-3) and vals["R"] == pytest.approx(47, rel=1e-3)


def test_coupled_system_is_solved_simultaneously():
    from sliderule.library import chemical

    pipe = next(c for c in chemical.CALCS if c.id.endswith("darcy_weisbach"))
    s = solve(pipe, {"rho": "998 kg/m^3", "mu": "1 cP", "L": "100 m", "eps": "0.05 mm", "dP": "50 kPa", "D": "100 mm"}, solve_for=["v"])
    assert s.ok and any(d.code == "COUPLED_SYSTEM" for d in s.diagnostics)            # the friction factor depends on the velocity and the velocity on the friction factor
    v = s.outputs[0]["si_value"]
    assert v == pytest.approx(2.3149, rel=1e-3)
    back = solve(pipe, {"rho": "998 kg/m^3", "mu": "1 cP", "L": "100 m", "eps": "0.05 mm", "v": f"{v} m/s", "D": "100 mm"}, solve_for=["dP"])
    assert back.ok and back.outputs[0]["si_value"] == pytest.approx(50e3, rel=1e-6)


def test_an_underdetermined_system_is_still_refused_with_an_explanation():
    from sliderule.library import chemical

    pipe = next(c for c in chemical.CALCS if c.id.endswith("darcy_weisbach"))
    s = solve(pipe, {"rho": "998 kg/m^3", "mu": "1 cP", "L": "100 m", "eps": "0.05 mm", "D": "100 mm"}, solve_for=["v"])
    assert not s.ok and s.diagnostics[0].code in {"MISSING_INPUTS", "CANNOT_ISOLATE"}


def test_overspecified_inconsistent_inputs_warn():
    from sliderule.library import electrical

    ohm = next(c for c in electrical.CALCS if c.id.endswith("ohms_law_power"))
    s = solve(ohm, {"V": "12 V", "R": "47 ohm", "I": "1 A"}, solve_for=["P"])
    assert s.ok and "OVERSPECIFIED" in codes(s, "warning")


def test_validity_condition_warns_but_computes():
    from sliderule.library import industrial

    mm1 = next(c for c in industrial.CALCS if c.id.endswith("mm1"))
    s = solve(mm1, {"lam": "30 ea/h", "mu": "24 ea/h"})
    assert "VALIDITY" in codes(s, "warning")


def test_steps_shape_and_unit_conversion_visible():
    s = solve(STRESS, {"F": "250 kN", "A": "3000 mm^2"}, output_units={"sigma": "psi"})
    assert set(s.steps) == {"symbolic", "numeric"}
    num = "\n".join(l.latex for st in s.steps["numeric"] for l in st.lines)
    assert r"\mathrm{kN}" in num and r"\mathrm{N}" in num and r"\mathrm{psi}" in num
    assert r"\mathrm{mm}" in num and "10^{-6}" in num                      # conversion factor for mm^2 -> m^2
    sym = "\n".join(l.latex for st in s.steps["symbolic"] for l in st.lines)
    assert r"\frac{F}{A}" in sym and r"\mathrm{Pa}" in sym                   # unit check reduces to Pa
    assert all(st.lines for st in s.steps["numeric"] + s.steps["symbolic"])


def test_closed_form_shown_for_chains():
    from sliderule.library import mechanical

    ax = next(c for c in mechanical.CALCS if c.id.endswith("axial_member"))
    s = solve(ax, {"F": "250 kN", "A": "3000 mm^2", "E": "200 GPa", "L": "2 m"}, solve_for=["dL"])
    titles = [st.title for st in s.steps["symbolic"]]
    assert any("Closed-form" in t for t in titles)
    assert s.outputs[0]["value"] == pytest.approx(0.83333, rel=1e-4)


def test_registration_rejects_dimensionally_inconsistent_equations():
    with pytest.raises(ValueError, match="homogeneous"):
        Calculation(id="t.bad", name="bad", disciplines=["mechanical"], description="",
                    variables=[V("F", "force", "N"), V("m", "mass", "kg"), V("a", "accel", "m/s^2")],
                    equations=["F = m*a^2"], outputs=["F"])
    with pytest.raises(ValueError, match="dimension"):
        Calculation(id="t.bad2", name="bad", disciplines=["mechanical"], description="",
                    variables=[V("x", "len", "m"), V("y", "len", "m")], equations=["y = log(x)"], outputs=["y"])
    with pytest.raises(ValueError, match="add terms"):
        Calculation(id="t.bad3", name="bad", disciplines=["mechanical"], description="",
                    variables=[V("x", "len", "m"), V("t", "time", "s"), V("y", "len", "m")], equations=["y = x + t"], outputs=["y"])


def test_number_formatting():
    from sliderule.core.units_expr import fmt_number

    assert fmt_number(83333.3333, 5) == ("83333", "83333")
    assert fmt_number(0.00083333, 3) == ("8.33e-4", r"8.33\times10^{-4}")
    assert fmt_number(250000.0, 5)[0] == "250000"
    assert fmt_number(1.0e7, 3)[0] == "1e7"
    assert fmt_number(9.99996, 5)[0] == "10"
    assert fmt_number(0, 5)[0] == "0"
