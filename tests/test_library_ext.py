"""Independent hand calculations for the discipline-coverage calculations."""

import math

import pytest

from sliderule.core import solve
from sliderule.core.catalog import default_catalog

CAT = default_catalog()


def out(cid, inputs, **kw):
    s = solve(CAT.get(cid), inputs, **kw)
    assert s.ok, [d.message for d in s.diagnostics]
    return {o["key"]: o for o in s.outputs}


def test_asce7_velocity_pressure_constant_emerges_from_units():
    o = out("civil.wind.velocity_pressure_shedding", {"rho": "0.002377 slug/ft^3", "Vw": "100 mph", "Kz": "1", "Kzt": "1", "Kd": "1", "St": "0.2", "D": "1 ft"})
    assert o["qz"]["value"] == pytest.approx(0.00256 * 100**2, rel=2e-3)


def test_hazen_williams_si_and_us_constants_agree():
    si = out("civil.hydraulics.hazen_williams", {"D": "300 mm", "L": "1000 m", "hf": "5 m", "Cw": "120"})["v"]["si_value"]
    R, S = 0.3 / 4, 5 / 1000
    assert si == pytest.approx(0.849 * 120 * R**0.63 * S**0.54, rel=1e-3)
    us = 1.318 * 120 * (0.3 / 4 / 0.3048) ** 0.63 * S**0.54 * 0.3048   # US-form (ft/s) converted to m/s
    assert si == pytest.approx(us, rel=1e-3)


def test_scs_curve_number_textbook():
    o = out("civil.water.scs_curve_number", {"P": "100 mm", "CN": "80"})
    assert o["Q"]["value"] == pytest.approx((100 - 12.7) ** 2 / (100 + 0.8 * 63.5), rel=1e-6)
    zero = out("civil.water.scs_curve_number", {"P": "5 mm", "CN": "80"})
    assert zero["Q"]["value"] == 0


def test_hohmann_leo_to_geo():
    o = out("space.astronautical.hohmann_transfer", {"r1": "6678 km", "r2": "42164 km"})
    assert o["dvt"]["value"] == pytest.approx(3.89, abs=0.03) and o["tof"]["value"] == pytest.approx(5.28, abs=0.05)


def test_geostationary_radius():
    assert out("space.satellite.geostationary_orbit", {"Tp": "23.9345 h"})["alt"]["value"] == pytest.approx(35786, abs=5)


def test_erlang_b_matches_recursive_definition():
    A, N = 6.0, 10
    inv = 1.0
    for k in range(1, N + 1):
        inv = 1 + inv * k / A
    o = out("computer.teletraffic.erlang_b", {"lam": "120 1/h", "hh": "3 min", "Nc": "10"})
    assert o["Bk"]["value"] / 100 == pytest.approx(1 / inv, rel=1e-6)


def test_enrichment_swu_known_value():
    o = out("nuclear.fuel.enrichment_swu", {"P": "1 kg", "xp": "4.5 %", "xt": "0.25 %", "xf": "0.711 %"})
    assert o["F"]["value"] == pytest.approx(9.219, rel=1e-3) and o["SWU"]["value"] == pytest.approx(6.87, abs=0.05)


def test_stokes_settling_and_reynolds():
    o = out("mechanical.fluids.stokes_settling", {"d": "50 um", "rhop": "2650 kg/m^3", "rhof": "998 kg/m^3", "mu": "1 cP"})
    assert o["vt"]["si_value"] == pytest.approx((2650 - 998) * 9.80665 * (50e-6) ** 2 / (18 * 1e-3), rel=1e-9)


def test_strain_gauge_microstrain_via_ppm():
    o = out("electrical.instrumentation.strain_gauge_bridge", {"GF": "2", "eps": "1000 ppm", "R": "350 ohm", "Vex": "5 V"})
    assert o["Vo"]["si_value"] == pytest.approx(2.5e-3) and o["dR"]["si_value"] == pytest.approx(0.7)


def test_rtd_pt100_100c():
    assert out("electrical.instrumentation.rtd_pt100", {"R0": "100 ohm", "T": "100 Δ°C", "Iex": "1 mA", "dis": "2.5 mW/K"})["RT"]["value"] == pytest.approx(138.51, abs=0.01)


def test_boost_buck_duty():
    assert out("electrical.power_electronics.buck_converter", {"Vin": "12 V", "Vo": "5 V", "L": "47 uH", "fsw": "100 kHz", "Co": "100 uF"})["D"]["value"] == pytest.approx(5 / 12)
    assert out("electrical.power_electronics.boost_converter", {"Vin": "5 V", "Vo": "12 V", "Io": "0.5 A", "L": "22 uH", "fsw": "500 kHz", "Co": "47 uF"})["D"]["value"] == pytest.approx(1 - 5 / 12)


