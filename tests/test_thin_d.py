"""Thin sub-disciplines, part D: one calculation each for fifty sub-disciplines (independent formulas, SI)."""

import math

import pytest
from pcutil import CAT, check_case, pi, solved

from sliderule.units import parse_unit

MONTH = parse_unit("month").to_si(1)
EULER = 0.5772156649
FARADAY = 96485.33212
C0 = 299792458.0
G = 9.80665


def iou(x):
    ix = min(x["ax2"], x["bx2"]) - max(x["ax1"], x["bx1"])
    iy = min(x["ay2"], x["by2"]) - max(x["ay1"], x["by1"])
    ai = max(ix, 0) * max(iy, 0)
    au = (x["ax2"] - x["ax1"]) * (x["ay2"] - x["ay1"]) + (x["bx2"] - x["bx1"]) * (x["by2"] - x["by1"]) - ai
    pr, rc = x["TP"] / (x["TP"] + x["FP"]), x["TP"] / (x["TP"] + x["FN"])
    return {"ix": ix, "iy": iy, "Ai": ai, "Au": au, "iou": ai / au, "pr": pr, "rc": rc, "f1": 2 * pr * rc / (pr + rc)}


def lr_sched(x):
    t = x["st"]
    if t < x["tw"]:
        lr = x["lmax"] * t / x["tw"]
    else:
        lr = x["lmin"] + (x["lmax"] - x["lmin"]) / 2 * (1 + math.cos(pi * (t - x["tw"]) / (x["Tt"] - x["tw"])))
    return {"lr": lr, "lsc": x["lmax"] * x["Bn"] / x["Bb"]}


def llm(x):
    tps = x["ef"] * x["Bw"] * x["Bs"] / (x["Np"] * x["bp"])
    return {"tps": tps, "cm": x["pr"] * 1e6 / (tps * x["ug"]), "mc": x["pr"] * x["ng"] * 730 * 3600 / MONTH}


def bleu(x):
    bp = 1 if x["cl"] > x["rl"] else math.exp(1 - x["rl"] / x["cl"])
    return {"bp": bp, "bl": bp * (x["p1"] * x["p2"] * x["p3"] * x["p4"]) ** 0.25}


def lander(x):
    cd = x["Nr"] * x["Lr"] / x["Gs"]
    return {"cd": cd, "fc": 1 - math.exp(-cd), "un": x["Gs"] * math.exp(-cd), "Nt": -x["Gs"] * math.log(1 - x["tg"]) / x["Lr"]}


def resorb(x):
    # rate constants are per second in SI, so the time is in seconds too
    return {"mt": x["m0"] * math.exp(-x["km"] * x["tt"]), "st": x["s0"] * math.exp(-x["ks"] * x["tt"]), "th": math.log(2) / x["km"], "tl": math.log(x["s0"] / x["sr"]) / x["ks"]}


def prosthesis(x):
    es = (x["Pm"] / x["et"] + x["Pa"]) * x["Ts"]
    return {"Es": es, "ns": x["Eb"] / es, "Dc": x["Eb"] / es * x["Ls"], "mb": x["nd"] * es / x["se"]}


def pcr(x):
    return {"Nn": x["N0"] * (1 + x["Ef"]) ** x["nc"], "fa": (1 + x["Ef"]) ** x["nc"], "ct": math.log(x["Nt"] / x["N0"]) / math.log(1 + x["Ef"])}


def mri(x):
    sa = x["Ma"] * (1 - math.exp(-x["TR"] / x["T1a"])) * math.exp(-x["TE"] / x["T2a"])
    sb = x["Mb"] * (1 - math.exp(-x["TR"] / x["T1b"])) * math.exp(-x["TE"] / x["T2b"])
    return {"Sa": sa, "Sb": sb, "cn": (sa - sb) / (sa + sb), "fL": 42.577478e6 * x["B0"]}


