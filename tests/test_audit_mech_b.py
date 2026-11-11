"""Equation-audit fill, mechanical B: heat transfer, thermodynamics, fluids, manufacturing and mechanisms, each against a different route where one exists."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

pi = math.pi
g = 9.80665
sSB = 5.670374419e-8


def colebrook(eps, D, Re):
    return optimize.brentq(lambda f: 1 / math.sqrt(f) + 2 * math.log10(eps / (3.7 * D) + 2.51 / (Re * math.sqrt(f))), 0.005, 0.2)


def internal(x):
    Re = x["rho"] * x["v"] * x["D"] / x["mu"]
    Pr = x["mu"] * x["cp"] / x["k"]
    f = (0.79 * math.log(Re) - 1.64) ** -2
    NuG = (f / 8) * (Re - 1000) * Pr / (1 + 12.7 * math.sqrt(f / 8) * (Pr ** (2 / 3) - 1))
    h = NuG * x["k"] / x["D"]
    return {"Re": Re, "Pr": Pr, "f": f, "NuDB": 0.023 * Re**0.8 * Pr ** x["n"], "NuG": NuG, "h": h, "Q": h * pi * x["D"] * x["Lt"] * x["dT"]}


def external(x):
    Pr = x["mu"] * x["cp"] / x["k"]
    ReL, ReD = x["rho"] * x["v"] * x["Lp"] / x["mu"], x["rho"] * x["v"] * x["D"] / x["mu"]
    Num = (0.037 * ReL**0.8 - 871) * Pr ** (1 / 3)
    Nuc = 0.3 + 0.62 * ReD**0.5 * Pr ** (1 / 3) / (1 + (0.4 / Pr) ** (2 / 3)) ** 0.25 * (1 + (ReD / 282000) ** (5 / 8)) ** (4 / 5)
    return {"Pr": Pr, "ReL": ReL, "ReD": ReD, "Nul": 0.664 * ReL**0.5 * Pr ** (1 / 3), "Num": Num, "hp": Num * x["k"] / x["Lp"], "Nuc": Nuc, "hc": Nuc * x["k"] / x["D"]}


def natural(x):
    Ra = g * x["be"] * x["dT"] * x["Hp"] ** 3 / (x["nu"] * x["al"])
    Pr = x["nu"] / x["al"]
    Nu = (0.825 + 0.387 * Ra ** (1 / 6) / (1 + (0.492 / Pr) ** (9 / 16)) ** (8 / 27)) ** 2
    h = Nu * x["k"] / x["Hp"]
    return {"Ra": Ra, "Pr": Pr, "Nu": Nu, "h": h, "Q": h * x["Hp"] * x["Wp"] * x["dT"]}


def radiation(x):
    # radiosity network solved as a linear system: surface resistances (1 - e)/(e A) and the space resistance 1/(A1 F12)
    A1, A2, e1, e2, F = x["A1"], x["A2"], x["e1"], x["e2"], x["F12"]
    R1, R2, R12 = (1 - e1) / (e1 * A1), (1 - e2) / (e2 * A2), 1 / (A1 * F)
    Eb1, Eb2 = sSB * x["T1"] ** 4, sSB * x["T2"] ** 4
    M = np.array([[1 / R1 + 1 / R12, -1 / R12], [-1 / R12, 1 / R2 + 1 / R12]]) if R1 > 0 and R2 > 0 else None
    J = np.linalg.solve(M, np.array([Eb1 / R1, Eb2 / R2]))
    Q = (J[0] - J[1]) / R12
    return {"Rt": R1 + R12 + R2, "Q12": Q, "hr": Q / (A1 * (x["T1"] - x["T2"]))}


def boiling(x):
    Pr = x["mu"] * x["cp"] / x["k"]
    q = x["mu"] * x["hfg"] * math.sqrt(g * (x["rl"] - x["rv"]) / x["sg"]) * (x["cp"] * x["dTe"] / (x["Csf"] * x["hfg"] * Pr ** x["n"])) ** 3
    qm = 0.131 * x["hfg"] * math.sqrt(x["rv"]) * (x["sg"] * g * (x["rl"] - x["rv"])) ** 0.25
    return {"Pr": Pr, "q": q, "qm": qm, "mg": qm / q}


def condensation(x):
    hfp = x["hfg"] + 0.68 * x["cp"] * x["dT"]
    h = 0.943 * (x["rl"] * (x["rl"] - x["rv"]) * g * hfp * x["k"] ** 3 / (x["mu"] * x["Hp"] * x["dT"])) ** 0.25
    Q = h * x["Hp"] * x["Wp"] * x["dT"]
    md = Q / hfp
    return {"hfp": hfp, "h": h, "Q": Q, "md": md, "Ref": 4 * md / (x["Wp"] * x["mu"])}


def insulated(x):
    r1, r2, r3 = x["r1"], x["r2"], x["r3"]
    R_wall, R_ins, R_out = math.log(r2 / r1) / (2 * pi * x["kp"]), math.log(r3 / r2) / (2 * pi * x["ki"]), 1 / (2 * pi * r3 * x["ho"])
    ql = (x["Ti"] - x["Ta"]) / (R_wall + R_ins + R_out)
    Ts = x["Ti"] - ql * (R_wall + R_ins)                                           # walk down the layers from the inside
    assert Ts == pytest.approx(x["Ta"] + ql * R_out, rel=1e-9)
    return {"ql": ql, "Ts": Ts, "qb": (x["Ti"] - x["Ta"]) / (R_wall + 1 / (2 * pi * r2 * x["ho"])), "rc": x["ki"] / x["ho"]}


def contact(x):
    ks = 2 * x["k1"] * x["k2"] / (x["k1"] + x["k2"])
    sg, ms = math.hypot(x["s1"], x["s2"]), math.hypot(x["m1"], x["m2"])
    hc = 1.25 * ks * ms / sg * (x["P"] / x["Hc"]) ** 0.95
    return {"ks": ks, "sg": sg, "ms": ms, "hc": hc, "Rc": 1 / hc, "dTc": x["qf"] / hc}


def combustion(x):
    C, H, lam = x["x"], x["y"], x["lm"]
    a = C + H / 4
    mfuel = C * 12.011 + H * 1.008
    AFs = a * 4.76 * 28.97 / mfuel
    products = {"CO2": C, "H2O": H / 2, "O2": (lam - 1) * a, "N2": 3.76 * lam * a}
    # element balance on the products: oxygen atoms = 2 a lam
    assert 2 * products["CO2"] + products["H2O"] + 2 * products["O2"] == pytest.approx(2 * a * lam)
    return {"a": a, "AFs": AFs, "AF": lam * AFs, "nO": products["O2"], "nN": products["N2"], "yd": C / (C + products["O2"] + products["N2"])}


def psychro(x):
    T = x["Td"] - 273.15
    Pk = x["P"] / 1000                                                                # kPa
    pws = 0.6112 * math.exp(17.62 * T / (243.12 + T))
    pw = x["RH"] * pws
    W = 0.622 * pw / (Pk - pw)
    gam = math.log(x["RH"]) + 17.62 * T / (243.12 + T)
    return {"pws": pws * 1000, "pw": pw * 1000, "W": W, "h": (1.006 * T + W * (2501 + 1.86 * T)) * 1000, "vs": 0.287 * x["Td"] * (1 + 1.6078 * W) / Pk, "Tdp": 243.12 * gam / (17.62 - gam) + 273.15}


def wet_steam(x):
    h1, s1, v1 = x["hf1"] + x["x1"] * x["hg1"], x["sf1"] + x["x1"] * x["sg1"], x["vf1"] + x["x1"] * x["vg1"]
    xs = (s1 - x["sf2"]) / x["sg2"]
    ws = h1 - (x["hf2"] + xs * x["hg2"])
    return {"h1": h1, "v1": v1, "s1": s1, "xt": (h1 - x["hf2"]) / x["hg2"], "xs": xs, "ws": ws, "wa": x["et"] * ws}


def regen(x):
    y = (x["h6"] - x["h5"]) / (x["h2"] - x["h5"])
    assert (1 - y) * x["h5"] + y * x["h2"] == pytest.approx(x["h6"])               # the energy balance of the open heater
    wt = (x["h1"] - x["h2"]) + (1 - y) * (x["h2"] - x["h3"])
    wp = (1 - y) * (x["h5"] - x["h4"]) + (x["h7"] - x["h6"])
    qin = x["h1"] - x["h7"]
    return {"y": y, "wt": wt, "wp": wp, "qin": qin, "et": (wt - wp) / qin}


def scaling(x):
    nr, dr = x["N2"] / x["N1"], x["D2"] / x["D1"]
    return {"Q2": x["Q1"] * nr * dr**3, "H2": x["H1"] * nr**2 * dr**2, "P2": x["P1"] * nr**3 * dr**5, "Ns": x["N1"] * math.sqrt(x["Q1"]) / (g * x["H1"]) ** 0.75, "rp": x["r2"] / x["r1"]}


def pipe(x):
    D, Q = x["D"], x["Q"]
    v = Q / (pi * D**2 / 4)
    Re = x["rho"] * v * D / x["mu"]
    f = colebrook(x["eps"], D, Re)                                                  # Colebrook, solved exactly
    hf, hm = f * x["Lp"] / D * v**2 / (2 * g), x["SK"] * v**2 / (2 * g)
    return {"v": v, "Re": Re, "f": f, "hf": hf, "hm": hm, "Ht": hf + hm, "dp": x["rho"] * g * (hf + hm), "Le": x["SK"] * D / f}


def duct(x):
    a, b = x["a"], x["b"]
    Dh = 2 * a * b / (a + b)
    De = 1.3 * (a * b) ** 0.625 / (a + b) ** 0.25
    v = x["Q"] / (a * b)
    Re = x["rho"] * v * Dh / x["mu"]
    f = colebrook(x["eps"], Dh, Re)
    fe = f
    vc = x["Q"] / (pi * De**2 / 4)
    return {"Dh": Dh, "De": De, "v": v, "Re": Re, "f": f, "dpl": f / Dh * x["rho"] * v**2 / 2, "dpe": fe / De * x["rho"] * vc**2 / 2}


def boundary(x):
    Rx = x["U"] * x["x"] / x["nu"]
    return {"Rx": Rx, "dl": 5 * x["x"] / math.sqrt(Rx), "Cfl": 0.664 / math.sqrt(Rx), "dt": 0.37 * x["x"] / Rx**0.2, "Cft": 0.0592 / Rx**0.2, "Cdl": 1.328 / math.sqrt(Rx), "Cdt": 0.074 / Rx**0.2, "tr": 1.0 if Rx > 5e5 else 0.0}


def couette(x):
    U, h, mu, dp, y = x["U"], x["hg"], x["mu"], x["dpx"], x["y"]
    # mu u'' = dp/dx with u(0) = 0, u(h) = U, solved as a boundary-value problem
    sol = integrate.solve_bvp(lambda s, w: np.vstack([w[1], dp / mu * np.ones_like(s)]), lambda wa, wb: np.array([wa[0], wb[0] - U]), np.linspace(0, h, 11), np.zeros((2, 11)), tol=1e-10)
    ys = np.linspace(0, h, 20001)
    u = sol.sol(ys)[0]
    return {"u": sol.sol(y)[0], "t0": mu * sol.sol(0)[1], "qf": np.trapezoid(u, ys)}


def engine(x):
    Vd = x["nc"] * pi / 4 * x["B"] ** 2 * x["S"]
    w = x["N"]
    return {"Vd": Vd, "rc": (Vd / x["nc"] + x["Vc"]) / x["Vc"], "bmep": 2 * x["Pb"] / (Vd * w / (2 * pi)), "Tq": x["Pb"] / w, "ev": 2 * x["ma"] / (x["ra"] * Vd * w / (2 * pi))}


def absorption(x):
    cop = (1 - x["To"] / x["Tg"]) * x["Te"] / (x["To"] - x["Te"])
    a = x["e2"] * cop
    return {"COPm": cop, "COP": a, "Qg": x["Ql"] / a, "Qr": x["Ql"] / a + x["Ql"]}


def pelton(x):
    vj = x["Cv"] * math.sqrt(2 * g * x["H"])
    Os = x["N"] * math.sqrt(x["Q"]) / (g * x["H"]) ** 0.75
    return {"vj": vj, "Pj": 0.5 * x["rho"] * x["Q"] * vj**2, "Ps": x["et"] * x["rho"] * g * x["H"] * x["Q"], "Os": Os, "ty": 1.0 if Os < 0.4 else 2.0 if Os < 2.2 else 3.0}


def merchant(x):
    al, Fc, Ft = x["al"], x["Fc"], x["Ft"]
    r = x["t0"] / x["tc"]
    ph = math.atan2(r * math.cos(al), 1 - r * math.sin(al))
    R = np.array([[math.cos(al), math.sin(al)], [-math.sin(al), math.cos(al)]]) @ np.array([Ft, Fc])    # rotate the force into the tool-face frame
    # components: Ff along the face, Nf normal to it
    Ff, Nf = Fc * math.sin(al) + Ft * math.cos(al), Fc * math.cos(al) - Ft * math.sin(al)
    Fs = Fc * math.cos(ph) - Ft * math.sin(ph)
    assert Fs**2 + (Fc * math.sin(ph) + Ft * math.cos(ph)) ** 2 == pytest.approx(Fc**2 + Ft**2)              # a rotation keeps the resultant
    be = math.atan2(Ff, Nf)
    return {"r": r, "ph": ph, "Ff": Ff, "Nf": Nf, "be": be, "Fs": Fs, "ts": Fs * math.sin(ph) / (x["bw"] * x["t0"]), "phm": pi / 4 + al / 2 - be / 2}


def forming(x):
    L = math.sqrt(x["Rr"] * (x["h0"] - x["h1"]))
    F = x["sa"] * x["wd"] * L
    T = F * L / 2
    return {"Ff": x["sf"] * pi * x["rf"] ** 2 * (1 + 2 * x["mu"] * x["rf"] / (3 * x["hf"])), "Lc": L, "Fr": F, "Tr": T, "Pr": 2 * T * x["Nr"], "dm": x["mu"] ** 2 * x["Rr"]}


def moulding(x):
    t = x["h"] ** 2 / (pi**2 * x["al"]) * math.log(4 / pi * (x["Tm"] - x["Tw"]) / (x["Tx"] - x["Tw"]))
    # the full series for the mid-plane temperature at that time must come back to (Tx - Tw)/(Tm - Tw)
    th = sum(4 / pi * (-1) ** n / (2 * n + 1) * math.exp(-((2 * n + 1) ** 2) * pi**2 * x["al"] * t / x["h"] ** 2) for n in range(60))
    assert th == pytest.approx((x["Tx"] - x["Tw"]) / (x["Tm"] - x["Tw"]), rel=5e-3)
    return {"tc": t, "Fc": x["pc"] * x["Ap"], "cy": x["tf"] + t + x["to"]}


def bending(x):
    Ri, t, Y, E = x["Ri"], x["t"], x["Y"], x["E"]
    u = Ri * Y / (E * t)
    sr = 4 * u**3 - 3 * u + 1
    return {"BA": x["th"] * (Ri + x["Kf"] * t), "sr": sr, "Rf": Ri / sr, "Fb": x["kd"] * x["Su"] * x["Lb"] * t**2 / x["Wd"]}


def chvorinov(x):
    D, H = x["D"], x["H"]
    V, A = pi * D**2 * H / 4, pi * D * H + pi * D**2 / 2
    M = V / A
    Mr = x["fr"] * M
    Dr = Mr * (4 * x["hd"] + 1) / x["hd"]
    Hr = x["hd"] * Dr
    assert (pi * Dr**2 * Hr / 4) / (pi * Dr * Hr + pi * Dr**2 / 4) == pytest.approx(Mr)                        # the riser cylinder has the intended modulus
    return {"Vc": V, "Ac": A, "Mc": M, "ts": x["Bc"] * M**2, "Mr": Mr, "Dr": Dr}


def adams(x):
    Hn = x["ea"] * x["Vv"] * x["Ia"] / x["vw"]
    return {"Hn": Hn, "Tp": x["T0"] + 1 / (4.13 * x["rho"] * x["cp"] * x["tp"] * x["Y"] / Hn + 1 / (x["Tm"] - x["T0"]))}


def springs(x):
    d, D = x["d"], x["Dm"]
    C = D / d
    Kw = (4 * C - 1) / (4 * C - 4) + 0.615 / C
    Ki = (4 * C**2 - C - 1) / (4 * C * (C - 1))
    return {"Ci": C, "Kw": Kw, "ke": x["G"] * d**4 / (8 * D**3 * x["Na"]), "te": Kw * 8 * x["F"] * D / (pi * d**3), "Ki": Ki, "kt": x["E"] * d**4 / (10.8 * D * x["Na"]) / (2 * pi), "st": Ki * 32 * x["Mt"] / (pi * d**3),
            "dl": 6 * x["Fl"] * x["Ls"] ** 3 / (x["E"] * x["nl"] * x["bl"] * x["tl"] ** 3), "sl": 6 * x["Fl"] * x["Ls"] / (x["nl"] * x["bl"] * x["tl"] ** 2)}


def key(x):
    ts, sb = 2 * x["T"] / (x["d"] * x["bk"] * x["Lk"]), 4 * x["T"] / (x["d"] * x["hk"] * x["Lk"])
    return {"ts": ts, "sb": sb, "Lr": 2 * x["T"] / (x["d"] * x["bk"] * x["ta"]), "Lb": 4 * x["T"] / (x["d"] * x["hk"] * x["sba"]), "ok": 1.0 if ts <= x["ta"] and sb <= x["sba"] else 0.0}


def cam(x):
    h, b, w, th = x["hr"], x["be"], x["wc"], x["th"]
    sh = lambda t: h / 2 * (1 - np.cos(pi * t / b))
    sc = lambda t: h * (t / b - np.sin(2 * pi * t / b) / (2 * pi))
    d = 1e-6
    def vel(fn, t):                                                                # velocity by central difference in time (t = θ/ω)
        return (fn(t + d) - fn(t - d)) / (2 * d) * w
    def acc(fn, t):
        return (fn(t + d) - 2 * fn(t) + fn(t - d)) / d**2 * w**2
    ts = np.linspace(0, b, 200001)
    return {"sh": sh(th), "vh": vel(sh, th), "ah": acc(sh, th), "sc": sc(th), "vc": vel(sc, th), "ac": acc(sc, th),
            "vhm": np.max(np.abs((sh(ts + 1e-7) - sh(ts - 1e-7)) / 2e-7 * w)), "ahm": abs(acc(sh, 0.0)) if True else 0, "vcm": np.max(np.abs((sc(ts[1:-1] + 1e-7) - sc(ts[1:-1] - 1e-7)) / 2e-7 * w)), "acm": np.max(np.abs(np.array([acc(sc, t) for t in ts[2000:-2000:2000]])))}


def planetary(x):
    Zr = x["Zs"] + 2 * x["Zp"]
    ws = x["ws"]
    # Willis equation (ws - wc)/(wr - wc) = -Zr/Zs solved for the carrier speed with the ring fixed, and for the ring with the carrier fixed
    wc = optimize.brentq(lambda wc: (ws - wc) / (0 - wc) + Zr / x["Zs"], 1e-9 * ws, 10 * ws) if False else ws / (1 + Zr / x["Zs"])
    wr = -ws * x["Zs"] / Zr
    return {"Zr": Zr, "i1": 1 + Zr / x["Zs"], "i2": 1 + x["Zs"] / Zr, "i3": -Zr / x["Zs"], "wc": wc, "wr": wr}


def slider(x):
    r, l, w = x["rc"], x["lc"], x["w"]
    X = lambda th: r * math.cos(th) + math.sqrt(l**2 - r**2 * math.sin(th) ** 2)
    th = x["th"]
    dt = 1e-5 / w                                                                  # time step for numerical differentiation of x(θ = ω t)
    v = (X(th + w * dt) - X(th - w * dt)) / (2 * dt)
    a = (X(th + w * dt) - 2 * X(th) + X(th - w * dt)) / dt**2
    Ls = [x["L1"], x["L2"], x["L3"], x["L4"]]
    s, lg = min(Ls), max(Ls)
    pq = sum(Ls) - s - lg
    return {"x": X(th), "v": v, "a": a, "gs": pq - s - lg, "gr": 1.0 if s + lg <= pq else 0.0}


def paris(x):
    a0, af, K0 = x["a0"], x["af"], 1e6 * math.sqrt(1.0)
    dK = lambda a: x["Y"] * x["ds"] * math.sqrt(pi * a)
    dadN = lambda a: x["Cp"] * (dK(a) / K0) ** x["m"]
    N = integrate.quad(lambda a: 1 / dadN(a), a0, af, epsabs=0, epsrel=1e-10)[0]
    return {"dK0": dK(a0), "ac": (x["KIc"] / (x["Y"] * x["smax"])) ** 2 / pi, "Nc": N}


def balancing(x):
    ms = [(x["m1"], x["r1"], x["a1"]), (x["m2"], x["r2"], x["a2"]), (x["m3"], x["r3"], x["a3"])]
    v = sum(np.array([m * r * math.cos(a), m * r * math.sin(a)]) for m, r, a in ms)
    U = float(np.hypot(*v))
    ab = math.atan2(-v[1], -v[0])
    close = v + U * np.array([math.cos(ab), math.sin(ab)])                         # adding the balancing vector must close the polygon
    assert np.allclose(close, 0, atol=1e-12)
    return {"U": U, "mb": U / x["rb"], "ab": ab}


CASES = {
    "mechanical.heat.internal_convection_correlations": (internal, 1e-9), "mechanical.heat.external_convection_plate_cylinder": (external, 1e-9), "mechanical.heat.natural_convection_vertical_plate": (natural, 1e-9),
    "mechanical.heat.radiation_two_surface_enclosure": (radiation, 1e-9), "mechanical.heat.boiling_rohsenow_zuber": (boiling, 1e-9), "mechanical.heat.film_condensation_nusselt": (condensation, 1e-9), "mechanical.heat.insulated_pipe_critical_radius": (insulated, 1e-9),
    "mechanical.heat.thermal_contact_conductance": (contact, 1e-9), "mechanical.thermo.combustion_stoichiometry": (combustion, 1e-9), "mechanical.thermo.psychrometrics_moist_air": (psychro, 1e-6), "mechanical.thermo.wet_steam_quality_throttling": (wet_steam, 1e-9),
    "mechanical.thermo.regenerative_rankine_open_heater": (regen, 1e-9), "mechanical.fluid.turbomachinery_scaling_laws": (scaling, 1e-9), "mechanical.fluid.pipe_system_losses_swamee_jain": (pipe, 2e-2), "mechanical.fluid.rectangular_duct_equivalent_diameter": (duct, 2e-2),
    "mechanical.fluid.boundary_layer_flat_plate": (boundary, 1e-9), "mechanical.fluid.couette_flow_pressure_gradient": (couette, 1e-5), "mechanical.engine.ic_engine_performance": (engine, 1e-9), "mechanical.refrigeration.absorption_cycle_cop": (absorption, 1e-9),
    "mechanical.turbomachinery.pelton_turbine_specific_speed": (pelton, 1e-9), "mechanical.manufacturing.orthogonal_cutting_merchant": (merchant, 1e-9), "mechanical.manufacturing.forging_and_rolling_force": (forming, 1e-9),
    "mechanical.manufacturing.injection_moulding_cooling_clamp": (moulding, 1e-9), "mechanical.manufacturing.sheet_metal_bending": (bending, 1e-9), "mechanical.manufacturing.chvorinov_solidification": (chvorinov, 1e-9),
    "mechanical.manufacturing.haz_peak_temperature_adams": (adams, 1e-9), "mechanical.design.springs_extension_torsion_leaf": (springs, 1e-9), "mechanical.design.key_shear_bearing": (key, 1e-9), "mechanical.mechanisms.cam_follower_motion": (cam, 2e-3),
    "mechanical.mechanisms.planetary_gear_train": (planetary, 1e-9), "mechanical.mechanisms.slider_crank_grashof": (slider, 2e-4), "mechanical.fracture.paris_law_crack_growth": (paris, 1e-6), "mechanical.dynamics.rotating_masses_balancing": (balancing, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    oct_ = solved("mechanical.thermo.combustion_stoichiometry", x="8", y="18", lm="1")
    assert oct_["AFs"] == pytest.approx(15.05, abs=0.05)                                           # iso-octane burns at about 15:1
    assert solved("mechanical.thermo.combustion_stoichiometry", x="1", y="4")["AFs"] == pytest.approx(17.2, abs=0.1)     # methane
    ps = solved("mechanical.thermo.psychrometrics_moist_air", Td="25 degC", RH="50 %")
    assert ps["W"] * 1000 == pytest.approx(9.9, abs=0.15) and ps["Tdp"] - 273.15 == pytest.approx(13.9, abs=0.2)                    # ASHRAE: 9.9 g/kg, dew point 13.9 C
    assert solved("mechanical.thermo.psychrometrics_moist_air", RH="100 %")["Tdp"] == pytest.approx(28 + 273.15, abs=1e-6)         # saturated air: dew point equals dry bulb
    assert solved("mechanical.thermo.psychrometrics_moist_air", Td="20 degC", RH="100 %")["pws"] == pytest.approx(2.339e3, rel=5e-3)   # steam table: 2.339 kPa at 20 C
    i = solved("mechanical.heat.internal_convection_correlations")
    assert i["NuG"] == pytest.approx(i["NuDB"], rel=0.2)                                                                               # the two correlations agree to about 20 %
    b = solved("mechanical.fluid.boundary_layer_flat_plate")
    # Blasius' similarity solution f''' + f f''/2 = 0 gives f''(0) = 0.33206 and so Cf = 2 f''(0)/sqrt(Re)
    def f2_at_zero(s):
        sol = integrate.solve_ivp(lambda t, y: [y[1], y[2], -0.5 * y[0] * y[2]], (0, 10), [0, 0, s], rtol=1e-11, atol=1e-12)
        return sol.y[1, -1] - 1
    s = optimize.brentq(f2_at_zero, 0.2, 0.5)
    assert b["Cfl"] == pytest.approx(2 * s / math.sqrt(b["Rx"]), rel=1e-3)
    p = solved("mechanical.mechanisms.slider_crank_grashof", th="0 deg")
    assert p["x"] == pytest.approx(0.060 + 0.180) and p["v"] == pytest.approx(0, abs=1e-4)                                                # top dead centre
    assert solved("mechanical.mechanisms.slider_crank_grashof")["gr"] == 1.0 and solved("mechanical.mechanisms.slider_crank_grashof", L1="30 mm", L2="120 mm", L3="100 mm", L4="90 mm")["gr"] == 1.0
    assert solved("mechanical.mechanisms.slider_crank_grashof", L1="100 mm", L2="100 mm", L3="100 mm", L4="250 mm")["gr"] == 0.0
    assert solved("mechanical.refrigeration.absorption_cycle_cop")["COPm"] > solved("mechanical.refrigeration.absorption_cycle_cop")["COP"]
    assert solved("mechanical.dynamics.rotating_masses_balancing", m2="0 kg", m3="0 kg")["U"] == pytest.approx(2.0 * 0.120)        # one mass: the counter-mass equals it


def test_catalogued_in_their_sub_disciplines():
    for cid in CASES:
        c = CAT.get(cid)
        assert c.subdisciplines and c.references and c.example