def test_induction_motor_synchronous_speed():
    o = out("electrical.machines.induction_motor", {"f": "50 Hz", "pp": "4", "n": "1450 rpm", "Po": "7.5 kW"})
    assert o["ns"]["value"] == pytest.approx(1500) and o["sl"]["value"] == pytest.approx(100 / 30)


def test_dc_motor_operating_point():
    o = out("electrical.machines.dc_motor", {"Va": "24 V", "Ra": "0.5 ohm", "k": "0.05 N*m/A", "Tl": "0.3 N*m"})
    assert o["Ia"]["value"] == pytest.approx(6) and o["w"]["si_value"] == pytest.approx(420) and o["eff"]["value"] == pytest.approx(87.5)


def test_shannon_and_pcm_use_hz_as_per_second():
    o = out("electrical.telecom.pcm_bitrate_sqnr", {"B": "3.4 kHz", "fs": "8 kHz", "Nb": "8", "ch": "24"})
    assert o["Rbit"]["value"] == pytest.approx(1536) and o["sqdb"]["value"] == pytest.approx(6.02 * 8 + 1.76, abs=0.05)


def test_free_space_link_budget_geo():
    o = out("aerospace.space_systems.link_budget_friis", {"Pt": "20 W", "Gt": "1000", "Gr": "31623", "f": "12 GHz", "d": "35786 km", "Ts": "150 K", "Rb": "10 Mbit/s"})
    assert o["Lfsdb"]["value"] == pytest.approx(205.1, abs=0.1) and o["EbN0db"]["value"] == pytest.approx(19.7, abs=0.1)


def test_dB_arithmetic():
    o = out("mechanical.acoustics.level_combination_distance", {"L1": "80 dB", "L2": "80 dB", "r1": "1 m", "r2": "10 m"})
    assert o["Ls"]["value"] == pytest.approx(83.0103, abs=1e-3) and o["Lr"]["value"] == pytest.approx(63.0103, abs=1e-3)


def test_nernst_and_goldman():
    o = out("biomedical.neural.nernst_goldman", CAT.get("biomedical.neural.nernst_goldman").example)
    assert o["En"]["value"] == pytest.approx(-89.06, abs=0.1) and -75 < o["Vm"]["value"] < -60


def test_pharmacokinetics_half_life():
    o = out("biomedical.pharma.one_compartment_pk", {"Dose": "500 mg", "Vd": "42 L", "CL": "6 L/h", "t": "4.852 h", "Fb": "100 %", "tau": "12 h"})
    assert o["th"]["value"] == pytest.approx(math.log(2) * 42 / 6, rel=1e-9) and o["Ct"]["value"] == pytest.approx(o["C0"]["value"] / 2, rel=1e-3)


def test_michaelis_menten_inhibition():
    o = out("biomedical.biomolecular.michaelis_menten", {"Vmax": "100 umol/(L*min)", "Km": "2 mM", "S": "2 mM", "I": "0 uM", "Ki": "20 uM"})
    assert o["v"]["value"] == pytest.approx(50) and o["vi"]["value"] == pytest.approx(50)


def test_hall_petch_low_carbon_steel():
    assert out("materials.metallurgy.hall_petch", CAT.get("materials.metallurgy.hall_petch").example)["sy"]["value"] == pytest.approx(235, abs=1)


def test_hertz_contact_closed_form():
    o = out("materials.tribology.hertz_sphere_on_flat", {"F": "500 N", "Rs": "10 mm", "E1": "210 GPa", "nu1": "0.3", "E2": "210 GPa", "nu2": "0.3"})
    Es = 210e9 / (2 * (1 - 0.09))
    a = (3 * 500 * 0.01 / (4 * Es)) ** (1 / 3)
    assert o["a"]["si_value"] == pytest.approx(a, rel=1e-9) and o["p0"]["si_value"] == pytest.approx(3 * 500 / (2 * math.pi * a * a), rel=1e-9)


def test_electroplating_thickness_copper():
    o = out("materials.surface.electroplating_thickness", CAT.get("materials.surface.electroplating_thickness").example)
    assert o["th"]["value"] == pytest.approx(63.55 * 0.02 * 30 * 60 * 0.95 / (2 * 96485.33 * 8.96) * 1e4, rel=1e-3)


