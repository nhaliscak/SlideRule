"""Core physics, part C: modern/atomic, nuclear/particle, solid state, gravitation/astrophysics (independent formulas)."""

import math

import pytest
from pcutil import CAT, G, NA, Rinf, a0, c, check_case, e, eps0, g, h, hbar, kB, me, mu0, pi, sSB, solved
from sliderule.units import parse_unit

MeV = e * 1e6
YR = parse_unit("yr").factor
AU = parse_unit("AU").factor
Msun, Lsun, pc = 1.98847e30, 3.828e26, 3.0856775814913673e16
deg = pi / 180


def doppler(x):
    bt = x["v"] / c
    return {"bt": bt, "fr": x["fs"] * math.sqrt((1 - bt) / (1 + bt)), "fa": x["fs"] * math.sqrt((1 + bt) / (1 - bt)), "zr": math.sqrt((1 + bt) / (1 - bt)) - 1,
            "vz": c * ((1 + x["zin"]) ** 2 - 1) / ((1 + x["zin"]) ** 2 + 1), "zcl": bt}


def muon(x):
    gam = 1 / math.sqrt(1 - x["v"] ** 2 / c**2)
    tl = gam * x["tau0"]
    Ld = x["v"] * tl
    return {"gam": gam, "tl": tl, "Ld": Ld, "Sr": math.exp(-x["dp"] / Ld), "Sn": math.exp(-x["dp"] / (x["v"] * x["tau0"]))}


def threshold(x):
    return {"Kth": (x["mf"] ** 2 - (x["ma"] + x["mb"]) ** 2) * c**2 / (2 * x["mb"]), "Epp": 2 * me * c**2}


def accelerated(x):
    K = e * x["Vacc"]
    gam = 1 + K / (x["m"] * c**2)
    p = math.sqrt(K * (K + 2 * x["m"] * c**2)) / c
    return {"K": K, "gam": gam, "bt": math.sqrt(1 - 1 / gam**2), "p": p, "lam": h / p, "lnr": h / math.sqrt(2 * x["m"] * K)}


def qho(x):
    w = math.sqrt(x["kf"] / x["mo"])
    return {"w": w, "E0": hbar * w / 2, "En": (x["nl"] + 0.5) * hbar * w, "dE": hbar * w, "lam": 2 * pi * c / w, "x0": math.sqrt(hbar / (x["mo"] * w))}


def tunnelling(x):
    kap = math.sqrt(2 * x["m"] * (x["V0"] - x["Ee"])) / hbar
    return {"kap": kap, "dpn": 1 / kap, "Tt": 1 / (1 + x["V0"] ** 2 * math.sinh(kap * x["a"]) ** 2 / (4 * x["Ee"] * (x["V0"] - x["Ee"])))}


def h_ground(x):
    Z = x["Z"]
    R = x["Rin"] * Z / a0
    return {"rmp": a0 / Z, "rm": 1.5 * a0 / Z, "Pin": 1 - math.exp(-2 * R) * (1 + 2 * R + 2 * R * R), "E1": -Rinf * h * c * Z**2}


def zeeman(x):
    muB = e * hbar / (2 * me)
    return {"muB": muB, "dEz": x["gf"] * muB * x["mj"] * x["Bf"], "fesr": x["gf"] * muB * x["Bf"] / h, "fnmr": x["gp"] * x["Bf"] / (2 * pi)}


def moseley(x):
    E = 0.75 * h * c * Rinf * (x["Z"] - 1) ** 2
    return {"EKa": E, "lKa": h * c / E, "lmin": h * c / (e * x["Vt"])}


def rutherford(x):
    d = x["Z1"] * x["Z2"] * e**2 / (4 * pi * eps0 * x["K"])
    return {"dca": d, "bi": d / (2 * math.tan(x["th"] / 2)), "Rn": 1.2e-15 * x["At"] ** (1 / 3)}


def quantum_numbers(x):
    n, l, m = x["nq"], x["lq"], x["mq"]
    return {"gn": 2 * n**2, "Lmag": hbar * math.sqrt(l * (l + 1)), "Lz": m * hbar, "thL": math.acos(m / math.sqrt(l * (l + 1)))}


