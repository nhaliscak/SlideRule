"""Classical mechanics gap-fillers (independent formulas, SI). Implicit ones (Kepler's equation, the brachistochrone) are checked with a root finder written here."""

import math

import pytest
from pcutil import CAT, G, check_case, g, pi, solved
from scipy.optimize import brentq


def newton2d(x):
    fx = sum(x[f"F{i}"] * math.cos(x[f"a{i}"]) for i in (1, 2, 3))
    fy = sum(x[f"F{i}"] * math.sin(x[f"a{i}"]) for i in (1, 2, 3))
    fn = math.hypot(fx, fy)
    a = fn / x["m"]
    return {"Fx": fx, "Fy": fy, "Fn": fn, "an": math.atan2(fy, fx), "ac": a, "vf": a * x["t"], "df": a * x["t"] ** 2 / 2}


def work_energy(x):
    m, v0, mu, th = x["m"], x["v0"], x["mu"], x["th"]
    # integrate the motion numerically with a small time step instead of using the closed form
    a = g * (math.sin(th) + mu * math.cos(th))
    t, v, d, dt = 0.0, v0, 0.0, 1e-5
    while v > 0:
        v2 = v - a * dt
        if v2 <= 0:
            frac = v / a
            d += v * frac - a * frac**2 / 2
            t += frac
            break
        d += (v + v2) / 2 * dt
        v, t = v2, t + dt
    wf = -mu * m * g * math.cos(th) * d
    return {"dd": d, "tt": t, "Ek": m * v0**2 / 2, "Wf": wf, "Qh": -wf, "hg": d * math.sin(th), "fq": -wf / (m * v0**2 / 2)}


def bungee(x):
    m, l0, k = x["m"], x["L0"], x["k"]
    xm = brentq(lambda e: m * g * (l0 + e) - k * e**2 / 2, 0, 1000)                  # energy balance, solved numerically
    xe = m * g / k
    vm = math.sqrt(2 * g * (l0 + xe) - k * xe**2 / m)
    am = k * xm / m - g
    return {"xm": xm, "Hd": l0 + xm, "xe": xe, "am": am, "ng": am / g, "vm": vm, "Tp": 2 * pi * math.sqrt(m / k)}


def inelastic2d(x):
    px = x["m1"] * x["v1"] + x["m2"] * x["v2"] * math.cos(x["ph"])
    py = x["m2"] * x["v2"] * math.sin(x["ph"])
    mt = x["m1"] + x["m2"]
    k0 = x["m1"] * x["v1"] ** 2 / 2 + x["m2"] * x["v2"] ** 2 / 2
    vf = math.hypot(px, py) / mt
    return {"px": px, "py": py, "Vf": vf, "an": math.atan2(py, px), "KEl": k0 - mt * vf**2 / 2, "fl": (k0 - mt * vf**2 / 2) / k0}


def elastic_scatter(x):
    # solve the collision by momentum and energy in the lab frame for the given CM angle, instead of the CM formulas
    m1, m2, v1, chi = x["m1"], x["m2"], x["v1"], x["ch"]
    vcm = m1 * v1 / (m1 + m2)
    u1x, u1y = vcm + m2 / (m1 + m2) * v1 * math.cos(chi), m2 / (m1 + m2) * v1 * math.sin(chi)           # projectile after, lab frame
    u2x, u2y = vcm - m1 / (m1 + m2) * v1 * math.cos(chi), -m1 / (m1 + m2) * v1 * math.sin(chi)
    assert m1 * u1x + m2 * u2x == pytest.approx(m1 * v1) and m1 * (u1x**2 + u1y**2) + m2 * (u2x**2 + u2y**2) == pytest.approx(m1 * v1**2)
    t1 = math.atan2(u1y, u1x)
    t2 = -math.atan2(u2y, u2x)
    ft = m2 * (u2x**2 + u2y**2) / (m1 * v1**2)
    return {"th1": t1, "th2": t2, "u1": math.hypot(u1x, u1y), "u2": math.hypot(u2x, u2y), "ft": ft, "thm": math.asin(m2 / m1) if m1 > m2 else pi}