def cable(x):
    ld = math.sqrt(x["Rm"] * x["dn"] / (4 * x["Ri"]))
    vx = x["V0"] * math.exp(-x["xd"] / ld)
    return {"ld": ld, "tm": x["Rm"] * x["Cm"], "Vx": vx, "at": 1 - vx / x["V0"]}


def cells(x):
    return {"Nc": x["N0"] * 2 ** (x["tc"] / x["td"]), "tn": x["td"] * math.log2(x["Nt"] / x["N0"]), "np": math.log(x["Nt"] / x["N0"]) / math.log(x["sr"])}


def fuel_cell(x):
    f = x["Is"] * x["Nc"]
    return {"mh": x["lh"] * f * 2.016e-3 / (2 * FARADAY), "ma": x["la"] * f * 28.97e-3 / (4 * FARADAY * 0.2095), "mw": f * 18.015e-3 / (2 * FARADAY)}


def md(x):
    tv = 1 / (C0 * x["nu"])
    dt = tv / x["fs"]
    wt = 1e-9 / dt * x["Na"] * x["ca"] / x["nco"]
    return {"Tv": tv, "dt": dt, "sn": 1e-9 / dt, "wt": wt, "pf": 1e-9 / wt}


def extruder(x):
    qd = pi**2 * x["Dm"] ** 2 * (x["Ns"] / (2 * pi)) * x["hc"] * math.sin(x["ph"]) * math.cos(x["ph"]) / 2     # N in rev/s
    qn = qd * (1 - x["lf"])
    return {"Qd": qd, "Qn": qn, "Mt": qn * x["rm"]}


def maturity(x):
    mt = sum(x[k] - x["T0"] for k in ("T1", "T2", "T3", "T4")) * x["dt"]
    return {"Mt": mt, "te": mt / (x["Tr"] - x["T0"])}


def spectrum(x):
    eta = max(math.sqrt(0.10 / (0.05 + x["xi"])), 0.55)
    a, s, tp = x["ag"], x["Sf"], x["Tp"]
    if tp < x["TB"]:
        se = a * s * (1 + tp / x["TB"] * (2.5 * eta - 1))
    elif tp < x["TC"]:
        se = 2.5 * a * s * eta
    elif tp < x["TD"]:
        se = 2.5 * a * s * eta * x["TC"] / tp
    else:
        se = 2.5 * a * s * eta * x["TC"] * x["TD"] / tp**2
    return {"eta": eta, "Se": se, "Sg": se / G}


def cooper_jacob(x):
    u = x["rd"] ** 2 * x["Ss"] / (4 * x["Tr"] * x["tp"])
    return {"uu": u, "sd": x["Qp"] / (4 * pi * x["Tr"]) * (-EULER - math.log(u))}


def braking(x):
    ae = x["ab"] + G * x["Gr"]
    sb = x["v"] ** 2 / (2 * ae)
    return {"ae": ae, "sb": sb, "St": x["v"] * x["td"] + sb, "tt": x["td"] + x["v"] / ae}


def mpm(x):
    th = x["rw"] * x["hf"] * x["Sb"] / ((x["rs"] - x["rw"]) * x["dg"])
    q = 8 * (th - 0.047) ** 1.5 if th > 0.047 else 0.0
    qb = q * math.sqrt((x["rs"] / x["rw"] - 1) * G * x["dg"] ** 3)
    return {"th": th, "qs": q, "qb": qb, "mb": x["rs"] * qb}


def fragility(x):
    pd = 0.5 * (1 + math.erf(math.log(x["im"] / x["md"]) / (x["be"] * math.sqrt(2))))
    return {"Pd": pd, "El": pd * x["Lr"] * x["Vb"]}


def cloud(x):
    hm = 730 * 3600 / MONTH
    co, cr = x["od"] * hm * x["ut"], x["rs"] * hm
    return {"be": x["rs"] / x["od"], "co": co, "cr": cr, "se": x["sp"] * (1 + x["pq"] * x["rw"]), "sv": 1 - cr / co}


