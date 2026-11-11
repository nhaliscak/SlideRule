"""Equation-audit fill, chemical engineering B: complex-fluid and two-phase flow, explosions, functional safety, crystallisation, membranes, adsorption, evaporation, fouling, absorption, slurries, thickening, cooling towers and flames."""

import math

import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize

PRE = "chemical."


def nonnewt(x):
    n, K, D, v, L, rho, mp, t0 = (x[k] for k in ("n", "K", "D", "v", "Lp", "rho", "mp", "t0"))
    R = D / 2

    def mean_velocity(tw):                                                       # integrate the power-law velocity profile u(r) = int_r^R (tau/K)^(1/n) dr
        u = lambda r: integrate.quad(lambda s: (tw * s / R / K) ** (1 / n), r, R)[0]
        return 2 / R ** 2 * integrate.quad(lambda r: u(r) * r, 0, R)[0]
    tw = optimize.brentq(lambda t: mean_velocity(t) - v, 1e-6, 1e4, xtol=1e-12)
    Kp = K * ((3 * n + 1) / (4 * n)) ** n
    return {"tw": tw, "Re": rho * v ** (2 - n) * D ** n / (Kp * 8 ** (n - 1)), "dpp": 4 * tw * L / D, "dpb": 32 * mp * v * L / D ** 2 + 16 * t0 * L / (3 * D)}


def twophase(x):
    X2 = x["dl"] / x["dg"]
    ph = 1 + x["Cc"] / math.sqrt(X2) + 1 / X2
    r = x["rg"] / x["rl"]
    q = x["xq"]
    return {"X2": X2, "ph": ph, "dp": ph * x["dl"] * x["Lp"], "ah": q / r / (q / r + 1 - q) if False else 1 / (1 + (1 - q) / q * r), "az": 1 / (1 + (1 - q) / q * r ** (2 / 3))}


def tnt(x):
    W = x["ef"] * x["m"] * x["dh"] / 4.68e6                                      # SI: J/kg heat of combustion vs 4.68 MJ/kg for TNT
    W = x["ef"] * x["m"] * x["dh"] / 4.68e6
    Z = x["Rd"] / W ** (1 / 3)
    pr = 808 * (1 + (Z / 4.5) ** 2) / (math.sqrt(1 + (Z / 0.048) ** 2) * math.sqrt(1 + (Z / 0.32) ** 2) * math.sqrt(1 + (Z / 1.35) ** 2))
    return {"Wt": W, "Z": Z, "pr": pr, "ps": pr * x["pa"]}


def sil(x):
    lt = x["lm"] * x["TI"]
    band = lambda p: 4 if p < 1e-5 else 3 if p < 1e-3 else 2 if p < 1e-2 else 1 if p < 1e-1 else 0
    P1, P2, P3 = lt / 2, lt ** 2 / 3, lt ** 2
    return {"P1": P1, "P2": P2, "P3": P3, "R1": 1 / P1, "S1": band(P1), "S2": band(P2), "S3": band(P3)}


def msmpr(x):
    sg = (x["C"] - x["Cs"]) / x["Cs"]
    G = x["kg"] * sg ** x["gx"]
    n0 = x["J"] / G
    tau = x["tau"]
    n = lambda L: n0 * math.exp(-L / (G * tau))
    MT = x["rc"] * x["kv"] * integrate.quad(lambda L: L ** 3 * n(L), 0, 80 * G * tau)[0]     # third moment of the size distribution
    Ld = optimize.minimize_scalar(lambda L: -L ** 3 * n(L), bounds=(1e-12, 20 * G * tau), method="bounded", options={"xatol": 1e-14}).x
    return {"sg": sg, "G": G, "Ld": Ld, "n0": n0, "MT": MT}


def ro(x):
    pif = x["iv"] * x["Cf"] / x["Mw"] * x["Rg"] * x["T"]
    def f(Jw):
        Cp = x["Bs"] * x["Cf"] / (Jw + x["Bs"])
        return Jw - x["Aw"] * (x["dp"] - pif + x["iv"] * Cp / x["Mw"] * x["Rg"] * x["T"])
    Jw = optimize.brentq(f, 1e-12, 1e-3, xtol=1e-18)
    Cp = x["Bs"] * x["Cf"] / (Jw + x["Bs"])
    return {"pif": pif, "Jw": Jw, "Cp": Cp, "rj": 1 - Cp / x["Cf"]}


