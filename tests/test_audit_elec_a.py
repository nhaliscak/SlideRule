"""Equation-audit fill, electrical A: circuits, machines, power systems, protection, magnetics, each against a different route."""

import cmath
import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

pi = math.pi
mu0 = 1.25663706212e-6


def thevenin(x):
    Vs, R1, R2, RL = x["Vs"], x["R1"], x["R2"], x["RL"]
    # nodal analysis of the loaded circuit gives the load voltage independently of the Thévenin reduction
    VL = Vs / R1 / (1 / R1 + 1 / R2 + 1 / RL)
    PL = VL**2 / RL
    Rth = R1 * R2 / (R1 + R2)
    Vth = Vs * R2 / (R1 + R2)
    pmax = optimize.minimize_scalar(lambda r: -(Vth**2 * r / (Rth + r) ** 2), bounds=(1e-3, 1e5), method="bounded", options={"xatol": 1e-10}).fun
    assert PL == pytest.approx(Vth**2 * RL / (Rth + RL) ** 2)
    return {"Vth": Vth, "Rth": Rth, "In": Vth / Rth, "PL": PL, "ef": RL / (Rth + RL), "Pm": -pmax}


def meshes(x):
    R1, R2, R3 = x["R1"], x["R2"], x["R3"]
    A = np.array([[R1 + R3, -R3], [-R3, R2 + R3]])
    I = np.linalg.solve(A, np.array([x["V1"], -x["V2"]]))
    return {"De": np.linalg.det(A), "I1": I[0], "I2": I[1], "I3": I[0] - I[1], "Pt": x["V1"] * I[0] - x["V2"] * I[1]}


def transformer(x):
    S, V2, z = x["Sr"], x["V2"], x["zp"]
    R = x["Pcu"] / S
    X = math.sqrt(z**2 - R**2)
    Zb = V2**2 / S
    phi = math.acos(x["pf"]) * x["lg"]
    I = x["ld"] * cmath.exp(-1j * phi)                                              # per-unit current, lagging for lg = 1
    V1 = 1 + I * (R + 1j * X)
    return {"Zb": Zb, "Rq": R * Zb, "Xq": X * Zb, "VR": abs(V1) - 1, "et": x["ld"] * S * x["pf"] / (x["ld"] * S * x["pf"] + x["Pfe"] + x["ld"] ** 2 * x["Pcu"])}


def synchronous(x):
    Vph = x["Vt"] / math.sqrt(3)
    Il = x["P"] / (math.sqrt(3) * x["Vt"] * x["pf"])
    I = Il * cmath.exp(-1j * math.acos(x["pf"]))
    E = Vph + 1j * x["Xs"] * I
    P3 = 3 * (Vph * abs(E) / x["Xs"]) * math.sin(cmath.phase(E))
    assert P3 == pytest.approx(x["P"], rel=1e-9)                                     # the power-angle relation returns the load power
    return {"Il": Il, "Ef": abs(E), "de": cmath.phase(E), "Pmx": 3 * Vph * abs(E) / x["Xs"], "Tq": x["P"] / x["ns"]}


def faults(x):
    a = cmath.exp(2j * pi / 3)
    A = np.array([[1, 1, 1], [1, a**2, a], [1, a, a**2]])
    Zseq = np.diag([x["Z0"], x["Z1"], x["Z2"]])
    Zabc = A @ Zseq @ np.linalg.inv(A)                                               # phase-domain impedance matrix
    E = np.array([x["Ep"], x["Ep"] * a**2, x["Ep"] * a])
    # single line-to-ground on phase a: Ib = Ic = 0, Va = Zf Ia
    Ia = E[0] / (Zabc[0, 0] + x["Zf"])
    # line-to-line between b and c: Ia = 0, Ib = -Ic, Vb = Vc
    M = np.zeros((3, 3), complex)
    M[0] = [1, 0, 0]
    M[1] = [0, 1, 1]
    M[2] = (Zabc[1] - Zabc[2]) * 1
    rhs = np.array([0, 0, E[1] - E[2]])
    Ill = np.linalg.solve(M, rhs)
    # double line-to-ground (b, c, ground, Zf in the common return): Ia = 0, Vb = Vc = Zf (Ib + Ic)
    Md = np.zeros((3, 3), complex)
    Md[0] = [1, 0, 0]
    Md[1] = Zabc[1] + np.array([0, x["Zf"], x["Zf"]])
    Md[2] = Zabc[2] + np.array([0, x["Zf"], x["Zf"]])
    Id = np.linalg.solve(Md, np.array([0, E[1], E[2]]))
    return {"I3": x["Ep"] / x["Z1"], "I0": abs(Ia) / 3, "Ig": abs(Ia), "Il": abs(Ill[1]), "Id": abs(Id[1] + Id[2]), "Sf": 3 * x["Ep"] * x["Ep"] / x["Z1"]}