def photon_force(x):
    E = h * c / x["lam"]
    return {"Eph": E, "pph": h / x["lam"], "Nr": x["Pl"] / E, "Fa": x["Pl"] / c, "Fr": 2 * x["Pl"] / c, "asl": 2 * x["Pl"] / c / x["ms"]}


def attenuation(x):
    mu = x["mum"] * x["rho"]
    return {"mu": mu, "Tt": math.exp(-mu * x["xt"]), "hvl": math.log(2) / mu, "tvl": math.log(10) / mu}


def bec(x):
    lth = h / math.sqrt(2 * pi * x["ma"] * kB * x["T"])
    return {"Tc": h**2 / (2 * pi * x["ma"] * kB) * (x["nd"] / 2.6123753486854883) ** (2 / 3), "lth": lth, "psd": x["nd"] * lth**3}


def rocket(x):
    gam = 1 + x["a"] * x["dist"] / (2 * c**2)
    return {"gam": gam, "bt": math.sqrt(1 - 1 / gam**2), "tp": 2 * c / x["a"] * math.acosh(gam), "te": 2 * c / x["a"] * math.sqrt(gam**2 - 1)}


def semf(x):
    A, Z, ps = x["At"], x["Z"], x["ps"]
    BE = 15.75 * A - 17.8 * A ** (2 / 3) - 0.711 * Z * (Z - 1) / A ** (1 / 3) - 23.7 * (A - 2 * Z) ** 2 / A + ps * 11.18 / math.sqrt(A)
    return {"Rn": 1.2e-15 * A ** (1 / 3), "BE": BE * MeV, "BEA": BE / A * MeV}


def q_value(x):
    Q = (x["ma"] + x["mb"] - x["mc"] - x["md"]) * c**2
    return {"Q": Q, "Kc": Q * x["md"] / (x["mc"] + x["md"]), "Kd": Q * x["mc"] / (x["mc"] + x["md"])}


def activity(x):
    N = x["ms"] * NA / x["Mm"]
    lam = math.log(2) / x["th"]
    return {"Nat": N, "lam": lam, "Act": lam * N, "ACi": lam * N, "sa": lam * N / x["ms"]}


def chain(x):
    lA, lB = math.log(2) / x["tA"], math.log(2) / x["tB"]
    t = x["t"]
    return {"lA": lA, "lB": lB, "AA": x["A0"] * math.exp(-lA * t), "AB": x["A0"] * lB / (lB - lA) * (math.exp(-lA * t) - math.exp(-lB * t)), "tmax": math.log(lB / lA) / (lB - lA), "req": lB / (lB - lA)}


def radiocarbon(x):
    return {"age": x["th"] * math.log(1 / x["fr"]) / math.log(2), "fa": math.exp(-math.log(2) * x["tw"] / x["th"])}


def cross_section(x):
    S = x["nd"] * x["sg"]
    return {"Sig": S, "mfp": 1 / S, "Rr": S * x["Phi"] * x["Vt"], "Tr": math.exp(-S * x["xs"]), "xh": math.log(2) / S}


def moderation(x):
    A = x["Am"]
    xi = 1 + (A - 1) ** 2 / (2 * A) * math.log((A - 1) / (A + 1))
    return {"xi": xi, "ncol": math.log(x["E0"] / x["Et"]) / xi}


def fusion(x):
    alpha = e**2 / (4 * pi * eps0 * hbar * c)
    mr = x["m1"] * x["m2"] / (x["m1"] + x["m2"])
    EG = 2 * mr * c**2 * (pi * alpha * x["Z1"] * x["Z2"]) ** 2
    return {"Bc": x["Z1"] * x["Z2"] * e**2 / (4 * pi * eps0 * 1.2e-15 * (x["A1"] ** (1 / 3) + x["A2"] ** (1 / 3))), "alf": alpha, "EG": EG, "Epk": (EG * x["kT"] ** 2 / 4) ** (1 / 3)}


def two_body(x):
    M, m1, m2 = x["M"], x["m1"], x["m2"]
    E1 = (M**2 + m1**2 - m2**2) * c**2 / (2 * M)
    return {"pc": math.sqrt((M**2 - (m1 + m2) ** 2) * (M**2 - (m1 - m2) ** 2)) * c**2 / (2 * M), "E1": E1, "K1": E1 - m1 * c**2, "Qd": (M - m1 - m2) * c**2}


