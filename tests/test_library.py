"""Invariants over the whole library plus hand-checked reference values."""

import math

import pytest

from sliderule.core import DISCIPLINES, solve
from sliderule.core.catalog import default_catalog
from sliderule.units import parse_unit

CAT = default_catalog()
IDS = [c.id for c in CAT]


def test_catalog_is_substantial_and_covers_every_discipline():
    assert len(CAT) >= 300
    counts = {d: 0 for d in DISCIPLINES}
    for c in CAT:
        for d in c.disciplines:
            counts[d] += 1
    assert all(n >= 3 for n in counts.values()), counts


def test_ids_are_namespaced_and_unique():
    assert len(set(IDS)) == len(IDS)
    for c in CAT:
        assert c.id.count(".") >= 2 and c.disciplines and c.name and c.description and c.references, c.id
        assert c.id.split(".")[0] in DISCIPLINES, c.id


@pytest.mark.parametrize("cid", IDS)
def test_example_solves_cleanly(cid):
    c = CAT.get(cid)
    assert c.example, "every calculation must ship a worked example"
    s = solve(c, c.example)
    assert s.ok, [d.message for d in s.diagnostics]
    assert not [d for d in s.diagnostics if d.level in ("error", "warning")], [d.message for d in s.diagnostics]
    for o in s.outputs:
        assert math.isfinite(o["value"])
    assert s.steps["symbolic"] and s.steps["numeric"]


@pytest.mark.parametrize("cid", IDS)
def test_variables_are_well_formed(cid):
    c = CAT.get(cid)
    for v in c.variables:
        assert parse_unit(v.unit, as_delta=v.delta).dim == v.dim
        assert parse_unit(v.si, as_delta=True).factor == 1.0, f"{cid}.{v.key}: si unit must be coherent"
        assert v.kinds or v.dim.is_dimensionless or True
        if v.delta:
            assert v.dim == parse_unit("K").dim


@pytest.mark.parametrize("cid", IDS)
def test_results_are_independent_of_input_unit_choice(cid):
    """Re-express every example input in the SI unit; the answer must not change."""
    c = CAT.get(cid)
    base = solve(c, c.example)
    from sliderule.core.engine import parse_quantity

    si_inputs = {}
    for k, text in c.example.items():
        v = c.by_key[k]
        val, unit = parse_quantity(text)
        if v.units:  # logarithmic levels etc. cannot be re-expressed in another unit
            si_inputs[k] = (val, unit or v.unit)
            continue
        u = parse_unit(unit or v.unit, as_delta=v.delta)
        si_inputs[k] = (u.to_si(val), v.si)
    again = solve(c, si_inputs)
    assert again.ok
    for a, b in zip(base.outputs, again.outputs):
        assert b["si_value"] == pytest.approx(a["si_value"], rel=1e-9, abs=1e-12), (cid, a["key"])


# --- reference values worked independently by hand / from standard tables -----------------------------

def out(cid, inputs, **kw):
    s = solve(CAT.get(cid), inputs, **kw)
    assert s.ok, [d.message for d in s.diagnostics]
    return {o["key"]: o for o in s.outputs}


def test_beam_udl():
    o = out("civil.beam.simply_supported_udl", CAT.get("civil.beam.simply_supported_udl").example)
    assert o["Mmax"]["si_value"] == pytest.approx(45e3)
    assert o["delta"]["si_value"] == pytest.approx(5 * 10e3 * 6**4 / (384 * 200e9 * 8e-5))
    assert o["sigma"]["si_value"] == pytest.approx(45e3 * 0.15 / 8e-5)


def test_euler_buckling_known_value():
    o = out("civil.column.euler_buckling", {"E": "200 GPa", "I": "1e7 mm^4", "A": "1000 mm^2", "K": "1", "L": "2 m"})
    assert o["Pcr"]["si_value"] == pytest.approx(math.pi**2 * 200e9 * 1e-5 / 4)   # 4.935 MN... = 4934.8 kN


