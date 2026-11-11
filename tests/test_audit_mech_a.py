"""Equation-audit fill, mechanical A and control: machine design, vibration and classical control theory, each against a different route."""

import cmath
import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

pi = math.pi
g = 9.80665


def stress_conc(x):
    q = 1 / (1 + x["ap"] / x["r"])
    Kf = 1 + q * (x["Kt"] - 1)
    return {"sm": x["Kt"] * x["sn"], "q": q, "Kf": Kf, "sf": Kf * x["sn"]}


def vessel(x):
    p, D, t = x["p"], x["D"], x["t"]
    return {"sh": p * D / (2 * t), "sl": p * D / (4 * t), "ss": p * D / (4 * t), "tr": p * D / (2 * x["sa"] * x["E"])}


def lame(x):
    pi_, po, ri, ro, r = x["pi"], x["po"], x["ri"], x["ro"], x["r"]
    # boundary conditions sigma_r(ri) = -pi, sigma_r(ro) = -po on sigma_r = A - B/r^2 give A and B by a linear solve
    A, B = np.linalg.solve(np.array([[1, -1 / ri**2], [1, -1 / ro**2]]), np.array([-pi_, -po]))
    return {"sr": A - B / r**2, "st": A + B / r**2, "sb": A + B / ri**2, "sz": A}


def press_fit(x):
    r, c, Eh, Es, nh, ns = x["r"], x["c"], x["Eh"], x["Es"], x["nh"], x["ns"]
    def mismatch(p):
        sigma_t_bore, sigma_r_bore = p * (c**2 + r**2) / (c**2 - r**2), -p
        u_hub = r / Eh * (sigma_t_bore - nh * sigma_r_bore)                       # radial displacement of the hub bore (plane stress)
        u_shaft = r / Es * (-p - ns * (-p))                                       # solid shaft under external pressure p
        return (u_hub - u_shaft) - x["dl"]
    p = optimize.brentq(mismatch, 1e3, 1e11)
    return {"pc": p, "sh": p * (c**2 + r**2) / (c**2 - r**2), "Tc": 2 * pi * r**2 * x["Lc"] * x["mu"] * p, "Fa": 2 * pi * r * x["Lc"] * x["mu"] * p}


def shaft(x):
    d = x["d"]
    sa = 32 * x["Kf"] * x["Ma"] / (pi * d**3)
    sm = math.sqrt(3) * 16 * x["Kfs"] * x["Tm"] / (pi * d**3)
    nG, nS = 1 / (sa / x["Se"] + sm / x["Sut"]), 1 / (sa / x["Se"] + sm / x["Sy"])
    dr = optimize.brentq(lambda dd: 1 / (32 * x["Kf"] * x["Ma"] / (pi * dd**3) / x["Se"] + math.sqrt(3) * 16 * x["Kfs"] * x["Tm"] / (pi * dd**3) / x["Sut"]) - x["nt"], 1e-3, 1.0)   # the diameter whose Goodman factor is the target
    return {"sa": sa, "sm": sm, "nG": nG, "nS": nS, "dr": dr}


def clutch(x):
    F, mu, ro, ri, N = x["F"], x["mu"], x["ro"], x["ri"], x["N"]
    # uniform pressure: p = F/(pi (ro^2 - ri^2)); T = N mu int p 2 pi r^2 dr   |   uniform wear: p r = const = F/(2 pi (ro - ri))
    p = F / (pi * (ro**2 - ri**2))
    Tp = N * mu * integrate.quad(lambda r: p * 2 * pi * r**2, ri, ro)[0]
    pw = F / (2 * pi * (ro - ri))
    Tw = N * mu * integrate.quad(lambda r: (pw / r) * 2 * pi * r**2, ri, ro)[0]
    return {"rw": (ro + ri) / 2, "Tw": Tw, "Tp": Tp}


def isolation(x):
    r = x["fe"] / x["fn"]
    z = x["ze"]
    TR = abs((1 + 2j * z * r) / (1 - r**2 + 2j * z * r))                          # complex transmissibility
    X = x["me"] / x["M"] * r**2 / abs(1 - r**2 + 2j * z * r)
    return {"r": r, "TR": TR, "Xa": X, "ei": 1 - TR, "ds": g / (2 * pi * x["fn"]) ** 2}


