"""Broad physics, part A: quantum and statistical mechanics (independent formulas, SI quantities)."""

import math

import pytest
from pcutil import CAT, NA, R, Rinf, a0, c, check_case, e, eps0, g, h, hbar, kB, me, pi, solved

Q = "physics.quantum."
S = "physics.statmech."
muB = e * hbar / (2 * me)
Eh = 2 * Rinf * h * c


def finite_well(x):
    z0 = x["Lw"] / 2 * math.sqrt(2 * x["mr"] * me * x["V0"]) / hbar
    E1 = pi**2 * hbar**2 / (2 * x["mr"] * me * x["Lw"] ** 2)
    return {"z0": z0, "nb": math.ceil(2 * z0 / pi), "E1": E1, "dr": x["V0"] / E1}


def delta(x):
    m = x["mr"] * me
    return {"Eb": m * x["al"] ** 2 / (2 * hbar**2), "xi": hbar**2 / (m * x["al"]), "Tt": 1 / (1 + m * x["al"] ** 2 / (2 * hbar**2 * x["En"]))}


def step(x):
    k1 = math.sqrt(2 * x["mr"] * me * x["En"]) / hbar
    k2 = math.sqrt(2 * x["mr"] * me * (x["En"] - x["V0"])) / hbar
    r = ((k1 - k2) / (k1 + k2)) ** 2
    return {"k1": k1, "k2": k2, "Rr": r, "Tt": 1 - r}


def hyd(x):
    n, l, Z = x["nq"], x["lq"], x["Z"]
    a = a0 / Z
    r2 = a * a * n * n * (5 * n * n + 1 - 3 * l * (l + 1)) / 2
    return {"aZ": a, "rm": a * (3 * n * n - l * (l + 1)) / 2, "r2": r2, "ri": 1 / (n * n * a), "rr": math.sqrt(r2), "rp": n * n * a, "En": -Rinf * h * c * Z * Z / n**2}


def rabi(x):
    Og = math.hypot(x["Om"], x["De"])
    return {"Og": Og, "Pe": x["Om"] ** 2 / Og**2 * math.sin(Og * x["tp"] / 2) ** 2, "tpi": pi / x["Om"], "tpi2": pi / (2 * x["Om"]), "Pm": x["Om"] ** 2 / Og**2}


def angmom(x):
    l, m = x["lq"], x["ml"]
    return {"Lm": math.sqrt(l * (l + 1)) * hbar, "Lz": m * hbar, "th": math.acos(m / math.sqrt(l * (l + 1))), "thm": math.acos(l / math.sqrt(l * (l + 1))), "nst": 2 * l + 1}


def fine(x):
    n, l, Z = x["nq"], x["lq"], x["Z"]
    al = e**2 / (4 * pi * eps0 * hbar * c)
    En = -Rinf * h * c * Z**2 / n**2
    d1 = En * (al * Z) ** 2 / n**2 * (n / l - 0.75)
    d2 = En * (al * Z) ** 2 / n**2 * (n / (l + 1) - 0.75)
    return {"alf": al, "En": En, "d1": d1, "d2": d2, "sp": d2 - d1, "fs": (d2 - d1) / h}


def lande(x):
    L, S_, J = x["Lq"], x["Sq"], x["Jq"]
    gj = 1 + (J * (J + 1) + S_ * (S_ + 1) - L * (L + 1)) / (2 * J * (J + 1))
    dE = gj * x["mJ"] * muB * x["B"]
    return {"muB": muB, "gj": gj, "dE": dE, "fz": dE / h}


def helium(x):
    Zf = x["Z"] - 5 / 16
    return {"Eh": Eh, "Zf": Zf, "E0": -Zf**2 * Eh, "IP": (Zf**2 - x["Z"] ** 2 / 2) * Eh}


