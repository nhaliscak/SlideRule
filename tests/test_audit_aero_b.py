"""Equation-audit fill, aerospace B: orbital mechanics and space systems, each against a different route (vis-viva stepping, averaged perturbation integrals, trajectory simulation, element recovery, shadow geometry)."""

import math

import numpy as np
import pytest
from pcutil import CAT, check_case, solved
from scipy import integrate, optimize
from scipy.spatial.transform import Rotation

PRE = "aerospace."
MU = 3.986004418e14
RE = 6378137.0
G = 9.80665


def visviva(r, a):
    return math.sqrt(MU * (2 / r - 1 / a))


def transfer(x):
    r1, r2, rb, di = x["r1"], x["r2"], x["rb"], x["di"]
    ah = (r1 + r2) / 2
    dH = abs(visviva(r1, ah) - visviva(r1, r1)) + abs(visviva(r2, r2) - visviva(r2, ah))
    a1, a2 = (r1 + rb) / 2, (rb + r2) / 2
    dB = abs(visviva(r1, a1) - visviva(r1, r1)) + abs(visviva(rb, a2) - visviva(rb, a1)) + abs(visviva(r2, r2) - visviva(r2, a2))
    v = visviva(r2, r2)
    vec0, vec1 = np.array([v, 0.0]), v * np.array([math.cos(di), math.sin(di)])          # circular velocity before and after rotating the plane
    return {"v1": visviva(r1, r1), "v2": v, "dH": dH, "tH": 2 * math.pi * math.sqrt(ah ** 3 / MU) / 2, "dB": dB, "dP": np.linalg.norm(vec1 - vec0)}


def j2(x):
    a, e, i = x["a"], x["ec"], x["i"]
    n = math.sqrt(MU / a ** 3)
    p = a * (1 - e * e)
    h = math.sqrt(MU * p)
    J2 = 1.08263e-3
    def rate(nu, omega=0.0):
        r = p / (1 + e * math.cos(nu))
        u = omega + nu
        pos = r * np.array([math.cos(u), math.sin(u) * math.cos(i), math.sin(u) * math.sin(i)])      # node on the x axis (Omega = 0)
        z, rr = pos[2], np.linalg.norm(pos)
        acc = -1.5 * J2 * MU * RE ** 2 / rr ** 4 * np.array([(1 - 5 * z * z / rr ** 2) * pos[0] / rr, (1 - 5 * z * z / rr ** 2) * pos[1] / rr, (3 - 5 * z * z / rr ** 2) * z / rr])
        hhat = np.array([0.0, -math.sin(i), math.cos(i)])
        return r * math.sin(u) / (h * math.sin(i)) * float(acc @ hhat) * r * r / h                   # Gauss equation for the node, times dt/dnu
    T = 2 * math.pi / n
    Od = integrate.quad(lambda nu: rate(nu, 0.0), 0, 2 * math.pi, limit=200)[0] / T
    # sun-synchronous: find the inclination that gives the tropical-year rate
    f = lambda ii: -1.5 * J2 * (RE / p) ** 2 * n * math.cos(ii) - 1.99106e-7
    iss = optimize.brentq(f, math.pi / 2, math.pi)
    return {"n": n, "pp": p, "Od": Od, "wd": 1.5 * J2 * (RE / p) ** 2 * n * (2 - 2.5 * math.sin(i) ** 2), "iss": iss}


def assist(x):
    ap, mp, Ms, vinf, rp, mup = x["ap"], x["mp"], x["Ms"], x["vinf"], x["rp"], x["mup"]
    vp = math.sqrt(vinf ** 2 + 2 * mup / rp)
    h = rp * vp
    e = math.sqrt(1 + (h * vinf / mup) ** 2)                                             # eccentricity from angular momentum and energy
    b = h / vinf                                                                         # impact parameter
    R0 = 5e12                                                                            # start far outside the sphere of influence so the velocity is the asymptote
    sol = integrate.solve_ivp(lambda t, s: [s[2], s[3], -mup * s[0] / np.hypot(s[0], s[1]) ** 3, -mup * s[1] / np.hypot(s[0], s[1]) ** 3], [0, 2.4 * R0 / vinf], [-R0, b, vinf, 0.0], method="DOP853", rtol=1e-12, atol=1e-6)
    vf = sol.y[2:, -1]
    delta = math.acos(vf[0] / np.linalg.norm(vf))                                        # angle between the outgoing and incoming asymptote directions
    return {"rs": ap * (mp / Ms) ** 0.4, "ef": e, "dl": delta, "dvm": np.linalg.norm(np.array([vinf, 0.0]) - vf)}


