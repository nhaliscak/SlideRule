"""Equation-audit fill, biomedical A: each worked example against a different route (compartment ODEs, superposition, moment integrals, BVP, shape of the Lamé solution, mass balance)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

PRE = "biomedical."
MMHG = 133.322387415
YEAR = 31557600.0
KCAL_DAY = 4184 / 86400


def bateman(x):
    F, D, V, ka, ke, t, tau = (x[k] for k in ("F", "D", "V", "ka", "ke", "t", "tau"))
    rhs = lambda s, y: [-ka * y[0], ka * y[0] - ke * y[1]]                               # gut amount and central amount
    sol = integrate.solve_ivp(rhs, [0, 3e6], [F * D, 0], rtol=1e-11, atol=1e-14, dense_output=True)
    conc = lambda s: sol.sol(s)[1] / V
    tm = optimize.minimize_scalar(lambda s: -conc(s), bounds=(1, 3e4), method="bounded", options={"xatol": 1e-6}).x
    auc = integrate.quad(conc, 0, 3e6, limit=800)[0]
    # accumulation: superposition of many doses with a very fast absorption (ka large) gives the elimination-phase ratio
    trough = sum(F * D / V * math.exp(-ke * tau * (k + 1)) for k in range(200))          # trough after 200 doses, each decaying by exp(-ke tau) per interval
    return {"Ct": conc(t), "tm": tm, "Cm": conc(tm), "CL": ke * V, "auc": auc, "Css": F * D / (ke * V * tau), "Rac": trough / (F * D / V * math.exp(-ke * tau))}


def twocomp(x):
    D, V1, k10, k12, k21, t = (x[k] for k in ("D", "V1", "k10", "k12", "k21", "t"))
    M = np.array([[-(k10 + k12), k21], [k12, -k21]])
    ev, vec = np.linalg.eig(M)
    order = np.argsort(ev)                                                               # most negative first: alpha, then beta
    lam = ev[order].real
    c = np.linalg.solve(vec[:, order], np.array([D, 0.0]))                               # initial amounts in the eigen basis
    A, B = (vec[0, order] * c)[0].real / V1, (vec[0, order] * c)[1].real / V1
    Cf = lambda s: (A * math.exp(lam[0] * s) + B * math.exp(lam[1] * s))
    auc = integrate.quad(Cf, 0, 40 / abs(lam[1]), limit=500)[0]
    aumc = integrate.quad(lambda s: s * Cf(s), 0, 40 / abs(lam[1]), limit=500)[0]
    return {"al": -lam[0], "be": -lam[1], "A": A, "B": B, "Ct": Cf(t), "auc": auc, "Vss": D * aumc / auc ** 2, "th": math.log(2) / -lam[1]}


def mm(x):
    sol = integrate.solve_ivp(lambda s, c: [(x["Rd"] - x["Vm"] * c[0] / (x["Km"] + c[0])) / x["V"]], [0, 1e9], [0.0], rtol=1e-11, atol=1e-14, method="LSODA")   # run to steady state
    Rt = x["Vm"] * x["Ct"] / (x["Km"] + x["Ct"])
    k_app = -(-x["Vm"] / (x["V"] * (x["Km"] + x["Ct"])))                                 # d ln C / dt of the elimination at the target
    return {"Css": sol.y[0, -1], "Rt": Rt, "th": math.log(2) / k_app}


def renal(x):
    age, wt, scr = x["age"] / YEAR, x["wt"], x["scr"] / 0.01                             # years, kg, mg/dL
    female = x["fem"] > 0.5
    cg = (140 - age) * wt / (72 * scr) * (0.85 if female else 1)
    kappa, alpha = (0.7, -0.241) if female else (0.9, -0.302)
    eg = 142 * min(scr / kappa, 1) ** alpha * max(scr / kappa, 1) ** -1.2 * 0.9938 ** age * (1.012 if female else 1)
    return {"cg": cg * 1e-6 / 60, "eg": eg * 1e-6 / 60}


def body(x):
    w, h, a, male = x["wt"], x["ht"] * 100, x["age"] / YEAR, x["male"] > 0.5
    return {"bmi": w / x["ht"] ** 2, "bsm": math.sqrt(h * w / 3600), "bsd": 0.007184 * w ** 0.425 * h ** 0.725,
            "mif": (10 * w + 6.25 * h - 5 * a + (5 if male else -161)) * KCAL_DAY, "hb": ((88.362 + 13.397 * w + 4.799 * h - 5.677 * a) if male else (447.593 + 9.247 * w + 3.098 * h - 4.33 * a)) * KCAL_DAY}


def o2(x):
    Sa, Sv = x["Sa"], x["Sv"]
    g_per_L = x["Hb"]                                                                    # SI: 1 g/L = 1 kg/m^3
    sl_si = 0.03 * 1e-3 / MMHG                                                           # 0.03 mL/(L mmHg) as a pure number per pascal
    hf = 1.34 * 1e-6 / 1e-3                                                              # mL/g -> m3/kg
    Ca = hf * g_per_L * Sa + sl_si * x["Pa"]
    Cv = hf * g_per_L * Sv + sl_si * x["Pv"]
    PA = x["Fi"] * (x["Pb"] - 47 * MMHG) - x["Pc"] / x["RQ"]
    Cc = hf * g_per_L + sl_si * PA
    return {"Ca": Ca, "Cv": Cv, "Co": x["VO"] / (Ca - Cv), "PA": PA, "AaG": PA - x["Pa"], "Cc": Cc, "Qs": (Cc - Ca) / (Cc - Cv)}


def stenosis(x):
    dpe = x["rho"] * (x["v2"] ** 2 - x["v1"] ** 2) / 2
    CO = x["CO"]                                                                         # m^3/s
    flow_sys = CO / x["HR"] / x["SEP"]                                                  # SI: HR in 1/s so CO/HR is the stroke volume
    dP = x["dP"] / MMHG
    Ag = flow_sys * 1e6 / (44.3 * math.sqrt(dP))                                         # cm^3/s over cm/s = cm^2
    return {"dpe": dpe, "dps": 4 * (x["v2"] ** 2) * MMHG, "Ac": x["Ao"] * x["vo"] / x["v2"], "Ag": Ag * 1e-4, "Ah": (CO * 6e4) / math.sqrt(dP) * 1e-4}


def haemo(x):
    pp = x["Ps"] - x["Pd"]
    mapp = x["Pd"] + pp / 3
    CO = x["SV"] * x["HR"]
    Rp = mapp / CO
    Cw = x["SV"] / pp
    tau = Rp * Cw
    r = x["Da"] / 2
    dA_dP = 2 * math.pi * r ** 3 / (x["Eh"] * x["hw"])                                   # area compliance of a thin elastic tube
    return {"pp": pp, "map": mapp, "CO": CO, "Rp": Rp, "Cw": Cw, "tau": tau, "Pe": x["Ps"] * math.exp(-x["td"] / tau), "pwv": math.sqrt(math.pi * r ** 2 / (x["rho"] * dA_dP)), "Re": x["rho"] * x["U"] * x["Da"] / x["mu"]}


def starling(x):
    npf = (x["Pc"] - x["Pi"]) - x["sg"] * (x["pc"] - x["pi"])
    Pe = optimize.brentq(lambda p: (p - x["Pi"]) - x["sg"] * (x["pc"] - x["pi"]), -1e5, 1e5)         # capillary pressure where the net pressure is zero
    return {"npf": npf, "Jv": x["Kf"] * npf, "Pe": Pe}


def lung(x):
    dr = x["Pl"] - x["Pp"]
    Cs = x["Vt"] / dr
    Ra = (x["Pk"] - x["Pl"]) / x["Q"]
    tau = Ra * Cs
    sol = integrate.solve_ivp(lambda s, v: [-v[0] / tau], [0, x["te"]], [x["Vt"]], rtol=1e-12, atol=1e-15)
    return {"dr": dr, "Cs": Cs, "Ra": Ra, "tau": tau, "em": 1 - sol.y[0, -1] / x["Vt"]}


def laplace(x):
    P, r, h = x["P"], x["r"], x["h"]
    ro = r + h
    sig = lambda s: P * r ** 2 / (ro ** 2 - r ** 2) * (1 + ro ** 2 / s ** 2)             # Lame hoop stress through the wall
    mean = integrate.quad(sig, r, ro)[0] / h                                             # the mean over the thickness is exactly P r / h
    return {"Tw": P * r, "sc": mean, "ss": P * r / (2 * h), "Pa": 2 * x["gm"] / x["ra"]}


def bioheat(x):
    d = math.sqrt(x["k"] / (x["wb"] * x["rb"] * x["cb"]))
    L = 25 * d
    k, w, Q = x["k"], x["wb"] * x["rb"] * x["cb"], x["Qe"]
    from scipy.integrate import solve_bvp
    z = np.linspace(-L, L, 400)
    sol = solve_bvp(lambda s, y: np.vstack([y[1], (w * y[0] - Q) / k]), lambda a, b: np.array([a[0], b[0]]), z, np.zeros((2, z.size)), tol=1e-10)   # k T'' - w T + Q = 0, T = 0 at both ends
    R = 0.5 if x["T"] >= 316.15 else 0.25
    cem = x["t"] * R ** (316.15 - x["T"])
    return {"dT": sol.sol(0)[0], "dl": d, "Rr": R, "cem": cem, "t240": 240 * 60 / R ** (316.15 - x["T"])}


def sar(x):
    sar_ = x["sg"] * x["E"] ** 2 / x["rho"]
    return {"sar": sar_, "dTr": sar_ / x["c"], "dT": sar_ / x["c"] * x["t"], "sw": x["Pab"] / x["mb"]}


def hill(x):
    F0, vm, af = x["F0"], x["vm"], x["af"]
    a = af * F0
    b = a * vm / F0
    v = lambda F: b * (F0 - F) / (F + a)
    opt = optimize.minimize_scalar(lambda F: -F * v(F), bounds=(1e-6, F0), method="bounded", options={"xatol": 1e-10})
    assert v(0) == pytest.approx(vm) and v(F0) == pytest.approx(0, abs=1e-12)            # the curve passes through (0, vmax) and (F0, 0)
    return {"aa": a, "bb": b, "v": v(x["F"]), "Pw": x["F"] * v(x["F"]), "Fo": opt.x, "Pm": -opt.fun}


def lq(x):
    n, d, ab, al = x["n"], x["d"], x["ab"], x["al"]
    D = n * d
    bed = n * (d + d * d / ab)
    n2 = bed / (2 * (1 + 2 / ab))
    return {"D": D, "bed": bed, "bt": bed - x["Kr"] * max(x["T"] - x["Tk"], 0), "eq": 2 * n2, "sf": math.exp(-(al * D + al / ab * d * D)), "tcp": math.exp(-x["N0"] * math.exp(-(al * D + al / ab * d * D)))}


def radio(x):
    lam = math.log(2) / x["Tp"] + math.log(2) / x["Tb"]
    Ac = integrate.quad(lambda t: x["fu"] * x["A0"] * math.exp(-lam * t), 0, 60 / lam)[0]    # area under the activity curve
    return {"Te": math.log(2) / lam, "Ac": Ac, "Dm": Ac * x["S"]}


def dialysis(x):
    R = x["c1"] / x["c0"]
    th = x["t"] / 3600
    kv = -math.log(R - 0.008 * th) + (4 - 3.5 * R) * (x["UF"] * 1e3) / x["W"]            # UF in L, W in kg
    K = x["Qb"] * (x["Ci"] - x["Co"]) / x["Ci"]
    V = x["wf"] * x["W"] * 1e-3
    return {"rr": 1 - R, "kv": kv, "K": K, "Vu": V, "kv2": K * x["t"] / V}


CASES = {
    PRE + "pharmacokinetics.oral_bateman_multiple_dosing": (bateman, 1e-5), PRE + "pharmacokinetics.two_compartment_iv_bolus": (twocomp, 1e-6), PRE + "pharmacokinetics.michaelis_menten_saturable": (mm, 1e-5),
    PRE + "clinical.renal_function_cockcroft_gault_ckdepi": (renal, 1e-9), PRE + "clinical.body_size_bsa_bmi_bmr": (body, 1e-9), PRE + "physiology.oxygen_content_fick_alveolar_shunt": (o2, 1e-9),
    PRE + "cardiology.stenosis_gradient_gorlin_valve_area": (stenosis, 1e-9), PRE + "cardiology.arterial_haemodynamics_windkessel_pwv": (haemo, 1e-9), PRE + "physiology.starling_capillary_filtration": (starling, 1e-9),
    PRE + "physiology.respiratory_system_mechanics": (lung, 1e-9), PRE + "biomechanics.laplace_law_vessel_alveolus_stent": (laplace, 1e-9), PRE + "thermal.pennes_bioheat_cem43": (bioheat, 1e-5),
    PRE + "imaging.specific_absorption_rate_rf": (sar, 1e-9), PRE + "biomechanics.hill_muscle_force_velocity": (hill, 1e-6), PRE + "radiation.linear_quadratic_bed_eqd2": (lq, 1e-9),
    PRE + "radiation.radiopharmaceutical_halflife_dose": (radio, 1e-9), PRE + "clinical.dialysis_urea_kinetics_ktv": (dialysis, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    b = solved(PRE + "clinical.body_size_bsa_bmi_bmr", wt="70 kg", ht="170 cm")
    assert b["bsm"] == pytest.approx(math.sqrt(170 * 70 / 3600), rel=1e-9) and b["bsm"] == pytest.approx(1.82, abs=0.01)    # a 70 kg, 170 cm adult has about 1.8 m^2
    s = solved(PRE + "cardiology.stenosis_gradient_gorlin_valve_area", v1="0 m/s", v2="4 m/s")
    assert s["dps"] == pytest.approx(s["dpe"], rel=0.01)                                                                  # the 4 v^2 rule matches Bernoulli for ordinary blood density
    st = solved(PRE + "physiology.starling_capillary_filtration")
    assert solved(PRE + "physiology.starling_capillary_filtration", Pc=f"{st['Pe'] / MMHG} mmHg")["Jv"] == pytest.approx(0, abs=1e-18)   # no net filtration at the equilibrium pressure
    m = solved(PRE + "pharmacokinetics.michaelis_menten_saturable", Rd="100 mg/day", Km="4 mg/L", Vm="500 mg/day")
    assert m["Css"] == pytest.approx(4e-3 * 100 / 400)                                                                      # Css = Km R / (Vm - R)
    assert solved(PRE + "radiation.linear_quadratic_bed_eqd2", d="2 Gy", n="30")["eq"] == pytest.approx(60)                # 2 Gy fractions: EQD2 equals the total dose
    t = solved(PRE + "pharmacokinetics.two_compartment_iv_bolus")
    assert t["A"] + t["B"] == pytest.approx(200e-6 / 15e-3, rel=1e-9)                                                       # C(0) = dose / V1


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "biomedical"
