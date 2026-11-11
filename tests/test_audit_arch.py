"""Equation-audit fill, architectural engineering: each worked example against a different route (vector sun geometry, Colebrook iteration, Monte Carlo stops, inverse psychrometrics)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import optimize

PRE = "architectural."
G = 9.80665
H = 3600.0
DAY = 86400.0


def daylight(x):
    DF = x["Aw"] * x["T"] * math.degrees(x["th"]) * x["M"] / (x["A"] * (1 - x["Rm"] ** 2)) / 100
    return {"DF": DF, "Ei": DF * x["Eo"], "Dmax": 2 / ((1 - x["Rb"]) * (1 / x["W"] + 1 / x["Hw"]))}


def comfort(x):
    Tg, Ta, va = x["Tg"], x["Ta"], x["va"]
    Tr = (Tg ** 4 + 1.1e8 * va ** 0.6 / (x["ep"] * x["D"] ** 0.4) * (Tg - Ta)) ** 0.25
    hc = max(3.1, 8.3 * va ** 0.6)
    To = (x["hr"] * Tr + hc * Ta) / (x["hr"] + hc)
    PPD = 1 - 0.95 * math.exp(-0.03353 * x["PMV"] ** 4 - 0.2179 * x["PMV"] ** 2)
    dr = max((34 - (Ta - 273.15)) * max(va - 0.05, 0) ** 0.62 * (0.37 * va * x["Tu"] * 100 + 3.14), 0) / 100
    return {"Tr": Tr, "hc": hc, "To": To, "PPD": PPD, "DR": dr}


def psat(T):
    t = T - 273.15
    return 610.5 * math.exp(17.269 * t / (237.3 + t))


def glaser(x):
    Rt = x["Rsi"] + x["R1"] + x["R2"] + x["Rse"]
    q = (x["Ti"] - x["Te"]) / Rt                                                         # heat flux
    Tx = x["Ti"] - q * (x["Rsi"] + x["R1"])                                              # temperature drop up to the interface
    pi, pe = x["RHi"] * psat(x["Ti"]), x["RHe"] * psat(x["Te"])
    px = pi + (pe - pi) * x["s1"] / (x["s1"] + x["s2"])                                  # vapour pressure falls linearly with the diffusion thickness
    Td = optimize.brentq(lambda T: psat(T) - pi, 250, 330)                               # temperature at which the indoor vapour is saturated
    return {"Rt": Rt, "U": 1 / Rt, "Tx": Tx, "pi": pi, "pe": pe, "px": px, "ps": psat(Tx), "mg": psat(Tx) - px, "Td": Td}


def egress(x):
    return {"Ws": x["N"] * x["ws"], "Wl": x["N"] * x["wl"], "tt": x["dt"] / x["vw"], "tq": x["N"] / (x["Fs"] * x["We"]), "te": x["tp"] + x["dt"] / x["vw"] + x["N"] / (x["Fs"] * x["We"])}


def sun(x):
    lat, nd = x["lat"], x["nd"]
    dec = math.radians(23.45) * math.sin(2 * math.pi * (284 + nd) / 365)
    ha = (x["ts"] / H - 12) * math.pi / 12
    # sun unit vector in the local frame (south, east, up) from an equatorial frame rotated by the latitude
    s_eq = np.array([math.cos(dec) * math.cos(ha), -math.cos(dec) * math.sin(ha), math.sin(dec)])    # toward the meridian, east, pole
    R = np.array([[math.sin(lat), 0, -math.cos(lat)], [0, 1, 0], [math.cos(lat), 0, math.sin(lat)]]) # rotate to (south, east, up)
    s = R @ s_eq
    alt = math.asin(s[2])
    az = math.atan2(-s[1], s[0])                                                         # azimuth from south, west positive (the east component of s is negative in the afternoon)
    alt_of = lambda w: math.asin(math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(w))
    wset = optimize.brentq(alt_of, 0.0, math.pi - 1e-9)                                  # hour angle at which the altitude falls to zero
    gw = x["gw"]
    normal = np.array([math.cos(gw), -math.sin(gw), 0.0])                                # façade normal, azimuth gw from south (east negative)
    sunh = np.array([s[0], s[1], s[2]])
    prof = math.atan2(sunh[2], sunh @ np.array([normal[0], normal[1], 0.0]))             # elevation of the sun's projection on the vertical plane through the normal
    return {"dl": dec, "ha": ha, "al": alt, "gs": az, "Nd": 2 * wset * 12 / math.pi * H, "pa": prof, "sd": x["Po"] * math.tan(prof)}


def hvac(x):
    Qc = x["UA"] * x["dT"]
    Qv = x["rho"] * x["cp"] * x["n"] * x["Vr"] * x["dT"]
    Vs = x["Qs"] / (x["rho"] * x["cp"] * x["dTs"])
    D = math.sqrt(4 * Vs / (math.pi * x["vd"]))
    Re = x["rho"] * x["vd"] * D / x["mu"]
    # friction factor from the Colebrook equation solved iteratively, against the explicit Swamee-Jain value used in the calculation
    cb = optimize.brentq(lambda f: 1 / math.sqrt(f) + 2 * math.log10(x["ks"] / (3.7 * D) + 2.51 / (Re * math.sqrt(f))), 1e-4, 0.5)
    sj = 0.25 / math.log10(x["ks"] / (3.7 * D) + 5.74 / Re ** 0.9) ** 2
    assert sj == pytest.approx(cb, rel=0.02)
    return {"Qc": Qc, "Qv": Qv, "Qt": Qc + Qv, "Vs": Vs, "Dd": D, "Re": Re, "fd": sj, "dpl": sj * x["rho"] * x["vd"] ** 2 / (2 * D)}


def degreedays(x):
    hdd = max(x["Tb"] - x["Tm"], 0) * x["Ns"]
    El = (x["UA"] + x["Hv"]) * hdd * 24 * H / DAY
    Eg = x["Qg"] * x["Ns"]
    Eh = max(El - Eg, 0)
    return {"hdd": hdd, "El": El, "Eg": Eg, "Eh": Eh, "Ef": Eh / x["eta"], "eui": Eh / x["eta"] / x["Af"]}


def floor(x):
    fn = 0.18 * math.sqrt(G / x["dl"])
    ap = x["P0"] * math.exp(-0.35 * fn) / (x["bt"] * x["W"])
    return {"dp": x["L"] / x["rt"], "fn": fn, "ap": ap, "ok": 1.0 if ap < x["al"] else 0.0}


def lift(x):
    N, P = int(x["Nf"]), int(x["Pc"])
    S1 = N * (1 - (1 - 1 / N) ** P)
    rtt = 2 * x["Hr"] * x["hf"] / x["vl"] + (S1 + 1) * x["ts"] + 2 * P * x["tpp"]
    hc = 300 * P * x["Ln"] / rtt
    return {"S1": S1, "rtt": rtt, "hc5": hc, "hcp": hc / x["pop"], "iv": rtt / x["Ln"]}


def hotwater(x):
    Vh = x["Vu"] * (x["Tu"] - x["Tc"]) / (x["Th"] - x["Tc"])                             # energy balance of the mix: Vh Th + (Vu - Vh) Tc = Vu Tu
    return {"Vh": Vh, "Ph": x["rho"] * x["cw"] * Vh * (x["Th"] - x["Tc"]) / (x["eta"] * x["tr"]), "Dp": math.sqrt(4 * x["Qp"] / (math.pi * x["vp"])), "Re": x["rho"] * x["vp"] * math.sqrt(4 * x["Qp"] / (math.pi * x["vp"])) / x["mu"]}


def plume(x):
    Q, Df, z = x["Q"] / 1e3, x["Df"], x["z"]                                             # kW
    Qc = x["cf"] * Q
    mp = 0.071 * Qc ** (1 / 3) * z ** (5 / 3) + 0.0018 * Qc
    Ts = x["To"] + Qc * 1e3 / (mp * x["cp"])
    return {"Lf": 0.235 * Q ** 0.4 - 1.02 * Df, "Qc": Qc * 1e3, "mp": mp, "Ts": Ts, "Vs": mp * x["To"] / (x["ro"] * Ts)}


def acoustics(x):
    nrc = round((x["a250"] + x["a500"] + x["a1k"] + x["a2k"]) / 4 / 0.05) * 0.05
    t1, t2 = 10 ** (-x["TL1"] / 10), 10 ** (-x["TL2"] / 10)
    TLc = -10 * math.log10((x["S1"] * t1 + x["S2"] * t2) / (x["S1"] + x["S2"]))          # sound power transmitted through each area adds
    return {"nrc": nrc, "t1": t1, "t2": t2, "TLc": TLc, "T60": 0.161 * x["Vr"] / x["Aa"]}


CASES = {
    PRE + "lighting.daylight_factor_bre": (daylight, 1e-9), PRE + "comfort.mean_radiant_operative_ppd_draught": (comfort, 1e-9), PRE + "moisture.glaser_interface_condensation": (glaser, 1e-7),
    PRE + "fire.egress_width_evacuation_time": (egress, 1e-9), PRE + "solar.sun_position_day_length_overhang_shading": (sun, 1e-6), PRE + "hvac.heating_load_supply_air_duct_friction": (hvac, 1e-9),
    PRE + "energy.degree_days_annual_heating_demand": (degreedays, 1e-9), PRE + "structures.preliminary_sizing_floor_vibration": (floor, 1e-9), PRE + "vertical_transport.lift_round_trip_capacity": (lift, 1e-9),
    PRE + "plumbing.hot_water_recovery_mixing_pipe_sizing": (hotwater, 1e-9), PRE + "fire.heskestad_plume_flame_height_smoke_flow": (plume, 1e-9), PRE + "acoustics.nrc_composite_tl_sabine": (acoustics, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_probable_stops_agree_with_a_simulation():
    rng = np.random.default_rng(3)
    N, P = 14, 10
    stops = np.mean([len(set(rng.integers(1, N + 1, P))) for _ in range(40000)])
    assert solved(PRE + "vertical_transport.lift_round_trip_capacity")["S1"] == pytest.approx(stops, rel=0.01)


def test_benchmarks():
    s = solved(PRE + "solar.sun_position_day_length_overhang_shading", lat="45 deg", nd="80", ts="12 h")                         # equinox at noon at 45 degrees: altitude 45 degrees
    assert s["al"] == pytest.approx(math.radians(45 - 0.4), abs=0.02) and s["gs"] == pytest.approx(0, abs=1e-6)
    assert solved(PRE + "solar.sun_position_day_length_overhang_shading", nd="80")["Nd"] == pytest.approx(12 * H, rel=0.01)       # equinox: twelve hours of daylight
    assert solved(PRE + "comfort.mean_radiant_operative_ppd_draught", PMV="0")["PPD"] == pytest.approx(0.05)                     # minimum PPD is 5 %
    g = solved(PRE + "moisture.glaser_interface_condensation", RHi="30 %", RHe="40 %")
    assert g["mg"] > 0                                                                                                            # a dry interior stays clear of condensation
    assert solved(PRE + "acoustics.nrc_composite_tl_sabine", S2="0.0001 m^2")["TLc"] == pytest.approx(50, abs=0.5)  # no opening: the wall's own loss
    d = solved(PRE + "lighting.daylight_factor_bre", Aw="0 m^2")
    assert d["DF"] == pytest.approx(0, abs=1e-12)


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "architectural"
