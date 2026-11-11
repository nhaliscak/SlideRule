"""Thin sub-disciplines, part B: knowledge, usability, security, data, ecology, materials, robotics, sports (independent formulas, SI)."""

import math

import pytest
from pcutil import CAT, check_case, eps0, g, pi, solved


def tfidf(x):
    tf = x["ft"] / x["Ld"]
    idf = math.log(x["Nd"] / x["nt"])
    return {"tf": tf, "idf": idf, "tfidf": tf * idf, "bm": idf * x["ft"] * (x["k1"] + 1) / (x["ft"] + x["k1"] * (1 - x["bb"] + x["bb"] * x["Ld"] / x["La"]))}


def ent(a, b):
    t = a + b
    return -(a / t) * math.log2(a / t) - (b / t) * math.log2(b / t)


def infogain(x):
    tp, tl, tr = x["pp"] + x["np"], x["pl"] + x["nl"], x["pr"] + x["nr"]
    return {"tp": tp, "tl": tl, "tr": tr, "Hp": ent(x["pp"], x["np"]), "Hl": ent(x["pl"], x["nl"]), "Hr": ent(x["pr"], x["nr"]),
            "ig": ent(x["pp"], x["np"]) - tl / tp * ent(x["pl"], x["nl"]) - tr / tp * ent(x["pr"], x["nr"])}


def klm(x):
    return {"Tt": x["nK"] * x["tK"] + x["nP"] * x["tP"] + x["nH"] * x["tH"] + x["nM"] * x["tM"] + x["nB"] * x["tB"] + x["tR"]}


def discovery(x):
    f = 1 - (1 - x["lam"]) ** x["nu"]
    return {"fnd": f, "need": math.log(1 - x["tg"]) / math.log(1 - x["lam"]), "npf": x["Pt"] * f}


def cvss(x):
    iss = 1 - (1 - x["Ci"]) * (1 - x["Ii"]) * (1 - x["Ai"])
    imp, ex = 6.42 * iss, 8.22 * x["AV"] * x["AC"] * x["PR"] * x["UI"]
    return {"iss": iss, "imp": imp, "exp": ex, "bs": 0 if imp <= 0 else math.ceil(round(10 * min(imp + ex, 10), 9)) / 10}


def ioc(x):
    return {"Rt": 2 ** (-x["ag"] / x["th"]), "tmax": x["th"] * math.log2(1 / x["Rth"]), "Rm": 2 ** (-x["sp"] / x["th"])}


def alerts(x):
    tp, fp, p = x["tpr"], x["fpr"], x["pa"]
    ad = x["ne"] * (tp * p + fp * (1 - p))
    return {"prec": tp * p / (tp * p + fp * (1 - p)), "ad": ad, "fa": x["ne"] * fp * (1 - p), "hr": ad * x["tm"]}


def clv(x):
    year = 365.25 * 86400
    return {"clv": x["mg"] * year * (1 + x["dr"]) / (1 + x["dr"] - x["rt"]) / year * year / year * year, "lf": year / (1 - x["rt"]), "ch": 1 - x["rt"],
            "ratio": x["mg"] * year * (1 + x["dr"]) / (1 + x["dr"] - x["rt"]) / x["cac"]}


def abtest(x):
    n = (x["za"] + x["zb"]) ** 2 * (x["p1"] * (1 - x["p1"]) + x["p2"] * (1 - x["p2"])) / (x["p1"] - x["p2"]) ** 2
    return {"nn": n, "ntot": 2 * n, "dd": 2 * n / x["tf"]}


def replication(x):
    a, n = x["an"], x["nr"]
    Aa, Am = 1 - (1 - a) ** n, 3 * a**2 * (1 - a) + a**3
    Ty = 525600 * 60 / (365.25 * 86400)                  # min per year is dimensionless in SI
    return {"Aa": Aa, "Am": Am, "d1": (1 - a) * Ty, "da": (1 - Aa) * Ty, "dm": (1 - Am) * Ty, "ov": 1 if x["Rq"] + x["Wq"] > n else 0}


def btree(x):
    fo = math.floor(x["Pg"] * x["fl"] / x["kb"])
    ht = math.ceil(math.log(x["Nr"]) / math.log(fo))
    return {"fo": fo, "ht": ht, "lt": ht * x["tio"], "Si": x["Nr"] * x["kb"] / x["fl"]}


def etl(x):
    tp = x["th"] * x["nw"] * x["ep"]
    tl = x["Vd"] / tp * (1 + x["ov"])
    return {"tp": tp, "tl": tl, "fit": 1 if tl <= x["wn"] else 0, "mg": x["wn"] - tl}


