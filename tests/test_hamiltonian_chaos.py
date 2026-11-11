"""Hamiltonian mechanics and chaos (independent computations, SI): numerical integration, quadrature and root finding written here, not the library's formulas."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, g, h, pi, solved
from scipy.integrate import quad, solve_ivp
from scipy.optimize import brentq, minimize_scalar

hbar = h / (2 * pi)


def sol_pendulum(x, t=None):
    m, L = x["m"], x["L"]
    t = x["t"] if t is None else t
    sol = solve_ivp(lambda _t, y: [y[1] / (m * L**2), -m * g * L * math.sin(y[0])], [0, t], [x["th0"], x["p0"]], method="DOP853", rtol=1e-12, atol=1e-14)
    return sol.y[0, -1], sol.y[1, -1]


def pendulum(x):
    th, p = sol_pendulum(x)
    m, L = x["m"], x["L"]
    e0 = x["p0"] ** 2 / (2 * m * L**2) - m * g * L * math.cos(x["th0"])
    en = p**2 / (2 * m * L**2) - m * g * L * math.cos(th)
    return {"th": th, "pth": p, "En": en, "E0": e0, "cn": 1.0}


def charged(x):
    m, q, b = x["m"], x["q"], x["B"]
    pos, vel = np.array([x["x"], x["y"], 0.0]), np.array([x["vx"], x["vy"], 0.0])
    a = 0.5 * np.cross([0, 0, b], pos)                                                # A = (1/2) B x r
    p = m * vel + q * a
    ll = np.cross(pos, p)[2]
    return {"Ax": a[0], "Ay": a[1], "pcx": p[0], "pcy": p[1], "Hm": float(np.dot(p - q * a, p - q * a) / (2 * m)), "Lc": ll, "Lm": float(m * np.cross(pos, vel)[2]), "wc": q * b / m,
            "rL": m * math.hypot(x["vx"], x["vy"]) / (q * b)}


def oscillator(x):
    m, k, e = x["m"], x["kk"], x["En"]
    amp = math.sqrt(2 * e / k)
    # the area of the phase-space ellipse by quadrature, with q = A sin(u) so that the integrand is smooth at the turning points
    area = 2 * quad(lambda u: math.sqrt(max(2 * m * (e - k * (amp * math.sin(u)) ** 2 / 2), 0.0)) * amp * math.cos(u), -pi / 2, pi / 2, epsabs=0, epsrel=1e-13)[0]
    w = math.sqrt(k / m)
    return {"w": w, "Ja": area / (2 * pi), "Ar": area, "nq": area / h - 0.5, "Ns": area / h, "dE": hbar * w}


def runge_lenz(x):
    m, k = x["m"], x["kk"]
    r, v = np.array([x["x"], x["y"], 0.0]), np.array([x["vx"], x["vy"], 0.0])
    p = m * v
    ang = np.cross(r, p)
    a = np.cross(p, ang) - m * k * r / np.linalg.norm(r)                                              # A = p x L - m k r/|r| in three dimensions
    en = 0.5 * m * float(v @ v) - k / np.linalg.norm(r)
    # the eccentricity from a numerical orbit: closest and farthest approach over one period
    aa = -k / (2 * en)
    period = 2 * pi * math.sqrt(m * aa**3 / k)
    sol = solve_ivp(lambda _t, y: [y[2], y[3], -k * y[0] / (m * math.hypot(y[0], y[1]) ** 3), -k * y[1] / (m * math.hypot(y[0], y[1]) ** 3)], [0, 1.02 * period], [x["x"], x["y"], x["vx"], x["vy"]],
                    method="DOP853", rtol=1e-12, atol=1e-6, dense_output=True)
    rs = np.hypot(*sol.sol(np.linspace(0, 1.02 * period, 40001))[:2])
    e_num = (rs.max() - rs.min()) / (rs.max() + rs.min())
    assert np.linalg.norm(a) / (m * k) == pytest.approx(e_num, rel=1e-4)                              # |A| / (m k) is the eccentricity of the orbit that is really followed
    return {"rr": float(np.linalg.norm(r)), "Lz": float(ang[2]), "En": en, "Ax": a[0], "Ay": a[1], "Am": float(np.linalg.norm(a)), "e1": float(np.linalg.norm(a)) / (m * k), "e2": e_num, "aa": aa, "pd": math.atan2(a[1], a[0])}


def kepler_actions(x):
    mu, k, a, e = x["mu"], x["kk"], x["aa"], x["ec"]
    ll = math.sqrt(mu * k * a * (1 - e * e))                                                          # from the angular momentum of the ellipse
    en = -k / (2 * a)
    rmin, rmax = a * (1 - e), a * (1 + e)
    def integrand(u):                                                                                  # r = rmin + (rmax - rmin) sin^2(u) removes the square-root edges
        r = rmin + (rmax - rmin) * math.sin(u) ** 2
        return math.sqrt(max(2 * mu * (en + k / r) - ll**2 / r**2, 0.0)) * 2 * (rmax - rmin) * math.sin(u) * math.cos(u)

    jr = quad(integrand, 0, pi / 2, epsabs=0, epsrel=1e-13)[0] / pi                                    # (1/2 pi) times the closed integral of p_r dr
    jt = jr + ll
    om = mu * k**2 / jt**3
    return {"L": ll, "Jt": jt, "Jr": jr, "En": en, "Om": om, "Tp": 2 * pi / om, "Tk": 2 * pi * math.sqrt(mu * a**3 / k), "nn": jt / hbar, "ll": ll / hbar}


def lorenz_rhs(s, r, b):
    def f(_t, w):
        x, y, z, ux, uy, uz = w
        return [s * (y - x), x * (r - z) - y, x * y - b * z, s * (uy - ux), (r - z) * ux - uy - x * uz, y * ux + x * uy - b * uz]
    return f


def lorenz(x):
    sol = solve_ivp(lorenz_rhs(x["sg"], x["rh"], x["bt"]), [0, x["t"]], [x["x0"], x["y0"], x["z0"], 1, 0, 0], method="DOP853", rtol=1e-12, atol=1e-14)
    w = sol.y[:, -1]
    return {"x": w[0], "y": w[1], "z": w[2], "ux": w[3], "uy": w[4], "uz": w[5], "lam": math.log(float(np.linalg.norm(w[3:]))) / x["t"]}


def lorenz_analytic(x):
    s, r, b = x["sg"], x["rh"], x["bt"]
    xs = math.sqrt(b * (r - 1))

    def worst(rho):                                                                                    # largest real part of the Jacobian at the fixed point (x*, x*, rho - 1)
        xr = math.sqrt(b * (rho - 1))
        jac = np.array([[-s, s, 0], [1, -1, -xr], [xr, xr, -b]])
        return float(np.max(np.linalg.eigvals(jac).real))

    rh = brentq(worst, 15, 40)                                                                         # where the fixed point stops being stable
    div = -(s + 1 + b)                                                                                # trace of the Jacobian
    l3 = div - x["l1"]
    assert abs(float(np.linalg.eigvals(np.array([[-s, s, 0], [1, -1, -xs], [xs, xs, -b]])).real.sum()) - div) < 1e-9
    f = [s * (xs - xs), xs * (r - (r - 1)) - xs, xs * xs - b * (r - 1)]
    assert max(abs(v) for v in f) < 1e-9
    return {"xs": xs, "zs": r - 1, "rH": rh, "rr": r / rh, "ct": div, "l3": l3, "dk": 2 + x["l1"] / abs(l3)}


def logistic(x):
    r = x["r"]
    f = lambda u: r * u * (1 - u)                                                                     # noqa: E731
    xf = brentq(lambda u: f(u) - u, 0.2, 0.99)
    cyc = sorted(set(round(v, 12) for v in _cycle(f, 0.4)))
    xa, xb = cyc[0], cyc[1]
    mc = r * (1 - 2 * xa) * r * (1 - 2 * xb)
    u, acc, n = 0.4, 0.0, 200000
    for _ in range(1000):
        u = f(u)
    for _ in range(n):
        acc += math.log(abs(r * (1 - 2 * u)))
        u = f(u)
    r2 = 1 + math.sqrt(6)
    return {"xf": xf, "mf": r * (1 - 2 * xf), "xa": xa, "xb": xb, "mc": mc, "ly": acc / n, "r2": r2, "r3": r2 + (r2 - 3) / 4.66920160910299, "ri": r2 + (r2 - 3) / (4.66920160910299 - 1)}


def _cycle(f, u):
    for _ in range(5000):
        u = f(u)
    out = []
    for _ in range(2):
        out.append(u)
        u = f(u)
    return out


def melnikov(x):
    dd, om, gm = x["dd"], x["om"], x["gm"]
    y0 = lambda t: -math.sqrt(2) / math.cosh(t) * math.tanh(t)                                       # noqa: E731  homoclinic orbit of x'' = x - x^3
    damp = quad(lambda t: y0(t) ** 2, -40, 40, limit=400)[0] * dd

    def peak(gamma):
        # M(t0) = integral of y0 (gamma cos(om (t + t0)) - dd y0) dt, maximised over t0 (coarse grid, then a bounded search)
        mt = lambda t0: gamma * quad(lambda t: y0(t) * math.cos(om * (t + t0)), -40, 40, limit=800)[0] - damp           # noqa: E731
        grid = np.linspace(0, 2 * pi / om, 13)
        t_best = grid[int(np.argmax([mt(t0) for t0 in grid]))]
        step = 2 * pi / om / 12
        res = minimize_scalar(lambda t0: -mt(t0), bounds=(t_best - step, t_best + step), method="bounded", options={"xatol": 1e-10})
        return -res.fun
    gc = brentq(peak, 1e-3, 5, xtol=1e-9)
    return {"gc": gc, "rg": gm / gc, "Mm": peak(gm), "ch": 1.0 if gm > gc else 0.0}


def predict(x):
    ly, d0, dt, kf = x["ly"], x["d0"], x["dt"], x["kf"]
    top = 1e2 / ly
    th = brentq(lambda t: d0 * math.exp(ly * t) - dt, 0, top)                                        # when d0 e^(lambda t) reaches the tolerance
    return {"tl": 1 / ly, "t2": brentq(lambda t: math.exp(ly * t) - 2, 0, top), "th": th, "gn": brentq(lambda t: math.exp(ly * t) - kf, 0, top), "fo": dt / d0}


def bifurcations(x):
    mu = x["mu"]
    d = lambda f, u: (f(u + 1e-6) - f(u - 1e-6)) / 2e-6                                              # noqa: E731
    sn = lambda u: -mu + u * u                                                                       # noqa: E731
    tc = lambda u: mu * u - u * u                                                                    # noqa: E731
    pf = lambda u: mu * u - u**3                                                                     # noqa: E731
    xsn = brentq(sn, 0, 10)
    xpf = brentq(pf, 1e-3, 10)
    return {"xsn": xsn, "esn": d(sn, xsn), "etc": d(tc, mu), "xpf": xpf, "epf": d(pf, xpf), "opf": d(pf, 0.0), "rho": xpf, "Th": 2 * pi / x["wh"], "tr": 1 / abs(d(pf, xpf))}


CASES = {
    "physics.analytical.hamilton_pendulum_trajectory": pendulum, "physics.analytical.charged_particle_canonical_momentum": charged, "physics.analytical.oscillator_action_bohr_sommerfeld": oscillator,
    "physics.analytical.laplace_runge_lenz": runge_lenz, "physics.analytical.kepler_action_variables": kepler_actions, "physics.nonlinear.lorenz_lyapunov": lorenz, "physics.nonlinear.lorenz_fixed_points_hopf": lorenz_analytic,
    "physics.nonlinear.logistic_map_period_doubling": logistic, "physics.nonlinear.melnikov_duffing_threshold": melnikov, "physics.nonlinear.predictability_horizon": predict, "physics.nonlinear.bifurcation_normal_forms": bifurcations,
}

REL = {"physics.analytical.hamilton_pendulum_trajectory": 2e-5, "physics.nonlinear.lorenz_lyapunov": 1e-4, "physics.analytical.laplace_runge_lenz": 1e-4, "physics.analytical.kepler_action_variables": 1e-6,
       "physics.nonlinear.logistic_map_period_doubling": 1e-3, "physics.nonlinear.melnikov_duffing_threshold": 2e-3, "physics.nonlinear.bifurcation_normal_forms": 1e-5, "physics.analytical.oscillator_action_bohr_sommerfeld": 1e-6}


def test_there_are_eleven_cases():
    assert len(CASES) == 11


@pytest.mark.parametrize("cid", sorted(set(CASES) - {"physics.analytical.hamilton_pendulum_trajectory"}))
def test_worked_example_matches_independent_computation(cid):
    check_case(cid, CASES[cid], rel=REL.get(cid, 1e-6))


def test_pendulum_trajectory_matches_and_conserves_energy():
    cid = "physics.analytical.hamilton_pendulum_trajectory"
    got = solved(cid)
    from pcutil import si_inputs

    want = pendulum(si_inputs(cid))
    for k in ("th", "pth", "En", "E0"):
        assert got[k] == pytest.approx(want[k], rel=2e-5, abs=1e-9), k
    assert solved(cid, th0="170 deg", t="0.001 s")["cn"] == 1
    assert got["cn"] == 1                                                                              # energy is conserved by the integration to better than one part in a million


def test_hamilton_equations_give_the_lorentz_force():
    """-dH/dx at fixed canonical momentum equals the x component of the Lorentz force q v x B (a check of the gauge bookkeeping, by finite differences)."""
    m, q, b = 9.109e-31, 1.602e-19, 0.01
    x0, y0, vx, vy = 1e-3, 0.0, 0.0, 1e6
    ham = lambda x, y, px, py: ((px + q * b * y / 2) ** 2 + (py - q * b * x / 2) ** 2) / (2 * m)       # noqa: E731  H = (p - qA)^2 / 2m
    px, py = m * vx - q * b * y0 / 2, m * vy + q * b * x0 / 2
    eps = 1e-8
    dhdx = (ham(x0 + eps, y0, px, py) - ham(x0 - eps, y0, px, py)) / (2 * eps)
    dhdy = (ham(x0, y0 + eps, px, py) - ham(x0, y0 - eps, px, py)) / (2 * eps)
    force = q * np.cross([vx, vy, 0], [0, 0, b])
    assert -dhdx == pytest.approx(force[0], rel=1e-4) and -dhdy == pytest.approx(force[1], abs=1e-9 * abs(force[0]))


def test_benchmarks_and_identities():
    assert solved("physics.analytical.kepler_action_variables")["nn"] == pytest.approx(2, rel=1e-4)                       # the n = 2, l = 1 Sommerfeld ellipse
    assert solved("physics.analytical.kepler_action_variables")["ll"] == pytest.approx(1, rel=1e-4)
    assert solved("physics.analytical.kepler_action_variables")["Tp"] == pytest.approx(solved("physics.analytical.kepler_action_variables")["Tk"], rel=1e-9)   # dE/dJ gives Kepler's third law
    assert solved("physics.analytical.laplace_runge_lenz")["e1"] == pytest.approx(solved("physics.analytical.laplace_runge_lenz")["e2"], rel=1e-9)
    assert solved("physics.nonlinear.lorenz_fixed_points_hopf")["rH"] == pytest.approx(24.737, abs=1e-3)                    # the classic ρ = 24.74
    assert solved("physics.nonlinear.lorenz_fixed_points_hopf")["dk"] == pytest.approx(2.062, abs=1e-3)                     # the known Kaplan–Yorke dimension of the Lorenz attractor
    assert solved("physics.nonlinear.logistic_map_period_doubling")["r3"] == pytest.approx(3.5441, rel=1e-3) and solved("physics.nonlinear.logistic_map_period_doubling")["ri"] == pytest.approx(3.5699, rel=1e-3)
    assert solved("physics.nonlinear.predictability_horizon")["t2"] == pytest.approx(solved("physics.nonlinear.predictability_horizon")["tl"] * math.log(2))
    assert solved("physics.nonlinear.melnikov_duffing_threshold", gm="0.1")["ch"] == 0 and solved("physics.nonlinear.melnikov_duffing_threshold")["ch"] == 1


def test_lorenz_at_twenty_time_units_still_agrees_with_an_independent_integration():
    from pcutil import si_inputs

    cid = "physics.nonlinear.lorenz_lyapunov"
    x = {**si_inputs(cid), "t": 20.0}
    got = solved(cid, t="20")
    want = lorenz(x)
    for k in ("x", "y", "z", "lam"):
        assert got[k] == pytest.approx(want[k], rel=5e-4), k                                           # 20 time units is about the limit of agreement between two integrators


def test_lorenz_trajectory_is_only_reproducible_for_a_few_lyapunov_times():
    """The calculation's own documented limit: a change of 1e-9 in the start changes x(t) a lot after t = 40 but not at t = 10."""
    from pcutil import si_inputs

    x = si_inputs("physics.nonlinear.lorenz_lyapunov")
    for t, same in ((10, True), (40, False)):
        a = lorenz({**x, "t": t})["x"]
        b = lorenz({**x, "t": t, "x0": x["x0"] + 1e-9})["x"]
        assert bool(abs(a - b) < 1e-3) is same


def test_catalogued_with_a_sub_discipline_and_reference():
    for cid in CASES:
        c = CAT.get(cid)
        assert c.subdisciplines and c.references
    assert all("Nonlinear Dynamics and Chaos" in CAT.get(c).subdisciplines for c in CASES if ".nonlinear." in c)