def critical_speed(x):
    ms, ys = [x["m1"], x["m2"], x["m3"]], [x["y1"], x["y2"], x["y3"]]
    wc = math.sqrt(g * sum(m * y for m, y in zip(ms, ys)) / sum(m * y * y for m, y in zip(ms, ys)))
    return {"wc": wc, "w1": math.sqrt(g / ys[0]), "mg": x["N"] / wc}


def two_dof(x):
    m1, m2, k1, k2, k3 = (x[k] for k in ("m1", "m2", "k1", "k2", "k3"))
    M = np.diag([m1, m2])
    K = np.array([[k1 + k2, -k2], [-k2, k2 + k3]])
    w2, v = np.linalg.eig(np.linalg.solve(M, K))
    order = np.argsort(w2)
    w2, v = w2[order], v[:, order]
    return {"a": (k1 + k2) / m1, "b": (k2 + k3) / m2, "f1": math.sqrt(w2[0]) / (2 * pi), "f2": math.sqrt(w2[1]) / (2 * pi), "r1": v[1, 0] / v[0, 0], "r2": v[1, 1] / v[0, 1]}


def gear(x):
    d = x["m"] * x["Nt"]
    v = x["n"] * d / 2
    Wt = x["P"] / v
    Kv = (6.1 + v) / 6.1
    sb = Wt * Kv / (x["Fw"] * x["m"] * x["Y"])
    return {"d": d, "v": v, "Wt": Wt, "Kv": Kv, "sb": sb, "nf": x["Sa"] / sb}


def bearing(x):
    Pe = x["X"] * x["Fr"] + x["Y"] * x["Fa"]
    L10 = (x["C"] / Pe) ** x["p"]
    rpm = x["n"] * 60 / (2 * pi)
    L10h = L10 * 1e6 / (60 * rpm) * 3600                                       # seconds
    return {"Pe": Pe, "L10": L10, "L10h": L10h, "Lna": x["a1"] * L10h}


def belt(x):
    D, d, C = x["D"], x["d"], x["Cd"]
    a = math.asin((D - d) / (2 * C))
    phi_d, phi_D = pi - 2 * a, pi + 2 * a
    L = math.sqrt(4 * C**2 - (D - d) ** 2) + (D * phi_D + d * phi_d) / 2          # exact open-belt length
    v = x["n"] * d / 2
    tr = math.exp(x["mu"] * phi_d / math.sin(x["be"] / 2))
    return {"Lb": L, "th": phi_d, "v": v, "tr": tr, "Pw": x["T1"] * (1 - 1 / tr) * v}


def bolt_joint(x):
    db, Lg, Eb, Em, dw, Fi, P = (x[k] for k in ("db", "Lg", "Eb", "Em", "dw", "Fi", "P"))
    kb = pi * db**2 / 4 * Eb / Lg
    t = math.tan(math.radians(30))
    km = pi * Em * db * t / (2 * math.log(((Lg * t + dw - db) * (dw + db)) / ((Lg * t + dw + db) * (dw - db))))
    C_ = kb / (kb + km)
    return {"kb": kb, "km": km, "Cj": C_, "Fb": C_ * P + Fi, "Fm": (1 - C_) * P - Fi, "n0": Fi / ((1 - C_) * P)}


def flywheel(x):
    w = x["n"]                                                                  # rad/s in SI
    I = x["dE"] / (x["Cs"] * w**2)
    wmax, wmin = w * (1 + x["Cs"] / 2), w * (1 - x["Cs"] / 2)
    assert 0.5 * I * (wmax**2 - wmin**2) == pytest.approx(x["dE"], rel=1e-9)  # the defining energy balance
    return {"I": I, "m": 2 * I / (x["D"] / 2) ** 2, "vr": w * x["D"] / 2, "wmax": wmax, "wmin": wmin}


