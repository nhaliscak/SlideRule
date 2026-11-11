"""Equation-audit fill, materials A: each worked example against a different route (numerical integration, mass balance, matrix transformation, geometry, CGS units)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

PRE = "materials."
R = 8.314462618


def truestress(x):
    et = math.log(1 + x["e"])
    st = x["S"] * (1 + x["e"])
    return {"et": et, "st": st, "sh": x["K"] * et ** x["n"], "en": x["n"], "er": st / x["E"] + 0.002 * (st / x["sy"]) ** x["m"]}


def larson(x):
    P = x["T"] * (x["CLM"] + math.log10(x["t"] / 3600))                                  # time in hours: t is in seconds in SI
    t2 = optimize.brentq(lambda lt: x["T2"] * (x["CLM"] + lt) - P, -20, 20)              # solve for log10(t2 / h) numerically
    return {"LMP": P, "t2": 10 ** t2 * 3600}


def avrami(x):
    k, n, t = x["k"], x["n"], x["t"] / 60                                                # work in minutes
    rate = lambda s: n * k * s ** (n - 1) * math.exp(-k * s ** n)                        # dX/dt integrated numerically
    X = integrate.quad(rate, 0, t)[0]
    t50 = optimize.brentq(lambda s: integrate.quad(rate, 0, s)[0] - 0.5, 1e-9, 1e4)
    return {"X": X, "t50": t50 * 60, "rt": rate(t) / 60}


def scheil(x):
    C0, k, fs, Ce = x["C0"], x["kp"], x["fs"], x["Ce"]
    Cs = lambda f: k * C0 * (1 - f) ** (k - 1)
    Cl = optimize.brentq(lambda c: integrate.quad(Cs, 0, fs)[0] + (1 - fs) * c - C0, 0, 1)     # solute balance: the solid already formed plus the liquid left
    fl_e = optimize.brentq(lambda fl: C0 * fl ** (k - 1) - Ce, 1e-12, 1)
    return {"Cs": Cs(fs), "Cl": Cl, "Cv": k * C0 / (1 - (1 - k) * fs), "fe": fl_e}


def strengthen(x):
    return {"dT": x["al"] * x["M"] * x["G"] * x["b"] * math.sqrt(x["rho"]), "dO": 0.4 * x["M"] * x["G"] * x["b"] / (math.pi * math.sqrt(1 - x["nu"]) * x["lam"]) * math.log(2 * x["rp"] / x["b"])}


def lamina(x):
    E1, E2, G12, n12, th = x["E1"], x["E2"], x["G12"], x["n12"], x["th"]
    n21 = n12 * E2 / E1
    Q = np.array([[E1, n12 * E2, 0], [n12 * E2, E2, 0], [0, 0, G12 * (1 - n12 * n21)]]) / (1 - n12 * n21)
    c, s = math.cos(th), math.sin(th)
    T = np.array([[c * c, s * s, 2 * s * c], [s * s, c * c, -2 * s * c], [-s * c, s * c, c * c - s * s]])    # stress transformation
    Rm = np.diag([1, 1, 2])                                                                               # Reuter matrix for engineering shear strain
    Qb = np.linalg.inv(T) @ Q @ Rm @ T @ np.linalg.inv(Rm)
    Sb = np.linalg.inv(Qb)
    return {"Q11": Q[0, 0], "Q12": Q[0, 1], "Q22": Q[1, 1], "Q66": G12, "B11": Qb[0, 0], "B12": Qb[0, 1], "B22": Qb[1, 1], "B16": Qb[0, 2], "B66": Qb[2, 2], "Ex": 1 / Sb[0, 0]}


def schottky(x):
    kT = 1.380649e-23 * x["T"]
    q = 1.602176634e-19
    pb = x["phm"] - x["chi"]
    J0 = x["As"] * x["T"] ** 2 * math.exp(-q * pb / kT)
    return {"pb": pb, "J0": J0, "J": J0 * math.expm1(q * x["Vb"] / (x["nid"] * kT))}


def curie(x):
    meff = x["gL"] * math.sqrt(x["J"] * (x["J"] + 1))
    C_cgs = meff ** 2 / 8                                                                # cm^3 K / mol, from the rounded textbook mu_eff = sqrt(8 C) (exact coefficient 0.12505), hence the 1e-3 tolerance
    Cc = C_cgs * 4 * math.pi * 1e-6                                                      # to SI molar units m^3 K / mol
    return {"meff": meff, "Cc": Cc, "chi": Cc / (x["T"] - x["Tc"])}


def corrosion(x):
    B = x["ba"] * x["bc"] / (2.303 * (x["ba"] + x["bc"]))
    ic = B / x["Rp"]
    atoms = ic / (x["zv"] * 96485.33212)                                                 # mol/(m^2 s) dissolving
    rate = atoms * x["M"] / x["rho"]                                                     # volume per area per time = thickness per time
    return {"PR": 100 * (x["Cr"] + 3.3 * x["Mo"] + 16 * x["N"]), "Bs": B, "ic": ic, "rate": rate}


def oxidation(x):
    kp = x["kp0"] * math.exp(-x["Q"] / (R * x["T"]))
    Vox, Vm = x["Mox"] / x["ro"], x["na"] * x["Mm"] / x["rm"]                           # molar volumes of the oxide and of the metal consumed
    return {"kp": kp, "x": math.sqrt(kp * x["t"]), "PBR": Vox / Vm}


def grain(x):
    kg = x["k0"] * math.exp(-x["Q"] / (R * x["T"]))
    n = x["ng"]
    d1 = 1e-6
    sol = integrate.solve_ivp(lambda t, d: [kg * d1 ** n / (n * d[0] ** (n - 1))], [0, x["t"]], [x["d0"]], rtol=1e-11, atol=1e-18)   # dd/dt = k/(n d^(n-1))
    d = sol.y[0, -1]
    hp = lambda dd: x["s0"] + x["ky"] / math.sqrt(dd)
    return {"kg": kg, "d": d, "sy0": hp(x["d0"]), "sy1": hp(d)}


def weibull(x):
    Pf = 1 - math.exp(-(x["V"] / x["V0"]) * (x["s"] / x["s0"]) ** x["m"])
    sa = optimize.brentq(lambda s: 1 - math.exp(-(x["V"] / x["V0"]) * (s / x["s0"]) ** x["m"]) - x["Pt"], 1e3, 1e10)
    Rs = x["sf"] * (1 - x["nu"]) / (x["E"] * x["al"])
    return {"Pf": Pf, "sa": sa, "Rs": Rs, "Rp": Rs * x["kt"]}


def hardness(x):
    kgf = 9.80665
    area_v = x["dv"] ** 2 / (2 * math.sin(math.radians(68)))                             # pyramid contact area from its geometry, m^2
    HV = (x["F"] / kgf) / (area_v * 1e6)
    h = (x["D"] - math.sqrt(x["D"] ** 2 - x["db"] ** 2)) / 2                             # depth of the spherical cap
    HB = (x["Fb"] / kgf) / (math.pi * x["D"] * h * 1e6)
    HK = 14.229 * (x["F"] / kgf) / (x["dk"] * 1e3) ** 2
    return {"HV": HV, "HB": HB, "HK": HK, "UTS": 3.45e6 * HB}


def stoney(x):
    return {"sf": x["Es"] * x["ts"] ** 2 / (6 * (1 - x["nus"]) * x["tf"] * x["Rc"]), "tint": x["N"] * x["lam"] / (2 * x["nf"])}


def sandwich(x):
    d = x["c"] + x["tf"]
    D = 2 * x["Ef"] * x["b"] * integrate.quad(lambda zz: zz ** 2, x["c"] / 2, x["c"] / 2 + x["tf"])[0]    # E z^2 b integrated over the two face sheets
    S = x["Gc"] * x["b"] * d ** 2 / x["c"]
    wb, ws = x["P"] * x["L"] ** 3 / (48 * D), x["P"] * x["L"] / (4 * S)
    zf = x["c"] / 2 + x["tf"]                                                            # outer fibre
    return {"d": d, "D": D, "S": S, "wb": wb, "ws": ws, "w": wb + ws, "sg": x["P"] * x["L"] / 4 * zf / D * x["Ef"]}


def foam(x):
    r, Es, sy, phi = x["rr"], x["Es"], x["sys"], x["phi"]
    eD = 1 - 1.4 * r
    so = 0.3 * sy * r ** 1.5
    return {"Eo": Es * r ** 2, "so": so, "Ec": Es * (phi ** 2 * r ** 2 + (1 - phi) * r), "sc": 0.3 * sy * (phi * r) ** 1.5 + (1 - phi) * r * sy, "eD": eD, "Wa": so * eD}


def charpy(x):
    E = lambda T: x["Els"] + (x["Eus"] - x["Els"]) / 2 * (1 + math.tanh((T - x["T0"]) / x["Wd"]))
    Tt = optimize.brentq(lambda T: E(T) - x["Et"], 100, 500)
    return {"E": E(x["T"]), "Tt": Tt}


CASES = {
    PRE + "mechanical.true_stress_strain_ramberg_osgood": (truestress, 1e-9), PRE + "mechanical.larson_miller_hollomon_jaffe": (larson, 1e-9), PRE + "kinetics.avrami_jmak": (avrami, 1e-7),
    PRE + "solidification.scheil_gulliver_segregation": (scheil, 1e-6), PRE + "strengthening.taylor_orowan": (strengthen, 1e-9), PRE + "composites.lamina_stiffness_transformation": (lamina, 1e-9),
    PRE + "electronic.schottky_barrier_diode": (schottky, 1e-6), PRE + "magnetic.curie_weiss_effective_moment": (curie, 1e-3), PRE + "corrosion.pren_faraday_stern_geary": (corrosion, 1e-3),
    PRE + "corrosion.oxidation_parabolic_pilling_bedworth": (oxidation, 1e-9), PRE + "microstructure.grain_growth_hall_petch": (grain, 1e-6), PRE + "ceramics.weibull_strength_thermal_shock": (weibull, 1e-6),
    PRE + "hardness.indentation_hardness_conversions": (hardness, 2e-3), PRE + "thin_films.stoney_stress_interference_thickness": (stoney, 1e-9), PRE + "composites.sandwich_panel_bending_shear": (sandwich, 1e-9),
    PRE + "cellular.gibson_ashby_foam": (foam, 1e-9), PRE + "fracture.charpy_ductile_brittle_transition": (charpy, 1e-6),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    n = 0.2
    h = 1e-6
    assert (800 * (n + h) ** n - 800 * (n - h) ** n) / (2 * h) == pytest.approx(800 * n ** n, rel=1e-6)          # Considere: d(sigma)/d(epsilon) = sigma at epsilon = n
    assert solved(PRE + "kinetics.avrami_jmak", t=f"{(math.log(2) / 0.002) ** (1 / 2.5)} min")["X"] == pytest.approx(0.5, abs=1e-9)
    assert solved(PRE + "composites.lamina_stiffness_transformation", th="0 deg")["Ex"] == pytest.approx(140e9, rel=1e-9)      # fibre direction: E1
    assert solved(PRE + "composites.lamina_stiffness_transformation", th="90 deg")["Ex"] == pytest.approx(10e9, rel=1e-9)
    assert solved(PRE + "electronic.schottky_barrier_diode", Vb="0 V")["J"] == pytest.approx(0, abs=1e-30)
    assert solved(PRE + "ceramics.weibull_strength_thermal_shock", s="400 MPa", V="1 cm^3")["Pf"] == pytest.approx(1 - math.exp(-1))       # at the characteristic strength: 63.2 %
    assert solved(PRE + "cellular.gibson_ashby_foam", phi="1")["sc"] == pytest.approx(solved(PRE + "cellular.gibson_ashby_foam")["so"])   # all solid in the edges: the open-cell law
    assert solved(PRE + "corrosion.oxidation_parabolic_pilling_bedworth", Mox="101.96 g/mol")["PBR"] == pytest.approx(1.29, abs=0.02)   # aluminium: Pilling-Bedworth ratio about 1.28
    t = solved(PRE + "fracture.charpy_ductile_brittle_transition", T="223.0128 K")["E"]
    assert t == pytest.approx(27, abs=0.05)                                                                       # the temperature for 27 J reproduces 27 J
    assert solved(PRE + "mechanical.larson_miller_hollomon_jaffe", T2="900 K")["t2"] == pytest.approx(1000 * 3600, rel=1e-9)   # same temperature: same time


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "materials"
