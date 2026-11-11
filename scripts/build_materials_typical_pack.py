"""Regenerate the ``materials-typical`` datapack (``python scripts/build_materials_typical_pack.py``).

Every number below is a value *printed* in an open source, with the printed unit; the conversion to SI is done here, so nothing is converted by hand.
Open sources only (US government works and openly distributed reports):

  NASA CR-123772   Materials Data Handbook: Aluminum Alloy 6061 (2nd ed.), R. F. Muraca and J. S. Whittick, Western Applied Research & Development for NASA MSFC,
                   May 1972, https://ntrs.nasa.gov/citations/19720022808 (compiled largely from MIL-HDBK-5A, which is superseded)
  NASA CR-123775   Materials Data Handbook: Titanium 6Al-4V, same authors and date, https://ntrs.nasa.gov/citations/19720022814
  NISTIR 7401      D. P. Bentz and K. R. Prasad, Thermal Performance of Fire Resistive Materials I, NIST, February 2007 (mild steel, section 3.1.2 and Table 5)
  Wyoming DOT      Bridge Design Manual, Chapter 1, revised January 2022, page 1-4 (steel modulus and thermal expansion)
  NIST cryogenics  Ti-6Al-4V conductivity fit, read from the shipped ``nist-cryo`` pack at 293 K
  NBS RP 1742      A. H. Stang, M. Greenspan and S. B. Newman, Poisson's Ratio of Some Structural Alloys for Large Strains, J. Res. NBS 37, 211-221 (October 1946),
                   Table 2 (page 216): elastic Poisson's ratio of six specimens of structural low-carbon steel (ASTM A7-42)

A value with no open source would keep the source "citation needed" instead of being dropped, so the gap is visible (none is left at present).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "src" / "sliderule" / "datapacks" / "materials-typical"
sys.path.insert(0, str(ROOT / "src"))

KSI = 6.894757               # MPa per ksi
CAL_K = 418.4                # W/(m K) per cal/(cm s degC)
CAL_CP = 4184.0              # J/(kg K) per cal/(g degC)
PER_F = 1.8                  # 1/K per 1/degF
ACCESSED = "2026-11-06"
#: Table 2 of NBS RP 1742, structural steel plates and angles, direction 0: 3/8 in plate (3 specimens) and 1/2 in angle (3 specimens)
STEEL_NU = [0.256, 0.265, 0.270, 0.265, 0.260, 0.271]


def sig(x: float, n: int = 4) -> float:
    return float(f"{x:.{n}g}")


def val(value, unit, source, note, *, low=None, high=None, at=None, basis="typical", **extra):
    d = {"value": value, "unit": unit, "basis": basis, "source": source}
    if low is not None:
        d["low"] = low
    if high is not None:
        d["high"] = high
    if at:
        d["at"] = at
    d["note"] = note
    d.update(extra)
    return d


def nist_ti_conductivity() -> tuple[float, float]:
    """Thermal conductivity of Ti-6Al-4V at 293 K and NIST's stated fit error, from the shipped nist-cryo pack."""
    from sliderule.core import datapack as dp

    here = dp.BUILTIN / "nist-cryo"
    pack, errs = dp.validate_pack(here)
    assert pack is not None, errs
    rec = next(r for r in pack["records"] if r["id"] == "ti-6al-4v")
    p = rec["properties"]["thermal_conductivity"]
    xs, ys = p["curve"]["x"], p["curve"]["y"]
    from sliderule.core import tables

    f = tables.interpolator(xs, ys, p["curve"].get("method", "pchip"), "error")[0]
    return sig(float(f(293.0)), 3), p["rel_uncertainty"]


