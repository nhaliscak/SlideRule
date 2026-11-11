"""Broad chemistry, part B: colloids, biochemistry, atmosphere, organic/inorganic extras (independent formulas, SI quantities)."""

import math

import pytest
from pcutil import CAT, NA, R, c, check_case, e, eps0, g, h, kB, pi, solved

CO = "chemistry.colloid."
BI = "chemistry.biochem."
AT = "chemistry.atmos."
cst = 1000.0
Da = 1.66053906660e-27


def debye(x):
    n0 = NA * x["Ic"]
    ld = math.sqrt(eps0 * x["er"] * kB * x["T"] / (2 * NA * e**2 * x["Ic"]))
    return {"ld": ld, "sg": math.sqrt(8 * eps0 * x["er"] * kB * x["T"] * n0) * math.sinh(e * x["psi"] / (2 * kB * x["T"])), "px": x["psi"] * math.exp(-x["xd"] / ld), "ccc": x["zc"] ** -6}


def zeta(x):
    ka = x["ap"] / x["ld"]
    fk = 1 + 1 / (2 * (1 + 2.5 / (ka * (1 + 2 * math.exp(-ka)))) ** 3)
    return {"zs": x["eta"] * x["mob"] / (eps0 * x["er"]), "zh": 1.5 * x["eta"] * x["mob"] / (eps0 * x["er"]), "ka": ka, "fk": fk, "zz": 1.5 * x["eta"] * x["mob"] / (eps0 * x["er"] * fk)}


def kelvin(x):
    a = 2 * x["gm"] * x["Vm"] / (x["rd"] * R * x["T"])
    return {"pdr": math.exp(a), "pcn": math.exp(-a), "dP": 2 * x["gm"] / x["rd"], "rcr": 2 * x["gm"] * x["Vm"] / (R * x["T"] * math.log(x["Sr"]))}


def langmuir(x):
    KA, KB, pA, pB = x["KA"], x["KB"], x["pA"], x["pB"]
    s = math.sqrt(x["Kd"] * pA)
    return {"th1": KA * pA / (1 + KA * pA), "thA": KA * pA / (1 + KA * pA + KB * pB), "thB": KB * pB / (1 + KA * pA + KB * pB), "thd": s / (1 + s), "p12": 1 / KA}


def szysz(x):
    Pi_ = R * x["T"] * x["Gm"] * math.log(1 + x["Ks"] * x["cs"])
    Gx = x["Gm"] * x["Ks"] * x["cs"] / (1 + x["Ks"] * x["cs"])
    return {"Pi": Pi_, "gam": x["g0"] - Pi_, "Gx": Gx, "Ax": 1 / (NA * Gx), "As": 1 / (NA * x["Gm"])}


def wetting(x):
    cth = (x["gSV"] - x["gSL"]) / x["gLV"]
    return {"cth": cth, "th": math.acos(cth), "Wa": x["gLV"] * (1 + cth), "Sp": x["gSV"] - x["gSL"] - x["gLV"], "thW": math.acos(x["rw"] * cth), "thC": math.acos(x["fs"] * (cth + 1) - 1)}


def micelle(x):
    v = 27.4e-30 + 26.9e-30 * x["nC"]
    lc = 1.5e-10 + 1.265e-10 * x["nC"]
    P = v / (x["a0"] * lc)
    return {"vt": v, "lc": lc, "Pk": P, "sh": 1 if P < 1 / 3 else 2 if P < 1 / 2 else 3 if P < 1 else 4, "Nag": 4 * pi * lc**3 / (3 * v)}


def inhibition(x):
    V_, K, S, I, Ki = x["Vmax"], x["Km"], x["S"], x["I"], x["Ki"]
    v0 = V_ * S / (K + S)
    vc = V_ * S / (K * (1 + I / Ki) + S)
    vu = V_ * S / (K + S * (1 + I / Ki))
    vn = V_ * S / ((K + S) * (1 + I / Ki))
    return {"v0": v0, "vc": vc, "vu": vu, "vn": vn, "ic": 1 - vc / v0, "iu": 1 - vu / v0, "inn": 1 - vn / v0, "IC50": Ki * (1 + S / K)}


def hill(x):
    sat = lambda p: (p / x["p50"]) ** x["nH"] / (1 + (p / x["p50"]) ** x["nH"])
    return {"Ya": sat(x["pa"]), "Yv": sat(x["pv"]), "pt": x["p50"] * (x["Ys"] / (1 - x["Ys"])) ** (1 / x["nH"]), "sl": x["nH"] / 4, "dO": 1.34e-3 * x["Hb"] * (sat(x["pa"]) - sat(x["pv"]))}


