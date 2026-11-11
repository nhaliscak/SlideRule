"""Thin sub-disciplines, part A: additive, agricultural, reinforcement learning, biomedical, chemical process, civil, climate (independent formulas, SI)."""

import math

import pytest
from pcutil import CAT, check_case, e, g, pi, solved

F = 96485.33212
atm_bar = 1.01325e5


def shape_memory(x):
    return {"Rf": x["eu"] / x["em"], "Rr": (x["eu"] - x["ep"]) / x["eu"], "sr": x["E"] * (x["eu"] - x["ep"])}


def hydrogel(x):
    Qv = 1 + (x["Qm"] - 1) * x["rp"] / x["rs"]
    return {"Qv": Qv, "lam": Qv ** (1 / 3), "L1": Qv ** (1 / 3) * x["L0"], "phi": 1 / Qv}


def rosenthal(x):
    return {"w": math.sqrt(8 * x["eta"] * x["P"] / (pi * math.e * x["rho"] * x["cp"] * x["v"] * x["dT"]))}


def build_rate(x):
    Rb = x["nl"] * x["v"] * x["hh"] * x["tl"]
    N = x["H"] / x["tl"]
    te = x["Vp"] / Rb
    return {"Rb": Rb, "te": te, "N": N, "tt": te + N * x["trc"]}


def greenhouse(x):
    Qc = x["U"] * x["Ac"] * x["dT"]
    Qa = 1.2 * 1005 * x["Qv"] * x["dT"]
    return {"Qc": Qc, "Qa": Qa, "Qh": x["sf"] * (Qc + Qa), "ach": x["Qv"] / x["Vg"]}


def grain(x):
    mdm = x["m1"] * (1 - x["M1"])
    m2 = mdm / (1 - x["M2"])
    return {"mdm": mdm, "m2": m2, "mw": x["m1"] - m2, "En": (x["m1"] - m2) * x["ed"]}


def compost(x):
    dm = [x[f"m{i}"] * (1 - x[f"w{i}"]) for i in (1, 2, 3)]
    return {"CN": sum(d * x[f"c{i}"] for d, i in zip(dm, (1, 2, 3))) / sum(d * x[f"n{i}"] for d, i in zip(dm, (1, 2, 3))),
            "wb": sum(x[f"m{i}"] * x[f"w{i}"] for i in (1, 2, 3)) / sum(x[f"m{i}"] for i in (1, 2, 3))}


def ethanol(x):
    mE = x["eta"] * 0.511 * x["ms"]
    return {"mE": mE, "VE": mE / 789, "mc": x["eta"] * 0.489 * x["ms"]}


def sprayer(x):
    AR = x["Q"] / (x["v"] * x["wb"])
    return {"AR": AR, "Ch": x["v"] * x["wb"], "At": x["Vt"] / AR, "qn": x["Q"] / x["nn"]}


def traction(x):
    return {"sl": 1 - x["va"] / x["vt"], "Pd": x["Fd"] * x["va"], "et": x["Fd"] * x["va"] / x["Pa"]}


def ucb(x):
    rad = x["cu"] * math.sqrt(math.log(x["tt"]) / x["na"])
    return {"rad": rad, "ucb": x["Qa"] + rad}


def td(x):
    d1 = x["r1"] + x["gm"] * x["Vn"] - x["Vs"]
    d2 = x["r2"] + x["gm"] * x["Vn2"] - x["Vn"]
    return {"d1": d1, "Vnew": x["Vs"] + x["al"] * d1, "d2": d2, "Ahat": d1 + x["gm"] * x["la"] * d2, "H": 1 / (1 - x["gm"])}


def filament(x):
    df = math.sqrt(4 * x["Q"] / (pi * x["v"]))
    return {"df": df, "sw": df / x["dn"], "tp": x["Lp"] / x["v"]}


def cell_dose(x):
    Ni = x["cd"] * x["Vc"]
    return {"Ni": Ni, "Nv": Ni * x["vb"], "Vb": x["Vc"] / x["pf"], "cdv": Ni * x["vb"] / x["Vc"]}


