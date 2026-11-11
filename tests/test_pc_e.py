"""Core chemistry, part B: analytical, spectroscopy, solid-state and inorganic, organic (independent formulas, SI quantities)."""

import math

import pytest
from pcutil import CAT, NA, R, Rinf, c, check_case, e, eps0, h, kB, pi, solved

cst = 1000.0        # 1 mol/L in mol/m^3
Kw = 1e-8           # 1e-14 mol^2/L^2 in mol^2/m^6
A = "chemistry.analytical."
S = "chemistry.spectroscopy."
I = "chemistry.inorganic."
O = "chemistry.organic."
Da = 1.66053906660e-27
log10 = math.log10


def mixing(x):
    cn = (x["Ca"] * x["Va"] - x["Cb"] * x["Vb"]) / (x["Va"] + x["Vb"])
    hh = (cn + math.sqrt(cn**2 + 4 * Kw)) / 2
    return {"cn": cn, "hh": hh, "pH": -log10(hh / cst)}


def diprotic(x):
    hh = cst * 10 ** (-x["pHs"])
    D = hh**2 + x["Ka1"] * hh + x["Ka1"] * x["Ka2"]
    return {"hh": hh, "Dn": D, "a0": hh**2 / D, "a1": x["Ka1"] * hh / D, "a2": x["Ka1"] * x["Ka2"] / D, "pHa": (-log10(x["Ka1"] / cst) - log10(x["Ka2"] / cst)) / 2}


def titration(x):
    Ka, Ca, Va, Cb, Vx = x["Ka"], x["Ca"], x["Va"], x["Cb"], x["Vx"]
    Veq = Ca * Va / Cb
    Kb = Kw / Ka
    Cs = Ca * Va / (Va + Veq)
    return {"Veq": Veq, "pH0": -log10((-Ka + math.sqrt(Ka**2 + 4 * Ka * Ca)) / 2 / cst), "pHh": -log10(Ka / cst), "Kb": Kb, "Cs": Cs,
            "pHe": 14 + log10((-Kb + math.sqrt(Kb**2 + 4 * Kb * Cs)) / 2 / cst), "pHx": 14 + log10(Cb * Vx / (Va + Veq + Vx) / cst)}


def hydrolysis(x):
    return {"pHa": 7 + (x["pKa"] + log10(x["Cs"] / cst)) / 2, "pHb": 7 - (x["pKb"] + log10(x["Cs"] / cst)) / 2, "pHab": 7 + (x["pKa"] - x["pKb"]) / 2}


def buffer(x):
    r = 10 ** (x["pHt"] - x["pKa"])
    cA, cHA = x["Ct"] * r / (1 + r), x["Ct"] / (1 + r)
    ka, hh = 10 ** (-x["pKa"]), 10 ** (-x["pHt"])
    return {"rt": r, "cA": cA, "cHA": cHA, "nA": cA * x["Vt"], "nHA": cHA * x["Vt"], "beta": math.log(10) * x["Ct"] * ka * hh / (ka + hh) ** 2}


def complexation(x):
    b = 1 + x["Kf"] * (x["CM"] + x["CL"])
    ML = (b - math.sqrt(b * b - 4 * x["Kf"] ** 2 * x["CM"] * x["CL"])) / (2 * x["Kf"])
    return {"bb": b, "ML": ML, "Mf": x["CM"] - ML, "Lf": x["CL"] - ML, "fc": ML / x["CM"]}


def calibration(x):
    xc = (x["sig"] - x["icp"]) / x["mcal"]
    return {"xc": xc, "lod": 3.3 * x["sb"] / x["mcal"], "loq": 10 * x["sb"] / x["mcal"]}


def std_add(x):
    return {"Cx": x["Cs"] * x["Vs"] * x["Ix"] / (x["Isx"] * (x["Vx"] + x["Vs"]) - x["Ix"] * x["Vx"])}


def conf(x):
    sem = x["sd"] / math.sqrt(x["nrep"])
    return {"sem": sem, "hw": x["tc"] * sem, "lo": x["xb"] - x["tc"] * sem, "hi": x["xb"] + x["tc"] * sem, "rsd": x["sd"] / x["xb"]}


