"""Broad physics, part B: analytical mechanics, plasma, particle physics, astrophysics (independent formulas, SI quantities)."""

import math

import pytest
from pcutil import CAT, G, Da, c, check_case, e, eps0, g, hbar, kB, me, mu0, pi, solved

AM = "physics.analytical."
PL = "physics.plasma."
PA = "physics.particle."
AS = "physics.astro."
Msun = 1.98841e30
mH = 1.00782503223 * Da
GeV = 1e9 * e


def rigid(x):
    Wp = (x["I3"] - x["I1"]) / x["I1"] * x["w3"]
    return {"Wp": Wp, "Tp": 2 * pi / Wp, "Lm": math.hypot(x["I1"] * x["w1"], x["I3"] * x["w3"]), "KE": x["I1"] * x["w1"] ** 2 / 2 + x["I3"] * x["w3"] ** 2 / 2, "th": math.atan(x["I1"] * x["w1"] / (x["I3"] * x["w3"]))}


def coupled(x):
    w1, w2 = math.sqrt(x["ks"] / x["m"]), math.sqrt((x["ks"] + 2 * x["kc"]) / x["m"])
    return {"w1": w1, "w2": w2, "f1": w1 / (2 * pi), "f2": w2 / (2 * pi), "Tb": 2 * pi / (w2 - w1), "Tt": pi / (w2 - w1)}


def hoop(x):
    wc = math.sqrt(g / x["Rh"])
    th = math.acos(g / (x["Wh"] ** 2 * x["Rh"])) if x["Wh"] > wc else 0.0
    wo = x["Wh"] * math.sin(th) if x["Wh"] > wc else math.sqrt(g / x["Rh"] - x["Wh"] ** 2)
    return {"wc": wc, "th0": th, "wo": wo}


def double(x):
    mu = x["mu"]
    l1, l2 = 1 + mu - math.sqrt(mu * (1 + mu)), 1 + mu + math.sqrt(mu * (1 + mu))
    return {"l1": l1, "l2": l2, "w1": math.sqrt(l1 * g / x["ll"]), "w2": math.sqrt(l2 * g / x["ll"]), "r1": l1 / (1 - l1), "r2": l2 / (1 - l2)}


def adiabatic(x):
    w1, w2 = math.sqrt(x["k1"] / x["m"]), math.sqrt(x["k2"] / x["m"])
    E2 = x["E1"] / w1 * w2
    return {"w1": w1, "w2": w2, "Jac": x["E1"] / w1, "E2": E2, "A1": math.sqrt(2 * x["E1"] / x["k1"]), "A2": math.sqrt(2 * E2 / x["k2"])}


def alfven(x):
    mi = x["mi"]
    vA = x["B"] / math.sqrt(mu0 * x["ni"] * mi)
    cs = math.sqrt((x["Te"] + x["gam"] * x["Ti"]) / mi)
    pB = x["B"] ** 2 / (2 * mu0)
    return {"vA": vA, "cs": cs, "vf": math.hypot(vA, cs), "pB": pB, "bt": x["ni"] * (x["Te"] + x["Ti"]) / pB}


def mirror(x):
    Rm = x["Bx"] / x["Bm"]
    Bp = x["Bm"] / math.sin(x["al"]) ** 2
    return {"Rm": Rm, "thl": math.asin(math.sqrt(1 / Rm)), "ft": math.sqrt(1 - 1 / Rm), "Bp": Bp, "mom": x["Ek"] * math.sin(x["al"]) ** 2 / x["Bm"], "tr": 1 if Bp < x["Bx"] else 0}


def lawson(x):
    tp = x["nd"] * x["Ti"] * x["tE"]
    L3 = 3e21 * 1e3 * e
    return {"tp": tp, "rt": tp / L3, "tq": L3 / (x["nd"] * x["Ti"])}


def spitzer(x):
    eta = 5.2e-5 * x["Zi"] * x["lnL"] / (x["Te"] / e) ** 1.5
    return {"eta": eta, "Dm": eta / mu0, "tD": mu0 * x["Ls"] ** 2 / eta, "Rm": mu0 * x["Ls"] * x["vf"] / eta}


def waves(x):
    wp = math.sqrt(x["ne"] * e**2 / (eps0 * me))
    wk = math.sqrt(wp**2 + 3 * x["kw"] ** 2 * x["Te"] / me)
    return {"wp": wp, "fp": wp / (2 * pi), "lD": math.sqrt(eps0 * x["Te"] / (x["ne"] * e**2)), "wk": wk, "vph": wk / x["kw"], "vg": 3 * x["kw"] * x["Te"] / (me * wk), "cs": math.sqrt((x["Te"] + 3 * x["Ti"]) / x["mi"])}