def defib(x):
    Es = x["Cd"] * x["Vd"] ** 2 / 2
    return {"Es": Es, "Ed": x["ef"] * Es, "tau": x["Rp"] * x["Cd"], "I0": x["Vd"] / x["Rp"]}


def cylinder(x):
    Vg = (x["Pc"] - x["Pr"]) * x["Vw"] / 1.01325e5
    return {"Vg": Vg, "td": Vg / x["Fq"]}


def stern_geary(x):
    B = x["ba"] * x["bc"] / (math.log(10) * (x["ba"] + x["bc"]))
    ic = B / x["Rp"]
    return {"B": B, "ic": ic, "CR": ic * x["M"] / (x["nz"] * F * x["rho"])}


def anode(x):
    I = x["As"] * x["id"] * x["fc"]
    return {"I": I, "Lf": x["ma"] * x["cap"] * x["ut"] / I, "mreq": I * x["Ld"] / (x["cap"] * x["ut"])}


def stock(x):
    S1, S2 = x["md"] / x["C1"], x["md"] / x["C2"]
    return {"S1": S1, "S2": S2, "ww": S2 - S1, "dr": (S2 - S1) / S1}


def paper(x):
    Pr = x["vm"] * x["wt"] * x["bw"]
    return {"Pr": Pr, "Pd": x["ef"] * Pr}                                   # 24 h/day is dimensionless in SI


def yarn(x):
    dy = math.sqrt(4 * x["tex"] / (pi * x["rf"] * x["ph"]))
    hr = math.sqrt(1 + (pi * dy * x["Tt"]) ** 2)
    return {"dy": dy, "th": math.atan(pi * dy * x["Tt"]), "hr": hr, "tc": 1 - 1 / hr}


def cover(x):
    Kw, Kf = x["dw"] * x["ep"], x["df"] * x["pp"]
    K = Kw + Kf - Kw * Kf
    return {"Kw": Kw, "Kf": Kf, "K": K, "op": 1 - K}


def snumber(x):
    SN = x["a1"] * x["D1"] + x["a2"] * x["D2"] * x["m2"] + x["a3"] * x["D3"] * x["m3"]
    return {"SN": SN, "ok": 1 if SN >= x["SNr"] else 0}


def asphalt(x):
    Va = 1 - x["Gmb"] / x["Gmm"]
    VMA = 1 - x["Gmb"] * (1 - x["Pb"]) / x["Gsb"]
    return {"Va": Va, "VMA": VMA, "VFA": (VMA - Va) / VMA}


def windprofile(x):
    us = 0.4 * x["vr"] / math.log(x["zr"] / x["z0"])
    return {"vp": x["vr"] * (x["z"] / x["zr"]) ** x["al"], "us": us, "vl": us / 0.4 * math.log(x["z"] / x["z0"]), "Iz": 1 / math.log(x["z"] / x["z0"])}


def windforce(x):
    q = x["rho"] * x["v"] ** 2 / 2
    F_ = q * x["G"] * x["Cf"] * x["A"]
    Mo = F_ * x["he"]
    return {"q": q, "F": F_, "Mo": Mo, "fs": x["Wd"] * x["bs"] / 2 / Mo}


def capture(x):
    mc = x["eta"] * x["y"] * x["Qn"] / 22.414e-3 * 44.01e-3
    return {"mc": mc, "Ma": mc * x["hy"], "Pr": mc * x["qr"]}


def cost_avoided(x):
    return {"ca": (x["c1"] - x["c0"]) / (x["e0"] - x["e1"]), "cc": (x["c1"] - x["c0"]) / x["ec"]}


def aerosol(x):
    dF = -25 * x["tau"]
    Ms = x["tau"] * 4 * pi * 6.371e6**2 / 8000          # 8 m^2/g is 8000 m^2/kg
    return {"dF": dF, "dTs": x["lam"] * dF, "Ms": Ms, "Ry": Ms / x["tl"]}