def binding(x):
    dG = R * x["T"] * math.log(x["Kd"] / cst)
    TdS = dG - x["dH"]
    return {"dG": dG, "TdS": TdS, "dS": -TdS / x["T"], "LE": -dG / x["Nha"], "th": x["Lc"] / (x["Kd"] + x["Lc"])}


def unfolding(x):
    dHm, Tm, dCp, T = x["dHm"], x["Tm"], x["dCp"], x["T"]
    G = lambda t: dHm * (1 - t / Tm) + dCp * (t - Tm - t * math.log(t / Tm))
    K = math.exp(-G(T) / (R * T))
    Ts = Tm * math.exp(-dHm / (dCp * Tm))
    return {"dG": G(T), "Ku": K, "fU": K / (1 + K), "Ts": Ts, "dGs": G(Ts)}


def aminoacid(x):
    pKC, pKN, pKR, rt, pH = x["pKC"], x["pKN"], x["pKR"], x["rt"], x["pH"]
    q = 1 / (1 + 10 ** (pH - pKN)) - 1 / (1 + 10 ** (pKC - pH))
    if rt > 0:
        q += 1 / (1 + 10 ** (pH - pKR))
    elif rt < 0:
        q -= 1 / (1 + 10 ** (pKR - pH))
    pI = (pKN + pKR) / 2 if rt > 0 else (pKC + pKR) / 2 if rt < 0 else (pKC + pKN) / 2
    return {"Qn": q, "pI": pI}


def svedberg(x):
    Mm = x["sS"] * 1e-13 * R * x["T"] / (x["D"] * (1 - x["vb"] * x["rhoS"]))
    f = kB * x["T"] / x["D"]
    f0 = 6 * pi * x["eta"] * (3 * x["vb"] * Mm / (4 * pi * NA)) ** (1 / 3)
    return {"Mm": Mm, "f": f, "f0": f0, "fr": f / f0}


def dna(x):
    Tm = 354.65 + 16.6 * math.log10(x["Na"] / cst) + 41 * x["gc"] - 600 / x["Nbp"]
    return {"Tm": Tm, "Tw": 273.15 + 2 * x["nAT"] + 4 * x["nGC"]}


def atp(x):
    Q = x["ADP"] * x["Pi"] / x["ATP"]
    return {"Qr": Q, "dG": x["dG0"] + R * x["T"] * math.log(Q / cst), "rat": x["ATP"] / x["ADP"], "ec": (x["ATP"] + x["ADP"] / 2) / (x["ATP"] + x["ADP"] + x["AMP"])}


def lifetime(x):
    J = x["sg"] * x["ph"] * x["Fa"]
    kO = x["kOH"] * x["OH"]
    return {"J": J, "kO": kO, "tO": 1 / kO, "tJ": 1 / J, "tt": 1 / (kO + J), "fO": kO / (kO + J)}


def chapman(x):
    O2 = x["fO2"] * x["M"]
    O3 = O2 * math.sqrt(x["J2"] * x["k2"] * x["M"] / (x["J3"] * x["k4"]))
    return {"O2": O2, "O3": O3, "xO3": O3 / x["M"]}


def rain(x):
    pc = x["xC"] * x["Ptot"]
    Kc_si = 0.034e3 / 101325.0 * 4.45e-4 * pc                                 # K_H [mol/(m^3 Pa)] * Ka1 [mol/m^3] * p [Pa] -> mol^2/m^6
    h0 = math.sqrt(Kc_si)
    hh = (x["Cs"] + math.sqrt(x["Cs"] ** 2 + 4 * Kc_si)) / 2
    return {"pc": pc, "Kc": Kc_si, "h0": h0, "pH0": -math.log10(h0 / cst), "h": hh, "pH": -math.log10(hh / cst)}


def visibility(x):
    bR = 0.012e-3
    bm = x["ae"] * x["Cm"] + bR
    bn = x["Nn"] * x["Qe"] * pi * x["rp"] ** 2 + bR
    return {"bm": bm, "bn": bn, "Vm": 3.912 / bm, "Vn": 3.912 / bn}


def dobson(x):
    Nc = x["DU"] * 101325 * 10e-6 / (kB * 273.15)
    Na = x["ps"] * NA / (28.97e-3 * g)
    return {"Nc": Nc, "th": x["DU"] * 10e-6, "Na": Na, "xm": Nc / Na}


def ring(x):
    Es = x["Hc"] - x["nr"] * 658.6e3
    return {"Es": Es, "Eps": Es / x["nr"], "dB": (109.47 * pi / 180 - pi * (x["nr"] - 2) / x["nr"]) / 2}