def pruning(x):
    fs = x["kp"] / x["Np"] * x["fc"]
    Rd = x["Ts"] / x["cr"] * fs
    return {"fs": fs, "Rd": Rd, "tq": Rd / x["bw"], "sp": x["Np"] / (x["kp"] * x["fc"])}


def little(x):
    return {"Wl": x["Lq"] / x["lam"], "rho": x["lam"] / x["mu"], "Wm": 1 / (x["mu"] - x["lam"]), "Lm": x["lam"] / (x["mu"] - x["lam"])}


def window(x):
    Sr = x["Kk"] * x["rk"] * x["Tw"] * x["be"]
    n = x["Tw"] / x["Sl"]
    Sp = x["Kk"] * n * x["ba"]
    return {"Sr": Sr, "np": n, "Sp": Sp, "sv": Sr / Sp}


def raingarden(x):
    V_ = x["Cr"] * x["Ac"] * x["Ps"]
    sA = x["dp"] + x["nm"] * x["dm"] + x["ki"] * x["ts"]
    return {"Vr": V_, "sA": sA, "Ag": V_ / sA, "rA": V_ / sA / x["Ac"]}


def logistic(x):
    N0, K, r = x["N0"], x["Kc"], x["r"]
    return {"Nt": K / (1 + (K - N0) / N0 * math.exp(-r * x["tt"])), "tf": math.log(x["fk"] * (K - N0) / (N0 * (1 - x["fk"]))) / r, "rmax": r * K / 4}


def ipat(x):
    I1 = x["P1"] * x["A1"] * x["T1"]
    T2 = x["tr"] * x["T1"] / (x["gP"] * x["gA"])
    return {"I1": I1, "I2": x["gP"] * x["gA"] * I1, "T2": T2, "fx": x["T1"] / T2}


def mips(x):
    Mt = x["mabi"] + x["mbio"] + x["mero"] + x["mwat"]
    return {"Mt": Mt, "mips": Mt / x["nuse"], "dem": x["ref"] / (Mt / x["nuse"])}


def halpin(x):
    ne = (x["Ef"] / x["Em"] - 1) / (x["Ef"] / x["Em"] + x["xe"])
    ng = (x["Gf"] / x["Gm"] - 1) / (x["Gf"] / x["Gm"] + x["xg"])
    Vf = x["Vf"]
    return {"ne": ne, "ng": ng, "E2": x["Em"] * (1 + x["xe"] * ne * Vf) / (1 - ne * Vf), "G12": x["Gm"] * (1 + x["xg"] * ng * Vf) / (1 - ng * Vf), "E2l": 1 / (Vf / x["Ef"] + (1 - Vf) / x["Em"])}


def kelly(x):
    lc = x["sf"] * x["df"] / (2 * x["ti"])
    L, Vf = x["Lf"], x["Vf"]
    sc = Vf * x["sf"] * (1 - lc / (2 * L)) + (1 - Vf) * x["sm"] if L >= lc else Vf * x["ti"] * L / x["df"] + (1 - Vf) * x["sm"]
    return {"lc": lc, "rl": L / lc, "sc": sc}


def fourpoint(x):
    Rs = x["cf"] * pi / math.log(2) * x["Vm"] / x["Im"]
    return {"Rs": Rs, "rho": Rs * x["tf"], "sg": 1 / (Rs * x["tf"])}


def dielectric(x):
    C_ = eps0 * x["er"] * x["Ap"] / x["dd"]
    w = 2 * pi * x["fr"]
    return {"Cp": C_, "Pl": w * C_ * x["Vr"] ** 2 * x["td"], "ESR": x["td"] / (w * C_), "Qf": 1 / x["td"]}


def carbon(x):
    CE = x["Cc"] + x["Mn"] / 6 + (x["Cr"] + x["Mo"] + x["Va"]) / 5 + (x["Ni"] + x["Cu"]) / 15
    Pcm = x["Cc"] + x["Si"] / 30 + (x["Mn"] + x["Cu"] + x["Cr"]) / 20 + x["Ni"] / 60 + x["Mo"] / 15 + x["Va"] / 10 + 5 * x["Bo"]
    return {"CE": CE, "Pcm": Pcm, "pre": 0 if CE < 0.004 else 1 if CE < 0.005 else 2}


def fillet(x):
    th = x["a"] / math.sqrt(2)
    qw = th * x["ta"]
    return {"th": th, "qw": qw, "Fc": x["ns"] * qw * x["Lw"], "Lr": x["Fl"] / (x["ns"] * qw)}


def trapezoid(x):
    vp = min(x["vm"], math.sqrt(x["D"] * x["am"]))
    ta = vp / x["am"]
    tc = x["D"] / vp - vp / x["am"]
    return {"vp": vp, "ta": ta, "tc": tc, "tt": 2 * ta + tc}