def test_bond_comminution_work():
    o = out("mining.mineral_processing.bond_comminution", {"Wi": "13 kWh/t", "F80": "10 mm", "P80": "100 um", "th": "200 t/h"})
    assert o["W"]["value"] == pytest.approx(10 * 13 * (1 / 10 - 1 / 100), rel=1e-9)


def test_konya_blast_burden_matches_feet_inches_form():
    o = out("mining.surface.konya_blast_design", {"De": "6.5 in", "re": "0.85 g/cm^3", "rr": "2.7 g/cm^3", "H": "12 m"})
    assert o["B"]["value"] == pytest.approx(3.15 * 6.5 * (0.85 / 2.7) ** (1 / 3) * 0.3048, rel=1e-6)


def test_oil_field_and_drilling_constants():
    assert out("petroleum.drilling.equivalent_circulating_density", {"rm": "10 ppg", "dPa": "250 psi", "D": "10000 ft"})["ECD"]["value"] == pytest.approx(10 + 250 / (0.0519 * 10000), rel=2e-3)
    o = out("petroleum.production.gas_well_inflow", CAT.get("petroleum.production.gas_well_inflow").example)
    field = 0.000703 * 10 * 50 * (3000**2 - 2000**2) / (0.02 * 0.9 * 620 * (math.log(2000 / 0.35) - 0.75))
    assert o["qg"]["value"] == pytest.approx(field, rel=2e-3)
    assert out("petroleum.reservoir.volumetric_gas_in_place", {"A": "1 ac", "h": "1 ft", "phi": "1", "Sw": "0", "Bg": "1"}, output_units={"G": "ft^3"})["G"]["value"] == pytest.approx(43560)


def test_vogel_ipr_endpoints():
    o = out("petroleum.production.vogel_ipr", {"pr": "3000 psi", "pt": "2000 psi", "qt": "800 bpd", "pw": "0 psi"})
    assert o["q"]["value"] == pytest.approx(o["qmax"]["value"])


def test_plank_freezing_slab():
    o = out("chemical.food.plank_freezing_time", CAT.get("chemical.food.plank_freezing_time").example)
    rho, Lf, dT, a, h, k = 1050, 250e3, 28.5, 0.05, 30, 1.6
    assert o["tf"]["si_value"] == pytest.approx(rho * Lf / dT * (0.5 * a / h + 0.125 * a * a / k), rel=1e-9)


def test_ergun_equation_terms():
    o = out("chemical.powder.ergun_packed_bed", {"eb": "0.4", "dp": "3 mm", "us": "0.1 m/s", "mu": "1 cP", "rho": "998 kg/m^3", "Lb": "2 m"})
    e, d, u, mu, rho = 0.4, 0.003, 0.1, 1e-3, 998
    gr = 150 * mu * u * (1 - e) ** 2 / (e**3 * d**2) + 1.75 * rho * u * u * (1 - e) / (e**3 * d)
    assert o["gr"]["si_value"] == pytest.approx(gr, rel=1e-9)


def test_wetland_k_c_star_inverts_the_decay_law():
    o = out("environmental.ecological.wetland_area_kc_star", {"Q": "500 m^3/day", "k": "34 m/yr", "C0": "100 mg/L", "Cs": "10 mg/L", "C": "30 mg/L"})
    A = o["A"]["si_value"]
    q = (500 / 86400) / A * 365.25 * 86400                  # hydraulic loading in m/yr
    assert 10 + (100 - 10) * math.exp(-34 / q) == pytest.approx(30, rel=1e-6)


def test_noise_dose_osha():
    o = out("industrial.human_factors.noise_exposure", {"L": "95 dB", "Lr": "90 dB", "ER": "5 dB", "tx": "4 h"})
    assert o["Tp"]["value"] == pytest.approx(4.0) and o["Dz"]["value"] == pytest.approx(100.0)


def test_niosh_equation_multipliers():
    o = out("industrial.ergonomics.niosh_lifting", {"H": "25 cm", "Vh": "75 cm", "D": "25 cm", "A": "0 deg", "FM": "1", "CM": "1", "Lw": "23 kg"})
    assert o["RWL"]["value"] == pytest.approx(23 * 1 * 1 * (0.82 + 4.5 / 25), rel=1e-9)


def test_npv_annuity():
    o = out("industrial.finance.npv_payback", {"I0": "250000 USD", "CF": "70000 USD/yr", "r": "8 %", "n": "5"})
    assert o["NPV"]["value"] == pytest.approx(-250000 + 70000 * (1 - 1.08**-5) / 0.08, rel=1e-6)