def rosi(x):
    aa = x["al"] * (1 - x["mt"])
    rr = x["al"] - aa
    return {"aa": aa, "rr": rr, "ro": (rr - x["cs"]) / x["cs"], "pb": x["ci"] / (rr - x["cs"])}


def slack(x):
    # sizes are held in bits by the engine; whole clusters are counted in bytes
    ac = math.ceil(x["fz"] / x["cl"]) * x["cl"]
    sx = x["cl"] / 2
    return {"ac": ac, "sl": ac - x["fz"], "sx": sx, "sw": x["Nf"] * sx, "ef": x["ms"] / (x["ms"] + sx)}


def bucket(x):
    adm = min(x["lm"] * x["Tw"], x["bk"] + x["rt"] * x["Tw"])
    return {"ad": adm, "te": x["bk"] / (x["lm"] - x["rt"]), "tf": x["bk"] / x["rt"], "dp": 1 - x["rt"] / x["lm"]}


def fuzz(x):
    nc = math.log(1 - x["cf"]) / math.log(1 - x["pb"])
    return {"Pn": 1 - (1 - x["pb"]) ** x["ne"], "nc": nc, "tc": nc / x["rx"], "tm": 1 / (x["pb"] * x["rx"])}


def geo(x):
    re, h = 6378.137e3, 35786e3
    ga = math.acos(math.cos(x["la"]) * math.cos(x["dl"]))
    d = math.sqrt(re**2 + (re + h) ** 2 - 2 * re * (re + h) * math.cos(ga))
    el = math.atan((math.cos(ga) - re / (re + h)) / math.sin(ga))
    return {"ga": ga, "dd": d, "el": el, "t1": d / C0, "t2": 2 * d / C0}


def weibull(x):
    c, k = x["cw"], x["kw"]
    return {"vm": c * math.gamma(1 + 1 / k), "pd": 0.5 * x["rho"] * c**3 * math.gamma(1 + 3 / k), "fo": math.exp(-((x["vi"] / c) ** k)) - math.exp(-((x["vo"] / c) ** k))}


def loop(x):
    r = x["Rc"]
    return {"vs": 1 - r, "Vv": x["Dm"] * (1 - r), "sn": sum(r**i for i in range(int(x["nc"]))), "sl": 1 / (1 - r), "n9": math.log(0.1) / math.log(r)}


def gwp(x):
    e2, e3, e4 = x["m2"] * x["g2"], x["m3"] * x["g3"], x["m4"] * x["g4"]
    tot = x["m1"] + e2 + e3 + e4
    return {"e1": x["m1"], "e2": e2, "e3": e3, "e4": e4, "et": tot, "sh": (tot - x["m1"]) / tot}


def telemed(x):
    tp = x["dk"] * x["nf"] / C0
    ts = x["ps"] / x["lr"]
    to = tp + ts + x["nh"] * x["th"] + x["tc"] + x["tj"]
    return {"tp": tp, "ts": ts, "to": to, "rt": 2 * to, "ok": 1 if to <= x["lg"] else 0}


def murrell(x):
    s, er = 5 * 4186.8 / 60, 1.5 * 4186.8 / 60
    ra = 0 if x["Ew"] <= s else (x["Ew"] - s) / (x["Ew"] - er)
    return {"ra": ra, "rt": x["Tw"] * ra / (1 - ra), "hp": ra * 3600}


def tribology(x):
    lam = x["hm"] / math.sqrt(x["r1"] ** 2 + x["r2"] ** 2)
    pr = x["Wl"] / (x["Db"] * x["Lb"])
    n_rev = x["Nr"] / (2 * pi)
    return {"lm": lam, "rg": 1 if lam < 1 else 2 if lam < 3 else 3, "pr": pr, "So": (x["Db"] / (2 * x["cr"])) ** 2 * x["mu"] * n_rev / pr}


