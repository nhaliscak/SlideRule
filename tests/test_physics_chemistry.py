"""Physics and chemistry calculations: every result is recomputed here from the textbook formula in plain Python (CODATA 2018
constants written out again, not imported from the library), so the library is checked against the physics and not against itself."""

import math

import pytest

from sliderule.core import solve
from sliderule.core.catalog import default_catalog

CAT = default_catalog()

h = 6.62607015e-34
c = 299792458.0
kB = 1.380649e-23
NA = 6.02214076e23
e = 1.602176634e-19
R = NA * kB
eps0 = 8.8541878128e-12
mu0 = 1.25663706212e-6
G = 6.67430e-11
sSB = 5.670374419e-8
me = 9.1093837015e-31
Rinf = 10973731.568160
a0 = 5.29177210903e-11
g = 9.80665
Da = 1.66053906660e-27
deg = math.pi / 180


def run(cid, solve_for=None, **given):
    calc = CAT.get(cid)
    inputs = dict(calc.example)
    inputs.update(given)
    if solve_for:
        for k in solve_for:
            inputs.pop(k, None)
    s = solve(calc, inputs, solve_for=solve_for)
    assert s.ok, [d.message for d in s.diagnostics]
    return {o["key"]: o["si_value"] for o in s.outputs}, s


def check(cid, expected, rel=1e-6, **given):
    out, _ = run(cid, **given)
    for k, v in expected.items():
        assert out[k] == pytest.approx(v, rel=rel, abs=1e-30), (cid, k, out[k], v)


# ---------------------------------------------------------------- classical mechanics
def test_kinematics():
    check("physics.mechanics.kinematics_constant_acceleration", {"v": 5 + 2 * 10, "s": (5 + 25) / 2 * 10, "vm": 15})


def test_kinematics_suvat_identity_holds():
    out, _ = run("physics.mechanics.kinematics_constant_acceleration", u="3 m/s", a="-1.5 m/s^2", t="4 s")
    assert out["v"] ** 2 == pytest.approx(3**2 + 2 * -1.5 * out["s"])


def test_collision_conserves_momentum_and_restitution():
    out, _ = run("physics.mechanics.collisions_1d")
    assert 2 * out["v1"] + 1 * out["v2"] == pytest.approx(2 * 3 + 1 * -1)
    assert (out["v2"] - out["v1"]) == pytest.approx(-0.5 * (-1 - 3))     # relative speed reverses by e
    assert out["dK"] == pytest.approx(9.5 - 5.5)


def test_elastic_equal_masses_swap_velocities():
    out, _ = run("physics.mechanics.collisions_1d", m1="1 kg", m2="1 kg", u1="4 m/s", u2="0 m/s", er="1")
    assert out["v1"] == pytest.approx(0, abs=1e-12) and out["v2"] == pytest.approx(4) and out["dK"] == pytest.approx(0, abs=1e-12)


def test_perfectly_inelastic_sticks_together():
    out, _ = run("physics.mechanics.collisions_1d", m1="3 kg", m2="1 kg", u1="2 m/s", u2="-2 m/s", er="0")
    assert out["v1"] == pytest.approx(out["v2"]) == pytest.approx((3 * 2 - 1 * 2) / 4)


def test_incline():
    th, mu, m, L = 30 * deg, 0.2, 5, 4
    a = g * (math.sin(th) - mu * math.cos(th))
    check("physics.mechanics.incline_friction", {"Fn": m * g * math.cos(th), "Ff": mu * m * g * math.cos(th), "a": a, "v": math.sqrt(2 * a * L), "t": math.sqrt(2 * L / a)})


def impossible(cid, expected_hint, **over):
    """The inputs break a stated physical limit: no result, and the diagnostics say which limit in the calculation's own words."""
    calc = CAT.get(cid)
    s = solve(calc, {**calc.example, **over})
    assert not s.ok
    assert any(d.code == "VALIDITY" and expected_hint in d.message for d in s.diagnostics), [d.message for d in s.diagnostics]


def test_incline_that_does_not_slide_is_explained():
    impossible("physics.mechanics.incline_friction", "does not slide", th="10 deg", mu="0.5")


def test_circular_motion():
    v, r, m = 20, 50, 1000
    check("physics.mechanics.uniform_circular_motion", {"ac": v**2 / r, "w": v / r, "T": 2 * math.pi * r / v, "f": v / (2 * math.pi * r), "Fc": m * v**2 / r, "thb": math.atan(v**2 / (r * g))})


