"""Core physics, part B: waves and acoustics, optics, electricity and magnetism (independent formulas)."""

import math

import pytest
from pcutil import CAT, R, c, check_case, e, eps0, g, h, kB, me, mu0, pi, solved

deg = pi / 180
k0 = 1 / (4 * pi * eps0)


def wave_parameters(x):
    return {"v": x["f"] * x["lam"], "k": 2 * pi / x["lam"], "w": 2 * pi * x["f"], "T": 1 / x["f"], "vym": x["A"] * 2 * pi * x["f"], "aym": x["A"] * (2 * pi * x["f"]) ** 2}


def string_wave(x):
    v = math.sqrt(x["Tt"] / x["mus"])
    w = 2 * pi * x["f"]
    return {"v": v, "lam": v / x["f"], "w": w, "Pav": x["mus"] * v * w**2 * x["A"] ** 2 / 2, "ul": x["mus"] * w**2 * x["A"] ** 2 / 2}


def sound_level(x):
    I = x["Pw"] / (4 * pi * x["rr"] ** 2)
    pm = math.sqrt(2 * x["rho"] * x["cs"] * I)
    return {"Is": I, "beta": 10 * math.log10(I / 1e-12), "pm": pm, "sm": pm / (x["rho"] * x["cs"] * 2 * pi * x["f"])}


def water_waves(x):
    k = 2 * pi / x["lam"]
    w = math.sqrt(g * k * math.tanh(k * x["d"]))
    cph = w / k
    kd = k * x["d"]
    return {"k": k, "w": w, "cph": cph, "cg": cph / 2 * (1 + 2 * kd / math.sinh(2 * kd)), "csh": math.sqrt(g * x["d"]), "cdp": math.sqrt(g * x["lam"] / (2 * pi))}


def impedance(x):
    Z1, Z2 = x["r1"] * x["c1"], x["r2"] * x["c2"]
    return {"Z1": Z1, "Z2": Z2, "Rp": (Z2 - Z1) / (Z2 + Z1), "Tp": 2 * Z2 / (Z1 + Z2), "RI": ((Z2 - Z1) / (Z2 + Z1)) ** 2, "TI": 4 * Z1 * Z2 / (Z1 + Z2) ** 2}


def sound_speeds(x):
    return {"vs": math.sqrt(x["Ey"] / x["rs"]), "vf": math.sqrt(x["Bf"] / x["rf"]), "vg": math.sqrt(x["gam"] * R * x["Tg"] / x["Mm"]), "va": 331.3 * math.sqrt(x["Tg"] / 273.15)}


def helmholtz(x):
    rn = math.sqrt(x["Ar"] / pi)
    Le = x["Ln"] + 1.7 * rn
    return {"rn": rn, "Le": Le, "fr": x["cs"] / (2 * pi) * math.sqrt(x["Ar"] / (x["Vc"] * Le))}


def room(x):
    V = x["Lx"] * x["Ly"] * x["Lz"]
    return {"fm": x["cs"] / 2 * math.sqrt((x["nx"] / x["Lx"]) ** 2 + (x["ny"] / x["Ly"]) ** 2 + (x["nz"] / x["Lz"]) ** 2), "f1x": x["cs"] / (2 * x["Lx"]), "Vr": V,
            "Nm": 4 * pi * V * x["fq"] ** 3 / (3 * x["cs"] ** 3)}


def mirror(x):
    f = x["Rm"] / 2
    di = 1 / (1 / f - 1 / x["do"])
    return {"f": f, "di": di, "M": -di / x["do"]}


def refraction(x):
    n1, n2 = x["n1"], x["n2"]
    di = n2 / ((n2 - n1) / x["Rs"] - n1 / x["do"])
    return {"di": di, "M": -n1 * di / (n2 * x["do"]), "dapp": x["do"] * n2 / n1}


def magnifiers(x):
    return {"Mr": x["Np"] / x["fm"], "Mn": x["Np"] / x["fm"] + 1, "Mmic": x["Ls"] / x["fo"] * x["Np"] / x["fe"], "Mtel": x["fT"] / x["fte"], "Lt": x["fT"] + x["fte"]}


