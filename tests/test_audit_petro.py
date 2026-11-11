"""Equation-audit fill, petroleum: each worked example against a different route (line-source well-test round trip, general flow equation, elasticity solution, force balance)."""

import math

import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize, special

PRE = "petroleum."
G = 9.80665
MPA = 1e6
PSI = 6894.757293168
MD = 9.869233e-16
DAY = 86400.0


def mb(x):
    F = x["Np"] * (x["Bo"] + (x["Rp"] - x["Rs"]) * x["Bg"])
    Eo = (x["Bo"] - x["Boi"]) + (x["Rsi"] - x["Rs"]) * x["Bg"]
    Eg = x["Boi"] * (x["Bg"] / x["Bgi"] - 1)
    Efw = x["Boi"] * (1 + x["mg"]) * (x["cw"] * x["Swi"] + x["cf"]) / (1 - x["Swi"]) * x["dp"]
    N = (F - x["We"]) / (Eo + x["mg"] * Eg + Efw)
    assert F == pytest.approx(N * (Eo + x["mg"] * Eg + Efw) + x["We"], rel=1e-12)       # the material balance closes
    return {"F": F, "Eo": Eo, "Eg": Eg, "Efw": Efw, "N": N, "DDI": N * Eo / F, "SDI": N * x["mg"] * Eg / F, "CDI": N * Efw / F, "WDI": x["We"] / F}


def welltest(x):
    k = 2.303 * x["q"] * x["B"] * x["mu"] / (4 * math.pi * x["ms"] * x["h"])
    s = 1.1513 * ((x["pin"] - x["p1"]) / x["ms"] - math.log10(k * 3600 / (x["phi"] * x["mu"] * x["ct"] * x["rw"] ** 2)) - 0.3514)
    dps = x["q"] * x["B"] * x["mu"] * s / (2 * math.pi * k * x["h"])
    return {"k": k, "s": s, "dps": dps, "FE": (x["pin"] - x["p1"] - dps) / (x["pin"] - x["p1"]), "Cs": x["q"] * x["B"] * x["dt"] / x["dpc"]}


def corey(x):
    Sn = (x["Sw"] - x["Swc"]) / (1 - x["Swc"] - x["Sor"])
    krw, kro = x["krw0"] * Sn ** x["nw"], x["kro0"] * (1 - Sn) ** x["no"]
    lw, lo = krw / x["muw"], kro / x["muo"]                                              # phase mobilities
    return {"Sn": Sn, "krw": krw, "kro": kro, "fw": lw / (lw + lo), "Mo": lw / lo, "Pc": x["J"] * x["sg"] * math.cos(x["th"]) * math.sqrt(x["phi"] / x["k"])}


def pvt(x):
    p, T = x["p"] / PSI, (x["T"] - 255.372) * 1.8
    API, g = x["API"], x["gg"]
    go = 141.5 / (API + 131.5)
    Rs = g * ((p / 18.2 + 1.4) * 10 ** (0.0125 * API - 0.00091 * T)) ** 1.2048                # scf/stb
    Bo = 0.9759 + 0.00012 * (Rs * math.sqrt(g / go) + 1.25 * T) ** 1.2
    ppr, tpr = x["p"] / x["Ppc"], x["T"] / x["Tpc"]
    Z = 1 - 3.52 * ppr / 10 ** (0.9813 * tpr) + 0.274 * ppr ** 2 / 10 ** (0.8157 * tpr)
    return {"go": go, "Rs": Rs * 0.178108, "Bo": Bo, "Ppr": ppr, "Tpr": tpr, "Z": Z, "Bg": Z * x["T"] * 101325 / (x["p"] * 288.706)}


def pipeline(x):
    p1, p2, D, L = x["p1"] / PSI, x["p2"] / PSI, x["D"] / 0.0254, x["L"] / 1609.344
    Tf, Tb, Pb = x["Tf"] * 1.8, x["Tb"] * 1.8, x["Pb"] / PSI
    f = 0.032 / D ** (1 / 3)                                                             # the Weymouth friction factor
    gen = 77.54 * (Tb / Pb) * ((p1 ** 2 - p2 ** 2) / (x["gg"] * Tf * L * x["Z"] * f)) ** 0.5 * D ** 2.5     # general (Darcy-Weisbach) gas flow equation, scf/day
    pan = 435.87 * x["E"] * (Tb / Pb) ** 1.0788 * ((p1 ** 2 - p2 ** 2) / (x["gg"] ** 0.8539 * Tf * L * x["Z"])) ** 0.5394 * D ** 2.6182
    return {"Qw": x["E"] * gen * 0.0283168 / DAY, "Qp": pan * 0.0283168 / DAY}


def vogel(x):
    xt = x["pt"] / x["pr"]
    qm = x["qt"] / (1 - 0.2 * xt - 0.8 * xt ** 2)
    ipr = lambda pw: qm * (1 - 0.2 * pw / x["pr"] - 0.8 * (pw / x["pr"]) ** 2)
    pd = optimize.brentq(lambda pw: ipr(pw) - x["qd"], 0, x["pr"])                       # flowing pressure at which the IPR gives the target rate
    return {"xt": xt, "qm": qm, "xw": x["pw"] / x["pr"], "qw": ipr(x["pw"]), "pd": pd}


def esp(x):
    H = x["Hl"] + x["hf"] + x["pwh"] / (x["rho"] * G)
    Ph = x["rho"] * G * x["Q"] * H
    return {"H": H, "ns": H / x["hs"], "Ph": Ph, "Ps": Ph / x["ep"], "Pm": Ph / x["ep"] / x["em"]}