def shade(x):
    f = 4 * x["dFt"] / (1361 * (1 - x["al"]))
    return {"fb": f, "As": f * pi * 6.371e6**2}


CASES = {
    "additive.4d_printing.shape_memory_cycle": shape_memory, "additive.4d_printing.hydrogel_swelling": hydrogel, "additive.metal.rosenthal_melt_pool": rosenthal, "additive.metal.build_rate_time": build_rate,
    "agricultural.structures.greenhouse_heat_balance": greenhouse, "agricultural.structures.grain_drying_water": grain, "agricultural.bioengineering.compost_cn_ratio": compost,
    "agricultural.bioengineering.ethanol_fermentation_yield": ethanol, "agricultural.machinery.sprayer_calibration": sprayer, "agricultural.machinery.traction_slip_efficiency": traction,
    "computer.ai.rl_ucb_exploration": ucb, "computer.ai.rl_td_error_update": td, "biomedical.bioprinting.filament_resolution": filament, "biomedical.bioprinting.cell_dose_construct": cell_dose,
    "biomedical.clinical.defibrillator_discharge": defib, "biomedical.clinical.gas_cylinder_duration": cylinder, "chemical.corrosion.stern_geary": stern_geary,
    "chemical.corrosion.sacrificial_anode_life": anode, "chemical.pulp_paper.stock_consistency_dilution": stock, "chemical.pulp_paper.machine_production_rate": paper,
    "chemical.textile.yarn_geometry_twist": yarn, "chemical.textile.fabric_cover_factor": cover, "civil.pavement.structural_number": snumber, "civil.pavement.asphalt_mix_volumetrics": asphalt,
    "civil.wind.mean_wind_profile": windprofile, "civil.wind.wind_force_overturning": windforce, "climate.ccs.capture_plant_rate": capture, "climate.ccs.cost_of_co2_avoided": cost_avoided,
    "climate.geoengineering.stratospheric_aerosol_injection": aerosol, "climate.geoengineering.space_sunshade_area": shade,
}


@pytest.mark.parametrize("cid", sorted(CASES))
def test_worked_example_matches_independent_formula(cid):
    check_case(cid, CASES[cid], rel=1e-5)


def test_benchmarks_and_identities():
    assert solved("additive.metal.rosenthal_melt_pool")["w"] * 1e6 == pytest.approx(116, abs=1)
    assert solved("chemical.corrosion.stern_geary")["CR"] * 1e3 * 3.156e7 == pytest.approx(0.0151, rel=0.01)           # mm/yr for 1.3 uA/cm^2 of iron
    assert solved("civil.pavement.asphalt_mix_volumetrics")["Va"] == pytest.approx(0.0402, abs=1e-4)
    assert solved("climate.geoengineering.space_sunshade_area")["fb"] == pytest.approx(0.0155, abs=2e-4)
    assert solved("climate.ccs.capture_plant_rate")["Ma"] * 3.156e7 / 1e9 == pytest.approx(3.44, abs=0.05)
    assert solved("agricultural.bioengineering.ethanol_fermentation_yield", eta="100 %")["mE"] == pytest.approx(0.511 * 100e3)      # theoretical yield, kg
    assert solved("agricultural.structures.grain_drying_water", M2="22 %")["mw"] == pytest.approx(0, abs=1e-9)
    assert solved("civil.pavement.structural_number", SNr="5")["ok"] == 0 and solved("civil.pavement.structural_number")["ok"] == 1
    assert solved("computer.ai.rl_td_error_update", gm="0.9")["H"] == pytest.approx(10)
    assert e > 0 and g > 0


def test_cover_factor_warning_when_threads_overlap():
    assert solved("chemical.textile.fabric_cover_factor", ep="80 1/cm", warnings_ok=True)["Kw"] > 1
    assert "Textile Engineering" in CAT.get("chemical.textile.fabric_cover_factor").subdisciplines


def test_catalogued_under_the_thin_sub_disciplines():
    for cid in CASES:
        assert CAT.get(cid).subdisciplines and CAT.get(cid).references
