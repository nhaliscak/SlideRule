"""Core chemistry, part A: general chemistry, thermodynamics, electrochemistry, kinetics, physical chemistry (independent formulas)."""

import math

import pytest
from pcutil import CAT, F, NA, R, atm, c, check_case, e, h, kB, pi, solved

bar = 1e5
cst = 1000.0   # 1 mol/L in mol/m^3
Da = 1.66053906660e-27


def mole(x):
    Vm = R * x["T"] / x["P"]
    n = x["ms"] / x["Mm"]
    return {"n": n, "Np": n * NA, "m1": x["Mm"] / NA, "Vm": Vm, "Vg": n * Vm}


def percent(x):
    M = x["nC"] * x["AC"] + x["nH"] * x["AH"] + x["nO"] * x["AO"]
    return {"Mm": M, "wC": x["nC"] * x["AC"] / M, "wH": x["nH"] * x["AH"] / M, "wO": x["nO"] * x["AO"] / M}


def combustion(x):
    AC, AH, AO = x["AC"], x["AH"], x["AO"]
    mC = x["mCO2"] * AC / (AC + 2 * AO)
    mH = 2 * x["mH2O"] * AH / (2 * AH + AO)
    mO = x["ms"] - mC - mH
    return {"mC": mC, "mH": mH, "mO": mO, "rH": (mH / AH) / (mC / AC), "rO": (mO / AO) / (mC / AC)}


def isotopes(x):
    return {"Mb": x["f1"] * x["m1"] + (1 - x["f1"]) * x["m2"]}


def dumas(x):
    return {"Mm": x["rho"] * R * x["T"] / x["P"], "cg": x["P"] / (R * x["T"]), "Vm": R * x["T"] / x["P"]}


def over_water(x):
    Pg = x["Pa"] - x["Pw"]
    n = Pg * x["Vc"] / (R * x["T"])
    return {"Pg": Pg, "n": n, "mg": n * x["Mm"]}


def mixture(x):
    Mb = x["x1"] * x["M1"] + (1 - x["x1"]) * x["M2"]
    return {"Mb": Mb, "w1": x["x1"] * x["M1"] / Mb, "rho": x["P"] * Mb / (R * x["T"]), "p1": x["x1"] * x["P"]}


def ppm(x):
    return {"cppm": x["cm"] / x["rho"], "cppb": x["cm"] / x["rho"], "cmM": x["cm"] / x["Mm"], "pwv": x["cm"] / 10.0}


def titration(x):
    n = x["Cb"] * x["Vb"] / x["na"]
    return {"nac": n, "mac": n * x["Mm"], "pur": n * x["Mm"] / x["ms"]}


def preparation(x):
    return {"msol": x["Ct"] * x["Vt"] * x["Mm"] / x["pur"], "Vcon": x["Ct"] * x["Vt"] * x["Mm"] / (x["wc"] * x["rc"])}


def ionic(x):
    I = (x["c1"] * x["z1"] ** 2 + x["c2"] * x["z2"] ** 2 + x["c3"] * x["z3"] ** 2) / 2
    s = math.sqrt(I / cst)
    gl = 10 ** (-0.509 * x["z1"] ** 2 * s)
    ge = 10 ** (-0.509 * x["z1"] ** 2 * s / (1 + 0.3281e10 * x["ai"] * s))
    return {"Is": I, "gl": gl, "ge": ge, "a1": ge * x["c1"]}


def atom_economy(x):
    return {"ae": x["Mp"] / (x["n1"] * x["M1"] + x["n2"] * x["M2"]), "Ef": (x["mi"] - x["mpr"]) / x["mpr"], "pmi": x["mi"] / x["mpr"]}


def polarity(x):
    return {"mu": x["qs"] * e * x["dl"] / 3.33564e-30, "ionic": x["mu_obs"] / (e * x["dl"]), "ionp": 1 - math.exp(-x["dchi"] ** 2 / 4)}


def hess(x):
    dH = x["c"] * x["Hc"] + x["d"] * x["Hd"] - x["a"] * x["Ha"] - x["b"] * x["Hb"]
    dS = x["c"] * x["Sc"] + x["d"] * x["Sd"] - x["a"] * x["Sa"] - x["b"] * x["Sb"]
    dG = dH - x["T"] * dS
    return {"dH": dH, "dS": dS, "dG": dG, "K": math.exp(-dG / (R * x["T"]))}