def uncertainty(x):
    rho = x["m1"] / x["Vv"]
    return {"mt": x["m1"] + x["m2"], "smt": math.hypot(x["s1"], x["s2"]), "rho": rho, "srho": rho * math.hypot(x["s1"] / x["m1"], x["sV"] / x["Vv"]),
            "Ar": pi * x["rr"] ** 2, "sA": 2 * pi * x["rr"] * x["sr"]}


def chromatography(x):
    k1, k2 = (x["t1"] - x["t0"]) / x["t0"], (x["t2"] - x["t0"]) / x["t0"]
    N = 16 * (x["t2"] / x["w2"]) ** 2
    return {"k1": k1, "k2": k2, "al": k2 / k1, "Rs": 2 * (x["t2"] - x["t1"]) / (x["w1"] + x["w2"]), "Np": N, "Hp": x["Lc"] / N}


def deemter(x):
    return {"Hh": x["Av"] + x["Bv"] / x["uv"] + x["Cv"] * x["uv"], "uo": math.sqrt(x["Bv"] / x["Cv"]), "Hm": x["Av"] + 2 * math.sqrt(x["Bv"] * x["Cv"])}


def two_comp(x):
    d = x["e11"] * x["e22"] - x["e12"] * x["e21"]
    return {"dt": d, "c1": (x["A1"] * x["e22"] - x["A2"] * x["e12"]) / (x["bl"] * d), "c2": (x["A2"] * x["e11"] - x["A1"] * x["e21"]) / (x["bl"] * d)}


def fluorescence(x):
    Ksv = (x["F0"] / x["Fq"] - 1) / x["Qc"]
    return {"Ksv": Ksv, "kq": Ksv / x["tau0"], "Phs": x["Phr"] * x["Fs"] / x["Fr"] * x["Ar"] / x["As"] * (x["ns"] / x["nr"]) ** 2}


def gravimetric(x):
    gf = x["sa"] * x["Ma"] / (x["sb"] * x["Mp"])
    return {"gf": gf, "ma": x["mp"] * gf, "pc": x["mp"] * gf / x["ms"]}


def mass_spec(x):
    return {"Rp": x["mz"] / x["dm"], "M1": x["nC"] * 0.0108, "M2": x["nCl"] * 0.3199 + x["nBr"] * 0.9728}


def ir(x):
    mu, mui = x["m1"] * x["m2"] / (x["m1"] + x["m2"]), x["m1"] * x["m2i"] / (x["m1"] + x["m2i"])
    nu, nui = math.sqrt(x["kf"] / mu) / (2 * pi * c), math.sqrt(x["kf"] / mui) / (2 * pi * c)
    return {"mu": mu, "mui": mui, "nu": nu, "nui": nui, "rr": nui / nu}


def nmr(x):
    nu0 = x["gp"] * x["Bf"] / (2 * pi)
    return {"nu0": nu0, "dl": x["dnu"] / nu0, "dHz": x["dpp"] * nu0, "lines": x["nn"] + 1}


def raman(x):
    return {"dRs": 1 / x["l0"] - 1 / x["ls"], "lst": 1 / (1 / x["l0"] - x["dv"]), "las": 1 / (1 / x["l0"] + x["dv"])}


def populations(x):
    f = h * c * x["Bc"] / (kB * x["T"])
    return {"NJ": (2 * x["Jq"] + 1) * math.exp(-f * x["Jq"] * (x["Jq"] + 1)), "Jm": math.sqrt(1 / (2 * f)) - 0.5, "rv": math.exp(-h * c * x["nvb"] / (kB * x["T"]))}


def photon(x):
    E = h * c / x["lam"]
    return {"Ee": E, "Em": E * NA, "Ek": E * NA, "nv": 1 / x["lam"], "fq": c / x["lam"]}


def slater(x):
    S_ = 0.35 * x["ns"] + 0.85 * x["n1"] + x["ni"]
    Z = x["Z"] - S_
    return {"Sg": S_, "Zf": Z, "Eo": -Rinf * h * c * Z**2 / x["nq"] ** 2}


def broadening(x):
    nu0 = c / x["l0"]
    dD = nu0 * math.sqrt(8 * kB * x["T"] * math.log(2) / (x["ma"] * c**2))
    return {"nu0": nu0, "dD": dD, "dN": 1 / (2 * pi * x["tau"]), "rQ": nu0 / dD}


