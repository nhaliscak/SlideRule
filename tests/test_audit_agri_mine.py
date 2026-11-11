"""Equation-audit fill, agriculture and mining: each worked example against a different route (infiltration ODE, Mualem integral, discrete lateral sum, mass balance, Poisson joint spacing)."""

import math

import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

PRE = ""
G = 9.80665


def infil(x):
    K, psi, dth, F, f0, fc, kh, th = (x[k] for k in ("K", "psi", "dth", "F", "f0", "fc", "kh", "th"))
    pd = psi * dth
    F0 = 1e-9
    sol = integrate.solve_ivp(lambda t, f: [K * (1 + pd / f[0])], [0, 1e5], [F0], events=lambda t, f: f[0] - F, rtol=1e-12, atol=1e-15)           # dF/dt = K (1 + psi dtheta / F) until F is reached
    tg = sol.t_events[0][0]
    Fh = integrate.quad(lambda t: fc + (f0 - fc) * math.exp(-kh * t), 0, th)[0]
    return {"tg": tg, "fg": K * (1 + pd / F), "fh": fc + (f0 - fc) * math.exp(-kh * th), "Fh": Fh}


def crop(x):
    Ya = x["Ym"] * (1 - x["Ky"] * (1 - x["ETa"] / x["ETm"]))
    return {"Ya": Ya, "ly": 1 - Ya / x["Ym"], "wp": Ya / x["ETa"], "dw": x["ETm"] - x["ETa"]}


def fert(x):
    Nr = (x["Yg"] * x["un"] - x["Ns"] - x["Nc"]) / x["ef"]
    Pm = Nr / x["fN"]
    return {"Nr": Nr, "Pm": Pm, "cs": Pm * x["pr"]}


def vg(x):
    n = x["n"]
    m = 1 - 1 / n
    th = lambda h: x["thr"] + (x["ths"] - x["thr"]) * (1 + (x["al"] * h) ** n) ** -m
    Se = (th(x["h"]) - x["thr"]) / (x["ths"] - x["thr"])
    hinv = lambda s: (s ** (-1 / m) - 1) ** (1 / n) / x["al"]                           # suction at an effective saturation
    num = integrate.quad(lambda s: 1 / hinv(s), 1e-12, Se, limit=200)[0]                # Mualem's integral of 1/h
    den = integrate.quad(lambda s: 1 / hinv(s), 1e-12, 1 - 1e-12, limit=200)[0]
    K = x["Ks"] * math.sqrt(Se) * (num / den) ** 2
    tfc, tpw = th(33e3), th(1500e3)
    return {"m": m, "Se": Se, "th": th(x["h"]), "Kh": K, "tfc": tfc, "tpw": tpw, "awc": tfc - tpw}


def sprinkler(x):
    Q, D, L, C, N = x["Q"], x["D"], x["L"], x["Chw"], int(round(x["N"]))
    hf0 = 10.67 * L * Q ** 1.852 / (C ** 1.852 * D ** 4.87)
    F = sum((k / N) ** 1.852 for k in range(1, N + 1)) / N                              # flow drops by Q/N after each outlet
    return {"hf0": hf0, "F": F, "hf": hf0 * F, "ar": x["qs"] / (x["Ss"] * x["Sl"])}


def grain(x):
    T = x["T"] - 273.15
    Me = (-math.log(1 - x["RH"]) / (x["Kh"] * (T + x["Ch"]))) ** (1 / x["nh"]) / 100
    # check the relation by inverting it back to the humidity
    assert 1 - math.exp(-x["Kh"] * (T + x["Ch"]) * (Me * 100) ** x["nh"]) == pytest.approx(x["RH"], rel=1e-12)
    t_h = x["t"] / 3600
    MR = math.exp(-x["kd"] * t_h ** x["nd"])
    tt = optimize.brentq(lambda th: Me + (x["M0"] - Me) * math.exp(-x["kd"] * th ** x["nd"]) - x["Mt"], 1e-9, 1e4)    # time at which the moisture reaches the target
    return {"Me": Me, "MR": MR, "M": Me + (x["M0"] - Me) * MR, "tt": tt * 3600}


def screen(x):
    f, o, u = x["f"], x["o"], x["u"]
    F = 100.0
    Oo = F * (f - u) / (o - u)                                                           # oversize stream from the two mass balances
    Uu = F - Oo
    Eo = o * Oo / (f * F)
    Eu = (1 - u) * Uu / ((1 - f) * F)
    Dc, Di, Do, Du, hc = (x[k] * 100 for k in ("Dc", "Di", "Do", "Du", "hc"))           # cm
    d50 = 50.5 * Dc ** 0.46 * Di ** 0.6 * Do ** 1.21 * (x["mu"] * 1000) ** 0.5 * math.exp(0.063 * x["Cv"] * 100) / (Du ** 0.71 * hc ** 0.38 * (x["Qf"] * 6e4) ** 0.45 * (x["dr"] / 1000) ** 0.5)
    d50 *= 1e-6
    return {"Eo": Eo, "Eu": Eu, "Et": Eo * Eu, "d50": d50, "Ec": 1 - math.exp(-0.693 * (x["d"] / d50) ** x["sh"])}