def bonds(x):
    return {"dH": x["nb1"] * x["Db1"] + x["nb2"] * x["Db2"] - x["nf1"] * x["Df1"] - x["nf2"] * x["Df2"]}


def kirchhoff(x):
    dH2 = x["dH1"] + x["dCp"] * (x["T2"] - x["T1"])
    dS2 = x["dS1"] + x["dCp"] * math.log(x["T2"] / x["T1"])
    return {"dH2": dH2, "dS2": dS2, "dG2": dH2 - x["T2"] * dS2}


def crossover(x):
    return {"Tx": x["dH"] / x["dS"], "dG2": x["T2"] * (x["dG1"] / x["T1"] + x["dH"] * (1 / x["T2"] - 1 / x["T1"]))}


def quotient(x):
    K = math.exp(-x["dG0"] / (R * x["T"]))
    return {"dG": x["dG0"] + R * x["T"] * math.log(x["Qr"]), "K": K, "QK": x["Qr"] / K}


def kp_kc(x):
    Kp = x["Kc"] * (cst * R * x["T"] / bar) ** x["dn"]
    return {"Kp": Kp, "Kx": Kp * (x["P"] / bar) ** (-x["dn"])}


def dissociation(x):
    al = math.sqrt(x["Kp"] / (x["Kp"] + 4 * x["P"] / bar))
    return {"al": al, "pA": (1 - al) * x["P"] / (1 + al), "pB": 2 * al * x["P"] / (1 + al), "Mb": x["MA"] / (1 + al)}


def clapeyron(x):
    sl = x["dHf"] / (x["T"] * x["dV"])
    return {"sl": sl, "dP": sl * x["dT"]}


def trouton(x):
    return {"dSv": x["dHv"] / x["Tb"], "dHe": 88 * x["Tb"]}


def flame(x):
    return {"Tad": x["T0"] - x["Hc"] / x["CpT"]}


def antoine(x):
    Pref, T0 = 133.322368 * 1, 273.15
    return {"Pv": Pref * 10 ** (x["Aa"] - x["Bk"] / (x["Ck"] + x["T"] - T0)), "Tb": x["Bk"] / (x["Aa"] - math.log10(x["Pt"] / 133.322368)) - x["Ck"] + T0}


def regular(x):
    x1 = x["x1"]
    dH = x["Om"] * x1 * (1 - x1)
    dS = -R * (x1 * math.log(x1) + (1 - x1) * math.log(1 - x1))
    return {"dH": dH, "dS": dS, "dG": dH - x["T"] * dS, "Tcr": x["Om"] / (2 * R)}


def cell(x):
    E0 = x["Ec"] - x["Ea"]
    return {"E0": E0, "dG": -x["ne"] * F * E0, "K": math.exp(x["ne"] * F * E0 / (R * x["T"]))}


def ph_electrode(x):
    sl = R * x["T"] * math.log(10) / F
    return {"sl": sl, "Ep": x["E0"] - sl * x["pH"], "Ecc": R * x["T"] / (x["ne"] * F) * math.log(x["c2"] / x["c1"])}


def battery(x):
    Qs = x["ne"] * F / x["Mm"]
    return {"Qs": Qs, "Es": Qs * x["Ec"], "Qc": Qs * x["ma"]}


def kohlrausch(x):
    L0 = x["vp"] * x["lp"] + x["vm"] * x["lm"]
    Lm = L0 - x["Kk"] * math.sqrt(x["cm"] / cst)
    return {"L0": L0, "Lm": Lm, "kap": Lm * x["cm"], "tp": x["vp"] * x["lp"] / L0, "up": x["lp"] / F}


def butler(x):
    f = F * x["eta"] / (R * x["T"])
    return {"ib": x["i0"] * (math.exp(x["aa"] * f) - math.exp(-x["ac"] * f)), "bt": R * x["T"] * math.log(10) / (x["aa"] * F)}


def fuel_cell(x):
    Er = -x["dG"] / (x["ne"] * F)
    eth = x["dG"] / x["dH"]
    return {"Er": Er, "eth": eth, "eov": eth * x["Eo"] / Er}


def initial_rates(x):
    n = math.log(x["r2"] / x["r1"]) / math.log(x["c2"] / x["c1"])
    k = x["r1"] / (x["c1"] / cst) ** n
    return {"nn": n, "kr": k, "r3": k * (x["c3"] / cst) ** n}


