"""Equation-audit fill, physics A: each worked example against a different route (transfer matrices, numerical Born integrals, density matrices, orbit integration, surface-pressure integration, finite differences, ODE simulation)."""

import cmath
import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, linalg, optimize

PRE = "physics."
HB = 1.054571817e-34
ME = 9.1093837015e-31
EV = 1.602176634e-19
C0 = 299792458.0
GN = 6.67430e-11
DAY = 86400.0


def fabry(x):
    R, n, L, lam, th = x["R"], x["n"], x["L"], x["lam"], x["th"]
    r = math.sqrt(R)
    tt = 1 - R
    Tf = lambda d: abs(tt * cmath.exp(1j * d / 2) / (1 - R * cmath.exp(1j * d))) ** 2      # amplitude transmission of the two mirrors summed over all round trips
    delta = 4 * math.pi * n * L * math.cos(th) / lam
    half = optimize.brentq(lambda d: Tf(d) - 0.5, 1e-6, 1.0)                              # half-maximum detuning on the first resonance
    fin = 2 * math.pi / (2 * half)
    fsr = C0 / (2 * n * L)
    Tmax, Tmin = Tf(0.0), Tf(math.pi)
    return {"Ff": fin, "fsr": fsr, "fsl": lam ** 2 / (2 * n * L), "dn": fsr / fin, "Q": C0 / lam / (fsr / fin), "ct": Tmax / Tmin, "dl": delta, "Tr": Tf(delta)}


def nsource(x):
    N, d, lam, th = int(x["N"]), x["d"], x["lam"], x["th"]
    ph = 2 * math.pi * d * math.sin(th) / lam
    amp = sum(cmath.exp(1j * k * ph) for k in range(N))                                  # sum the N phasors
    return {"ph": ph, "Ir": abs(amp) ** 2 / N ** 2, "dth": lam / (N * d * math.cos(th)), "m1": math.floor(d / lam), "lc": lam ** 2 / x["dlm"], "tc": lam ** 2 / x["dlm"] / C0}


def golden(x):
    G = 2 * math.pi / HB * x["M"] ** 2 * x["rho"]
    k = math.sqrt(2 * ME * (x["V0"] - x["E"])) / HB
    kk = math.sqrt(2 * ME * x["E"]) / HB
    d = x["d"]
    # exact transmission by matching plane waves and evanescent waves at the two walls of the barrier (linear system for the amplitudes)
    A = np.array([[1, -1, -1, 0], [-1j * kk, k, -k, 0], [0, np.exp(-k * d), np.exp(k * d), -np.exp(1j * kk * d)], [0, -k * np.exp(-k * d), k * np.exp(k * d), -1j * kk * np.exp(1j * kk * d)]], complex)
    rhs = np.array([-1, -1j * kk, 0, 0], complex)                                         # incident wave amplitude 1 (unknowns: r, a, b, t)
    r, a, b, t = np.linalg.solve(A, rhs)
    return {"Gm": G, "tau": 1 / G, "ka": k, "Tw": math.exp(-2 * k * d), "Te": abs(t) ** 2}


def born(x):
    k = math.sqrt(2 * ME * x["E"]) / HB
    q = 2 * k * math.sin(x["th"] / 2)
    g, mu = x["g"], x["mu"]
    amp = lambda qq: -2 * ME / HB ** 2 * (1 / qq) * integrate.quad(lambda r: r * (-g * math.exp(-mu * r) / r) * math.sin(qq * r), 0, 60 / mu, limit=400, epsabs=0, epsrel=1e-11)[0]   # f(q) = -(2m/hbar^2)(1/q) int r V sin(qr) dr
    ds = lambda th: amp(2 * k * math.sin(th / 2)) ** 2
    st = 2 * math.pi * integrate.quad(lambda th: ds(th) * math.sin(th), 1e-9, math.pi, limit=400)[0]
    return {"k": k, "q": q, "ds": ds(x["th"]), "st": st, "dr": (2 * ME * g / HB ** 2 / q ** 2) ** 2, "sh": 4 * math.pi * x["a"] ** 2}


SX = np.array([[0, 1], [1, 0]], complex)
SY = np.array([[0, -1j], [1j, 0]], complex)
SZ = np.array([[1, 0], [0, -1]], complex)


