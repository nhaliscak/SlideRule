"""The CRC Handbook importer, tested on a small synthetic extract in the same shape as the real one (no Handbook content is kept in the repository)."""

import importlib.util
import json
from pathlib import Path

import pytest

from sliderule.core import datapack as dp

ROOT = Path(dp.__file__).parents[3]
spec = importlib.util.spec_from_file_location("import_crc_materials", ROOT / "scripts" / "import_crc_materials.py")
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)


def table(page, rows):
    return {"type": "Table", "page": page, "text": "", "table_rows": rows}


def extract(tmp_path):
    els = [
        # metals table: one cell per column holding all names (three metals, the third has no density value printed in the grid order)
        table(2082, [["Metal", "Atomic", "tm", "tb", "∆fus H", "ρ25", "α × 106", "cp", "λ"], ["(symbol)"] + [""] * 8,
                     ["Fooium (Fo) Barium (Ba) Bazium (Bz)", "1. 0 2. 0 3. 0", "1 2 3", "4 5 6", "7 8 9", "2. 70 8. 96 0. 534", "1 2", "0.1 0.2 0.3", "1 2 3"]]),
        # newer extract: one metal per row; 'b' marks a value taken at 100 degC (dropped), 'a' an estimate
        table(2083, [["Metal", "Atomic", "tm", "tb", "∆fus H", "ρ25", "α× 10^6", "cp", "λ"], ["(symbol)", "weight", "°C", "°C", "J/g", "g/cm3", "K-1", "J/g K", "W/cm K"],
                     ["Quuxium (Qx)", "50. 0", "100", "200", "10. 0", "4. 50", "12. 0", "0. 500", "1. 50b"], ["Zetium (Ze)", "60. 0", "100", "200", "", "7. 10", "", "0. 250a", "2. 5a"]]),
        # thermal conductivity of pure metals against T, W/cm K, header names with a footnote letter, a carbon-like column that is skipped
        table(2084, [["", "", "Thermal Conductivity in W/cm K"], ["T/K", "Ag", "Cu"],
                     ["1", "39.4", "42.2"], ["100", "4.50", "4.82"], ["200", "4.30", "4.13"], ["300", "4.29", "4.01"], ["400", "4.25", "3.93"]]),
        table(2085, [["T/K", "Fe", "Gea"], ["100", "1.0", "0.60"], ["200", "0.94", "0.30"], ["300", "0.80", "0.60"], ["2000", "0.5*", ""]]),
        table(2086, [["", "", "Thermal conductivity in W/m K"] + [""] * 7, ["", "Alloy", "4 K", "20 K", "77 K", "194 K", "273 K", "373 K", "573 K", "973 K"],
                     ["Ferrous:", "plain carbon steel(AISI 1020)", "13", "20", "58", "65", "65", "", "", ""], ["", "stainless steel", "0.3", "2", "8", "13", "14", "16", "19", "25"],
                     ["Gold:", "only cryogenic", "1.2", "8.6", "", "", "", "", "", ""]]),
        table(2081, [["", "", "", "Cp in J/mol K"], ["Name", "200 K", "250 K", "300 K 350 K", "400 K", "500 K", "600 K"],
                     ["Aluminum", "21.33", "23.08", "24.25 25.11", "25.78", "26.84", "27.89"], ["Potassium", "27.00", "28.01", "29.60", "", "", ""],
                     ["Germanium", "", "", "23.25 23.85", "24.31", "24.96", "25.45"], ["Benzoic acid", "102.7", "123.5", "147.4 172.0", "", "", ""]]),
        table(2089, [["Material", "Dens.", "t", "Ther. cond.", "Material", "Dens.", "t", "Ther. cond."], ["", "g/cm3", "°C", "W/m K", "", "", "", ""],
                     ["Alumina (Al2O3)", "3.8", "100", "30", "Ebonite", "1.2", "0", "0.16"], ["", "", "400", "13", "Glass wool", "0.2", "–200 to 20", "0.005"],
                     ["", "3.5", "100", "17", "", "", "50", "0.04"], ["Graphite", "", "", "", "Mica:", "", "", ""], ["100 mesh", "0.48", "40", "0.18", "muscovite", "", "100", "0.72"],
                     ["Linoleum cork", "0.54", "20", "0.08", "", "", "300", "0.65"]]),
        table(2090, [["Material", "Dens.", "t", "Ther. cond.", "Material", "Dens.", "t", "Ther. cond."], ["", "g/cm3", "°C", "W/m K", "", "", "", ""],
                     ["Canadian", "", "300", "0.19", "Wood:", "", "", ""], ["", "", "600", "0.2", "balsa, ⊥", "0.11", "30", "0.04"], ["Sand, dry", "1.5", "20", "0.33", "Wool", "0.09", "30", "0.04"]]),
        table(748, [["", "Elastic moduli (GPa)", "", "", "Mechanical properties (MPa)", "", "", ""], ["Rare earth", "Young’s (elastic) Shear Bulk", "Poisson’s", "Yield", "UTS", "Uniform", "Red.", "Recryst."],
                    ["Qq", "74.4 29.1 56.6", "0.279", "173a", "255a", "5.0a", "8.0a", "550"], ["βZz", "— — —", "", "", "", "", "", ""],
                    ["γCe", "10.0 4.0 7.0", "0.200", "50", "90", "", "", ""]]),
        table(748, [["", "", "Elastic moduli (GPa)", "", "", "", "Mechanical properties (MPa)", "", "", ""],
                    ["Rare earth", "Young’s (elastic)", "Shear", "Bulk", "Poisson’s", "Yield strength", "Ultimate tensile", "Uniform", "Reduction", "Recryst."],
                    ["metal", "modulus", "modulus", "modulus", "ratio", "0.2% offset", "strength", "elongation (%)", "in area (%)", "temp. (°C)"],
                    ["αLa", "11.0", "4.0", "8.0", "0.300", "30a", "60", "7.0", "—", "300"], ["βCe", "—", "—", "—", "—", "86", "138", "—", "24.0", "—"]]),
    ]
    folder = tmp_path / "hb"
    folder.mkdir()
    (folder / "handbook.elements.jsonl").write_text("\n".join(json.dumps(e) for e in els), encoding="utf-8")
    return imp.build(folder)