def arrhenius2(x):
    Ea = R * math.log(x["k2"] / x["k1"]) / (1 / x["T1"] - 1 / x["T2"])
    A = x["k1"] * math.exp(Ea / (R * x["T1"]))
    return {"Ea": Ea, "Af": A, "k3": A * math.exp(-Ea / (R * x["T3"]))}


def consecutive(x):
    A0, k1, k2, t = x["A0"], x["k1"], x["k2"], x["t"]
    A = A0 * math.exp(-k1 * t)
    B = A0 * k1 / (k2 - k1) * (math.exp(-k1 * t) - math.exp(-k2 * t))
    return {"A": A, "B": B, "Cc": A0 - A - B, "tmx": math.log(k2 / k1) / (k2 - k1), "Bmx": A0 * (k1 / k2) ** (k2 / (k2 - k1))}


def parallel(x):
    kt = x["k1"] + x["k2"]
    f = 1 - math.exp(-kt * x["t"])
    return {"kt": kt, "th": math.log(2) / kt, "f1": x["k1"] / kt, "P1": x["A0"] * x["k1"] / kt * f, "P2": x["A0"] * x["k2"] / kt * f}


def lindemann(x):
    return {"ku": x["k1"] * x["k2"] * x["Mc"] / (x["km1"] * x["Mc"] + x["k2"]), "kinf": x["k1"] * x["k2"] / x["km1"], "Mh": x["k2"] / x["km1"]}


def collision(x):
    Z = x["sg"] * math.sqrt(8 * kB * x["T"] / (pi * x["mu"])) * NA
    return {"Zf": Z, "kr": x["Ps"] * Z * math.exp(-x["Ea"] / (R * x["T"]))}


def reversible(x):
    K = x["kf"] / x["kb"]
    Ae = x["A0"] / (1 + K)
    return {"Ke": K, "Ae": Ae, "At": Ae + (x["A0"] - Ae) * math.exp(-(x["kf"] + x["kb"]) * x["t"]), "tau": 1 / (x["kf"] + x["kb"])}


def eyring2(x):
    dH = R * math.log(x["k2"] * x["T1"] / (x["k1"] * x["T2"])) / (1 / x["T1"] - 1 / x["T2"])
    return {"dHa": dH, "dSa": R * math.log(x["k1"] * h / (kB * x["T1"])) + dH / x["T1"]}


def surface(x):
    d = 1 + x["KA"] * x["pA"] + x["KB"] * x["pB"]
    return {"rLH": x["kr"] * x["KA"] * x["pA"] * x["KB"] * x["pB"] / d**2, "rER": x["kr"] * x["KA"] * x["pA"] * (x["pB"] / bar) / (1 + x["KA"] * x["pA"]), "thA": x["KA"] * x["pA"] / d}


def eos(x):
    Tc, Pc, T, V = x["Tc"], x["Pc"], x["T"], x["Vm"]
    a, b = 27 * R**2 * Tc**2 / (64 * Pc), R * Tc / (8 * Pc)
    aR, bR = 0.42748 * R**2 * Tc**2.5 / Pc, 0.08664 * R * Tc / Pc
    Pv = R * T / (V - b) - a / V**2
    Pr = R * T / (V - bR) - aR / (math.sqrt(T) * V * (V + bR))
    return {"a": a, "b": b, "aR": aR, "bR": bR, "Pid": R * T / V, "Pv": Pv, "Pr": Pr, "Zv": Pv * V / (R * T), "Zr": Pr * V / (R * T)}


def virial(x):
    Z = 1 + x["Bv"] * x["P"] / (R * x["T"])
    return {"Zc": Z, "Vm": Z * R * x["T"] / x["P"], "dev": Z - 1}


def joule_thomson(x):
    return {"mj": (2 * x["a"] / (R * x["T"]) - x["b"]) / x["Cp"], "Ti": 2 * x["a"] / (R * x["b"])}


def adsorption(x):
    xr, cb = x["xr"], x["cb"]
    return {"Vb": x["Vmo"] * cb * xr / ((1 - xr) * (1 - xr + cb * xr)), "SA": x["Vmo"] / 22414e-6 * NA * x["sgN"], "qf": x["Kf"] * (x["Cf"] / 1e-3) ** (1 / x["nf"])}