def crystal(x):
    return {"apf": x["Zc"] * 4 * pi * x["rr"] ** 3 / 3, "rho": x["Zc"] * x["Mm"] / (NA * x["a"] ** 3), "nat": x["Zc"] / x["a"] ** 3, "dnn": 2 * x["rr"] * x["a"]}


def pn(x):
    Na, Nd, er = x["Na"], x["Nd"], x["er"]
    Vbi = kB * x["T"] / e * math.log(Na * Nd / x["ni"] ** 2)
    W = math.sqrt(2 * eps0 * er * (Vbi + x["Vr"]) / e * (1 / Na + 1 / Nd))
    xn = W * Na / (Na + Nd)
    return {"Vbi": Vbi, "W": W, "xp": W * Nd / (Na + Nd), "xn": xn, "Emx": e * Nd * xn / (eps0 * er), "Cj": eps0 * er * x["Aj"] / W}


def varshni(x):
    Eg = x["Eg0"] - x["alp"] * x["T"] ** 2 / (x["T"] + x["bet"])
    return {"Eg": Eg, "dEg": Eg - x["Eg0"], "lg": h * c / Eg}


def debye(x):
    n = x["rho"] * NA / x["Mm"]
    thD = hbar * x["vs"] * (6 * pi**2 * n) ** (1 / 3) / kB
    return {"nat": n, "thD": thD, "wD": kB * thD / h}


def supercond(x):
    D0 = 1.764 * kB * x["Tc"]
    return {"D0": D0, "BcT": x["Bc0"] * (1 - (x["T"] / x["Tc"]) ** 2), "lL": math.sqrt(me / (mu0 * x["ns"] * e**2)), "xi0": hbar * x["vF"] / (pi * D0), "Ph0": h / (2 * e)}


def wf(x):
    L0 = pi**2 * kB**2 / (3 * e**2)
    return {"L0": L0, "ke": L0 * x["sg"] * x["T"]}


def chain_ph(x):
    w0 = math.sqrt(x["Kc"] / x["ma"])
    return {"wm": 2 * w0, "vs": x["a"] * w0, "wk": 2 * w0 * abs(math.sin(x["ka"] / 2)), "vg": x["a"] * w0 * abs(math.cos(x["ka"] / 2))}


def curie(x):
    muB = e * hbar / (2 * me)
    pe = x["gj"] * math.sqrt(x["Jq"] * (x["Jq"] + 1))
    return {"pe": pe, "Ms": x["nd"] * x["gj"] * x["Jq"] * muB, "chi": x["nd"] * mu0 * pe**2 * muB**2 / (3 * kB * x["T"])}


def thermoelectric(x):
    Tm = (x["Th"] + x["Tc"]) / 2
    ZT = x["Sb"] ** 2 * x["sg"] * Tm / x["kt"]
    return {"Tm": Tm, "PF": x["Sb"] ** 2 * x["sg"], "ZT": ZT, "eta": (x["Th"] - x["Tc"]) / x["Th"] * (math.sqrt(1 + ZT) - 1) / (math.sqrt(1 + ZT) + x["Tc"] / x["Th"]), "etC": 1 - x["Tc"] / x["Th"]}


def brus(x):
    E = x["Eg0"] + h**2 / (8 * x["Rq"] ** 2) * (1 / (x["mer"] * me) + 1 / (x["mhr"] * me)) - 1.786 * e**2 / (4 * pi * eps0 * x["er"] * x["Rq"])
    return {"Eqd": E, "lq": h * c / E}


def vis_viva(x):
    GM, a, ec = G * x["M"], x["a"], x["ecc"]
    rp, ra = a * (1 - ec), a * (1 + ec)
    return {"rp": rp, "ra": ra, "vp": math.sqrt(GM * (2 / rp - 1 / a)), "va": math.sqrt(GM * (2 / ra - 1 / a)), "vr": math.sqrt(GM * (2 / x["rc"] - 1 / a)), "Tp": 2 * pi * math.sqrt(a**3 / GM), "eo": -GM / (2 * a)}


