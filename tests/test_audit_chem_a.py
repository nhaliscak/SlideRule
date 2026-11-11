"""Equation-audit fill, chemical engineering: separations, reactors, mass transfer, thermodynamic models, safety, economics, each against a different route where one exists."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

R = 8.314462618


def flash(x):
    z1, K1, K2 = x["z1"], x["K1"], x["K2"]
    rr = lambda v: z1 * (K1 - 1) / (1 + v * (K1 - 1)) + (1 - z1) * (K2 - 1) / (1 + v * (K2 - 1))
    ps = optimize.brentq(rr, 1e-9, 1 - 1e-9)                                           # the Rachford-Rice equation solved numerically
    x1, x2 = z1 / (1 + ps * (K1 - 1)), (1 - z1) / (1 + ps * (K2 - 1))
    return {"ps": ps, "x1": x1, "y1": K1 * x1, "x2": x2, "y2": K2 * x2, "al": K1 / K2}


def fug(x):
    xD, xB, zF, al, Rr = x["xD"], x["xB"], x["zF"], x["al"], x["R"]
    Nm = math.log(xD / (1 - xD) * (1 - xB) / xB) / math.log(al)
    # Underwood: sum alpha_i z_i/(alpha_i - theta) = 1 - q = 0 for a saturated liquid, then Rmin + 1 = sum alpha_i xD_i/(alpha_i - theta)
    th = optimize.brentq(lambda t: al * zF / (al - t) + (1 - zF) / (1 - t), 1 + 1e-9, al - 1e-9)
    Rm = al * xD / (al - th) + (1 - xD) / (1 - th) - 1
    X = (Rr - Rm) / (Rr + 1)
    Y = 1 - math.exp((1 + 54.4 * X) / (11 + 117.2 * X) * (X - 1) / math.sqrt(X))
    return {"Nm": Nm, "Rm": Rm, "X": X, "Y": Y, "Nt": (Y + Nm) / (1 - Y)}


def kremser(x):
    A, N = x["A"], int(round(x["Nst"]))
    def fraction(A_, n):
        # stage-by-stage mass balance for a solute-free solvent: y_{n+1} = ... solved as a linear system (V = 1, m = 1, L = A)
        M = np.zeros((n, n))
        b = np.zeros(n)
        for i in range(n):                                                           # stage i receives gas from stage i + 1 (i = n - 1 receives the feed gas y = 1) and liquid from stage i - 1
            M[i, i] = -(1 + A_)                                                      # outflows: V y_i + L x_i with y_i = x_i (m = 1)
            if i > 0:
                M[i, i - 1] = A_                                                     # liquid in
            if i < n - 1:
                M[i, i + 1] = 1                                                      # gas in
            else:
                b[i] = -1                                                            # feed gas with y = 1
        xs = np.linalg.solve(M, b)
        return 1 - xs[0]
    fa = fraction(A, N)
    rt = x["rt"]
    Nr = optimize.brentq(lambda n: (A ** (n + 1) - A) / (A ** (n + 1) - 1) - rt, 0.01, 200)
    St = 1 / A
    return {"fa": fa, "Nr": Nr, "St": St, "fs": (St ** (N + 1) - St) / (St ** (N + 1) - 1)}


def drying(x):
    Ws, Ar, Rc = x["Ws"], x["Ar"], x["h"] * x["dT"] / x["lm"]
    t1 = integrate.solve_ivp(lambda t, X: [-Rc * Ar / Ws], (0, 1e7), [x["X1"]], events=lambda t, X: X[0] - x["Xc"], rtol=1e-12, atol=1e-14)
    tc = t1.t_events[0][0]
    f = lambda t, X: [-Rc * Ar / Ws * X[0] / x["Xc"]]                                # falling-rate: rate proportional to the free moisture
    stop = lambda t, X: X[0] - x["X2"]
    stop.terminal = True
    t2 = integrate.solve_ivp(f, (0, 1e8), [x["Xc"]], events=stop, rtol=1e-12, atol=1e-14).t_events[0][0]
    return {"Rc": Rc, "t1": tc, "t2": t2, "tt": tc + t2}


def filtration(x):
    a = x["mu"] * x["al"] * x["cs"] / (2 * x["Ar"] ** 2 * x["dp"])
    b = x["mu"] * x["Rm"] / (x["Ar"] * x["dp"])
    # dV/dt = A dP/(mu (alpha c V/A + Rm)) integrated from V = 0
    sol = integrate.solve_ivp(lambda t, V: [x["Ar"] * x["dp"] / (x["mu"] * (x["al"] * x["cs"] * V[0] / x["Ar"] + x["Rm"]))], (0, x["t"]), [0.0], rtol=1e-11, atol=1e-14)
    V = sol.y[0, -1]
    return {"a2": a, "b2": b, "Vf": V, "qa": V / x["t"], "Mc": x["cs"] * V}


def cyclone(x):
    d50 = math.sqrt(9 * x["mu"] * x["W"] / (2 * math.pi * x["Ne"] * x["vi"] * (x["rp"] - x["rg"])))
    return {"d50": d50, "et": 1 / (1 + (d50 / x["dp"]) ** 2), "dP": x["NH"] * x["rg"] * x["vi"] ** 2 / 2}


def agitator(x):
    n = x["Ni"] / (2 * math.pi)
    P = x["Np"] * x["rho"] * n**3 * x["D"] ** 5
    return {"Re": x["rho"] * n * x["D"] ** 2 / x["mu"], "P": P, "pv": P / x["Vt"], "vt": math.pi * n * x["D"], "Fr": n**2 * x["D"] / 9.80665}


def rtd(x):
    N = x["tm"] ** 2 / x["s2"]
    n = int(round(N))
    c = 1.0
    for _ in range(n):                                                             # n equal CSTRs, each with residence time t/n
        c /= 1 + x["k"] * x["tm"] / n
    return {"Nt": N, "sd": x["s2"] / x["tm"] ** 2, "Xn": 1 - c, "Xp": 1 - math.exp(-x["k"] * x["tm"]), "Xc": x["k"] * x["tm"] / (1 + x["k"] * x["tm"])}


def thiele(x):
    k, De, Cs = x["k"], x["De"], x["Cs"]
    # slab: De C'' = k C, C'(0) = 0, C(L) = Cs; the effectiveness is the mean rate over the rate at the surface
    L = x["Ls"]
    sol = integrate.solve_bvp(lambda s, y: np.vstack([y[1], k / De * y[0]]), lambda a, b: np.array([a[1], b[0] - Cs]), np.linspace(0, L, 60), np.ones((2, 60)) * Cs * 0.5, tol=1e-10)
    es = integrate.quad(lambda s: sol.sol(s)[0], 0, L)[0] / (L * Cs)
    # sphere: C'' + 2C'/r = (k/De) C with regular centre, C(R) = Cs; effectiveness = 3 int C r^2 dr / (Cs R^3)
    Rp = x["Rp"]
    r0 = Rp * 1e-6
    sp = integrate.solve_bvp(lambda r, y: np.vstack([y[1], k / De * y[0] - 2 * y[1] / r]), lambda a, b: np.array([a[1], b[0] - Cs]), np.linspace(r0, Rp, 200), np.ones((2, 200)) * Cs * 0.5, tol=1e-10, max_nodes=100000)
    ep = 3 * integrate.quad(lambda r: sp.sol(r)[0] * r**2, r0, Rp)[0] / (Cs * Rp**3)
    fp = Rp / 3 * math.sqrt(k / De)
    return {"fs": L * math.sqrt(k / De), "es": es, "fp": fp, "ep": ep, "rs": ep * k * Cs, "wp": ep * fp**2}


def batch(x):
    X, C0 = x["X"], x["C0"]
    def time_to(rate):
        ev = lambda t, C: C[0] - C0 * (1 - X)
        ev.terminal = True
        return integrate.solve_ivp(lambda t, C: [-rate(C[0])], (0, 1e9), [C0], events=ev, rtol=1e-12, atol=1e-15).t_events[0][0]
    return {"t1": time_to(lambda c: x["k1"] * c), "t2": time_to(lambda c: x["k2"] * c * c), "th": time_to(lambda c: x["kh"] * math.sqrt(c)), "Cf": C0 * (1 - X)}


def adiabatic(x):
    dTm = -x["dH"] * x["CA0"] / (x["rho"] * x["cp"])
    return {"dTa": dTm * x["X"], "T1": x["T0"] + dTm * x["X"], "dTm": dTm, "Xl": (x["Tmx"] - x["T0"]) / dTm}


def two_film(x):
    ky, kx, m, A = x["ky"], x["kx"], x["m"], x["A"]
    Ky = 1 / (1 / ky + m / kx)
    y1, y2, x2 = x["y1"], x["y2"], x["x2"]
    # NOG = integral dy/(y - y*) along the operating line L(x - x2) = V(y - y2), i.e. x = x2 + (y - y2)/(A m)
    NOG = integrate.quad(lambda y: 1 / (y - m * (x2 + (y - y2) / (A * m))), y2, y1)[0]
    return {"Ky": Ky, "fg": (1 / ky) / (1 / ky + m / kx), "NOG": NOG, "Zt": x["HOG"] * NOG}


def relief(x):
    # API 520 in customary units, converted back: A [in^2] = W [lb/h] sqrt(T Z/M)/(C Kd P1 Kb Kc), T in rankine, P1 in psia
    W = x["W"] * 3600 / 0.45359237
    P1 = x["P1"] / 6894.757
    T = x["T"] * 1.8
    k = x["k"]
    C = 520 * math.sqrt(k * (2 / (k + 1)) ** ((k + 1) / (k - 1)))
    A_in2 = W * math.sqrt(T * x["Z"] / (x["M"] * 1000)) / (C * x["Kd"] * P1 * x["Kb"] * x["Kc"])
    G = x["P1"] * math.sqrt(k * x["M"] * 1000 / 1000 / (x["Z"] * R * x["T"])) * (2 / (k + 1)) ** ((k + 1) / (2 * (k - 1)))
    return {"G": x["P1"] * math.sqrt(k * x["M"] / (x["Z"] * R * x["T"])) * (2 / (k + 1)) ** ((k + 1) / (2 * (k - 1))), "Ao": A_in2 * 0.00064516}


def compress(x):
    Pin, Pout, N, T1, Ra, k, eta = (x[v] for v in ("Pin", "Pout", "Ns", "T1", "Ra", "k", "ei"))
    w = lambda r: k / (k - 1) * Ra * T1 * (r ** ((k - 1) / k) - 1) / eta
    n = int(round(N))
    # optimise the interstage ratios numerically for n stages (log-ratios sum to the overall ratio)
    obj = lambda lr: sum(w(math.exp(v)) for v in lr) + 1e3 * (sum(lr) - math.log(Pout / Pin)) ** 2
    res = optimize.minimize(lambda v: sum(w(math.exp(t)) for t in list(v) + [math.log(Pout / Pin) - sum(v)]), np.full(n - 1, math.log(Pout / Pin) / n), method="Nelder-Mead", options={"xatol": 1e-12, "fatol": 1e-12}) if n > 1 else None
    best = res.fun if res is not None else w(Pout / Pin)
    r = (Pout / Pin) ** (1 / n)
    assert n * w(r) == pytest.approx(best, rel=1e-6)                                  # equal ratios are the optimum
    return {"rs": r, "ws": w(r), "wt": n * w(r), "w1": w(Pout / Pin), "Td": T1 * (1 + (r ** ((k - 1) / k) - 1) / eta), "sv": 1 - n * w(r) / w(Pout / Pin)}


def pr(x):
    Tc, Pc, om, T, Vm = x["Tc"], x["Pc"], x["om"], x["T"], x["Vm"]
    a0, b = 0.45724 * R**2 * Tc**2 / Pc, 0.07780 * R * Tc / Pc
    ka = 0.37464 + 1.54226 * om - 0.26992 * om**2
    al = (1 + ka * (1 - math.sqrt(T / Tc))) ** 2
    P = R * T / (Vm - b) - a0 * al / (Vm**2 + 2 * b * Vm - b**2)
    return {"a0": a0, "b": b, "ka": ka, "al": al, "P": P, "Z": P * Vm / (R * T)}


def vanlaar(x1, A12, A21):
    x2 = 1 - x1
    return math.exp(A12 * (A21 * x2 / (A12 * x1 + A21 * x2)) ** 2), math.exp(A21 * (A12 * x1 / (A12 * x1 + A21 * x2)) ** 2)


def wilson(x1, L12, L21):
    x2 = 1 - x1
    t = L12 / (x1 + L12 * x2) - L21 / (L21 * x1 + x2)
    return math.exp(-math.log(x1 + L12 * x2) + x2 * t), math.exp(-math.log(x2 + L21 * x1) - x1 * t)


def nrtl(x1, t12, t21, an):
    x2 = 1 - x1
    G12, G21 = math.exp(-an * t12), math.exp(-an * t21)
    g1 = x2**2 * (t21 * (G21 / (x1 + x2 * G21)) ** 2 + t12 * G12 / (x2 + x1 * G12) ** 2)
    g2 = x1**2 * (t12 * (G12 / (x2 + x1 * G12)) ** 2 + t21 * G21 / (x1 + x2 * G21) ** 2)
    return math.exp(g1), math.exp(g2)


def activity(x):
    v, w, n = vanlaar(x["x1"], x["A12"], x["A21"]), wilson(x["x1"], x["L12"], x["L21"]), nrtl(x["x1"], x["t12"], x["t21"], x["an"])
    return {"gv1": v[0], "gv2": v[1], "gw1": w[0], "gw2": w[1], "gn1": n[0], "gn2": n[1]}


def tuning(x):
    K, t, d, lm = x["Kp"], x["tp"], x["td"], x["lm"]
    return {"Kc": t / (K * d) * (4 / 3 + d / (4 * t)), "Ti": d * (32 + 6 * d / t) / (13 + 8 * d / t), "Td": 4 * d / (11 + 2 * d / t), "Kl": t / (K * (lm + d)), "Til": t}


def economics(x):
    C2 = x["C1"] * (x["S2"] / x["S1"]) ** x["ex"]
    C3 = C2 * x["I2"] / x["I1"]
    Cp = x["fl"] * C3
    i, n = x["rt"], x["ny"] / 3.15576e7
    return {"C2": C2, "C3": C3, "Cp": Cp, "Aa": Cp * (i * (1 + i) ** n / ((1 + i) ** n - 1)) / 3.15576e7}                 # annuity in the SI per-second form


CASES = {
    "chemical.separation.binary_flash_rachford_rice": (flash, 1e-6), "chemical.separation.fenske_underwood_gilliland": (fug, 1e-6), "chemical.separation.kremser_absorption": (kremser, 1e-6), "chemical.operations.drying_time_constant_falling_rate": (drying, 1e-5),
    "chemical.operations.cake_filtration_ruth": (filtration, 1e-5), "chemical.operations.cyclone_lapple_cut_size": (cyclone, 1e-9), "chemical.operations.agitator_power": (agitator, 1e-9), "chemical.reactors.tanks_in_series_rtd": (rtd, 1e-9),
    "chemical.reactors.thiele_effectiveness": (thiele, 2e-4), "chemical.reactors.batch_reactor_time": (batch, 1e-6), "chemical.reactors.adiabatic_temperature_rise": (adiabatic, 1e-9), "chemical.mass_transfer.two_film_overall_htu": (two_film, 1e-6),
    "chemical.safety.relief_valve_gas_sizing": (relief, 2e-3), "chemical.operations.multistage_compression_intercooling": (compress, 1e-6), "chemical.thermodynamics.peng_robinson_pressure": (pr, 1e-9), "chemical.thermodynamics.binary_activity_models": (activity, 1e-9),
    "chemical.control.cohen_coon_imc_tuning": (tuning, 1e-9), "chemical.economics.equipment_cost_scaling_annuity": (economics, 1e-6),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_activity_models_obey_the_gibbs_duhem_equation():
    for f in (lambda x1: vanlaar(x1, 1.2, 0.9), lambda x1: wilson(x1, 0.65, 0.85), lambda x1: nrtl(x1, 0.35, 0.95, 0.3)):
        for x1 in (0.1, 0.4, 0.8):
            h = 1e-6
            d1 = (math.log(f(x1 + h)[0]) - math.log(f(x1 - h)[0])) / (2 * h)
            d2 = (math.log(f(x1 + h)[1]) - math.log(f(x1 - h)[1])) / (2 * h)
            assert x1 * d1 + (1 - x1) * d2 == pytest.approx(0, abs=1e-6)                                   # x1 dln(g1) + x2 dln(g2) = 0
    assert solved("chemical.thermodynamics.binary_activity_models", x1="0.999")["gv1"] == pytest.approx(1, abs=1e-3)   # infinite dilution limit of the other component is not 1, but this one is


def test_benchmarks():
    pc = solved("chemical.thermodynamics.peng_robinson_pressure", T="190.56 K", Vm=f"{0.3074 * 8.314462618 * 190.56 / 4.599e6 * 1e6} cm^3/mol")
    assert pc["P"] == pytest.approx(4.599e6, rel=2e-4) and pc["Z"] == pytest.approx(0.3074, abs=1e-4)             # the model's own critical compressibility
    ideal = solved("chemical.thermodynamics.peng_robinson_pressure", T="400 K", Vm="100000 cm^3/mol")
    assert ideal["Z"] == pytest.approx(1.0, abs=1e-3)                                                              # dilute gas
    f = solved("chemical.separation.fenske_underwood_gilliland")
    assert 1.0 < f["Rm"] < 1.8 and f["Nt"] > f["Nm"]
    assert solved("chemical.reactors.thiele_effectiveness", k="0.0001 1/s")["es"] > 0.999                          # slow reaction: no diffusion limit
    assert solved("chemical.reactors.thiele_effectiveness", k="2000 1/s")["es"] == pytest.approx(1 / solved("chemical.reactors.thiele_effectiveness", k="2000 1/s")["fs"], rel=1e-3)   # large modulus: eta = 1/phi
    assert solved("chemical.reactors.tanks_in_series_rtd", s2="144 min^2")["Xn"] == pytest.approx(solved("chemical.reactors.tanks_in_series_rtd", s2="144 min^2")["Xc"])   # N = 1: a CSTR
    assert solved("chemical.separation.kremser_absorption", A="1.0001", Nst="3")["fa"] == pytest.approx(3 / 4, abs=1e-3)   # A = 1: N/(N + 1)
    assert solved("chemical.separation.binary_flash_rachford_rice", z1="0.4", K1="2.5", K2="0.4")["x1"] < 0.4 < solved("chemical.separation.binary_flash_rachford_rice")["y1"]   # light component richer in the vapour


def test_catalogued_in_their_sub_disciplines():
    for cid in CASES:
        c = CAT.get(cid)
        assert c.subdisciplines and c.references and c.example