def selectivity(x):
    er = math.exp(x["ddG"] / (R * x["T"]))
    return {"er": er, "ee": (er - 1) / (er + 1), "fm": er / (1 + er), "dreq": R * x["T"] * math.log((1 + x["eet"]) / (1 - x["eet"]))}


def control(x):
    RT = R * x["T"]
    kr = kB * x["T"] / h * math.exp(-(x["GkA"] - x["GA"]) / RT)
    return {"rk": math.exp(-(x["GkA"] - x["GkB"]) / RT), "rt": math.exp(-(x["GA"] - x["GB"]) / RT), "kr": kr, "th": math.log(2) / kr}


def kie(x):
    mH, mD, mX = 1.00782503223, 2.01410177812, x["mX"] / Da
    rr = math.sqrt((mX * mH / (mX + mH)) / (mX * mD / (mX + mD)))
    return {"rr": rr, "KIE": math.exp(h * c * x["nuH"] * (1 - rr) / (2 * kB * x["T"]))}


def lever(x):
    fb = (x["z"] - x["xa"]) / (x["xb"] - x["xa"])
    return {"F": x["Cn"] - x["Pn"] + 2, "Fc": x["Cn"] - x["Pn"] + 1, "fb": fb, "fa": 1 - fb, "mb": fb * x["mt"]}


def electrons(x):
    tot = x["gr"] + 2 * x["n2"] + x["n1"] + 3 * x["n3"] + 5 * x["n5"] + 6 * x["n6"] - x["q"]
    return {"tot": tot, "gap": 18 - tot, "dn": x["gr"] - x["ox"], "ok": 1 if tot == 18 else 0}


def bvs(x):
    s = math.exp((x["R0"] - x["Rb"]) / x["bb"])
    return {"s": s, "BVS": x["nb"] * s, "dev": (x["nb"] * s - x["Vx"]) / x["Vx"]}


def perovskite(x):
    t = (x["rA"] + x["rX"]) / (math.sqrt(2) * (x["rB"] + x["rX"]))
    return {"tt": t, "mu": x["rB"] / x["rX"], "cl": 0 if t < 0.71 else 1 if t < 0.9 else 2 if t < 1.05 else 3}