def eye(x):
    Pm = -1 / x["dfar"]
    return {"Pm": Pm, "Ph": 1 / x["Np"] - 1 / x["dnear"], "Pc": Pm / (1 - x["dv"] * Pm)}


def thin_film(x):
    return {"tcon": (x["m"] + 0.5) * x["lam"] / (2 * x["nf"]), "tdes": (x["m"] + 1) * x["lam"] / (2 * x["nf"]), "nid": math.sqrt(x["ns"]), "tAR": x["lam"] / (4 * x["nc"])}


def polarisers(x):
    I1 = x["I0"] / 2
    I2 = I1 * math.cos(x["t12"]) ** 2
    return {"I1": I1, "I2": I2, "I3": I2 * math.cos(x["t23"]) ** 2}


def fresnel(x):
    n1, n2, t1 = x["n1"], x["n2"], x["th1"]
    t2 = math.asin(n1 * math.sin(t1) / n2)
    rs = (n1 * math.cos(t1) - n2 * math.cos(t2)) / (n1 * math.cos(t1) + n2 * math.cos(t2))
    rp = (n2 * math.cos(t1) - n1 * math.cos(t2)) / (n2 * math.cos(t1) + n1 * math.cos(t2))
    Ru = (rs**2 + rp**2) / 2
    return {"th2": t2, "rs": rs, "rp": rp, "Rs": rs**2, "Rp": rp**2, "Ru": Ru, "Tu": 1 - Ru}


def michelson(x):
    return {"Nf": 2 * x["dm"] / x["lam"], "dN": x["Nc"] * x["lam"] / 2, "ng": x["Ng"] * x["lam"] / (2 * x["Lc"])}


def bragg(x):
    d = x["a"] / math.sqrt(x["hh"] ** 2 + x["kk"] ** 2 + x["ll"] ** 2)
    th = math.asin(x["nb"] * x["lam"] / (2 * d))
    return {"dh": d, "thB": th, "tt": 2 * th}


def gaussian(x):
    zR = pi * x["w0"] ** 2 / x["lam"]
    return {"zR": zR, "wz": x["w0"] * math.sqrt(1 + (x["z"] / zR) ** 2), "th": x["lam"] / (pi * x["w0"]), "Rz": x["z"] * (1 + (zR / x["z"]) ** 2)}


def prism(x):
    A = x["Ap"]
    return {"dmin": 2 * math.asin(x["n"] * math.sin(A / 2)) - A, "nm": math.sin((A + x["dmeas"]) / 2) / math.sin(A / 2), "Vd": (x["nd"] - 1) / (x["nF"] - x["nC"])}


def camera(x):
    H = x["fl"] ** 2 / (x["Nf"] * x["cc"]) + x["fl"]
    near = H * x["s"] / (H + (x["s"] - x["fl"]))
    far = H * x["s"] / (H - (x["s"] - x["fl"]))
    return {"Dap": x["fl"] / x["Nf"], "H": H, "Dn": near, "Df": far, "dof": far - near}


def photometry(x):
    Phi = 4 * pi * x["Iv"]
    return {"Ev": x["Iv"] * math.cos(x["th"]) / x["r"] ** 2, "Phi": Phi, "eff": Phi / x["Pe"]}


def capacitor(x):
    C = x["kd"] * eps0 * x["Ap"] / x["d"]
    return {"Cc": C, "Q": C * x["Vb"], "U": C * x["Vb"] ** 2 / 2, "Ed": x["Vb"] / x["d"], "Cs": C * x["C2"] / (C + x["C2"]), "Cp": C + x["C2"]}


def resistivity(x):
    R0 = x["rho0"] * x["Lw"] / x["Aw"]
    rhoT = x["rho0"] * (1 + x["al"] * (x["T"] - x["T0"]))
    RT = rhoT * x["Lw"] / x["Aw"]
    return {"R0": R0, "rhoT": rhoT, "RT": RT, "Pd": x["Ic"] ** 2 * RT}