def diffusion(x):
    return {"J": x["D"] * x["dc"] / x["Ld"], "td": x["Ld"] ** 2 / (2 * x["D"]), "xr": math.sqrt(2 * x["D"] * x["tt"])}


def gas_transport(x):
    m = x["Mm"] / NA
    eta = 5 * math.sqrt(m * kB * x["T"] / pi) / (16 * x["dm"] ** 2)
    return {"mm": m, "eta": eta, "kg": 15 * kB * eta / (4 * m), "Ds": 3 * kB * x["T"] / (8 * x["P"] * x["dm"] ** 2) * math.sqrt(kB * x["T"] / (pi * m))}


def raoult(x):
    P = x["x1"] * x["P1s"] + (1 - x["x1"]) * x["P2s"]
    return {"Pb": P, "y1": x["x1"] * x["P1s"] / P, "al": x["P1s"] / x["P2s"], "Pd": 1 / (x["yd"] / x["P1s"] + (1 - x["yd"]) / x["P2s"])}


def extraction(x):
    K, Va, Vo, n = x["Kd"], x["Va"], x["Vo"], x["nx"]
    return {"E1": K * Vo / (Va + K * Vo), "fn": (Va / (Va + K * Vo)) ** n, "fo": Va / (Va + K * n * Vo)}


def partition(x):
    m = x["Mm"] / NA
    L = h / math.sqrt(2 * pi * m * kB * x["T"])
    qr = x["T"] / (x["sy"] * x["thr"])
    return {"mm": m, "Lm": L, "qt": kB * x["T"] / (x["P"] * L**3), "qr": qr, "qv": 1 / (1 - math.exp(-x["thv"] / x["T"])), "Sr": R * (math.log(qr) + 1)}


CASES = {
    "chemistry.general.mole_conversions": mole, "chemistry.general.percent_composition": percent, "chemistry.general.combustion_analysis": combustion, "chemistry.general.isotopic_average_mass": isotopes,
    "chemistry.general.gas_density_molar_mass": dumas, "chemistry.general.gas_collected_over_water": over_water, "chemistry.general.gas_mixture_molar_mass": mixture,
    "chemistry.general.concentration_units_ppm": ppm, "chemistry.general.titration_standardisation": titration, "chemistry.general.solution_preparation": preparation,
    "chemistry.general.ionic_strength_activity": ionic, "chemistry.general.atom_economy_efactor": atom_economy, "chemistry.general.bond_polarity_dipole": polarity,
    "chemistry.thermo.hess_reaction_thermodynamics": hess, "chemistry.thermo.bond_enthalpy_estimate": bonds, "chemistry.thermo.kirchhoff_temperature_dependence": kirchhoff,
    "chemistry.thermo.gibbs_helmholtz_crossover": crossover, "chemistry.thermo.reaction_quotient_gibbs": quotient, "chemistry.thermo.kp_kc_conversion": kp_kc,
    "chemistry.thermo.gas_dissociation_equilibrium": dissociation, "chemistry.thermo.clapeyron_melting": clapeyron, "chemistry.thermo.trouton_rule": trouton,
    "chemistry.thermo.adiabatic_flame_temperature": flame, "chemistry.thermo.antoine_vapour_pressure": antoine, "chemistry.thermo.regular_solution_mixing": regular,
    "chemistry.electro.standard_cell_potential": cell, "chemistry.electro.ph_electrode_concentration_cell": ph_electrode, "chemistry.electro.battery_capacity": battery,
    "chemistry.electro.conductivity_kohlrausch": kohlrausch, "chemistry.electro.butler_volmer": butler, "chemistry.electro.fuel_cell_efficiency": fuel_cell,
    "chemistry.kinetics.initial_rates_order": initial_rates, "chemistry.kinetics.arrhenius_two_point": arrhenius2, "chemistry.kinetics.consecutive_reactions": consecutive,
    "chemistry.kinetics.parallel_reactions": parallel, "chemistry.kinetics.lindemann_hinshelwood": lindemann, "chemistry.kinetics.collision_theory": collision,
    "chemistry.kinetics.reversible_first_order": reversible, "chemistry.kinetics.eyring_two_point": eyring2, "chemistry.kinetics.surface_catalysis": surface,
    "chemistry.physical.eos_critical_constants": eos, "chemistry.physical.virial_compressibility": virial, "chemistry.physical.joule_thomson": joule_thomson,
    "chemistry.physical.adsorption_bet_freundlich": adsorption, "chemistry.physical.diffusion_fick": diffusion, "chemistry.physical.gas_transport_properties": gas_transport,
    "chemistry.physical.raoult_binary_vle": raoult, "chemistry.physical.solvent_extraction": extraction, "chemistry.physical.partition_functions": partition,
}


