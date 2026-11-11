"""Equation-audit fill, chemistry and emerging fields: each worked example against a different route (microstate enumeration, wavefunction overlap, Jacobian eigenvalues, optimal CHSH settings, iterated Kalman filter, exhaustive enumeration, exact harmonic sums)."""

import itertools
import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, special

HB, NA = 1.054571817e-34, 6.02214076e23


def hund(x):
    l, n = int(x["l"]), int(x["ne"])
    orbs = [(m, s) for m in range(-l, l + 1) for s in (0.5, -0.5)]
    best = None
    for occ in itertools.combinations(orbs, n):                                       # every microstate of the subshell
        MS, ML = sum(o[1] for o in occ), sum(o[0] for o in occ)
        if best is None or (MS, ML) > best:
            best = (MS, ML)                                                           # Hund: largest spin first, then largest orbital momentum
    S, L = best
    J = abs(L - S) if n <= 2 * l + 1 else L + S
    return {"S": S, "L": L, "J": J, "mult": 2 * S + 1, "deg": 2 * J + 1}


def fc(x):
    mu = x["mu"] / NA
    w = 2 * math.pi * x["fq"]
    a = math.sqrt(mu * w / HB)
    dq = x["dq"]
    psi = lambda n, q: (a / math.pi ** 0.5 / 2 ** n / math.factorial(n)) ** 0.5 * math.exp(-(a * q) ** 2 / 2) * special.eval_hermite(n, a * q)
    ov = lambda n: integrate.quad(lambda q: psi(0, q - dq) * psi(n, q), -10 / a, 10 / a)[0] ** 2       # overlap of the displaced ground state with level n
    return {"S": mu * w * dq ** 2 / (2 * HB), "F0": ov(0), "F1": ov(1), "F2": ov(2), "F3": ov(3), "ss": 2 * mu * w * dq ** 2 / (2 * HB) * HB * w}


def brus(x):
    A, B = x["A"], x["B"]
    J = np.array([[B - 1, A ** 2], [-B, -A ** 2]])
    ev = np.linalg.eigvals(J)
    wi = abs(ev[0].imag)
    return {"xs": A, "ys": B / A, "tr": np.trace(J), "dt": np.linalg.det(J), "st": 1.0 if max(ev.real) < 0 else 0.0, "lr": ev[0].real, "wi": wi, "Tp": 2 * math.pi / wi if wi > 1e-3 else 0.0}


def kapus(x):
    r = x["rp"] + x["rm"]
    return {"rs": r, "U": 1.2025e-4 * x["nu"] * x["zp"] * x["zm"] / r * (1 - 34.5e-12 / r)}


def isotherm(x):
    c = x["c"] / 1e-3                                                                 # mg/L
    qL = x["qm"] * x["KL"] * x["c"] / (1 + x["KL"] * x["c"])
    return {"qF": x["Kf"] * c ** (1 / x["nf"]) * 1e-6 / 1e-3, "qL": qL, "th": qL / x["qm"], "ch": 1 / x["KL"], "RL": 1 / (1 + x["KL"] * x["c"])}


def qubit(x):
    th = x["th"]
    psi = np.array([math.cos(th / 2), -1j * math.sin(th / 2)])                         # R_x(theta)|0>
    Z = np.diag([1, -1])
    # CHSH of a Werner state: maximise over the standard optimal settings
    X, Zm = np.array([[0, 1], [1, 0]]), np.diag([1.0, -1.0])
    bell = np.array([1, 0, 0, 1]) / math.sqrt(2)
    rho = x["V1"] * np.outer(bell, bell) + (1 - x["V1"]) * np.eye(4) / 4
    A0, A1 = Zm, X
    B0, B1 = (Zm + X) / math.sqrt(2), (Zm - X) / math.sqrt(2)
    Sc = abs(np.trace(rho @ (np.kron(A0, B0) + np.kron(A0, B1) + np.kron(A1, B0) - np.kron(A1, B1))))
    return {"P1": abs(psi[1]) ** 2, "sz": float((psi.conj() @ Z @ psi).real), "Sc": Sc, "vi": 1.0 if Sc > 2 else 0.0, "Ft": (2 * x["Fe"] + 1) / 3, "Vs": x["V1"] * x["V2"]}