def rl(x):
    tau = x["Li"] / x["Rr"]
    I = x["Vb"] / x["Rr"]
    it = I * (1 - math.exp(-x["t"] / tau))
    return {"tau": tau, "Iinf": I, "it": it, "tx": -tau * math.log(1 - x["fx"]), "vL": x["Vb"] * math.exp(-x["t"] / tau), "UL": x["Li"] * it**2 / 2}


def lc(x):
    w0 = 1 / math.sqrt(x["Li"] * x["Cc"])
    al = x["Rr"] / (2 * x["Li"])
    return {"w0": w0, "f0": w0 / (2 * pi), "Qf": math.sqrt(x["Li"] / x["Cc"]) / x["Rr"], "al": al, "wd": math.sqrt(w0**2 - al**2), "E0": x["Cc"] * x["V0"] ** 2 / 2, "Im": x["V0"] * math.sqrt(x["Cc"] / x["Li"])}


def solenoid(x):
    Ls = mu0 * x["Nt"] ** 2 * x["As"] / x["ls"]
    return {"Bs": mu0 * x["Nt"] * x["Ic"] / x["ls"], "Ls": Ls, "Us": Ls * x["Ic"] ** 2 / 2, "Bt": mu0 * x["Ntt"] * x["Ic"] / (2 * pi * x["Rt"]), "Lt": mu0 * x["Ntt"] ** 2 * x["As"] / (2 * pi * x["Rt"])}


def coax(x):
    lg = math.log(x["bo"] / x["ai"])
    Cl, Ll = 2 * pi * eps0 * x["er"] / lg, mu0 / (2 * pi) * lg
    return {"Cl": Cl, "Ll": Ll, "Z0": math.sqrt(Ll / Cl), "vp": 1 / math.sqrt(Ll * Cl)}


def hall(x):
    return {"VH": x["Ic"] * x["Bf"] / (x["nc"] * e * x["tp"]), "RH": 1 / (x["nc"] * e)}


def magforce(x):
    mom = x["Nt"] * x["Ic"] * x["Al"]
    return {"Fw": x["Ic"] * x["Lw"] * x["Bf"] * math.sin(x["thw"]), "mom": mom, "tau": mom * x["Bf"] * math.sin(x["thl"]), "Um": -mom * x["Bf"] * math.cos(x["thl"])}


def dipole(x):
    p = x["qd"] * x["ds"]
    return {"pd": p, "Eax": 2 * k0 * p / x["r"] ** 3, "Eeq": k0 * p / x["r"] ** 3, "tau": p * x["E0"] * math.sin(x["thd"]), "Ud": -p * x["E0"] * math.cos(x["thd"])}


def emwave(x):
    E0 = x["E0"]
    I = c * eps0 * E0**2 / 2
    return {"B0": E0 / c, "Is": I, "Smax": E0 * (E0 / c) / mu0, "uE": eps0 * E0**2 / 2, "lam": c / x["fr"], "pa": I / c, "pr": 2 * I / c, "Fr": 2 * I / c * x["Ar"]}


def plasma(x):
    lD = math.sqrt(eps0 * x["Te"] / (x["ne"] * e**2))
    vth = math.sqrt(2 * x["Te"] / me)
    return {"lD": lD, "ND": 4 * pi / 3 * x["ne"] * lD**3, "vth": vth, "rL": me * vth / (e * x["Bf"]), "fce": e * x["Bf"] / (2 * pi * me)}


def displacement(x):
    A = pi * x["Rp"] ** 2
    Id = eps0 * A * x["dVdt"] / x["d"]
    return {"Ap": A, "Id": Id, "Bin": mu0 * Id * x["ri"] / (2 * pi * x["Rp"] ** 2), "Bout": mu0 * Id / (2 * pi * x["ro"])}


def drude(x):
    sg = x["nc"] * e**2 * x["tau"] / me
    return {"Jd": x["Ic"] / x["Aw"], "vd": x["Ic"] / (x["nc"] * e * x["Aw"]), "sg": sg, "mob": e * x["tau"] / me, "rho": 1 / sg}