@pytest.mark.parametrize("cid", list(CASES))
def test_against_the_textbook_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


# ---------------------------------------------------------------- identities, limits and benchmarks
def test_one_mole_of_gas_at_stp_is_22_4_litres():
    out = solved("chemistry.general.mole_conversions")
    assert out["Vg"] * 1e3 == pytest.approx(22.414, abs=1e-3) and out["Np"] == pytest.approx(NA)


def test_glucose_composition_adds_to_100_percent():
    out = solved("chemistry.general.percent_composition")
    assert out["wC"] + out["wH"] + out["wO"] == pytest.approx(1) and out["Mm"] * 1e3 == pytest.approx(180.16, abs=0.01)


def test_ethanol_combustion_gives_c2h6o():
    out = solved("chemistry.general.combustion_analysis")
    assert out["rH"] == pytest.approx(3, rel=0.01) and out["rO"] == pytest.approx(0.5, rel=0.01)


def test_chlorine_average_atomic_mass():
    assert solved("chemistry.general.isotopic_average_mass")["Mb"] / Da == pytest.approx(35.453, abs=0.001)


def test_dry_air_molar_mass():
    assert solved("chemistry.general.gas_mixture_molar_mass", x1="0.21", M1="32.00 g/mol", M2="28.01 g/mol")["Mb"] * 1e3 == pytest.approx(28.85, abs=0.01)


def test_one_milligram_per_litre_of_water_is_one_ppm():
    assert solved("chemistry.general.concentration_units_ppm", cm="1 mg/L")["cppm"] == pytest.approx(1e-6)


def test_khp_standardisation_is_close_to_pure():
    assert solved("chemistry.general.titration_standardisation")["pur"] == pytest.approx(1.0, abs=1e-3)


def test_activity_coefficients_of_calcium_chloride():
    out = solved("chemistry.general.ionic_strength_activity")
    assert out["Is"] == pytest.approx(30) and out["ge"] > out["gl"] and 0 < out["gl"] < 1       # I = 0.030 mol/L
    assert solved("chemistry.general.ionic_strength_activity", c1="1e-10 mol/L", c2="2e-10 mol/L")["gl"] == pytest.approx(1, abs=1e-4)       # infinite dilution


def test_aspirin_atom_economy_is_75_percent():
    assert solved("chemistry.general.atom_economy_efactor")["ae"] == pytest.approx(0.75, abs=1e-3)


def test_haber_process_at_298_k():
    out = solved("chemistry.thermo.hess_reaction_thermodynamics")
    assert out["dG"] / 1e3 == pytest.approx(-32.7, abs=0.1) and out["K"] == pytest.approx(5.4e5, rel=0.01)
    assert solved("chemistry.thermo.hess_reaction_thermodynamics", T="700 K")["K"] < 1                  # exothermic: K falls with temperature


def test_methane_combustion_from_bond_enthalpies():
    assert solved("chemistry.thermo.bond_enthalpy_estimate")["dH"] / 1e3 == pytest.approx(-802)


def test_kirchhoff_with_zero_heat_capacity_change_changes_nothing():
    out = solved("chemistry.thermo.kirchhoff_temperature_dependence", dCp="0 J/(mol*K)")
    assert out["dH2"] == pytest.approx(-91.8e3) and out["dS2"] == pytest.approx(-198.1)


def test_limestone_decomposition_crossover_and_gibbs_helmholtz_identity():
    assert solved("chemistry.thermo.gibbs_helmholtz_crossover")["Tx"] == pytest.approx(1111, abs=1)
    assert solved("chemistry.thermo.gibbs_helmholtz_crossover", T2="298.15 K")["dG2"] == pytest.approx(130.4e3)


def test_gibbs_energy_vanishes_when_q_equals_k():
    K = solved("chemistry.thermo.reaction_quotient_gibbs")["K"]
    out = solved("chemistry.thermo.reaction_quotient_gibbs", Qr=str(K))
    assert out["dG"] == pytest.approx(0, abs=1e-6) and out["QK"] == pytest.approx(1)