def com(x):
    ms = [x["m1"], x["m2"], x["m3"]]
    xs = [x["x1"], x["x2"], x["x3"]]
    ys = [x["y1"], x["y2"], x["y3"]]
    mt = sum(ms)
    xc, yc = sum(m * a for m, a in zip(ms, xs)) / mt, sum(m * b for m, b in zip(ms, ys)) / mt
    ic = sum(m * ((a - xc) ** 2 + (b - yc) ** 2) for m, a, b in zip(ms, xs, ys))                         # directly about the centre of mass
    return {"Mt": mt, "Xc": xc, "Yc": yc, "Io": sum(m * (a * a + b * b) for m, a, b in zip(ms, xs, ys)), "Ic": ic}


def cables(x):
    w = x["m"] * g
    al, be = x["al"], x["be"]
    # horizontal and vertical balance solved as two linear equations
    import numpy as np

    # T1 cos(al) - T2 cos(be) = 0 and T1 sin(al) + T2 sin(be) = W
    t1, t2 = np.linalg.solve([[math.cos(al), -math.cos(be)], [math.sin(al), math.sin(be)]], [0.0, w])
    return {"W": w, "T1": t1, "T2": t2, "Hh": t1 * math.cos(al)}


def incline_projectile(x):
    v0, ph, th = x["v0"], x["ph"], x["th"]
    ax, ay = -g * math.sin(th), -g * math.cos(th)                                                       # axes along and across the slope
    vx, vy = v0 * math.cos(ph), v0 * math.sin(ph)
    tf = -2 * vy / ay
    rng = vx * tf + ax * tf**2 / 2
    best = max((v0**2 * math.sin(p) * math.cos(p + th) * 2 / (g * math.cos(th) ** 2), p) for p in [i * pi / 2 / 20000 for i in range(1, 20000)])
    return {"Tf": tf, "Rr": rng, "hm": vy**2 / (-2 * ay), "Rx": best[0], "pm": best[1]}


def drum(x):
    w = x["w"]
    nf = x["m"] * w**2 * x["Rd"]
    return {"wm": math.sqrt(g / (x["mu"] * x["Rd"])), "vr": w * x["Rd"], "Nf": nf, "Fs": x["mu"] * nf, "mg": x["m"] * g, "mr": x["mu"] * nf - x["m"] * g}


def torque(x):
    al = x["tq"] / x["In"]
    wf = x["w0"] + al * x["t"]
    ag = x["w0"] * x["t"] + al * x["t"] ** 2 / 2
    return {"al": al, "wf": wf, "ag": ag, "nr": ag / (2 * pi), "Ek": x["In"] * wf**2 / 2, "Wk": x["tq"] * ag, "Pf": x["tq"] * wf}


def capstan(x):
    ph = 2 * pi * x["nw"]
    rt = math.exp(x["mu"] * ph)
    return {"ph": ph, "rt": rt, "Tm": x["Tl"] / rt, "nn": math.log(x["Tl"] / x["Th"]) / (2 * pi * x["mu"]), "Pw": (x["Tl"] - x["Tl"] / rt) * x["vb"]}


def machines(x):
    w, ef = x["W"], x["ef"]
    mal, map_, mai = x["Le"] / x["Ll"], x["ns"], x["Ln"] / x["Hn"]
    return {"MAl": mal, "MAp": map_, "MAi": mai, "Fl": w / (mal * ef), "Fp": w / (map_ * ef), "Fi": w / (mai * ef), "dr": x["ns"]}


def chain_belt(x):
    return {"Fc": 3 * x["lam"] * g * x["xf"], "Fm": 3 * x["lam"] * g * x["Lc"], "Fb": x["mdot"] * x["vb"], "Pb": x["mdot"] * x["vb"] ** 2, "Pk": x["mdot"] * x["vb"] ** 2 / 2, "fh": 0.5}


def tunnel(x):
    w = math.sqrt(G * x["Mp"] / x["Rp"] ** 3)
    return {"w": w, "Tp": 2 * pi / w, "vc": w * x["Rp"], "tc": pi / w, "vx": w * x["dc"] / 2, "dp": x["Rp"] - math.sqrt(x["Rp"] ** 2 - x["dc"] ** 2 / 4)}