def ring_disk(x):
    Qr, Rr, z = x["Qr"], x["Rr"], x["z"]
    return {"Vr": k0 * Qr / math.sqrt(Rr**2 + z**2), "Er": k0 * Qr * z / (Rr**2 + z**2) ** 1.5, "Vd": x["sg"] / (2 * eps0) * (math.sqrt(z**2 + x["Rd"] ** 2) - z),
            "Ed": x["sg"] / (2 * eps0) * (1 - z / math.sqrt(z**2 + x["Rd"] ** 2))}


def cap_geometries(x):
    a, b = x["a"], x["b"]
    return {"Ciso": 4 * pi * eps0 * a, "Csp": 4 * pi * x["kd"] * eps0 * a * b / (b - a), "Ccy": 2 * pi * x["kd"] * eps0 * x["Lc"] / math.log(b / a)}


def larmor(x):
    return {"Pl": x["q"] ** 2 * x["acc"] ** 2 / (6 * pi * eps0 * c**3), "t0": x["q"] ** 2 / (6 * pi * eps0 * x["m"] * c**3)}


def magmat(x):
    B = mu0 * (1 + x["chi"]) * x["Hf"]
    return {"Mg": x["chi"] * x["Hf"], "mr": 1 + x["chi"], "Bf": B, "ub": B * x["Hf"] / 2}


def estat(x):
    return {"Ush": x["Q"] ** 2 / (8 * pi * eps0 * x["Rs"]), "Uso": 3 * x["Q"] ** 2 / (20 * pi * eps0 * x["Rs"]), "uE": eps0 * x["E0"] ** 2 / 2}


CASES = {
    "physics.waves.wave_parameters": wave_parameters, "physics.waves.string_wave_power": string_wave, "physics.waves.sound_intensity_level": sound_level,
    "physics.waves.water_wave_dispersion": water_waves, "physics.waves.acoustic_impedance_reflection": impedance, "physics.waves.speed_of_sound_media": sound_speeds,
    "physics.waves.helmholtz_resonator": helmholtz, "physics.waves.room_modes": room, "physics.optics.spherical_mirror": mirror, "physics.optics.refraction_spherical_surface": refraction,
    "physics.optics.magnifying_instruments": magnifiers, "physics.optics.eye_vision_correction": eye, "physics.optics.thin_film_coating": thin_film, "physics.optics.polarisers_malus": polarisers,
    "physics.optics.fresnel_polarised_reflectance": fresnel, "physics.optics.michelson_interferometer": michelson, "physics.optics.bragg_diffraction": bragg, "physics.optics.gaussian_beam": gaussian,
    "physics.optics.prism_dispersion": prism, "physics.optics.camera_depth_of_field": camera, "physics.optics.photometry": photometry, "physics.em.capacitor_dielectric": capacitor,
    "physics.em.resistivity_temperature": resistivity, "physics.em.rl_circuit": rl, "physics.em.lc_rlc_oscillator": lc, "physics.em.solenoid_toroid": solenoid, "physics.em.coaxial_line": coax,
    "physics.em.hall_effect": hall, "physics.em.magnetic_force_torque": magforce, "physics.em.electric_dipole": dipole, "physics.em.em_wave_intensity_pressure": emwave,
    "physics.em.plasma_parameters": plasma, "physics.em.displacement_current": displacement, "physics.em.drift_velocity_drude": drude, "physics.em.charged_ring_disk_fields": ring_disk,
    "physics.em.capacitance_geometries": cap_geometries, "physics.em.larmor_radiation": larmor, "physics.em.magnetic_materials": magmat, "physics.em.electrostatic_energy": estat,
}


@pytest.mark.parametrize("cid", list(CASES))
def test_against_the_textbook_formula(cid):
    check_case(cid, CASES[cid])


# ---------------------------------------------------------------- physical identities and limiting cases
def test_wave_speed_of_concert_a():
    assert solved("physics.waves.wave_parameters")["v"] == pytest.approx(343.2)