def servo(x):
    tm = x["tL"] / (x["Nr"] * x["eg"]) + (x["Jm"] + x["JL"] / x["Nr"] ** 2) * x["Nr"] * x["aL"]
    wm = x["Nr"] * x["wL"]
    return {"wm": wm, "tm": tm, "Pm": tm * wm, "ir": x["JL"] / (x["Nr"] ** 2 * x["Jm"]), "Nopt": math.sqrt(x["JL"] / x["Jm"])}


def cycling(x):
    th = math.atan(x["gr"])
    Pr = x["Crr"] * x["mt"] * g * x["v"] * math.cos(th)
    Pa = x["rho"] * x["CdA"] * x["v"] ** 3 / 2
    Pg = x["mt"] * g * x["v"] * math.sin(th)
    return {"Pr": Pr, "Pa": Pa, "Pg": Pg, "Pw": Pr + Pa + Pg, "Pc": (Pr + Pa + Pg) / x["et"]}


def jump(x):
    v = (x["Fa"] - x["mb"] * g) * x["tp"] / x["mb"]
    return {"vt": v, "hj": v * v / (2 * g), "tf": 2 * v / g, "Pm": x["mb"] * v * v / (2 * x["tp"])}


CASES = {
    "computer.knowledge.tf_idf_bm25": tfidf, "computer.knowledge.information_gain_split": infogain, "computer.usability.klm_task_time": klm, "computer.usability.problem_discovery": discovery,
    "computer.security.cvss_base_score": cvss, "computer.security.ioc_decay_relevance": ioc, "computer.security.alert_precision_base_rate": alerts,
    "data.bi.customer_lifetime_value": clv, "data.bi.ab_test_sample_size": abtest, "data.architecture.replication_availability": replication, "data.architecture.btree_index_cost": btree,
    "data.warehouse.etl_load_window": etl, "data.warehouse.partition_pruning_scan": pruning, "data.streaming.littles_law_queue": little, "data.streaming.window_state_size": window,
    "environmental.ecological.rain_garden_sizing": raingarden, "environmental.ecological.logistic_restoration_growth": logistic, "green.industrial_ecology.ipat_factor_x": ipat,
    "green.industrial_ecology.material_intensity_mips": mips, "materials.composites.halpin_tsai_moduli": halpin, "materials.composites.kelly_tyson_short_fibre": kelly,
    "materials.electronic.four_point_probe": fourpoint, "materials.electronic.dielectric_loss_capacitor": dielectric, "materials.welding.carbon_equivalent": carbon,
    "materials.welding.fillet_weld_capacity": fillet, "mechanical.robotics.trapezoidal_motion_profile": trapezoid, "mechanical.robotics.servo_gearbox_sizing": servo,
    "mechanical.sports.cycling_power": cycling, "mechanical.sports.vertical_jump_impulse": jump,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


def test_benchmarks_and_identities():
    assert solved("computer.security.cvss_base_score")["bs"] == pytest.approx(9.8)                                        # the specification's textbook case
    assert solved("computer.security.cvss_base_score", Ci="0 1", Ii="0 1", Ai="0 1")["bs"] == 0
    assert solved("computer.usability.problem_discovery", nu="5")["fnd"] == pytest.approx(0.8436, abs=1e-3)                # Nielsen: five users find about 85 %
    assert solved("data.bi.customer_lifetime_value")["ratio"] == pytest.approx(4.4)
    assert solved("data.streaming.littles_law_queue")["Wl"] == pytest.approx(0.05)
    assert solved("data.architecture.replication_availability", Rq="1", Wq="1")["ov"] == 0
    assert solved("materials.electronic.four_point_probe")["Rs"] == pytest.approx(4.532 * 4.2, rel=1e-3)                   # pi/ln2 = 4.532
    assert solved("mechanical.robotics.trapezoidal_motion_profile", D="0.1 m")["tc"] == pytest.approx(0, abs=1e-9)            # too short to reach the speed limit
    assert solved("materials.composites.halpin_tsai_moduli", Vf="0 %")["E2"] == pytest.approx(3.5e9)                      # all matrix
    assert solved("materials.composites.halpin_tsai_moduli")["E2"] > solved("materials.composites.halpin_tsai_moduli")["E2l"]
    assert solved("mechanical.sports.vertical_jump_impulse", Fa="1500 N")["hj"] * 100 == pytest.approx(47.7, abs=0.1)
    assert solved("computer.knowledge.information_gain_split", pp="8", np="8", pl="7", nl="1", pr="1", nr="7")["ig"] == pytest.approx(1 - ent(7, 1))


def test_catalogued_under_the_thin_sub_disciplines():
    for cid in CASES:
        assert CAT.get(cid).subdisciplines and CAT.get(cid).references