def collisions(x):
    TeV = x["Te"] / e
    nue = 2.91e-6 * (x["ne"] / 1e6) * x["lnL"] / TeV**1.5          # per cm^3 -> per m^3 handled below
    nue = 2.91e-6 * (x["ne"] * 1e-6) * x["lnL"] / TeV**1.5
    vte = math.sqrt(x["Te"] / me)
    return {"nue": nue, "vte": vte, "mfp": vte / nue}


def collider(x):
    ma, mb, Ea, Eb = x["ma"], x["mb"], x["Ea"], x["Eb"]
    pa, pb = math.sqrt(Ea**2 - ma**2), math.sqrt(Eb**2 - mb**2)
    s = ma**2 + mb**2 + 2 * (Ea * Eb + pa * pb)
    return {"pa": pa, "pb": pb, "s": s, "rs": math.sqrt(s), "Eft": (s - ma**2 - mb**2) / (2 * mb)}


def neutrino(x):
    ph = x["dm"] * x["Lb"] / (4 * hbar * c * x["En"])
    return {"ph": ph, "Pa": x["s2"] * math.sin(ph) ** 2, "Lo": 4 * pi * hbar * c * x["En"] / x["dm"]}


def resonance(x):
    tau = hbar / x["Gm"]
    gm = x["gm"]
    return {"tau": tau, "ct": c * tau, "Ld": gm * math.sqrt(1 - 1 / gm**2) * c * tau, "rl": (x["Gm"] / 2) ** 2 / ((x["En"] - x["Mr"]) ** 2 + (x["Gm"] / 2) ** 2)}


def lcdm(x):
    H0 = x["hh"] * 100e3 / 3.0856775814913673e22
    Om = x["Om"]
    OL = 1 - Om
    z = x["zz"]
    pref = 2 / (3 * H0 * math.sqrt(OL))
    return {"OL": OL, "H0": H0, "Hz": H0 * math.sqrt(Om * (1 + z) ** 3 + OL), "t0": pref * math.asinh(math.sqrt(OL / Om)), "tz": pref * math.asinh(math.sqrt(OL / Om) * (1 + z) ** -1.5),
            "rc": 3 * H0**2 / (8 * pi * G), "q0": Om / 2 - OL}


def chandra(x):
    M = 2.018236 * math.sqrt(3 * pi) / 2 * (hbar * c / G) ** 1.5 / (x["mue"] * mH) ** 2
    return {"MCh": M, "MS": M / Msun}


def jeans(x):
    lJ = math.sqrt(15 * kB * x["T"] / (4 * pi * G * x["mum"] * mH * x["rho"]))
    MJ = 4 * pi / 3 * x["rho"] * (lJ / 2) ** 3
    return {"lJ": lJ, "MJ": MJ, "MS": MJ / Msun, "tff": math.sqrt(3 * pi / (32 * G * x["rho"]))}


def gw(x):
    m1, m2, f = x["m1"], x["m2"], x["fg"]
    Mc = (m1 * m2) ** 0.6 / (m1 + m2) ** 0.2
    Mk = Mc * Msun
    return {"Mc": Mc, "tc": 5 / 256 * c**5 / G ** (5 / 3) * (pi * f) ** (-8 / 3) * Mk ** (-5 / 3), "hs": 4 * (G * Mk) ** (5 / 3) * (pi * f) ** (2 / 3) / (c**4 * x["dist"]),
            "fi": c**3 / (6**1.5 * pi * G * (m1 + m2) * Msun)}


def parallax(x):
    au, pc = 1.495978707e11, 3.0856775814913673e16
    d = au / math.tan(x["pa"])
    mu = 5 * math.log10(d / pc / 10)
    return {"d": d, "dpc": d / pc, "mu": mu, "Mabs": x["mapp"] - mu}


def virial(x):
    return {"Tv": G * x["Ms"] * x["mum"] * mH / (kB * x["Rs"]), "Pc": 3 * G * x["Ms"] ** 2 / (8 * pi * x["Rs"] ** 4), "rho": 3 * x["Ms"] / (4 * pi * x["Rs"] ** 3), "tKH": G * x["Ms"] ** 2 / (x["Rs"] * x["Ls"])}


def exoplanet(x):
    a = (G * (x["Ms"] + x["mp"]) * x["Po"] ** 2 / (4 * pi**2)) ** (1 / 3)
    Td = x["Po"] / pi * math.asin(math.sqrt((x["Rs"] + x["Rp"]) ** 2 - (x["bi"] * x["Rs"]) ** 2) / a)
    K = (2 * pi * G / x["Po"]) ** (1 / 3) * x["mp"] * math.sin(x["inc"]) / (x["Ms"] + x["mp"]) ** (2 / 3)
    return {"dep": (x["Rp"] / x["Rs"]) ** 2, "ao": a, "Td": Td, "Kr": K}


