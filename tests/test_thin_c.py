"""Thin sub-disciplines, part C: metamaterials, nanomedicine, neuro, quantum communication, robotics, smart cities, soft robotics, space debris (independent formulas, SI)."""

import math

import pytest
from pcutil import CAT, NA, R, check_case, eps0, g, kB, mu0, pi, solved

mu_e = 3.986004418e14
Re = 6.371e6


def holo_res(x):
    dl = 1.22 * x["lam"] * x["zd"] / x["Dh"]
    return {"dl": dl, "th": math.asin(x["lam"] / x["Lf"]), "Np": x["Dh"] / dl}


def holo_cap(x):
    Ct = x["Vm"] * x["nr"] ** 3 / x["lam"] ** 3
    Cp = x["Mp"] * x["Px"] * x["bp"] * x["cr"]
    return {"Ct": Ct, "Cp": Cp, "ef": Cp / Ct}


def garnett(x):
    eh, ei, f = x["eh"], x["ei"], x["fv"]
    ee = eh * (ei + 2 * eh + 2 * f * (ei - eh)) / (ei + 2 * eh - f * (ei - eh))
    return {"ee": ee, "ne": math.sqrt(ee)}


def veselago(x):
    return {"t2": math.asin(x["n1"] * math.sin(x["t1"]) / x["n2"]), "vz": x["ds"] - x["us"], "vi": x["ds"] - (x["ds"] - x["us"])}


def capsules(x):
    nv = 6 * x["vf"] / (pi * x["dc"] ** 3)
    N = nv * x["Ac"] * x["dc"]
    Va = N * x["cf"] * pi * x["dc"] ** 3 / 6
    return {"nv": nv, "Nr": N, "Va": Va, "Vk": x["Ac"] * x["wo"], "hf": Va / (x["Ac"] * x["wo"])}


def healing(x):
    sf = math.exp(x["Ea"] / R * (1 / x["Tr"] - 1 / x["Th"]))
    th = x["tr"] / sf
    return {"sf": sf, "th": th, "kr": -math.log(1 - x["hg"]) / th}


def kp(x):
    t = x["tt"] / 3600
    return {"Ml": x["kk"] * t ** x["nx"], "t50": 3600 * (1 / (2 * x["kk"])) ** (1 / x["nx"]), "mech": 1 if x["nx"] <= 0.43 else 2 if x["nx"] < 0.85 else 3,
            "Qh": math.sqrt(x["Dd"] * (2 * x["Ad"] - x["cs"]) * x["cs"] * x["tt"])}


def loading(x):
    LC = x["mdl"] / x["mp"]
    mpp = x["rp"] * pi * x["dp"] ** 3 / 6
    return {"LC": LC, "EE": x["mdl"] / x["md0"], "mpp": mpp, "Nd": LC * mpp / x["Md"] * NA, "Np": x["Dm"] / (LC * mpp)}


def erp(x):
    S1 = x["As"] / x["sn"]
    Nn = (x["St"] / S1) ** 2
    return {"S1": S1, "SN": S1 * math.sqrt(x["Nt"]), "dB": 10 * math.log10(x["Nt"]), "Nn": Nn, "Tr": Nn * (x["tr"] + x["iti"])}


def electrode(x):
    Vj = math.sqrt(4 * kB * x["Tb"] * x["Re"] * x["Bw"])
    Va = x["en"] * math.sqrt(x["Bw"])
    Vt = math.hypot(Vj, Va)
    return {"Vj": Vj, "Va": Va, "Vt": Vt, "snr": x["Vs"] / Vt}


def synaptic(x):
    sops = x["Nn"] * x["fo"] * x["fr"]
    Pd = sops * x["Es"]
    return {"sops": sops, "Pd": Pd, "Pt": Pd + x["Ps"], "Ei": (Pd + x["Ps"]) * x["ti"]}


def crossbar(x):
    P = (x["g11"] + x["g12"]) * x["v1"] ** 2 + (x["g21"] + x["g22"]) * x["v2"] ** 2 + (x["g31"] + x["g32"]) * x["v3"] ** 2
    return {"i1": x["g11"] * x["v1"] + x["g21"] * x["v2"] + x["g31"] * x["v3"], "i2": x["g12"] * x["v1"] + x["g22"] * x["v2"] + x["g32"] * x["v3"], "Pa": P, "Em": P * x["tp"] / 6}


def plob(x):
    eta = 10 ** (-x["al"] * x["Lk"] / 10)
    Cb = -math.log2(1 - eta)
    return {"etr": eta, "Cb": Cb, "Rb": Cb * x["fr"], "Rd": eta * x["fr"] / 2}


def h2(p):
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def qber(x):
    Q = x["Y0"] + x["etr"] * x["mu"]
    e = (x["Y0"] / 2 + x["ed"] * x["etr"] * x["mu"]) / Q
    return {"Qd": Q, "qb": e, "h2": h2(e), "rk": 1 - 2 * h2(e)}