def entry(x):
    rho0 = 1.225
    beta = x["m"] / (x["CD"] * x["A"])
    H, ge = x["H"], x["ge"]
    # ballistic entry at constant flight-path angle in an exponential atmosphere: dV/dt = -rho V^2/(2 beta), dh/dt = -V sin(ge)
    def f(t, s):
        V, h = s
        return [-rho0 * math.exp(-h / H) * V * V / (2 * beta), -V * math.sin(ge)]
    h0 = H * math.log(rho0 / 1e-8)
    sol = integrate.solve_ivp(f, [0, 400], [x["ve"], h0], rtol=1e-11, atol=1e-9, dense_output=True)
    t = np.linspace(0, 400, 400001)
    V, h = sol.sol(t)
    acc = rho0 * np.exp(-h / H) * V ** 2 / (2 * beta)
    k = int(np.argmax(acc))
    return {"qs": 1.7415e-4 * math.sqrt(x["rho"] / x["Rn"]) * x["v"] ** 3, "bc": beta, "am": acc[k], "gl": acc[k] / G, "rpk": rho0 * math.exp(-h[k] / H)}


def staging(x):
    mp = 1.0                                                                             # build the stack from the payload up
    M2 = mp / x["l2"]
    m2_burnout = mp + x["e2"] * M2
    above1 = mp + M2
    M1 = above1 / x["l1"]
    N1 = (above1 + M1) / (above1 + x["e1"] * M1)
    N2 = above1 / m2_burnout
    d1, d2 = x["I1"] * G * math.log(N1), x["I2"] * G * math.log(N2)
    return {"N1": N1, "N2": N2, "d1": d1, "d2": d2, "dt": d1 + d2, "pf": mp / (above1 + M1)}


def launch(x):
    r = RE + x["h"]
    vc = math.sqrt(MU / r)
    vr = 7.292115e-5 * RE * math.cos(x["lat"])
    g_mean = MU / (RE + x["h"] / 2) ** 2
    dg = g_mean * x["tb"] * math.sin(x["gm"])
    dv = vc + dg + x["dvd"] - vr
    return {"vc": vc, "vr": vr, "dg": dg, "dv": dv, "pf": 1 - math.exp(-dv / (x["Isp"] * G))}


def cw(x):
    n = math.sqrt(MU / x["r0"] ** 3)
    def f(t, s):
        X, Y, Z, VX, VY, VZ = s
        return [VX, VY, VZ, 3 * n * n * X + 2 * n * VY, -2 * n * VX, -n * n * Z]
    sol = integrate.solve_ivp(f, [0, x["t"]], [x["x0"], x["y0"], x["z0"], x["vx0"], x["vy0"], x["vz0"]], rtol=1e-12, atol=1e-12)
    return {"n": n, "x": sol.y[0, -1], "y": sol.y[1, -1], "z": sol.y[2, -1]}


def adcs(x):
    q = Rotation.from_euler("ZYX", [x["ps"], x["th"], x["ph"]]).as_quat()                # x, y, z, w
    w, qx, qy, qz = q[3], q[0], q[1], q[2]
    sgn = 1 if w >= 0 else -1
    Tg = 3 * MU / (2 * x["r0"] ** 3) * (x["Iz"] - x["Iy"]) * math.sin(2 * x["tg"])
    return {"Tg": Tg, "q0": sgn * w, "q1": sgn * qx, "q2": sgn * qy, "q3": sgn * qz, "qn": 1.0}


def thermal(x):
    sb = 5.670374419e-8
    Qa = x["al"] * 1361 * x["As"] + x["al"] * x["ab"] * 1361 * x["F"] * x["Ae"] + x["em"] * x["qE"] * x["F"] * x["Ae"] + x["Q"]
    Te = optimize.brentq(lambda T: x["em"] * sb * x["Ar"] * T ** 4 - Qa, 1, 2000)       # emitted power equals absorbed power
    return {"Qa": Qa, "Te": Te}


def track(x):
    a, eta = x["a"], x["eta"]
    T = 2 * math.pi * math.sqrt(a ** 3 / MU)
    s = np.array([a, 0.0])
    d = np.array([-math.cos(eta), math.sin(eta)])                                        # ray from the satellite, eta from the nadir direction
    b = s @ d
    t = -b - math.sqrt(b * b - (s @ s - RE ** 2))                                        # first intersection with the Earth sphere
    pt = s + t * d
    lam = math.acos(pt @ s / (np.linalg.norm(pt) * a))
    dl = 7.292115e-5 * T
    return {"T": T, "dl": dl, "lc": lam, "sw": 2 * RE * lam, "sp": RE * dl, "ov": 2 * RE * lam / (RE * dl)}


