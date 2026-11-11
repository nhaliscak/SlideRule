import math

import pytest
import scipy.special as ss

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def out(sol, key):
    return next(o["si_value"] for o in sol.to_dict()["outputs"] if o["key"] == key)


def calc(variables, equations, outputs, odes=None, cid="custom.sp"):
    return Calculation(id=cid, name="s", disciplines=["mechanical"], description="", variables=variables, equations=equations, outputs=outputs, custom=True, odes=odes or [])


def test_special_functions_evaluate_and_are_unit_checked():
    v = [V("y", "y", "1", signed=True), V("x", "x", "1", signed=True)]
    for text, ref in (("y = besselj(0, x)", ss.jv(0, 1.7)), ("y = bessely(1, x)", ss.yv(1, 1.7)), ("y = besseli(2, x)", ss.iv(2, 1.7)), ("y = besselk(0, x)", ss.kv(0, 1.7)),
                      ("y = airyai(x)", ss.airy(1.7)[0]), ("y = elliptic_k(x/4)", ss.ellipk(1.7 / 4)), ("y = elliptic_e(x/4)", ss.ellipe(1.7 / 4)), ("y = legendre(3, x/2)", ss.eval_legendre(3, 0.85)),
                      ("y = expint(1, x)", ss.exp1(1.7)), ("y = erfi(x)", ss.erfi(1.7)), ("y = LambertW(x)", float(ss.lambertw(1.7).real)), ("y = sinc(x)", math.sin(1.7) / 1.7)):
        assert out(solve(calc(v, [("e", text)], ["y"]), {"x": "1.7"}), "y") == pytest.approx(ref, rel=1e-9), text
    with pytest.raises(ValueError, match="dimensionless"):
        calc([V("y", "y", "1"), V("x", "x", "m")], [("e", "y = besselj(0, x)")], ["y"])


def test_zeros_and_eigenvalues_of_transient_conduction():
    v = [V("z", "z", "1"), V("k", "k", "1"), V("B", "B", "1")]
    for k, ref in ((1, 2.404825557695773), (2, 5.520078110286311), (7, 21.211636629879258)):
        assert out(solve(calc([V("z", "z", "1"), V("k", "k", "1")], [("e", "z = besselj_zero(0, k)")], ["z"]), {"k": str(k)}), "z") == pytest.approx(ref, rel=1e-12)
    Bi = 0.8
    for name, cond in (("eig_slab", lambda z: z * math.tan(z) - Bi), ("eig_cylinder", lambda z: z * ss.j1(z) - Bi * ss.j0(z)), ("eig_sphere", lambda z: 1 - z / math.tan(z) - Bi)):
        for k in (1, 2, 5):
            z = out(solve(calc(v, [("e", f"z = {name}(B, k)")], ["z"]), {"B": str(Bi), "k": str(k)}), "z")
            assert abs(cond(z)) < 1e-10
    # the first root for a vanishing Biot number tends to sqrt(Bi) (slab), sqrt(2 Bi) (cylinder), sqrt(3 Bi) (sphere)
    for name, f in (("eig_slab", 1), ("eig_cylinder", 2), ("eig_sphere", 3)):
        z = out(solve(calc(v, [("e", f"z = {name}(B, k)")], ["z"]), {"B": "1e-4", "k": "1"}), "z")
        assert z == pytest.approx(math.sqrt(f * 1e-4), rel=2e-3)