def test_spring_mass():
    k, m, A = 200, 0.5, 0.04
    w = math.sqrt(k / m)
    check("physics.mechanics.spring_mass_oscillator", {"w0": w, "T": 2 * math.pi / w, "f": w / (2 * math.pi), "vmax": A * w, "amax": A * w * w, "Et": k * A * A / 2})


def test_pendulums():
    check("physics.mechanics.small_angle_pendulums", {"Ts": 2 * math.pi * math.sqrt(1 / g), "Tp": 2 * math.pi * math.sqrt(0.12 / (1.5 * g * 0.25))})


def test_physical_pendulum_reduces_to_simple_pendulum_for_a_point_mass():
    out, _ = run("physics.mechanics.small_angle_pendulums", Lp="0.8 m", Ip="0.64 kg*m^2", mb="1 kg", dc="0.8 m")     # I = m L^2
    assert out["Tp"] == pytest.approx(out["Ts"])


def test_rolling():
    th, k, hh = 25 * deg, 0.4, 2
    a = g * math.sin(th) / (1 + k)
    v = math.sqrt(2 * g * hh / (1 + k))
    check("physics.mechanics.rolling_incline", {"a": a, "v": v, "t": v / a, "Fr": k / (1 + k)})


def test_rolling_speed_agrees_with_kinematics():
    out, _ = run("physics.mechanics.rolling_incline")
    L = 2 / math.sin(25 * deg)
    assert out["v"] ** 2 == pytest.approx(2 * out["a"] * L)


def test_angular_momentum():
    I1, w1, I2 = 4, 2, 1.5
    w2 = I1 * w1 / I2
    check("physics.mechanics.angular_momentum_conservation", {"Lm": 8, "w2": w2, "K1": I1 * w1**2 / 2, "K2": I2 * w2**2 / 2, "W": I2 * w2**2 / 2 - I1 * w1**2 / 2})


# ---------------------------------------------------------------- thermodynamics and statistical physics
def test_blackbody():
    T, lam = 5772, 500e-9
    B = 2 * h * c**2 / lam**5 / math.expm1(h * c / (lam * kB * T))
    check("physics.thermo.blackbody_radiation", {"lpk": 2.897771955e-3 / T, "Mx": sSB * T**4, "Pr": sSB * T**4, "Bl": B})      # SI value: W/(m^2 sr m)


def test_wien_constant_follows_from_planck():
    """b = hc/(4.965114231 k): ties the quoted Wien constant to Planck's law, independently of the formula in the library."""
    assert 2.897771955e-3 == pytest.approx(h * c / (4.965114231744276 * kB), rel=1e-8)


def test_planck_peak_is_at_the_wien_wavelength():
    T = 5000
    lam_pk = run("physics.thermo.blackbody_radiation", T="5000 K")[0]["lpk"]
    def planck(lam):
        return 2 * h * c**2 / lam**5 / math.expm1(h * c / (lam * kB * T))

    assert planck(lam_pk) > planck(lam_pk * 1.01) and planck(lam_pk) > planck(lam_pk / 1.01)


def test_kinetic_theory():
    T, M, d, P = 300, 28.0134e-3, 0.37e-9, 101325
    m = M / NA
    vm = math.sqrt(8 * kB * T / (math.pi * m))
    lm = kB * T / (math.sqrt(2) * math.pi * d**2 * P)
    check("physics.thermo.kinetic_theory_gas", {"mm": m, "vrms": math.sqrt(3 * kB * T / m), "vmean": vm, "vp": math.sqrt(2 * kB * T / m), "Ek": 1.5 * kB * T, "lmfp": lm, "zc": vm / lm})
    out, _ = run("physics.thermo.kinetic_theory_gas")
    assert out["vp"] < out["vmean"] < out["vrms"]


def test_heat_capacities():
    n, f, dT = 2, 5, 50
    Cv = f * R / 2
    check("physics.thermo.ideal_gas_heat_capacities", {"Cv": Cv, "Cp": Cv + R, "gam": (Cv + R) / Cv, "dU": n * Cv * dT, "Qp": n * (Cv + R) * dT, "Wp": n * R * dT})


def test_first_law_for_constant_pressure_heating():
    out, _ = run("physics.thermo.ideal_gas_heat_capacities")
    assert out["Qp"] == pytest.approx(out["dU"] + out["Wp"])