def kalman(x):
    P = x["P"]
    xp, Pp = x["a"] * x["xh"], x["a"] ** 2 * x["P"] + x["Q"]
    K = Pp * x["h"] / (x["h"] ** 2 * Pp + x["R"])
    Pn = (1 - K * x["h"]) * Pp
    p = 1.0
    for _ in range(2000):                                                              # iterate the covariance recursion to steady state
        pp = p + x["Q"]
        k = pp / (pp + x["R"])
        p = (1 - k) * pp
    pinf = p + x["Q"]
    return {"xp": xp, "Pp": Pp, "K": K, "xn": xp + K * (x["z"] - x["h"] * xp), "Pn": Pn, "Pinf": pinf, "Kinf": pinf / (pinf + x["R"])}


def attack(x):
    Pr = 0.0
    for a, b, c in itertools.product((0, 1), repeat=3):                                # enumerate every combination of the three steps
        pr = (x["pa"] if a else 1 - x["pa"]) * (x["pb"] if b else 1 - x["pb"]) * (x["pc"] if c else 1 - x["pc"])
        if (a and b) or c:
            Pr += pr
    rs = x["Lk"] * x["Is"]
    return {"pab": x["pa"] * x["pb"], "Pr": Pr, "EL": Pr * x["Imp"], "rs": rs, "lv": 3.0 if rs >= 15 else 2.0 if rs >= 6 else 1.0}


def zipf(x):
    Nk, k = int(x["Nk"]), int(x["k"])
    H = np.sum(1 / np.arange(1, Nk + 1))                                               # exact harmonic number
    Hk = np.sum(1 / np.arange(1, k + 1))
    p, rq = x["pn"], int(x["Rr"])
    # probability that at least Rr of 3 nodes are up
    av = sum(math.comb(3, j) * p ** j * (1 - p) ** (3 - j) for j in range(rq, 4))
    return {"Hn": H, "f1": 1 / H, "fk": Hk / H, "ns": math.ceil(x["Dv"] / (x["Sh"] * x["fu"])), "cons": 1.0 if x["Rr"] + x["Ww"] > x["N"] else 0.0, "Av": av}


CASES = {
    "chemistry.atomic.hund_rules_term_symbol": (hund, 1e-9), "chemistry.spectroscopy.franck_condon_huang_rhys": (fc, 1e-5), "chemistry.kinetics.brusselator_oscillating_reaction": (brus, 1e-9),
    "chemistry.solid_state.kapustinskii_lattice_energy": (kapus, 1e-9), "chemistry.surface.freundlich_langmuir_isotherms": (isotherm, 1e-9), "quantum.computing.qubit_rotation_chsh_teleportation": (qubit, 1e-9),
    "robotics.estimation.kalman_filter_scalar": (kalman, 1e-6), "cybersecurity.risk.attack_tree_probability_risk_matrix": (attack, 1e-9), "data.architecture.zipf_hot_keys_sharding_quorum": (zipf, 2e-5),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    t = lambda l, n: solved("chemistry.atomic.hund_rules_term_symbol", l=str(l), ne=str(n))
    assert (t(1, 2)["S"], t(1, 2)["L"], t(1, 2)["J"]) == (1, 1, 0)                    # carbon 3P0
    assert (t(2, 5)["S"], t(2, 5)["L"]) == (2.5, 0) and t(2, 5)["J"] == 2.5             # Mn2+ 6S5/2
    assert solved("chemistry.kinetics.brusselator_oscillating_reaction", B="1.5")["st"] == 1.0         # below 1 + A^2: stable steady state
    assert solved("quantum.computing.qubit_rotation_chsh_teleportation", V1="0.7")["vi"] == 0.0        # 0.7 < 1/sqrt(2)
    assert solved("quantum.computing.qubit_rotation_chsh_teleportation", th="180 deg")["P1"] == pytest.approx(1.0)
    assert solved("chemistry.solid_state.kapustinskii_lattice_energy", rp="117 pm", rm="167 pm")["U"] / 1e3 == pytest.approx(800, rel=0.1)   # NaF-like salt


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == cid.split(".")[0]
