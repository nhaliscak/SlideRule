"""Physics and chemistry stage four: organic mechanisms, thermochemistry, transport, electrochemistry, astrophysics, plasma and particle physics (independent formulas, SI)."""

import math

import pytest
from pcutil import CAT, F, R, c, check_case, e, eps0, g, h, kB, me, pi, solved

amu = 1.66053906660e-27
Msun = 1.98847e30
Lsun = 3.828e26
pc = 3.0856775814913673e16
Om = 7.2921159e-5
mu0 = 1.25663706212e-6


def sn(x):
    r2, r1 = x["kS"] * x["RX"] * x["Nu"], x["k1"] * x["RX"]
    k = x["k1"] + x["kS"] * x["Nu"]
    return {"r2": r2, "r1": r1, "fr": r2 / (r1 + r2), "kobs": k, "th": math.log(2) / k}


def bronsted(x):
    d = x["al"] * (x["pK1"] - x["pK2"])
    return {"k2": x["k1"] * 10**d, "rt": 10**d, "dl": d}


def evans(x):
    ea = x["E0"] + x["al"] * x["dH"]
    return {"Ea": ea, "kr": x["Af"] * math.exp(-ea / (R * x["T"])), "rt": math.exp(-x["al"] * x["dH"] / (R * x["T"]))}


def maier(x):
    a, b, cc, t1, t2 = x["a"], x["b"], x["c"], x["T1"], x["T2"]
    # numerical integration of Cp and Cp/T (Simpson), independent of the closed forms
    n = 2000
    ts = [t1 + (t2 - t1) * i / n for i in range(n + 1)]
    w = [1] + [4 if i % 2 else 2 for i in range(1, n)] + [1]
    dh = sum(wi * (a + b * t + cc / t**2) for wi, t in zip(w, ts)) * (t2 - t1) / (3 * n)
    ds = sum(wi * (a + b * t + cc / t**2) / t for wi, t in zip(w, ts)) * (t2 - t1) / (3 * n)
    return {"Cp1": a + b * t1 + cc / t1**2, "Cp2": a + b * t2 + cc / t2**2, "dH": dh, "dS": ds}


def stokes(x):
    d = kB * x["T"] / (6 * pi * x["et"] * x["rh"])
    dr = kB * x["T"] / (8 * pi * x["et"] * x["rh"] ** 3)
    return {"D": d, "Dr": dr, "tc": 1 / (6 * dr), "rm": kB * x["T"] / (6 * pi * x["et"] * x["Dm"])}


def ranz(x):
    re, sc = x["rho"] * x["v"] * x["dp"] / x["mu"], x["mu"] / (x["rho"] * x["Dd"])
    sh = 2 + 0.6 * math.sqrt(re) * sc ** (1 / 3)
    kc = sh * x["Dd"] / x["dp"]
    return {"Re": re, "Sc": sc, "Sh": sh, "kc": kc, "Nf": kc * (x["Cs"] - x["Cb"])}


def stern(x):
    b = x["ba"] * x["bc"] / (2.302585092994046 * (x["ba"] + x["bc"]))
    ic = b / x["Rp"]
    return {"Bs": b, "ic": ic, "cr": ic * x["EW"] / (F * x["rm"])}


def cottrell(x):
    k = x["ni"] * F * x["Ae"] * x["Cb"]
    return {"it": k * math.sqrt(x["Dd"] / (pi * x["tm"])), "Qt": 2 * k * math.sqrt(x["Dd"] * x["tm"] / pi), "dl": math.sqrt(pi * x["Dd"] * x["tm"])}


def randles(x):
    n = x["ni"]
    return {"ip": 0.4463 * n * F * x["Ae"] * x["Cb"] * math.sqrt(n * F * x["vs"] * x["Dd"] / (R * x["T"])), "dE": 2.218 * R * x["T"] / (n * F)}


def photolysis(x):
    j = x["sg"] * x["ph"] * x["Fa"]
    return {"J": j, "tau": 1 / j, "th": math.log(2) / j, "fp": 1 - math.exp(-j * x["tt"])}


