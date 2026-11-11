"""Regenerate the ``fluids-coolprop`` datapack with CoolProp (``pip install CoolProp``; ``python scripts/build_coolprop_pack.py``).

CoolProp (MIT licence, https://coolprop.org) evaluates published equations of state and transport correlations. The pack stores the
*computed values* on a temperature grid at 101.325 kPa, one record per fluid and phase (liquid up to the boiling point, gas above it
to 1000 K or the model limit), so nothing needs CoolProp at run time. Each fluid's source lists the literature keys CoolProp reports
for its equation of state, viscosity and conductivity models.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "src" / "sliderule" / "datapacks" / "fluids-coolprop"
P_ATM = 101325.0
T_TOP = 1000.0
POINTS = 41

#: CoolProp name -> (display name, category)
FLUIDS = {
    "Water": ("Water", "water"), "Air": ("Air", "air"), "Nitrogen": ("Nitrogen", "gas"), "Oxygen": ("Oxygen", "gas"),
    "Argon": ("Argon", "gas"), "Helium": ("Helium", "gas"), "Hydrogen": ("Hydrogen", "gas"), "CarbonDioxide": ("Carbon dioxide", "gas"),
    "CarbonMonoxide": ("Carbon monoxide", "gas"), "Methane": ("Methane", "hydrocarbon"), "Ethane": ("Ethane", "hydrocarbon"),
    "Propane": ("Propane", "hydrocarbon"), "n-Butane": ("n-Butane", "hydrocarbon"), "IsoButane": ("Isobutane", "hydrocarbon"),
    "n-Pentane": ("n-Pentane", "hydrocarbon"), "n-Hexane": ("n-Hexane", "hydrocarbon"), "n-Heptane": ("n-Heptane", "hydrocarbon"),
    "Ethylene": ("Ethylene", "hydrocarbon"), "Benzene": ("Benzene", "solvent"), "Toluene": ("Toluene", "solvent"),
    "Methanol": ("Methanol", "solvent"), "Ethanol": ("Ethanol", "solvent"), "Acetone": ("Acetone", "solvent"),
    "Ammonia": ("Ammonia", "refrigerant"), "R134a": ("R-134a", "refrigerant"), "R32": ("R-32", "refrigerant"),
    "R125": ("R-125", "refrigerant"), "R152A": ("R-152a", "refrigerant"), "R1234yf": ("R-1234yf", "refrigerant"),
    "R1234ze(E)": ("R-1234ze(E)", "refrigerant"), "SulfurDioxide": ("Sulfur dioxide", "gas"), "NitrousOxide": ("Nitrous oxide", "gas"),
}

#: property -> (CoolProp output key, unit, extra inputs)
PROPS = {"density": ("D", "kg/m^3"), "dynamic_viscosity": ("V", "Pa*s"), "thermal_conductivity": ("L", "W/(m*K)"), "specific_heat": ("C", "J/(kg*K)")}

#: published model uncertainty is fluid-specific; these are the generic CoolProp-documented orders of magnitude, kept conservative
REL_UNC = {"density": 0.005, "dynamic_viscosity": 0.05, "thermal_conductivity": 0.05, "specific_heat": 0.02, "vapour_pressure": 0.005}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _grid(lo: float, hi: float) -> list[float]:
    return [lo + (hi - lo) * i / (POINTS - 1) for i in range(POINTS)]


def _series(CP, fluid: str, key: str, grid: list[float], phase: str, Tb: float | None) -> tuple[list[float], list[float]]:
    """Temperatures and values where CoolProp answers and reports the intended phase; at the boiling temperature itself, the saturated liquid or vapour."""
    xs, ys = [], []
    for T in grid:
        try:
            if Tb is not None and abs(T - Tb) < 1e-9:
                v = CP.PropsSI(key, "T", T, "Q", 0 if phase == "liquid" else 1, fluid)
            elif CP.PhaseSI("T", T, "P", P_ATM, fluid) in (phase, "supercritical_gas" if phase == "gas" else phase):
                v = CP.PropsSI(key, "T", T, "P", P_ATM, fluid)
            else:
                continue
        except (ValueError, RuntimeError):
            continue
        if v == v and v > 0:
            xs.append(T)
            ys.append(v)
    return xs, ys


def _round(v: float) -> float:
    return float(f"{v:.7g}")


def _describe(CP, fluid: str) -> str:
    keys = {}
    for what in ("EOS", "VISCOSITY", "CONDUCTIVITY"):
        try:
            k = CP.get_BibTeXKey(fluid, what)
            if k and k.lower() not in ("n/a", "none"):
                keys[what] = k
        except (ValueError, RuntimeError):
            pass
    parts = ", ".join(f"{w.lower()}: {k}" for w, k in keys.items())
    return f"Bell et al., Ind. Eng. Chem. Res. 53, 2498 (2014), CoolProp {CP.get_global_param_string('version')}; literature keys as reported by CoolProp ({parts or 'none reported'})"


def build() -> tuple[dict, dict]:
    import CoolProp.CoolProp as CP

    version = CP.get_global_param_string("version")
    sources = [{"id": "coolprop", "ref": f"I. H. Bell, J. Wronski, S. Quoilin, V. Lemort, Pure and pseudo-pure fluid thermophysical property evaluation and the "
                                         f"open-source thermophysical property library CoolProp, Ind. Eng. Chem. Res. 53(6), 2498-2508 (2014); CoolProp {version} (MIT licence)",
                "url": "https://coolprop.org"}]
    records = []
    for fluid, (name, category) in FLUIDS.items():
        Tmin, Tmax = CP.PropsSI("Tmin", fluid), CP.PropsSI("Tmax", fluid)
        Tcrit = CP.PropsSI("Tcrit", fluid) if fluid != "Air" else 132.5
        try:
            Tb = CP.PropsSI("T", "P", P_ATM, "Q", 0, fluid)
        except (ValueError, RuntimeError):
            Tb = None
        sid = "cp-" + _slug(fluid)
        sources.append({"id": sid, "ref": _describe(CP, fluid)})
        for phase, lo, hi in (("liquid", Tmin + 0.5, Tb), ("gas", Tb if Tb else Tmin + 0.5, min(Tmax, T_TOP))):
            if hi is None or hi - lo < 5 or (fluid == "Air" and phase == "liquid"):     # air is a pseudo-pure mixture; its liquid is not a use case
                continue
            props = {}
            for prop, (key, unit) in PROPS.items():
                xs, ys = _series(CP, fluid, key, _grid(lo, hi), phase, Tb)
                if len(xs) < 5:
                    continue
                props[prop] = {"curve": {"x_unit": "K", "method": "pchip", "x": [_round(x) for x in xs], "y": [_round(y) for y in ys]},
                               "unit": unit, "basis": "computed", "source": sid, "rel_uncertainty": REL_UNC[prop], "at": {"pressure": "101.325 kPa"}}
            if phase == "liquid" and "density" in props:
                xs = [x for x in _grid(lo, hi) if x < Tcrit]
                vp = []
                for T in xs:
                    try:
                        vp.append(CP.PropsSI("P", "T", T, "Q", 0, fluid))
                    except (ValueError, RuntimeError):
                        vp.append(None)
                pts = [(x, y) for x, y in zip(xs, vp) if y and y > 1e-3]
                if len(pts) >= 5:
                    props["vapour_pressure"] = {"curve": {"x_unit": "K", "method": "pchip", "x": [_round(x) for x, _ in pts], "y": [_round(y) for _, y in pts]},
                                                "unit": "Pa", "basis": "computed", "source": sid, "rel_uncertainty": REL_UNC["vapour_pressure"]}
            if not props:
                continue
            records.append({
                "id": f"{_slug(fluid)}-{phase}", "name": f"{name} ({phase})", "category": category, "designation": CP.get_fluid_param_string(fluid, "formula"),
                "condition": f"{phase}, {lo:.0f} to {hi:.0f} K at 101.325 kPa",
                "note": ("Saturated-liquid-like values at 101.325 kPa; density, viscosity, conductivity and specific heat of a liquid change little with pressure far from the critical point."
                         if phase == "liquid" else
                         "Gas at 101.325 kPa. Density scales with pressure (about proportionally while the gas is nearly ideal); at other pressures use a real-gas calculation, not this record."),
                "properties": props})
    manifest = {
        "id": "fluids-coolprop", "version": "0.1.0", "title": "Common fluids from CoolProp (curves against temperature at 1 atm)", "kind": "fluids",
        "licence": "Values computed with the MIT-licensed CoolProp library from published equations of state; the computed numbers are physical facts and are released under the MIT licence of this repository",
        "status": f"Computed by CoolProp {version}; for hand calculations and checking, see each property's rel_uncertainty (generic orders of magnitude, fluid-specific uncertainties are in the cited models)",
        "design_use": False, "sources": sources, "checksum": ""}
    return manifest, {"records": records}


def main() -> None:
    from sliderule.core import datapack

    manifest, data = build()
    PACK.mkdir(parents=True, exist_ok=True)
    (PACK / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (PACK / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("sealed", datapack.seal(PACK))
    pack, errs = datapack.validate_pack(PACK)
    print(f"{len(data['records'])} records", "ok" if pack else errs)


if __name__ == "__main__":
    main()