CASES = {
    CO + "debye_double_layer": debye, CO + "electrophoretic_zeta_potential": zeta, CO + "kelvin_equation": kelvin, CO + "competitive_langmuir_adsorption": langmuir, CO + "surfactant_gibbs_szyszkowski": szysz,
    CO + "contact_angle_wetting": wetting, CO + "micelle_packing_parameter": micelle, BI + "enzyme_inhibition_modes": inhibition, BI + "hill_cooperativity_oxygen": hill, BI + "ligand_binding_thermodynamics": binding,
    BI + "protein_unfolding_two_state": unfolding, BI + "amino_acid_charge_isoelectric": aminoacid, BI + "svedberg_sedimentation": svedberg, BI + "dna_melting_temperature": dna, BI + "atp_hydrolysis_free_energy": atp,
    AT + "lifetime_oh_photolysis": lifetime, AT + "chapman_ozone": chapman, AT + "rain_ph_co2_acid": rain, AT + "visibility_extinction": visibility, AT + "ozone_column_dobson": dobson,
    "chemistry.organic.ring_strain_cycloalkane": ring, "chemistry.organic.selectivity_ddg_enantiomeric_excess": selectivity, "chemistry.organic.kinetic_vs_thermodynamic_control": control,
    "chemistry.organic.kinetic_isotope_effect": kie, "chemistry.physical.phase_rule_lever_rule": lever, "chemistry.inorganic.electron_count_18": electrons, "chemistry.inorganic.bond_valence_sum": bvs,
    "chemistry.inorganic.perovskite_tolerance_factor": perovskite,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


def test_debye_length_of_decimolar_and_millimolar_salt():
    assert solved(CO + "debye_double_layer", Ic="100 mmol/L")["ld"] * 1e9 == pytest.approx(0.96, abs=0.01)
    assert solved(CO + "debye_double_layer", Ic="1 mmol/L")["ld"] * 1e9 == pytest.approx(9.6, abs=0.1)


def test_henry_function_between_the_smoluchowski_and_huckel_limits():
    assert solved(CO + "electrophoretic_zeta_potential", ap="1e6 nm")["fk"] == pytest.approx(1.5, rel=1e-3)
    assert solved(CO + "electrophoretic_zeta_potential", ap="1e-3 nm")["fk"] == pytest.approx(1.0, rel=1e-3)


def test_kelvin_ratios_are_reciprocal_and_wetting_limits():
    out = solved(CO + "kelvin_equation")
    assert out["pdr"] * out["pcn"] == pytest.approx(1)
    assert solved(CO + "contact_angle_wetting", gSV="100 mN/m", gSL="30 mN/m", rw="1")["th"] < 0.4


def test_langmuir_competition_reduces_coverage_and_micelle_shape_changes_with_head_area():
    out = solved(CO + "competitive_langmuir_adsorption")
    assert out["thA"] < out["th1"]
    assert solved(CO + "micelle_packing_parameter", a0="35 angstrom^2")["sh"] == 3 and solved(CO + "micelle_packing_parameter", a0="50 angstrom^2")["sh"] == 2


def test_inhibition_ordering_and_competitive_overcome_by_substrate():
    out = solved(BI + "enzyme_inhibition_modes")
    assert out["vn"] < out["vc"] < out["v0"]
    assert solved(BI + "enzyme_inhibition_modes", S="1e6 mmol/L")["ic"] < 1e-3


def test_haemoglobin_half_saturation_and_lysozyme_stability():
    assert solved(BI + "hill_cooperativity_oxygen", pa="3.5 kPa")["Ya"] == pytest.approx(0.5)
    out = solved(BI + "protein_unfolding_two_state", T="348 K")
    assert out["dG"] == pytest.approx(0, abs=1e-6) and out["fU"] == pytest.approx(0.5)


def test_lysine_alanine_isoelectric_points_and_charge_at_pI():
    assert solved(BI + "amino_acid_charge_isoelectric")["pI"] == pytest.approx(9.74)
    ala = solved(BI + "amino_acid_charge_isoelectric", pKC="2.34", pKN="9.69", rt="0", pH="6.015")
    assert ala["pI"] == pytest.approx(6.015) and ala["Qn"] == pytest.approx(0, abs=1e-6)


def test_ten_nanomolar_binding_free_energy_and_atp_physiology():
    assert solved(BI + "ligand_binding_thermodynamics")["dG"] / 1e3 == pytest.approx(-45.7, abs=0.05)
    assert solved(BI + "atp_hydrolysis_free_energy")["dG"] / 1e3 == pytest.approx(-53, abs=1)


def test_acid_rain_ph_limits_and_chapman_ozone_scaling():
    assert solved(AT + "rain_ph_co2_acid")["pH0"] == pytest.approx(5.6, abs=0.05)
    assert solved(AT + "rain_ph_co2_acid", Cs="1e-9 umol/L")["pH"] == pytest.approx(solved(AT + "rain_ph_co2_acid")["pH0"], abs=1e-6)
    a = solved(AT + "chapman_ozone")["O3"]
    assert solved(AT + "chapman_ozone", J2="1.2e-11 1/s")["O3"] == pytest.approx(2 * a, rel=1e-9)


def test_dobson_conversion_and_ring_strain_values():
    assert solved(AT + "ozone_column_dobson", DU="1")["Nc"] == pytest.approx(2.687e20, rel=1e-3)
    assert solved("chemistry.organic.ring_strain_cycloalkane")["Es"] / 1e3 == pytest.approx(115.2, abs=0.1)
    assert solved("chemistry.organic.ring_strain_cycloalkane", nr="6", Hc="3952 kJ/mol")["Es"] == pytest.approx(0, abs=1e3)


def test_enantioselectivity_and_control_regimes():
    assert solved("chemistry.organic.selectivity_ddg_enantiomeric_excess", ddG="0 kJ/mol")["ee"] == pytest.approx(0)
    out = solved("chemistry.organic.kinetic_vs_thermodynamic_control")
    assert out["rk"] > 1 > out["rt"] and out["th"] > 3600


def test_isotope_effect_phase_rule_and_electron_counts():
    assert solved("chemistry.organic.kinetic_isotope_effect")["KIE"] == pytest.approx(6.5, abs=0.2)
    assert solved("chemistry.physical.phase_rule_lever_rule", z="0.1")["fb"] == pytest.approx(0)
    assert solved("chemistry.inorganic.electron_count_18", gr="6", n2="6")["ok"] == 1
    cp2fe = solved("chemistry.inorganic.electron_count_18", n2="0", n5="2")
    assert cp2fe["tot"] == 18
    assert solved("chemistry.inorganic.electron_count_18", gr="9", n2="4", n1="0")["gap"] == 1


def test_perovskite_classes_and_catalogued():
    assert solved("chemistry.inorganic.perovskite_tolerance_factor", rA="1.1 angstrom")["cl"] == 1
    for cid in CASES:
        assert "chemistry" in CAT.get(cid).disciplines
    for sub, cid in (("Colloid and Surface Chemistry", CO + "debye_double_layer"), ("Biochemistry", BI + "hill_cooperativity_oxygen"), ("Atmospheric Chemistry", AT + "chapman_ozone")):
        assert sub in CAT.get(cid).subdisciplines