def wigner(x):
    u = h * c * x["nu"] / (kB * x["T"])
    return {"xw": u, "kp": 1 + u**2 / 24, "kc": (1 + u**2 / 24) * x["kt"]}


def venturi(x):
    ar = (x["D2"] / x["D1"]) ** 2
    v2 = math.sqrt(2 * x["dP"] / (x["rho"] * (1 - ar**2)))
    return {"v2": v2, "v1": v2 * ar, "Qv": v2 * pi * x["D2"] ** 2 / 4, "vp": math.sqrt(2 * x["dPp"] / x["rho"])}


def poiseuille(x):
    q = pi * x["Rr"] ** 4 * x["dP"] / (8 * x["mu"] * x["Ltu"])
    v = q / (pi * x["Rr"] ** 2)
    return {"Qv": q, "vm": v, "tw": x["Rr"] * x["dP"] / (2 * x["Ltu"]), "Re": x["rho"] * v * 2 * x["Rr"] / x["mu"]}


def cepheid(x):
    day = 86400.0
    M = -2.43 * (math.log10(x["Pd"] / day) - 1) - 4.05
    mu = x["mv"] - M - x["Av"]
    dpc = 10 ** (mu / 5 + 1)
    return {"Mabs": M, "mu": mu, "dpc": dpc, "d": dpc * pc}


def lifetime(x):
    ls = Lsun * x["Mr"] ** 3.5
    return {"Ls": ls, "Lr": ls / Lsun, "tms": 0.007 * 0.1 * x["Mr"] * Msun * c**2 / ls}


def pulsar(x):
    i = 0.4 * x["Mn"] * x["Rn"] ** 2
    p, pd = x["Pp"], x["Pd"]
    return {"In": i, "ta": p / (2 * pd), "Bs": math.sqrt(3 * mu0 * c**3 * i * p * pd / (8 * pi**3 * x["Rn"] ** 6)), "Ed": 4 * pi**2 * i * pd / p**3}


def kepler(x):
    m, k, L, E = x["ms"], x["kk"], x["Lz"], x["En"]
    r0 = L**2 / (m * k)
    ec = math.sqrt(1 + 2 * E * L**2 / (m * k**2))
    a = -k / (2 * E)
    return {"r0": r0, "Um": -m * k**2 / (2 * L**2), "ec": ec, "rmin": r0 / (1 + ec), "rmax": r0 / (1 - ec), "aa": a, "Tp": 2 * pi * math.sqrt(m * a**3 / k)}


def coriolis(x):
    f = 2 * Om * math.sin(x["la"])
    return {"fc": f, "dy": f * x["dd"] ** 2 / (2 * x["vv"]), "Tf": 2 * pi / (Om * math.sin(x["la"])), "rt": Om * math.sin(x["la"])}


def bohm(x):
    mi = x["Ai"] * amu
    cs = math.sqrt(x["Te"] / mi)
    return {"mi": mi, "cs": cs, "Is": math.exp(-0.5) * e * x["np"] * x["Ap"] * cs, "dV": x["Te"] / (2 * e) * math.log(mi / (2 * pi * me))}


def invariant(x):
    p1, p2 = math.sqrt(x["E1"] ** 2 - x["m1"] ** 2), math.sqrt(x["E2"] ** 2 - x["m2"] ** 2)
    cth = math.cos(x["th"])
    m = math.sqrt(x["m1"] ** 2 + x["m2"] ** 2 + 2 * (x["E1"] * x["E2"] - p1 * p2 * cth))
    # the same quantity from the four-vector sum: components along and across the first momentum
    px, py = p1 + p2 * cth, p2 * math.sin(x["th"])
    et = x["E1"] + x["E2"]
    assert math.sqrt(et**2 - px**2 - py**2) == pytest.approx(m)
    return {"p1": p1, "p2": p2, "Mi": m, "Et": et, "pt": math.hypot(px, py), "gm": et / m}


def synchrotron(x):
    gm = x["Eb"] / (0.51099895 * 1.602176634e-13)
    u0 = e**2 * gm**4 / (3 * eps0 * x["rb"])
    return {"gm": gm, "U0": u0, "Pr": u0 * x["Ib"] / e, "fl": u0 / x["Eb"]}