def ittc(x):
    re = x["v"] * x["Lw"] / x["nu"]
    cf = 0.075 / (math.log10(re) - 2) ** 2
    rf = 0.5 * x["rho"] * x["Sw"] * cf * x["v"] ** 2
    return {"Re": re, "Cf": cf, "Rf": rf, "Pe": rf * x["v"], "Fn": x["v"] / math.sqrt(G * x["Lw"])}


def lens(x):
    dc = (x["am"] - x["al"]) * x["Dl"] * x["dT"] / 2
    return {"dc": dc, "c1": x["c0r"] + dc, "ok": 1 if x["c0r"] + dc > 0 else 0}


def plant(x):
    qf = x["Pn"] / x["et"]
    mf = qf / x["LH"]
    me = qf * x["ef"]
    return {"hr": 1 / x["et"], "Qf": qf, "mf": mf, "me": me, "ei": me / x["Pn"]}


def cold_room(x):
    v = x["Lr"] * x["Wr"] * x["Hr"]
    qt = x["U"] * 2 * (x["Lr"] * x["Wr"] + x["Lr"] * x["Hr"] + x["Wr"] * x["Hr"]) * x["dT"]
    qp = x["mp"] * x["cp"] * x["dTp"]
    qa = x["ac"] * v * 1.2 * x["dh"]
    ql = qt + qp + qa + x["Qi"]
    return {"Qt": qt, "Qp": qp, "Qa": qa, "Ql": ql, "Qc": ql * 86400 / x["tr"]}


def mine_air(x):
    return {"Qa": x["Ph"] / (x["ra"] * x["cp"] * x["dT"]), "Ta": G * x["Dz"] / x["cp"]}


def spr(x):
    kd = x["koff"] / x["kon"]
    re = x["Rx"] * x["Ca"] / (kd + x["Ca"])
    ko = x["kon"] * x["Ca"] + x["koff"]
    rt = re * (1 - math.exp(-ko * x["ta"]))
    return {"KD": kd, "Re": re, "ko": ko, "Rt": rt, "t95": math.log(20) / ko, "Rd": rt * math.exp(-x["koff"] * x["td"])}


def teed(x):
    ip = x["Vs"] / x["Zs"]
    te = x["Vs"] ** 2 / x["Zs"] * x["pw"] * x["fs"]
    pb = te / x["ic"] + x["Ph"]
    return {"Ip": ip, "Qp": ip * x["pw"], "TE": te, "Pb": pb, "Ly": x["Eb"] / pb}


def greenwood(x):
    xp = 1 - x["di"] / x["Lc"]
    xt = math.log10(x["ft"] / 165.4 + 0.88) / 2.1
    return {"xp": xp, "fc": 165.4 * (10 ** (2.1 * xp) - 0.88), "xt": xt, "dt": (1 - xt) * x["Lc"]}


def migration(x):
    va = x["Kh"] * x["ig"] / x["pn"]
    rf = 1 + x["rb"] * x["Kd"] / x["pn"]
    vc = va / rf
    tt = x["Lp"] / vc
    return {"va": va, "Rf": rf, "vc": vc, "tt": tt, "fs": math.exp(-math.log(2) * tt / x["th"])}


def decoherence(x):
    tp = 1 / (1 / x["T2"] - 1 / (2 * x["T1"]))
    er = x["tg"] / (3 * x["T1"]) + x["tg"] / (3 * tp)
    return {"Tp": tp, "er": er, "nd": math.log(1 / x["Ft"]) / er}


def magnetometer(x):
    et = 1 / (1.76085963e11 * x["Cn"] * math.sqrt(x["Ns"] * x["Ts"]))
    return {"et": et, "dB": et / math.sqrt(x["Tm"])}


def beacons(x):
    ta = x["Sb"] / x["br"] + x["tpr"]
    cb = x["Nv"] * x["fb"] * ta
    return {"ta": ta, "cb": cb, "Nm": x["cl"] / (x["fb"] * ta), "ok": 1 if cb <= x["cl"] else 0}