def eclipse(x):
    r = RE + x["h"]
    Om, i, ds = x["dO"], x["i"], x["ds"]
    sun = np.array([math.cos(ds), 0.0, math.sin(ds)])
    hh = np.array([math.sin(Om) * math.sin(i), -math.cos(Om) * math.sin(i), math.cos(i)])
    beta = math.asin(sun @ hh)
    u = np.linspace(0, 2 * math.pi, 400001)
    P = np.column_stack([np.cos(Om) * np.cos(u) - np.sin(Om) * np.sin(u) * math.cos(i), np.sin(Om) * np.cos(u) + np.cos(Om) * np.sin(u) * math.cos(i), np.sin(u) * math.sin(i)]) * r
    behind = P @ sun < 0
    perp = np.linalg.norm(P - np.outer(P @ sun, sun), axis=1)
    frac = np.mean(behind & (perp < RE))                                                 # fraction of the orbit inside the cylindrical shadow
    T = 2 * math.pi * math.sqrt(r ** 3 / MU)
    return {"bt": beta, "bc": math.asin(RE / r), "T": T, "Te": frac * T}


def electric(x):
    c = G * x["Isp"]
    F = 2 * x["et"] * x["P"] / c
    md = F / c
    sol = integrate.solve_ivp(lambda t, s: [-md], [0, 1e9], [x["m0"]], events=lambda t, s: s[0] - x["mf"], rtol=1e-12, atol=1e-12)    # mass until it reaches the final mass
    return {"F": F, "md": md, "dv": c * math.log(x["m0"] / x["mf"]), "tb": sol.t_events[0][0], "asl": 2 * 1361 / x["ra"] ** 2 * x["As"] * math.cos(x["al"]) ** 2 / (299792458 * x["ms"])}


def tank(x):
    tc = x["p"] * x["r"] * x["sf"] / x["sy"]
    th = tc / 2
    Vshell = 2 * math.pi * x["r"] * x["Lc"] * tc + 4 * math.pi * x["r"] ** 2 * th
    Mt = x["rho"] * Vshell
    Vt = math.pi * x["r"] ** 2 * x["Lc"] + 4 / 3 * math.pi * x["r"] ** 3
    Mp = x["rp"] * Vt
    return {"tc": tc, "th": th, "Mt": Mt, "Vt": Vt, "Mp": Mp, "mf": Mt / (Mt + Mp)}


def rv2coe(r, v):
    """Standard recovery of the elements from a state vector (Vallado, algorithm 9)."""
    rn, vn = np.linalg.norm(r), np.linalg.norm(v)
    h = np.cross(r, v)
    nvec = np.cross([0, 0, 1], h)
    evec = ((vn ** 2 - MU / rn) * r - (r @ v) * v) / MU
    e = np.linalg.norm(evec)
    a = -MU / (2 * (vn ** 2 / 2 - MU / rn))
    i = math.acos(h[2] / np.linalg.norm(h))
    Om = math.acos(nvec[0] / np.linalg.norm(nvec))
    Om = 2 * math.pi - Om if nvec[1] < 0 else Om
    om = math.acos(nvec @ evec / (np.linalg.norm(nvec) * e))
    om = 2 * math.pi - om if evec[2] < 0 else om
    nu = math.acos(evec @ r / (e * rn))
    nu = 2 * math.pi - nu if r @ v < 0 else nu
    return a, e, i, Om, om, nu


def elements(x):
    a, e, i, Om, om, nu = x["a"], x["ec"], x["i"], x["Om"], x["wp"], x["nu"]
    p = a * (1 - e * e)
    rm = p / (1 + e * math.cos(nu))
    rpf = rm * np.array([math.cos(nu), math.sin(nu), 0])
    vpf = math.sqrt(MU / p) * np.array([-math.sin(nu), e + math.cos(nu), 0])
    Q = Rotation.from_euler("ZXZ", [Om, i, om]).as_matrix()                              # perifocal to inertial, intrinsic z-x-z
    r, v = Q @ rpf, Q @ vpf
    back = rv2coe(r, v)
    for got, want in zip(back, (a, e, i, Om, om, nu)):
        assert got == pytest.approx(want, rel=1e-9, abs=1e-9)                            # the state vector reproduces the elements
    return {"pp": p, "rm": rm, "rx": r[0], "ry": r[1], "rz": r[2], "vx": v[0], "vy": v[1], "vz": v[2], "vm": np.linalg.norm(v), "en": -MU / (2 * a)}