def tides(x):
    return {"at": 2 * G * x["M"] * x["Rm"] / x["a"] ** 3, "dR": 2.44 * x["RM"] * (x["rM"] / x["rm"]) ** (1 / 3), "rH": x["a"] * (x["m"] / (3 * x["M"])) ** (1 / 3)}


def stellar(x):
    L = 4 * pi * x["Rs"] ** 2 * sSB * x["Ts"] ** 4
    Ma = 4.74 - 2.5 * math.log10(L / Lsun)
    dm = 5 * math.log10(x["ds"] / (10 * pc))
    return {"Ls": L, "Lr": L / Lsun, "Fs": L / (4 * pi * x["ds"] ** 2), "Ma": Ma, "dmod": dm, "ma": Ma + dm}


def planet(x):
    return {"Sf": sSB * x["Ts"] ** 4 * (x["Rs"] / x["ap"]) ** 2, "Teq": x["Ts"] * math.sqrt(x["Rs"] / (2 * x["ap"])) * (1 - x["Ab"]) ** 0.25}


def hubble(x):
    Mpc = 3.0856775814913673e22
    vh = x["H0"] * x["dM"]
    Hs = x["H0"] / Mpc
    return {"vh": vh, "zh": vh / c, "Hs": Hs, "tH": 1 / Hs, "rc": 3 * Hs**2 / (8 * pi * G)}


def binary(x):
    Mt = 4 * pi**2 * x["a"] ** 3 / (G * x["Pb"] ** 2)
    return {"Mt": Mt, "Mtr": Mt / Msun, "M1": Mt * (x["a"] - x["a1"]) / x["a"], "M2": Mt * x["a1"] / x["a"]}


def mass_luminosity(x):
    return {"Lms": Lsun * x["Mr"] ** 3.5, "tl": 1e10 * YR * x["Mr"] ** -2.5, "LE": 4 * pi * G * x["Mbh"] * Msun * 1.67262192369e-27 * c / 6.6524587321e-29, "LEr": 4 * pi * G * x["Mbh"] * Msun * 1.67262192369e-27 * c / 6.6524587321e-29 / Lsun}


def einstein(x):
    return {"thE": math.sqrt(4 * G * x["M"] / c**2 * (x["Ds"] - x["Dl"]) / (x["Dl"] * x["Ds"]))}


def black_hole(x):
    M = x["Mr"] * Msun
    rs = 2 * G * M / c**2
    return {"rs": rs, "rph": 1.5 * rs, "risco": 3 * rs, "TH": hbar * c**3 / (8 * pi * G * M * kB), "Sbh": 4 * pi * G * M**2 / (hbar * c), "tev": 5120 * pi * G**2 * M**3 / (hbar * c**4)}


def gr_tests(x):
    d = 6 * pi * G * x["M"] / (c**2 * x["a"] * (1 - x["ecc"] ** 2))
    return {"dphi": d, "dcen": d * 36525 * 86400 / x["Tn"], "alp": 4 * G * x["M"] / (c**2 * x["bi"])}


CASES = {
    "physics.modern.relativistic_doppler": doppler, "physics.modern.muon_time_dilation": muon, "physics.modern.reaction_threshold": threshold, "physics.modern.accelerated_particle": accelerated,
    "physics.modern.quantum_harmonic_oscillator": qho, "physics.modern.quantum_tunnelling": tunnelling, "physics.modern.hydrogen_ground_state": h_ground, "physics.modern.zeeman_nmr_esr": zeeman,
    "physics.modern.moseley_duane_hunt": moseley, "physics.modern.rutherford_scattering": rutherford, "physics.modern.hydrogen_quantum_numbers": quantum_numbers,
    "physics.modern.photon_momentum_laser_force": photon_force, "physics.modern.radiation_attenuation": attenuation, "physics.modern.bose_einstein_condensation": bec, "physics.modern.relativistic_rocket": rocket,
    "physics.nuclear.semi_empirical_binding_energy": semf, "physics.nuclear.reaction_q_value": q_value, "physics.nuclear.activity_from_mass": activity, "physics.nuclear.parent_daughter_chain": chain,
    "physics.nuclear.radiocarbon_dating": radiocarbon, "physics.nuclear.cross_section_attenuation": cross_section, "physics.nuclear.neutron_moderation": moderation, "physics.nuclear.fusion_coulomb_gamow": fusion,
    "physics.nuclear.two_body_decay": two_body, "physics.solid.crystal_structure_density": crystal, "physics.solid.pn_junction": pn, "physics.solid.band_gap_temperature": varshni, "physics.solid.debye_temperature": debye,
    "physics.solid.superconductor_parameters": supercond, "physics.solid.wiedemann_franz": wf, "physics.solid.monatomic_chain_phonons": chain_ph, "physics.solid.curie_paramagnetism": curie,
    "physics.solid.thermoelectric_zt": thermoelectric, "physics.solid.quantum_dot_brus": brus, "physics.gravitation.elliptical_orbit_vis_viva": vis_viva, "physics.gravitation.tides_roche_hill": tides,
    "physics.gravitation.stellar_luminosity_magnitude": stellar, "physics.gravitation.planet_equilibrium_temperature": planet, "physics.gravitation.hubble_law_cosmology": hubble,
    "physics.gravitation.binary_star_masses": binary, "physics.gravitation.stellar_mass_luminosity_eddington": mass_luminosity, "physics.gravitation.einstein_ring": einstein,
    "physics.gravitation.black_hole_thermodynamics": black_hole, "physics.gravitation.gr_tests_precession_deflection": gr_tests,
}