def thomas(x):
    cr = 1 / (1 + math.exp(x["kT"] / x["Q"] * (x["q0"] * x["m"] - x["Cf"] * x["Vt"])))
    ts = x["N0"] / (x["Cf"] * x["vb"]) * x["Zb"] - math.log(x["Cf"] / x["Cb"] - 1) / (x["Ka"] * x["Cf"])
    return {"cr": cr, "ts": ts}


def evap(x):
    V = (x["S"] * x["ls"] - x["F"] * x["cp"] * (x["Tb"] - x["Tf"])) / x["lv"]
    return {"Vv": V, "ec": V / x["S"], "Ah": x["S"] * x["ls"] / (x["U"] * x["dT"]), "eN": 0.85 * x["Ne"]}


def fouling(x):
    Rw = x["do"] * math.log(x["do"] / x["di"]) / (2 * x["kw"])
    Uc = 1 / (1 / x["ho"] + Rw + x["do"] / (x["hi"] * x["di"]))
    Ud = 1 / (1 / Uc + x["Rfo"] + x["Rfi"] * x["do"] / x["di"])
    return {"Uc": Uc, "Ud": Ud, "cf": Ud / Uc, "ar": Uc / Ud - 1}


def hatta(x):
    Ha = math.sqrt(x["kr"] * x["DA"]) / x["kL"]
    Ef = Ha / math.tanh(Ha)
    Ei = 1 + x["DB"] * x["CB"] / (x["nu"] * x["DA"] * x["Cs"])
    E = min(Ef, Ei)
    return {"Ha": Ha, "Ef": Ef, "Ei": Ei, "E": E, "Nf": E * x["kL"] * x["Cs"]}


def durand(x):
    Sg = x["rs"] / x["rl"]
    Vc = x["FL"] * math.sqrt(2 * 9.80665 * x["D"] * (Sg - 1))
    return {"Sg": Sg, "rm": x["rl"] * (1 + x["Cv"] * (Sg - 1)), "Vc": Vc, "Qc": Vc * math.pi * x["D"] ** 2 / 4}


def thick(x):
    Fs = x["F"] * x["C0"]
    ua = (1 / x["Ci"] - 1 / x["Cu"]) / x["vi"]
    At = Fs * ua
    return {"Fs": Fs, "ua": ua, "At": At, "Dt": math.sqrt(4 * At / math.pi), "ld": Fs / At}


def hsat_minus_ha(x, frac):
    Tc = x["Two"] - 273.15 + frac * (x["Twi"] - x["Two"])                       # degC
    pw = 611.2 * math.exp(17.62 * Tc / (243.12 + Tc))                             # Magnus saturation pressure, Pa
    W = 0.622 * pw / (x["P"] - pw)
    hs = 1006 * Tc + W * (2.501e6 + 1860 * Tc)                                    # J/kg dry air
    return hs - x["ha1"] - x["LG"] * 4186 * frac * (x["Twi"] - x["Two"])


def merkel(x):
    out = {f"h{i + 1}": hsat_minus_ha(x, f) for i, f in enumerate((0.1, 0.4, 0.6, 0.9))}
    out["Me"] = 4186 * (x["Twi"] - x["Two"]) / 4 * sum(1 / out[k] for k in ("h1", "h2", "h3", "h4"))
    return out


def flame(x):
    ph = x["ph"]
    al, be = 2.18 - 0.8 * (ph - 1), -0.16 + 0.22 * (ph - 1)
    SL = x["S0"] * (x["Tu"] / x["T0"]) ** al * (x["P"] / x["P0"]) ** be
    return {"al": al, "be": be, "SL": SL, "dl": x["dth"] / SL}


