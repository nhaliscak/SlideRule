"""Equation-audit fill, aerospace A: each worked example against a different route (conservation-law solves, quadrature, eigenvalues, Fourier lifting line, collocation, hydrostatics)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

PRE = "aerospace."
G = 9.80665


def isa(x):
    Ra, T = 287.053, 216.65
    sol = integrate.solve_ivp(lambda h, p: [-p[0] / (Ra * T) * G], [11000, x["h"]], [22632.06], rtol=1e-12, atol=1e-6)       # hydrostatic dp/dh = -rho g
    p = sol.y[0, -1]
    return {"Tz": T, "pz": p, "rz": p / (Ra * T), "az": math.sqrt(1.4 * Ra * T), "dl": p / 101325, "sg": p / (Ra * T) / 1.225}


def airfoil(x):
    a0 = 2 * math.pi * x["ea"]
    n = 15
    th = np.linspace(math.pi / 2 / n, math.pi / 2, n)
    odd = np.arange(1, 2 * n, 2)
    mu0 = a0 / (math.pi * x["AR"] * x["eo"])                                             # elliptic planform with the span efficiency as an effective aspect ratio: mu = mu0 sin(theta)
    A = np.array([[math.sin(k * t) * (1 + k * mu0) for k in odd] for t in th])           # Glauert collocation, unit angle of attack
    rhs = mu0 * np.sin(th)
    a1 = np.linalg.solve(A, rhs)[0]
    a3 = math.pi * x["AR"] * x["eo"] * a1                                                          # lift slope from the first Fourier coefficient
    CL = a3 * (x["al"] - x["al0"])
    return {"a0": a0, "a3": a3, "CL": CL, "ep": CL / (math.pi * x["AR"] * x["eo"]), "CLc": CL / math.sqrt(1 - x["M"] ** 2)}


def rankine(M1, g):
    # nondimensional upstream state with a1 = 1: rho1 = g, p1 = 1, u1 = M1
    def eq(v):
        r2, u2, p2 = v
        return [g * M1 - r2 * u2, 1 + g * M1 ** 2 - p2 - r2 * u2 ** 2, g / (g - 1) * 1 / g + M1 ** 2 / 2 - g / (g - 1) * p2 / r2 - u2 ** 2 / 2]
    r2, u2, p2 = optimize.fsolve(eq, [2 * g, M1 / 2, 2 * M1 ** 2], xtol=1e-13)
    return r2 / g, u2, p2


def normal(x):
    M1, g = x["M1"], x["gam"]
    rr, u2, pr = rankine(M1, g)
    a2 = math.sqrt(g * pr / (rr * g))
    M2 = u2 / a2
    stag = lambda M, p: p * (1 + (g - 1) / 2 * M ** 2) ** (g / (g - 1))
    p0r = stag(M2, pr) / stag(M1, 1.0)
    return {"M2": M2, "pr": pr, "rr": rr, "Tr": pr / rr, "p0r": p0r, "ds": -math.log(p0r)}


def oblique(x):
    M1, be, g = x["M1"], x["be"], x["gam"]
    rr, un2, pr = rankine(M1 * math.sin(be), g)                                          # shock-normal problem at the normal Mach number
    ut = M1 * math.cos(be)                                                               # tangential velocity is unchanged
    a2 = math.sqrt(pr / rr)                                                              # a2 / a1 for a perfect gas
    un2_abs = M1 * math.sin(be) / rr * 1.0
    th = be - math.atan2(un2_abs, ut)
    V2 = math.hypot(un2_abs, ut)
    return {"th": th, "Mn1": M1 * math.sin(be), "Mn2": un2_abs / a2, "M2": V2 / a2, "pr": pr}


def pm(x):
    g = x["gam"]
    nu = lambda M: integrate.quad(lambda m: math.sqrt(m * m - 1) / (1 + (g - 1) / 2 * m * m) / m, 1, M)[0]       # dnu = sqrt(M^2 - 1)/(1 + (g - 1)/2 M^2) dM/M
    n1, n2 = nu(x["M1"]), nu(x["M2"])
    return {"n1": n1, "n2": n2, "th": n2 - n1, "mu1": math.asin(1 / x["M1"]), "mu2": math.asin(1 / x["M2"]), "pr": ((1 + (g - 1) / 2 * x["M1"] ** 2) / (1 + (g - 1) / 2 * x["M2"] ** 2)) ** (g / (g - 1))}


def nozzle(x):
    g, Me = x["gam"], x["Me"]
    T = lambda M: 1 / (1 + (g - 1) / 2 * M ** 2)                                         # T/T0
    rho, a = lambda M: T(M) ** (1 / (g - 1)), lambda M: math.sqrt(T(M))
    AR = rho(1) * a(1) / (rho(Me) * Me * a(Me))                                          # mass conservation
    pe = x["pc"] * T(Me) ** (g / (g - 1))
    # thrust from momentum: F = mdot Ve + (pe - pa) Ae; with a0^2 = g p0/rho0, mdot Ve / (p0 At) = g rho* a* Ve
    CF = g * rho(1) * a(1) * Me * a(Me) + (pe - x["pa"]) / x["pc"] * AR
    return {"AR": AR, "pe": pe, "CF": CF, "F": CF * x["pc"] * x["At"]}


def prop(x):
    k = x["eta"] / (x["cp"] * G)
    Wn = lambda m: m * G
    E = k * x["CL"] ** 1.5 / x["CD"] * math.sqrt(x["rho"] * x["S"] / 2) * integrate.quad(lambda W: W ** -1.5, Wn(x["W1"]), Wn(x["W0"]))[0]
    return {"Rg": k * x["LD"] * math.log(x["W0"] / x["W1"]), "En": E}


def climb(x):
    W = x["m"] * G
    hab = optimize.brentq(lambda h: x["RC0"] + (x["RC1"] - x["RC0"]) / x["h1"] * h, 1, 1e6)                             # the straight line through the two climb rates reaches zero
    hsv = optimize.brentq(lambda h: x["RC0"] * (1 - h / hab) - 0.508, 0, hab)           # climb rate falls linearly to 0.508 m/s
    return {"Ps": (x["T"] - x["D"]) * x["V"] / W, "ga": math.asin((x["T"] - x["D"]) / W), "hab": hab, "hsv": hsv}


def turn(x):
    W = x["m"] * G
    phi, V = x["ph"], x["V"]
    L = W / math.cos(phi)                                                                # vertical balance
    om = L * math.sin(phi) / (x["m"] * V)                                                # horizontal component gives the turn rate
    Vs = math.sqrt(2 * W / (x["rho"] * x["S"] * x["CLm"]))
    n = L / W
    return {"n": n, "wd": om, "Rt": V / om, "Vs": Vs, "Vst": Vs * math.sqrt(n), "na": 0.5 * x["rho"] * V ** 2 * x["S"] * x["CLm"] / W}


def takeoff(x):
    W = x["m"] * G
    Vs = math.sqrt(2 * W / (x["rho"] * x["S"] * x["CLm"]))
    Vlo = 1.1 * Vs
    q = 0.5 * x["rho"] * (0.7 * Vlo) ** 2
    F = x["T"] - x["mu"] * (W - q * x["S"] * x["CLg"]) - q * x["S"] * x["CDg"]
    a = F / x["m"]
    return {"Vs": Vs, "Vlo": Vlo, "aa": a, "sg": Vlo ** 2 / (2 * a), "Vtd": 1.15 * Vs, "sl": (1.15 * Vs) ** 2 / (2 * G * x["mub"])}


def disk(x):
    A = math.pi * x["D"] ** 2 / 4
    vh = optimize.brentq(lambda v: 2 * x["rho"] * A * v * v - x["T"], 1e-3, 100)         # T = 2 rho A v^2 in hover
    vi = optimize.brentq(lambda v: 2 * x["rho"] * A * (x["V"] + v) * v - x["T"], 1e-6, 100)   # forward flight: T = 2 rho A (V + v_i) v_i
    return {"A": A, "DL": x["T"] / A, "vh": vh, "Pi": x["T"] * vh, "FM": x["T"] * vh / x["Pa"], "ei": x["V"] / (x["V"] + vi), "Mt": x["Om"] * x["D"] / 2 / x["asd"]}


def jet(x):
    g, cp = x["gam"], x["cp"]
    V0 = x["M0"] * math.sqrt((g - 1) * cp * x["T0"])
    T02 = x["T0"] + V0 ** 2 / (2 * cp)                                                   # total temperature from the energy equation
    p02 = x["p0"] * (T02 / x["T0"]) ** (g / (g - 1))
    T03 = T02 * x["pic"] ** ((g - 1) / g)
    T05 = x["T04"] - (T03 - T02)
    p05 = x["pic"] * p02 * (T05 / x["T04"]) ** (g / (g - 1))
    Te = T05 * (x["p0"] / p05) ** ((g - 1) / g)                                          # static exit temperature after full expansion
    Ve = math.sqrt(2 * cp * (T05 - Te))
    fa = cp * (x["T04"] - T03) / (x["eb"] * x["QR"])
    return {"V0": V0, "T02": T02, "p02": p02, "T03": T03, "T05": T05, "p05": p05, "Ve": Ve, "Fm": Ve - V0, "fa": fa, "TS": fa / (Ve - V0)}


def stab(x):
    # moment slope from the wing and tail contributions
    Cma = x["aw"] * (x["hcg"] - x["hac"]) - x["et"] * x["VH"] * x["at"] * (1 - x["de"])
    hn = x["hcg"] - Cma / x["aw"]                                                        # the c.g. position where the moment slope vanishes
    alt = -x["Cm0"] / Cma
    return {"hn": hn, "SM": hn - x["hcg"], "Cma": Cma, "alt": alt, "CLt": x["aw"] * alt}


def dyn(x):
    q = 0.5 * x["rho"] * x["V"] ** 2
    Ma, Mq = q * x["S"] * x["cb"] * x["Cma"] / x["Iy"], q * x["S"] * x["cb"] ** 2 * x["Cmq"] / (2 * x["V"] * x["Iy"])
    lam = np.linalg.eigvals(np.array([[Mq, Ma], [1.0, 0.0]]))                           # theta'' = Mq theta' + Ma theta
    w = abs(lam[0])
    z = -lam[0].real / w
    ph = np.linalg.eigvals(np.array([[-2 * G / (x["V"] * x["LD"]), -G], [2 * G / x["V"] ** 2, 0.0]]))
    wp = abs(ph[0])
    return {"qd": q, "Ma": Ma, "Mq": Mq, "wsp": w, "zsp": z, "wp": wp, "Tp": 2 * math.pi / wp, "zp": -ph[0].real / wp}


def wing(x):
    L = x["n"] * x["m"] * G
    s = x["b"] / 2
    w0 = L / (math.pi * s / 2)                                                           # elliptic load: integral of w0 sqrt(1 - (y/s)^2) over the full span is L
    Mr = integrate.quad(lambda y: w0 * math.sqrt(1 - (y / s) ** 2) * y, 0, s)[0]
    q = x["Tq"] / (2 * x["Ab"])
    return {"Lt": L, "Vr": L / 2, "Mr": Mr, "qf": q, "ta": q / x["tw"], "tr": x["Tq"] * x["pb"] / (4 * x["Ab"] ** 2 * x["G"] * x["tw"])}


def panel(x):
    D = x["E"] * x["t"] ** 3 / (12 * (1 - x["nu"] ** 2))
    a = 12 * x["bp"]                                                                     # long plate: Navier buckling stress, minimised over the half-wave number
    s = min(math.pi ** 2 * D / (x["bp"] ** 2 * x["t"]) * (m * x["bp"] / a + a / (m * x["bp"])) ** 2 for m in range(1, 40))
    return {"scp": s, "we": 1.9 * x["t"] * math.sqrt(x["E"] / x["sa"]), "sce": math.pi ** 2 * x["E"] * (x["rg"] / (x["Kf"] * x["Le"])) ** 2}


def tunnel(x):
    Mf, Ref = x["Vf"] / x["af"], x["rf"] * x["Vf"] * x["Lf"] / x["mf"]
    Vt = Mf * x["at"]
    Rem = x["rt"] * Vt * x["Lm"] / x["mt"]
    qf, qm = 0.5 * x["rf"] * x["Vf"] ** 2 * x["Lf"] ** 2, 0.5 * x["rt"] * Vt ** 2 * x["Lm"] ** 2
    return {"Mf": Mf, "Ref": Ref, "Vt": Vt, "Rem": Rem, "rr": Rem / Ref, "fs": qf / qm}


def diverge(x):
    qD = optimize.brentq(lambda q: x["Kt"] - q * x["S"] * x["aw"] * x["ee"], 1, 1e7)     # the determinant of the static-twist equation vanishes
    VD = math.sqrt(2 * qD / x["rho"])
    return {"qD": qD, "VD": VD, "mg": VD / x["Vf"], "ap": sum((x["Vf"] / VD) ** (2 * k) for k in range(2000))}      # the geometric (Neumann) series of the twist


CASES = {
    PRE + "atmosphere.isa_lower_stratosphere": (isa, 1e-6), PRE + "aerodynamics.thin_airfoil_finite_wing_glauert": (airfoil, 1e-6), PRE + "aerodynamics.normal_shock_relations": (normal, 1e-7),
    PRE + "aerodynamics.oblique_shock_theta_beta_mach": (oblique, 1e-6), PRE + "aerodynamics.prandtl_meyer_expansion": (pm, 1e-7), PRE + "propulsion.nozzle_area_mach_thrust_coefficient": (nozzle, 1e-9),
    PRE + "aeronautical.propeller_range_endurance_breguet": (prop, 1e-7), PRE + "aeronautical.climb_excess_power_ceiling": (climb, 1e-9), PRE + "aeronautical.turn_performance_load_factor": (turn, 1e-9),
    PRE + "aeronautical.takeoff_landing_distance": (takeoff, 1e-9), PRE + "propulsion.actuator_disk_propeller_rotor": (disk, 1e-7), PRE + "propulsion.turbojet_ideal_cycle_ramjet": (jet, 1e-9),
    PRE + "aeronautical.static_stability_neutral_point": (stab, 1e-9), PRE + "aeronautical.short_period_phugoid_approximations": (dyn, 1e-7), PRE + "structures.wing_bending_torsion_shear_flow": (wing, 1e-7),
    PRE + "structures.skin_stringer_panel_buckling": (panel, 1e-9), PRE + "aerodynamics.wind_tunnel_similarity_scaling": (tunnel, 1e-9), PRE + "aeroelasticity.wing_divergence_speed": (diverge, 1e-6),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    n = solved(PRE + "aerodynamics.normal_shock_relations", M1="1.0001")
    assert n["M2"] == pytest.approx(1, abs=1e-3) and n["p0r"] == pytest.approx(1, abs=1e-9)                              # a vanishing shock
    assert solved(PRE + "aerodynamics.normal_shock_relations", M1="2")["M2"] == pytest.approx(0.5774, abs=1e-4)           # NACA 1135 table value at Mach 2
    assert solved(PRE + "aerodynamics.oblique_shock_theta_beta_mach", M1="2", be="90 deg")["M2"] == pytest.approx(0.5774, abs=1e-4)   # normal shock limit
    assert solved(PRE + "aerodynamics.prandtl_meyer_expansion", M1="1", M2="1e6")["th"] == pytest.approx(math.radians(130.45), abs=2e-3)   # turning to vacuum
    assert solved(PRE + "aerodynamics.prandtl_meyer_expansion")["n2"] == pytest.approx(math.radians(39.12), abs=2e-3)      # NACA 1135: nu(2.5) = 39.12 degrees
    assert solved(PRE + "propulsion.nozzle_area_mach_thrust_coefficient", Me="2.0", gam="1.4")["AR"] == pytest.approx(1.6875, abs=1e-4)   # A/A* at Mach 2
    j = solved(PRE + "propulsion.turbojet_ideal_cycle_ramjet", pic="1", M0="3")
    assert j["T03"] == pytest.approx(j["T02"]) and j["Fm"] > 0                                                            # ramjet: no compression, no turbine work
    assert solved(PRE + "aeronautical.propeller_range_endurance_breguet", W1="1200 kg")["Rg"] == pytest.approx(0, abs=1e-6)
    assert solved(PRE + "aeronautical.turn_performance_load_factor", ph="60 deg")["n"] == pytest.approx(2.0)               # 60 degrees of bank: 2 g
    assert solved(PRE + "aeronautical.static_stability_neutral_point", hcg="0.5")["SM"] == pytest.approx(0.01334, abs=1e-9)   # c.g. just ahead of the neutral point at 0.51334: small positive margin
    assert solved(PRE + "aerodynamics.thin_airfoil_finite_wing_glauert", AR="1e6")["a3"] == pytest.approx(2 * math.pi * 0.97, rel=1e-4)    # infinite wing: section slope
    assert solved(PRE + "atmosphere.isa_lower_stratosphere", h="11 km")["pz"] == pytest.approx(22632.06)


def test_takeoff_roll_agrees_with_integrating_the_equation_of_motion():
    c = CAT.get(PRE + "aeronautical.takeoff_landing_distance")
    r = solved(PRE + "aeronautical.takeoff_landing_distance")
    m, S, rho, T, mu, CDg, CLg = 1400, 16, 1.225, 3800, 0.04, 0.06, 0.6
    acc = lambda V: (T - mu * (m * G - 0.5 * rho * V * V * S * CLg) - 0.5 * rho * V * V * S * CDg) / m
    s = integrate.quad(lambda V: V / acc(V), 0, r["Vlo"])[0]                                                              # s = integral of V dV / a(V)
    assert r["sg"] == pytest.approx(s, rel=0.02)


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "aerospace"