@pytest.mark.parametrize("cid", list(CASES))
def test_against_the_textbook_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


# ---------------------------------------------------------------- physical identities and benchmarks
def test_doppler_classical_limit_and_round_trip():
    slow = solved("physics.modern.relativistic_doppler", v="0.3 Mm/s")
    assert slow["zr"] == pytest.approx(slow["zcl"], rel=2e-3)
    zr = solved("physics.modern.relativistic_doppler")["zr"]
    assert solved("physics.modern.relativistic_doppler", zin=str(zr))["vz"] == pytest.approx(29.9792458e6, rel=1e-9)


def test_relativity_saves_the_muons():
    out = solved("physics.modern.muon_time_dilation")
    assert out["Sr"] > 0.2 and out["Sn"] < 1e-9 and out["gam"] == pytest.approx(17.45, abs=0.05)


def test_proton_proton_antiproton_threshold_is_six_rest_energies():
    assert solved("physics.modern.reaction_threshold")["Kth"] / (938.272 * MeV) == pytest.approx(6, rel=1e-4)


def test_slow_electrons_have_the_classical_wavelength():
    out = solved("physics.modern.accelerated_particle", Vacc="0.1 kV")
    assert out["lam"] == pytest.approx(out["lnr"], rel=1e-4)
    assert solved("physics.modern.accelerated_particle")["lam"] * 1e12 == pytest.approx(3.70, abs=0.01)         # 100 kV electron microscope


def test_oscillator_levels_are_evenly_spaced():
    a, b = solved("physics.modern.quantum_harmonic_oscillator", nl="2"), solved("physics.modern.quantum_harmonic_oscillator", nl="3")
    assert b["En"] - a["En"] == pytest.approx(a["dE"]) and solved("physics.modern.quantum_harmonic_oscillator", nl="0")["En"] == pytest.approx(a["E0"])
    assert 1 / (a["lam"] * 100) == pytest.approx(2145, rel=3e-3)             # CO stretch, cm^-1


def test_tunnelling_falls_with_width_and_rises_with_energy():
    base = solved("physics.modern.quantum_tunnelling")["Tt"]
    assert solved("physics.modern.quantum_tunnelling", a="1 nm")["Tt"] < base < solved("physics.modern.quantum_tunnelling", Ee="3 eV")["Tt"]


def test_one_s_electron_is_inside_a_bohr_radius_a_third_of_the_time():
    assert solved("physics.modern.hydrogen_ground_state", Rin=f"{a0 * 1e12} pm")["Pin"] == pytest.approx(1 - 5 * math.exp(-2), rel=1e-6)
    assert solved("physics.modern.hydrogen_ground_state", Rin="2000 pm")["Pin"] == pytest.approx(1, abs=1e-9)


def test_resonance_frequencies_per_tesla():
    out = solved("physics.modern.zeeman_nmr_esr", Bf="1 T")
    assert out["fesr"] / 1e9 == pytest.approx(28.02, abs=0.01) and out["fnmr"] / 1e6 == pytest.approx(42.577, abs=0.001)