CASES = {
    PRE + "fluid.non_newtonian_pipe_flow": (nonnewt, 1e-5), PRE + "fluid.two_phase_lockhart_martinelli": (twophase, 1e-9), PRE + "safety.tnt_equivalent_overpressure": (tnt, 1e-9),
    PRE + "safety.sil_pfd_architectures": (sil, 1e-9), PRE + "crystallization.msmpr_population_balance": (msmpr, 1e-5), PRE + "membrane.reverse_osmosis_flux_rejection": (ro, 1e-6),
    PRE + "adsorption.thomas_breakthrough_bdst": (thomas, 1e-9), PRE + "operations.single_effect_evaporator": (evap, 1e-9), PRE + "heat_transfer.exchanger_fouling_overall_u": (fouling, 1e-9),
    PRE + "mass_transfer.gas_absorption_hatta_enhancement": (hatta, 1e-9), PRE + "slurry.critical_deposition_velocity_durand": (durand, 1e-6), PRE + "operations.thickener_talmage_fitch": (thick, 1e-9),
    PRE + "operations.cooling_tower_merkel_number": (merkel, 1e-9), PRE + "combustion.laminar_flame_speed_scaling": (flame, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_hatta_enhancement_matches_the_film_reaction_diffusion_problem():
    import numpy as np
    from scipy.integrate import solve_bvp
    r = solved(PRE + "mass_transfer.gas_absorption_hatta_enhancement", kr="0.05 1/s")                   # Ha = 2
    D, kL, Cs = 1.8e-6, 1.5e-4, 20.0
    d = D / kL                                                                                          # film thickness
    sol = solve_bvp(lambda z, y: np.vstack([y[1], 0.05 / D * y[0]]), lambda a, b: np.array([a[0] - Cs, b[0]]), np.linspace(0, d, 200), np.vstack([Cs * (1 - np.linspace(0, 1, 200)), -Cs / d * np.ones(200)]), tol=1e-10)
    E = -D * sol.sol(0)[1] / (kL * Cs)
    assert r["Ef"] == pytest.approx(E, rel=1e-4)


def test_sil_formulas_match_time_averaged_failure_probability():
    lt = 2.0e-6 * 8766
    q = lambda t: 1 - math.exp(-lt * t)                                                                 # unavailability of one channel at t/TI
    for key, f in (("P1", q), ("P2", lambda t: q(t) ** 2), ("P3", lambda t: 3 * q(t) ** 2 - 2 * q(t) ** 3)):
        avg = integrate.quad(f, 0, 1)[0]
        assert solved(PRE + "safety.sil_pfd_architectures")[key] == pytest.approx(avg, rel=0.05)


def test_thomas_curve_crosses_one_half_at_the_stoichiometric_volume():
    assert solved(PRE + "adsorption.thomas_breakthrough_bdst", Vt=f"{35 * 20 / 50 / 1.0} L")["cr"] == pytest.approx(0.5, abs=1e-9)


def test_merkel_four_point_rule_agrees_with_the_exact_integral():
    x = {"Two": 302.15, "Twi": 313.15, "LG": 1.2, "ha1": 62000.0, "P": 101325.0}
    exact = integrate.quad(lambda f: 4186 * (x["Twi"] - x["Two"]) / hsat_minus_ha(x, f), 0, 1)[0]
    assert solved(PRE + "operations.cooling_tower_merkel_number")["Me"] == pytest.approx(exact, rel=0.01)


def test_limits():
    assert solved(PRE + "fluid.non_newtonian_pipe_flow", n="1.0", t0="0 Pa")["dpp"] == pytest.approx(solved(PRE + "fluid.non_newtonian_pipe_flow", n="1.0", t0="0 Pa", mp="1800 mPa*s")["dpb"], rel=1e-9)   # n = 1, K = mu: Poiseuille, same as a Newtonian Bingham fluid
    assert solved(PRE + "fluid.two_phase_lockhart_martinelli")["az"] < solved(PRE + "fluid.two_phase_lockhart_martinelli")["ah"]
    assert solved(PRE + "mass_transfer.gas_absorption_hatta_enhancement", kr="1e-6 1/s")["Ef"] == pytest.approx(1.0, abs=1e-4)       # slow reaction: no enhancement
    assert solved(PRE + "membrane.reverse_osmosis_flux_rejection", dp="20 bar")["Jw"] < solved(PRE + "membrane.reverse_osmosis_flux_rejection")["Jw"]
    assert solved(PRE + "combustion.laminar_flame_speed_scaling", P="101.3 kPa", Tu="298 K")["SL"] == pytest.approx(34 / 100, rel=1e-9)   # reference state returns the reference speed (m/s)


def test_catalogued():
    for cid in CASES:
        assert "chemical" in CAT.get(cid).disciplines