CASES = {
    AM + "torque_free_rigid_body": rigid, AM + "coupled_oscillators": coupled, AM + "bead_on_rotating_hoop": hoop, AM + "double_pendulum_modes": double,
    AM + "adiabatic_invariant_oscillator": adiabatic, PL + "alfven_and_magnetosonic_speeds": alfven, PL + "magnetic_mirror": mirror, PL + "lawson_triple_product": lawson, PL + "spitzer_resistivity": spitzer,
    PL + "langmuir_and_ion_acoustic_waves": waves, PL + "electron_ion_collisions": collisions, PA + "collider_cm_energy": collider, PA + "neutrino_oscillation": neutrino, PA + "resonance_width_lifetime": resonance,
    AS + "flat_lcdm_age_expansion": lcdm, AS + "chandrasekhar_limit": chandra, AS + "jeans_instability": jeans, AS + "gravitational_wave_inspiral": gw, AS + "parallax_distance_modulus": parallax,
    AS + "stellar_virial_estimates": virial, AS + "exoplanet_transit_radial_velocity": exoplanet,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


def test_chandler_wobble_period_of_a_rigid_earth_and_chandrasekhar_mass():
    assert solved(AM + "torque_free_rigid_body")["Tp"] / 86400 == pytest.approx(303, abs=1)
    assert solved(AS + "chandrasekhar_limit")["MS"] == pytest.approx(1.44, abs=0.02)


def test_equal_mass_double_pendulum_has_the_textbook_modes():
    out = solved(AM + "double_pendulum_modes")
    assert out["l1"] == pytest.approx(2 - math.sqrt(2)) and out["l2"] == pytest.approx(2 + math.sqrt(2))


def test_coupled_modes_degenerate_when_the_coupling_vanishes():
    out = solved(AM + "coupled_oscillators", kc="1e-9 N/m")
    assert out["w1"] == pytest.approx(out["w2"], rel=1e-6) and out["Tb"] > 1e6


def test_hoop_below_critical_speed_stays_at_the_bottom():
    out = solved(AM + "bead_on_rotating_hoop", Wh="3 rad/s")
    assert out["th0"] == 0 and out["wo"] == pytest.approx(math.sqrt(g / 0.2 - 9))


def test_adiabatic_invariant_conserves_the_ratio_of_energy_to_frequency():
    out = solved(AM + "adiabatic_invariant_oscillator")
    assert out["E2"] / out["w2"] == pytest.approx(10e-3 / out["w1"])


def test_lcdm_matter_only_limit_is_the_einstein_de_sitter_age():
    out = solved(AS + "flat_lcdm_age_expansion", Om="0.999999")
    assert out["t0"] == pytest.approx(2 / (3 * out["H0"]), rel=1e-3)


def test_loss_cone_for_equal_fields_is_ninety_degrees_and_fusion_threshold():
    assert solved(PL + "magnetic_mirror", Bx="0.5 T")["thl"] == pytest.approx(pi / 2)
    assert solved(PL + "lawson_triple_product", tE="0.6 s")["rt"] == pytest.approx(0.3)


def test_z_boson_lifetime_and_lhc_energy_and_neutrino_oscillation_length():
    assert solved(PA + "resonance_width_lifetime")["tau"] == pytest.approx(2.638e-25, rel=1e-3)
    assert solved(PA + "collider_cm_energy")["rs"] / (1e12 * e) == pytest.approx(13, rel=1e-4)
    assert solved(PA + "neutrino_oscillation")["Lo"] / 1e3 == pytest.approx(595, rel=0.01)


def test_ligo_like_chirp_mass_and_hot_jupiter_signals():
    assert solved(AS + "gravitational_wave_inspiral")["Mc"] == pytest.approx(28.1, abs=0.1)
    out = solved(AS + "exoplanet_transit_radial_velocity")
    assert out["dep"] == pytest.approx(0.015, abs=0.001) and out["Kr"] == pytest.approx(84, abs=2)


def test_sirius_absolute_magnitude_and_catalogued():
    assert solved(AS + "parallax_distance_modulus")["Mabs"] == pytest.approx(1.43, abs=0.02)
    for cid in CASES:
        assert "physics" in CAT.get(cid).disciplines
    assert "Plasma Physics" in CAT.get(PL + "magnetic_mirror").subdisciplines and "Analytical Mechanics" in CAT.get(AM + "coupled_oscillators").subdisciplines