def test_adiabatic():
    p1, V1, V2, T1, gam = 100e3, 10e-3, 5e-3, 300, 1.4
    p2 = p1 * (V1 / V2) ** gam
    check("physics.thermo.adiabatic_ideal_gas", {"p2": p2, "T2": T1 * (V1 / V2) ** (gam - 1), "W": (p1 * V1 - p2 * V2) / (gam - 1)})


def test_adiabatic_work_equals_internal_energy_loss():
    out, _ = run("physics.thermo.adiabatic_ideal_gas")
    n = 100e3 * 10e-3 / (R * 300)
    Cv = R / (1.4 - 1)
    assert out["W"] == pytest.approx(-n * Cv * (out["T2"] - 300))


def test_entropy():
    n, f, T1, T2, V1, V2 = 1, 3, 300, 600, 1e-3, 2e-3
    Cv = f * R / 2
    check("physics.thermo.entropy_change", {"Cv": Cv, "dSg": n * Cv * math.log(T2 / T1) + n * R * math.log(V2 / V1), "dSu": 1000 * (1 / 300 - 1 / 500)})


# ---------------------------------------------------------------- waves and acoustics
def test_doppler():
    check("physics.waves.doppler_effect", {"fo": 440 * 343 / (343 - 30), "df": 440 * 343 / (343 - 30) - 440})
    out, _ = run("physics.waves.doppler_effect", vo="20 m/s", vs="0 m/s")
    assert out["fo"] == pytest.approx(440 * (343 + 20) / 343)


def test_doppler_approaching_and_receding_are_not_symmetric():
    up = run("physics.waves.doppler_effect", vs="30 m/s")[0]["fo"]
    down = run("physics.waves.doppler_effect", vs="-30 m/s")[0]["fo"]
    assert up > 440 > down and (up - 440) != pytest.approx(440 - down)


def test_standing_waves():
    L, n, T, mu, cs = 0.65, 3, 80, 0.001, 343
    v = math.sqrt(T / mu)
    check("physics.waves.standing_waves", {"vw": v, "fstr": n * v / (2 * L), "fopen": n * cs / (2 * L), "fcl": (2 * n - 1) * cs / (4 * L)})


def test_superposition():
    check("physics.waves.superposition_beats", {"fb": 4, "fav": 442, "Ar": math.sqrt(1 + 0.36 + 2 * 0.6 * math.cos(60 * deg)) * 1e-3})
    in_phase = run("physics.waves.superposition_beats", ph="0 deg")[0]["Ar"]
    opposed = run("physics.waves.superposition_beats", ph="180 deg")[0]["Ar"]
    assert in_phase == pytest.approx(1.6e-3) and opposed == pytest.approx(0.4e-3)


# ---------------------------------------------------------------- optics
def test_snell():
    n1, n2, th1 = 1.5, 1.0, 30 * deg
    check("physics.optics.snell_refraction", {"th2": math.asin(n1 * math.sin(th1) / n2), "thB": math.atan(n2 / n1), "Rn": ((n1 - n2) / (n1 + n2)) ** 2})


def test_snell_total_internal_reflection_is_explained():
    impossible("physics.optics.snell_refraction", "Total internal reflection", th1="60 deg")


def test_reflectance_glass_air_is_four_percent():
    assert run("physics.optics.snell_refraction")[0]["Rn"] == pytest.approx(0.04)


def test_critical_angle():
    n1, n2, th, lam = 1.5, 1.0, 60 * deg, 600e-9
    check("physics.optics.critical_angle_tir", {"thc": math.asin(n2 / n1), "dpen": lam / (2 * math.pi * math.sqrt(n1**2 * math.sin(th) ** 2 - n2**2))})


def test_thin_lens():
    f = 1 / ((1.5 - 1) * (1 / 0.20 - 1 / -0.20))
    di = 1 / (1 / f - 1 / 0.30)
    check("physics.optics.thin_lens", {"f": f, "di": di, "M": -di / 0.30, "Pw": 1 / f})


def test_thin_lens_virtual_image_when_object_inside_focal_length():
    out, _ = run("physics.optics.thin_lens", do="10 cm")
    assert out["di"] < 0 and out["M"] > 1