def dos(x):
    m, E = x["mr"] * me, x["En"]
    return {"g3": (2 * m) ** 1.5 * math.sqrt(E) / (2 * pi**2 * hbar**3), "g2": m / (pi * hbar**2), "g1": 2 * math.sqrt(m / (2 * E)) / (pi * hbar)}


def landau(x):
    B = x["B"]
    nB = e * B / h
    nu = x["ns"] / nB
    return {"wc": hbar * e * B / (x["mr"] * me), "lB": math.sqrt(hbar / (e * B)), "nB": nB, "nu": nu, "RH": h / (e**2 * nu)}


def exotic(x):
    mu = x["m1"] * x["m2"] / (x["m1"] + x["m2"])
    return {"mu": mu, "E1": -Rinf * h * c * mu, "aB": a0 / mu, "lam": 1 / (Rinf * mu * (1 / x["nl"] ** 2 - 1 / x["nh"] ** 2))}


def emission(x):
    w = x["dE"] / hbar
    A = w**3 * e**2 * (x["Rr"] * a0) ** 2 * x["an"] / (3 * pi * eps0 * hbar * c**3)
    return {"wt": w, "Ar": A, "tau": 1 / A, "dnu": A / (2 * pi)}


def three_level(x):
    T = x["T"]
    x1, x2 = math.exp(-x["e1"] / (kB * T)), math.exp(-x["e2"] / (kB * T))
    Z = x["g0"] + x["g1"] * x1 + x["g2"] * x2
    U = (x["g1"] * x["e1"] * x1 + x["g2"] * x["e2"] * x2) / Z
    U2 = (x["g1"] * x["e1"] ** 2 * x1 + x["g2"] * x["e2"] ** 2 * x2) / Z
    F = -kB * T * math.log(Z)
    return {"x1": x1, "x2": x2, "Zp": Z, "p0": x["g0"] / Z, "p1": x["g1"] * x1 / Z, "p2": x["g2"] * x2 / Z, "U": U, "U2": U2, "F": F, "S": (U - F) / T, "Cv": (U2 - U * U) / (kB * T * T)}


def einstein(x):
    N, q, ep = x["Nn"], x["q"], x["ep"]
    lnO = math.lgamma(q + N) - math.lgamma(q + 1) - math.lgamma(N)
    T = ep / (kB * math.log(1 + N / q))
    xx = ep / (kB * T)
    return {"lnO": lnO, "S": kB * lnO, "T": T, "U": q * ep, "xx": xx, "Cv": N * kB * xx**2 * math.exp(xx) / (math.exp(xx) - 1) ** 2}


def maxwell(x):
    vp = math.sqrt(2 * kB * x["T"] / x["ma"])
    xr = x["vc"] / vp
    fa = math.erfc(xr) + 2 * xr * math.exp(-xr * xr) / math.sqrt(pi)
    return {"vp": vp, "xr": xr, "fa": fa, "fb": 1 - fa}


def barometric(x):
    H = R * x["T"] / (x["Mm"] * g)
    mb = 4 * pi * x["rp"] ** 3 * x["dr"] / 3
    return {"H": H, "rat": math.exp(-x["hh"] / H), "mb": mb, "Hp": kB * x["T"] / (mb * g)}


def brillouin(x):
    J, gl = x["Jq"], x["gl"]
    xb = gl * muB * J * x["B"] / (kB * x["T"])
    coth = lambda z: 1 / math.tanh(z)
    BJ = (2 * J + 1) / (2 * J) * coth((2 * J + 1) * xb / (2 * J)) - coth(xb / (2 * J)) / (2 * J)
    Ms = x["nd"] * gl * muB * J
    return {"muB": muB, "xb": xb, "BJ": BJ, "Ms": Ms, "Mg": Ms * BJ, "fr": BJ}


def ising(x):
    J, T = x["Jc"], x["T"]
    return {"Tmf": x["zc"] * J / kB, "T2": 2 * J / (kB * math.log(1 + math.sqrt(2))), "rat": 2 / (x["zc"] * math.log(1 + math.sqrt(2))),
            "Ms": (1 - math.sinh(2 * J / (kB * T)) ** -4) ** 0.125, "xi": -1 / math.log(math.tanh(J / (kB * T)))}