def test_xray_lines_and_tube_limit():
    assert solved("physics.modern.moseley_duane_hunt")["EKa"] / (e * 1e3) == pytest.approx(8.05, rel=0.01)       # Cu K-alpha
    assert solved("physics.modern.moseley_duane_hunt", Z="42")["EKa"] / (e * 1e3) == pytest.approx(17.48, rel=0.03)    # Mo K-alpha: the (Z-1)^2 law is good to about 2 %
    assert solved("physics.modern.moseley_duane_hunt", Vt="12.398 kV")["lmin"] * 1e10 == pytest.approx(1.0, rel=1e-3)


def test_rutherford_alpha_stays_outside_the_nucleus_and_head_on_limit():
    out = solved("physics.modern.rutherford_scattering")
    assert out["dca"] > out["Rn"] and out["dca"] * 1e15 == pytest.approx(45.5, abs=0.1)
    assert solved("physics.modern.rutherford_scattering", th="179.9 deg")["bi"] < 0.01 * out["dca"]


def test_angular_momentum_selection_rules():
    top = solved("physics.modern.hydrogen_quantum_numbers", mq="2")
    assert top["Lz"] == pytest.approx(2 * hbar) and top["gn"] == 18


def test_laser_force_and_attenuation_half_value_layer():
    assert solved("physics.modern.photon_momentum_laser_force")["Fa"] == pytest.approx(1000 / c)
    assert solved("physics.modern.radiation_attenuation", xt="0.92412 cm")["Tt"] == pytest.approx(0.5, abs=1e-4)


def test_phase_space_density_at_the_condensation_temperature():
    Tc = solved("physics.modern.bose_einstein_condensation")["Tc"]
    assert solved("physics.modern.bose_einstein_condensation", T=f"{Tc} K")["psd"] == pytest.approx(2.6123753486854883, rel=1e-9)


def test_rocket_reduces_to_newtonian_motion_for_a_short_trip():
    out = solved("physics.modern.relativistic_rocket", dist="1e-5 Pm")
    assert out["tp"] == pytest.approx(2 * math.sqrt(1e10 / g), rel=1e-4) and out["te"] == pytest.approx(out["tp"], rel=1e-4)


def test_binding_energy_of_iron_and_the_pairing_term():
    assert solved("physics.nuclear.semi_empirical_binding_energy")["BEA"] / MeV == pytest.approx(8.79, rel=0.02)
    ee, oo = solved("physics.nuclear.semi_empirical_binding_energy", ps="1")["BE"], solved("physics.nuclear.semi_empirical_binding_energy", ps="-1")["BE"]
    assert (ee - oo) / MeV == pytest.approx(2 * 11.18 / math.sqrt(56))


def test_deuterium_tritium_fusion_energy_and_momentum_sharing():
    out = solved("physics.nuclear.reaction_q_value")
    assert out["Q"] / MeV == pytest.approx(17.59, abs=0.01) and out["Kd"] / MeV == pytest.approx(14.05, abs=0.01)
    assert out["Kc"] / out["Kd"] == pytest.approx(1.00866492 / 4.00260325)


def test_cobalt_60_gram_is_about_1130_curies():
    assert solved("physics.nuclear.activity_from_mass")["ACi"] / 3.7e10 == pytest.approx(1131.6, rel=2e-3)


def test_generator_daughter_peaks_at_tmax_and_tends_to_the_equilibrium_ratio():
    out = solved("physics.nuclear.parent_daughter_chain")
    tm = out["tmax"]
    peak = solved("physics.nuclear.parent_daughter_chain", t=f"{tm} s")["AB"]
    assert peak > solved("physics.nuclear.parent_daughter_chain", t=f"{tm * 0.9} s")["AB"] and peak > solved("physics.nuclear.parent_daughter_chain", t=f"{tm * 1.1} s")["AB"]
    late = solved("physics.nuclear.parent_daughter_chain", t="400 h")
    assert late["AB"] / late["AA"] == pytest.approx(out["req"], rel=1e-3)