def test_double_and_single_slit():
    lam, d, a, L, m = 600e-9, 0.2e-3, 0.05e-3, 1.5, 3
    check("physics.optics.double_single_slit", {"dy": lam * L / d, "ym": m * lam * L / d, "Wc": 2 * lam * L / a})


def test_grating():
    lam, dg, m, N = 589e-9, 1e-3 / 600, 2, 5000
    check("physics.optics.diffraction_grating", {"dg": dg, "thm": math.asin(m * lam / dg), "Rp": m * N, "dl": lam / (m * N)})


# ---------------------------------------------------------------- electricity and magnetism
def test_coulomb():
    q1, q2, r = 5e-9, -2e-9, 0.03
    k = 1 / (4 * math.pi * eps0)
    check("physics.em.coulomb_point_charges", {"F": k * q1 * q2 / r**2, "Ef": k * q1 / r**2, "Vp": k * q1 / r, "U": k * q1 * q2 / r})
    assert 1 / (4 * math.pi * eps0) == pytest.approx(8.9875517923e9, rel=1e-9)


def test_gauss_fields():
    k = 1 / (4 * math.pi * eps0)
    check("physics.em.gauss_symmetric_fields", {"Eo": k * 10e-9 / 0.10**2, "Ei": k * 10e-9 * 0.02 / 0.05**3, "El": 2e-9 / (2 * math.pi * eps0 * 0.04), "Es": 3e-6 / (2 * eps0), "Ec": 3e-6 / eps0})


def test_sphere_field_is_continuous_at_the_surface():
    out_at_R = run("physics.em.gauss_symmetric_fields", ro="5 cm")[0]["Eo"]
    in_at_R = run("physics.em.gauss_symmetric_fields", ri="5 cm")[0]["Ei"]
    assert out_at_R == pytest.approx(in_at_R)


def test_magnetic_fields():
    I, r, Rl, z, n, I2, d = 10, 0.05, 0.10, 0.10, 1000, 5, 0.02
    check("physics.em.magnetic_field_currents", {"Bw": mu0 * I / (2 * math.pi * r), "Bc": mu0 * I / (2 * Rl), "Ba": mu0 * I * Rl**2 / (2 * (Rl**2 + z**2) ** 1.5), "Bs": mu0 * n * I, "Fl": mu0 * I * I2 / (2 * math.pi * d)})


def test_ampere_defines_the_force_between_wires():
    """The old definition of the ampere: 1 A in two wires 1 m apart gives 2e-7 N/m."""
    out, _ = run("physics.em.magnetic_field_currents", Ic="1 A", I2="1 A", dw="1 m")
    assert out["Fl"] == pytest.approx(2e-7, rel=1e-9)


def test_loop_axis_field_reduces_to_centre_field_at_z_zero():
    out, _ = run("physics.em.magnetic_field_currents", z="0 cm")
    assert out["Ba"] == pytest.approx(out["Bc"])


def test_charged_particle():
    q, m, v, B, E = e, 1.67262192369e-27, 2e6, 0.5, 1e6
    check("physics.em.charged_particle_in_b_field", {"rc": m * v / (q * B), "Tc": 2 * math.pi * m / (q * B), "wc": q * B / m, "fc": q * B / m / (2 * math.pi), "Ek": m * v * v / 2, "vsel": E / B})


def test_induced_emf():
    w = 377.0
    check("physics.em.induced_emf", {"Em": 0.4 * 0.5 * 6, "Ef": -200 * 50e-4 * 0.3 / 0.02, "Ep": 200 * 0.4 * 50e-4 * w, "Er": 200 * 0.4 * 50e-4 * w / math.sqrt(2)})


# ---------------------------------------------------------------- modern physics
def test_photoelectric():
    lam, phi = 250e-9, 2.28 * e
    Eph = h * c / lam
    K = Eph - phi
    check("physics.modern.photoelectric_effect", {"Eph": Eph, "KEm": K, "Vs": K / e, "vm": math.sqrt(2 * K / me), "f0": phi / h, "lam0": h * c / phi})


def test_photoelectric_below_threshold_is_explained():
    impossible("physics.modern.photoelectric_effect", "below the work function", lam="700 nm")


def test_faster_than_light_is_explained():
    impossible("physics.modern.special_relativity", "below the speed of light", v="3.1e8 m/s")


def test_violated_limit_that_still_computes_is_a_warning():
    calc = CAT.get("physics.thermo.entropy_change")
    s = solve(calc, {**calc.example, "Th": "200 K"})
    assert s.ok and any(d.level == "warning" and d.code == "VALIDITY" for d in s.diagnostics)


