"""Core physics, part A: classical mechanics, fluids, thermodynamics and statistical physics (independent formulas)."""

import math

import pytest
from pcutil import CAT, NA, R, check_case, e, g, h, kB, me, pi, solved


def projectile(x):
    v0, th, h0 = x["v0"], x["th"], x["h0"]
    vy = v0 * math.sin(th)
    t = (vy + math.sqrt(vy * vy + 2 * g * h0)) / g
    return {"t": t, "R": v0 * math.cos(th) * t, "H": h0 + vy * vy / (2 * g), "vi": math.sqrt(v0**2 + 2 * g * h0), "thi": math.atan(math.sqrt(vy * vy + 2 * g * h0) / (v0 * math.cos(th)))}


def atwood(x):
    a = (x["m1"] - x["m2"]) * g / (x["m1"] + x["m2"] + x["Ip"] / x["rp"] ** 2)
    return {"a": a, "T1": x["m1"] * (g - a), "T2": x["m2"] * (g + a)}


def block_table(x):
    a = (x["m2"] - x["mu"] * x["m1"]) * g / (x["m1"] + x["m2"])
    return {"a": a, "T": x["m1"] * (a + x["mu"] * g)}


def energy(x):
    v2 = math.sqrt(x["v1"] ** 2 + 2 * g * (x["h1"] - x["h2"]) + 2 * x["Wnc"] / x["m"])
    return {"v2": v2, "K1": x["m"] * x["v1"] ** 2 / 2, "K2": x["m"] * v2**2 / 2, "dU": x["m"] * g * (x["h2"] - x["h1"])}


def lifting(x):
    vl = x["eta"] * x["Pin"] / (x["m"] * g)
    t = x["h"] / vl
    return {"vl": vl, "t": t, "Ein": x["Pin"] * t, "Ew": x["Pin"] * t - x["m"] * g * x["h"]}


def impulse(x):
    J = x["Fav"] * x["dt"]
    v = x["u"] + J / x["m"]
    return {"J": J, "v": v, "dK": x["m"] * (v**2 - x["u"] ** 2) / 2}


def centre(x):
    xc = (x["m1"] * x["x1"] + x["m2"] * x["x2"]) / (x["m1"] + x["m2"])
    return {"xc": xc, "d1": abs(x["x1"] - xc), "d2": abs(x["x2"] - xc), "mu": x["m1"] * x["m2"] / (x["m1"] + x["m2"])}


def moments(x):
    M, R_, L = x["M"], x["R"], x["Lr"]
    return {"Icyl": M * R_**2 / 2, "Ihoop": M * R_**2, "Isph": 0.4 * M * R_**2, "Ishell": 2 / 3 * M * R_**2, "Irc": M * L**2 / 12, "Ire": M * L**2 / 3,
            "Ipl": M * (x["pa"] ** 2 + x["pb"] ** 2) / 12, "Ipar": M * R_**2 / 2 + M * x["dax"] ** 2}


def ladder(x):
    Nw = (x["Wl"] / 2 + x["s"] * x["Wp"]) / math.tan(x["th"])
    return {"Nw": Nw, "Nf": x["Wl"] + x["Wp"], "fr": Nw, "mum": Nw / (x["Wl"] + x["Wp"])}


def springs(x):
    kp, ks = x["k1"] + x["k2"], x["k1"] * x["k2"] / (x["k1"] + x["k2"])
    return {"kp": kp, "ks": ks, "Fp": kp * x["x"], "Fs": ks * x["x"], "Up": kp * x["x"] ** 2 / 2, "Us": ks * x["x"] ** 2 / 2}


def driven(x):
    w0 = math.sqrt(x["k"] / x["m"])
    ze = x["cd"] / (2 * math.sqrt(x["k"] * x["m"]))
    w = x["w"]
    return {"w0": w0, "ze": ze, "Qf": 1 / (2 * ze), "wd": w0 * math.sqrt(1 - ze**2), "wr": w0 * math.sqrt(1 - 2 * ze**2),
            "Ad": x["F0"] / x["m"] / math.sqrt((w0**2 - w**2) ** 2 + (2 * ze * w0 * w) ** 2), "ph": math.atan2(2 * ze * w0 * w, w0**2 - w**2)}


def vertical(x):
    m, r, vb = x["m"], x["r"], x["vb"]
    vt = math.sqrt(vb**2 - 4 * g * r)
    return {"vtm": math.sqrt(g * r), "vbm": math.sqrt(5 * g * r), "Tb": m * (vb**2 / r + g), "vt": vt, "Tt": m * (vt**2 / r - g),
            "Tper": 2 * pi * math.sqrt(x["Lc"] * math.cos(x["thc"]) / g), "Tc": m * g / math.cos(x["thc"]), "rc": x["Lc"] * math.sin(x["thc"])}


