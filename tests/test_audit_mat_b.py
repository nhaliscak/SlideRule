"""Equation-audit fill, materials B: each worked example against a different route (beam-theory integration, ODEs, complex permittivity, matrix algebra, root finding on the defining equation)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

PRE = "materials."


def bimetal(x):
    t1, t2, E1, E2, a1, a2, dT = (x[k] for k in ("t1", "t2", "E1", "E2", "a1", "a2", "dT"))
    h = t1 + t2
    # curvature from force and moment balance of the two layers: a strip with mismatch strain, found by solving the linear equilibrium equations
    # unknowns: strain at the interface e0 and curvature k; layer 2 sits on top (z from 0 to t2), layer 1 below (z from -t1 to 0)
    def resid(u):
        e0, k = u
        eps1 = lambda z: e0 + k * z - a1 * dT
        eps2 = lambda z: e0 + k * z - a2 * dT
        N = E1 * integrate.quad(eps1, -t1, 0)[0] + E2 * integrate.quad(eps2, 0, t2)[0]
        M = E1 * integrate.quad(lambda z: eps1(z) * z, -t1, 0)[0] + E2 * integrate.quad(lambda z: eps2(z) * z, 0, t2)[0]
        return [N, M]
    e0, k = optimize.fsolve(resid, [0, 0], xtol=1e-13)
    kap = k
    return {"hh": h, "kap": abs(kap), "dl": abs(kap) * x["L"] ** 2 / 2, "sf": x["Ef"] * (x["asub"] - x["af"]) * dT / (1 - x["nuf"])}


def viscoel(x):
    tk = x["eta"] / x["E"]
    ts = x["etam"] / x["Eu"]
    # standard linear solid stress relaxation integrated as an ODE: spring E2 parallel with (spring E1 + dashpot) in series
    sol = integrate.solve_ivp(lambda t, y: [-y[0] / ts], [0, x["t"]], [x["e0"] * x["Eu"]], rtol=1e-11, atol=1e-6)         # stress in the Maxwell arm
    sr = sol.y[0, -1] + x["e0"] * x["Er"]
    lat = -x["C1"] * (x["T"] - x["Tr"]) / (x["C2"] + x["T"] - x["Tr"])
    kv = integrate.solve_ivp(lambda t, e: [(x["s0"] - x["E"] * e[0]) / x["eta"]], [0, x["t"]], [0.0], rtol=1e-11, atol=1e-12)    # Kelvin-Voigt: eta de/dt + E e = sigma
    return {"tk": tk, "ek": kv.y[0, -1], "ts": ts, "sr": sr, "lat": lat, "teq": x["t"] * 10 ** lat}


def debye(x):
    w = 2 * math.pi * x["f"]
    eps = x["ei"] + (x["es"] - x["ei"]) / (1 + 1j * w * x["tau"])                        # complex permittivity eps' - i eps''
    return {"w": w, "er": eps.real, "ex": -eps.imag, "td": -eps.imag / eps.real, "fp": 1 / (2 * math.pi * x["tau"]), "ep": (x["es"] - x["ei"]) / 2}


def friction(x):
    # steady circular heat source on a half-space (Carslaw & Jaeger): disc source of total power q over radius a, mean temperature = q/(4 a k) ... shared between the two bodies by the sum of the conductivities
    q = x["Ff"] * x["v"]
    return {"mu": x["Ff"] / x["N"], "phi": math.atan(x["Ff"] / x["N"]), "Pw": q, "dTf": q / (4 * x["a"] * (x["k1"] + x["k2"]))}


def surface(x):
    Fv = x["A"] * x["Rs"] / (6 * x["D"] ** 2)
    # Derjaguin: F = 2 pi R W with the plane-plane interaction energy W = A / (12 pi D^2)
    W = x["A"] / (12 * math.pi * x["D"] ** 2)
    assert 2 * math.pi * x["Rs"] * W == pytest.approx(Fv)
    return {"Fv": Fv, "dp": x["gl"] * (1 / x["R1"] + 1 / x["R2"]), "Fc": 4 * math.pi * x["Rs"] * x["gl"] * math.cos(x["thc"]), "cth": math.acos((x["gsv"] - x["gsl"]) / x["gl"])}


def afm(x):
    I = x["wc"] * x["tc"] ** 3 / 12
    kc = 3 * x["E"] * I / x["Lc"] ** 3                                                   # tip load deflection PL^3/(3EI)
    lam = optimize.brentq(lambda b: math.cos(b) * math.cosh(b) + 1, 1.5, 2.2)            # clamped-free beam characteristic equation
    f0 = lam ** 2 / (2 * math.pi) * math.sqrt(x["E"] * I / (x["rho"] * x["wc"] * x["tc"])) / x["Lc"] ** 2
    return {"kc": kc, "f0": f0, "zt": math.sqrt(1.380649e-23 * x["T"] / kc)}


def tsaiwu(x):
    s = np.array([x["s1"], x["s2"], x["t12"]])
    Xt, Xc, Yt, Yc, S = (x[k] for k in ("Xt", "Xc", "Yt", "Yc", "Ss"))
    F1, F2, F11, F22, F66 = 1 / Xt - 1 / Xc, 1 / Yt - 1 / Yc, 1 / (Xt * Xc), 1 / (Yt * Yc), 1 / S ** 2
    F12 = -0.5 * math.sqrt(F11 * F22)
    f = lambda r: F1 * r * s[0] + F2 * r * s[1] + F11 * (r * s[0]) ** 2 + F22 * (r * s[1]) ** 2 + F66 * (r * s[2]) ** 2 + 2 * F12 * r * r * s[0] * s[1] - 1
    R = optimize.brentq(f, 1e-6, 100)                                                    # scale the stresses until the index reaches 1
    ratios = [s[0] / Xt if s[0] > 0 else -s[0] / Xc, s[1] / Yt if s[1] > 0 else -s[1] / Yc, abs(s[2]) / S]
    return {"F1": F1, "F2": F2, "F11": F11, "F22": F22, "F66": F66, "F12": F12, "FI": f(1) + 1, "Rtw": R, "Rmx": 1 / max(ratios)}


def matth(x):
    rr = x["An"] * x["xa"] * (1 - x["xa"])
    rp = x["rph"] * x["T"] / x["T3"]
    return {"rr": rr, "rp": rp, "rt": rr + rp, "RRR": (rr + x["rph"]) / rr}


def effcond(x):
    km, kp, ph = x["km"], x["kp"], x["ph"]
    kbr = optimize.brentq(lambda k: ph * (kp - k) / (kp + 2 * k) + (1 - ph) * (km - k) / (km + 2 * k), min(km, kp), max(km, kp))   # the defining Bruggeman equation
    # Maxwell-Eucken from the dilute-sphere field solution: (k - km)/(k + 2 km) = ph (kp - km)/(kp + 2 km)
    beta = ph * (kp - km) / (kp + 2 * km)
    kme = km * (1 + 2 * beta) / (1 - beta)
    return {"kpar": ph * kp + (1 - ph) * km, "kser": 1 / (ph / kp + (1 - ph) / km), "kme": kme, "kbr": kbr, "kph": x["Cv"] * x["vs"] * x["lm"] / 3}


CASES = {
    PRE + "thermal.bimetal_curvature_coating_stress": (bimetal, 1e-6), PRE + "polymers.kelvin_voigt_sls_wlf": (viscoel, 1e-6), PRE + "dielectrics.debye_relaxation": (debye, 1e-9),
    PRE + "tribology.friction_heating_flash_temperature": (friction, 1e-9), PRE + "nano.surface_forces_hamaker_capillary_laplace": (surface, 1e-9), PRE + "nano.afm_cantilever_stiffness_resonance": (afm, 1e-4),
    PRE + "composites.tsai_wu_max_stress_failure": (tsaiwu, 1e-6), PRE + "electronic.matthiessen_nordheim_resistivity": (matth, 1e-9), PRE + "thermal.effective_conductivity_bounds_kinetic": (effcond, 1e-6),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    k = solved(PRE + "thermal.effective_conductivity_bounds_kinetic")
    assert k["kser"] < k["kbr"] < k["kme"] + 5 and k["kme"] < k["kpar"] and k["kser"] < k["kme"]                       # the rigorous bounds bracket the models
    same = solved(PRE + "thermal.effective_conductivity_bounds_kinetic", kp="0.25 W/(m*K)")
    assert same["kme"] == pytest.approx(0.25) and same["kbr"] == pytest.approx(0.25) and same["kpar"] == pytest.approx(0.25)    # identical phases: no change
    d = solved(PRE + "dielectrics.debye_relaxation", f=f"{1 / (2 * math.pi * 8e-9) / 1e6} MHz")
    assert d["ex"] == pytest.approx(d["ep"], rel=1e-9) and d["er"] == pytest.approx((80 + 5) / 2, rel=1e-9)              # at w tau = 1 the loss peaks at (es - ei)/2
    assert solved(PRE + "polymers.kelvin_voigt_sls_wlf", T="373 K")["lat"] == pytest.approx(0)                          # at the reference temperature no shift
    assert solved(PRE + "polymers.kelvin_voigt_sls_wlf", t="1e6 s")["ek"] == pytest.approx(5 / 800, rel=1e-9)            # long-time creep strain sigma / E
    assert solved(PRE + "composites.tsai_wu_max_stress_failure", s1="1500 MPa", s2="0 MPa", t12="0 MPa")["Rtw"] == pytest.approx(1, rel=1e-9)   # uniaxial tension at the strength: failure index 1
    assert solved(PRE + "thermal.bimetal_curvature_coating_stress", dT="0 K")["kap"] == pytest.approx(0, abs=1e-12)
    assert solved(PRE + "electronic.matthiessen_nordheim_resistivity", xa="0.5")["rr"] > solved(PRE + "electronic.matthiessen_nordheim_resistivity", xa="0.1")["rr"]   # Nordheim peak at 50 %


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "materials"