def test_de_broglie():
    m, v, dx = me, 1e6, 0.1e-9
    p = m * v
    check("physics.modern.de_broglie_uncertainty", {"p": p, "lam": h / p, "dp": h / (4 * math.pi * dx), "dv": h / (4 * math.pi * dx) / m})
    assert h / p == pytest.approx(0.7274e-9, rel=1e-3)         # the textbook electron wavelength at 10^6 m/s


def test_compton():
    lam, th = 71.1e-12, 90 * deg
    lc = h / (me * c)
    lam2 = lam + lc * (1 - math.cos(th))
    check("physics.modern.compton_scattering", {"lC": lc, "dlam": lc, "lam2": lam2, "E1": h * c / lam, "E2": h * c / lam2, "Ke": h * c / lam - h * c / lam2})
    back = run("physics.modern.compton_scattering", th="180 deg")[0]
    assert back["dlam"] == pytest.approx(2 * lc)


def test_bohr():
    check("physics.modern.bohr_hydrogen", {"Ei": -Rinf * h * c / 9, "Ef": -Rinf * h * c / 4, "dE": Rinf * h * c * (1 / 4 - 1 / 9), "lam": 1 / (Rinf * (1 / 4 - 1 / 9)), "rn": 4 * a0, "Eion": Rinf * h * c})
    out, _ = run("physics.modern.bohr_hydrogen")
    assert out["lam"] * 1e9 == pytest.approx(656.11, abs=0.01)                # H-alpha
    assert out["Eion"] / e == pytest.approx(13.6057, abs=1e-3)
    assert out["dE"] == pytest.approx(h * c / out["lam"], rel=1e-9)           # photon energy matches its wavelength


def test_bohr_helium_ion_scales_with_z_squared():
    he = run("physics.modern.bohr_hydrogen", Z="2")[0]
    h1 = run("physics.modern.bohr_hydrogen")[0]
    assert he["Eion"] == pytest.approx(4 * h1["Eion"]) and he["lam"] == pytest.approx(h1["lam"] / 4)


def test_relativity():
    v = 1.798754748e8
    gam = 1 / math.sqrt(1 - v**2 / c**2)
    u1 = 1e8
    check("physics.modern.special_relativity", {"gam": gam, "t": gam, "L": 1 / gam, "p": gam * me * v, "Et": gam * me * c**2, "KE": (gam - 1) * me * c**2, "us": (u1 + v) / (1 + u1 * v / c**2)}, rel=1e-6)
    assert gam == pytest.approx(1.25, rel=1e-6)
    assert run("physics.modern.special_relativity", u1=f"{c} m/s")[0]["us"] == pytest.approx(c)        # nothing exceeds c


def test_relativistic_energy_momentum_relation():
    out, _ = run("physics.modern.special_relativity")
    assert out["Et"] ** 2 == pytest.approx((out["p"] * c) ** 2 + (me * c**2) ** 2, rel=1e-9)


def test_relativity_at_low_speed_matches_newton():
    out, _ = run("physics.modern.special_relativity", v="1000 m/s")
    assert out["KE"] == pytest.approx(0.5 * me * 1000**2, rel=1e-6)


def test_particle_in_box():
    E1 = h**2 / (8 * me * 1e-18)
    check("physics.modern.particle_in_box", {"Ei": E1, "Ef": 4 * E1, "dE": 3 * E1, "lam": h * c / (3 * E1)})
    assert E1 / e == pytest.approx(0.376, abs=1e-3)


# ---------------------------------------------------------------- gravitation
def test_gravity():
    m1, m2, r = 5.972e24, 7.342e22, 3.844e8
    check("physics.gravitation.newton_gravity", {"F": G * m1 * m2 / r**2, "gl": G * m1 / r**2, "U": -G * m1 * m2 / r, "Eo": -G * m1 * m2 / (2 * r)})
    out, _ = run("physics.gravitation.newton_gravity")
    assert out["Eo"] == pytest.approx(out["U"] / 2)                          # virial theorem for a circular orbit