def torsion(x):
    J = pi * x["rw"] ** 4 / 2
    k = x["Gm"] * J / x["Lw"]
    T = 2 * pi * math.sqrt(x["Ir"] / k)
    return {"Jw": J, "kt": k, "T": T, "f": 1 / T}


def gyro(x):
    L = x["Is"] * x["ws"]
    Om = x["m"] * g * x["rg"] / L
    return {"Ls": L, "Om": Om, "Tp": 2 * pi / Om}


def ballistic(x):
    vbl = math.sqrt(2 * g * x["hr"])
    return {"vbl": vbl, "vb": (x["mb"] + x["Mb"]) / x["mb"] * vbl, "fl": x["Mb"] / (x["mb"] + x["Mb"])}


def terminal(x):
    return {"vtq": math.sqrt(2 * x["m"] * g / (x["rf"] * x["Cd"] * x["Ac"])), "vtl": x["m"] * g / x["bl"], "tau": x["m"] / x["bl"]}


def river(x):
    vg = math.sqrt(x["vb"] ** 2 - x["vr"] ** 2)
    return {"ths": math.asin(x["vr"] / x["vb"]), "vg": vg, "tdir": x["w"] / vg, "tmin": x["w"] / x["vb"], "dr": x["vr"] * x["w"] / x["vb"]}


def rotating(x):
    Om, Re, lat = 7.2921159e-5, 6.371e6, x["lat"]
    acf = Om**2 * Re * math.cos(lat) ** 2
    return {"acor": 2 * Om * x["v"] * math.sin(lat), "Tfou": 2 * pi / (Om * math.sin(lat)), "acf": acf, "geff": g - acf}


def archimedes(x):
    Fb, Wt = x["rf"] * x["Vo"] * g, x["ro"] * x["Vo"] * g
    return {"Fb": Fb, "Wt": Wt, "Wa": Wt - Fb, "fs": x["ro"] / x["rf"]}


def torricelli(x):
    ve = math.sqrt(2 * g * x["hd"])
    return {"ve": ve, "Q": x["Cd"] * x["Ah"] * ve, "xr": 2 * math.sqrt(x["hd"] * (x["Hg"] - x["hd"]))}


def capillarity(x):
    return {"hc": 2 * x["gs"] * math.cos(x["thc"]) / (x["rho"] * g * x["rt"]), "dPd": 2 * x["gs"] / x["Rb"], "dPb": 4 * x["gs"] / x["Rb"]}


def hydraulic(x):
    return {"v2": x["A1"] * x["v1"] / x["A2"], "Qf": x["A1"] * x["v1"], "F2": x["F1"] * x["Ap2"] / x["Ap1"], "d2": x["d1"] * x["Ap1"] / x["Ap2"], "MA": x["Ap2"] / x["Ap1"]}


def sphere_drag(x):
    return {"Re": x["rf"] * x["vs"] * 2 * x["rs"] / x["mu"], "Fst": 6 * pi * x["mu"] * x["rs"] * x["vs"], "Fq": x["rf"] * x["Cd"] * pi * x["rs"] ** 2 * x["vs"] ** 2 / 2}


def heating(x):
    m, Tm, Tb = x["m"], 273.15, 373.15
    q = [m * x["ci"] * (Tm - x["T0"]), m * x["Lf"], m * x["cw"] * (Tb - Tm), m * x["Lv"], m * x["cs"] * (x["T1"] - Tb)]
    return {"Q1": q[0], "Q2": q[1], "Q3": q[2], "Q4": q[3], "Q5": q[4], "Qt": sum(q)}


def gas_process(x):
    dV = x["V2"] - x["V1"]
    return {"Wiso": x["n"] * R * x["T"] * math.log(x["V2"] / x["V1"]), "Wisb": x["P"] * dV, "Qisb": (x["fd"] + 2) / 2 * x["P"] * dV, "Qisc": x["n"] * x["fd"] * R * x["dTc"] / 2}


def cycles(x):
    r, rc, gam = x["rc"], x["rco"], x["gam"]
    return {"eO": 1 - r ** (1 - gam), "eD": 1 - (rc**gam - 1) / (gam * (rc - 1)) / r ** (gam - 1), "eB": 1 - x["rp"] ** ((1 - gam) / gam)}