def test_kp_equals_kc_when_the_gas_moles_do_not_change():
    assert solved("chemistry.thermo.kp_kc_conversion", dn="0")["Kp"] == pytest.approx(0.0059)


def test_dissociation_is_complete_at_vanishing_pressure_and_n2o4_at_one_bar():
    assert solved("chemistry.thermo.gas_dissociation_equilibrium", P="1e-6 bar")["al"] == pytest.approx(1, abs=1e-3)
    assert solved("chemistry.thermo.gas_dissociation_equilibrium")["al"] == pytest.approx(0.1845, abs=1e-3)
    out = solved("chemistry.thermo.gas_dissociation_equilibrium")
    assert out["pA"] + out["pB"] == pytest.approx(1e5 * (1 - out["al"] + 2 * out["al"]) / (1 + out["al"]))


def test_ice_melts_under_pressure_with_a_negative_slope():
    assert solved("chemistry.thermo.clapeyron_melting")["sl"] / 1e6 == pytest.approx(-13.5, abs=0.05)


def test_trouton_constant_for_benzene():
    assert solved("chemistry.thermo.trouton_rule")["dSv"] == pytest.approx(87.2, abs=0.1)


def test_water_boils_at_100_celsius_by_the_antoine_equation():
    assert solved("chemistry.thermo.antoine_vapour_pressure")["Tb"] == pytest.approx(373.15, abs=0.01)


def test_regular_solution_curve_is_convex_above_the_critical_temperature_and_a_double_well_below():
    def curve(T):
        return [solved("chemistry.thermo.regular_solution_mixing", x1=str(x), T=f"{T} K")["dG"] for x in (0.4, 0.5, 0.6)]
    hot, cold = curve(700), curve(500)
    assert hot[1] < (hot[0] + hot[2]) / 2          # convex: no miscibility gap
    assert cold[1] > (cold[0] + cold[2]) / 2       # concave at the centre: the solution separates


def test_daniell_cell_and_ph_electrode_slopes():
    assert solved("chemistry.electro.standard_cell_potential")["E0"] == pytest.approx(1.1)
    out = solved("chemistry.electro.ph_electrode_concentration_cell")
    assert out["sl"] * 1e3 == pytest.approx(59.16, abs=0.01) and out["Ecc"] == pytest.approx(2 * out["sl"])     # a hundredfold ratio


def test_lithium_iron_phosphate_capacity():
    assert solved("chemistry.electro.battery_capacity")["Qs"] / 3600 == pytest.approx(169.9, abs=0.1)         # C/kg -> mAh/g


def test_sodium_chloride_limiting_conductivity():
    assert solved("chemistry.electro.conductivity_kohlrausch")["L0"] * 1e3 == pytest.approx(12.64, abs=0.01)


def test_symmetric_butler_volmer_is_a_hyperbolic_sine():
    out = solved("chemistry.electro.butler_volmer")
    assert out["ib"] == pytest.approx(2 * 1e-3 * 1e4 * math.sinh(F * 0.1 / (2 * R * 298.15)), rel=1e-9) and out["bt"] * 1e3 == pytest.approx(118.3, abs=0.1)


def test_hydrogen_oxygen_fuel_cell():
    out = solved("chemistry.electro.fuel_cell_efficiency")
    assert out["Er"] == pytest.approx(1.229, abs=1e-3) and out["eth"] == pytest.approx(0.83, abs=0.001)


def test_second_order_reaction_has_the_right_order():
    assert solved("chemistry.kinetics.initial_rates_order")["nn"] == pytest.approx(2)


def test_eyring_and_arrhenius_activation_energies_differ_by_rt():
    Ea = solved("chemistry.kinetics.arrhenius_two_point")["Ea"]
    dH = solved("chemistry.kinetics.eyring_two_point")["dHa"]
    assert Ea - dH == pytest.approx(R * 310, rel=0.02)


def test_intermediate_peaks_at_the_predicted_time():
    out = solved("chemistry.kinetics.consecutive_reactions")
    at_peak = solved("chemistry.kinetics.consecutive_reactions", t=f"{out['tmx']} s")["B"]
    assert at_peak == pytest.approx(out["Bmx"]) and at_peak >= solved("chemistry.kinetics.consecutive_reactions", t="20 s")["B"]