def contact(x):
    mu = 1 / (1 / x["mh"] + 1 / x["mr"])
    F = x["v"] * math.sqrt(x["ks"] * mu)
    p = F / x["Ac"]
    return {"mu": mu, "Fc": F, "pc": p, "va": min(x["Fl"], x["pl"] * x["Ac"]) / math.sqrt(x["ks"] * mu), "ok": 1 if F <= x["Fl"] and p <= x["pl"] else 0}


def shared(x):
    Cp = max(x["Th"], x["Tr"]) + 2 * x["th"]
    Cs = x["Th"] + x["Tr"]
    return {"Cp": Cp, "Cs": Cs, "ih": (Cp - x["Th"]) / Cp, "ir": (Cp - x["Tr"]) / Cp, "pr": 1 / Cp, "gn": Cs / Cp - 1}


def cleaning(x):
    cv = x["v"] * x["wb"] * (1 - x["ov"]) * x["ef"]
    rt = x["Eb"] / x["Pr"]
    return {"cv": cv, "tc": x["Ar"] / cv, "rt": rt, "Ac": cv * rt}


def delivery(x):
    Ft = x["Crr"] * x["mt"] * g + x["rho"] * x["CdA"] * x["v"] ** 2 / 2
    Pm = Ft * x["v"] / x["et"] + x["Pa"]
    ek = Pm / x["v"]
    return {"Ft": Ft, "Pm": Pm, "ek": ek, "Rg": x["Eb"] / ek, "rt": x["Eb"] / Pm}


def swarm(x):
    N, A, r = x["Nr"], x["Aw"], x["rc"]
    rg = math.sqrt(math.log(N) * A / (pi * N))
    return {"kd": N * pi * r**2 / A, "rp": math.sqrt(4.512 * A / (pi * N)), "rg": rg, "cn": 1 if r >= rg else 0}


def consensus(x):
    N, ep = x["Na"], x["ep"]
    l2r = 2 * (1 - math.cos(2 * pi / N))
    L = math.log(1 / x["tl"])
    return {"l2r": l2r, "l2c": N, "tr": L / (ep * l2r) * x["dt"], "tf": L / (ep * N) * x["dt"], "sl": N / l2r}


def webster(x):
    Ls = x["np"] * x["tl"]
    Y = x["y1"] + x["y2"]
    Co = (1.5 * Ls + 5) / (1 - Y)
    return {"Ls": Ls, "Yt": Y, "Co": Co, "g1": x["y1"] / Y * (Co - Ls), "g2": x["y2"] / Y * (Co - Ls)}


def water(x):
    rl = x["Vin"] - x["Vb"] - x["Vu"] - x["Va"]
    ua = (18e-3 / 1e3 / 86400 * x["Lm"] + 0.8e-3 / 86400 * x["Nc"] + 25e-3 / 1e3 / 86400 * x["Lp"]) * x["Pm"]   # (L/(km d m)) -> m^3/s per metre of head
    return {"nrw": (x["Vin"] - x["Vb"]) / x["Vin"], "rl": rl, "lc": rl / x["Nc"], "ua": ua, "ili": rl / ua}


def exo_battery(x):
    Pm = x["nj"] * x["tj"] * x["wj"]
    Pe = Pm / x["ea"] + x["Pi"]
    return {"Pm": Pm, "Pe": Pe, "rt": x["Eb"] / Pe, "mb": Pe * x["Tg"] / x["se"]}


def metabolic(x):
    pen = x["cm"] * x["me"]
    net = x["Pa"] + pen - x["P0"]
    return {"pen": pen, "net": net, "pc": net / x["P0"], "ef": -net / x["pe"]}


def heated(x):
    Rt = x["rho"] * x["Lt"] / (pi * x["dt"] ** 2 / 4)
    P = x["Vs"] ** 2 / Rt
    q = P / x["Ap"]
    return {"Rt": Rt, "Pj": P, "qf": q, "dT": q / x["hc"], "tb": x["Eb"] / P}


def capsense(x):
    dd = x["d0"] * (1 - x["pp"] / x["Es"])
    C0, Cp = eps0 * x["er"] * x["As"] / x["d0"], eps0 * x["er"] * x["As"] / dd
    return {"dd": dd, "C0": C0, "Cp": Cp, "rc": Cp / C0 - 1, "fo": 1 / (2 * pi * x["Ro"] * Cp)}


def dea(x):
    E = x["Vd"] / x["tf"]
    p = eps0 * x["er"] * E**2
    return {"Ef": E, "pm": p, "sz": p / x["Ye"], "rb": E / x["Eb"], "wd": p / 2}


def sma(x):
    A = pi * x["dw"] ** 2 / 4
    F = x["sr"] * A
    st = x["er"] * x["Lw"]
    m = x["rho"] * A * x["Lw"]
    Rw = x["re"] * x["Lw"] / A
    Eh = m * x["cp"] * x["dTh"]
    return {"Fw": F, "st": st, "mw": m, "Rw": Rw, "Eh": Eh, "Ih": math.sqrt(Eh / (x["ta"] * Rw)), "wm": F * st / m}