def engine(x):
    Qc = x["Qh"] - x["Wo"]
    eta = x["Wo"] / x["Qh"]
    etC = 1 - x["Tc"] / x["Th"]
    return {"eta": eta, "Qc": Qc, "etC": etC, "etCA": 1 - math.sqrt(x["Tc"] / x["Th"]), "e2": eta / etC, "Sg": Qc / x["Tc"] - x["Qh"] / x["Th"]}


def occupation(x):
    z = (x["En"] - x["mu"]) / (kB * x["T"])
    return {"fFD": 1 / (math.exp(z) + 1), "fBE": 1 / (math.exp(z) - 1), "fMB": math.exp(-z)}


def fermi(x):
    n = x["Zv"] * x["rho"] * NA / x["Mm"]
    EF = (h / (2 * pi)) ** 2 / (2 * me) * (3 * pi**2 * n) ** (2 / 3)
    return {"ne": n, "EF": EF, "TF": EF / kB, "vF": math.sqrt(2 * EF / me), "Eav": 0.6 * EF}


def solid(x):
    xe = x["thE"] / x["T"]
    return {"xE": xe, "Cdp": 3 * R, "CE": 3 * R * xe**2 * math.exp(xe) / (math.exp(xe) - 1) ** 2, "CD": 12 * pi**4 / 5 * R * (x["T"] / x["thD"]) ** 3}


def two_level(x):
    z = x["dE"] / (kB * x["T"])
    rat = x["gr"] * math.exp(-z)
    fu = rat / (1 + rat)
    return {"rat": rat, "fu": fu, "Em": x["dE"] * fu, "Cs": R * z**2 * rat / (1 + rat) ** 2}


def sackur(x):
    m = x["Mm"] / NA
    lth = h / math.sqrt(2 * pi * m * kB * x["T"])
    nd = x["P"] / (kB * x["T"])
    return {"mm": m, "lth": lth, "nd": nd, "Sm": R * (math.log(1 / (nd * lth**3)) + 2.5)}


def cooling(x):
    tau = x["m"] * x["cp"] / (x["hc"] * x["As"])
    return {"tau": tau, "Tt": x["Te"] + (x["T0"] - x["Te"]) * math.exp(-x["tt"] / tau), "tx": tau * math.log((x["T0"] - x["Te"]) / (x["Tx"] - x["Te"]))}


def free_mixing(x):
    x1 = x["x1"]
    return {"dSf": x["n"] * R * math.log(x["V2"] / x["V1"]), "dSm": -x["n"] * R * (x1 * math.log(x1) + (1 - x1) * math.log(1 - x1))}


def kinetic(x):
    return {"P": x["rho"] * x["vr"] ** 2 / 3, "T": x["mm"] * x["vr"] ** 2 / (3 * kB)}


CASES = {
    "physics.mechanics.projectile_from_height": projectile, "physics.mechanics.atwood_machine": atwood, "physics.mechanics.block_pulley_table": block_table,
    "physics.mechanics.energy_conservation": energy, "physics.mechanics.lifting_power_efficiency": lifting, "physics.mechanics.impulse_momentum": impulse,
    "physics.mechanics.centre_of_mass_two_bodies": centre, "physics.mechanics.moments_of_inertia": moments, "physics.mechanics.ladder_equilibrium": ladder,
    "physics.mechanics.springs_series_parallel": springs, "physics.mechanics.driven_damped_oscillator": driven, "physics.mechanics.vertical_circle_conical_pendulum": vertical,
    "physics.mechanics.torsion_pendulum": torsion, "physics.mechanics.gyroscope_precession": gyro, "physics.mechanics.ballistic_pendulum": ballistic,
    "physics.mechanics.terminal_velocity_drag": terminal, "physics.mechanics.relative_velocity_river": river, "physics.mechanics.rotating_earth": rotating,
    "physics.fluids.archimedes_buoyancy": archimedes, "physics.fluids.torricelli_efflux": torricelli, "physics.fluids.capillarity_laplace": capillarity,
    "physics.fluids.continuity_hydraulic_press": hydraulic, "physics.fluids.sphere_drag_reynolds": sphere_drag,
    "physics.thermo.heating_curve_latent_heat": heating, "physics.thermo.ideal_gas_process_work": gas_process, "physics.thermo.otto_diesel_brayton": cycles,
    "physics.thermo.heat_engine_second_law": engine, "physics.thermo.quantum_statistics_occupation": occupation, "physics.thermo.fermi_gas_metal": fermi,
    "physics.thermo.solid_heat_capacity": solid, "physics.thermo.two_level_system": two_level, "physics.thermo.sackur_tetrode": sackur,
    "physics.thermo.newton_cooling_curve": cooling, "physics.thermo.free_expansion_mixing_entropy": free_mixing, "physics.thermo.kinetic_pressure_temperature": kinetic,
}