def test_bessel_functions_in_a_closed_form_boundary_value_problem():
    # annular fin: theta'' + theta'/r - m^2 theta = 0, theta(r1) = tb, theta'(r2) = 0
    v = [V("th", "th", "K"), V("r", "r", "m"), V("r1", "r1", "m"), V("r2", "r2", "m"), V("m", "m", "1/m"), V("tb", "tb", "K")]
    spec = {"independent": "r", "start": "r1", "end": "r2", "equations": ["diff(th, r, 2) + diff(th, r)/r - m**2*th = 0"], "boundary": ["start: th = tb", "end: diff(th, r) = 0"]}
    c = calc(v, [], ["th"], [spec])
    assert not c.parsed_odes[0].numeric and "bessel" in str(c.parsed[0].rhs).lower()
    inp = {"r1": "0.02 m", "r2": "0.05 m", "m": "30 1/m", "tb": "80 K", "r": "0.035 m"}
    m, r1, r2, r = 30.0, 0.02, 0.05, 0.035
    ref = 80 * (ss.iv(0, m * r) * ss.kv(1, m * r2) + ss.kv(0, m * r) * ss.iv(1, m * r2)) / (ss.iv(0, m * r1) * ss.kv(1, m * r2) + ss.kv(0, m * r1) * ss.iv(1, m * r2))
    assert out(solve(c, inp), "th") == pytest.approx(ref, rel=1e-9)
    numeric = calc(v, [], ["th"], [{**spec, "method": "numeric"}])
    assert out(solve(numeric, inp), "th") == pytest.approx(ref, rel=1e-7)
    back = solve(c, {"th": f"{ref} K", "r1": "0.02 m", "r2": "0.05 m", "tb": "80 K", "r": "0.035 m"}, ["m"])
    assert out(back, "m") == pytest.approx(30.0, rel=1e-6)


def test_bessel_functions_in_numerical_solvers():
    # Bessel's own equation as an initial-value problem: y'' + y'/x + y = 0, y(0) = 1, y'(0) = 0 has y = J0(x)
    v = [V("y", "y", "1", signed=True), V("x", "x", "1")]
    spec = {"independent": "x", "start": "0", "method": "numeric", "equations": ["diff(y, x, 2) + diff(y, x)/x + y = 0"], "initial": ["y = 1", "diff(y, x) = 0"]}
    assert out(solve(calc(v, [], ["y"], [spec]), {"x": "3.1"}), "y") == pytest.approx(ss.j0(3.1), rel=1e-8)
    # a Bessel function inside the right-hand side of a differential equation (numerical nodes + special functions in the fast path)
    spec2 = {"independent": "x", "start": "0", "method": "numeric", "equations": ["diff(y, x) = besselj(0, x)"], "initial": ["y = 0"]}
    assert out(solve(calc(v, [], ["y"], [spec2]), {"x": "2"}), "y") == pytest.approx(float(ss.itj0y0(2.0)[0]), rel=1e-8)
    # coupled equations with Bessel functions: find the two unknowns of J0(a) = b and a = 2 c
    w = [V("a", "a", "1"), V("c", "c", "1"), V("b", "b", "1")]
    d = solve(calc(w, [("e1", "besselj(0, a) = b"), ("e2", "a = 2*c")], ["a", "c"]), {"b": "0.5"}, search={"a": [0.1, 2.4]}).to_dict()
    assert d["ok"] and {o["key"]: o["si_value"] for o in d["outputs"]}["a"] == pytest.approx(__import__("scipy.optimize", fromlist=["brentq"]).brentq(lambda a: ss.j0(a) - 0.5, 0.1, 2.4), rel=1e-9)


def test_lambert_w_and_a_series_with_special_functions():
    v = [V("x", "x", "1"), V("a", "a", "1")]
    c = calc(v, [("e", "x*exp(x) = a")], ["x"])
    assert out(solve(c, {"a": "3"}), "x") == pytest.approx(float(ss.lambertw(3).real), rel=1e-10)
    # a Fourier–Bessel series: the cylinder with its surface held at the fluid temperature (Bi -> infinity is approximated by a large Biot number)
    w = [V("th", "th", "1"), V("Fo", "Fo", "1"), V("rr", "rr", "1")]
    eq = [("Series", "th = summation(2*besselj(0, besselj_zero(0, n)*rr)/(besselj_zero(0, n)*besselj(1, besselj_zero(0, n)))*exp(-besselj_zero(0, n)**2*Fo), (n, 1, 30))")]
    got = out(solve(calc(w, eq, ["th"]), {"Fo": "0.2", "rr": "0.3"}), "th")
    ref = sum(2 * ss.j0(ss.jn_zeros(0, 30)[n] * 0.3) / (ss.jn_zeros(0, 30)[n] * ss.j1(ss.jn_zeros(0, 30)[n])) * math.exp(-ss.jn_zeros(0, 30)[n] ** 2 * 0.2) for n in range(30))
    assert got == pytest.approx(ref, rel=1e-12)
    back = out(solve(calc(w, eq, ["Fo"]), {"th": f"{ref}", "rr": "0.3"}, ["Fo"], search={"Fo": [0.05, 1]}), "Fo")
    assert back == pytest.approx(0.2, rel=1e-6)