def two_bus(x):
    V1, V2, X, d = x["V1"], x["V2"], x["X"], x["de"]
    v1, v2 = V1 * cmath.exp(1j * d), V2
    S1 = v1 * ((v1 - v2) / (1j * X)).conjugate()                                      # complex power leaving bus 1
    S2 = v2 * ((v1 - v2) / (1j * X)).conjugate()
    return {"P12": S1.real, "Q1": S1.imag, "Q2": S2.imag, "Pm": V1 * V2 / X, "dV": (x["Pl"] * x["R"] + x["Ql"] * X) / V2**2}


def idmt(x):
    M = x["If"] / x["Is"]
    ts, tv, te = (x["TMS"] * k / (M**p - 1) for k, p in ((0.14, 0.02), (13.5, 1), (80, 2)))
    return {"M": M, "ts": ts, "tv": tv, "te": te, "I2t": x["If"] ** 2 * ts}


def ampacity(x):
    kt = math.sqrt((x["Tmax"] - x["Ta"]) / (x["Tmax"] - x["Tref"]))
    Iad = x["Iz"] * kt * x["kg"]
    return {"kt": kt, "Iad": Iad, "mg": Iad / x["Ib"] - 1, "Tc": x["Ta"] + (x["Tmax"] - x["Tref"]) * (x["Ib"] / x["Iz"]) ** 2}


def battery(x):
    tr = x["Hr"] * (x["Cr"] / (x["Id"] * x["Hr"])) ** x["k"]
    return {"tr": tr, "Ce": x["Id"] * tr, "Vt": x["Eo"] - x["Id"] * x["Ri"], "soc": 1 - x["t"] / tr}


def dc_motor(x):
    Ish = x["TL"] / x["Kf"]
    Iser = math.sqrt(x["TL"] / x["Ks"])
    return {"Ish": Ish, "ws": (x["Vm"] - Ish * x["Ra"]) / x["Kf"], "Iser": Iser, "wse": (x["Vm"] - Iser * (x["Ra"] + x["Rs"])) / (x["Ks"] * Iser), "Ist": x["Vm"] / x["Ra"], "Rst": x["Vm"] / x["Il"] - x["Ra"]}


def magnetic(x):
    Rc, Rg = x["lc"] / (mu0 * x["ur"] * x["Ac"]), x["lg"] / (mu0 * x["Ac"])
    phi = x["Nt"] * x["Ic"] / (Rc + Rg)
    lam = x["Nt"] * phi                                                              # flux linkage
    L = lam / x["Ic"]
    return {"Rc": Rc, "Rg": Rg, "ph": phi, "B": phi / x["Ac"], "L": L, "We": 0.5 * lam * x["Ic"], "fg": Rg / (Rc + Rg)}


def core_loss(x):
    Ps = x["ks"] * x["f"] ** x["a"] * x["Bp"] ** x["b"]
    # eddy loss: average of sigma (omega B x)^2 / 2 over the thickness
    sigma, w = 1 / x["rho"], 2 * pi * x["f"]
    Pv = integrate.quad(lambda xx: sigma * (w * x["Bp"] * xx) ** 2 / 2, -x["d"] / 2, x["d"] / 2)[0] / x["d"]
    Pe = Pv / x["rm"]
    return {"Ps": Ps, "Pe": Pe, "se": Pe / Ps}