def test_newsvendor_critical_ratio():
    o = out("industrial.operations_research.newsvendor", {"Cu": "6 USD/ea", "Co": "4 USD/ea", "mu": "500 ea", "sg": "80 ea"})
    assert o["zc"]["value"] == pytest.approx(0.2533, abs=1e-3)


def test_computer_amdahl_and_cpu_time():
    o = out("computer.architecture.amdahl_gustafson", {"pf": "95 %", "Np": "64"})
    assert o["Sa"]["value"] == pytest.approx(1 / (0.05 + 0.95 / 64))
    assert out("computer.architecture.cpu_time_mips", {"IC": "5e9", "CPI": "1.4", "fclk": "3.2 GHz"})["Tcpu"]["value"] == pytest.approx(5e9 * 1.4 / 3.2e9)


def test_packet_rate_at_10g():
    assert out("computer.network.packet_rate_utilisation", {"Rb": "10 Gbit/s", "Fs": "64 B", "ov": "20 B", "Lo": "1 Gbit/s"})["pps"]["value"] == pytest.approx(14.881, abs=1e-3)


def test_training_compute_chinchilla_style():
    o = out("computer.ai.training_compute_memory", CAT.get("computer.ai.training_compute_memory").example)
    assert o["Cf"]["value"] == pytest.approx(6 * 7e9 * 1e12, rel=1e-9)


def test_grover_iterations():
    o = out("quantum.computing.grover_search", {"N": "1e6", "M": "1"})
    assert o["k"]["value"] == 785 and o["Ps"]["value"] > 99.9


def test_forcing_co2_doubling():
    o = out("climate.geoengineering.forcing_temperature", {"C": "560 ppm", "C0": "280 ppm", "da": "0", "lam": "0.8 K/(W/m^2)"})
    assert o["dFc"]["value"] == pytest.approx(5.35 * math.log(2), rel=1e-9) and o["dT"]["value"] == pytest.approx(0.8 * 5.35 * math.log(2), rel=1e-9)


def test_return_period_100_year_flood_over_50_years():
    assert out("climate.resilience.return_period_risk", {"T": "100 yr", "n": "50 yr", "Rt": "5 %"})["R"]["value"] == pytest.approx(39.5, abs=0.1)


def test_electrolyzer_specific_energy():
    assert out("energy.hydrogen.electrolyzer", {"P": "5 MW", "eta": "70 %", "t": "24 h"})["sec"]["value"] == pytest.approx(141.8 / 3.6 / 0.7, rel=1e-6)


def test_pv_temperature_derating():
    o = out("energy.solar.pv_power_yield", {"Pstc": "5 kWp", "G": "800 W/m^2", "Ta": "30 degC", "dN": "25 K", "gam": "-0.004 1/K", "PR": "90 %", "PSH": "5 h/day"})
    assert o["P"]["value"] == pytest.approx(5 * 0.8 * (1 - 0.004 * 30) * 0.9, rel=1e-9)


def test_wind_power_betz():
    o = out("energy.wind.turbine_power", {"rho": "1.225 kg/m^3", "Dr": "100 m", "v": "10 m/s", "Cp": "0.45", "eg": "94 %", "CF": "35 %", "Pr": "3000 kW"})
    assert o["Pb"]["value"] == pytest.approx(16 / 27 * o["Pw"]["value"])


def test_diagnostic_ppv_bayes():
    o = out("healthinfo.diagnostics.test_performance", {"se": "92 %", "sp": "95 %", "pv": "2 %"})
    assert o["PPV"]["value"] == pytest.approx(100 * 0.92 * 0.02 / (0.92 * 0.02 + 0.05 * 0.98), rel=1e-9)


def test_mci_fully_linear_is_zero():
    assert out("green.circular_economy.material_circularity_indicator", {"M": "10 kg", "Fr": "0 %", "Fc": "0 %", "Ef": "0 %", "X": "1"})["MCI"]["value"] == pytest.approx(0.1)


def test_mckibben_zero_force_angle():
    o = out("softrobotics.actuators.mckibben_muscle", {"p": "400 kPa", "D0": "20 mm", "th": "54.7356 deg"})
    assert abs(o["F"]["value"]) < 1e-3 and o["thm"]["value"] == pytest.approx(54.7356, abs=1e-3)


def test_robot_pick_and_place_cycle():
    o = out("robotics.industrial.pick_place_cycle", {"d": "300 mm", "vm": "1500 mm/s", "am": "15 m/s^2", "tp": "80 ms", "tq": "60 ms"})
    assert o["tm"]["value"] == pytest.approx(300) and o["tc"]["value"] == pytest.approx(740)
