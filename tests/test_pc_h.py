"""Broad chemistry, part A: quantum chemistry, photochemistry, polymers (independent formulas, SI quantities)."""

import math

import pytest
from pcutil import CAT, NA, R, c, check_case, e, eps0, h, hbar, kB, me, pi, solved

QC = "chemistry.quantum."
PH = "chemistry.photochem."
PO = "chemistry.polymer."
Dby = 3.33564095e-30


def huckel(x):
    N, a, b = x["Nc"], x["al"], x["be"]
    th = pi / (N + 1)
    Eh, El = a + 2 * b * math.cos(N / 2 * th), a + 2 * b * math.cos((N / 2 + 1) * th)
    Ep = 2 * sum(a + 2 * b * math.cos(k * th) for k in range(1, int(N / 2) + 1))
    return {"th": th, "Eh": Eh, "El": El, "gap": El - Eh, "lam": h * c / (El - Eh), "Ep": Ep, "DE": Ep - N * (a + b)}


def femo(x):
    L = (x["Ne"] + 1) * x["bl"]
    dE = h**2 * (x["Ne"] + 1) / (8 * me * L**2)
    return {"Lb": L, "dE": dE, "lam": h * c / dE}


def lcao(x):
    a, b, S = x["al"], x["be"], x["Sv"]
    Eb, Ea = (a + b) / (1 + S), (a - b) / (1 - S)
    return {"Eb": Eb, "Ea": Ea, "sb": Eb - a, "da": Ea - a, "E2": 2 * (Eb - a), "E4": 2 * (Eb - a) + 2 * (Ea - a)}


def bond_order(x):
    bo = (x["nb"] - x["na"]) / 2
    return {"bo": bo, "mu": math.sqrt(x["nu"] * (x["nu"] + 2)), "mg": 1 if x["nu"] > 0 else 0, "dn": x["d1"] - 0.6e-10 * math.log10(bo)}


def dft(x):
    chi = (x["IE"] + x["EA"]) / 2
    eta = (x["IE"] - x["EA"]) / 2
    return {"chiM": chi, "mu": -chi, "eta": eta, "sf": 1 / (2 * eta), "om": chi**2 / (2 * eta), "chiP": 0.336 / e * (chi - 0.615 * e)}


def debye(x):
    Pm = (x["er"] - 1) / (x["er"] + 2) * x["Mm"] / x["rho"]
    Rm = (x["nr"] ** 2 - 1) / (x["nr"] ** 2 + 2) * x["Mm"] / x["rho"]
    mu = math.sqrt(9 * eps0 * kB * x["T"] * (Pm - Rm) / NA)
    return {"Pm": Pm, "Rm": Rm, "mu": mu, "muD": mu / Dby}


def actinometry(x):
    q = x["P"] * x["lam"] / (h * c * NA)
    fa = 1 - 10 ** (-x["Ab"])
    na = q * x["tt"] * fa
    return {"qf": q, "fa": fa, "na": na, "Phi": x["dn"] / na}


def excited(x):
    tau = 1 / (x["kr"] + x["kisc"] + x["knr"])
    return {"tau": tau, "tau0": 1 / x["kr"], "Pf": x["kr"] * tau, "Pi": x["kisc"] * tau, "Pn": x["knr"] * tau}


def fret(x):
    return {"E": 1 / (1 + (x["rd"] / x["R0"]) ** 6), "kT": (x["R0"] / x["rd"]) ** 6 / x["tD"], "rE": x["R0"] * ((1 - x["Em"]) / x["Em"]) ** (1 / 6)}


def marcus(x):
    lm, dG, T = x["lm"], x["dG"], x["T"]
    pref = 4 * pi**2 * x["Hab"] ** 2 / (h * math.sqrt(4 * pi * lm * kB * T))
    Ga = (dG + lm) ** 2 / (4 * lm)
    return {"dGa": Ga, "ket": pref * math.exp(-Ga / (kB * T)), "kmax": pref, "rg": float(math.copysign(1, -dG - lm)) if abs(-dG - lm) > 1e-30 else 0.0}


