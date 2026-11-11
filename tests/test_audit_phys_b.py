"""Equation-audit fill, physics B: each worked example against a different route (boundary-value problem, force balance in the rotating frame, Newton's integrals, four-vectors, Christoffel eigenproblem, numerical distributions)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize, special, stats

PRE = "physics."
KB, Q, EPS0, MU0, C0 = 1.380649e-23, 1.602176634e-19, 8.8541878128e-12, 1.25663706212e-6, 299792458.0
GN = 6.67430e-11
ME, MP = 9.1093837015e-31, 1.67262192369e-27
HB = 1.054571817e-34
YEAR = 31557600.0


def semi(x):
    kT = KB * x["T"]
    Dn, Dh = x["mn"] * kT / Q, x["mh"] * kT / Q
    L = math.sqrt(Dh * x["tau"])
    from scipy.integrate import solve_bvp
    xs = np.linspace(0, 25 * L, 600)
    sol = solve_bvp(lambda s, y: np.vstack([y[1], y[0] / (Dh * x["tau"])]), lambda a, b: np.array([a[0] - 1, b[0]]), xs, np.vstack([np.exp(-xs / L), -np.exp(-xs / L) / L]), tol=1e-10)    # D p'' = p / tau with p(0) = 1 and p(inf) = 0
    sg = Q * (x["n"] * x["mn"] + x["p"] * x["mh"])
    return {"Dn": Dn, "Dh": Dh, "Lh": L, "sg": sg, "rho": 1 / sg, "Jd": sg * x["E"], "pr": sol.sol(x["x"])[0], "RH": -1 / (x["n"] * Q), "VH": -1 / (x["n"] * Q) * x["I"] * x["B"] / x["w"]}


def mos(x):
    kT = KB * x["T"]
    pF = kT / Q * math.log(x["Na"] / x["ni"])
    es, Cox = x["es"] * EPS0, x["eox"] * EPS0 / x["tox"]
    psi = lambda W: Q * x["Na"] * W ** 2 / (2 * es)                                       # surface potential of a depletion layer of width W
    Wm = optimize.brentq(lambda W: psi(W) - 2 * pF, 1e-9, 1e-5)                           # strong inversion: psi_s = 2 phi_F
    Qd = Q * x["Na"] * Wm
    return {"Cox": Cox, "pF": pF, "Wm": Wm, "Vt": x["VFB"] + 2 * pF + Qd / Cox, "Cmin": Cox * (es / Wm) / (Cox + es / Wm)}


def three(x):
    M1, M2, a = x["M1"], x["M2"], x["a"]
    mu = M2 / (M1 + M2)
    # collinear points from the force balance in the co-rotating frame (primary at -mu a, secondary at (1 - mu) a)
    w2 = GN * (M1 + M2) / a ** 3
    f = lambda xx: -GN * M1 * (xx + mu * a) / abs(xx + mu * a) ** 3 - GN * M2 * (xx - (1 - mu) * a) / abs(xx - (1 - mu) * a) ** 3 + w2 * xx
    xs = (1 - mu) * a
    L1 = optimize.brentq(f, xs - 0.1 * a, xs - 1e-3 * a, xtol=1e-3)
    L3 = optimize.brentq(f, -1.2 * a, -0.8 * a, xtol=1e-3)
    mr = M1 / M2
    # linear stability of L4: lambda^4 + lambda^2 + 27 mu (1 - mu) / 4 = 0 has purely imaginary roots when the discriminant is not negative
    disc = 1 - 27 * mu * (1 - mu)
    roche = lambda k: k * x["Rm"] * (x["rhoM"] / x["rhom"]) ** (1 / 3)
    return {"rH": a * (M2 / (3 * M1)) ** (1 / 3), "L1": xs - L1, "L3": -L3 - mu * a, "mr": mr, "st": 1.0 if disc >= 0 else 0.0, "dRg": roche(1.26), "dRf": roche(2.44)}


def radiation(x):
    alpha = Q ** 2 / (4 * math.pi * EPS0 * HB * C0)
    sin2 = 1 - 1 / (x["n"] * x["bt"]) ** 2
    yld = integrate.quad(lambda lam: 2 * math.pi * alpha * sin2 / lam ** 2, x["l1"], x["l2"])[0]       # Frank-Tamm: dN/dx = int 2 pi alpha sin^2(theta) dlambda / lambda^2
    return {"Pl": Q ** 2 * x["a"] ** 2 / (6 * math.pi * EPS0 * C0 ** 3), "Pd": x["p0"] ** 2 * x["om"] ** 4 / (12 * math.pi * EPS0 * C0 ** 3), "sT": 8 * math.pi / 3 * (Q ** 2 / (4 * math.pi * EPS0 * ME * C0 ** 2)) ** 2, "rr": (x["l2"] / x["l1"]) ** 4, "bth": 1 / x["n"], "thc": math.acos(1 / (x["n"] * x["bt"])), "Ny": yld}


def mhd(x):
    vA = x["B"] / math.sqrt(MU0 * x["rho"])
    pB = x["B"] ** 2 / (2 * MU0)
    return {"Ha": x["B"] * x["L"] * math.sqrt(x["sg"] / (x["rho"] * x["nu"])), "Rm": MU0 * x["sg"] * x["v"] * x["L"], "vA": vA, "S": MU0 * x["sg"] * vA * x["L"], "pB": pB, "bt": x["pg"] / pB}


def astro(x):
    sT = 6.6524587321e-29
    M = x["M"]
    LE = optimize.brentq(lambda L: sT * L / (4 * math.pi * 1e10 ** 2 * C0) - GN * M * MP / 1e10 ** 2, 1e20, 1e40)      # radiation force on a proton balances gravity
    Mv = optimize.brentq(lambda m: 2 * (0.5 * m * 3 * x["sg"] ** 2) - 3 * GN * m ** 2 / (5 * x["R"]), 1e30, 1e50)    # 2K + U = 0 with K = 1/2 M (3 sigma^2) and U = -3 G M^2 / 5R
    La = x["et"] * x["Md"] * C0 ** 2
    return {"LE": LE, "Me": LE / (x["et"] * C0 ** 2), "Mv": Mv, "tKH": GN * M ** 2 / (x["Rs"] * x["Ls"]), "La": La, "rE": La / LE}


def simil(x):
    return {"npi": x["nv"] - x["kd"], "Re": x["rho"] * x["U"] * x["L"] / x["mu"], "Fr": x["U"] / math.sqrt(x["g"] * x["L"]), "Ma": x["U"] / x["a"], "We": x["rho"] * x["U"] ** 2 * x["L"] / x["sg"], "St": x["f"] * x["L"] / x["U"], "Eu": x["dp"] / (x["rho"] * x["U"] ** 2)}


def stat(x):
    z = lambda a, b, c: a * b / c
    grads = [(z(x["x"] * (1 + 1e-6), x["y"], x["w"]) - z(x["x"], x["y"], x["w"])) / (x["x"] * 1e-6), (z(x["x"], x["y"] * (1 + 1e-6), x["w"]) - z(x["x"], x["y"], x["w"])) / (x["y"] * 1e-6), (z(x["x"], x["y"], x["w"] * (1 + 1e-6)) - z(x["x"], x["y"], x["w"])) / (x["w"] * 1e-6)]
    dz = math.sqrt((grads[0] * x["dx"]) ** 2 + (grads[1] * x["dy"]) ** 2 + (grads[2] * x["dw"]) ** 2)    # first-order propagation with numerical partial derivatives
    zz = z(x["x"], x["y"], x["w"])
    return {"z": zz, "rz": dz / zz, "dz": dz, "pg": stats.norm.cdf(x["kk"]) - stats.norm.cdf(-x["kk"]), "pp": stats.poisson.pmf(int(x["kc"]), x["lm"]), "rc": x["chi"] / x["nu"], "pv": stats.chi2.sf(x["chi"], x["nu"])}


def elastic(x):
    E, nu, rho = x["E"], x["nu"], x["rho"]
    G, K, lam = E / (2 * (1 + nu)), E / (3 * (1 - 2 * nu)), E * nu / ((1 + nu) * (1 - 2 * nu))
    Cxx = np.array([[lam + 2 * G, 0, 0], [0, G, 0], [0, 0, G]])                          # Christoffel matrix for propagation along x
    ev = np.sort(np.linalg.eigvalsh(Cxx))
    cS, cP = math.sqrt(ev[0] / rho), math.sqrt(ev[-1] / rho)
    k2 = (cS / cP) ** 2
    xi = optimize.brentq(lambda s: (2 - s) ** 2 - 4 * math.sqrt(1 - s) * math.sqrt(1 - k2 * s), 0.5, 0.999999)     # exact Rayleigh equation for xi = (cR / cS)^2
    return {"G": G, "K": K, "lm": lam, "Mp": K + 4 * G / 3, "cP": cP, "cS": cS, "cR": cS * math.sqrt(xi)}


def acoustic(x):
    w = 2 * math.pi * x["f"]
    ka = w / x["c"] * x["a"]
    dirn = lambda th: (2 * special.j1(ka * math.sin(th)) / (ka * math.sin(th))) ** 2 * math.sin(th) if th > 0 else 0.0
    S = math.pi * x["a"] ** 2
    Rr = x["rho"] * x["c"] * S * ka ** 2 / 2 * integrate.quad(dirn, 0, math.pi / 2, limit=400)[0]    # radiated power from the far-field directivity
    alpha = w ** 2 / (2 * x["rho"] * x["c"] ** 3) * (4 / 3 * x["mu"] + (x["gam"] - 1) * x["kt"] / x["cp"])
    return {"mc": math.asin(1 / x["Ma"]), "al": alpha * 20 / math.log(10), "ka": ka, "Rr": Rr, "th0": math.asin(min(3.8317 / ka, 1))}


def ghk(x):
    R, F = 8.314462618, 96485.33212
    z, T, ci, co, V, P = x["z"], x["T"], x["ci"], x["co"], x["Vm"], x["Pm"]
    d = 5e-9
    D = P * d                                                                             # diffusivity from the permeability and the thickness
    u = z * F * V / (R * T)
    def end(J):                                                                           # integrate dc/dx = -J/D + (u/d) c across the membrane (potential V at x = 0 inside and 0 outside)
        s = integrate.solve_ivp(lambda xx, c: [-J / D + u / d * c[0]], [0, d], [ci], rtol=1e-12, atol=1e-14)
        return s.y[0, -1] - co
    J = optimize.brentq(end, -1e3 * ci, 1e3 * ci, xtol=1e-14)
    EN = R * T / (z * F) * math.log(co / ci)
    return {"EN": EN, "u": u, "Ig": z * F * J}


def gravity(x):
    M, R, r = x["M"], x["R"], x["r"]
    shell = lambda rr, Rs: -GN * 1.0 / (2 * Rs * rr) * integrate.quad(lambda th: math.sin(th) * Rs * rr / math.sqrt(Rs ** 2 + rr ** 2 - 2 * Rs * rr * math.cos(th)), 0, math.pi, limit=400)[0]    # unit-mass shell potential by Newton's integral
    sph = lambda rr: integrate.quad(lambda s: 3 * M * s ** 2 / R ** 3 * shell(rr, s), 1e-3, R, limit=400, points=[rr] if rr < R else None)[0]       # superpose shells of the solid sphere
    h = 1e-3 * r
    return {"Ps": sph(r), "gs": (sph(r + h) - sph(r - h)) / (2 * h), "Psh": M * shell(r, R), "gsh": 0.0, "ve": math.sqrt(2 * GN * M / R)}


def mandel(x):
    p, m, th = x["p"], x["m"], x["th"]
    E = math.sqrt(p ** 2 + m ** 2)
    g = np.diag([1, -1, -1, -1])
    dot = lambda a, b: a @ g @ b
    p1, p2 = np.array([E, 0, 0, p]), np.array([E, 0, 0, -p])
    p3, p4 = np.array([E, p * math.sin(th), 0, p * math.cos(th)]), np.array([E, -p * math.sin(th), 0, -p * math.cos(th)])
    s, t, u = dot(p1 + p2, p1 + p2), dot(p1 - p3, p1 - p3), dot(p1 - p4, p1 - p4)         # squares of four-momentum sums and transfers
    assert s + t + u == pytest.approx(4 * m ** 2, rel=1e-9)                              # s + t + u = sum of the squared masses
    L = x["f"] * x["nb"] * x["Nb"] ** 2 / (4 * math.pi * x["sx"] * x["sy"])
    return {"s": s, "t": t, "u": u, "Lm": L, "rt": x["sig"] * L}


def cmb(x):
    Tz = x["T0"] * (1 + x["z"])
    kT = KB * Tz
    n = integrate.quad(lambda k: k ** 2 / (math.exp(HB * C0 * k / kT) - 1), 0, 60 * kT / (HB * C0))[0] / math.pi ** 2    # photon gas: n = (1/pi^2) int k^2 dk / (exp(hbar c k / kT) - 1)
    np1 = math.exp(-x["dm"] / x["Tf"])
    np2 = np1 * math.exp(-x["tn"] / x["tau"])
    return {"Tz": Tz, "ng": n, "np1": np1, "np2": np2, "Yp": 2 * np2 / (1 + np2)}


CASES = {
    PRE + "solid_state.semiconductor_drift_diffusion_hall": (semi, 1e-6), PRE + "solid_state.mos_capacitor_threshold_voltage": (mos, 1e-6), PRE + "gravitation.lagrange_hill_roche_limits": (three, 1e-2),
    PRE + "electromagnetism.larmor_dipole_thomson_cherenkov": (radiation, 1e-4), PRE + "plasma.mhd_hartmann_magnetic_reynolds_alfven": (mhd, 1e-9), PRE + "astrophysics.eddington_virial_kh_accretion": (astro, 1e-6),
    PRE + "fluids.similarity_numbers_buckingham_pi": (simil, 1e-9), PRE + "statistics.error_propagation_poisson_chi_square": (stat, 1e-5), PRE + "elasticity.isotropic_moduli_wave_speeds": (elastic, 3e-3),
    PRE + "acoustics.mach_cone_absorption_piston_radiation": (acoustic, 1e-5), PRE + "electrochemistry.nernst_planck_ghk_current": (ghk, 1e-6), PRE + "gravitation.sphere_and_shell_potential_field": (gravity, 1e-4),
    PRE + "particle.mandelstam_variables_luminosity": (mandel, 1e-9), PRE + "cosmology.cmb_temperature_bbn_helium": (cmb, 1e-6),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_ghk_current_vanishes_at_the_nernst_potential():
    en = solved(PRE + "electrochemistry.nernst_planck_ghk_current")["EN"]
    assert solved(PRE + "electrochemistry.nernst_planck_ghk_current", Vm=f"{en * 1000} mV")["Ig"] == pytest.approx(0, abs=1e-9)


def test_benchmarks():
    assert solved(PRE + "gravitation.lagrange_hill_roche_limits", M1="1.989e30 kg", M2="1.898e27 kg", a="778.5e6 km")["st"] == 1.0         # Sun-Jupiter: the Trojans are stable
    assert solved(PRE + "gravitation.lagrange_hill_roche_limits", M1="5.972e24 kg", M2="1.2e24 kg", a="384400 km")["st"] == 0.0           # a mass ratio below 24.96: unstable
    assert solved(PRE + "cosmology.cmb_temperature_bbn_helium")["Yp"] == pytest.approx(0.223, abs=0.003)
    assert solved(PRE + "statistics.error_propagation_poisson_chi_square", kk="1")["pg"] == pytest.approx(0.6827, abs=1e-4)                # one sigma coverage
    assert solved(PRE + "elasticity.isotropic_moduli_wave_speeds", nu="0.25")["cP"] == pytest.approx(math.sqrt(3) * solved(PRE + "elasticity.isotropic_moduli_wave_speeds", nu="0.25")["cS"])    # Poisson solid: cP = sqrt(3) cS
    assert solved(PRE + "electromagnetism.larmor_dipole_thomson_cherenkov")["sT"] == pytest.approx(6.6524587e-29, rel=1e-6)                 # the Thomson cross-section
    assert solved(PRE + "astrophysics.eddington_virial_kh_accretion")["LE"] / 3.828e26 == pytest.approx(3.28e4, rel=0.01)     # 3.3e4 solar luminosities per solar mass
    assert solved(PRE + "gravitation.sphere_and_shell_potential_field", r="6371 km")["ve"] == pytest.approx(11186, rel=1e-3)                  # Earth's escape speed
    assert solved(PRE + "gravitation.sphere_and_shell_potential_field", r="3000 km")["gsh"] == 0.0                                           # no field inside a shell


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "physics"