CASES = {
    "chemistry.organic.sn1_sn2_competition": sn, "chemistry.organic.bronsted_catalysis": bronsted, "chemistry.organic.evans_polanyi": evans, "chemistry.thermo.maier_kelley_heat_capacity": maier,
    "chemistry.physical.stokes_einstein_diffusion": stokes, "chemistry.physical.ranz_marshall_mass_transfer": ranz, "chemistry.electro.stern_geary_corrosion_rate": stern,
    "chemistry.electro.cottrell_chronoamperometry": cottrell, "chemistry.electro.randles_sevcik_voltammetry": randles, "chemistry.photochem.photolysis_rate_constant": photolysis,
    "chemistry.quantum.wigner_tunnelling_correction": wigner, "physics.fluids.venturi_pitot_bernoulli": venturi, "physics.fluids.hagen_poiseuille_flow": poiseuille,
    "physics.astro.cepheid_period_luminosity": cepheid, "physics.astro.main_sequence_lifetime": lifetime, "physics.astro.pulsar_spindown": pulsar,
    "physics.analytical.kepler_effective_potential": kepler, "physics.analytical.coriolis_foucault": coriolis, "physics.plasma.bohm_sheath_probe_current": bohm,
    "physics.particle.invariant_mass_two_body": invariant, "physics.particle.synchrotron_radiation_loss": synchrotron,
}


def test_there_are_twenty_one_cases():
    assert len(CASES) == 21


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


def test_benchmarks_and_identities():
    assert solved("chemistry.organic.sn1_sn2_competition", Nu="1e-9 mol/L")["fr"] < 1e-3                                              # no nucleophile: pure SN1
    assert solved("chemistry.organic.bronsted_catalysis", pK2="4.76")["rt"] == pytest.approx(1)                                       # the same acid
    assert solved("chemistry.organic.evans_polanyi", dH="0 kJ/mol")["rt"] == pytest.approx(1)                                         # thermoneutral: no enhancement
    assert solved("chemistry.thermo.maier_kelley_heat_capacity", T2="298.16 K")["dH"] == pytest.approx(37.144 * 0.01, rel=1e-3)    # a 0.01 K step is Cp dT
    assert solved("chemistry.electro.randles_sevcik_voltammetry")["dE"] == pytest.approx(0.0570, abs=1e-4)                           # 57 mV at 25 °C
    assert solved("chemistry.electro.cottrell_chronoamperometry", tm="4 s")["it"] == pytest.approx(solved("chemistry.electro.cottrell_chronoamperometry")["it"] / 2)   # i falls as 1/sqrt(t)
    assert solved("chemistry.quantum.wigner_tunnelling_correction", nu="1 1/cm")["kp"] == pytest.approx(1, abs=1e-5)                  # no curvature, no tunnelling
    assert solved("physics.fluids.hagen_poiseuille_flow", Rr="2 mm")["Qv"] / solved("physics.fluids.hagen_poiseuille_flow")["Qv"] == pytest.approx(16)   # Q ~ R^4
    assert solved("physics.astro.main_sequence_lifetime", Mr="1")["tms"] / 3.15576e7 == pytest.approx(1.0e10, rel=0.06)             # about 10 Gyr for the Sun
    assert solved("physics.astro.pulsar_spindown")["Ed"] == pytest.approx(7.2e31, rel=0.02)
    assert solved("physics.analytical.kepler_effective_potential")["ec"] < 1
    assert solved("physics.analytical.coriolis_foucault", la="90 deg")["Tf"] / 3600 == pytest.approx(23.934, abs=0.01)                # one sidereal day at the pole
    assert solved("physics.particle.invariant_mass_two_body", E1="45.6 GeV", E2="45.6 GeV", th="180 deg")["Mi"] / 1.602176634e-10 == pytest.approx(91.2, abs=0.01)   # Z boson
    assert solved("physics.particle.synchrotron_radiation_loss")["U0"] / 1.602176634e-10 == pytest.approx(3.41, abs=0.02)            # LEP-2: about 3.4 GeV per turn
    assert g > 0


def test_catalogued_under_their_sub_disciplines():
    for cid in CASES:
        assert CAT.get(cid).subdisciplines and CAT.get(cid).references