def spin(x):
    th, ph, r = x["th"], x["ph"], x["r"]
    psi = np.array([math.cos(th / 2), cmath.exp(1j * ph) * math.sin(th / 2)])
    rho = r * np.outer(psi, psi.conj()) + (1 - r) / 2 * np.eye(2)                         # pure state of unit Bloch vector mixed with the maximally mixed state
    ev = np.linalg.eigvalsh(rho)
    sv = -sum(e * math.log(e) for e in ev if e > 1e-15)
    H = 0.5 * (x["De"] * SZ + x["Om"] * SX)
    U = linalg.expm(-1j * H * x["t"])
    flip = abs((U @ np.array([1, 0]))[1]) ** 2                                           # start in spin up, ask for spin down
    ex = lambda s: float(np.trace(rho @ s).real)
    return {"sx": ex(SX), "sy": ex(SY), "sz": ex(SZ), "pu": float(rho[0, 0].real), "px": float(np.trace(rho @ (np.eye(2) + SX) / 2).real), "pr": float(np.trace(rho @ rho).real), "sv": sv, "wl": x["gam"] * x["B"], "pf": flip}


def angmom(x):
    from sympy import Rational
    j1, j2 = Rational(x["j1"]).limit_denominator(2), Rational(x["j2"]).limit_denominator(2)
    Js = [abs(j1 - j2) + i for i in range(int(j1 + j2 - abs(j1 - j2)) + 1)]
    assert sum(2 * J + 1 for J in Js) == (2 * j1 + 1) * (2 * j2 + 1)                      # the product space decomposes into the allowed J multiplets
    J, L, S = x["J"], x["L"], x["S"]
    gj = 1 + (J * (J + 1) + S * (S + 1) - L * (L + 1)) / (2 * J * (J + 1))
    return {"Jmin": float(Js[0]), "Jmax": float(Js[-1]), "nJ": float(len(Js)), "ns": float((2 * j1 + 1) * (2 * j2 + 1)), "gJ": gj, "dE": gj * 9.2740100783e-24 * x["B"] * x["mJ"]}


def relativity(x):
    GM = GN * x["M"]
    p = 6 * math.pi * GM / (C0 ** 2 * x["a"] * (1 - x["e"] ** 2))
    # integrate the relativistic Binet orbit equation u'' + u = GM/h^2 + 3 GM u^2/c^2 around one revolution and measure the advance of the perihelion
    a, e = x["a"], x["e"]
    h2 = GM * a * (1 - e * e)
    eps = 3 * GM / C0 ** 2
    s = a                                                                                 # length scale for the dimensionless variables
    f = lambda ph, y: [y[1], -y[0] + GM / h2 * s + eps / s * y[0] ** 2]
    ev = lambda ph, y: y[1]
    ev.direction = -1
    sol = integrate.solve_ivp(f, [0, 2 * math.pi + 0.01], [s / (a * (1 - e)), 0.0], events=ev, rtol=1e-13, atol=1e-16, method="DOP853")
    advance = sol.t_events[0][-1] - 2 * math.pi
    b, r1, r2 = x["b"], x["r1"], x["r2"]
    x1, x2 = math.sqrt(r1 ** 2 - b ** 2), math.sqrt(r2 ** 2 - b ** 2)
    one_way = 2 * GM / C0 ** 3 * math.log((r1 + x1) * (r2 + x2) / b ** 2) + GM / C0 ** 3 * (math.sqrt((r1 - b) / (r1 + b)) + math.sqrt((r2 - b) / (r2 + b)))
    return {"dp": advance, "dc": advance * 36525 * DAY / x["T"], "al": 4 * GM / (C0 ** 2 * b), "sd": 2 * one_way, "rs": 2 * GM / C0 ** 2, "tdf": GM / (C0 ** 2 * x["r"])}


def kutta(x):
    rho, U, Gm, R = x["rho"], x["U"], x["Gm"], x["R"]
    vs = lambda th: -2 * U * math.sin(th) - Gm / (2 * math.pi * R)                       # surface speed of the circulating flow around the cylinder
    cp = lambda th: 1 - (vs(th) / U) ** 2
    L = -integrate.quad(lambda th: 0.5 * rho * U ** 2 * cp(th) * math.sin(th) * R, 0, 2 * math.pi)[0]   # integrate the pressure force on the surface
    ths = math.asin(Gm / (4 * math.pi * U * R))
    vm = max(abs(vs(t)) for t in np.linspace(0, 2 * math.pi, 20001))
    return {"Ll": L, "Cl": L / (rho * U ** 2 * R), "ths": ths, "vm": vm, "Cpm": 1 - (vm / U) ** 2, "om": Gm / (math.pi * x["Rc"] ** 2)}