@pytest.fixture
def built(tmp_path):
    return extract(tmp_path)


def rec(built, rid):
    return next(r for r in built[1]["records"] if r["id"] == rid)


def test_the_extract_is_a_valid_materials_pack(built, tmp_path):
    manifest, data, _ = built
    out = tmp_path / "pack"
    out.mkdir()
    (out / "manifest.json").write_text(json.dumps(manifest))
    (out / "data.json").write_text(json.dumps(data))
    dp.seal(out)
    pack, errs = dp.validate_pack(out)
    assert errs == [] and pack["manifest"]["design_use"] is False and "Do not redistribute" in manifest["licence"]


def test_pure_metal_conductivity_is_converted_and_limited_to_100_k_and_above(built):
    ag = rec(built, "element-ag")["properties"]["thermal_conductivity"]["curve"]
    assert ag["x"] == [100.0, 200.0, 300.0, 400.0] and ag["y"] == [450.0, 430.0, 429.0, 425.0]          # W/cm K x 100; the 1 K row is dropped
    assert rec(built, "element-cu")["properties"]["thermal_conductivity"]["curve"]["y"][0] == 482.0
    assert rec(built, "element-ge")["properties"]["thermal_conductivity"]["curve"]["x"] == [100.0, 200.0, 300.0]   # 'Gea' read as Ge; the 2000 K row is blank for it
    assert rec(built, "element-fe")["properties"]["thermal_conductivity"]["curve"]["x"][-1] == 2000.0


def test_alloys_use_the_group_label_and_need_two_points_from_77_k(built):
    ss = rec(built, "alloy-ferrous-stainless-steel")["properties"]["thermal_conductivity"]["curve"]
    assert ss["x"] == [77.0, 194.0, 273.0, 373.0, 573.0, 973.0] and ss["y"] == [8.0, 13.0, 14.0, 16.0, 19.0, 25.0]
    assert rec(built, "alloy-ferrous-plain-carbon-steel-aisi-1020")["name"].startswith("Ferrous: ")
    assert not any(r["id"].startswith("alloy-gold") for r in built[1]["records"])                      # one point at 77 K or above is not a curve


def test_molar_heat_capacity_becomes_specific_heat_and_ambiguous_cells_are_handled(built):
    al = rec(built, "element-aluminum")["properties"]["specific_heat"]["curve"]
    assert al["x"] == [200, 250, 300, 350, 400, 500, 600] and al["y"][2] == pytest.approx(24.25 / 26.982 * 1000, rel=1e-5)
    k = rec(built, "element-potassium")["properties"]["specific_heat"]["curve"]
    assert k["x"] == [200, 250, 300]                                                                  # one value in the merged cell and nothing after it: 300 K
    ge = rec(built, "element-germanium")["properties"]["specific_heat"]["curve"]
    assert ge["x"] == [300, 350, 400, 500, 600]                                                       # blank 200 and 250 K cells stay blank
    assert not any("benzoic" in r["id"] for r in built[1]["records"])                                 # no atomic weight, not an element: left out


def test_density_comes_from_the_complete_column_only(built):
    assert rec(built, "element-fooium")["properties"]["density"]["value"] == 2700.0
    assert rec(built, "element-barium")["properties"]["density"]["value"] == 8960.0 and rec(built, "element-bazium")["properties"]["density"]["value"] == 534.0
    assert "specific_heat" not in rec(built, "element-fooium")["properties"]                          # the incomplete columns of that table are not used