def aoi(x):
    rho = x["lm"] / x["mu"]
    return {"Ap": x["Tu"] / 2 + x["dl"], "Pk": x["Tu"] + x["dl"], "rho": rho, "Am": (1 + 1 / rho + rho**2 / (1 - rho)) / x["mu"]}


def kappa(x):
    gf = (1 + x["kp"] * x["rh"] / (1 - x["rh"])) ** (1 / 3)
    return {"gf": gf, "pd": x["pm"] / gf**3}


def spo2(x):
    r = (x["acr"] / x["dcr"]) / (x["aci"] / x["dci"])
    return {"Rr": r, "sp": (110 - 25 * r) / 100, "pf": x["aci"] / x["dci"]}


def entry(x):
    am = x["ve"] ** 2 * math.sin(x["ga"]) / (2 * math.e * x["Hs"])
    return {"am": am, "ag": am / G, "hp": x["Hs"] * math.log(x["r0"] * x["Hs"] / (x["be"] * math.sin(x["ga"]))), "vp": x["ve"] * math.exp(-0.5)}


def crispr(x):
    pd = 1 - math.exp(-x["lg"])
    pe = pd * x["ee"]
    return {"pd": pd, "pe": pe, "pb": pe**2, "nc": math.log(1 - x["cf"]) / math.log(1 - pe**2)}


def escalation(x):
    cu = x["c0"] * x["kf"] ** x["nl"]
    ct = x["Nd"] * cu
    ce = x["Nd"] * ((1 - x["sh"]) * cu + x["sh"] * x["c0"] * x["kf"] ** (x["nl"] - x["ne"]))
    return {"cu": cu, "ct": ct, "ce": ce, "sv": ct - ce}


CASES = {
    "computer.ai.detection_iou_f1": iou, "computer.ai.lr_schedule_warmup_cosine": lr_sched, "computer.ai.llm_serving_cost_per_token": llm, "computer.ai.bleu_score": bleu,
    "biomedical.bioinformatics.lander_waterman_coverage": lander, "biomedical.biomaterials.resorbable_implant_degradation": resorb, "biomedical.biomechatronics.prosthetic_joint_energy": prosthesis,
    "biomedical.biomolecular.pcr_amplification": pcr, "biomedical.imaging.mri_spin_echo_contrast": mri, "biomedical.neural.cable_length_constant": cable, "biomedical.tissue.cell_expansion_doubling": cells,
    "chemical.fuel_cell.reactant_consumption": fuel_cell, "chemical.molecular.md_timestep_cost": md, "chemical.polymer.extruder_drag_flow": extruder,
    "civil.construction.concrete_maturity": maturity, "civil.earthquake.elastic_response_spectrum": spectrum, "civil.groundwater.cooper_jacob_drawdown": cooper_jacob,
    "civil.railway.braking_distance": braking, "civil.river.meyer_peter_muller_bedload": mpm, "climate.resilience.lognormal_fragility": fragility,
    "computer.cloud.reserved_vs_ondemand_breakeven": cloud, "computer.security.rosi_security_investment": rosi, "computer.forensics.slack_space_waste": slack,
    "computer.security.token_bucket_rate_limit": bucket, "computer.security.fuzzing_bug_discovery": fuzz, "electrical.satellite.geo_slant_range_delay": geo,
    "energy.wind.weibull_resource": weibull, "green.circular_economy.closed_loop_recycling": loop, "green.lca.gwp_co2_equivalent": gwp,
    "healthinfo.telemedicine.latency_budget": telemed, "industrial.ergonomics.energy_rest_allowance": murrell, "materials.tribology.lambda_ratio_sommerfeld": tribology,
    "mechanical.marine.ittc_friction_resistance": ittc, "mechanical.optomechanical.lens_mount_thermal_clearance": lens, "mechanical.power_plant.heat_rate_fuel_co2": plant,
    "mechanical.refrigeration.cold_room_load": cold_room, "mining.ventilation.heat_load_airflow": mine_air, "nanotech.nanobiosensors.spr_binding_kinetics": spr,
    "neuro.neuromodulation.teed_dbs_battery": teed, "neuro.neuroprosthetics.greenwood_place_frequency": greenwood, "nuclear.waste.retardation_travel_time": migration,
    "quantum.computing.decoherence_gate_error": decoherence, "quantum.sensing.spin_magnetometer_sensitivity": magnetometer, "smartcities.connected_vehicles.beacon_channel_load": beacons,
    "smartcities.digital_twin.age_of_information": aoi, "smartcities.urban_sensing.pm_humidity_correction": kappa, "softrobotics.wearables.spo2_ratio_of_ratios": spo2,
    "space.planetary.allen_eggers_entry": entry, "synbio.crispr.editing_clone_screening": crispr, "systems.requirements.change_cost_escalation": escalation,
}