def fracture(x):
    E_plane = 2 * x["G"] / (1 - x["nu"])                                                 # plane-strain modulus
    a = x["hf"] / 2
    w = lambda y: 4 * x["pn"] * math.sqrt(a * a - y * y) / E_plane                      # Sneddon/Griffith opening (both faces) under uniform pressure
    wm = w(0)
    wa = integrate.quad(w, -a, a)[0] / x["hf"]                                           # average opening over the height
    V = x["qi"] * x["t"]
    return {"wm": wm, "wa": wa, "Vf": V, "xf": V / (2 * wa * x["hf"])}


def bit(x):
    At = x["Nn"] * math.pi * x["dn"] ** 2 / 4
    vn = x["Qm"] / At
    dpb = x["rho"] * vn ** 2 / (2 * x["Cd"] ** 2)
    hhp = dpb * x["Qm"]
    return {"At": At, "vn": vn, "dpb": dpb, "hhp": hhp, "hsi": hhp / (math.pi * x["Db"] ** 2 / 4), "Fj": x["Cd"] * x["rho"] * x["Qm"] * vn, "ecd": x["rho"] + x["dpa"] / (G * x["TVD"])}


def drag(x):
    w = x["ms"] * G * (1 - x["rho"] / x["rs"])
    W, a, mu = w * x["L"], x["al"], x["mu"]
    # force balance of a body on an incline: moving up needs the along-hole weight component plus friction; moving down is eased by the friction
    up = W * math.cos(a) + mu * W * math.sin(a)
    down = W * math.cos(a) - mu * W * math.sin(a)
    return {"w": w, "Hp": up, "Hn": W * math.cos(a), "Hs": down, "Fd": mu * W * math.sin(a), "Tq": mu * W * math.sin(a) * x["rp"]}


def cement(x):
    area = lambda d: math.pi * d * d / 4
    Va = (area(x["dh"]) - area(x["dco"])) * x["La"] * (1 + x["ex"])
    Vs = area(x["dci"]) * x["Ls"]
    return {"Va": Va, "Vs": Vs, "Vsl": Va + Vs, "Vd": area(x["dci"]) * (x["Lc"] - x["Ls"]), "sk": (Va + Vs) / x["y"]}


CASES = {
    PRE + "reservoir.havlena_odeh_material_balance": (mb, 1e-9), PRE + "reservoir.well_test_semilog_skin_wellbore_storage": (welltest, 1e-9), PRE + "reservoir.corey_relperm_fractional_flow": (corey, 1e-9),
    PRE + "reservoir.standing_pvt_papay_z_factor": (pvt, 1e-6), PRE + "production.weymouth_panhandle_gas_pipeline": (pipeline, 2e-3), PRE + "production.vogel_ipr_inflow_performance": (vogel, 1e-9),
    PRE + "production.esp_sizing_head_stages_power": (esp, 1e-9), PRE + "production.sneddon_fracture_width_length": (fracture, 1e-6), PRE + "drilling.bit_hydraulics_nozzle_ecd": (bit, 1e-9),
    PRE + "drilling.torque_drag_soft_string_tangent": (drag, 1e-9), PRE + "drilling.cement_slurry_volume_displacement": (cement, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_well_test_recovers_permeability_and_skin_from_the_line_source_solution():
    k0, s0 = 80 * MD, 5.0
    q, B, mu, h, phi, ct, rw, pi_ = 100 / DAY, 1.2, 1.5e-3, 15.0, 0.18, 1.5e-9, 0.1, 25e6
    pwf = lambda t: pi_ - q * B * mu / (4 * math.pi * k0 * h) * (special.exp1(rw ** 2 * phi * mu * ct / (4 * k0 * t)) + 2 * s0)    # line source with skin, exact
    t = 3600.0
    ms = pwf(t) - pwf(10 * t)                                                           # drop per log10 cycle between 1 and 10 hours
    r = solved(PRE + "reservoir.well_test_semilog_skin_wellbore_storage", pin=f"{pi_ / 1e6} MPa", p1=f"{pwf(t) / 1e6} MPa", ms=f"{ms / 1e6} MPa")
    assert r["k"] == pytest.approx(k0, rel=2e-3) and r["s"] == pytest.approx(s0, abs=0.02)


def test_benchmarks():
    m = solved(PRE + "reservoir.havlena_odeh_material_balance")
    assert m["DDI"] + m["SDI"] + m["CDI"] + m["WDI"] == pytest.approx(1.0, rel=1e-12)
    assert solved(PRE + "reservoir.corey_relperm_fractional_flow", Sw="80 %")["fw"] > solved(PRE + "reservoir.corey_relperm_fractional_flow")["fw"]
    assert solved(PRE + "reservoir.standing_pvt_papay_z_factor", p="0.1 MPa")["Z"] == pytest.approx(1.0, abs=0.01)           # low pressure: ideal gas
    assert solved(PRE + "production.vogel_ipr_inflow_performance", pw="0 MPa")["qw"] == pytest.approx(solved(PRE + "production.vogel_ipr_inflow_performance")["qm"])   # zero flowing pressure: q_max
    assert solved(PRE + "drilling.torque_drag_soft_string_tangent", al="0 deg")["Fd"] == pytest.approx(0, abs=1e-9)             # vertical hole: no drag
    s = solved(PRE + "production.sneddon_fracture_width_length")
    assert s["wa"] == pytest.approx(math.pi / 4 * s["wm"])


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "petroleum"