def test_insulators_follow_the_headings_children_and_the_two_block_reading_order(built):
    ids = {r["id"] for r in built[1]["records"]}
    al = rec(built, "material-alumina-al2o3-3-8")["properties"]
    assert al["thermal_conductivity"]["curve"]["x"] == [100.0, 400.0] and al["density"]["value"] == 3800.0
    assert rec(built, "material-alumina-al2o3-3-5")["properties"]["density"]["value"] == 3500.0        # a second density starts a second entry
    assert rec(built, "material-graphite-100-mesh-0-48")["name"].startswith("Graphite: 100 mesh")      # a lower-case entry under a heading is its child
    assert "material-linoleum-cork-0-54" in ids and "material-graphite-linoleum-cork-0-54" not in ids  # a capitalised entry ends the group
    mica = rec(built, "material-mica-muscovite")["properties"]["thermal_conductivity"]["curve"]
    assert mica["x"] == [100.0, 300.0]                                                                # the right block of page 1 continues with the left block of page 2
    assert rec(built, "material-mica-canadian")["properties"]["thermal_conductivity"]["curve"]["x"] == [300.0, 600.0]   # the known exception
    assert rec(built, "material-wood-balsa-perp-0-11")["properties"]["thermal_conductivity"]["value"] == 0.04
    assert rec(built, "material-sand-dry-1-5")["properties"]["density"]["value"] == 1500.0
    gw = rec(built, "material-glass-wool-0-2")["properties"]["thermal_conductivity"]                    # the '-200 to 20' row is a range, not a point: only the 50 degC row remains
    assert gw["value"] == 0.04 and gw["at"] == {"temperature": "50 degC"}


def rec_full(built, rid):
    return next(r for r in built[1]["records"] if r["id"] == rid)


def test_rare_earth_moduli_and_mechanical_properties(built):
    r = rec(built, "element-qq")["properties"]
    assert r["youngs_modulus"]["value"] == 74.4 and r["poisson_ratio"]["value"] == 0.279 and r["yield_strength"]["value"] == 173.0 and r["ultimate_strength"]["value"] == 255.0
    assert not any(x["id"] == "element-zz" for x in built[1]["records"])                               # a row of dashes has no values


def test_pure_metals_table_one_metal_per_row(built):
    q = rec(built, "element-quuxium")["properties"]
    assert q["density"]["value"] == 4500.0 and q["density"]["at"] == {"temperature": "25 degC"}
    assert q["thermal_expansion"]["value"] == pytest.approx(1.2e-5) and q["specific_heat"]["value"] == 500.0
    assert "thermal_conductivity" not in q                                                             # footnote b: measured at 100 degC, not at the column's temperature
    z = rec(built, "element-zetium")["properties"]
    assert z["thermal_conductivity"]["value"] == 250.0 and z["thermal_conductivity"]["at"] == {"temperature": "27 degC"}
    assert "Estimated" in z["thermal_conductivity"]["note"] and "thermal_expansion" not in z           # an empty cell gives no value


def test_rare_earth_grid_layout_and_phases(built):
    la = rec_full(built, "element-lanthanum-alpha")
    assert la["name"] == "Lanthanum (alpha)" and la["properties"]["youngs_modulus"]["value"] == 11.0 and la["properties"]["yield_strength"]["value"] == 30.0
    ce = rec_full(built, "element-cerium-beta")
    assert set(ce["properties"]) == {"yield_strength", "ultimate_strength"}                          # dashes give no modulus, the strengths remain
    assert "element-cerium-gamma" in {r["id"] for r in built[1]["records"]}                           # two phases of one element stay two records


def test_rare_earth_records_carry_the_element_name_and_keep_the_phase(built):
    ce = rec_full(built, "element-cerium-gamma")
    assert ce["name"] == "Cerium (gamma)" and ce["designation"] == "γ-Ce" and "gamma phase" in ce["condition"]
    assert rec_full(built, "element-qq")["name"] == "Qq"                                               # an unknown symbol stays as printed
    assert all(r["name"] not in imp.ELEMENT_NAMES.keys() for r in built[1]["records"])               # never a bare symbol such as 'Ce' or 'Ge'
    assert set(imp.SYMBOLS) <= set(imp.ELEMENT_NAMES)


def test_a_changed_table_layout_is_reported_not_silent(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    (folder / "handbook.elements.jsonl").write_text(json.dumps({"type": "Title", "text": "nothing", "page": 1, "bbox": [0, 0, 1, 1]}) + "\n")
    _, _, report = imp.build(folder)
    assert sum(line.startswith("WARNING") for line in report) == 3


def test_numbers_with_footnotes_and_text_are_told_apart():
    assert imp.num("173a") == 173.0 and imp.num("0.402*") == 0.402 and imp.num("–150") == -150.0 and imp.num("–200 to 20") is None and imp.num("—") is None and imp.num("") is None
    assert imp.num("12 ± 3") is None


def test_the_extract_never_lands_in_the_repository_by_default():
    default = dp.user_folder() / "crc-materials"
    assert ROOT not in default.parents
    assert "crc-" in (ROOT / ".gitignore").read_text()