def test_parallel_products_add_up_to_the_reacted_amount():
    out = solved("chemistry.kinetics.parallel_reactions")
    assert out["P1"] + out["P2"] == pytest.approx(1000 * (1 - math.exp(-0.04 * 20)))


def test_lindemann_limits():
    assert solved("chemistry.kinetics.lindemann_hinshelwood", Mc="1000 mmol/L")["ku"] == pytest.approx(solved("chemistry.kinetics.lindemann_hinshelwood")["kinf"], rel=2e-3)
    low = solved("chemistry.kinetics.lindemann_hinshelwood", Mc="1e-9 mmol/L")["ku"]
    assert low == pytest.approx(1e3 * 1e-9, rel=1e-4)                       # k1[M]: k1 = 1e6 L/(mol s) = 1e3 m^3/(mol s), [M] = 1e-9 mol/m^3


def test_reversible_reaction_reaches_the_equilibrium_value():
    assert solved("chemistry.kinetics.reversible_first_order", t="1000 s")["At"] == pytest.approx(solved("chemistry.kinetics.reversible_first_order")["Ae"], rel=1e-6)


def test_surface_coverages_cannot_exceed_one():
    assert 0 < solved("chemistry.kinetics.surface_catalysis")["thA"] < 1


def test_carbon_dioxide_van_der_waals_constants_and_attraction():
    out = solved("chemistry.physical.eos_critical_constants")
    assert out["a"] == pytest.approx(0.364, rel=0.01)                      # 3.64 L^2 bar/mol^2 in Pa m^6/mol^2
    assert out["Pv"] < out["Pid"] and out["Pr"] < out["Pid"] and out["Zv"] < 1


def test_virial_coefficient_signs():
    assert solved("chemistry.physical.virial_compressibility")["Zc"] < 1 < solved("chemistry.physical.virial_compressibility", Bv="+20 cm^3/mol")["Zc"]


def test_joule_thomson_coefficient_vanishes_at_the_inversion_temperature():
    Ti = solved("chemistry.physical.joule_thomson")["Ti"]
    assert solved("chemistry.physical.joule_thomson", T=f"{Ti} K")["mj"] == pytest.approx(0, abs=1e-12)


def test_bet_isotherm_and_surface_area():
    assert solved("chemistry.physical.adsorption_bet_freundlich")["SA"] == pytest.approx(130.6e3, rel=2e-3)
    assert solved("chemistry.physical.adsorption_bet_freundlich", nf="1")["qf"] == pytest.approx(5e-3 * 20, rel=1e-9)          # linear isotherm


def test_diffusion_time_of_a_millimetre():
    assert solved("chemistry.physical.diffusion_fick")["td"] == pytest.approx(500)


def test_argon_viscosity():
    assert solved("chemistry.physical.gas_transport_properties")["eta"] * 1e6 == pytest.approx(22.6, rel=0.04)


def test_raoult_limits_and_dew_bubble_consistency():
    assert solved("chemistry.physical.raoult_binary_vle", x1="1")["Pb"] == pytest.approx(100.9e3) and solved("chemistry.physical.raoult_binary_vle", x1="0")["Pb"] == pytest.approx(38.8e3)
    out = solved("chemistry.physical.raoult_binary_vle")
    assert solved("chemistry.physical.raoult_binary_vle", yd=str(out["y1"]))["Pd"] == pytest.approx(out["Pb"])


def test_several_small_extractions_beat_one_large():
    out = solved("chemistry.physical.solvent_extraction")
    assert out["fn"] < out["fo"] and solved("chemistry.physical.solvent_extraction", nx="1")["fn"] == pytest.approx(solved("chemistry.physical.solvent_extraction", nx="1")["fo"])


def test_hydrogen_chloride_rotational_entropy():
    assert solved("chemistry.physical.partition_functions")["Sr"] == pytest.approx(33.06, abs=0.05)


def test_chemistry_core_a_catalogued_under_chemistry_and_new_subdisciplines():
    for cid in CASES:
        assert "chemistry" in CAT.get(cid).disciplines
    assert "Electrochemistry" in CAT.get("chemistry.electro.butler_volmer").subdisciplines and "Chemical Kinetics" in CAT.get("chemistry.kinetics.arrhenius_two_point").subdisciplines
    assert atm > 0 and c > 0