def morse(x):
    we, wx, v = x["we"], x["wx"], x["vq"]
    De = we**2 / (4 * wx)
    return {"Gv": we * (v + 0.5) - wx * (v + 0.5) ** 2, "f01": we - 2 * wx, "f02": 2 * we - 6 * wx, "De": De, "D0": h * c * NA * (De - we / 2 + wx / 4)}


def rotor(x):
    I_ = h / (8 * pi**2 * c * x["Bc"])
    return {"nl": 2 * x["Bc"] * (x["Jq"] + 1), "fl": c * 2 * x["Bc"] * (x["Jq"] + 1), "Iin": I_, "rb": math.sqrt(I_ / x["mu"])}


def lattice(x):
    f = NA * x["zp"] * x["zm"] * e**2 / (4 * pi * eps0)
    s = x["rp"] + x["rm"]
    return {"Ubl": -f * x["Mad"] / x["r0"] * (1 - 1 / x["nb"]), "Uk": -1.2025e-4 * x["nion"] * x["zp"] * x["zm"] / s * (1 - 34.5e-12 / s)}


def born_haber(x):
    return {"Hf": x["Hs"] + x["Dd"] / 2 + x["Ie"] - x["Ea"] + x["Ul"]}


def cft(x):
    return {"cfse": (-0.4 * x["nt"] + 0.6 * x["neg"]) * h * c * NA * x["Do"], "Dt": 4 * x["Do"] / 9, "mso": math.sqrt(x["nu"] * (x["nu"] + 2)), "lam": 1 / x["Do"]}


def radius_ratio(x):
    r = x["rp"] / x["rm"]
    cn = 2 if r < 0.155 else 3 if r < 0.225 else 4 if r < 0.414 else 6 if r < 0.732 else 8
    return {"rr": r, "cn": cn}


def crystal_density(x):
    a = x["gf"] * (x["rp"] + x["rm"])
    return {"ac": a, "rho": x["Zc"] * x["Mf"] / (NA * a**3), "nfu": x["Zc"] / a**3}


def dou(x):
    return {"dou": (2 * x["nC"] + 2 + x["nN"] - x["nH"] - x["nX"]) / 2}


def hammett(x):
    return {"ks": x["k0"] * 10 ** (x["rhoH"] * x["sg"]), "pKs": x["pKa0"] - x["sg"]}


def huckel(x):
    a, b = x["al"], x["be"]
    Ee, Eb, Ez = 2 * a + 2 * b, 4 * a + 2 * math.sqrt(5) * b, 6 * a + 8 * b
    return {"Ee": Ee, "Eb": Eb, "Ebz": Ez, "DEb": Eb - 2 * Ee, "DEz": Ez - 3 * Ee}


def polarimetry(x):
    sr = x["aobs"] / (x["lp"] * x["cc"])
    ee = abs(sr / x["amax"])
    return {"sr": sr, "ee": ee, "fm": (1 + ee) / 2}


def conformers(x):
    r = x["gdeg"] * math.exp(-x["dG"] / (R * x["T"]))
    return {"rat": r, "pl": 1 / (1 + r), "ph": r / (1 + r)}


def logd(x):
    return {"fai": 1 / (1 + 10 ** (x["pKa"] - x["pHs"])), "fbi": 1 / (1 + 10 ** (x["pHs"] - x["pKa"])),
            "lDa": x["lP"] - log10(1 + 10 ** (x["pHs"] - x["pKa"])), "lDb": x["lP"] - log10(1 + 10 ** (x["pKa"] - x["pHs"]))}