def accel_frame(x):
    gx, gy = x["ah"], g + x["av"]
    ge = math.hypot(gx, gy)
    return {"ge": ge, "tl": math.atan2(gx, gy), "Wa": x["m"] * ge, "Tp": 2 * pi * math.sqrt(x["Lp"] / ge)}


def bucket(x):
    w, r, h0 = x["w"], x["Rb"], x["H0"]
    # volume of the liquid: depth at the axis plus the paraboloid, integrated numerically over the radius
    ha = h0 - w**2 * r**2 / (4 * g)
    n = 20000
    vol = sum((ha + w**2 * ((i + 0.5) * r / n) ** 2 / (2 * g)) * 2 * pi * (i + 0.5) * (r / n) * (r / n) for i in range(n))
    assert vol == pytest.approx(pi * r**2 * h0, rel=1e-6)
    return {"dz": w**2 * r**2 / (2 * g), "ha": ha, "hw": ha + w**2 * r**2 / (2 * g), "wd": math.sqrt(4 * g * h0) / r, "ff": g / (2 * w**2)}


def decay(x):
    dl = math.log(x["A0"] / x["An"]) / x["nc"]
    ze = dl / math.sqrt(4 * pi**2 + dl**2)
    wd = 2 * pi / x["Td"]
    w0 = wd / math.sqrt(1 - ze**2)
    return {"dl": dl, "ze": ze, "Qf": 1 / (2 * ze), "tau": x["Td"] / dl, "wd": wd, "w0": w0, "cd": 2 * x["m"] * ze * w0, "kk": x["m"] * w0**2}


def kepler(x):
    a, e, mc, t = x["aa"], x["ec"], x["Mc"], x["t"]
    n = math.sqrt(G * mc / a**3)
    m = n * t
    ea = brentq(lambda u: u - e * math.sin(u) - m, 0, 2 * pi)
    nu = math.atan2(math.sqrt(1 - e * e) * math.sin(ea), math.cos(ea) - e)                               # the textbook form of the true anomaly
    r = a * (1 - e * math.cos(ea))
    return {"nm": n, "Tp": 2 * pi / n, "Ma": m, "Ea": ea, "nu": nu % (2 * pi), "rr": r, "vv": math.sqrt(G * mc * (2 / r - 1 / a))}


def brachistochrone(x):
    xh, yd = x["Xh"], x["Yd"]
    th = brentq(lambda u: (u - math.sin(u)) / (1 - math.cos(u)) - xh / yd, 1e-4, 2 * pi - 1e-4)
    a = yd / (1 - math.cos(th))
    tc = th * math.sqrt(a / g)
    length = math.hypot(xh, yd)
    tl = math.sqrt(2 * length / (g * yd / length))                                                     # constant acceleration g sin(alpha) along the line
    return {"th": th, "ar": a, "Tc": tc, "Tl": tl, "sv": 1 - tc / tl}


def kapitza(x):
    l, a, om = x["Lp"], x["ad"], x["Om"]
    ws = math.sqrt(a**2 * om**2 / (2 * l**2) - g / l)
    return {"sr": a**2 * om**2 / (2 * g * l), "Oc": math.sqrt(2 * g * l) / a, "ws": ws, "Ts": 2 * pi / ws}


def duffing(x):
    w0 = math.sqrt(x["kk"] / x["m"])
    # first-order harmonic balance, checked in the test below against numerical integration
    wa = math.sqrt(w0**2 + 3 * x["be"] * x["Am"] ** 2 / (4 * x["m"]))
    return {"w0": w0, "wa": wa, "sh": wa / w0 - 1, "Ta": 2 * pi / wa}


def separatrix(x):
    m, l, e = x["m"], x["Lp"], x["En"]
    es = 2 * m * g * l
    return {"Es": es, "rE": e / es, "rg": 1 if e < es else 2, "vb": math.sqrt(2 * e / m), "tm": math.acos(1 - e / (m * g * l)) if e < es else pi, "vt": 0.0 if e < es else math.sqrt(2 * (e - es) / m), "w0": math.sqrt(g / l)}