def test_sound_level_drops_six_decibels_per_doubling_of_distance():
    assert solved("physics.waves.sound_intensity_level", rr="10 m")["beta"] == pytest.approx(solved("physics.waves.sound_intensity_level")["beta"] - 20 * math.log10(2), abs=1e-9)


def test_water_wave_limits_and_group_speed():
    shallow = solved("physics.waves.water_wave_dispersion", d="0.05 m", lam="1000 m")
    assert shallow["cph"] == pytest.approx(shallow["csh"], rel=1e-3) and shallow["cg"] == pytest.approx(shallow["cph"], rel=1e-3)
    deep = solved("physics.waves.water_wave_dispersion", d="4000 m", lam="50 m")
    assert deep["cph"] == pytest.approx(deep["cdp"], rel=1e-6) and deep["cg"] == pytest.approx(deep["cph"] / 2, rel=1e-6)


def test_air_water_interface_reflects_almost_everything_and_a_matched_one_nothing():
    out = solved("physics.waves.acoustic_impedance_reflection")
    assert out["RI"] + out["TI"] == pytest.approx(1) and out["RI"] > 0.998
    matched = solved("physics.waves.acoustic_impedance_reflection", r2="1.204 kg/m^3", c2="343 m/s")
    assert matched["Rp"] == pytest.approx(0, abs=1e-12) and matched["TI"] == pytest.approx(1)


def test_speed_of_sound_in_air_two_ways_agree():
    out = solved("physics.waves.speed_of_sound_media")
    assert out["vg"] == pytest.approx(out["va"], rel=2e-3) and out["vg"] == pytest.approx(343.2, abs=0.2)


def test_larger_cavity_lowers_the_helmholtz_frequency():
    assert solved("physics.waves.helmholtz_resonator", Vc="2 L")["fr"] < solved("physics.waves.helmholtz_resonator")["fr"]


def test_room_axial_mode_and_mode_count():
    assert solved("physics.waves.room_modes", nx="1", ny="0", nz="0")["fm"] == pytest.approx(solved("physics.waves.room_modes")["f1x"])
    assert solved("physics.waves.room_modes", fq="400 Hz")["Nm"] == pytest.approx(8 * solved("physics.waves.room_modes")["Nm"])


def test_concave_mirror_and_object_at_twice_the_focal_length():
    out = solved("physics.optics.spherical_mirror", do="40 cm")
    assert out["di"] == pytest.approx(0.40) and out["M"] == pytest.approx(-1)


def test_flat_surface_gives_a_virtual_image_at_the_apparent_depth():
    out = solved("physics.optics.refraction_spherical_surface", Rs="1e9 cm", n1="1.33", n2="1")
    assert -out["di"] == pytest.approx(out["dapp"], rel=1e-6)


def test_magnifier_near_point_is_one_more_than_relaxed():
    out = solved("physics.optics.magnifying_instruments")
    assert out["Mn"] == pytest.approx(out["Mr"] + 1)


def test_ar_coating_is_a_quarter_wave_and_the_ideal_index_is_the_geometric_mean():
    out = solved("physics.optics.thin_film_coating")
    assert out["tAR"] * 4 * 1.38 == pytest.approx(550e-9) and out["nid"] == pytest.approx(math.sqrt(1.52))


def test_crossed_polarisers_block_light():
    assert solved("physics.optics.polarisers_malus", t12="90 deg")["I3"] == pytest.approx(0, abs=1e-12)


def test_fresnel_brewster_angle_and_normal_incidence():
    brew = solved("physics.optics.fresnel_polarised_reflectance", th1=f"{math.degrees(math.atan(1.5))} deg")
    assert brew["Rp"] == pytest.approx(0, abs=1e-12) and brew["Rs"] > 0.1
    normal = solved("physics.optics.fresnel_polarised_reflectance", th1="0 deg")
    assert normal["Rs"] == pytest.approx(0.04) == pytest.approx(normal["Rp"])