CASES = {
    A + "strong_acid_base_mixing_ph": mixing, A + "diprotic_acid_species": diprotic, A + "weak_acid_titration_curve": titration, A + "salt_hydrolysis_ph": hydrolysis,
    A + "buffer_design": buffer, A + "complex_formation": complexation, A + "calibration_detection_limit": calibration, A + "standard_addition": std_add,
    A + "confidence_interval": conf, A + "uncertainty_propagation": uncertainty, A + "chromatography_figures": chromatography, A + "van_deemter": deemter,
    A + "two_component_spectrophotometry": two_comp, A + "fluorescence_quenching": fluorescence, A + "gravimetric_analysis": gravimetric, A + "mass_spectrometry_figures": mass_spec,
    S + "ir_isotope_shift": ir, S + "nmr_chemical_shift": nmr, S + "raman_shift": raman, S + "level_populations_boltzmann": populations, S + "photon_energy_per_mole": photon,
    S + "slater_rules": slater, S + "spectral_line_broadening": broadening, S + "morse_anharmonic": morse, S + "rotational_spectrum": rotor,
    I + "lattice_energy": lattice, I + "born_haber_cycle": born_haber, I + "crystal_field_theory": cft, I + "radius_ratio_coordination": radius_ratio, I + "ionic_crystal_density": crystal_density,
    O + "degree_of_unsaturation": dou, O + "hammett_equation": hammett, O + "huckel_pi_energies": huckel, O + "optical_rotation_ee": polarimetry,
    O + "conformer_populations": conformers, O + "ionisation_logd": logd,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-6)


def test_acid_base_neutralisation_gives_ph_seven():
    out = solved(A + "strong_acid_base_mixing_ph", Vb="25 mL")
    assert out["pH"] == pytest.approx(7.0, abs=1e-6)


def test_species_fractions_sum_to_one_and_half_titration_pka():
    out = solved(A + "diprotic_acid_species")
    assert out["a0"] + out["a1"] + out["a2"] == pytest.approx(1)
    assert solved(A + "weak_acid_titration_curve")["pHh"] == pytest.approx(4.7447, abs=1e-3)


def test_buffer_at_pka_is_equimolar_with_maximum_capacity():
    out = solved(A + "buffer_design", pHt="4.76")
    assert out["rt"] == pytest.approx(1) and out["beta"] == pytest.approx(math.log(10) * 100 / 4, rel=1e-6)


def test_standard_addition_recovers_the_concentration():
    # Signal proportional to concentration: sample 4 mg/L; after adding 1 mL of 100 mg/L to 25 mL the concentration is (4*25+100)/26.
    s = 1.0
    Ix, Isx = 4 * s, (4 * 25 + 100) / 26 * s
    assert solved(A + "standard_addition", Ix=str(Ix), Isx=str(Isx))["Cx"] == pytest.approx(4e-3, rel=1e-9)


def test_hydrogen_chloride_deuteration_ratio_is_near_inverse_root_two():
    assert solved(S + "ir_isotope_shift")["rr"] == pytest.approx(1 / math.sqrt(2), rel=0.03)


def test_halide_isotope_pattern_two_chlorines_about_two_thirds():
    assert solved(A + "mass_spectrometry_figures")["M2"] == pytest.approx(0.64, abs=0.01)


def test_sodium_chloride_lattice_energy_and_born_haber_formation():
    assert solved(I + "lattice_energy")["Ubl"] / 1e3 == pytest.approx(-753, rel=0.01)
    assert solved(I + "born_haber_cycle")["Hf"] / 1e3 == pytest.approx(-411, rel=0.01)


def test_benzene_density_and_rocksalt_density_of_nacl():
    assert solved(I + "ionic_crystal_density")["rho"] == pytest.approx(2140, rel=0.01)


def test_carbon_monoxide_bond_length():
    assert solved(S + "rotational_spectrum")["rb"] * 1e10 == pytest.approx(1.128, abs=0.002)


def test_aspirin_degrees_of_unsaturation_and_benzene_delocalisation():
    assert solved(O + "degree_of_unsaturation")["dou"] == 6
    out = solved(O + "huckel_pi_energies")
    assert out["DEz"] / (-2.4 * e) == pytest.approx(2.0, rel=1e-6)           # 2 beta stabilisation


def test_racemic_mixture_has_zero_excess_and_equal_fractions():
    out = solved(O + "optical_rotation_ee", aobs="0 deg")
    assert out["ee"] == 0 and out["fm"] == pytest.approx(0.5)


def test_ionisation_fractions_complementary_at_pka():
    out = solved(O + "ionisation_logd", pHs="3.5")
    assert out["fai"] == pytest.approx(0.5) and out["fbi"] == pytest.approx(0.5)


def test_chemistry_core_b_catalogued():
    for cid in CASES:
        assert "chemistry" in CAT.get(cid).disciplines
    assert "Solid-State and Inorganic Chemistry" in CAT.get(I + "lattice_energy").subdisciplines
    assert "Organic Chemistry" in CAT.get(O + "hammett_equation").subdisciplines