def hard_sphere(x):
    th = 2 * math.acos(x["bp"] / x["Rs"])
    # the angle for the impact parameter, and the cross-section from b db = (R^2/4) sin(theta) dtheta
    return {"th": th, "ds": x["Rs"] ** 2 / 4, "sg": pi * x["Rs"] ** 2, "lm": 1 / (x["nd"] * pi * x["Rs"] ** 2)}


def principal(x):
    import numpy as np

    ix, iy, ixy = x["Ix"], x["Iy"], x["Ixy"]
    t = np.array([[ix, -ixy], [-ixy, iy]])
    w, v = np.linalg.eigh(t)                                                                           # the inertia tensor of a planar body
    big = v[:, 1]
    tp = math.atan2(big[1], big[0])
    if tp > pi / 2:
        tp -= pi
    if tp <= -pi / 2:
        tp += pi
    ph = x["ph"]
    axis = np.array([math.cos(ph), math.sin(ph)])
    return {"I1": float(w[1]), "I2": float(w[0]), "tp": tp, "Ip": float(axis @ t @ axis)}


def euler_stab(x):
    import numpy as np

    i1, i2, i3, w = x["I1"], x["I2"], x["I3"], x["wp"]
    i = [i1, i2, i3]
    eig = {}
    for axis in range(3):                                                                              # linearise Euler's equations about each spin axis and take the eigenvalues of the 2 x 2 system
        a, b = [k for k in range(3) if k != axis]
        mat = np.array([[0, w * (i[b] - i[axis]) / i[a]], [w * (i[axis] - i[a]) / i[b], 0]])
        eig[axis] = np.linalg.eigvals(mat)
    lam = float(np.max(eig[1].real))
    return {"O1": float(np.max(np.abs(eig[0].imag))), "O3": float(np.max(np.abs(eig[2].imag))), "gr": lam, "te": 1 / lam}


def cubic(x):
    m, a, b = x["m"], x["Ak"], x["Bk"]
    xu = 2 * a / (3 * b)
    ub = a * xu**2 - b * xu**3
    force = lambda u: -(2 * a * u - 3 * b * u * u)                                                      # noqa: E731
    xs = [i * xu / 100000 for i in range(1, 100000)]
    fm = max(abs(force(u)) for u in xs)
    return {"xu": xu, "Ub": ub, "w0": math.sqrt(2 * a / m), "T0": 2 * pi / math.sqrt(2 * a / m), "ve": math.sqrt(2 * ub / m), "Fm": fm}


CASES = {
    "physics.mechanics.newton_second_law_2d": newton2d, "physics.mechanics.work_energy_friction": work_energy, "physics.mechanics.bungee_energy": bungee, "physics.mechanics.collision_2d_inelastic": inelastic2d,
    "physics.mechanics.elastic_scattering_target_at_rest": elastic_scatter, "physics.mechanics.centre_of_mass_system": com, "physics.mechanics.static_equilibrium_two_cables": cables, "physics.mechanics.projectile_on_incline": incline_projectile,
    "physics.mechanics.rotating_drum_friction": drum, "physics.mechanics.rotational_dynamics_torque": torque, "physics.mechanics.capstan_belt_friction": capstan, "physics.mechanics.simple_machines": machines,
    "physics.mechanics.variable_mass_chain_belt": chain_belt, "physics.mechanics.gravity_tunnel_shm": tunnel, "physics.mechanics.accelerating_frame_apparent_gravity": accel_frame, "physics.mechanics.rotating_bucket_surface": bucket,
    "physics.mechanics.damped_free_decay": decay, "physics.analytical.kepler_equation_position": kepler, "physics.analytical.brachistochrone": brachistochrone, "physics.analytical.kapitza_pendulum": kapitza,
    "physics.analytical.duffing_backbone": duffing, "physics.analytical.pendulum_separatrix": separatrix, "physics.analytical.hard_sphere_scattering": hard_sphere, "physics.analytical.inertia_tensor_principal_2d": principal,
    "physics.analytical.euler_rotation_stability": euler_stab, "physics.analytical.cubic_potential_escape": cubic,
}