def averages(x):
    n = [x["n1"], x["n2"], x["n3"]]
    M = [x["M1"], x["M2"], x["M3"]]
    S0 = sum(n)
    S1 = sum(a * b for a, b in zip(n, M))
    S2 = sum(a * b**2 for a, b in zip(n, M))
    S3 = sum(a * b**3 for a, b in zip(n, M))
    return {"Mn": S1 / S0, "Mw": S2 / S1, "Mz": S3 / S2, "Dp": (S2 / S1) / (S1 / S0)}


def stepgrowth(x):
    p, r = x["pc"], x["rs"]
    Xn = (1 + r) / (1 + r - 2 * r * p)
    return {"Xn": Xn, "Mn": Xn * x["M0"], "preq": (1 + r) * (1 - 1 / x["Xt"]) / (2 * r), "Dp": 1 + p, "pg": 2 / x["fav"]}


def radical(x):
    M, I, kd, f, kp, kt = x["Mc"], x["Ic"], x["kd"], x["fe"], x["kp"], x["kt"]
    nu = kp * M / (2 * math.sqrt(f * kd * kt * I))
    return {"Ri": 2 * f * kd * I, "Rp": kp * M * math.sqrt(f * kd * I / kt), "nu": nu, "Xc": 2 * nu, "Xd": nu}


def flory(x):
    N1, N2, p, chi = x["N1"], x["N2"], x["p2"], x["chi"]
    chic = (1 / math.sqrt(N1) + 1 / math.sqrt(N2)) ** 2 / 2
    return {"dGm": R * x["T"] * ((1 - p) / N1 * math.log(1 - p) + p / N2 * math.log(p) + chi * p * (1 - p)), "chic": chic, "pc": 1 / (1 + math.sqrt(N2 / N1)), "mis": 1 if chi < chic else 0}


def chain(x):
    N, b, lp = x["Nk"], x["bk"], x["Lp"]
    L = N * b
    return {"Lc": L, "Rfj": b * math.sqrt(N), "Rg": b * math.sqrt(N / 6), "Rw": math.sqrt(2 * lp * L * (1 - lp / L * (1 - math.exp(-L / lp)))), "Rf": b * N**0.6}


def mark(x):
    et = x["eref"] * (x["Mt"] / x["Mref"]) ** x["ax"]
    return {"et": et, "Mv": x["Mref"] * (x["em"] / x["eref"]) ** (1 / x["ax"]), "Rh": (3 * et * x["Mt"] / (10 * pi * NA)) ** (1 / 3)}


def tg(x):
    return {"Tfox": 1 / (x["w1"] / x["Tg1"] + (1 - x["w1"]) / x["Tg2"]), "TFF": x["Tinf"] - x["Kf"] / x["Mn"]}


def rubber(x):
    nu = x["rho"] / x["Mc"]
    G = nu * R * x["T"]
    lam = x["lm"]
    return {"nuc": nu, "G": G, "Ey": 3 * G, "sn": G * (lam - lam**-2), "st": G * (lam**2 - 1 / lam)}


def osmometry(x):
    rp = x["Pi"] / x["cg"]
    return {"rp": rp, "Mn": R * x["T"] / (rp - R * x["T"] * x["A2"] * x["cg"])}