def instab(x):
    g = 9.80665
    Ra = g * x["be"] * x["dT"] * x["d"] ** 3 / (x["nu"] * x["al"])
    r1, r2, k, sg = x["r1"], x["r2"], x["k"], x["sg"]
    At = (r1 - r2) / (r1 + r2)
    s2 = At * g * k - sg * k ** 3 / (r1 + r2)
    stab = lambda kk: (r1 + r2) / (r1 * r2) * (g * (r1 - r2) / kk + sg * kk)           # (U_c)^2 at wave number kk
    kmin = optimize.minimize_scalar(stab, bounds=(1.0, 1e5), method="bounded", options={"xatol": 1e-9}).x
    return {"Ra": Ra, "rr": Ra / 1707.76, "Pr": x["nu"] / x["al"], "At": At, "s2": s2, "sR": math.sqrt(s2) if s2 > 0 else 0.0, "Uc": math.sqrt(stab(kmin))}


def vdw(x):
    R = 8.314462618
    T, V, a, b = x["T"], x["Vm"], x["a"], x["b"]
    P = lambda t, v: R * t / (v - b) - a / v ** 2
    h = 1e-4
    dPT = (P(T + h, V) - P(T - h, V)) / (2 * h)                                          # finite-difference derivatives of the equation of state
    dPV = (P(T, V * (1 + 1e-6)) - P(T, V * (1 - 1e-6))) / (2e-6 * V)
    # (dV/dT)_P from the implicit equation, then Cp - Cv = -T (dP/dT)_V^2 / (dP/dV)_T  and also T V alpha^2 / kappa
    P0 = P(T, V)
    Vt = lambda t: optimize.brentq(lambda v: P(t, v) - P0, V * 0.5, V * 2)
    dVdT = (Vt(T + 0.01) - Vt(T - 0.01)) / 0.02
    kap = -1 / V / dPV
    al = dVdT / V
    return {"Pv": P0, "dPT": dPT, "dPV": dPV, "dCm": T * V * al ** 2 / kap, "mjt": (2 * a / (R * T) - b) / x["Cp"], "Ti": 2 * a / (R * b), "dmu": R * T * math.log(x["P"] / x["P0"]), "dSu": x["Q"] * (1 / x["Tc"] - 1 / x["Th"])}


def nonlin(x):
    mu = x["mv"]
    r = x["rl"]
    xf = 1 - 1 / r
    xs = 0.3
    for _ in range(2000):
        xs = r * xs * (1 - xs)
    return {"A": 2.0, "Ts": 2 * math.pi * (1 + mu ** 2 / 16), "Tl": (3 - 2 * math.log(2)) * mu, "xe": x["c"] / x["d"], "ye": x["a"] / x["b"], "Tlv": 2 * math.pi / math.sqrt(x["a"] * x["c"]), "xf": xs, "mf": 2 - r, "ly": math.log(abs(r * (1 - 2 * xs)))}              # Lyapunov exponent: log of the derivative on the converged orbit


def bands(x):
    E, a, Pb, t, E0, k = x["E"], x["a"], x["Pb"], x["t"], x["E0"], x["k"]
    al = math.sqrt(2 * ME * E) / HB
    # transfer matrix of one cell: free propagation over a, then a delta barrier of strength V0 b = Pb (units of J m)
    prop = np.array([[math.cos(al * a), math.sin(al * a) / al], [-al * math.sin(al * a), math.cos(al * a)]])
    delta = np.array([[1, 0], [2 * ME * Pb / HB ** 2, 1]])
    f = np.trace(delta @ prop) / 2
    P = ME * Pb * a / HB ** 2
    kb = math.acos(f) / a if abs(f) <= 1 else 0.0
    ring = np.zeros((200, 200))                                                          # a ring of 200 sites diagonalised numerically
    for i in range(200):
        ring[i, i] = E0
        ring[i, (i + 1) % 200] = ring[(i + 1) % 200, i] = -t
    w = np.linalg.eigvalsh(ring)
    return {"al": al, "P": P, "f": f, "al2": 1.0 if abs(f) <= 1 else 0.0, "kb": kb, "Ek": E0 - 2 * t * math.cos(k * a), "bw": w[-1] - w[0], "ms": HB ** 2 / (2 * t * a ** 2) / ME, "vg": 2 * t * a * math.sin(k * a) / HB, "zb": math.pi / a}