LOOSE = {"physics.mechanics.work_energy_friction": 1e-4, "physics.analytical.brachistochrone": 1e-4, "physics.mechanics.projectile_on_incline": 1e-4, "physics.analytical.cubic_potential_escape": 1e-4}


def test_there_are_twenty_six_cases():
    assert len(CASES) == 26


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=LOOSE.get(cid, 1e-6))


def test_benchmarks_and_identities():
    assert solved("physics.mechanics.elastic_scattering_target_at_rest", m1="1 kg", m2="1 kg", ch="60 deg")["th1"] + solved("physics.mechanics.elastic_scattering_target_at_rest", m1="1 kg", m2="1 kg", ch="60 deg")["th2"] == pytest.approx(pi / 2)   # equal masses: 90 degrees apart
    assert solved("physics.mechanics.elastic_scattering_target_at_rest", m1="1 kg", m2="1 kg", ch="180 deg")["u1"] == pytest.approx(0, abs=1e-9)              # head-on, equal masses: the projectile stops
    assert solved("physics.mechanics.collision_2d_inelastic", ph="0 deg")["KEl"] == pytest.approx(0.5 * (1500 * 1000 / 2500) * (20 - 15) ** 2)             # collinear: half the reduced mass times the relative speed squared
    assert solved("physics.mechanics.static_equilibrium_two_cables", al="45 deg", be="45 deg", m="10 kg")["T1"] == pytest.approx(10 * g / math.sqrt(2))     # symmetric cables
    assert solved("physics.mechanics.gravity_tunnel_shm")["Tp"] / 60 == pytest.approx(84.35, abs=0.05)                                                           # the famous 84-minute tunnel
    assert solved("physics.mechanics.projectile_on_incline", th="0 deg", ph="45 deg")["Rr"] == pytest.approx(solved("physics.mechanics.projectile_on_incline", th="0 deg", ph="45 deg")["Rx"])   # level ground: 45 degrees is best
    assert solved("physics.mechanics.damped_free_decay", An="19.99999 mm", nc="1")["ze"] < 1e-5                                                             # no decay, no damping
    assert solved("physics.mechanics.work_energy_friction", th="0 deg")["dd"] == pytest.approx(8**2 / (2 * 0.25 * g), rel=1e-9)
    assert solved("physics.mechanics.capstan_belt_friction", nw="0.5")["rt"] == pytest.approx(math.exp(0.3 * pi))
    assert solved("physics.analytical.brachistochrone", Xh="1 m", Yd="1 m")["Tc"] < solved("physics.analytical.brachistochrone", Xh="1 m", Yd="1 m")["Tl"]       # the cycloid always wins
    assert solved("physics.analytical.hard_sphere_scattering", bp="0.0000001 m")["th"] == pytest.approx(pi, abs=1e-4)                                         # head-on: reflected straight back
    assert solved("physics.analytical.pendulum_separatrix", En="20 J")["rg"] == 2 and solved("physics.analytical.pendulum_separatrix", En="20 J")["vt"] > 0


def test_duffing_backbone_against_numerical_integration():
    """The harmonic-balance frequency is checked against a direct integration of m x'' + k x + beta x^3 = 0 (period from the zero crossings)."""
    from scipy.integrate import solve_ivp

    m, k, beta, amp = 1.0, 100.0, 2000.0, 0.1
    sol = solve_ivp(lambda t, y: [y[1], -(k * y[0] + beta * y[0] ** 3) / m], [0, 2], [amp, 0], rtol=1e-11, atol=1e-13, dense_output=True, events=lambda t, y: y[0])
    crossings = sol.t_events[0]
    period = 4 * (crossings[0])                                                                                                                     # first zero crossing is a quarter period
    got = solved("physics.analytical.duffing_backbone")["Ta"]
    assert got == pytest.approx(period, rel=0.01)                                                                                                    # first-order theory: within one per cent here


def test_catalogued_under_classical_or_analytical_mechanics():
    for cid in CASES:
        c = CAT.get(cid)
        assert ("Classical Mechanics" in c.subdisciplines or "Analytical Mechanics" in c.subdisciplines) and c.references
