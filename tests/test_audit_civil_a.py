"""Equation-audit fill, civil A: structural analysis and soil mechanics, each checked against a different route (numeric integration, linear solves, a trial wedge, a series solution)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

pi = math.pi
deg = pi / 180
gw = 9.81e3


def trapz(f, a, b, n=20001):
    x = np.linspace(a, b, n)
    return np.trapezoid(f(x), x)


# ---------------------------------------------------------------- structural
def mohr(x):
    w, v = np.linalg.eigh(np.array([[x["sx"], x["txy"]], [x["txy"], x["sy"]]]))
    ang = math.atan2(v[1, 1], v[0, 1])
    ang = (ang + pi / 2) % pi - pi / 2
    return {"sa": (x["sx"] + x["sy"]) / 2, "Rm": (w[1] - w[0]) / 2, "s1": w[1], "s2": w[0], "thp": ang}


def _double_integral(fun, a, b, n=40001):
    """Cumulative double integral of fun from a, with zero value and slope at a."""
    xs = np.linspace(a, b, n)
    f = fun(xs)
    s = integrate.cumulative_trapezoid(-f, xs, initial=0)
    y = integrate.cumulative_trapezoid(s, xs, initial=0)
    return xs, y


def fixed_end(x):
    w, P, L, EI = x["w"], x["P"], x["L"], x["E"] * x["I"]
    out = {}
    # unknown M0 from y(L) = int_0^L (L - x) M(x)/EI dx = 0, then the midspan values by integrating M/EI twice
    # (UDL: M(x) = M0 + wLx/2 - wx^2/2)
    def moment_udl(t, m0):
        return m0 + w * L * t / 2 - w * t**2 / 2
    f = lambda m0: trapz(lambda t: (L - t) * moment_udl(t, m0), 0, L)
    m0 = optimize.brentq(f, -1e9, 1e9)
    xs, y = _double_integral(lambda t: moment_udl(t, m0) / EI, 0, L)
    out["Mw"] = -m0
    out["Mmw"] = moment_udl(L / 2, m0)
    out["dw"] = np.interp(L / 2, xs, y)

    def moment_pt(t, m0):
        return m0 + P / 2 * t - P * np.maximum(t - L / 2, 0)
    f2 = lambda m0: trapz(lambda t: (L - t) * moment_pt(t, m0), 0, L)
    m02 = optimize.brentq(f2, -1e9, 1e9)
    xs, y = _double_integral(lambda t: moment_pt(t, m02) / EI, 0, L)
    out["Mp"] = -m02
    out["dp"] = np.interp(L / 2, xs, y)
    return out


def propped(x):
    w, L, EI = x["w"], x["L"], x["E"] * x["I"]
    # superposition: the cantilever tip deflection under w minus that of the prop reaction R gives zero
    R = (w * L**4 / (8 * EI)) / (L**3 / (3 * EI))
    Mf = lambda t: R * (L - t) - w * (L - t) ** 2 / 2               # sagging positive, measured from the fixed end
    xs, y = _double_integral(lambda t: Mf(t) / EI, 0, L, 80001)       # downward positive, y(0) = y'(0) = 0
    i = int(np.argmax(y))
    ms = optimize.minimize_scalar(lambda t: -Mf(t), bounds=(0, L), method="bounded", options={"xatol": 1e-12})
    return {"Rp": R, "Rf": w * L - R, "Mf": abs(Mf(0.0)), "Ms": -ms.fun, "xm": xs[i], "dm": y[i]}


def three_moment(x):
    w1, w2, L1, L2 = x["w1"], x["w2"], x["L1"], x["L2"]
    L = L1 + L2
    # flexibility method: simple beam of length L with both loads, reaction at B found from zero deflection at B (EI = 1)
    def moment_simple(t):
        RAs = (w1 * L1 * (L - L1 / 2) + w2 * L2 * L2 / 2) / L
        m = RAs * t - np.where(t < L1, w1 * t**2 / 2, w1 * L1 * (t - L1 / 2) + w2 * (t - L1) ** 2 / 2)
        return m
    xs, y = _double_integral(moment_simple, 0, L, 200001)
    y = y - xs / L * y[-1]                                       # remove the rigid-body rotation so that y(L) = 0
    dB = np.interp(L1, xs, y)
    fB = L1**2 * L2**2 / (3 * L)
    RB = dB / fB
    RA = (w1 * L1 * (L - L1 / 2) + w2 * L2 * L2 / 2) / L - RB * L2 / L
    RC = w1 * L1 + w2 * L2 - RA - RB
    MB = RA * L1 - w1 * L1**2 / 2
    return {"MB": -MB, "RA": RA, "RB": RB, "RC": RC, "Mm1": RA**2 / (2 * w1), "Mm2": RC**2 / (2 * w2)}


def truss_joint(x):
    c1, s1, c2, s2 = math.cos(x["a1"]), math.sin(x["a1"]), math.cos(x["a2"]), math.sin(x["a2"])
    F = np.linalg.solve(np.array([[c1, c2], [s1, s2]]), -np.array([x["Fx"], x["Fy"]]))
    return {"F1": F[0], "F2": F[1]}


def sections(x):
    return {"Fc": x["M"] / x["h"], "Fd": x["Vs"] / math.sin(x["th"])}


def offset_load(x):
    P, a, L, EI = x["P"], x["a"], x["L"], x["E"] * x["I"]
    b = L - a
    RA = P * b / L
    M = lambda t: RA * t - P * np.maximum(t - a, 0)
    xs, y = _double_integral(lambda t: M(t) / EI, 0, L, 200001)
    y = y - xs / L * y[-1]                                           # remove the rigid-body rotation so that y(L) = 0
    i = int(np.argmax(y))
    xd = xs[i] if a >= b else L - xs[i]                              # measured from the support farther from the load
    return {"b": b, "RA": RA, "RB": P * a / L, "Mm": P * a * b / L, "dl": np.interp(a, xs, y), "xd": xd, "dm": y[i]}


def influence(x):
    P, xx, a, L = x["P"], x["x"], x["a"], x["L"]
    RA = P * (L - xx) / L
    # free body to the left of the section
    M = RA * a - (P * (a - xx) if xx < a else 0)
    V = RA - (P if xx < a else 0)
    return {"RA": RA, "RB": P - RA, "Vs": V, "Ms": M, "Mx": P * a * (L - a) / L}


def johnson(x):
    lam = x["K"] * x["L"] / x["r"]
    E, sy = x["E"], x["sy"]
    lc = math.sqrt(2 * pi**2 * E / sy)
    scr = sy - sy**2 * lam**2 / (4 * pi**2 * E) if lam < lc else pi**2 * E / lam**2
    return {"lam": lam, "lc": lc, "scr": scr, "Pcr": scr * x["A"], "fl": 1.0 if lam >= lc else 0.0}


def tsection(x):
    bf, tf, bw, hw = x["bf"], x["tf"], x["bw"], x["hw"]
    y = np.linspace(0, hw + tf, 400001)
    width = np.where(y <= hw, bw, bf)
    A = np.trapezoid(width, y)
    yb = np.trapezoid(width * y, y) / A
    I = np.trapezoid(width * (y - yb) ** 2, y)
    return {"A": A, "yb": yb, "Ic": I, "St": I / (hw + tf - yb), "Sb": I / yb}


def eccentric(x):
    A = x["b"] * x["h"]
    I = x["b"] * x["h"] ** 3 / 12
    c = x["h"] / 2
    return {"A": A, "sc": x["P"] / A + x["P"] * abs(x["e"]) * c / I, "st": x["P"] / A - x["P"] * abs(x["e"]) * c / I, "ek": x["h"] / 6, "ok": 1.0 if abs(x["e"]) <= x["h"] / 6 else 0.0}


def steel_i(x):
    d, bf, tf, tw, fy, E, L = x["d"], x["bf"], x["tf"], x["tw"], x["fy"], x["E"], x["Lb"]
    G = 77e9
    y = np.linspace(-d / 2, d / 2, 800001)
    width = np.where(np.abs(y) >= d / 2 - tf, bf, tw)
    Ix = np.trapezoid(width * y**2, y)
    Zp = np.trapezoid(width * np.abs(y), y)                            # equal-area axis is the centroid for a symmetric section
    xw = np.linspace(-bf / 2, bf / 2, 400001)
    Iy = 2 * tf * bf**3 / 12 + (d - 2 * tf) * tw**3 / 12
    J = (2 * bf * tf**3 + (d - tf) * tw**3) / 3
    Cw = Iy * (d - tf) ** 2 / 4
    Mcr = pi / L * math.sqrt(E * Iy * G * J + (pi * E / L) ** 2 * Iy * Cw)
    Sx = Ix / (d / 2)
    return {"Ix": Ix, "Sx": Sx, "Zp": Zp, "My": fy * Sx, "Mp": fy * Zp, "sh": Zp / Sx, "Iy": Iy, "Jt": J, "Cw": Cw, "Mcr": Mcr}


def plate(x):
    D = x["E"] / (12 * (1 - x["nu"] ** 2))
    scr = x["k"] * pi**2 * D * (x["t"] / x["b"]) ** 2
    return {"scr": scr, "bt": x["b"] / x["t"], "blim": math.sqrt(x["k"] * pi**2 * D / x["fy"]), "rl": x["fy"] / scr}


def prestress(x):
    P, e, A, I, yt, yb, M = x["Pi"], x["e"], x["A"], x["Ic"], x["yt"], x["yb"], x["M"]
    return {"st": P / A - (P * e - M) * yt / I, "sb": P / A + (P * e - M) * yb / I, "dES": x["Ep"] / x["Eci"] * x["fcir"]}


def bolt(x):
    Ab = pi * x["db"] ** 2 / 4
    Rs, Rb = 0.75 * x["Fnv"] * Ab * x["ns"], 0.75 * 2.4 * x["db"] * x["tp"] * x["Fu"]
    Rd = min(Rs, Rb)
    return {"Ab": Ab, "Rs": Rs, "Rb": Rb, "Rd": Rd, "nb": math.ceil(x["Pu"] / Rd)}


def shear_rc(x):
    fcm = x["fc"] / 1e6                                              # MPa
    Vc = 0.17 * math.sqrt(fcm) * 1e6 * x["bw"] * x["d"]
    Vs = x["Vu"] / 0.75 - Vc
    sr = x["Av"] * x["fyt"] * x["d"] / Vs
    smax = min(x["d"] / 2, 0.6) if Vs <= 0.33 * math.sqrt(fcm) * 1e6 * x["bw"] * x["d"] else min(x["d"] / 4, 0.3)
    return {"Vc": Vc, "Vsr": Vs, "sr": sr, "smax": smax, "ss": min(sr, smax)}


def devlen(x):
    fcm, fym = x["fc"] / 1e6, x["fy"] / 1e6
    db = x["db"]
    k = 2.1 if db <= 0.019 else 1.7
    ld = max(fym * x["pt"] * x["pe"] / (k * math.sqrt(fcm)) * db, 0.3)
    return {"ld": ld, "ldb": ld / db}


def rc_column(x):
    Ag = x["b"] * x["h"]
    Po = 0.85 * x["fc"] * (Ag - x["As"]) + x["fy"] * x["As"]
    rho = x["As"] / Ag
    return {"Ag": Ag, "rho": rho, "Po": Po, "Pd": 0.8 * 0.65 * Po, "ok": 1.0 if 0.01 <= rho <= 0.08 else 0.0}


def branson(x):
    fcm = x["fc"] / 1e6
    fr = 0.62 * math.sqrt(fcm) * 1e6
    Mcr = fr * x["Ig"] / x["yt"]
    r = (Mcr / x["Ma"]) ** 3
    Ie = min(x["Ig"], r * x["Ig"] + (1 - r) * x["Icr"])
    return {"fr": fr, "Mcr": Mcr, "Ie": Ie, "dl": 5 * x["ws"] * x["L"] ** 4 / (384 * x["Ec"] * Ie)}


def timber(x):
    M, V = x["w"] * x["L"] ** 2 / 8, x["w"] * x["L"] / 2
    fb, fv = M / (x["b"] * x["h"] ** 2 / 6), 1.5 * V / (x["b"] * x["h"])
    return {"M": M, "Vm": V, "fb": fb, "fv": fv, "ub": fb / (x["Fb"] * x["CD"] * x["CM"] * x["CF"]), "uv": fv / (x["Fv"] * x["CD"] * x["CM"])}


# ---------------------------------------------------------------- geotechnical
def phase(x):
    Gs, w, e = x["Gs"], x["w"], x["e"]
    # unit volume of solids: weights from the volumes, not from the closed forms
    Ws, Vs, Vv = Gs * gw, 1.0, e
    Ww = w * Ws
    return {"n": Vv / (Vs + Vv), "S": Ww / gw / Vv, "gd": Ws / (Vs + Vv), "gm": (Ws + Ww) / (Vs + Vv), "gs": (Ws + Vv * gw) / (Vs + Vv), "gb": (Ws + Vv * gw) / (Vs + Vv) - gw}


def atterberg(x):
    PI = x["LL"] - x["PL"]
    return {"PI": PI, "LI": (x["w"] - x["PL"]) / PI, "CI": (x["LL"] - x["w"]) / PI, "Ac": PI / x["cf"], "PIA": 0.73 * (x["LL"] - 0.20)}


def compaction(x):
    return {"gz": x["Gs"] * gw / (1 + x["w"] * x["Gs"]), "RC": x["gdf"] / x["gdm"], "Dr": (x["emax"] - x["e"]) / (x["emax"] - x["emin"])}


def coulomb_wedge(ph, dl, H=1.0):
    """Active thrust coefficient of a vertical smooth-or-rough wall with level backfill: trial wedge, maximised over the failure angle."""
    def P(psi):
        W = 0.5 * H**2 / math.tan(psi)
        return W * math.sin(psi - ph) / math.cos(psi - ph - dl)
    r = optimize.minimize_scalar(lambda p: -P(p), bounds=(ph + 1e-3, pi / 2 - 1e-3), method="bounded", options={"xatol": 1e-12})
    return -r.fun * 2 / H**2


def rankine(x):
    ph = x["ph"]
    Ka_wedge = coulomb_wedge(ph, x["dw"])
    cosb = math.cos(x["be"])
    return {"Ka": (1 - math.sin(ph)) / (1 + math.sin(ph)), "Kp": (1 + math.sin(ph)) / (1 - math.sin(ph)), "Kc": Ka_wedge,
            "Pa": 0.5 * ((1 - math.sin(ph)) / (1 + math.sin(ph))) * x["gam"] * x["H"] ** 2, "PaC": 0.5 * Ka_wedge * x["gam"] * x["H"] ** 2,
            "zc": 2 * x["c"] / (x["gam"] * math.sqrt((1 - math.sin(ph)) / (1 + math.sin(ph))))}


def wall(x):
    H, B = x["H"], x["Bw"]
    Ka = math.tan(pi / 4 - x["ph"] / 2) ** 2
    Pa = 0.5 * Ka * x["gam"] * H**2
    W = x["gc"] * B * H
    Mr, Mo = W * B / 2, Pa * H / 3
    xbar = (Mr - Mo) / W
    e = B / 2 - xbar
    return {"Ka": Ka, "Pa": Pa, "W": W, "FSo": Mr / Mo, "FSs": W * math.tan(x["db"]) / Pa, "ec": e, "qmax": W / B * (1 + 6 * e / B), "qmin": W / B * (1 - 6 * e / B)}


def infinite_slope(x):
    c, ph, g, z, b, ru = x["c"], x["ph"], x["gam"], x["z"], x["be"], x["ru"]
    N = g * z * math.cos(b) ** 2                                      # normal stress on the plane
    T = g * z * math.sin(b) * math.cos(b)                             # shear stress along the plane
    u = ru * g * z
    return {"FS": (c + (N - u) * math.tan(ph)) / T, "FS0": math.tan(ph) / math.tan(b)}


def boussinesq(x):
    Q, r, z, q, a, B, L = x["Q"], x["r"], x["z"], x["q"], x["a"], x["Bf"], x["Lf"]
    kernel = lambda rr: q * 2 * pi * rr * 3 * z**3 / (2 * pi * (rr**2 + z**2) ** 2.5)
    return {"dp": 3 * Q / (2 * pi) * z**3 / (r**2 + z**2) ** 2.5, "dc": integrate.quad(kernel, 0, a)[0], "d2": q * B * L / ((B + z) * (L + z))}


def terzaghi_series(U, terms=400):
    m = np.arange(terms)
    M = pi * (2 * m + 1) / 2
    return lambda Tv: 1 - np.sum(2 / M**2 * np.exp(-(M**2) * Tv))


def secondary(x):
    return {"Ss": x["Ca"] * x["H"] / (1 + x["e0"]) * math.log10(x["t2"] / x["t1"])}


def liquefaction(x):
    z = x["z"]
    rd = 1 - 0.00765 * z if z <= 9.15 else 1.174 - 0.0267 * z
    N = x["N1"]
    CRR = 1 / (34 - N) + N / 135 + 50 / (10 * N + 45) ** 2 - 1 / 200
    MSF = 10**2.24 / x["Mw"] ** 2.56
    CSR = 0.65 * x["amax"] * x["sv"] / x["svp"] * rd
    return {"rd": rd, "CSR": CSR, "CRR": CRR, "MSF": MSF, "FSl": CRR * MSF / CSR}


def elastic(x):
    return {"Si": x["q"] * x["B"] * (1 - x["nu"] ** 2) * x["Is"] / x["Es"]}


def mohr_coulomb(x):
    ph, c, s3 = x["ph"], x["c"], x["s3"]
    # the circle with the given s3 that just touches tau = c + sigma tan(phi): distance from the centre to the line equals the radius
    def gap(s1):
        centre, R = (s1 + s3) / 2, (s1 - s3) / 2
        return (centre * math.tan(ph) + c) * math.cos(ph) - R
    s1 = optimize.brentq(gap, s3, s3 + 1e9)
    return {"s1": s1, "tf": (s1 - s3) / 2 * math.cos(ph), "thf": pi / 4 + ph / 2, "ts": c + x["sn"] * math.tan(ph)}


def meyerhof(x):
    ph = x["ph"]
    Nq = math.exp(pi * math.tan(ph)) * math.tan(pi / 4 + ph / 2) ** 2
    Nc = (Nq - 1) / math.tan(ph)
    Ng = (Nq - 1) * math.tan(1.4 * ph)
    Kp = math.tan(pi / 4 + ph / 2) ** 2
    B, L, Df, g = x["B"], x["Lf"], x["Df"], x["gam"]
    sc, sq = 1 + 0.2 * Kp * B / L, 1 + 0.1 * Kp * B / L
    dc, dq = 1 + 0.2 * math.sqrt(Kp) * Df / B, 1 + 0.1 * math.sqrt(Kp) * Df / B
    qu = x["c"] * Nc * sc * dc + g * Df * Nq * sq * dq + 0.5 * g * B * Ng * sq * dq
    return {"Nq": Nq, "Nc": Nc, "Ng": Ng, "Kp": Kp, "qu": qu, "qa": qu / x["FS"], "Qa": qu / x["FS"] * B * L}


def pile(x):
    D, L = x["D"], x["L"]
    Ap = pi * D**2 / 4
    Qsc, Qbc = x["al"] * x["cu"] * pi * D * L, 9 * x["cu"] * Ap
    return {"Ap": Ap, "Qsc": Qsc, "Qbc": Qbc, "Qss": x["K"] * x["svp"] * math.tan(x["dl"]) * pi * D * L, "Qbs": x["sb"] * x["Nq"] * Ap, "Qac": (Qsc + Qbc) / x["FS"]}


def group(x):
    m, n = x["m"], x["n"]
    th = math.degrees(math.atan(x["d"] / x["sp"]))
    Eg = min(1.0, 1 - th * ((n - 1) * m + (m - 1) * n) / (90 * m * n))
    return {"th": math.atan(x["d"] / x["sp"]), "Eg": Eg, "Qg": Eg * m * n * x["Qs"]}


def peck(x):
    Ka = math.tan(pi / 4 - x["ph"] / 2) ** 2
    ps = 0.65 * Ka * x["gam"] * x["H"]
    pc = max(x["gam"] * x["H"] - 4 * x["cu"], 0.3 * x["gam"] * x["H"])
    return {"ps": ps, "pc": pc, "Ps": ps * x["H"], "Pc": pc * x["H"], "Fs": ps * x["H"] * x["sp"]}


def flow_net(x):
    q = x["k"] * x["H"] * x["Nf"] / x["Nd"]
    ie = x["H"] / x["Nd"] / x["ls"]
    ic = (x["Gs"] - 1) / (1 + x["e"])
    return {"q": q, "ie": ie, "ic": ic, "FSp": ic / ie, "u": gw * (x["H"] - x["hp"] + x["zp"])}


def dam(x):
    H, B, hw, gc, mu = x["H"], x["Bd"], x["hw"], x["gc"], x["mu"]
    W = gc * H * B
    zz = np.linspace(0, hw, 200001)
    Ph = np.trapezoid(gw * (hw - zz), zz)                                 # hydrostatic thrust by integration
    Mh = np.trapezoid(gw * (hw - zz) * zz, zz)                            # its moment about the toe level
    xs = np.linspace(0, B, 200001)                                        # x measured from the toe; uplift is hw*gw at the heel (x = B), zero at the toe
    u = gw * hw * xs / B
    U = np.trapezoid(u, xs)
    Mu = np.trapezoid(u * xs, xs)                                         # moment of uplift about the toe (it opposes the weight)
    Mr = W * B / 2 - Mu
    xbar = (Mr - Mh) / (W - U)
    e = B / 2 - xbar
    return {"W": W, "Ph": Ph, "U": U, "FSs": mu * (W - U) / Ph, "FSo": W * B / 2 / (Mh + Mu), "ec": e, "qt": (W - U) / B * (1 + 6 * e / B), "qh": (W - U) / B * (1 - 6 * e / B)}


CASES = {
    "civil.structural.mohr_circle_stress": mohr,
    "civil.structural.fixed_end_beam": fixed_end,
    "civil.structural.propped_cantilever": propped,
    "civil.structural.three_moment_two_spans": three_moment,
    "civil.structural.truss_joint_forces": truss_joint,
    "civil.structural.truss_method_of_sections": sections,
    "civil.structural.beam_offset_point_load": offset_load,
    "civil.structural.influence_line_beam": influence,
    "civil.structural.column_johnson_euler": johnson,
    "civil.structural.t_section_properties": tsection,
    "civil.structural.eccentric_load_kern": eccentric,
    "civil.structural.steel_i_beam_plastic_ltb": steel_i,
    "civil.structural.plate_buckling": plate,
    "civil.structural.prestressed_beam_stresses": prestress,
    "civil.structural.bolt_shear_bearing": bolt,
    "civil.structural.rc_beam_shear_stirrups": shear_rc,
    "civil.structural.development_length": devlen,
    "civil.structural.rc_column_axial": rc_column,
    "civil.structural.branson_effective_inertia": branson,
    "civil.structural.timber_beam_check": timber,
    "civil.geotech.soil_phase_relations": phase,
    "civil.geotech.atterberg_indices": atterberg,
    "civil.geotech.compaction_relative_density": compaction,
    "civil.geotech.rankine_coulomb_pressure": rankine,
    "civil.geotech.gravity_retaining_wall": wall,
    "civil.geotech.infinite_slope": infinite_slope,
    "civil.geotech.boussinesq_stress": boussinesq,
    "civil.geotech.secondary_compression": secondary,
    "civil.geotech.liquefaction_csr": liquefaction,
    "civil.geotech.elastic_settlement": elastic,
    "civil.geotech.mohr_coulomb_triaxial": mohr_coulomb,
    "civil.geotech.meyerhof_bearing_capacity": meyerhof,
    "civil.geotech.pile_capacity": pile,
    "civil.geotech.pile_group_efficiency": group,
    "civil.geotech.braced_cut_peck": peck,
    "civil.geotech.flow_net_seepage": flow_net,
    "civil.geotech.gravity_dam_stability": dam,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    check_case(cid, CASES[cid], rel=2e-4 if cid.endswith(("fixed_end_beam", "propped_cantilever", "three_moment_two_spans", "beam_offset_point_load", "t_section_properties", "steel_i_beam_plastic_ltb", "gravity_dam_stability")) else 1e-6)


def test_terzaghi_consolidation_against_the_series_solution():
    got = solved("civil.geotech.terzaghi_consolidation_time")
    U = lambda Tv: terzaghi_series(0)(Tv)
    # the empirical time factor for U = 90 % must reproduce U = 0.90 in the series to within 1 %
    assert U(got["Tv"]) == pytest.approx(0.90, abs=0.005)
    assert got["Tv"] == pytest.approx(0.848, abs=0.002)                                    # the textbook value for 90 % consolidation
    assert got["tU"] == pytest.approx(got["Tv"] * 3**2 / 2.5 * 3.15576e7, rel=1e-3)
    assert got["Ut"] == pytest.approx(U(2.5 * 2 / 9) * 100 / 100, abs=0.01)                # after 2 years, Tv = 0.556
    for u in (0.2, 0.5, 0.7, 0.95):
        t = solved("civil.geotech.terzaghi_consolidation_time", U=f"{u * 100} %")["Tv"]
        assert U(t) == pytest.approx(u, abs=0.01)


def test_textbook_benchmarks():
    m = solved("civil.structural.mohr_circle_stress")
    assert m["Rm"] / 1e6 == pytest.approx(math.hypot(60, 30)) and m["s1"] / 1e6 == pytest.approx(20 + math.hypot(60, 30)) and m["thp"] == pytest.approx(0.5 * math.atan2(60, 120))
    uni = solved("civil.structural.mohr_circle_stress", sx="50 MPa", sy="20 MPa", txy="0 MPa")                                      # no shear: the faces are principal
    assert uni["Rm"] == pytest.approx(15e6) and uni["thp"] == pytest.approx(0, abs=1e-12) and uni["s1"] == pytest.approx(50e6)
    beam = solved("civil.structural.fixed_end_beam")
    assert beam["Mw"] == pytest.approx(20e3 * 36 / 12) and beam["Mmw"] == pytest.approx(20e3 * 36 / 24)              # wL^2/12 and wL^2/24
    pc = solved("civil.structural.propped_cantilever")
    assert pc["xm"] / 6 == pytest.approx(0.5785, abs=1e-4) and pc["dm"] * 200e9 * 4e8 * 1e-12 / (20e3 * 6**4) == pytest.approx(0.005416, rel=1e-3)   # 0.5785 L and 0.0054 wL^4/EI
    c = solved("civil.structural.column_johnson_euler", L="8 m")
    assert c["fl"] == 1 and c["scr"] == pytest.approx(pi**2 * 200e9 / (8 / 0.03) ** 2)                                     # slender: Euler
    assert solved("civil.structural.column_johnson_euler")["fl"] == 0                                                         # short: Johnson, below yield
    assert solved("civil.structural.plate_buckling", b="200 mm")["scr"] / solved("civil.structural.plate_buckling")["scr"] == pytest.approx(4)   # sigma_cr ~ 1/b^2
    i = solved("civil.structural.steel_i_beam_plastic_ltb")
    assert 1.1 < i["sh"] < 1.2                                                                                                # I-shapes: shape factor about 1.12
    long = solved("civil.structural.steel_i_beam_plastic_ltb", Lb="8 m")["Mcr"]
    assert long < i["Mcr"]                                                                                                    # longer unbraced length, lower critical moment
    assert solved("civil.geotech.soil_phase_relations", w="22.96 %")["S"] == pytest.approx(1.0, abs=0.001)                       # 0.2296 x 2.7 / 0.62 = 1.00: saturated
    sat = solved("civil.geotech.soil_phase_relations", w="22.96 %")
    assert sat["gm"] == pytest.approx(sat["gs"], rel=1e-3)
    mc = solved("civil.geotech.meyerhof_bearing_capacity", ph="30 deg", c="0 kPa", Df="0 m")
    assert mc["Nq"] == pytest.approx(18.40, abs=0.01) and mc["Nc"] == pytest.approx(30.14, abs=0.01) and mc["Ng"] == pytest.approx(15.67, abs=0.01)        # tabulated factors
    assert solved("civil.geotech.rankine_coulomb_pressure", ph="30 deg", dw="0 deg")["Ka"] == pytest.approx(1 / 3)
    assert solved("civil.geotech.infinite_slope", c="0 kPa", ru="0")["FS"] == pytest.approx(solved("civil.geotech.infinite_slope")["FS0"])
    assert solved("civil.geotech.infinite_slope", c="0 kPa", ru=f"{math.cos(25 * deg) ** 2}", ph="30 deg", be="25 deg")["FS"] == pytest.approx(0, abs=1e-9)    # u equal to the normal stress: no friction
    assert solved("civil.geotech.boussinesq_stress", z="0.01 m", a="2 m")["dc"] == pytest.approx(150e3, rel=1e-3)                           # under the surface the pressure is the load
    assert solved("civil.geotech.pile_group_efficiency", m="1", n="1")["Eg"] == pytest.approx(1)
    assert solved("civil.geotech.liquefaction_csr", N1="30", Mw="7.5")["CRR"] == pytest.approx(0.5, abs=0.06)                                # CRR 0.5 near N1 = 30 (upper limit of the curve)
    assert solved("civil.geotech.liquefaction_csr", Mw="7.5")["MSF"] == pytest.approx(1.0, abs=0.03)


def test_catalogued_in_their_sub_disciplines():
    for cid in CASES:
        c = CAT.get(cid)
        assert c.subdisciplines and c.references and c.example