def test_there_are_fifty_cases():
    assert len(CASES) == 50


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


def test_benchmarks_and_identities():
    assert solved("computer.ai.detection_iou_f1", bx1="10", by1="20", bx2="110", by2="120")["iou"] == pytest.approx(1)                 # identical boxes
    assert solved("computer.ai.detection_iou_f1", bx1="500", by1="500", bx2="600", by2="600")["iou"] == 0                                # disjoint boxes
    assert solved("computer.ai.bleu_score", p1="100 %", p2="100 %", p3="100 %", p4="100 %", cl="1000", rl="1000")["bl"] == pytest.approx(1)  # a perfect match
    assert solved("biomedical.biomolecular.pcr_amplification", Ef="100 %", nc="10")["fa"] == pytest.approx(1024)                          # perfect doubling
    assert solved("biomedical.imaging.mri_spin_echo_contrast", B0="1.5 T")["fL"] / 1e6 == pytest.approx(63.87, abs=0.01)                  # protons at 1.5 T
    assert solved("climate.resilience.lognormal_fragility", im="0.45")["Pd"] == pytest.approx(0.5)                                         # at the median capacity
    assert solved("energy.wind.weibull_resource", kw="2", cw="8 m/s")["vm"] == pytest.approx(8 * math.sqrt(pi) / 2)                        # Rayleigh mean
    assert solved("green.circular_economy.closed_loop_recycling", Rc="50 %")["sl"] == pytest.approx(2)
    assert solved("mechanical.power_plant.heat_rate_fuel_co2", et="100 %")["hr"] == pytest.approx(1)                                       # all the fuel energy delivered: 3600 kJ/kWh, i.e. 1 in SI
    near = solved("electrical.satellite.geo_slant_range_delay", la="0.001 deg", dl="0.001 deg")                                             # almost at the sub-satellite point
    assert near["dd"] == pytest.approx(35786e3, rel=1e-6) and near["el"] == pytest.approx(pi / 2, abs=1e-3)
    assert solved("civil.groundwater.cooper_jacob_drawdown")["uu"] < 0.05
    assert solved("quantum.computing.decoherence_gate_error", T1="100 us", T2="100 us")["Tp"] == pytest.approx(200e-6)                         # T2 = T1: 1/Tphi = 1/(2 T1)
    assert solved("smartcities.digital_twin.age_of_information", lm="0.05 1/s", mu="1 1/s")["Am"] == pytest.approx(1 + 20 + 0.0025 / 0.95, rel=0.02)
    assert solved("neuro.neuroprosthetics.greenwood_place_frequency", di="0 mm")["fc"] == pytest.approx(165.4 * (10**2.1 - 0.88))        # base of the cochlea: about 20 kHz


def test_catalogued_under_the_thin_sub_disciplines():
    for cid in CASES:
        assert CAT.get(cid).subdisciplines and CAT.get(cid).references