def grounding(x):
    Cs = 1 - 0.09 * (1 - x["rr"] / x["rs"]) / (2 * x["hs"] + 0.09)
    return {"Cs": Cs, "Et": (1000 + 1.5 * Cs * x["rs"]) * 0.116 / math.sqrt(x["ts"]), "Es": (1000 + 6 * Cs * x["rs"]) * 0.116 / math.sqrt(x["ts"])}


def sag(x):
    Sst = x["ki"] * x["Pm"] / (x["ef"] * x["pf"])
    return {"Vs": x["Zf"] / (x["Zs"] + x["Zf"]), "Sst": Sst, "dv": Sst / (x["Ss"] + Sst)}


CASES = {
    "electrical.circuits.thevenin_max_power_transfer": (thevenin, 1e-6), "electrical.circuits.two_mesh_analysis": (meshes, 1e-9), "electrical.machines.transformer_equivalent_regulation": (transformer, 1e-9),
    "electrical.machines.synchronous_power_angle": (synchronous, 1e-9), "electrical.power.fault_currents_symmetrical_components": (faults, 1e-6), "electrical.power.two_bus_power_flow": (two_bus, 1e-9),
    "electrical.protection.idmt_relay_curves": (idmt, 1e-9), "electrical.power.cable_ampacity_derating": (ampacity, 1e-9), "electrical.energy.battery_peukert_runtime": (battery, 1e-9), "electrical.machines.dc_motor_shunt_series": (dc_motor, 1e-9),
    "electrical.magnetics.magnetic_circuit_gap": (magnetic, 1e-9), "electrical.magnetics.core_losses_steinmetz_eddy": (core_loss, 1e-6), "electrical.power.grounding_touch_step_voltage": (grounding, 1e-9), "electrical.power.sag_and_motor_start_dip": (sag, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    t = solved("electrical.circuits.thevenin_max_power_transfer", RL="75 ohm")                                 # RL = Rth = 75 ohm: matched
    assert t["PL"] == pytest.approx(t["Pm"]) and t["ef"] == pytest.approx(0.5)
    f = solved("electrical.power.fault_currents_symmetrical_components")
    assert f["Ig"] == pytest.approx(3 * 6350 / 3.2, rel=1e-9) and f["Ig"] < f["I3"]                               # 3E/(Z1 + Z2 + Z0), smaller than the three-phase current when Z0 is large
    s = solved("electrical.power.fault_currents_symmetrical_components", Z0="0.8 ohm")                          # equal sequence impedances: LG current equals the three-phase one
    assert s["Ig"] == pytest.approx(s["I3"])
    sy = solved("electrical.machines.synchronous_power_angle", P="0.001 MW")
    assert abs(sy["de"]) < 0.01                                                                               # a light load needs a small angle
    assert solved("electrical.machines.transformer_equivalent_regulation", lg="-1", pf="0.85")["VR"] < solved("electrical.machines.transformer_equivalent_regulation")["VR"]   # leading loads regulate better
    assert solved("electrical.protection.idmt_relay_curves", If="800 A")["ts"] > solved("electrical.protection.idmt_relay_curves")["ts"]      # a smaller fault clears more slowly
    assert solved("electrical.energy.battery_peukert_runtime", k="1.0")["tr"] == pytest.approx(100 / 25 * 3600)       # k = 1: capacity over current
    assert solved("electrical.magnetics.magnetic_circuit_gap", lg="0.001 mm")["fg"] < 0.05                         # a tiny gap carries little MMF
    assert solved("electrical.power.cable_ampacity_derating", Ta="30 degC", kg="1")["Iad"] == pytest.approx(176)    # reference conditions: the table value


def test_catalogued_in_their_sub_disciplines():
    for cid in CASES:
        c = CAT.get(cid)
        assert c.subdisciplines and c.references and c.example