def test_one_fringe_is_half_a_wavelength():
    assert solved("physics.optics.michelson_interferometer", Nc="1")["dN"] == pytest.approx(632.8e-9 / 2)


def test_aluminium_111_reflection_is_at_38_5_degrees():
    assert solved("physics.optics.bragg_diffraction")["tt"] / deg == pytest.approx(38.47, abs=0.02)


def test_gaussian_beam_is_root_two_wider_at_the_rayleigh_range():
    zR = pi * 0.4e-3**2 / 632.8e-9
    assert solved("physics.optics.gaussian_beam", z=f"{zR} m")["wz"] == pytest.approx(0.4e-3 * math.sqrt(2))


def test_prism_index_round_trip():
    n = 1.5168
    dmin = solved("physics.optics.prism_dispersion")["dmin"] / deg
    assert solved("physics.optics.prism_dispersion", dmeas=f"{dmin} deg")["nm"] == pytest.approx(n)
    assert solved("physics.optics.prism_dispersion")["Vd"] == pytest.approx(63.8, abs=0.05)


def test_smaller_aperture_gives_more_depth_of_field():
    assert solved("physics.optics.camera_depth_of_field", Nf="16")["dof"] > solved("physics.optics.camera_depth_of_field")["dof"]


def test_illuminance_follows_the_inverse_square_law():
    assert solved("physics.optics.photometry", r="4 m")["Ev"] == pytest.approx(solved("physics.optics.photometry")["Ev"] / 4)


def test_dielectric_multiplies_capacitance_and_combinations_obey_their_rules():
    out, plain = solved("physics.em.capacitor_dielectric"), solved("physics.em.capacitor_dielectric", kd="1")
    assert out["Cc"] == pytest.approx(3.9 * plain["Cc"]) and out["Cs"] < min(out["Cc"], 50e-12) and out["Cp"] == pytest.approx(out["Cc"] + 50e-12)


def test_wire_resistance_is_constant_without_a_temperature_coefficient():
    assert solved("physics.em.resistivity_temperature", al="0 1/K")["RT"] == pytest.approx(solved("physics.em.resistivity_temperature")["R0"])


def test_rl_circuit_reaches_63_percent_in_one_time_constant():
    out = solved("physics.em.rl_circuit", t="25 ms")
    assert out["it"] == pytest.approx(out["Iinf"] * (1 - math.exp(-1)))
    assert solved("physics.em.rl_circuit", fx=f"{100 * (1 - math.exp(-1))} %")["tx"] == pytest.approx(0.025, rel=1e-9)


def test_lc_energy_exchange_and_lossless_limit():
    out = solved("physics.em.lc_rlc_oscillator")
    assert 0.5 * 10e-3 * out["Im"] ** 2 == pytest.approx(out["E0"])
    assert solved("physics.em.lc_rlc_oscillator", Rr="1e-9 ohm")["wd"] == pytest.approx(out["w0"], rel=1e-9)


def test_solenoid_energy_equals_field_energy_in_its_volume():
    out = solved("physics.em.solenoid_toroid")
    assert out["Us"] == pytest.approx(out["Bs"] ** 2 / (2 * mu0) * 4e-4 * 0.2)


def test_coax_matches_the_60_ohm_rule_and_signal_speed():
    out = solved("physics.em.coaxial_line")
    assert out["Z0"] == pytest.approx(59.96 / math.sqrt(2.25) * math.log(1.47 / 0.45), rel=1e-3) and out["vp"] == pytest.approx(c / 1.5, rel=1e-9)


def test_hall_voltage_scales_inversely_with_carrier_density():
    assert solved("physics.em.hall_effect", nc="1.698e29 1/m^3")["VH"] == pytest.approx(solved("physics.em.hall_effect")["VH"] / 2)


def test_force_vanishes_parallel_to_the_field_and_torque_peaks_perpendicular():
    assert solved("physics.em.magnetic_force_torque", thw="0 deg")["Fw"] == pytest.approx(0, abs=1e-12)
    assert solved("physics.em.magnetic_force_torque", thl="90 deg")["tau"] > solved("physics.em.magnetic_force_torque")["tau"]
    assert solved("physics.em.magnetic_force_torque", thl="0 deg")["Um"] < 0