def test_one_half_life_of_radiocarbon_halves_the_activity():
    assert solved("physics.nuclear.radiocarbon_dating", fr="50 %")["age"] == pytest.approx(5730 * YR)
    assert solved("physics.nuclear.radiocarbon_dating", tw="5730 yr")["fa"] == pytest.approx(0.5)


def test_moderators_graphite_and_heavy_water():
    assert solved("physics.nuclear.neutron_moderation")["ncol"] == pytest.approx(115, abs=1)
    assert solved("physics.nuclear.neutron_moderation", Am="2")["xi"] == pytest.approx(0.725, abs=0.001)
    assert solved("physics.nuclear.neutron_moderation", Am="1.011")["xi"] == pytest.approx(1, abs=1e-3)


def test_dt_coulomb_barrier_and_fine_structure_constant():
    out = solved("physics.nuclear.fusion_coulomb_gamow")
    assert 1 / out["alf"] == pytest.approx(137.036, abs=0.001) and out["Bc"] / MeV == pytest.approx(0.444, abs=0.001) and out["Epk"] > solved("physics.nuclear.fusion_coulomb_gamow", kT="1 keV")["Epk"]


def test_pion_decay_conserves_energy_and_momentum():
    out = solved("physics.nuclear.two_body_decay")
    assert out["pc"] / MeV == pytest.approx(29.79, abs=0.01) and out["E1"] ** 2 == pytest.approx(out["pc"] ** 2 + (0.1134289 * 1.66053906660e-27 * c**2) ** 2, rel=1e-6)


def test_packing_fractions_of_the_cubic_lattices():
    assert solved("physics.solid.crystal_structure_density", Zc="2", rr=str(math.sqrt(3) / 4))["apf"] == pytest.approx(0.6802, abs=1e-4)
    assert solved("physics.solid.crystal_structure_density", Zc="1", rr="0.5")["apf"] == pytest.approx(pi / 6)
    assert solved("physics.solid.crystal_structure_density")["rho"] / 1000 == pytest.approx(8.93, abs=0.01)


def test_depletion_region_widens_with_reverse_bias_and_is_charge_neutral():
    out = solved("physics.solid.pn_junction")
    assert solved("physics.solid.pn_junction", Vr="10 V")["W"] > out["W"] and 1e23 * out["xp"] == pytest.approx(1e22 * out["xn"])
    assert out["Cj"] == pytest.approx(eps0 * 11.7 * 1e-6 / out["W"])


def test_silicon_gap_at_zero_kelvin_and_room_temperature():
    assert solved("physics.solid.band_gap_temperature", T="0.001 K")["Eg"] / e == pytest.approx(1.170, abs=1e-5) and solved("physics.solid.band_gap_temperature")["Eg"] / e == pytest.approx(1.1245, abs=2e-4)


def test_copper_debye_temperature_and_lorenz_number():
    assert solved("physics.solid.debye_temperature")["thD"] == pytest.approx(343, rel=0.02) and solved("physics.solid.wiedemann_franz")["L0"] == pytest.approx(2.443e-8, rel=1e-3)


def test_superconductor_limits():
    assert solved("physics.solid.superconductor_parameters", T="9.25 K", warnings_ok=True)["BcT"] == pytest.approx(0, abs=1e-12)
    assert solved("physics.solid.superconductor_parameters")["Ph0"] == pytest.approx(2.067833848e-15, rel=1e-9)


def test_chain_acoustic_limit_and_zone_boundary():
    out = solved("physics.solid.monatomic_chain_phonons", ka="0.01")
    assert out["wk"] / out["vs"] == pytest.approx(0.01 / 2.55e-10, rel=1e-4) and out["vg"] == pytest.approx(out["vs"], rel=1e-4)
    assert solved("physics.solid.monatomic_chain_phonons", ka="3.14159")["vg"] == pytest.approx(0, abs=1)


def test_curie_susceptibility_and_gadolinium_moment():
    assert solved("physics.solid.curie_paramagnetism")["pe"] == pytest.approx(7.94, abs=0.01)
    assert solved("physics.solid.curie_paramagnetism", T="150 K")["chi"] == pytest.approx(2 * solved("physics.solid.curie_paramagnetism")["chi"])


def test_thermoelectric_efficiency_limits():
    assert solved("physics.solid.thermoelectric_zt", Sb="0 uV/K")["eta"] == pytest.approx(0, abs=1e-12)
    assert solved("physics.solid.thermoelectric_zt", kt="1e-9 W/(m*K)")["eta"] == pytest.approx(0.25, rel=1e-3)