def test_schwarzschild():
    M, r = 2.7846e30, 12e3
    rs = 2 * G * M / c**2
    check("physics.gravitation.schwarzschild_redshift", {"rs": rs, "zr": 1 / math.sqrt(1 - rs / r) - 1, "rate": math.sqrt(1 - rs / r)})
    sun = run("physics.gravitation.schwarzschild_redshift", M="1.98847e30 kg", r="1e6 km")[0]
    assert sun["rs"] == pytest.approx(2953.25, rel=1e-3)                   # the Sun's Schwarzschild radius is about 2.95 km


# ---------------------------------------------------------------- general chemistry
def test_solution_concentration():
    Ms, Mv, w, rho = 36.46e-3, 18.015e-3, 0.37, 1180
    check("chemistry.general.solution_concentration", {"cm": w * rho / Ms, "bm": w / ((1 - w) * Ms), "xs": (w / Ms) / (w / Ms + (1 - w) / Mv)})
    assert run("chemistry.general.solution_concentration")[0]["cm"] / 1000 == pytest.approx(11.97, abs=0.01)       # 37 % HCl is about 12 M


def test_limiting_reagent():
    nA, nB = 4.0 / 2.016, 24 / 31.998
    xi = min(nA / 2, nB / 1)
    mth = 2 * xi * 18.015
    out, _ = run("chemistry.general.limiting_reagent_yield")
    assert out["xi"] == pytest.approx(xi) and out["mth"] == pytest.approx(mth * 1e-3) and out["py"] == pytest.approx(25 / mth)
    assert xi == nB                                                          # oxygen is limiting here


def test_limiting_reagent_switches_when_the_other_is_scarce():
    out, _ = run("chemistry.general.limiting_reagent_yield", mB="100 g")
    assert out["xi"] == pytest.approx(4.0 / 2.016 / 2)                        # now hydrogen limits


def test_dilution_and_mixing():
    check("chemistry.general.dilution_mixing", {"Cf": 12e3 * 25 / 500, "Vadd": 475e-6, "Cmix": (0.5 * 100 + 0.2 * 150) / 250 * 1e3})


def test_gas_laws():
    check("chemistry.general.gas_laws_dalton_graham", {"V2": 5e-3 * 300 / 273.15 / 2, "Pi": 0.21 * 760 * 133.322368, "rr": math.sqrt(32.00 / 2.016)}, rel=1e-5)


def test_colligative():
    R_ = R
    check("chemistry.general.colligative_properties", {"dTb": 2 * 0.512 * 0.5, "dTf": 2 * 1.86 * 0.5, "Pi": 2 * 490 * R_ * 298.15, "Pv": 0.9823 * 3169, "dP": 3169 - 0.9823 * 3169})


# ---------------------------------------------------------------- physical chemistry
def test_van_der_waals():
    a, b, n, V, T = 3.640e-1, 0.04267e-3, 1, 1e-3, 300          # a in Pa m^6/mol^2 (3.640 L^2 bar/mol^2 = 0.364)
    P = n * R * T / (V - n * b) - a * n**2 / V**2
    check("chemistry.physical.van_der_waals", {"P": P, "Pid": n * R * T / V, "Zc": P * V / (n * R * T)})
    assert run("chemistry.physical.van_der_waals")[0]["P"] / 1e5 == pytest.approx(22.415, abs=0.01)


def test_van_der_waals_becomes_ideal_for_a_dilute_gas():
    out, _ = run("chemistry.physical.van_der_waals", Vg="1000 L")
    assert out["Zc"] == pytest.approx(1, abs=1e-3)


def test_van_der_waals_volume_by_numerical_inversion():
    """Solving for V is a cubic: the automatic scan meets the pole at V = n·b, so a search range above it is given."""
    calc = CAT.get("chemistry.physical.van_der_waals")
    p = run("chemistry.physical.van_der_waals")[0]["P"]
    given = {k: v for k, v in calc.example.items() if k != "Vg"} | {"P": f"{p} Pa"}
    s = solve(calc, given, solve_for=["Vg"], search={"Vg": ["0.5 L", "5 L"]})
    assert s.ok and s.outputs[0]["si_value"] == pytest.approx(1e-3, rel=1e-4)


def test_gibbs_and_van_t_hoff():
    dH, dS, T, T2 = -92.4e3, -198.7, 298.15, 500
    dG = dH - T * dS
    K = math.exp(-dG / (R * T))
    check("chemistry.physical.gibbs_equilibrium_vant_hoff", {"dG": dG, "K": K, "K2": K * math.exp(-dH / R * (1 / T2 - 1 / T))})
    out, _ = run("chemistry.physical.gibbs_equilibrium_vant_hoff")
    assert out["K2"] < out["K"]                                              # an exothermic reaction favours products less when hot