# ---------------------------------------------------------------- control
def routh(x):
    coef = [x["a4"], x["a3"], x["a2"], x["a1"], x["a0"]]
    roots = np.roots(coef)
    rhp = int(np.sum(roots.real > 0))
    b1 = (x["a3"] * x["a2"] - x["a4"] * x["a1"]) / x["a3"]
    c1 = (b1 * x["a1"] - x["a3"] * x["a0"]) / b1
    return {"b1": b1, "c1": c1, "nsc": float(rhp), "st": 1.0 if rhp == 0 else 0.0}


def root_locus(x):
    a, b = x["a"], x["b"]
    poly = np.poly([0, -a, -b])                                                   # s^3 + (a + b)s^2 + ab s
    dK = np.polyder(poly)                                                         # K(s) = -poly(s): breakaway where poly'(s) = 0
    roots = np.roots(dK)
    sb = max(r.real for r in roots if abs(r.imag) < 1e-12 and -a < r.real < 0)
    Kb = abs(np.polyval(poly, sb))
    loop = lambda K: [1, a + b, a * b, K]                                         # s^3 + (a + b)s^2 + ab s + K = 0
    kc = optimize.brentq(lambda K: max(np.roots(loop(K)).real), 1e-6, 1e4)        # gain at which a root reaches the imaginary axis
    wc = abs(max(np.roots(loop(kc)), key=lambda r: abs(r.imag)).imag)
    return {"sa": -(a + b) / 3, "sb": sb, "Kb": Kb, "Kc": kc, "wc": wc}


def lead(x):
    al = (1 - math.sin(x["ph"])) / (1 + math.sin(x["ph"]))
    T = 1 / (x["wm"] * math.sqrt(al))
    G = lambda w: (1 + 1j * w * T) / (1 + 1j * w * al * T)
    assert cmath.phase(G(x["wm"])) == pytest.approx(x["ph"], rel=1e-9)             # the phase at ωm is the one asked for
    assert max(cmath.phase(G(w)) for w in np.geomspace(x["wm"] / 100, x["wm"] * 100, 4001)) == pytest.approx(x["ph"], rel=1e-5)
    return {"al": al, "Tl": T, "wz": 1 / T, "wp": 1 / (al * T), "gm": abs(G(x["wm"])), "gh": 1 / al}


def freq_response(x):
    wn, z, w = x["wn"], x["ze"], x["w"]
    G = lambda ww: wn**2 / ((1j * ww) ** 2 + 2 * z * wn * 1j * ww + wn**2)
    ws = np.linspace(0.01 * wn, 3 * wn, 300001)
    mag = np.abs(G(ws))
    i = int(np.argmax(mag))
    wb = optimize.brentq(lambda ww: abs(G(ww)) - 1 / math.sqrt(2), 1e-6 * wn, 10 * wn)
    return {"r": w / wn, "Mg": abs(G(w)), "Mdb": 20 * math.log10(abs(G(w))), "phi": cmath.phase(G(w)), "Mr": mag[i], "wr": ws[i], "wb": wb}


def state_space(x):
    A = np.array([[x["a11"], x["a12"]], [x["a21"], x["a22"]]])
    B = np.array([[x["b1"]], [x["b2"]]])
    Cc = np.array([[x["c1"], x["c2"]]])
    lam = np.linalg.eigvals(A)
    real_case = np.all(np.abs(lam.imag) < 1e-12)
    return {"tr": float(np.trace(A)), "dt": float(np.linalg.det(A)), "lr": float(lam.real.mean()), "li": float(abs(lam.imag).max()), "l1": float(lam.real.max()) if real_case else float(lam.real.mean()),
            "st": 1.0 if np.all(lam.real < 0) else 0.0, "Mc": float(np.linalg.det(np.hstack([B, A @ B]))), "Mo": float(np.linalg.det(np.vstack([Cc, Cc @ A])))}