def test_large_quantum_dot_recovers_the_bulk_gap():
    assert solved("physics.solid.quantum_dot_brus", Rq="1000 nm")["Eqd"] / e == pytest.approx(1.74, abs=2e-3)


def test_kepler_orbit_relations():
    out = solved("physics.gravitation.elliptical_orbit_vis_viva")
    assert out["vp"] * out["rp"] == pytest.approx(out["va"] * out["ra"], rel=1e-9) and out["Tp"] / YR == pytest.approx(1.0, abs=2e-4)
    circ = solved("physics.gravitation.elliptical_orbit_vis_viva", ecc="0")
    assert circ["vp"] == pytest.approx(math.sqrt(G * 1.98847e30 / AU), rel=1e-9)


def test_hill_sphere_of_the_earth_and_the_moon_roche_limit():
    assert solved("physics.gravitation.tides_roche_hill", M="1.98847e30 kg", m="5.972e24 kg", a="1 AU")["rH"] / 1e9 == pytest.approx(1.50, abs=0.01)
    assert solved("physics.gravitation.tides_roche_hill")["dR"] / 1e3 == pytest.approx(18365, rel=1e-3)


def test_the_sun_has_one_solar_luminosity_and_earth_is_cooler_with_albedo():
    sun = solved("physics.gravitation.stellar_luminosity_magnitude", Rs="695.7 Mm", Ts="5772 K", ds="149.597870700 Gm")
    assert sun["Lr"] == pytest.approx(1.0, abs=2e-3) and sun["Fs"] == pytest.approx(1361, rel=2e-3)
    assert solved("physics.gravitation.planet_equilibrium_temperature", Ab="0")["Teq"] > solved("physics.gravitation.planet_equilibrium_temperature")["Teq"]


def test_hubble_time_and_critical_density_for_h0_70():
    out = solved("physics.gravitation.hubble_law_cosmology")
    assert out["tH"] / YR / 1e9 == pytest.approx(13.97, abs=0.02) and out["rc"] == pytest.approx(9.2e-27, rel=0.01)


def test_kepler_third_law_for_the_earth_sun_pair_and_star_masses_add_up():
    assert solved("physics.gravitation.binary_star_masses", a="1 AU", Pb="1 yr", a1="0 AU")["Mtr"] == pytest.approx(1.0, abs=2e-3)
    out = solved("physics.gravitation.binary_star_masses")
    assert out["M1"] + out["M2"] == pytest.approx(out["Mt"])


def test_solar_scaling_of_luminosity_lifetime_and_eddington_limit():
    out = solved("physics.gravitation.stellar_mass_luminosity_eddington", Mr="1", Mbh="1")
    assert out["Lms"] == pytest.approx(Lsun) and out["tl"] == pytest.approx(1e10 * YR) and out["LEr"] == pytest.approx(3.28e4, rel=0.01)


def test_einstein_radius_scales_with_the_root_of_the_mass():
    assert solved("physics.gravitation.einstein_ring", M="7.95388e42 kg")["thE"] == pytest.approx(2 * solved("physics.gravitation.einstein_ring")["thE"])


def test_black_hole_scalings_and_the_suns_schwarzschild_radius():
    sun = solved("physics.gravitation.black_hole_thermodynamics", Mr="1")
    assert sun["rs"] / 1e3 == pytest.approx(2.953, abs=0.001) and solved("physics.gravitation.black_hole_thermodynamics", Mr="20")["TH"] == pytest.approx(sun["TH"] / 20)
    assert sun["Sbh"] == pytest.approx(1.05e77, rel=0.01)


def test_mercury_perihelion_and_grazing_starlight():
    out = solved("physics.gravitation.gr_tests_precession_deflection")
    assert out["dcen"] * 206264.806 == pytest.approx(42.98, abs=0.05)
    assert out["alp"] * 206264.806 == pytest.approx(1.751, abs=0.002)


def test_every_core_physics_batch_c_calculation_is_catalogued_under_physics():
    for cid in CASES:
        assert "physics" in CAT.get(cid).disciplines and g > 0