def decay(x):
    a = Re + x["hh"]
    bc = x["ms"] / (x["Cd"] * x["As"])
    da = x["rho"] * math.sqrt(mu_e * a) / bc
    return {"aa": a, "vo": math.sqrt(mu_e / a), "Po": 2 * pi * math.sqrt(a**3 / mu_e), "bc": bc, "da": da, "Lf": x["Hs"] / da}


def impacts(x):
    N = x["Fx"] * x["As"] * x["Ty"]
    m = x["rp"] * pi * x["dp"] ** 3 / 6
    return {"Nx": N, "Pi": 1 - math.exp(-N), "Tm": 1 / (x["Fx"] * x["As"]), "mp": m, "Ek": m * x["vi"] ** 2 / 2}


CASES = {
    "metamaterials.holography.reconstruction_resolution": holo_res, "metamaterials.holography.volume_storage_capacity": holo_cap, "metamaterials.design.maxwell_garnett_permittivity": garnett,
    "metamaterials.design.negative_index_refraction": veselago, "metamaterials.self_healing.microcapsule_agent_volume": capsules, "metamaterials.self_healing.healing_time_arrhenius": healing,
    "nanotech.nanomedicine.korsmeyer_peppas_release": kp, "nanotech.nanomedicine.drug_loading_efficiency": loading, "neuro.bci.erp_averaging_trials": erp, "neuro.bci.electrode_thermal_noise": electrode,
    "neuro.neuromorphic.synaptic_energy_budget": synaptic, "neuro.neuromorphic.memristor_crossbar_mac": crossbar, "quantum.communication.plob_repeaterless_bound": plob,
    "quantum.communication.qber_dark_counts": qber, "robotics.hri.transient_contact_force": contact, "robotics.hri.shared_task_cycle": shared, "robotics.service.coverage_cleaning_time": cleaning,
    "robotics.service.delivery_robot_energy_range": delivery, "robotics.swarm.connectivity_radius": swarm, "robotics.swarm.consensus_convergence": consensus,
    "smartcities.smart_infrastructure.webster_signal_timing": webster, "smartcities.smart_infrastructure.water_network_losses": water, "softrobotics.exoskeleton.battery_runtime_assist": exo_battery,
    "softrobotics.exoskeleton.metabolic_net_benefit": metabolic, "softrobotics.smart_textiles.heated_garment_joule": heated, "softrobotics.smart_textiles.capacitive_pressure_sensor": capsense,
    "softrobotics.actuators.dielectric_elastomer_actuator": dea, "softrobotics.actuators.sma_wire_actuator": sma, "space.debris.orbital_decay_drag": decay, "space.debris.impact_flux_energy": impacts,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


def test_benchmarks_and_identities():
    assert solved("metamaterials.design.negative_index_refraction")["t2"] == pytest.approx(-pi / 6)                       # n = -1: same angle, other side of the normal
    assert solved("metamaterials.design.maxwell_garnett_permittivity", fv="0 %")["ee"] == pytest.approx(2.1)               # no inclusions: the host
    assert solved("metamaterials.design.maxwell_garnett_permittivity", ei="2.1")["ee"] == pytest.approx(2.1)               # inclusions like the host
    assert solved("quantum.communication.plob_repeaterless_bound")["Cb"] == pytest.approx(1.4427 * 1e-4, rel=1e-3)         # -log2(1-eta) ~ eta/ln2 for small eta
    assert solved("quantum.communication.qber_dark_counts", Y0="1e-12")["qb"] == pytest.approx(0.015, rel=1e-3)              # no dark counts: the misalignment error
    assert solved("neuro.bci.erp_averaging_trials", Nt="100")["dB"] == pytest.approx(20)
    assert solved("neuro.bci.electrode_thermal_noise", Re="100 kohm", Bw="100 Hz")["Vj"] * 1e6 == pytest.approx(0.41, abs=0.01)     # 1.6 nV/sqrt(Hz) per kohm
    assert solved("smartcities.smart_infrastructure.webster_signal_timing")["Co"] == pytest.approx(40.476, abs=1e-3)
    assert solved("robotics.swarm.consensus_convergence", Na="3", ep="0.1")["l2r"] == pytest.approx(3)                      # a 3-ring is the complete graph
    assert solved("space.debris.orbital_decay_drag")["Po"] / 60 == pytest.approx(94.5, abs=0.2)                               # 500 km orbit
    assert solved("robotics.hri.transient_contact_force")["ok"] == 1 and solved("robotics.hri.transient_contact_force", v="0.8 m/s")["ok"] == 0
    assert mu0 > 0


def test_catalogued_under_the_thin_sub_disciplines():
    for cid in CASES:
        assert CAT.get(cid).subdisciplines and CAT.get(cid).references
