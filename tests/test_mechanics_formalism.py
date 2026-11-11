"""Inertia tensor, canonical transformations, Hamilton–Jacobi, Noether, the standard and Hénon maps, fractal dimension (independent computations, SI)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, pi, solved
from scipy.integrate import quad, solve_ivp


def tensor(x):
    t = np.array([[x["Ixx"], -x["Ixy"], -x["Ixz"]], [-x["Ixy"], x["Iyy"], -x["Iyz"]], [-x["Ixz"], -x["Iyz"], x["Izz"]]])
    ev = np.linalg.eigvalsh(t)
    q = float(np.trace(t) / 3)
    dev = t - q * np.eye(3)
    p = math.sqrt(float(np.sum(dev**2)) / 6)                                                           # the spread of the principal moments
    r = float(np.linalg.det(dev / p) / 2)
    return {"Ia": ev[2], "Ib": ev[1], "Ic": ev[0], "qm": q, "pp": p, "rr": r, "ph": math.acos(r) / 3}


def rigid_body(x):
    t = np.array([[x["Ixx"], -x["Ixy"], -x["Ixz"]], [-x["Ixy"], x["Iyy"], -x["Iyz"]], [-x["Ixz"], -x["Iyz"], x["Izz"]]])
    w = np.array([x["wx"], x["wy"], x["wz"]])
    ang = t @ w
    return {"Lx": ang[0], "Ly": ang[1], "Lz": ang[2], "Lm": float(np.linalg.norm(ang)), "an": math.acos(float(w @ ang / (np.linalg.norm(w) * np.linalg.norm(ang)))), "Tk": float(0.5 * w @ ang)}


def canonical(x):
    a, b, c, d, m, k = x["a"], x["b"], x["c"], x["d"], x["m"], x["kk"]
    # the Poisson bracket from finite differences of the map (q, p) -> (Q, P)
    f = lambda q, p: (a * q + b * p, c * q + d * p)                                                    # noqa: E731
    e = 1e-3
    dQdq = (f(e, 0)[0] - f(-e, 0)[0]) / (2 * e)
    dQdp = (f(0, e)[0] - f(0, -e)[0]) / (2 * e)
    dPdq = (f(e, 0)[1] - f(-e, 0)[1]) / (2 * e)
    dPdp = (f(0, e)[1] - f(0, -e)[1]) / (2 * e)
    pb = dQdq * dPdp - dQdp * dPdq
    # the new Hamiltonian: transform points back and fit the three coefficients by least squares
    rng = np.random.default_rng(1)
    qq, pp_ = rng.normal(size=40), rng.normal(size=40)
    rows, rhs = [], []
    for q, p in zip(qq, pp_):
        bq, bp = f(q, p)
        rows.append([bp**2, bq**2, bq * bp])
        rhs.append(p**2 / (2 * m) + k * q**2 / 2)
    sol = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0]
    return {"pb": pb, "cn": 1.0 if abs(pb - 1) < 1e-9 else 0.0, "hPP": sol[0], "hQQ": sol[1], "hQP": sol[2]}


def action_angle(x):
    m, k, q0, p0, t = x["m"], x["kk"], x["q0"], x["p0"], x["t"]
    sol = solve_ivp(lambda _t, y: [y[1] / m, -k * y[0]], [0, t], [q0, p0], method="DOP853", rtol=1e-12, atol=1e-14)
    q1, p1 = sol.y[0, -1], sol.y[1, -1]
    w = math.sqrt(k / m)
    en = p0**2 / (2 * m) + k * q0**2 / 2
    ja = en / w
    ph = math.atan2(m * w * q0, p0)
    # {q, p} in the new variables by finite differences of (J, phi) -> (q, p)
    qp = lambda j, f: (math.sqrt(2 * j / (m * w)) * math.sin(f), math.sqrt(2 * j * m * w) * math.cos(f))        # noqa: E731
    e = 1e-7
    dqdj, dpdj = [(a - b) / (2 * e * ja) for a, b in zip(qp(ja * (1 + e), ph), qp(ja * (1 - e), ph))]
    dqdf, dpdf = [(a - b) / (2 * e) for a, b in zip(qp(ja, ph + e), qp(ja, ph - e))]
    return {"w": w, "En": en, "Ja": ja, "f0": ph, "pb": dqdf * dpdj - dqdj * dpdf, "f1": ph + w * t, "q1": q1, "p1": p1, "E1": p1**2 / (2 * m) + k * q1**2 / 2}


def hamilton_jacobi(x):
    m, k, e, q = x["m"], x["kk"], x["En"], x["q"]
    w = math.sqrt(k / m)
    pmom = lambda u: math.sqrt(max(2 * m * (e - k * u * u / 2), 0.0))                                   # noqa: E731
    amp = math.sqrt(2 * e / k)
    # W from the integral of p dq, and the time from the integral of dt = m dq / p, both by quadrature in u with q = A sin(u)
    uq = math.asin(q / amp)
    big_w = quad(lambda u: pmom(amp * math.sin(u)) * amp * math.cos(u), 0, uq, epsabs=0, epsrel=1e-13)[0]
    tz = quad(lambda u: m * amp * math.cos(u) / max(pmom(amp * math.sin(u)), 1e-300), 0, uq, epsabs=0, epsrel=1e-12)[0]
    return {"w": w, "am": amp, "pp": pmom(q), "W": big_w, "tz": tz, "Tp": 2 * pi / w}


def noether(x):
    m, kx, ky = x["m"], x["kx"], x["ky"]

    def rhs(_t, s):
        return [s[2], s[3], -kx * s[0] / m, -ky * s[1] / m]

    sol = solve_ivp(rhs, [0, x["t"]], [x["x0"], x["y0"], x["ux"], x["uy"]], method="DOP853", rtol=1e-12, atol=1e-14)
    x1, y1, vx1, vy1 = sol.y[:, -1]
    fx, fy = -kx * x["x0"], -ky * x["y0"]
    l0 = m * (x["x0"] * x["uy"] - x["y0"] * x["ux"])
    l1 = m * (x1 * vy1 - y1 * vx1)
    return {"wx": math.sqrt(kx / m), "wy": math.sqrt(ky / m), "tq": x["x0"] * fy - x["y0"] * fx, "L0": l0, "x1": x1, "y1": y1, "vx1": vx1, "vy1": vy1, "L1": l1, "dL": l1 - l0,
            "Ex0": m * x["ux"] ** 2 / 2 + kx * x["x0"] ** 2 / 2, "Ex1": m * vx1**2 / 2 + kx * x1**2 / 2}


def std_map_jacobian(k, th, p):
    # the Jacobian of (th, p) -> (th + p', p') with p' = p + K sin th, found by finite differences
    def f(v):
        pn = v[1] + k * math.sin(v[0])
        return np.array([v[0] + pn, pn])
    jac = np.zeros((2, 2))
    for i in range(2):
        d = np.zeros(2)
        d[i] = 1e-6
        jac[:, i] = (f(np.array([th, p]) + d) - f(np.array([th, p]) - d)) / 2e-6
    return jac


def standard_map(x):
    k = x["K"]
    j0, j1 = std_map_jacobian(k, 0.0, 0.0), std_map_jacobian(k, pi, 0.0)
    ev = np.linalg.eigvals(j1)
    return {"t0": float(np.trace(j0)), "t1": float(np.trace(j1)), "el": 1.0 if abs(np.trace(j1)) < 2 else 0.0, "om": float(abs(np.angle(ev[0]))), "rK": k / 0.971635406, "rg": 1.0 if k < 0.971635406 else 2.0,
            "Dq": k**2 / 4, "ly": max(0.0, math.log(k / 2))}


def henon(x):
    a, b, l1 = x["a"], x["b"], x["l1"]
    roots = np.roots([a, 1 - b, -1.0])                                                                  # a x^2 + (1 - b) x - 1 = 0
    xp, xm = float(max(roots)), float(min(roots))
    jac = np.array([[-2 * a * xp, 1.0], [b, 0.0]])
    mu = sorted(np.linalg.eigvals(jac).real)
    l2 = math.log(b) - l1
    return {"xp": xp, "xm": xm, "m1": mu[0], "m2": mu[1], "ar": abs(float(np.linalg.det(jac))), "l2": l2, "dk": 1 + l1 / abs(l2)}


def fractal(x):
    return {"Ds": math.log(x["Np"]) / math.log(x["sc"]), "Db": math.log(x["N2"] / x["N1"]) / math.log(x["e1"] / x["e2"]), "N3": x["N2"] * (x["e2"] / x["e3"]) ** (math.log(x["N2"] / x["N1"]) / math.log(x["e1"] / x["e2"]))}


CASES = {
    "physics.analytical.inertia_tensor_3d": tensor, "physics.analytical.rigid_body_angular_momentum_3d": rigid_body, "physics.analytical.linear_canonical_transformation": canonical, "physics.analytical.canonical_action_angle_oscillator": action_angle,
    "physics.analytical.hamilton_jacobi_oscillator": hamilton_jacobi, "physics.analytical.noether_anisotropic_oscillator": noether, "physics.nonlinear.standard_map_stability": standard_map,
    "physics.nonlinear.henon_map_properties": henon, "physics.nonlinear.fractal_dimension": fractal,
}

REL = {"physics.analytical.canonical_action_angle_oscillator": 1e-6, "physics.analytical.linear_canonical_transformation": 1e-5, "physics.analytical.noether_anisotropic_oscillator": 2e-6, "physics.nonlinear.standard_map_stability": 1e-5}


def test_there_are_nine_cases():
    assert len(CASES) == 9


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_computation(cid):
    check_case(cid, CASES[cid], rel=REL.get(cid, 1e-6))


def test_inertia_tensor_special_cases():
    # a diagonal tensor: the principal moments are the diagonal, L is parallel to the rotation axis only on a principal axis
    diag = dict(Ixy="0 kg*m^2", Ixz="0 kg*m^2", Iyz="0 kg*m^2")
    r = solved("physics.analytical.inertia_tensor_3d", **diag)
    assert (r["Ia"], r["Ib"], r["Ic"]) == pytest.approx((0.25, 0.20, 0.12)) and r["Ia"] + r["Ib"] + r["Ic"] == pytest.approx(0.57)         # the trace is invariant
    assert solved("physics.analytical.rigid_body_angular_momentum_3d", **diag, wx="0 rad/s", wy="0 rad/s", wz="10 rad/s")["an"] == pytest.approx(0, abs=1e-6)     # about a principal axis L is parallel to ω
    assert solved("physics.analytical.rigid_body_angular_momentum_3d", **diag, wx="10 rad/s", wy="10 rad/s", wz="0 rad/s")["an"] > 1e-3                          # about a non-principal axis it is not
    # a rotated body has the same principal moments: rotate the tensor about z by 30 degrees
    th = math.radians(30)
    rot = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    t = rot @ np.diag([0.12, 0.2, 0.25]) @ rot.T
    r = solved("physics.analytical.inertia_tensor_3d", Ixx=f"{t[0, 0]} kg*m^2", Iyy=f"{t[1, 1]} kg*m^2", Izz="0.25 kg*m^2", Ixy=f"{-t[0, 1]} kg*m^2", Ixz="0.0000001 kg*m^2", Iyz="0.0000001 kg*m^2")
    assert (r["Ia"], r["Ib"], r["Ic"]) == pytest.approx((0.25, 0.20, 0.12), rel=1e-6)


def test_canonical_flag_and_oscillator_invariance():
    ok = solved("physics.analytical.linear_canonical_transformation")
    assert ok["cn"] == 1 and ok["pb"] == pytest.approx(1)
    bad = solved("physics.analytical.linear_canonical_transformation", d="1.5")                        # a stretch of p alone is not canonical
    assert bad["cn"] == 0 and bad["pb"] == pytest.approx(1.2 * 1.5 - 0.2)
    rot = solved("physics.analytical.linear_canonical_transformation", a=str(math.cos(0.3)), d=str(math.cos(0.3)), b=f"{math.sin(0.3)} s/kg", c=f"{-math.sin(0.3)} kg/s")
    assert rot["cn"] == 1                                                                              # a rotation in phase space preserves the bracket


def test_action_angle_and_hamilton_jacobi_benchmarks():
    r = solved("physics.analytical.canonical_action_angle_oscillator")
    assert r["En"] == pytest.approx(r["E1"], rel=1e-12) and r["pb"] == pytest.approx(1, rel=1e-12)       # energy and the bracket are both preserved
    assert solved("physics.analytical.canonical_action_angle_oscillator", t="0 s")["q1"] == pytest.approx(0.05)
    r2 = solved("physics.analytical.hamilton_jacobi_oscillator", q="0.0001 m")
    assert r2["tz"] == pytest.approx(0.0001 / (math.sqrt(2 * 0.4 / 0.5)), rel=1e-3)                    # near the crossing the speed is the maximum speed
    h = solved("physics.analytical.hamilton_jacobi_oscillator")
    dq = 1e-6
    wp = solved("physics.analytical.hamilton_jacobi_oscillator", q=f"{0.03 + dq} m")["W"]
    wm = solved("physics.analytical.hamilton_jacobi_oscillator", q=f"{0.03 - dq} m")["W"]
    assert (wp - wm) / (2 * dq) == pytest.approx(h["pp"], rel=1e-6)                                    # p = dW/dq
    de = 1e-6
    wpe = solved("physics.analytical.hamilton_jacobi_oscillator", En=f"{0.4 + de} J")["W"]
    wme = solved("physics.analytical.hamilton_jacobi_oscillator", En=f"{0.4 - de} J")["W"]
    assert (wpe - wme) / (2 * de) == pytest.approx(h["tz"], rel=1e-5)                                  # t = dW/dE


def test_noether_conservation_only_for_the_symmetric_potential():
    sym = solved("physics.analytical.noether_anisotropic_oscillator", ky="100 N/m")
    assert sym["tq"] == pytest.approx(0, abs=1e-12) and sym["dL"] == pytest.approx(0, abs=1e-12)           # kx = ky: rotation symmetry, L is conserved
    brk = solved("physics.analytical.noether_anisotropic_oscillator")
    assert abs(brk["dL"]) > 0.01 and brk["tq"] == pytest.approx(-0.25)
    assert brk["Ex0"] == pytest.approx(brk["Ex1"])                                                       # the x energy is conserved all the same


def test_standard_map_against_iteration():
    # the Lyapunov exponent for K = 10 by iterating the map with its tangent vector
    k = 10.0
    th, p, v, acc, n = 1.0, 0.5, np.array([1.0, 0.0]), 0.0, 20000
    for _ in range(n):
        pn = p + k * math.sin(th)
        jac = np.array([[1 + k * math.cos(th), 1.0], [k * math.cos(th), 1.0]])
        th, p = th + pn, pn
        v = jac @ v
        nv = np.linalg.norm(v)
        acc += math.log(nv)
        v /= nv
    assert solved("physics.nonlinear.standard_map_stability", K="10")["ly"] == pytest.approx(acc / n, rel=0.1)       # ln(K/2) is an asymptotic estimate
    # the momentum diffusion per step for K = 10 from an ensemble of random starts
    rng = np.random.default_rng(3)
    th0, p0 = rng.uniform(0, 2 * pi, 4000), np.zeros(4000)
    th_, p_ = th0.copy(), p0.copy()
    for _ in range(10):
        p_ = p_ + k * np.sin(th_)
        th_ = th_ + p_
    measured = float(np.var(p_)) / 10 / 2
    assert measured == pytest.approx(solved("physics.nonlinear.standard_map_stability", K="10")["Dq"], rel=0.45) and measured < solved("physics.nonlinear.standard_map_stability", K="10")["Dq"]   # a quasilinear estimate: correlated kicks reduce the real value (about 0.65 at K = 10)
    assert solved("physics.nonlinear.standard_map_stability", K="1.5")["rg"] == 2 and solved("physics.nonlinear.standard_map_stability", K="5")["el"] == 0


def test_henon_exponents_from_iteration():
    a, b = 1.4, 0.3
    x, y, q, acc = 0.1, 0.1, np.eye(2), np.zeros(2)
    n = 60000
    for i in range(n + 500):
        jac = np.array([[-2 * a * x, 1.0], [b, 0.0]])
        x, y = 1 - a * x * x + y, b * x
        q, r = np.linalg.qr(jac @ q)
        if i >= 500:
            acc += np.log(np.abs(np.diag(r)))
    l1, l2 = acc / n
    assert l1 == pytest.approx(0.42, abs=0.01) and l1 + l2 == pytest.approx(math.log(b), abs=1e-3)       # the sum of the exponents is ln|det J| = ln b
    got = solved("physics.nonlinear.henon_map_properties", l1=str(l1))
    assert got["dk"] == pytest.approx(1 + l1 / abs(l2), rel=1e-3) and got["dk"] == pytest.approx(1.26, abs=0.02)


def test_fractal_dimension_from_a_constructed_cantor_set():
    pieces = [(0.0, 1.0)]
    counts = {}
    for level in range(1, 8):
        pieces = [seg for lo, hi in pieces for seg in ((lo, lo + (hi - lo) / 3), (hi - (hi - lo) / 3, hi))]
        counts[level] = len(pieces)                                                                       # 2^level boxes of size 3^-level cover the set
    r = solved("physics.nonlinear.fractal_dimension", Np="2", sc="3", e1=str(3.0**-3), N1=str(counts[3]), e2=str(3.0**-6), N2=str(counts[6]), e3=str(3.0**-7))
    assert r["Ds"] == pytest.approx(math.log(2) / math.log(3)) and r["Db"] == pytest.approx(math.log(2) / math.log(3)) and r["N3"] == pytest.approx(counts[7], rel=1e-9)


def test_catalogued_with_sub_disciplines_and_references():
    for cid in CASES:
        c = CAT.get(cid)
        assert c.subdisciplines and c.references