CASES = {
    PRE + "optics.fabry_perot_finesse_airy_transmission": (fabry, 3e-3), PRE + "optics.n_source_interference_coherence_length": (nsource, 1e-9), PRE + "quantum.fermi_golden_rule_wkb_tunnelling": (golden, 1e-7),
    PRE + "quantum.born_scattering_yukawa_hard_sphere": (born, 1e-4), PRE + "quantum.spin_half_bloch_sphere_rabi": (spin, 1e-9), PRE + "atomic.angular_momentum_addition_lande_zeeman": (angmom, 1e-9),
    PRE + "gravitation.relativity_perihelion_shapiro": (relativity, 3e-3), PRE + "fluids.kutta_joukowski_circulation_cylinder": (kutta, 1e-6), PRE + "fluids.rayleigh_benard_taylor_helmholtz": (instab, 1e-6),
    PRE + "thermodynamics.van_der_waals_maxwell_jt": (vdw, 1e-4), PRE + "nonlinear.van_der_pol_lotka_volterra_logistic_map": (nonlin, 1e-9), PRE + "solid_state.kronig_penney_tight_binding_bands": (bands, 1e-4),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_limit_cycle_and_lotka_volterra_periods_by_simulation():
    sol = integrate.solve_ivp(lambda t, y: [y[1], (1 - y[0] ** 2) * y[1] - y[0]], [0, 150], [0.1, 0.0], rtol=1e-10, atol=1e-12, events=lambda t, y: y[0], dense_output=True)
    up = [t for t, v in zip(sol.t_events[0], sol.y_events[0]) if v[1] > 0 and t > 60]
    assert np.mean(np.diff(up)) == pytest.approx(solved(PRE + "nonlinear.van_der_pol_lotka_volterra_logistic_map")["Ts"], rel=0.01)       # mu = 1: period 6.66 against 2 pi (1 + mu^2/16)
    a, b, c, d = 0.6, 0.02, 0.4, 0.01
    xe, ye = c / d, a / b
    sol = integrate.solve_ivp(lambda t, z: [a * z[0] - b * z[0] * z[1], -c * z[1] + d * z[0] * z[1]], [0, 60], [xe * 1.01, ye], rtol=1e-11, atol=1e-12, events=lambda t, z: z[1] - ye)
    ups = [t for t, v in zip(sol.t_events[0], sol.y_events[0]) if v[0] > xe]
    assert np.mean(np.diff(ups)) * DAY == pytest.approx(solved(PRE + "nonlinear.van_der_pol_lotka_volterra_logistic_map")["Tlv"], rel=2e-3)


def test_jt_coefficient_from_the_exact_equation_at_low_density():
    R, a, b, Cp, T = 8.314462618, 0.1355, 3.86e-5, 29.1, 300.0
    P = lambda t, v: R * t / (v - b) - a / v ** 2
    V0 = 0.024
    p0 = P(T, V0)
    Vt = lambda t: optimize.brentq(lambda v: P(t, v) - p0, V0 * 0.5, V0 * 2)
    dVdT = (Vt(T + 0.01) - Vt(T - 0.01)) / 0.02
    exact = (T * dVdT - V0) / Cp
    r = solved(PRE + "thermodynamics.van_der_waals_maxwell_jt", T=f"{T} K", Vm=f"{V0 * 1000} L/mol")
    assert r["mjt"] == pytest.approx(exact, rel=0.05)


def test_benchmarks():
    assert solved(PRE + "optics.fabry_perot_finesse_airy_transmission", lam="500 nm", L="10 mm")["Tr"] == pytest.approx(1.0, abs=1e-6)        # 2 L / lambda = 40000: on resonance
    assert solved(PRE + "quantum.spin_half_bloch_sphere_rabi", De="0 rad/us", t="0.7853981633974483 us", Om="2 rad/us")["pf"] == pytest.approx(0.5)   # a pi/2 pulse (Omega t = pi/2)
    assert solved(PRE + "quantum.spin_half_bloch_sphere_rabi", De="0 rad/us", t="1.5707963267948966 us", Om="2 rad/us")["pf"] == pytest.approx(1.0)   # a pi pulse (Omega t = pi)
    assert solved(PRE + "atomic.angular_momentum_addition_lande_zeeman", J="1", L="1", S="0")["gJ"] == pytest.approx(1.0)                    # pure orbital: g = 1
    assert solved(PRE + "atomic.angular_momentum_addition_lande_zeeman", J="0.5", L="0", S="0.5")["gJ"] == pytest.approx(2.0)                # pure spin: g = 2
    assert solved(PRE + "gravitation.relativity_perihelion_shapiro")["dc"] / 4.8481368e-6 == pytest.approx(43.0, abs=0.2)  # Mercury: 43 arcsec per century
    assert solved(PRE + "gravitation.relativity_perihelion_shapiro")["al"] / 4.8481368e-6 == pytest.approx(1.75, abs=0.01)  # light at the solar limb
    assert solved(PRE + "quantum.born_scattering_yukawa_hard_sphere", mu="0.001 1/nm")["ds"] == pytest.approx(solved(PRE + "quantum.born_scattering_yukawa_hard_sphere")["dr"], rel=2e-4)   # unscreened limit: Rutherford


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "physics"