CASES = {
    "mechanical.design.stress_concentration_notch": (stress_conc, 1e-9), "mechanical.design.pressure_vessel_thin_wall": (vessel, 1e-9), "mechanical.design.lame_thick_cylinder": (lame, 1e-9), "mechanical.design.press_fit_interference": (press_fit, 1e-6),
    "mechanical.design.shaft_fatigue_goodman": (shaft, 1e-6), "mechanical.design.disc_clutch_brake": (clutch, 1e-6), "mechanical.vibration.transmissibility_unbalance": (isolation, 1e-9), "mechanical.vibration.critical_speed_rayleigh": (critical_speed, 1e-9),
    "mechanical.vibration.two_dof_modes": (two_dof, 1e-6), "mechanical.design.gear_tooth_bending": (gear, 1e-9), "mechanical.design.bearing_life_l10": (bearing, 1e-9), "mechanical.design.v_belt_drive": (belt, 5e-3),
    "mechanical.design.bolted_joint_stiffness": (bolt_joint, 1e-9), "mechanical.design.flywheel_sizing": (flywheel, 1e-9),
    "electrical.control.routh_hurwitz_fourth_order": (routh, 1e-9), "electrical.control.root_locus_third_order": (root_locus, 1e-6), "electrical.control.lead_compensator_design": (lead, 1e-9),
    "electrical.control.second_order_frequency_response": (freq_response, 2e-4), "electrical.control.state_space_second_order": (state_space, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_routh_agrees_with_the_roots_for_stable_and_unstable_polynomials():
    for a0, expect in (("5", 0), ("-1", 1), ("0.5", 0)):
        got = solved("electrical.control.routh_hurwitz_fourth_order", a0=a0)
        roots = np.roots([1, 6, 11, 6, float(a0)])
        assert got["nsc"] == int(np.sum(roots.real > 0)) == expect and got["st"] == (1 if expect == 0 else 0)
    unstable = solved("electrical.control.routh_hurwitz_fourth_order", a4="1", a3="1", a2="1", a1="2", a0="1")       # s^4 + s^3 + s^2 + 2s + 1
    assert unstable["nsc"] == int(np.sum(np.roots([1, 1, 1, 2, 1]).real > 0)) == 2


def test_root_locus_critical_gain_puts_roots_on_the_imaginary_axis():
    a, b = 2.0, 5.0
    got = solved("electrical.control.root_locus_third_order")
    roots = np.roots([1, a + b, a * b, got["Kc"]])
    assert sum(abs(r.real) < 1e-6 for r in roots) == 2 and max(abs(r.imag) for r in roots) == pytest.approx(got["wc"], rel=1e-6)
    stable_below = np.roots([1, a + b, a * b, 0.9 * got["Kc"]])
    assert max(stable_below.real) < 0 and max(np.roots([1, a + b, a * b, 1.1 * got["Kc"]]).real) > 0


def test_vibration_and_design_benchmarks():
    at_root_two = solved("mechanical.vibration.transmissibility_unbalance", fe="11.3137 Hz", fn="8 Hz", ze="0.3")
    assert at_root_two["TR"] == pytest.approx(1.0, abs=1e-4)                                              # every curve crosses 1 at r = √2
    assert solved("mechanical.design.shaft_fatigue_goodman", d=f"{solved('mechanical.design.shaft_fatigue_goodman')['dr'] * 1000} mm")["nG"] == pytest.approx(1.8, rel=1e-6)   # the required diameter gives the target factor
    assert solved("mechanical.design.lame_thick_cylinder", r="50 mm")["sr"] == pytest.approx(-60e6)         # radial stress equals minus the bore pressure at the bore
    assert solved("mechanical.design.lame_thick_cylinder", r="100 mm")["sr"] == pytest.approx(0, abs=1)    # and zero at the free outer surface
    assert solved("mechanical.design.bearing_life_l10", Fa="0 kN", Fr="30.7 kN", X="1", p="3")["L10"] == pytest.approx(1.0)    # load equal to the rating: one million revolutions
    assert 0 < solved("mechanical.design.bolted_joint_stiffness")["Cj"] < 0.5
    assert solved("mechanical.design.disc_clutch_brake")["Tw"] < solved("mechanical.design.disc_clutch_brake")["Tp"]          # uniform wear gives the smaller capacity


def test_catalogued_in_their_sub_disciplines():
    for cid in CASES:
        c = CAT.get(cid)
        assert c.subdisciplines and c.references and c.example