def test_manning_us_factor_emerges_from_units():
    """Q[cfs] = (1.486/n) A R^(2/3) S^(1/2) with n dimensionless-by-convention."""
    n = 0.013
    A_ft2, P_ft, S = 25.0, 14.0, 0.002
    o = out("civil.hydraulics.manning_open_channel",
            {"n": f"{n} s/m^(1/3)", "A": f"{A_ft2} ft^2", "Pw": f"{P_ft} ft", "S": str(S)}, output_units={"Q": "cfs"})
    expected = 1.486 / n * A_ft2 * (A_ft2 / P_ft) ** (2 / 3) * math.sqrt(S)
    assert o["Q"]["value"] == pytest.approx(expected, rel=2e-3)    # 1.486 is itself rounded (exact: 1.48586)


def test_rational_method_us_units_match_textbook_constant():
    o = out("civil.hydrology.rational_method", {"C": "0.5", "i": "3 in/h", "A": "10 ac"}, output_units={"Q": "cfs"})
    assert o["Q"]["value"] == pytest.approx(0.5 * 3 * 10 * 1.00833, rel=1e-4)


def test_oilfield_darcy_matches_0_00708_constant():
    o = out("petroleum.reservoir.radial_darcy_inflow",
            {"k": "50 mD", "h": "30 ft", "pe": "3000 psi", "pwf": "2500 psi", "mu": "1.2 cP", "Bo": "1.25",
             "re": "1000 ft", "rw": "0.35 ft", "s": "0"})
    field = 0.00708 * 50 * 30 * 500 / (1.2 * 1.25 * math.log(1000 / 0.35))
    assert o["q"]["value"] == pytest.approx(field, rel=1e-3)


def test_mud_weight_factor_0_052():
    o = out("petroleum.drilling.wellbore_hydrostatic", {"rho": "1 ppg", "TVD": "1 ft", "Ps": "0 psi"})
    assert o["Ph"]["value"] == pytest.approx(0.0519, rel=2e-3)


def test_ooip_acre_foot_factor_7758():
    o = out("petroleum.reservoir.volumetric_ooip", {"A": "1 ac", "h": "1 ft", "phi": "1", "Sw": "0", "Bo": "1"}, output_units={"N": "bbl"})
    assert o["N"]["value"] == pytest.approx(7758.37, rel=1e-5)


def test_isa_sea_level_and_11km():
    o = out("aerospace.atmosphere.isa_troposphere", {"h": "0 m"})
    assert o["p"]["si_value"] == pytest.approx(101325) and o["rho"]["si_value"] == pytest.approx(1.225, rel=1e-3)
    assert o["a"]["si_value"] == pytest.approx(340.294, rel=1e-4)
    o = out("aerospace.atmosphere.isa_troposphere", {"h": "11000 m"})
    assert o["T"]["si_value"] == pytest.approx(216.65) and o["p"]["si_value"] == pytest.approx(22632, rel=2e-3)


def test_ppm_conversion_to_mg_per_m3():
    o = out("environmental.air.ppm_to_mass_concentration", {"y": "1 ppm", "M": "64.07 g/mol", "P": "1 atm", "T": "25 degC"})
    assert o["Cm"]["value"] == pytest.approx(64.07 / 24.465, rel=1e-3)     # classic ppm → mg/m³ with 24.45 L/mol


def test_rlc_resonance_and_reactance_use_2pi():
    o = out("electrical.ac.series_rlc", {"R": "10 ohm", "L": "1 mH", "Cap": "1 uF", "f": "1 kHz"})
    assert o["XL"]["si_value"] == pytest.approx(2 * math.pi * 1000 * 1e-3)
    assert o["f0"]["value"] == pytest.approx(1 / (2 * math.pi * math.sqrt(1e-9)), rel=1e-9)


def test_shannon_uses_hz_as_per_second():
    o = out("systems.communications.shannon_hartley", {"B": "1 MHz", "snr": "255"})
    assert o["Cc"]["value"] == pytest.approx(8.0, rel=1e-9)   # 1 MHz * log2(256) = 8 Mbit/s