def build() -> tuple[dict, dict]:
    k_ti, err_ti = nist_ti_conductivity()
    old = "A 1972 handbook compiled largely from MIL-HDBK-5A, which is superseded (MMPDS replaced it): the minimums shown as `low` are that edition's A-basis or specification values, not current allowables."
    sources = [
        {"id": "nasa-al6061", "ref": "R. F. Muraca and J. S. Whittick, Materials Data Handbook: Aluminum Alloy 6061 (2nd edition), NASA CR-123772, Western Applied Research & Development "
                                    "for NASA Marshall Space Flight Center, May 1972; page numbers in the notes are the printed ones",
         "url": "https://ntrs.nasa.gov/citations/19720022808", "accessed": ACCESSED},
        {"id": "nasa-ti64", "ref": "R. F. Muraca and J. S. Whittick, Materials Data Handbook: Titanium 6Al-4V (2nd edition), NASA CR-123775, Western Applied Research & Development "
                                   "for NASA Marshall Space Flight Center, May 1972; page numbers in the notes are the printed ones",
         "url": "https://ntrs.nasa.gov/citations/19720022814", "accessed": ACCESSED},
        {"id": "nist-cryo-ti", "ref": "NIST Cryogenic Technologies Group, Cryogenic Material Properties: Ti-6Al-4V, log10 polynomial fit for thermal conductivity, evaluated at 293 K by SlideRule "
                                       "(see the nist-cryo pack for NIST's notice)",
         "url": "https://trc.nist.gov/cryogenics/materials/Ti6Al4V/Ti6Al4V_rev.htm", "accessed": "2026-11-03"},
        {"id": "nistir7401", "ref": "D. P. Bentz and K. R. Prasad, Thermal Performance of Fire Resistive Materials I. Characterization with Respect to Thermal Performance Models, "
                                     "NISTIR 7401, National Institute of Standards and Technology, February 2007, section 3.1.2 and Table 5 (page 8); the conductivity and heat capacity "
                                     "are values collected for NIST's World Trade Center investigation",
         "url": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=860705", "accessed": ACCESSED},
        {"id": "wydot", "ref": "Wyoming Department of Transportation, Bridge Design Manual, Chapter 1, General Design Information (revised January 2022), page 1-4: coefficient of thermal "
                                "expansion for steel and the modulus of elasticity for all grades of structural steel (design values prescribed by the manual)",
         "url": "https://dot.state.wy.us/files/live/sites/wydot/files/shared/Bridge/Bridge%20Design%20Manual/Chapter%201%20-%20General%20Design%20Information_revised%20January%202022%20final.pdf",
         "accessed": ACCESSED},
        {"id": "nbs-rp1742", "ref": "A. H. Stang, M. Greenspan and S. B. Newman, Poisson's Ratio of Some Structural Alloys for Large Strains, Journal of Research of the National Bureau of "
                                    "Standards 37, 211-221 (October 1946), Research Paper RP 1742, Table 2 (page 216)",
         "url": "https://nvlpubs.nist.gov/nistpubs/jres/37/jresv37n4p211_A1b.pdf", "accessed": "2026-11-07"},
    ]
    steel = {
        "id": "steel-carbon-structural", "name": "Structural carbon steel (generic)", "category": "steel", "designation": "", "condition": "room temperature",
        "note": "Generic values for hand estimates, from open sources; no grade-specific strengths (A36, A992, S355 ...) because no open source for them has been entered yet.",
        "properties": {
            "density": val(7860, "kg/m^3", "nistir7401", "'Commonly reported as 7860 kg/m3 at 23 degC' (section 3.1.2, page 7)", at={"temperature": "23 degC"}),
            "youngs_modulus": val(sig(29000 * KSI / 1000, 4), "GPa", "wydot", "29,000,000 psi, 'for all grades of structural steel' (page 1-4): 199.9 GPa", basis="design"),
            "poisson_ratio": val(sig(sum(STEEL_NU) / len(STEEL_NU), 3), "1", "nbs-rp1742", "mean of six specimens of structural low-carbon steel to ASTM A7-42 (3/8 in plate and 1/2 in angle), "
                                 "measured in 1946: 0.256 to 0.271 (low and high); fully killed carbon steel plate averages 0.271 (18 specimens, 0.263 to 0.279). "
                                 "Modern grades such as A36 and A992 were not tested", low=min(STEEL_NU), high=max(STEEL_NU)),
            "thermal_expansion": val(sig(6.5e-6 * PER_F, 3), "1/K", "wydot", "6.5e-6 per degF as printed (page 1-4), the value the manual prescribes for steel", basis="design"),
            "thermal_conductivity": val(48.8, "W/(m*K)", "nistir7401", "Table 5, mild steel at 26.85 degC (page 8); it falls to 29.7 at 716.85 degC", at={"temperature": "26.85 degC"}),
            "specific_heat": val(435, "J/(kg*K)", "nistir7401", "Table 5, mild steel at 26.85 degC (page 8); it rises to 871 at 716.85 degC", at={"temperature": "26.85 degC"}),
        }}
    aluminium = {
        "id": "aluminium-6061-t6", "name": "Aluminium alloy 6061-T6", "category": "aluminium", "designation": "6061", "condition": "T6",
        "note": "Typical values with the printed minimums as `low`. " + old,
        "properties": {
            "density": val(2700, "kg/m^3", "nasa-al6061", "2.70 g/cm3 at 20 degC (0.098 lb/in3 at 68 degF), section 9.1, page 75", at={"temperature": "20 degC"}),
            "youngs_modulus": val(sig(10.0e3 * KSI / 1000, 3), "GPa", "nasa-al6061", "typical E 10.0 x 10^3 ksi (section 7.222, page 39); `low` is the design value 9.9 x 10^3 ksi (section 7.221)",
                                  low=sig(9.9e3 * KSI / 1000, 3)),
            "poisson_ratio": val(0.33, "1", "nasa-al6061", "section 7.21, page 39"),
            "thermal_expansion": val(sig(23.4e-6, 3), "1/K", "nasa-al6061", "mean 20 to 100 degC, 23.4 x 10^-6 per degC (section 9.22, page 75)"),
            "thermal_conductivity": val(sig(0.40 * CAL_K, 3), "W/(m*K)", "nasa-al6061", "T6 temper 0.40 cal/(cm s degC) at 25 degC (section 9.21, page 75, and the abstract, page iv); the NIST cryogenic fit "
                                        "in the nist-cryo pack gives 154 at 293 K, kept as `low`", low=154, at={"temperature": "25 degC"}),
            "specific_heat": val(sig(0.23 * CAL_CP, 3), "J/(kg*K)", "nasa-al6061", "0.23 cal/(g degC) at 100 degC (section 9.23, page 75)", at={"temperature": "100 degC"}),
            "yield_strength": val(sig(40.0 * KSI, 4), "MPa", "nasa-al6061", "typical tensile yield 40.0 ksi (abstract, page iv); `low` is the A-basis minimum 35 ksi for sheet, plate, bar, rod and shapes in T6 "
                                  "(Table 7.4111, page 43)", low=sig(35 * KSI, 4)),
            "ultimate_strength": val(sig(45.0 * KSI, 4), "MPa", "nasa-al6061", "typical ultimate tensile strength 45.0 ksi (abstract, page iv); `low` is the A-basis minimum 42 ksi "
                                     "(Table 7.4111, page 43)", low=sig(42 * KSI, 4)),
        }}
    titanium = {
        "id": "titanium-ti6al4v-annealed", "name": "Titanium Ti-6Al-4V (Grade 5), annealed", "category": "titanium", "designation": "Ti-6Al-4V", "condition": "annealed",
        "note": "Annealed typical values with the printed minimums as `low`. " + old,
        "properties": {
            "density": val(4424, "kg/m^3", "nasa-ti64", "4.424 g/cm3 at 20 degC (abstract, page iv); 0.160 lb/in3 (section 9.1, page 81)", at={"temperature": "20 degC"}),
            "youngs_modulus": val(sig(16.5e3 * KSI / 1000, 4), "GPa", "nasa-ti64", "typical E 16.5 x 10^3 ksi in tension (abstract, page iv); `low` is the design value 16.0 x 10^3 ksi for all forms "
                                  "(section 7.221, page 39)", low=sig(16.0e3 * KSI / 1000, 4)),
            "poisson_ratio": val(0.342, "1", "nasa-ti64", "section 7.21, page 39"),
            "thermal_expansion": val(sig(8.8e-6, 3), "1/K", "nasa-ti64", "mean 0 to 100 degC, 8.8 x 10^-6 per degC (abstract, page iv)"),
            "thermal_conductivity": val(k_ti, "W/(m*K)", "nist-cryo-ti", "NIST's log10 polynomial fit evaluated at 293 K; `rel_uncertainty` is NIST's stated fit error against its own data. "
                                        "The 1972 abstract prints 0.012 with garbled units, so it is not used", basis="computed", rel_uncertainty=err_ti),
            "specific_heat": val(sig(0.135 * CAL_CP, 3), "J/(kg*K)", "nasa-ti64", "0.135 cal/(g degC) at 20 degC as printed (abstract, page iv); an old value, check it against a current source",
                                 at={"temperature": "20 degC"}),
            "yield_strength": val(sig(128 * KSI, 4), "MPa", "nasa-ti64", "typical annealed tensile yield 128 ksi (abstract, page iv); `low` is the specification minimum 120 ksi for annealed plate "
                                  "0.1876 to 4.000 in (Table 7.4111, page 42); the A-basis for sheet up to 0.1875 in is 126 ksi", low=sig(120 * KSI, 4)),
            "ultimate_strength": val(sig(138 * KSI, 4), "MPa", "nasa-ti64", "typical annealed ultimate strength 138 ksi (abstract, page iv); `low` is the specification minimum 130 ksi for annealed plate "
                                     "0.1876 to 4.000 in (Table 7.4111, page 42); the A-basis for sheet up to 0.1875 in is 134 ksi", low=sig(130 * KSI, 4)),
        }}
    manifest = {
        "id": "materials-typical", "version": "0.2.1", "title": "Typical engineering materials (starter)", "kind": "materials",
        "licence": "Values read from NASA contractor reports (NASA CR-123772 and CR-123775, 1972), NIST reports (NISTIR 7401; National Bureau of Standards RP 1742, 1946) and NIST's cryogenic fits (all published without a copyright notice "
                   "by US government sources, distributed through NASA's and NIST's public servers) and from one state agency manual (Wyoming DOT) for two code-prescribed steel values; the numbers are "
                   "physical facts compiled and converted to SI by the SlideRule authors, released under the MIT licence of this repository",
        "status": "Starter pack: typical values with the printed minimums as the low end, NOT design values. The aluminium and titanium sources are 1972 and rest on a superseded handbook; "
                  "a value without an open source would read 'citation needed' (none at present)",
        "design_use": False, "sources": sources, "checksum": ""}
    return manifest, {"records": [steel, aluminium, titanium]}


def main() -> None:
    from sliderule.core import datapack

    manifest, data = build()
    (PACK / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (PACK / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("sealed", datapack.seal(PACK))
    pack, errs = datapack.validate_pack(PACK)
    print("ok" if pack else errs)


if __name__ == "__main__":
    main()
