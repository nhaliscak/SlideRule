"""Regenerate the ``fluids-water-air`` datapack from published correlations (``python scripts/build_fluid_pack.py``).

Computed curves (no table is copied):
  water density     Kell (1975), air-free water at 101.325 kPa, 0 to 150 degC (J. Chem. Eng. Data 20, 97)
  water viscosity   Vogel form  mu = A 10^(B/(T - C)), A = 2.414e-5 Pa s, B = 247.8 K, C = 140 K (about 2 % from 0 to 100 degC)
  water vapour pressure  IAPWS-IF97 region 4 saturation-pressure equation (IAPWS R7-97(2012), section 8.1)
  air density       ideal gas, p/(R T) with R = 287.05 J/(kg K) at 101.325 kPa
  air viscosity     Sutherland: mu0 = 1.716e-5 Pa s, T0 = 273.15 K, S = 110.4 K (White, Viscous Fluid Flow)
  air conductivity  Sutherland: k0 = 0.0241 W/(m K), T0 = 273.15 K, S = 194 K (White, Viscous Fluid Flow)
Reference points (typed from the published table, 10 degC steps for water, 50 to 100 K steps for air; the property has no correlation we checked):
  water specific heat and conductivity, air specific heat: Cengel and Cimbala, Fluid Mechanics, 3rd ed. (2014), Tables A-3 and A-9.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "src" / "sliderule" / "datapacks" / "fluids-water-air"

R_AIR = 287.05
P_ATM = 101325.0

#: measured worst-case relative deviation from the reference table at rows not used to build the curve (see tests/test_datapack_fluids.py)
REL_UNCERTAINTY = {
    ("water", "density"): 0.001, ("water", "dynamic_viscosity"): 0.025, ("water", "vapour_pressure"): 0.001,
    ("water", "specific_heat"): 0.0005, ("water", "thermal_conductivity"): 0.002,
    ("air", "density"): 0.001, ("air", "dynamic_viscosity"): 0.015, ("air", "thermal_conductivity"): 0.03, ("air", "specific_heat"): 0.002,
}


def kell_density(t: float) -> float:
    """kg/m3 at t degC."""
    num = 999.83952 + 16.945176 * t - 7.9870401e-3 * t**2 - 46.170461e-6 * t**3 + 105.56302e-9 * t**4 - 280.54253e-12 * t**5
    return num / (1 + 16.879850e-3 * t)


def vogel_viscosity(T: float) -> float:
    """Pa s at T kelvin."""
    return 2.414e-5 * 10 ** (247.8 / (T - 140.0))


_N = [0.11670521452767e4, -0.72421316703206e6, -0.17073846940092e2, 0.12020824702470e5, -0.32325550322333e7,
      0.14915108613530e2, -0.48232657361591e4, 0.40511340542057e6, -0.23855557567849, 0.65017534844798e3]


def if97_psat(T: float) -> float:
    """Pa at T kelvin (IAPWS-IF97 eq. 30, 273.15 K to 647.096 K)."""
    n = _N
    th = T + n[8] / (T - n[9])
    A = th**2 + n[0] * th + n[1]
    B = n[2] * th**2 + n[3] * th + n[4]
    C = n[5] * th**2 + n[6] * th + n[7]
    return 1e6 * (2 * C / (-B + math.sqrt(B * B - 4 * A * C))) ** 4


def air_density(T: float) -> float:
    return P_ATM / (R_AIR * T)


def sutherland(T: float, v0: float, T0: float, S: float) -> float:
    return v0 * (T / T0) ** 1.5 * (T0 + S) / (T + S)


WATER_GRID_C = [0.01] + [2.5 * i for i in range(1, 41)]            # 0.01 to 100 degC
AIR_GRID_C = [-50.0 + 25.0 * i for i in range(43)]                 # -50 to 1000 degC
WATER_REF_C = [0.01, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
WATER_CP = [4217, 4194, 4182, 4178, 4179, 4181, 4185, 4190, 4197, 4206, 4217]
WATER_K = [0.561, 0.580, 0.598, 0.615, 0.631, 0.644, 0.654, 0.663, 0.670, 0.675, 0.679]
AIR_REF_C = [-50, 0, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
AIR_CP = [999, 1006, 1007, 1009, 1023, 1044, 1069, 1093, 1115, 1135, 1153, 1169, 1184]


def _curve(xs, ys, source, basis, unit, rel, note, at=None, digits=7):
    out = {"curve": {"x_unit": "degC", "method": "pchip", "x": [float(x) for x in xs], "y": [float(f"{y:.{digits}g}") for y in ys]},
           "unit": unit, "basis": basis, "source": source, "rel_uncertainty": rel, "note": note}
    if at:
        out["at"] = at
    return out


def build() -> tuple[dict, dict]:
    atm = {"pressure": "101.325 kPa"}
    T_w = [t + 273.15 for t in WATER_GRID_C]
    T_a = [t + 273.15 for t in AIR_GRID_C]
    water = {
        "id": "water-liquid", "name": "Liquid water", "category": "water", "designation": "H2O", "condition": "liquid, 0.01 to 100 degC",
        "note": "Pure air-free water at 101.325 kPa; the liquid properties change negligibly with pressure away from the critical point, and the vapour pressure is the saturation pressure.",
        "properties": {
            "density": _curve(WATER_GRID_C, [kell_density(t) for t in WATER_GRID_C], "kell", "computed", "kg/m^3", REL_UNCERTAINTY[("water", "density")],
                              "Kell (1975) formula, air-free water", atm),
            "dynamic_viscosity": _curve(WATER_GRID_C, [vogel_viscosity(T) for T in T_w], "vogel", "computed", "Pa*s", REL_UNCERTAINTY[("water", "dynamic_viscosity")],
                                        "Three-constant Vogel fit; it is about 2 % low at 0 degC, so use IAPWS values when better is needed", atm),
            "vapour_pressure": _curve(WATER_GRID_C, [if97_psat(T) for T in T_w], "if97", "computed", "Pa", REL_UNCERTAINTY[("water", "vapour_pressure")],
                                      "IAPWS-IF97 saturation-pressure equation"),
            "specific_heat": _curve(WATER_REF_C, WATER_CP, "cengel", "typical", "J/(kg*K)", REL_UNCERTAINTY[("water", "specific_heat")],
                                    "Reference points every 10 degC from the published table, interpolated", atm),
            "thermal_conductivity": _curve(WATER_REF_C, WATER_K, "cengel", "typical", "W/(m*K)", REL_UNCERTAINTY[("water", "thermal_conductivity")],
                                           "Reference points every 10 degC from the published table, interpolated", atm)}}
    air = {
        "id": "air-dry", "name": "Dry air", "category": "air", "designation": "", "condition": "ideal gas at 101.325 kPa, -50 to 1000 degC",
        "note": "Density is the ideal-gas value at 101.325 kPa (scale with pressure); viscosity, conductivity and specific heat do not depend on pressure for an ideal gas.",
        "properties": {
            "density": _curve(AIR_GRID_C, [air_density(T) for T in T_a], "idealgas", "computed", "kg/m^3", REL_UNCERTAINTY[("air", "density")],
                              "p/(R T) with R = 287.05 J/(kg K)", atm),
            "dynamic_viscosity": _curve(AIR_GRID_C, [sutherland(T, 1.716e-5, 273.15, 110.4) for T in T_a], "white", "computed", "Pa*s",
                                        REL_UNCERTAINTY[("air", "dynamic_viscosity")], "Sutherland's law"),
            "thermal_conductivity": _curve(AIR_GRID_C, [sutherland(T, 0.0241, 273.15, 194.0) for T in T_a], "white", "computed", "W/(m*K)",
                                           REL_UNCERTAINTY[("air", "thermal_conductivity")],
                                           "Sutherland's law for conductivity; it runs up to 2.4 % above the reference table, worst near 20 to 60 degC"),
            "specific_heat": _curve(AIR_REF_C, AIR_CP, "cengel", "typical", "J/(kg*K)", REL_UNCERTAINTY[("air", "specific_heat")],
                                    "Reference points from the published table, interpolated")}}
    manifest = {
        "id": "fluids-water-air", "version": "0.1.0", "title": "Water and dry air (curves against temperature)", "kind": "fluids",
        "licence": "Correlations are published formulas; reference points are facts from the cited table; the compiled pack is released under the MIT licence of this repository",
        "status": "Computed curves from published correlations, checked against a reference table; suitable for hand calculations, see each property's rel_uncertainty",
        "design_use": False,
        "sources": [
            {"id": "kell", "ref": "G. S. Kell, Density, thermal expansivity and compressibility of liquid water from 0 to 150 C, J. Chem. Eng. Data 20(1), 97-105 (1975)"},
            {"id": "vogel", "ref": "Vogel-form viscosity fit mu = 2.414e-5 * 10^(247.8/(T-140)) Pa s; checked here against the IAPWS-based table at https://www.chem-casts.com/knowledge/viscosity-of-water"},
            {"id": "if97", "ref": "IAPWS R7-97(2012), Revised Release on the IAPWS Industrial Formulation 1997, section 8.1 saturation-pressure equation", "url": "https://iapws.org/documents/release/IF97-Rev.download"},
            {"id": "idealgas", "ref": "Ideal-gas law with the specific gas constant of dry air, 287.05 J/(kg K)"},
            {"id": "white", "ref": "F. M. White, Viscous Fluid Flow, Sutherland constants for air (viscosity: 1.716e-5 Pa s, 273.15 K, 110.4 K; conductivity: 0.0241 W/(m K), 273 K, 194 K)"},
            {"id": "cengel", "ref": "Y. A. Cengel and J. M. Cimbala, Fluid Mechanics: Fundamentals and Applications, 3rd ed., McGraw-Hill (2014), Table A-3 (saturated water) and Table A-9 (air at 1 atm)",
             "url": "https://www.me.psu.edu/cimbala/me405/Links/Table_A_3_CC_Saturated_Water.pdf", "accessed": "2026-10-31"}],
        "checksum": ""}
    return manifest, {"records": [water, air]}


def main() -> None:
    from sliderule.core import datapack

    manifest, data = build()
    PACK.mkdir(parents=True, exist_ok=True)
    (PACK / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (PACK / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("sealed", datapack.seal(PACK))
    pack, errs = datapack.validate_pack(PACK)
    print("ok" if pack else errs)


if __name__ == "__main__":
    main()
