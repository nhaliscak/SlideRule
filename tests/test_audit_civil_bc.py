"""Equation-audit fill, civil B and C: hydraulics, hydrology, transport, surveying, project management, waves, environmental (each checked by a different route where one exists)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import optimize, special, stats

pi = math.pi
deg = pi / 180
g = 9.80665


# ---------------------------------------------------------------- hydraulics
def critical(x):
    q = x["Q"] / x["b"]
    Fr = lambda y: (q / y) / math.sqrt(g * y)
    yc = optimize.brentq(lambda y: Fr(y) - 1, 0.01, 50)                                     # Froude number 1
    Emin = optimize.minimize_scalar(lambda y: y + q**2 / (2 * g * y**2), bounds=(0.01, 50), method="bounded", options={"xatol": 1e-12}).fun
    y = x["y"]
    return {"q": q, "yc": yc, "Ec": Emin, "v": q / y, "E": y + q**2 / (2 * g * y**2), "Fr": Fr(y), "sup": 1.0 if Fr(y) > 1 else 0.0}


def jump(x):
    q = x["Q"] / x["b"]
    y1 = x["y1"]
    mom = lambda y: q**2 / (g * y) + y**2 / 2                                                # momentum function per unit weight
    y2 = optimize.brentq(lambda y: mom(y) - mom(y1), y1 * 1.0001, 100)
    E = lambda y: y + q**2 / (2 * g * y**2)
    v1 = q / y1
    return {"v1": v1, "F1": v1 / math.sqrt(g * y1), "y2": y2, "dE": E(y1) - E(y2), "Lj": 6 * y2, "ef": (E(y1) - E(y2)) / E(y1)}


def step(x):
    Q, b, n, S0 = x["Q"], x["b"], x["n"], x["S0"]
    def sec(y):
        A, P = b * y, b + 2 * y
        v = Q / A
        return y + v**2 / (2 * g), (n * v) ** 2 / (A / P) ** (4 / 3)
    E1, S1 = sec(x["y1"])
    E2, S2 = sec(x["y2"])
    return {"E1": E1, "E2": E2, "Sf1": S1, "Sf2": S2, "dx": (E2 - E1) / (S0 - (S1 + S2) / 2)}


def culvert(x):
    A = pi * x["D"] ** 2 / 4
    v = x["Q"] / A
    R = x["D"] / 4
    Hf = x["n"] ** 2 * v**2 * x["Lc"] / R ** (4 / 3)                                          # Manning friction loss
    Ho = (1 + x["Ke"]) * v**2 / (2 * g) + Hf
    HWo = Ho + x["ho"] - x["S"] * x["Lc"]
    HWi = x["D"] / 2 + (x["Q"] / (x["Cd"] * A)) ** 2 / (2 * g)
    return {"v": v, "Ho": Ho, "HWo": HWo, "HWi": HWi, "HW": max(HWo, HWi)}


def hammer(x):
    a = 1 / math.sqrt(x["rho"] * (1 / x["K"] + x["D"] * x["c1"] / (x["Ep"] * x["t"])))
    Tcr = 2 * x["Lp"] / a
    return {"a": a, "dP": x["rho"] * a * x["v0"], "dH": a * x["v0"] / g, "Tcr": Tcr, "rap": 1.0 if x["tc"] <= Tcr else 0.0}


def hw_pipe_q(D, L, C, hf):
    A, R = pi * D**2 / 4, D / 4
    return A * 0.849 * C * R**0.63 * (hf / L) ** 0.54


def parallel(x):
    f = lambda hf: hw_pipe_q(x["D1"], x["L1"], x["C1"], hf) + hw_pipe_q(x["D2"], x["L2"], x["C2"], hf) - x["Q"]
    hf = optimize.brentq(f, 1e-6, 1e4)
    return {"hf": hf, "Q1": hw_pipe_q(x["D1"], x["L1"], x["C1"], hf), "Q2": hw_pipe_q(x["D2"], x["L2"], x["C2"], hf)}


def hardy(x):
    rs = [x["r1"], x["r2"], x["r3"]]
    Qs = [x["Q1"], x["Q2"], x["Q3"]]
    h = lambda r, Q: r * np.sign(Q) * abs(Q) ** 1.852
    hs = sum(h(r, Q) for r, Q in zip(rs, Qs))
    dh = sum((h(r, Q + 1e-7) - h(r, Q - 1e-7)) / 2e-7 for r, Q in zip(rs, Qs))         # derivative of the loop head loss by finite differences
    dQ = -hs / dh
    return {"hs": hs, "dQ": dQ, "Q1n": Qs[0] + dQ, "Q2n": Qs[1] + dQ, "Q3n": Qs[2] + dQ}


def scour(x):
    Fr = x["v1"] / math.sqrt(g * x["y1"])
    ys = 2 * x["K1"] * x["K2"] * x["K3"] * x["y1"] * (x["a"] / x["y1"]) ** 0.65 * Fr**0.43
    return {"Fr": Fr, "ys": ys, "rs": ys / x["y1"]}


def weirs(x):
    H = x["H"]
    return {"Qv": 8 / 15 * x["Cv"] * math.sqrt(2 * g) * math.tan(x["th"] / 2) * H**2.5, "Qb": x["Cb"] * x["bw"] * math.sqrt(g * (2 * H / 3) ** 3), "Qc": 2 / 3 * x["Cc"] * math.sqrt(2 * g) * x["bw"] * H**1.5}


def detention(x):
    Cr, A, a, b, Qo = x["Cr"], x["A"], x["a"], x["b"], x["Qo"]
    V = lambda t: (Cr * A * (a / (t + b)) - Qo) * t                                           # SI: a in m*s/s..., t in s
    r = optimize.minimize_scalar(lambda t: -V(t), bounds=(1.0, 1e6), method="bounded", options={"xatol": 1e-9})
    ts = r.x
    return {"ts": ts, "Qin": Cr * A * a / (ts + b), "Vs": -r.fun}


# ---------------------------------------------------------------- hydrology
def unit_hydro(x):
    Tp = x["D"] / 2 + 0.6 * x["Tc"]
    Tb = 2.67 * Tp
    V = x["A"] * x["Pe"]
    return {"Tp": Tp, "Tb": Tb, "Qp": 2 * V / Tb, "Vq": V}                                  # a triangle of base Tb has area Qp Tb/2 = V


def muskingum(x):
    K, X, dt, I1, I2, O1 = (x[k] for k in ("K", "X", "dt", "I1", "I2", "O1"))
    # storage balance S2 - S1 = (I1 + I2) dt/2 - (O1 + O2) dt/2 with S = K[XI + (1 - X)O], solved for O2
    S1 = K * (X * I1 + (1 - X) * O1)
    O2 = (dt * (I1 + I2) / 2 - dt * O1 / 2 + S1 - K * X * I2) / (K * (1 - X) + dt / 2)
    den = K * (1 - X) + dt / 2
    return {"C0": (dt / 2 - K * X) / den, "C1": (dt / 2 + K * X) / den, "C2": (K * (1 - X) - dt / 2) / den, "O2": O2}


def idf(x):
    i = x["a"] * x["Tr"] ** x["m"] / ((x["t"] + x["b"]) / 60) ** x["n"]
    return {"i": i, "P": i * x["t"]}


def tconc(x):
    ft = 3.28084
    L, S = x["L"], x["S0"]
    Tk = 0.0078 * (L * ft) ** 0.77 * S ** -0.385                                             # Kirpich in customary units (L in ft), minutes
    Sr = 1000 / x["CN"] - 10
    lag = (L * ft) ** 0.8 * (Sr + 1) ** 0.7 / (1900 * (100 * S) ** 0.5)                        # NRCS lag in customary units, hours
    return {"Tk": Tk * 60, "Sr": Sr, "Tl": lag * 3600, "Tn": lag / 0.6 * 3600}


def gumbel(x):
    scale = x["sg"] * math.sqrt(6) / pi
    loc = x["mu"] - 0.5772156649 * scale
    T = x["T"] / 3.15576e7
    xT = stats.gumbel_r.ppf(1 - 1 / T, loc=loc, scale=scale)
    return {"K": (xT - x["mu"]) / x["sg"], "xT": xT, "Pn": 1 - (1 - 1 / T) ** (x["nl"] / 3.15576e7)}


def fao_pm(x):
    T = x["Tm"] - 273.15
    es = 0.6108 * math.exp(17.27 * T / (T + 237.3))
    ea = es * x["RH"]
    D = 4098 * es / (T + 237.3) ** 2
    gm = 0.000665 * x["P"] / 1e3
    Rn, G = x["Rn"] / 1e6, x["G"] / 1e6                                                      # MJ per m2 per s -> carried in SI: convert to MJ/m2/day
    Rn_d, G_d = Rn * 86400, G * 86400
    et = (0.408 * D * (Rn_d - G_d) + gm * 900 / (T + 273) * (x["u2"]) * (es - ea)) / (D + gm * (1 + 0.34 * x["u2"]))
    return {"es": es * 1e3, "ea": ea * 1e3, "Dl": D * 1e3, "gm": gm * 1e3, "ET0": et * 1e-3 / 86400}


def hargreaves(x):
    Tm, Tx, Tn = (x[k] - 273.15 for k in ("Tm", "Tx", "Tn"))
    return {"ET0": 0.0023 * x["Ra"] * (Tm + 17.8) * math.sqrt(Tx - Tn)}


def theis(x):
    u = x["r"] ** 2 * x["S"] / (4 * x["T"] * x["t"])
    W = special.exp1(u)
    return {"u": u, "Wu": W, "s": x["Q"] * W / (4 * pi * x["T"])}


# ---------------------------------------------------------------- transport, survey, management
def vcurve(x):
    g1, g2, S, h1, h2, L, y0, xx = x["g1"], x["g2"], x["S"], x["h1"], x["h2"], x["Lc"], x["y0"], x["x"]
    A = g1 - g2
    elev = lambda t: y0 + g1 * t - A * t**2 / (2 * L)
    xh = optimize.minimize_scalar(lambda t: -elev(t), bounds=(0, L), method="bounded", options={"xatol": 1e-10}).x           # crest by direct maximisation
    # stopping sight distance on a parabola: the length at which the sight line just clears the crest (S < L)
    Lm = A * S**2 / (2 * (math.sqrt(h1) + math.sqrt(h2)) ** 2)
    return {"A": A, "Lm": Lm, "K": L / (100 * A), "y": elev(xx), "xh": xh, "yh": elev(xh)}


def freeway(x):
    D = x["vp"] / x["Sp"]
    los = 1 + sum(D > t for t in (7 / 1e3, 11 / 1e3, 16 / 1e3, 22 / 1e3, 28 / 1e3))        # per metre in SI
    return {"D": D, "vc": x["vp"] / x["cap"], "los": float(los)}


def gravity(x):
    f = np.array([x["A1"] * (60 / x["t1"]) ** x["be"], x["A2"] * (60 / x["t2"]) ** x["be"], x["A3"] * (60 / x["t3"]) ** x["be"]])
    T = x["Pt"] * f / f.sum()
    return {"T1": T[0], "T2": T[1], "T3": T[2]}


def traverse(x):
    L = [x[f"L{i}"] for i in range(1, 5)]
    az = [x[f"a{i}"] for i in range(1, 5)]
    pts = [(0.0, 0.0)]
    for l, a in zip(L, az):
        pts.append((pts[-1][0] + l * math.sin(a), pts[-1][1] + l * math.cos(a)))               # walk the traverse
    e = math.hypot(*pts[-1])
    return {"SN": pts[-1][1], "SE": pts[-1][0], "em": e, "Pm": sum(L), "N": sum(L) / e}


def polygon(x):
    pts = [(x[f"x{i}"], x[f"y{i}"]) for i in range(1, 5)]
    # area by splitting into two triangles with the cross product, perimeter by summing the sides
    def tri(p, q, r):
        return abs((q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1])) / 2
    return {"Ar": tri(pts[0], pts[1], pts[2]) + tri(pts[0], pts[2], pts[3]), "Pm": sum(math.dist(pts[i], pts[(i + 1) % 4]) for i in range(4))}


def curvature(x):
    hc = x["D"] ** 2 / (2 * x["Rt"])
    return {"hc": hc, "hr": x["kr"] * hc, "hcr": hc * (1 - x["kr"])}


def cpm(x):
    # longest paths by enumerating the two routes A-B-D and A-C-D
    routes = {"B": x["dA"] + x["dB"] + x["dD"], "C": x["dA"] + x["dC"] + x["dD"]}
    T = max(routes.values())
    EFB, EFC = x["dA"] + x["dB"], x["dA"] + x["dC"]
    return {"EFB": EFB, "EFC": EFC, "ESD": T - x["dD"], "Tp": T, "fB": T - routes["B"], "fC": T - routes["C"], "cp": 1.0 if routes["B"] >= routes["C"] else 2.0}


def evm(x):
    BAC, PV, EV, AC = x["BAC"], x["PV"], x["EV"], x["AC"]
    cpi = EV / AC
    return {"CV": EV - AC, "SV": EV - PV, "CPI": cpi, "SPI": EV / PV, "EAC": BAC / cpi, "ETC": BAC / cpi - AC, "TCPI": (BAC - EV) / (BAC - AC)}


# ---------------------------------------------------------------- coastal
def waves(x):
    H0, T, h, a0 = x["H0"], x["Tw"], x["h"], x["a0"]
    w = 2 * pi / T
    k = optimize.brentq(lambda k: w**2 - g * k * math.tanh(k * h), 1e-6, 100)               # the exact dispersion relation
    c, L = w / k, 2 * pi / k
    n = 0.5 * (1 + 2 * k * h / math.sinh(2 * k * h))
    c0 = g * T / (2 * pi)
    Ks = math.sqrt((c0 / 2) / (n * c))
    al = math.asin(c / c0 * math.sin(a0))
    Kr = math.sqrt(math.cos(a0) / math.cos(al))
    H = H0 * Ks * Kr
    y = w**2 * h / g
    return {"y": y, "kh": k * h, "Lw": L, "c": c, "cg": n * c, "c0": c0, "Ks": Ks, "al": al, "Kr": Kr, "H": H, "Hb": 0.78 * h, "br": 1.0 if H > 0.78 * h else 0.0}


def runup(x):
    L0 = g * x["Tw"] ** 2 / (2 * pi)
    xi = x["sl"] / math.sqrt(x["Hs"] / L0)
    return {"L0": L0, "xi": xi, "Ru": x["Hs"] * min(1.65 * xi, 4 - 1.5 / math.sqrt(xi))}


# ---------------------------------------------------------------- environmental
def bod(x):
    kT = x["k20"] * x["th"] ** (x["Ts"] - 293.15)
    L0 = x["BOD5"] / (1 - math.exp(-x["k20"] * 5 * 86400))
    return {"kT": kT, "L0": L0, "Bt": L0 * (1 - math.exp(-x["k20"] * x["t"])), "BtT": L0 * (1 - math.exp(-kT * x["t"]))}


def trickling(x):
    W = x["W"] * 86400                                                                        # kg/d from kg/s
    F = (1 + x["R"]) / (1 + x["R"] / 10) ** 2
    E = 1 / (1 + 0.4432 * math.sqrt(W / (x["Vf"] * F)))
    return {"F": F, "E": E, "Se": x["Si"] * (1 - E)}


def sandfilter(x):
    S = 6 / (x["ph"] * x["d"])
    return {"hL": 5 * x["mu"] * (1 - x["ep"]) ** 2 * S**2 * x["Lf"] * x["v"] / (x["rho"] * g * x["ep"] ** 3), "Af": x["Q"] / x["v"]}


def flocc(x):
    G = math.sqrt(x["P"] / (x["mu"] * x["Vb"]))
    return {"G": G, "Gt": G * x["td"]}


def landfill(x):
    Q = x["k"] * x["L0"] * x["M"] * math.exp(-x["k"] * x["t"])
    return {"Q": Q, "fr": 1 - math.exp(-x["k"] * x["t"]), "Pw": Q * 35.8e6}


def barrier(x):
    A = math.hypot(x["a"], x["hb"])
    B = math.hypot(x["b"], x["hb"])
    dl = A + B - (x["a"] + x["b"])
    lam = x["cs"] / x["f"]
    N = 2 * dl / lam
    return {"dl": dl, "lam": lam, "N": N, "IL": 10 * math.log10(3 + 20 * N)}


def plume(x):
    Fb = g * x["vs"] * x["ds"] ** 2 * (x["Ts"] - x["Ta"]) / (4 * x["Ts"])
    dh = 21.425 * Fb**0.75 / x["u"] if Fb < 55 else 38.71 * Fb**0.6 / x["u"]
    return {"Fb": Fb, "dh": dh, "He": x["hs"] + dh}


CASES = {
    "civil.hydraulics.critical_depth_specific_energy": (critical, 1e-6), "civil.hydraulics.hydraulic_jump": (jump, 1e-6), "civil.hydraulics.standard_step_reach": (step, 1e-9), "civil.hydraulics.culvert_headwater": (culvert, 1e-9),
    "civil.hydraulics.water_hammer": (hammer, 1e-9), "civil.hydraulics.parallel_pipes_hazen_williams": (parallel, 1e-6), "civil.hydraulics.hardy_cross_loop": (hardy, 1e-5), "civil.hydraulics.pier_scour": (scour, 1e-9),
    "civil.hydraulics.weirs_other_shapes": (weirs, 1e-9), "civil.hydrology.detention_pond_rational": (detention, 1e-5),
    "civil.hydrology.scs_unit_hydrograph": (unit_hydro, 1e-9), "civil.hydrology.muskingum_routing": (muskingum, 1e-9), "civil.hydrology.idf_bernard": (idf, 1e-9), "civil.hydrology.time_of_concentration": (tconc, 2e-3),
    "civil.hydrology.gumbel_flood_frequency": (gumbel, 1e-6), "civil.hydrology.penman_monteith_fao56": (fao_pm, 1e-6), "civil.hydrology.hargreaves_et0": (hargreaves, 1e-6), "civil.hydrology.theis_well_function": (theis, 1e-5),
    "civil.highway.vertical_curve": (vcurve, 1e-6), "civil.transport.freeway_density_los": (freeway, 1e-9), "civil.transport.gravity_trip_distribution": (gravity, 1e-9), "civil.survey.traverse_closure": (traverse, 1e-6),
    "civil.survey.polygon_area_coordinates": (polygon, 1e-9), "civil.survey.curvature_refraction": (curvature, 1e-9), "civil.construction.cpm_diamond_network": (cpm, 1e-9), "civil.construction.earned_value": (evm, 1e-9),
    "civil.coastal.wave_shoaling_refraction": (waves, 2e-3), "civil.coastal.wave_runup": (runup, 1e-9),
    "environmental.wastewater.bod_kinetics": (bod, 1e-6), "environmental.wastewater.trickling_filter_nrc": (trickling, 1e-6), "environmental.water.sand_filter_headloss": (sandfilter, 1e-6),
    "environmental.water.flocculation_g_value": (flocc, 1e-9), "environmental.waste.landfill_gas_first_order": (landfill, 1e-9), "environmental.noise.barrier_attenuation": (barrier, 1e-6), "environmental.air.briggs_plume_rise": (plume, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_learning_curve_against_the_exact_sum():
    got = solved("civil.construction.learning_curve")
    b = math.log(0.85) / math.log(2)
    exact = sum(40 * k**b for k in range(1, 21))                                              # unit times added one by one
    assert got["b"] == pytest.approx(b) and got["Tn"] == pytest.approx(40 * 20**b * 3600)                          # SI results are in seconds
    assert got["Tt"] == pytest.approx(exact * 3600, rel=0.01) and got["Ta"] == pytest.approx(got["Tt"] / 20)


def test_hydrology_and_hydraulics_benchmarks():
    j = solved("civil.hydraulics.hydraulic_jump", y1="0.3 m", Q="9 m^3/s", b="5 m")                # Fr1 = 5.96/1.715... large jump
    assert j["y2"] / 0.3 == pytest.approx(0.5 * (math.sqrt(1 + 8 * j["F1"] ** 2) - 1), rel=1e-9)
    assert solved("civil.hydraulics.critical_depth_specific_energy", y="1.0 m", Q="10 m^3/s", b="5 m")["sup"] in (0, 1)
    assert solved("civil.hydraulics.critical_depth_specific_energy")["Ec"] == pytest.approx(1.5 * solved("civil.hydraulics.critical_depth_specific_energy")["yc"])   # Ec = 1.5 yc
    m = solved("civil.hydrology.muskingum_routing")
    assert m["C0"] + m["C1"] + m["C2"] == pytest.approx(1.0)
    assert solved("civil.hydrology.muskingum_routing", I2="30 m^3/s")["O2"] == pytest.approx(30)                       # steady flow stays steady
    assert solved("civil.hydrology.gumbel_flood_frequency", T="2.7183 year")["K"] == pytest.approx(-math.sqrt(6) / pi * (0.5772 + math.log(math.log(2.7183 / 1.7183))), rel=1e-3)   # K = 0 near T = 2.33
    assert solved("civil.hydrology.gumbel_flood_frequency", T="2.33 year")["K"] == pytest.approx(0, abs=0.01)
    assert solved("civil.hydrology.theis_well_function", t="48 h")["s"] < solved("civil.hydrology.theis_well_function")["s"] * 2     # drawdown grows slowly with time
    assert solved("civil.hydrology.theis_well_function", t="1 h")["Wu"] == pytest.approx(special.exp1(0.72 / (4 * 0.004 * 3600)), rel=1e-4)
    assert solved("civil.hydrology.scs_unit_hydrograph")["Qp"] > 0
    assert solved("civil.highway.vertical_curve", g1="2 %", g2="-2 %", Lc="200 m", x="100 m")["xh"] == pytest.approx(100, rel=1e-6)   # symmetric curve: crest at the middle
    assert solved("civil.survey.polygon_area_coordinates", x1="0 m", y1="0 m", x2="10 m", y2="0 m", x3="10 m", y3="5 m", x4="0 m", y4="5 m")["Ar"] == pytest.approx(50)
    assert solved("civil.survey.traverse_closure", L1="100 m", L2="100 m", L3="100 m", L4="100 m", a1="0 deg", a2="90 deg", a3="180 deg", a4="270 deg")["em"] == pytest.approx(0, abs=1e-9)   # a square closes
    assert solved("civil.coastal.wave_shoaling_refraction", h="200 m")["Ks"] == pytest.approx(1.0, abs=0.01)                      # deep water: no shoaling
    assert solved("civil.coastal.wave_shoaling_refraction", h="1.5 m")["br"] == 1                                               # a 2 m wave in 1.5 m of water breaks
    assert solved("environmental.noise.barrier_attenuation", hb="0.001 m")["IL"] == pytest.approx(10 * math.log10(3), abs=0.3)   # grazing: about 5 dB
    assert solved("environmental.wastewater.bod_kinetics", Ts="20 degC")["kT"] == pytest.approx(0.23 / 86400, rel=1e-9)            # no correction at 20 C


def test_catalogued_in_their_sub_disciplines():
    for cid in CASES:
        c = CAT.get(cid)
        assert c.subdisciplines and c.references and c.example