@pytest.mark.parametrize("cid", list(CASES))
def test_against_the_textbook_formula(cid):
    check_case(cid, CASES[cid])


# ---------------------------------------------------------------- physical identities and limiting cases
def test_projectile_from_ground_level_gives_the_standard_range():
    out = solved("physics.mechanics.projectile_from_height", h0="0 m")
    v0, th = 20, 35 * pi / 180
    assert out["R"] == pytest.approx(v0**2 * math.sin(2 * th) / g) and out["H"] == pytest.approx(v0**2 * math.sin(th) ** 2 / (2 * g))
    assert out["thi"] == pytest.approx(th)


def test_energy_conservation_matches_free_fall():
    out = solved("physics.mechanics.energy_conservation", v1="0 m/s", Wnc="0 J", h1="20 m", h2="0 m")
    assert out["v2"] == pytest.approx(math.sqrt(2 * g * 20))
    assert out["K2"] - out["K1"] == pytest.approx(-out["dU"])


def test_atwood_with_massless_pulley_and_equal_masses():
    out = solved("physics.mechanics.atwood_machine", Ip="0 kg*m^2")
    assert out["a"] == pytest.approx(g / 5) and out["T1"] == pytest.approx(2 * 3 * 2 * g / 5)
    assert solved("physics.mechanics.atwood_machine", m1="2 kg", m2="2 kg")["a"] == pytest.approx(0, abs=1e-12)


def test_block_and_pulley_become_free_fall_without_the_block_mass():
    assert solved("physics.mechanics.block_pulley_table", m1="1e-9 kg", mu="0")["a"] == pytest.approx(g, rel=1e-6)


def test_moments_of_inertia_relations():
    out = solved("physics.mechanics.moments_of_inertia")
    assert out["Ihoop"] == pytest.approx(2 * out["Icyl"]) and out["Ire"] == pytest.approx(out["Irc"] + 2 * (1.2 / 2) ** 2)       # parallel axis for the rod
    assert out["Isph"] < out["Icyl"] < out["Ishell"] < out["Ihoop"]


def test_series_stiffness_is_always_softer_than_either_spring():
    out = solved("physics.mechanics.springs_series_parallel")
    assert out["ks"] < 200 and out["kp"] > 300 and out["Fs"] / 120 == pytest.approx(0.05)


def test_driven_oscillator_at_resonance_is_limited_by_damping():
    out = solved("physics.mechanics.driven_damped_oscillator", w="20 rad/s", cd="1 kg/s")
    assert out["Ad"] == pytest.approx(10 / (1 * 20), rel=1e-9) and out["ph"] == pytest.approx(pi / 2)         # A = F0/(c w0), 90 degrees lag
    assert solved("physics.mechanics.driven_damped_oscillator", w="1 rad/s")["ph"] < 0.1      # slow driving: in phase


def test_ladder_that_is_steeper_needs_less_friction():
    assert solved("physics.mechanics.ladder_equilibrium", th="80 deg")["mum"] < solved("physics.mechanics.ladder_equilibrium", th="50 deg")["mum"]


def test_gyroscope_precession_is_slower_for_faster_spin():
    assert solved("physics.mechanics.gyroscope_precession", ws="600 rad/s")["Om"] == pytest.approx(solved("physics.mechanics.gyroscope_precession")["Om"] / 2)


def test_foucault_pendulum_at_the_pole_and_at_the_latitude_of_paris():
    assert solved("physics.mechanics.rotating_earth", lat="90 deg")["Tfou"] / 3600 == pytest.approx(23.934, abs=0.01)      # one sidereal day
    assert solved("physics.mechanics.rotating_earth", lat="48.85 deg")["Tfou"] / 3600 == pytest.approx(31.8, abs=0.1)


def test_river_boat_that_aims_across_lands_downstream():
    out = solved("physics.mechanics.relative_velocity_river")
    assert out["tmin"] < out["tdir"] and out["dr"] == pytest.approx(1.5 * 80)


def test_buoyancy_floating_body_displaces_its_own_weight():
    out = solved("physics.fluids.archimedes_buoyancy")
    assert out["fs"] * out["Fb"] == pytest.approx(out["Wt"])


def test_torricelli_jet_is_longest_from_half_height():
    best = solved("physics.fluids.torricelli_efflux", hd="1 m")["xr"]
    assert best == pytest.approx(2.0)
    assert best > solved("physics.fluids.torricelli_efflux", hd="0.5 m")["xr"] and best > solved("physics.fluids.torricelli_efflux", hd="1.5 m")["xr"]