def antenna(x):
    lam = 299792458 / x["f"]
    A = math.pi * x["D"] ** 2 / 4
    G_lin = 4 * math.pi * x["ea"] * A / lam ** 2                                         # gain from the effective aperture
    bw = 70 * lam / x["D"] * math.pi / 180
    return {"lam": lam, "Gd": 10 * math.log10(G_lin), "bw": bw, "Lp": 12 * (x["er"] / bw) ** 2}


CASES = {
    PRE + "orbits.hohmann_bielliptic_plane_change": (transfer, 1e-9), PRE + "orbits.j2_nodal_regression_sun_synchronous": (j2, 5e-4), PRE + "orbits.sphere_of_influence_gravity_assist": (assist, 1e-3),
    PRE + "reentry.sutton_graves_heating_allen_eggers": (entry, 1e-4), PRE + "propulsion.multistage_rocket_delta_v": (staging, 1e-9), PRE + "propulsion.launch_delta_v_budget_gravity_losses": (launch, 1e-9),
    PRE + "orbits.clohessy_wiltshire_relative_motion": (cw, 1e-6), PRE + "adcs.gravity_gradient_torque_quaternion": (adcs, 1e-9), PRE + "thermal.spacecraft_equilibrium_temperature": (thermal, 1e-6),
    PRE + "orbits.ground_track_swath_coverage": (track, 1e-9), PRE + "orbits.eclipse_duration_beta_angle": (eclipse, 2e-3), PRE + "propulsion.electric_propulsion_solar_sail": (electric, 1e-6),
    PRE + "structures.spacecraft_propellant_tank_mass": (tank, 1e-9), PRE + "orbits.keplerian_elements_to_state_vector": (elements, 1e-9), PRE + "space_systems.antenna_pointing_loss_beamwidth": (antenna, 1e-9),
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_route(cid):
    fn, rel = CASES[cid]
    check_case(cid, fn, rel=rel)


def test_benchmarks():
    t = solved(PRE + "orbits.hohmann_bielliptic_plane_change", r1="6678 km", r2="384400 km", rb="1e6 km")                 # beyond r2/r1 = 15.58: the bi-elliptic transfer is cheaper
    assert t["dB"] < t["dH"]
    assert solved(PRE + "orbits.hohmann_bielliptic_plane_change")["dB"] > solved(PRE + "orbits.hohmann_bielliptic_plane_change")["dH"]    # r2/r1 = 6.3: Hohmann wins
    assert solved(PRE + "orbits.j2_nodal_regression_sun_synchronous", i="63.4349 deg", ec="0.01")["wd"] == pytest.approx(0, abs=1e-10)       # critical inclination: no apsidal rotation
    ss = solved(PRE + "orbits.j2_nodal_regression_sun_synchronous")
    assert solved(PRE + "orbits.j2_nodal_regression_sun_synchronous", i=f"{ss['iss'] * 180 / math.pi} deg")["Od"] == pytest.approx(1.99106e-7, rel=1e-9)   # sun-synchronous: 360 degrees per tropical year
    assert solved(PRE + "orbits.sphere_of_influence_gravity_assist")["rs"] == pytest.approx(48.2e9, rel=2e-3)                 # Jupiter's sphere of influence, about 48 million km
    assert solved(PRE + "orbits.eclipse_duration_beta_angle", ds="0 deg", i="98 deg", dO="90 deg")["Te"] == pytest.approx(0, abs=1)             # sun almost normal to the plane: no eclipse
    assert solved(PRE + "propulsion.electric_propulsion_solar_sail")["F"] == pytest.approx(0.2447, abs=1e-3)
    assert solved(PRE + "propulsion.launch_delta_v_budget_gravity_losses", tb="0 s")["dg"] == pytest.approx(0)
    assert solved(PRE + "orbits.clohessy_wiltshire_relative_motion", vy0="-0.2 m/s", t="0 s")["y"] == pytest.approx(-2000)    # at t = 0 the initial offset
    assert solved(PRE + "adcs.gravity_gradient_torque_quaternion", ph="0 deg", th="0 deg", ps="0 deg")["q0"] == pytest.approx(1)  # identity rotation
    assert solved(PRE + "space_systems.antenna_pointing_loss_beamwidth", er="0 deg")["Lp"] == pytest.approx(0, abs=1e-12)
    bw = solved(PRE + "space_systems.antenna_pointing_loss_beamwidth")["bw"]
    gauss = -10 * math.log10(math.exp(-4 * math.log(2) * (0.1 * math.pi / 180 / bw) ** 2))                                   # Gaussian beam: 12.04 (e/bw)^2 dB
    assert solved(PRE + "space_systems.antenna_pointing_loss_beamwidth")["Lp"] == pytest.approx(gauss, rel=5e-3)


def test_catalogued():
    for cid in CASES:
        assert CAT.get(cid).disciplines[0] == "aerospace"