def photon_gas(x):
    T = x["T"]
    n = 2 * 1.2020569031595942 / pi**2 * (kB * T / (hbar * c)) ** 3
    u = pi**2 * (kB * T) ** 4 / (15 * hbar**3 * c**3)
    return {"nph": n, "uph": u, "pph": u / 3, "sph": 4 * u / (3 * T), "Em": u / n}


def brownian(x):
    fr = 6 * pi * x["eta"] * x["rp"]
    D = kB * x["T"] / fr
    return {"fr": fr, "Dc": D, "x1": math.sqrt(2 * D * x["tt"]), "x3": math.sqrt(6 * D * x["tt"]), "tL": x["Ld"] ** 2 / (2 * D)}


def landauer(x):
    E = kB * x["T"] * math.log(2)
    return {"Eb": E, "Eg": E, "Pw": E * x["rate"], "Sb": x["Nb"] * kB * math.log(2)}


def lj(x):
    eps = kB * x["epK"]
    s, r = x["sg"], x["rs"]
    return {"eps": eps, "rm": 2 ** (1 / 6) * s, "U": 4 * eps * ((s / r) ** 12 - (s / r) ** 6), "Fr": 24 * eps / r * (2 * (s / r) ** 12 - (s / r) ** 6), "TB": 3.418 * x["epK"]}


def thermal(x):
    lam = h / math.sqrt(2 * pi * x["ma"] * kB * x["T"])
    return {"lam": lam, "nQ": lam**-3, "dg": x["nd"] * lam**3, "mu": kB * x["T"] * math.log(x["nd"] * lam**3)}


def landau_theory(x):
    return {"m0": math.sqrt(x["aL"] * (x["Tc"] - x["T"]) / (2 * x["bL"])), "dF": -x["aL"] ** 2 * (x["Tc"] - x["T"]) ** 2 / (4 * x["bL"]), "dC": x["aL"] ** 2 * x["Tc"] / (2 * x["bL"])}


CASES = {
    Q + "finite_square_well": finite_well, Q + "delta_function_potential": delta, Q + "potential_step": step, Q + "hydrogen_expectation_values": hyd, Q + "rabi_oscillation": rabi,
    Q + "angular_momentum_quantisation": angmom, Q + "hydrogen_fine_structure": fine, Q + "lande_zeeman_shift": lande, Q + "helium_variational": helium, Q + "free_electron_density_of_states": dos,
    Q + "landau_levels": landau, Q + "exotic_hydrogenic_atoms": exotic, Q + "spontaneous_emission_rate": emission, S + "three_level_canonical": three_level, S + "einstein_solid_entropy": einstein,
    S + "maxwell_speed_fraction": maxwell, S + "barometric_sedimentation": barometric, S + "brillouin_magnetisation": brillouin, S + "ising_critical_temperature": ising, S + "photon_gas_cmb": photon_gas,
    S + "brownian_motion": brownian, S + "landauer_limit": landauer, S + "lennard_jones": lj, S + "thermal_wavelength_quantum_concentration": thermal, S + "landau_theory": landau_theory,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-6)


def test_hydrogen_2p_to_1s_lifetime_and_fine_structure():
    assert solved(Q + "spontaneous_emission_rate")["tau"] * 1e9 == pytest.approx(1.6, rel=0.01)
    assert solved(Q + "hydrogen_fine_structure")["fs"] / 1e9 == pytest.approx(10.95, rel=0.01)


def test_rabi_pi_pulse_inverts_the_population_on_resonance():
    assert solved(Q + "rabi_oscillation", De="0 rad/us", Om="1 rad/us", tp=f"{math.pi} us")["Pe"] == pytest.approx(1)
    assert solved(Q + "rabi_oscillation", De="0 rad/us", Om="1 rad/us", tp=f"{math.pi / 2} us")["Pe"] == pytest.approx(0.5)