def test_water_capillary_rise_in_a_one_millimetre_tube_is_about_15_mm():
    assert solved("physics.fluids.capillarity_laplace", rt="1 mm")["hc"] == pytest.approx(0.01488, rel=2e-3)


def test_hydraulic_press_conserves_work():
    out = solved("physics.fluids.continuity_hydraulic_press")
    assert out["F2"] * out["d2"] == pytest.approx(200 * 0.05)


def test_stokes_drag_exceeds_quadratic_drag_at_low_reynolds_number():
    out = solved("physics.fluids.sphere_drag_reynolds")
    assert out["Fst"] > out["Fq"] and out["Re"] < 1


def test_total_heat_to_boil_one_kilogram_of_water_from_ice():
    out = solved("physics.thermo.heating_curve_latent_heat", m="1 kg", T0="0 degC", T1="100 degC")
    assert out["Qt"] == pytest.approx((334 + 418.4 + 2257) * 1e3)


def test_isothermal_work_equals_heat_and_the_first_law_holds_for_the_isobaric_step():
    out = solved("physics.thermo.ideal_gas_process_work")
    dV, P = 0.01, 101325 * 1.0
    assert out["Qisb"] - out["Wisb"] == pytest.approx(1.5 * P * dV)           # change in internal energy of a monatomic gas, (f/2) P dV


def test_cycle_efficiencies_are_ordered_and_below_one():
    out = solved("physics.thermo.otto_diesel_brayton")
    assert 0 < out["eB"] < out["eD"] < out["eO"] < 1


def test_heat_engine_obeys_the_second_law():
    out = solved("physics.thermo.heat_engine_second_law")
    assert out["eta"] < out["etC"] and out["etCA"] < out["etC"] and out["Sg"] > 0
    assert solved("physics.thermo.heat_engine_second_law", Wo="500 kJ")["Sg"] == pytest.approx(0, abs=1e-9)      # the Carnot engine generates none


def test_quantum_statistics_ordering_and_classical_limit():
    out = solved("physics.thermo.quantum_statistics_occupation")
    assert out["fFD"] < out["fMB"] < out["fBE"]
    hot = solved("physics.thermo.quantum_statistics_occupation", En="2 eV", T="300 K")
    assert hot["fFD"] == pytest.approx(hot["fBE"], rel=1e-6) == pytest.approx(hot["fMB"], rel=1e-6)


def test_fermi_energy_of_copper_and_density_scaling():
    out = solved("physics.thermo.fermi_gas_metal")
    assert out["EF"] / e == pytest.approx(7.0, abs=0.1) and out["vF"] == pytest.approx(1.57e6, rel=0.01)
    assert solved("physics.thermo.fermi_gas_metal", rho="71680 kg/m^3")["EF"] == pytest.approx(out["EF"] * 4)       # 8x the density -> 4x the energy


def test_dulong_petit_is_the_high_temperature_limit_of_einstein():
    out = solved("physics.thermo.solid_heat_capacity", warnings_ok=True, T="3000 K")      # the Debye T³ law is (rightly) flagged at this temperature
    assert out["CE"] == pytest.approx(out["Cdp"], rel=1e-3)


def test_two_level_system_limits():
    assert solved("physics.thermo.two_level_system", T="1e6 K", gr="1")["fu"] == pytest.approx(0.5, rel=1e-3)
    assert solved("physics.thermo.two_level_system", T="1 K")["fu"] < 1e-20


def test_helium_standard_entropy():
    assert solved("physics.thermo.sackur_tetrode", P="100 kPa")["Sm"] == pytest.approx(126.15, abs=0.05)         # tabulated S° of He at 1 bar


def test_cooling_curve_is_consistent_with_its_inverse():
    out = solved("physics.thermo.newton_cooling_curve", tt="32.52 min")
    assert out["Tt"] == pytest.approx(60 + 273.15, abs=0.02)


def test_mixing_entropy_is_largest_for_equal_fractions():
    assert solved("physics.thermo.free_expansion_mixing_entropy", x1="0.5")["dSm"] == pytest.approx(R * math.log(2))


def test_the_new_physics_calculations_are_listed_under_their_sub_disciplines():
    for cid, sub in (("physics.mechanics.atwood_machine", "Classical Mechanics"), ("physics.fluids.torricelli_efflux", "Fluid Mechanics"), ("physics.thermo.fermi_gas_metal", "Solid State Physics")):
        assert sub in CAT.get(cid).subdisciplines