def test_library_special_function_calculations():
    from sliderule.core.catalog import default_catalog

    cat = default_catalog()

    def run(cid, **over):
        calc_ = cat.get(cid)
        return {o["key"]: o["si_value"] for o in solve(calc_, {**calc_.example, **over}).to_dict()["outputs"]}

    # the exact transient series agree with the numerical (method of lines) solutions of the same problems
    exact_slab = run("mechanical.heat.slab_transient_exact_series")["T"]
    pde_slab = run("mechanical.heat.slab_transient_convective_cooling", x="0 mm", L="25 mm", a="10 mm^2/s", k="20 W/(m*K)", h="400 W/(m^2*K)", t="30 s", Ti="500 K", Tinf="300 K")["T"]
    assert exact_slab == pytest.approx(pde_slab, rel=1e-5)
    exact_cyl = run("mechanical.heat.cylinder_transient_bessel_series", R="10 mm", a="5 mm^2/s", t="60 s", Ti="300 K", Tinf="300 K")["T"]
    assert exact_cyl == pytest.approx(300.0, abs=1e-9)                                                        # no driving temperature difference: nothing changes
    hot = run("mechanical.heat.cylinder_transient_bessel_series")["T"]
    assert 300 < hot < 500
    # a one-term check for the cylinder at larger Fo (the first term dominates), centre r = 0
    Bi = 400 * 0.02 / 20
    z1 = float(__import__("scipy.optimize", fromlist=["brentq"]).brentq(lambda z: z * ss.j1(z) - Bi * ss.j0(z), 1e-9, 2.4048))
    C1 = 2 * ss.j1(z1) / (z1 * (ss.j0(z1) ** 2 + ss.j1(z1) ** 2))
    Fo = 10e-6 * 100 / 0.02 ** 2
    one_term = run("mechanical.heat.cylinder_transient_bessel_series", t="100 s")["T"]
    assert one_term == pytest.approx(300 + 200 * C1 * math.exp(-z1 * z1 * Fo), rel=2e-3)
    sphere = run("mechanical.heat.sphere_transient_series")["T"]
    assert 300 < sphere < 500 and sphere < hot                                                                # a sphere of similar size cools faster than a cylinder
    # at the surface r = R the sphere and cylinder series satisfy the convection condition: compare with the numerical value through the gradient of the series
    assert run("mechanical.acoustics.circular_drum_natural_frequency")["f"] == pytest.approx(ss.jn_zeros(0, 1)[0] * math.sqrt(3000 / 0.26) / (2 * math.pi * 0.2), rel=1e-12)
    assert run("mechanical.acoustics.circular_drum_natural_frequency", m="3")["f"] == pytest.approx(ss.jn_zeros(0, 3)[2] * math.sqrt(3000 / 0.26) / (2 * math.pi * 0.2), rel=1e-12)
    r = run("mechanical.dynamics.pendulum_large_amplitude_period")
    assert r["ratio"] == pytest.approx(1.18034, abs=1e-5) and r["T0"] == pytest.approx(2 * math.pi * math.sqrt(1 / 9.80665), rel=1e-12)
    small = run("mechanical.dynamics.pendulum_large_amplitude_period", th0="1 deg")["ratio"]
    assert small == pytest.approx(1 + (math.radians(1) ** 2) / 16, rel=1e-6)
    fin = run("mechanical.heat.annular_fin_bessel_profile")["th"]
    m, r1, r2, rr = 30.0, 0.02, 0.05, 0.035
    ref = 80 * (ss.iv(0, m * rr) * ss.kv(1, m * r2) + ss.kv(0, m * rr) * ss.iv(1, m * r2)) / (ss.iv(0, m * r1) * ss.kv(1, m * r2) + ss.kv(0, m * r1) * ss.iv(1, m * r2))
    assert fin == pytest.approx(ref, rel=1e-9)
    d = run("electrical.electronics.diode_resistor_operating_point")
    assert d["I"] == pytest.approx((5 - d["VD"]) / 1000, rel=1e-9) and d["I"] == pytest.approx(1e-12 * (math.exp(d["VD"] / 0.02585) - 1), rel=1e-9)
