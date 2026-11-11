"""Equation-audit fill, nuclear engineering: each worked example against a different route (point-kinetics ODE, finite-difference eigenvalue, rate-equation steady state, radial heat conduction)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize, special

PRE = "nuclear."


def kinetics(x):
    be, la, Lg = x["be"], x["la"], x["Lg"]
    rho = x["rd"] * be

    def rhs(t, y):
        n, c = y
        return [(rho - be) / Lg * n + la * c, be / Lg * n - la * c]
    c0 = be / (la * Lg)                                                                  # precursors in equilibrium with n = 1 before the step
    t_end = 200.0
    sol = integrate.solve_ivp(rhs, [0, t_end], [1.0, c0], method="Radau", rtol=1e-11, atol=1e-14, dense_output=True)
    t1, t2 = 150.0, 200.0
    w = (math.log(sol.sol(t2)[0]) - math.log(sol.sol(t1)[0])) / (t2 - t1)                # asymptotic slope of ln n
    tj = 0.3
    pj = sol.sol(tj)[0] / math.exp(w * tj)
    return {"rho": rho, "w": w, "T": 1 / w, "Td": math.log(2) / w, "pj": pj}


def bare(x):
    D, Sa, nSf = x["D"], x["Sa"], x["nSf"]
    L2, kinf = D / Sa, nSf / Sa
    d = 2.13 * D
    # sphere: u = r phi obeys u'' + B^2 u = 0 with u(0) = u(Rext) = 0; the lowest eigenvalue of the finite-difference operator
    Rext, n = x["R"] + d, 4000
    h = Rext / n
    main, off = np.full(n - 1, 2.0 / h ** 2), np.full(n - 2, -1.0 / h ** 2)
    from scipy.linalg import eigh_tridiagonal
    Bs = eigh_tridiagonal(main, off, select="i", select_range=(0, 0))[0][0]
    zero = special.jn_zeros(0, 1)[0]
    Bc = (zero / (x["R"] + d)) ** 2 + (math.pi / (x["H"] + 2 * d)) ** 2
    Bl = (math.pi / (x["a"] + 2 * d)) ** 2
    Bm = (kinf - 1) / L2
    Rc = optimize.brentq(lambda r: kinf / (1 + L2 * (math.pi / (r + d)) ** 2) - 1, 1e-4, 10)     # the radius where k_eff = 1
    return {"L2": L2, "kinf": kinf, "Bm": Bm, "dx": d, "Bs": Bs, "Bc": Bc, "Bl": Bl, "ks": kinf / (1 + L2 * Bs), "kc": kinf / (1 + L2 * Bc), "kl": kinf / (1 + L2 * Bl), "Rc": Rc, "Mc": 4 / 3 * math.pi * Rc ** 3 * x["rho"]}


def xenon(x):
    phi, Sf, Sa = x["ph"], x["Sf"], x["Sa"]
    gI, gX, lI, lX, sX = x["gI"], x["gX"], x["lI"], x["lX"], x["sX"]
    sol = integrate.solve_ivp(lambda t, y: [gI * Sf * phi - lI * y[0], gX * Sf * phi + lI * y[0] - lX * y[1] - sX * phi * y[1]], [0, 3e6], [0.0, 0.0], method="Radau", rtol=1e-11, atol=1e-6)   # run both to equilibrium
    I, X = sol.y[0, -1], sol.y[1, -1]
    P = sX * X / Sa
    return {"Ie": I, "Xe": X, "P": P, "rx": -P / (1 + P), "Pm": (gI + gX) * Sf / Sa}


def pin(x):
    ql, rf, kf = x["ql"], x["rf"], x["kf"]
    from scipy.integrate import solve_bvp
    q3 = ql / (math.pi * rf ** 2)
    r = np.linspace(1e-6, rf, 200)
    # k (T'' + T'/r) = -q''' with T'(0) = 0 and T(rf) = 0: the centre-to-surface rise of the pellet
    sol = solve_bvp(lambda s, y: np.vstack([y[1], -q3 / kf - y[1] / s]), lambda a, b: np.array([a[1], b[0]]), r, np.zeros((2, r.size)), tol=1e-10)
    dTp = sol.sol(1e-6)[0]
    film = ql / (2 * math.pi * x["rco"] * x["hc"])
    clad = integrate.quad(lambda rr: ql / (2 * math.pi * rr * x["kc"]), x["rci"], x["rco"])[0]     # integrate the Fourier law through the wall
    gap = ql / (2 * math.pi * rf * x["hg"])
    qs = ql / (2 * math.pi * x["rco"])
    return {"dTf": film, "dTc": clad, "dTg": gap, "dTp": dTp, "Tcl": x["Tc"] + film + clad + gap + dTp, "qs": qs, "dnbr": x["qc"] / qs}


def fission(x):
    E = x["Ef"]
    Rf = x["P"] / E
    mf = (1 + x["al"]) * Rf * x["t"] * x["A"] / 6.02214076e23
    return {"Rf": Rf, "mf": mf, "Bu": x["P"] * x["t"] / x["Mhm"], "sc": (1 + x["al"]) * x["A"] / (6.02214076e23 * E)}


def shield(x):
    mx = x["mu"] * x["x"]
    B = 1 + x["ab"] * mx * math.exp(x["bb"] * mx)
    Iu = x["I0"] * math.exp(-mx)
    Is = Iu * B
    return {"mx": mx, "B": B, "Iu": Iu, "Is": Is, "Af": Is / x["I0"], "ph": x["S"] * math.exp(-x["Sr"] * x["xn"]) / (4 * math.pi * x["r"] ** 2)}


def activation(x):
    la = math.log(2) / x["T12"]
    sol = integrate.solve_ivp(lambda t, y: [x["N"] * x["sg"] * x["ph"] - la * y[0]], [0, x["ti"]], [0.0], rtol=1e-12, atol=1e-6)       # number of product nuclei
    A = la * sol.y[0, -1]
    t = x["ts"]
    Pd = x["P0"] * 0.066 * (t ** -0.2 - (t + x["To"]) ** -0.2)
    H = x["wR"] * x["D"]
    return {"la": la, "As": x["N"] * x["sg"] * x["ph"], "Ai": A, "Pd": Pd, "H": H, "E": x["wT"] * H}


CASES = {
    PRE + "reactor.point_kinetics_period_prompt_jump": (kinetics, 2e-3), PRE + "reactor.bare_reactor_criticality_buckling": (bare, 1e-4), PRE + "reactor.xenon_135_equilibrium_poisoning": (xenon, 1e-6),
    PRE + "thermal_hydraulics.fuel_pin_centerline_dnbr": (pin, 1e-5), PRE + "fuel.fission_rate_burnup_consumption": (fission, 1e-9), PRE + "shielding.gamma_buildup_neutron_removal": (shield, 1e-9),
    PRE + "radiological.activation_decay_heat_effective_dose": (activation, 1e-6),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    f = solved(PRE + "fuel.fission_rate_burnup_consumption")
    assert f["sc"] * 86400e6 * 1e3 == pytest.approx(1.23, abs=0.02)                                                       # about 1.05 g fissioned and 1.2 g consumed per MWd
    b = solved(PRE + "reactor.bare_reactor_criticality_buckling")
    assert b["ks"] > 1 and solved(PRE + "reactor.bare_reactor_criticality_buckling", R=f"{b['Rc'] * 100} cm")["ks"] == pytest.approx(1.0, abs=1e-9)   # supercritical above the critical radius, critical at it
    assert 30 < b["Mc"] < 80                                                                                              # a bare highly enriched uranium sphere: tens of kilograms
    assert solved(PRE + "reactor.point_kinetics_period_prompt_jump", rd="-1")["w"] < 0                                    # subcritical: the power falls
    k = solved(PRE + "reactor.point_kinetics_period_prompt_jump", rd="0.01")["T"]
    assert k == pytest.approx((0.0065 - 0.0000650) / (0.08 * 0.0000650), rel=0.02)                                          # small reactivity: T = (beta - rho) / (lambda rho)
    x = solved(PRE + "reactor.xenon_135_equilibrium_poisoning", ph="1e16 1/(cm^2*s)")
    assert x["P"] == pytest.approx(x["Pm"], rel=2e-3)                                                                     # at very high flux the poison reaches its limit
    assert solved(PRE + "shielding.gamma_buildup_neutron_removal", x="0 cm")["B"] == pytest.approx(1.0)
    a = solved(PRE + "radiological.activation_decay_heat_effective_dose", ti="3000 year")
    assert a["Ai"] == pytest.approx(a["As"], rel=1e-6)                                                                    # long irradiation saturates at N sigma phi


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "nuclear"