def test_step_and_barrier_limits():
    assert solved(Q + "potential_step", V0="0 eV")["Rr"] == pytest.approx(0, abs=1e-12)
    out = solved(Q + "delta_function_potential")
    assert out["Eb"] > 0 and 0 < out["Tt"] < 1


def test_positronium_and_muonic_hydrogen_scaling():
    assert solved(Q + "exotic_hydrogenic_atoms")["E1"] / e == pytest.approx(-6.8, abs=0.01)
    muonic = solved(Q + "exotic_hydrogenic_atoms", m1="206.768", m2="1836.15")
    assert muonic["E1"] / e == pytest.approx(-2528, rel=0.01)


def test_helium_variational_energy_and_ionisation():
    out = solved(Q + "helium_variational")
    assert out["E0"] / e == pytest.approx(-77.5, abs=0.1) and out["IP"] / e == pytest.approx(23.1, abs=0.1)


def test_density_of_states_integrates_to_free_electron_count():
    # N/V = integral g3 dE = (2/3) g3(E) E for a parabolic band
    n = 2 / 3 * solved(Q + "free_electron_density_of_states")["g3"] * e
    kf = (3 * pi**2 * n) ** (1 / 3)
    assert hbar**2 * kf**2 / (2 * me) == pytest.approx(e, rel=1e-9)


def test_einstein_solid_high_temperature_limit_and_sum_of_populations():
    assert solved(S + "einstein_solid_entropy", Nn="300", q="30000")["Cv"] == pytest.approx(300 * kB, rel=1e-3)
    out = solved(S + "three_level_canonical")
    assert out["p0"] + out["p1"] + out["p2"] == pytest.approx(1)


def test_photon_gas_numbers_for_the_cmb_and_stefan_boltzmann():
    out = solved(S + "photon_gas_cmb")
    assert out["nph"] / 1e6 == pytest.approx(411, rel=0.01)
    sigma = 5.670374419e-8
    assert out["uph"] == pytest.approx(4 * sigma / c * 2.7255**4, rel=1e-6)


def test_perrin_and_atmosphere_scale_heights_have_the_right_size():
    out = solved(S + "barometric_sedimentation")
    assert out["H"] / 1e3 == pytest.approx(8.4, abs=0.1)
    assert NA > 0


def test_ising_critical_ratio_and_magnetisation_vanish_at_tc():
    assert solved(S + "ising_critical_temperature")["rat"] == pytest.approx(0.5673, abs=1e-3)
    Tc = solved(S + "ising_critical_temperature")["T2"]
    assert solved(S + "ising_critical_temperature", T=f"{Tc * 0.99999999} K")["Ms"] < 0.2


def test_lennard_jones_minimum_force_vanishes_and_energy_is_minus_epsilon():
    rm = solved(S + "lennard_jones")["rm"]
    out = solved(S + "lennard_jones", rs=f"{rm} m")
    assert out["Fr"] == pytest.approx(0, abs=1e-18) and out["U"] == pytest.approx(-out["eps"], rel=1e-9)


def test_landau_theory_free_energy_is_minimum_of_the_potential():
    x = CAT.get(S + "landau_theory")
    assert x is not None
    out = solved(S + "landau_theory")
    a, b, dT = 4e5, 1e8, 50
    assert a * (-dT) * out["m0"] ** 2 + b * out["m0"] ** 4 == pytest.approx(out["dF"])


def test_catalogued_under_the_new_subdisciplines():
    for cid in CASES:
        assert "physics" in CAT.get(cid).disciplines
    assert "Quantum Mechanics" in CAT.get(Q + "rabi_oscillation").subdisciplines and "Statistical Mechanics" in CAT.get(S + "ising_critical_temperature").subdisciplines