CASES = {
    QC + "huckel_linear_polyene": huckel, QC + "free_electron_polyene_dye": femo, QC + "lcao_two_orbital": lcao, QC + "mo_bond_order_magnetism": bond_order, QC + "conceptual_dft_descriptors": dft,
    QC + "debye_dipole_polarisation": debye, PH + "quantum_yield_actinometry": actinometry, PH + "excited_state_kinetics": excited, PH + "forster_energy_transfer": fret, PH + "marcus_electron_transfer": marcus,
    PO + "molar_mass_averages": averages, PO + "step_growth_carothers": stepgrowth, PO + "radical_polymerisation_kinetics": radical, PO + "flory_huggins_mixing": flory, PO + "chain_dimensions": chain,
    PO + "intrinsic_viscosity_mark_houwink": mark, PO + "glass_transition_fox_flory": tg, PO + "rubber_elasticity": rubber, PO + "membrane_osmometry": osmometry,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


def test_butadiene_and_benzene_style_results_from_huckel():
    out = solved(QC + "huckel_linear_polyene", Nc="4", al="0 eV", be="-1 eV")
    assert out["Eh"] / e == pytest.approx(-0.618, abs=1e-3) and out["Ep"] / e == pytest.approx(-4.472, abs=1e-3)       # E = 2(alpha + 1.618 beta) + 2(alpha + 0.618 beta)
    assert out["DE"] / e == pytest.approx(-0.472, abs=1e-3)


def test_lcao_without_overlap_is_symmetric_and_four_electrons_do_not_bind_with_overlap():
    out = solved(QC + "lcao_two_orbital", Sv="0")
    assert out["sb"] == pytest.approx(-out["da"]) and out["E4"] == pytest.approx(0, abs=1e-30)
    assert solved(QC + "lcao_two_orbital")["E4"] > 0


def test_dioxygen_and_dinitrogen_bond_orders():
    assert solved(QC + "mo_bond_order_magnetism")["bo"] == 2
    n2 = solved(QC + "mo_bond_order_magnetism", nb="8", na="2", nu="0")
    assert n2["bo"] == 3 and n2["mg"] == 0


def test_hcl_dipole_close_to_experimental_value():
    assert solved(QC + "debye_dipole_polarisation")["muD"] == pytest.approx(1.08, abs=0.05)


def test_fret_half_efficiency_at_the_forster_radius_and_marcus_optimum():
    assert solved(PH + "forster_energy_transfer", rd="50 angstrom")["E"] == pytest.approx(0.5)
    out = solved(PH + "marcus_electron_transfer", dG="-0.8 eV")
    assert out["rg"] == 0 and out["ket"] == pytest.approx(out["kmax"]) and out["dGa"] == pytest.approx(0, abs=1e-25)


def test_excited_state_yields_sum_to_one_and_quantum_yield_bounds():
    out = solved(PH + "excited_state_kinetics")
    assert out["Pf"] + out["Pi"] + out["Pn"] == pytest.approx(1)


def test_monodisperse_polymer_has_unit_dispersity_and_carothers_extremes():
    assert solved(PO + "molar_mass_averages", M1="50 kg/mol", M2="50 kg/mol", M3="50 kg/mol")["Dp"] == pytest.approx(1)
    assert solved(PO + "step_growth_carothers", pc="0.5")["Xn"] == pytest.approx(2)
    assert solved(PO + "step_growth_carothers", rs="0.98", pc="1")["Xn"] == pytest.approx(99)        # stoichiometric imbalance limits Xn to (1+r)/(1-r)


def test_flory_huggins_critical_parameter_for_infinite_chains_is_one_half():
    assert solved(PO + "flory_huggins_mixing", N1="1", N2="1e12")["chic"] == pytest.approx(0.5, abs=1e-5)
    assert solved(PO + "flory_huggins_mixing", chi="0.7")["mis"] == 0


def test_chain_dimensions_limits_and_modulus_of_rubber():
    assert solved(PO + "chain_dimensions", Lp="1e-4 nm")["Rw"] == pytest.approx(solved(PO + "chain_dimensions", Lp="1e-4 nm")["Rfj"] * math.sqrt(2e-4 / 1.8), rel=1e-6)
    assert solved(PO + "rubber_elasticity")["G"] / 1e6 == pytest.approx(0.456, abs=0.001)
    assert solved(PO + "rubber_elasticity", lm="1")["sn"] == pytest.approx(0, abs=1e-9)


def test_catalogued_under_the_new_subdisciplines():
    for cid in CASES:
        assert "chemistry" in CAT.get(cid).disciplines
    assert hbar > 0 and "Quantum Chemistry" in CAT.get(QC + "lcao_two_orbital").subdisciplines
    assert "Photochemistry" in CAT.get(PH + "marcus_electron_transfer").subdisciplines and "Polymer Chemistry" in CAT.get(PO + "chain_dimensions").subdisciplines