def test_equilibrium_constant_from_gibbs_energy_inverts():
    out, _ = run("chemistry.physical.gibbs_equilibrium_vant_hoff", solve_for=["dH"], dG="-33.158 kJ/mol")
    assert out["dH"] == pytest.approx(-92.4e3, rel=1e-3)


def test_integrated_rate_laws():
    A0, t, k0, k1, k2 = 0.5e3, 120, 2e0, 0.005, 0.01e-3
    check("chemistry.physical.integrated_rate_laws", {"Az": A0 - k0 * t, "Af": A0 * math.exp(-k1 * t), "As": 1 / (1 / A0 + k2 * t), "th0": A0 / (2 * k0), "th1": math.log(2) / k1, "th2": 1 / (k2 * A0)})


def test_half_life_leaves_half():
    out, _ = run("chemistry.physical.integrated_rate_laws")
    A0 = 0.5e3
    assert A0 * math.exp(-0.005 * out["th1"]) == pytest.approx(A0 / 2) and 1 / (1 / A0 + 0.01e-3 * out["th2"]) == pytest.approx(A0 / 2)


def test_eyring():
    dH, dS, T = 75e3, -20, 298.15
    dG = dH - T * dS
    check("chemistry.physical.eyring_transition_state", {"dGa": dG, "k": kB * T / h * math.exp(-dG / (R * T)), "Ea": dH + R * T})
    assert kB * 298.15 / h == pytest.approx(6.2125e12, rel=1e-4)


def test_clausius_clapeyron():
    P1, T1, dHv, T2, Pt = 101325, 373.15, 40.66e3, 353.15, 70e3
    check("chemistry.physical.clausius_clapeyron", {"P2": P1 * math.exp(-dHv / R * (1 / T2 - 1 / T1)), "Tb": 1 / (1 / T1 - R * math.log(Pt / P1) / dHv)})
    out, _ = run("chemistry.physical.clausius_clapeyron", T2="373.15 K")
    assert out["P2"] == pytest.approx(P1)                                    # same temperature: same pressure
    assert run("chemistry.physical.clausius_clapeyron", Pt="101.325 kPa")[0]["Tb"] == pytest.approx(373.15)


def test_calorimetry():
    check("chemistry.physical.calorimetry", {"Tf": 273.15 + 60, "dHr": -(100 * 4.184 + 20) * 6.5 / 0.05}, rel=1e-6)


# ---------------------------------------------------------------- analytical chemistry
def test_weak_acid_and_base():
    Ka, Ca = 1.8e-2, 100.0          # mol/m^3 (1.8e-5 mol/L and 0.10 mol/L)
    H = (-Ka + math.sqrt(Ka**2 + 4 * Ka * Ca)) / 2
    check("chemistry.analytical.weak_acid_base_ph", {"H": H, "pH": -math.log10(H / 1000), "pKa": -math.log10(Ka / 1000), "ion": H / Ca, "OH": H, "pHb": 14 + math.log10(H / 1000)})
    out, _ = run("chemistry.analytical.weak_acid_base_ph")
    assert out["pH"] == pytest.approx(2.875, abs=1e-3) and out["pHb"] == pytest.approx(11.125, abs=1e-3)


def test_weak_acid_satisfies_its_own_equilibrium_expression():
    out, _ = run("chemistry.analytical.weak_acid_base_ph")
    x = out["H"]
    assert x * x / (100.0 - x) == pytest.approx(1.8e-2, rel=1e-9)


def test_ph_for_a_target_concentration():
    out, _ = run("chemistry.analytical.weak_acid_base_ph", solve_for=["Ca"], H="1.3327e-3 mol/L")
    assert out["Ca"] / 1000 == pytest.approx(0.10, rel=1e-3)


def test_henderson_hasselbalch():
    check("chemistry.analytical.henderson_hasselbalch", {"pH0": 4.76, "pH1": 4.76 + math.log10(80 / 120)})
    assert run("chemistry.analytical.henderson_hasselbalch", nA="200 mmol")[0]["pH0"] == pytest.approx(4.76 + math.log10(2))