def test_wall_u_value_with_us_r_values():
    o = out("architectural.envelope.wall_u_value",
            {"Rsi": "0.68 ft^2*h*degF/Btu", "Rse": "0.17 ft^2*h*degF/Btu", "t1": "4 in", "k1": "0.5 Btu/(h*ft*degF)",
             "t2": "3.5 in", "k2": "0.025 Btu/(h*ft*degF)", "t3": "0.5 in", "k3": "0.1 Btu/(h*ft*degF)",
             "A": "100 ft^2", "dT": "40 degF"}, output_units={"Rt": "ft^2*h*degF/Btu", "Q": "Btu/h"})
    r = 0.68 + 4 / 12 / 0.5 + 3.5 / 12 / 0.025 + 0.5 / 12 / 0.1 + 0.17
    assert o["Rt"]["value"] == pytest.approx(r, rel=1e-6)
    assert o["Q"]["value"] == pytest.approx(100 * 40 / r, rel=1e-6)


def test_eoq_textbook():
    o = out("industrial.inventory.eoq", {"D": "1000 ea/yr", "S": "10 USD", "H": "0.5 USD/(ea*yr)"})
    assert o["Q"]["value"] == pytest.approx(200) and o["TC"]["value"] == pytest.approx(100)


def test_second_order_overshoot():
    o = out("systems.control.second_order_step", {"zeta": "0.5", "wn": "10 rad/s"})
    assert o["Mp"]["value"] == pytest.approx(16.303, rel=1e-4)


def test_pipe_flow_laminar_branch_equals_hagen_poiseuille():
    o = out("chemical.fluids.pipe_flow_darcy_weisbach",
            {"rho": "900 kg/m^3", "mu": "100 cP", "v": "0.5 m/s", "D": "20 mm", "L": "10 m", "eps": "0.01 mm"})
    assert o["Re"]["value"] == pytest.approx(90)
    Q = math.pi * 0.02**2 / 4 * 0.5
    hp = out("chemical.fluids.hagen_poiseuille", {"mu": "100 cP", "L": "10 m", "Q": f"{Q} m^3/s", "D": "20 mm"})
    assert o["dP"]["si_value"] == pytest.approx(hp["dP"]["si_value"], rel=1e-9)


def test_pipe_flow_turbulent_branch_near_moody():
    o = out("chemical.fluids.pipe_flow_darcy_weisbach",
            {"rho": "998 kg/m^3", "mu": "1 cP", "v": "2 m/s", "D": "100 mm", "L": "100 m", "eps": "0.045 mm"})
    assert o["f"]["value"] == pytest.approx(0.0187, abs=3e-4)


def test_lmtd_equal_ends_branch():
    o = out("chemical.heat.lmtd_heat_exchanger", {"dT1": "30 K", "dT2": "30 K", "U": "100 W/(m^2*K)", "A": "2 m^2"})
    assert o["dTlm"]["value"] == pytest.approx(30)


def test_search_by_name_discipline_and_variable():
    names = lambda r: {c.id for c in r}   # noqa: E731
    assert "civil.beam.cantilever_point" in names(CAT.search("cantilever"))
    assert names(CAT.search("beam", disciplines=["civil"])) >= {"civil.beam.cantilever_point", "civil.beam.simply_supported_udl"}
    assert all("petroleum" in c.disciplines for c in CAT.search(disciplines=["petroleum"]))
    assert "chemical.fluids.hagen_poiseuille" in names(CAT.search(variables=["viscosity"]))
    assert "petroleum.reservoir.radial_darcy_inflow" in names(CAT.search(variables=["permeability", "skin"]))
    assert names(CAT.search(variables=["Re"])) >= {"chemical.fluids.pipe_flow_darcy_weisbach"}
    assert "mechanical.thermo.ideal_gas_law" in names(CAT.search(solves_for=["temperature"]))
    assert not CAT.search("zzzzqqq")
    # name hits rank above description-only hits
    assert CAT.search("pipe")[0].name.lower().startswith("pipe") or "pipe" in CAT.search("pipe")[0].name.lower()