def blast(x):
    A, B, S, H, dh, Lc, Q, E, W = (x[k] for k in ("A", "B", "Sp", "Hb", "dh", "Lc", "Q", "E", "W"))
    V = B * S * H
    X = A * (V / Q) ** 0.8 * Q ** (1 / 6) * (115 / E) ** (19 / 30) / 100
    n = (2.2 - 14 * B / (dh * 1e3)) * math.sqrt((1 + S / B) / 2) * (1 - W / B) * Lc / H
    sd = x["R"] / math.sqrt(x["Wc"])
    return {"pf": Q / V, "X": X, "n": n, "Pp": 1 - math.exp(-0.693 * (x["x"] / X) ** n), "sd": sd, "pv": x["Kp"] * sd ** -x["be"]}


def rock(x):
    lam = x["lj"]
    mean = 1 / lam
    # Poisson joints: share of the core length that lies in intact pieces longer than 0.1 m
    rqd = integrate.quad(lambda s: s * lam * math.exp(-lam * s), 0.1, math.inf)[0] / mean
    Q = rqd * 100 / x["Jn"] * x["Jr"] / x["Ja"] * x["Jw"] / x["SRF"]
    Is = x["P"] / x["De"] ** 2 * (x["De"] / 0.05) ** 0.45
    return {"RQD": rqd, "Q": Q, "Is": Is, "ucs": 22 * Is, "gsi": x["RMR"] - 5}


def haul(x):
    TR = x["mt"] * G * (x["rr"] + math.sin(math.atan(x["gr"])))
    vl = x["Pw"] / TR
    TE = x["me"] * G * x["rr"]
    ve = x["Pw"] / TE
    th, tr = x["Lh"] / vl, x["Lh"] / min(x["vr"], ve)
    tc = x["tl"] + th + tr + x["td"]
    return {"TR": TR, "vl": vl, "TE": TE, "ve": ve, "th": th, "tr": tr, "tc": tc, "pr": x["pl"] / tc}


def dewater(x):
    Qm = x["Q"]
    v = Qm / (math.pi * x["D"] ** 2 / 4)
    hf = 10.67 * x["L"] * Qm ** 1.852 / (x["Chw"] ** 1.852 * x["D"] ** 4.87)
    hv = v ** 2 / (2 * G)
    H = x["Hs"] + hf + hv + x["lm"] * hv
    Ph = x["rho"] * G * Qm * H
    return {"v": v, "hf": hf, "hv": hv, "hm": x["lm"] * hv, "H": H, "Ph": Ph, "Ps": Ph / x["ep"]}


CASES = {
    "agricultural.soil_water.green_ampt_horton_infiltration": (infil, 1e-5), "agricultural.crop.yield_water_production_function": (crop, 1e-9), "agricultural.soil_fertility.nitrogen_fertiliser_rate_balance": (fert, 1e-9),
    "agricultural.soil_water.van_genuchten_retention_conductivity": (vg, 1e-5), "agricultural.irrigation.sprinkler_lateral_christiansen": (sprinkler, 3e-4), "agricultural.grain.henderson_moisture_page_drying": (grain, 1e-7),
    "mining.mineral_processing.screen_cyclone_plitt_d50": (screen, 1e-9), "mining.blasting.kuz_ram_fragmentation_ppv": (blast, 1e-9), "mining.rock_mechanics.rqd_q_system_point_load": (rock, 1e-7),
    "mining.haulage.haul_road_grade_resistance_cycle_productivity": (haul, 1e-9), "mining.dewatering.mine_dewatering_pump_head_power": (dewater, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    y = solved("agricultural.crop.yield_water_production_function", ETa="550 mm")
    assert y["ly"] == pytest.approx(0) and y["Ya"] == pytest.approx(1.0)                                                # no deficit: the maximum yield (10 t/ha = 1 kg/m^2)
    assert solved("agricultural.soil_water.green_ampt_horton_infiltration", F="1e6 mm")["fg"] == pytest.approx(10 / 3.6e6, rel=1e-3)   # long-time Green-Ampt rate approaches K
    v = solved("agricultural.soil_water.van_genuchten_retention_conductivity", h="0.001 kPa")
    assert v["Se"] == pytest.approx(1, abs=1e-4) and v["th"] == pytest.approx(0.43, abs=1e-3)                          # saturated at zero suction
    assert solved("mining.rock_mechanics.rqd_q_system_point_load", lj="0.1 1/m")["RQD"] > 0.99                          # nearly unjointed
    s = solved("mining.mineral_processing.screen_cyclone_plitt_d50", o="100 %", u="0 %")
    assert s["Eo"] == pytest.approx(1) and s["Eu"] == pytest.approx(1)                                                   # a perfect screen
    assert solved("mining.blasting.kuz_ram_fragmentation_ppv", R="100 m", Wc="25 kg")["pv"] > solved("mining.blasting.kuz_ram_fragmentation_ppv")["pv"]


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == cid.split(".")[0]
