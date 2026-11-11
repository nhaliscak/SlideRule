"""Equation-audit fill, biomedical B: each worked example against a different route (boundary-value and rate-equation integration, exact acoustic Doppler, statistical distributions, mass-action kinetics)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize, stats

PRE = "biomedical."
MMHG = 133.322387415


def viscosity(x):
    D, H = x["D"] * 1e6, x["H"]                                                          # micrometres, fraction
    e45 = 220 * math.exp(-1.3 * D) + 3.2 - 2.44 * math.exp(-0.06 * D ** 0.645)
    w = 1 / (1 + 1e-11 * D ** 12)
    Cc = (0.8 + math.exp(-0.075 * D)) * (-1 + w) + w
    er = 1 + (e45 - 1) * ((1 - H) ** Cc - 1) / (0.55 ** Cc - 1)
    mb = x["mp"] * er
    Rv = 8 * mb * x["L"] / (math.pi * (x["D"] / 2) ** 4)                                 # Hagen-Poiseuille
    return {"e45": e45, "Cc": Cc, "er": er, "mb": mb, "Rv": Rv, "Rn": Rv / x["Nv"], "TPR": x["MAP"] / x["CO"]}


def krogh(x):
    k = x["Dd"] * x["sa"]
    rc, Rt, Pc, M = x["rc"], x["Rt"], x["Pc"], x["M"]
    from scipy.integrate import solve_bvp
    # k (P'' + P'/r) = M with P(rc) = Pc and P'(Rt) = 0 (no flux at the outer boundary)
    r = np.linspace(rc, Rt, 400)
    sol = solve_bvp(lambda s, y: np.vstack([y[1], M / k - y[1] / s]), lambda a, b: np.array([a[0] - Pc, b[1]]), r, np.vstack([np.full_like(r, Pc), np.zeros_like(r)]), tol=1e-11)
    return {"Pr": sol.sol(x["r"])[0], "Pe": sol.sol(Rt)[0], "dP": Pc - sol.sol(Rt)[0]}


def bloodgas(x):
    pH = 6.1 + math.log10((x["HCO"]) / (0.0307 * (x["PCO"] / MMHG) * 1000 / 1000))          # concentrations in mol/m3, pressures in mmHg
    Pb = x["P50"] * 10 ** (0.48 * (x["ph0"] - pH))
    return {"pH": pH, "AG": x["Na"] - x["Cl"] - x["HCO"], "Pb": Pb, "SO": 1 / (1 + (Pb / x["PO"]) ** x["nh"])}


def ultrasound(x):
    f, c, th = x["f"], x["c"], x["th"]
    # exact Doppler shift of an echo from a reflector moving at v (angle th): fr = f (c + v cos) / (c - v cos)
    v = optimize.brentq(lambda v: f * (c + v * math.cos(th)) / (c - v * math.cos(th)) - f - x["df"], 0, 50)
    return {"At": 2 * 0.5 * (x["z"] * 100) * (f / 1e6) , "v": v, "MI": (x["pn"] / 1e6) / math.sqrt(f / 1e6), "ra": x["cy"] * c / f / 2 / 2}


def donnan(x):
    Ko, Ai, z = x["Ko"], x["Ai"], x["zA"]
    sol = optimize.fsolve(lambda u: [u[0] * u[1] - Ko ** 2, u[0] - u[1] - z * Ai], [Ko + 1, Ko - 1], xtol=1e-13)    # Ki Cli = Ko^2 and electroneutrality
    Ki, Cl = sol
    return {"Ki": Ki, "Cli": Cl, "Vm": 8.314462618 * x["T"] / 96485.33212 * math.log(Cl / Ko), "ex": Ki + Cl + Ai - 2 * Ko}


def hh(x):
    V = x["Vv"] * 1e3                                                                    # mV
    am = 0.1 * (V + 40) / (1 - math.exp(-(V + 40) / 10))
    bm = 4 * math.exp(-(V + 65) / 18)
    ah = 0.07 * math.exp(-(V + 65) / 20)
    bh = 1 / (1 + math.exp(-(V + 35) / 10))
    an = 0.01 * (V + 55) / (1 - math.exp(-(V + 55) / 10))
    bn = 0.125 * math.exp(-(V + 65) / 80)
    m, h, n = am / (am + bm), ah / (ah + bh), an / (an + bn)
    GNa, GK = 120 * m ** 3 * h, 36 * n ** 4                                              # mS/cm^2
    I = GNa * (V - 50) + GK * (V + 77) + 0.3 * (V + 54.387)                              # uA/cm^2
    return {"am": am * 1e3, "bm": bm * 1e3, "ah": ah * 1e3, "bh": bh * 1e3, "an": an * 1e3, "bn": bn * 1e3, "mi": m, "hi": h, "ni": n, "GNa": GNa * 10, "GK": GK * 10, "Ii": I * 1e-6 / 1e-4}


def sensory(x):
    arc = math.radians(1 / 60)
    va = 2 * math.atan(x["hs"] / (2 * x["ds"]))
    return {"SPL": 10 * math.log10(x["I"] / 1e-12), "so": 2 ** ((x["ph"] - 40) / 10), "va": va, "lm": math.log10(va / arc), "dec": arc / va, "acc": 1 / x["dn"]}


def higuchi(x):
    D, A, Cs, t = x["Dd"], x["A"], x["Cs"], x["t"]
    # moving-front model: Q = (A - Cs/2) h and dh/dt = D Cs / ((A - Cs/2) h), integrated numerically
    sol = integrate.solve_ivp(lambda s, h: [D * Cs / ((A - Cs / 2) * max(h[0], 1e-12))], [0, t], [1e-9], rtol=1e-12, atol=1e-15)
    Q = (A - Cs / 2) * sol.y[0, -1]
    return {"Q": Q, "fr": x["k"] * (t / 3600) ** x["n"], "t5": 3600 * (0.5 / x["k"]) ** (1 / x["n"])}


def receptor(x):
    L, Kd, Bmax = x["L"], x["Kd"], x["Bmax"]
    kon = 1.0
    koff = kon * Kd                                                                      # rate constants with the right ratio
    sol = integrate.solve_ivp(lambda s, B: [kon * L * (Bmax - B[0]) - koff * B[0]], [0, 200 / (kon * L + koff)], [0.0], rtol=1e-12, atol=1e-18)   # mass-action kinetics to equilibrium
    B = sol.y[0, -1]
    return {"oc": B / Bmax, "B": B, "BF": (Bmax - B) / Kd, "Ef": x["Emax"] * L ** x["nH"] / (x["EC50"] ** x["nH"] + L ** x["nH"]), "Ki": x["IC50"] / (1 + x["Lr"] / x["Kr"])}


def sir(x):
    be, ga = x["be"], x["ga"]
    R0 = be / ga
    I0 = 1e-9
    sol = integrate.solve_ivp(lambda t, y: [-be * y[0] * y[1], be * y[0] * y[1] - ga * y[1]], [0, 400 / ga], [1 - I0, I0], rtol=1e-11, atol=1e-16, dense_output=True)
    t = np.linspace(0, 400 / ga, 400001)
    I = sol.sol(t)[1]
    t1, t2 = 5 / be, 12 / be                                                             # an early window before the epidemic grows large
    r = (math.log(sol.sol(t2)[1]) - math.log(sol.sol(t1)[1])) / (t2 - t1)
    return {"R0": R0, "r": r, "Td": math.log(2) / r, "hit": 1 - 1 / R0, "Re": R0 * x["sf"], "pk": I.max()}


def tumour(x):
    N0, K, r, b, t = x["N0"], x["K"], x["r"], x["b"], x["t"]
    ex = integrate.solve_ivp(lambda s, N: [r * N[0]], [0, t], [N0], rtol=1e-12, atol=1e-22).y[0, -1]
    lg = integrate.solve_ivp(lambda s, N: [r * N[0] * (1 - N[0] / K)], [0, t], [N0], rtol=1e-12, atol=1e-22).y[0, -1]
    gp = integrate.solve_ivp(lambda s, N: [b * N[0] * math.log(K / N[0])], [0, t], [N0], rtol=1e-12, atol=1e-22).y[0, -1]
    inf_l = optimize.minimize_scalar(lambda N: -r * N * (1 - N / K), bounds=(K * 1e-6, K), method="bounded", options={"xatol": K * 1e-12}).x       # size of fastest growth
    inf_g = optimize.minimize_scalar(lambda N: -b * N * math.log(K / N), bounds=(K * 1e-6, K * (1 - 1e-9)), method="bounded", options={"xatol": K * 1e-12}).x
    return {"Ne": ex, "Nl": lg, "Ng": gp, "Td": math.log(2) / r, "Ni": inf_l, "Nj": inf_g}


def qt(x):
    RR, QT = x["RR"], x["QT"]
    hr = 1 / RR
    return {"hr": hr, "qb": QT / math.sqrt(RR), "qf": QT / RR ** (1 / 3), "qg": QT + 0.154 * (1 - RR), "qh": QT + 1.75e-3 * (hr * 60 - 60)}


def bone(x):
    sc = 68 * (x["er"]) ** 0.06 * (x["rho"] / 1000) ** 2 * 1e6                           # rho in g/cm3 from kg/m3
    Eb = 3790 * x["er"] ** 0.06 * (x["rho"] / 1000) ** 3 * 1e6
    return {"sc": sc, "Eb": Eb, "phi": x["Fa"] / (sc * x["Ab"]), "Fp": math.pi * x["d"] * x["Le"] * x["ts"] * x["kf"]}


def roc(x):
    m0, m1, sd, cu = x["m0"], x["m1"], x["sd"], x["cu"]
    fpr = lambda c: 1 - stats.norm.cdf(c, m0, sd)
    tpr = lambda c: 1 - stats.norm.cdf(c, m1, sd)
    cs = np.linspace(m0 - 8 * sd, m1 + 8 * sd, 200001)
    auc = -np.trapezoid(tpr(cs), fpr(cs))                                                # integrate the ROC curve numerically
    best = optimize.minimize_scalar(lambda c: -(tpr(c) - fpr(c)), bounds=(m0 - 3, m1 + 3), method="bounded", options={"xatol": 1e-10}).x
    return {"dp": (m1 - m0) / sd, "auc": auc, "se": tpr(cu), "sp": 1 - fpr(cu), "yj": tpr(cu) - fpr(cu), "co": best}


CASES = {
    PRE + "biomechanics.blood_viscosity_fahraeus_resistance": (viscosity, 1e-9), PRE + "tissue_engineering.krogh_cylinder_oxygen": (krogh, 1e-6), PRE + "physiology.blood_gas_acid_base_bohr": (bloodgas, 1e-6),
    PRE + "imaging.ultrasound_doppler_mechanical_index": (ultrasound, 1e-3), PRE + "neural.donnan_equilibrium_potential": (donnan, 1e-9), PRE + "neural.hodgkin_huxley_gating_steady_state": (hh, 1e-9),
    PRE + "sensory.loudness_hearing_visual_acuity": (sensory, 1e-9), PRE + "pharmaceutics.higuchi_korsmeyer_peppas_release": (higuchi, 1e-6), PRE + "pharmacology.receptor_binding_emax_scatchard": (receptor, 1e-6),
    PRE + "epidemiology.sir_r0_herd_immunity_peak": (sir, 1e-4), PRE + "oncology.tumour_growth_logistic_gompertz": (tumour, 1e-6), PRE + "cardiology.qt_correction_formulas": (qt, 1e-9),
    PRE + "orthopaedics.bone_strength_density_screw_pullout": (bone, 1e-9), PRE + "statistics.roc_auc_binormal_cutoff": (roc, 1e-6),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    v = lambda D, H="45 %": solved(PRE + "biomechanics.blood_viscosity_fahraeus_resistance", D=f"{D} um", H=H)
    assert v(100)["er"] == pytest.approx(v(100)["e45"], rel=1e-9)                                                          # at 45 % haematocrit the relative viscosity is the 45 % value
    assert 1.0 < v(7)["e45"] < v(100)["e45"] and 1.0 < v(7)["e45"] < 1.4                                                    # Fahraeus-Lindqvist: lower apparent viscosity in tubes of about 7 micrometres
    assert v(100, "5 %")["er"] < v(100, "60 %")["er"]
    g = solved(PRE + "physiology.blood_gas_acid_base_bohr", PO="26.8 mmHg", P50="26.8 mmHg")
    assert g["SO"] == pytest.approx(0.5, abs=0.01)                                                                          # at P50 (pH close to 7.4) the saturation is half
    h = solved(PRE + "neural.hodgkin_huxley_gating_steady_state", Vv="-65 mV")
    assert h["mi"] == pytest.approx(0.0529, abs=2e-3) and h["hi"] == pytest.approx(0.5961, abs=2e-3) and h["ni"] == pytest.approx(0.3177, abs=2e-3)   # the resting gating values of the model
    s = solved(PRE + "sensory.loudness_hearing_visual_acuity")
    assert s["lm"] == pytest.approx(0, abs=2e-3) and s["dec"] == pytest.approx(1, abs=2e-3)                                  # 1 arcmin detail: 20/20
    q = solved(PRE + "cardiology.qt_correction_formulas", RR="1 s")
    assert q["qb"] == pytest.approx(q["qf"]) == pytest.approx(0.38) and q["qh"] == pytest.approx(0.38)                      # at 60 beats/min every correction leaves the QT unchanged
    assert solved(PRE + "statistics.roc_auc_binormal_cutoff", m1="0")["auc"] == pytest.approx(0.5)                          # no separation: chance
    assert solved(PRE + "epidemiology.sir_r0_herd_immunity_peak", be="0.4 1/day", ga="0.2 1/day")["hit"] == pytest.approx(0.5)  # R0 = 2: half the population


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "biomedical"