def test_dipole_axis_field_is_twice_the_equatorial_field():
    out = solved("physics.em.electric_dipole")
    assert out["Eax"] == pytest.approx(2 * out["Eeq"])


def test_em_wave_relations():
    out = solved("physics.em.em_wave_intensity_pressure")
    assert out["Is"] == pytest.approx(c * out["uE"]) and out["Smax"] == pytest.approx(2 * out["Is"]) and out["pr"] == pytest.approx(2 * out["pa"])
    assert solved("physics.em.em_wave_intensity_pressure", E0="1013 V/m")["Is"] == pytest.approx(1361, rel=2e-3)     # the solar constant


def test_plasma_gyroradius_and_cyclotron_frequency():
    out = solved("physics.em.plasma_parameters")
    assert solved("physics.em.plasma_parameters", Bf="4 T")["fce"] == pytest.approx(2 * out["fce"]) and out["lD"] < 1e-3


def test_displacement_current_equals_c_dv_dt_and_the_field_is_continuous():
    out = solved("physics.em.displacement_current", ri="5 cm", ro="5 cm")
    assert out["Id"] == pytest.approx(eps0 * pi * 0.05**2 / 2e-3 * 1e9) and out["Bin"] == pytest.approx(out["Bout"])


def test_drude_conductivity_of_copper_and_ohms_law_link():
    out = solved("physics.em.drift_velocity_drude")
    assert out["sg"] * out["rho"] == pytest.approx(1) and out["sg"] / 1e6 == pytest.approx(59.6, rel=0.01) and out["sg"] == pytest.approx(8.49e28 * e * out["mob"])


def test_ring_and_disk_limits():
    far = solved("physics.em.charged_ring_disk_fields", z="100 m")
    assert far["Er"] == pytest.approx(k0 * 10e-9 / 100**2, rel=1e-6) and far["Vr"] == pytest.approx(k0 * 10e-9 / 100, rel=1e-6)
    huge = solved("physics.em.charged_ring_disk_fields", Rd="1000 m")
    assert huge["Ed"] == pytest.approx(2e-6 / (2 * eps0), rel=1e-3)           # infinite sheet
    assert solved("physics.em.charged_ring_disk_fields", z="0 cm")["Er"] == pytest.approx(0, abs=1e-9)


def test_capacitor_geometry_limits():
    assert solved("physics.em.capacitance_geometries", b="1e9 cm")["Csp"] == pytest.approx(solved("physics.em.capacitance_geometries")["Ciso"], rel=1e-6)
    assert solved("physics.em.capacitance_geometries", a="1 cm", b=f"{math.e} cm", kd="2")["Ccy"] == pytest.approx(2 * pi * 2 * eps0 * 1)


def test_larmor_power_scales_with_acceleration_squared_and_the_classical_electron_time():
    base = solved("physics.em.larmor_radiation")
    assert solved("physics.em.larmor_radiation", acc="2e20 m/s^2")["Pl"] == pytest.approx(4 * base["Pl"]) and base["t0"] == pytest.approx(6.26e-24, rel=1e-3)


def test_b_equals_mu0_h_plus_m():
    out = solved("physics.em.magnetic_materials")
    assert out["Bf"] == pytest.approx(mu0 * (100 + out["Mg"]))


def test_uniform_sphere_stores_six_fifths_of_the_shell_energy():
    out = solved("physics.em.electrostatic_energy")
    assert out["Uso"] == pytest.approx(1.2 * out["Ush"])


def test_batch_b_sub_disciplines():
    for cid, sub in (("physics.waves.room_modes", "Waves and Acoustics"), ("physics.optics.bragg_diffraction", "Solid State Physics"), ("physics.em.hall_effect", "Solid State Physics")):
        assert sub in CAT.get(cid).subdisciplines
    assert kB > 0 and h > 0