def test_buffer_ratio_for_a_target_ph():
    out, _ = run("chemistry.analytical.henderson_hasselbalch", solve_for=["nA"], pH0="5.06")
    assert out["nA"] / 1e-3 == pytest.approx(100 * 10 ** (5.06 - 4.76), rel=1e-6)


def test_solubility_product():
    s = (1.1e-12 / 4) ** (1 / 3) * 1000          # mol/m^3
    check("chemistry.analytical.solubility_product", {"s": s, "cM": 2 * s, "cX": s, "Qi": 1e-3**2 * 5e-4}, rel=1e-5)
    assert s / 1000 == pytest.approx(6.5e-5, rel=1e-2)                       # Ag2CrO4 is about 6.5e-5 M


def test_common_ion_suppresses_solubility():
    plain = run("chemistry.analytical.solubility_product", Ksp="1.77e-10", a="1", b="1", cc="0 mol/L")[0]["s"]
    suppressed = run("chemistry.analytical.solubility_product", Ksp="1.77e-10", a="1", b="1", cc="0.10 mol/L")[0]["s"]
    assert plain / 1000 == pytest.approx(math.sqrt(1.77e-10), rel=1e-4)
    assert suppressed / 1000 == pytest.approx(1.77e-9, rel=1e-3)             # AgCl in 0.10 M chloride


# ---------------------------------------------------------------- spectroscopy
def test_diatomic():
    m1, m2, k, re, J = 1.00782503 * Da, 34.96885268 * Da, 516, 1.275e-10, 3
    mu = m1 * m2 / (m1 + m2)
    nu = math.sqrt(k / mu) / (2 * math.pi * c)
    I = mu * re**2
    B = h / (8 * math.pi**2 * c * I)
    check("chemistry.spectroscopy.diatomic_vibration_rotation", {"mu": mu, "nu": nu, "zpe": h * c * nu * NA / 2, "Inr": I, "Bc": B, "FJ": B * J * (J + 1)}, rel=1e-6)
    out, _ = run("chemistry.spectroscopy.diatomic_vibration_rotation")
    assert out["nu"] / 100 == pytest.approx(2990, abs=2)                       # HCl fundamental ~2991 cm^-1
    assert out["Bc"] / 100 == pytest.approx(10.59, abs=0.02)                  # HCl rotational constant ~10.59 cm^-1


# ---------------------------------------------------------------- catalogue-level behaviour
from sliderule.library import chemistry as _chem_pilot, physics as _phys_pilot

NEW = [c_.id for c_ in (*_phys_pilot.CALCS, *_chem_pilot.CALCS)]       # the pilot set; the core set has its own tests (test_pc_*.py)


def test_pilot_size_and_ids():
    assert len(NEW) == 49 and sum(i.startswith("physics.") for i in NEW) == 34


def test_every_new_calculation_belongs_to_its_discipline_and_a_subdiscipline():
    for cid in NEW:
        c_ = CAT.get(cid)
        assert cid.split(".")[0] in c_.disciplines and c_.subdisciplines and c_.references and c_.assumptions, cid


def test_existing_engineering_disciplines_are_cross_listed():
    blackbody = CAT.get("physics.thermo.blackbody_radiation")
    assert {"physics", "mechanical", "energy"} <= set(blackbody.disciplines)
    assert "chemical" in CAT.get("chemistry.general.colligative_properties").disciplines
    assert "biomedical" in CAT.get("chemistry.analytical.henderson_hasselbalch").disciplines


def test_existing_calculations_are_listed_under_the_new_subdisciplines_without_duplicates():
    for cid, sub in (("mechanical.sports.projectile_range", "Classical Mechanics"), ("chemical.kinetics.arrhenius", "Physical Chemistry"),
                     ("electrical.photonics.beer_lambert", "Analytical Chemistry"), ("space.planetary.escape_velocity", "Gravitation and Astrophysics")):
        c_ = CAT.get(cid)
        assert sub in c_.subdisciplines and c_.disciplines, cid
    names = [c_.name.lower() for c_ in CAT]
    assert len(names) == len(set(names))


def test_search_finds_the_new_equations_by_name_and_tag():
    from sliderule import api
    res = api.list_calculations("snell", [], [], [], [])
    assert any(r["id"] == "physics.optics.snell_refraction" for r in res["results"])
    res = api.list_calculations("henderson", ["chemistry"], [], [], [])
    assert "chemistry.analytical.henderson_hasselbalch" in [r["id"] for r in res["results"]]
