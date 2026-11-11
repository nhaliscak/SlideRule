"""The NIST cryogenic importer, on a synthetic page in the same layout (no NIST data is stored in the repository)."""

import importlib.util
from pathlib import Path

import pytest

from sliderule.core import datapack as dp

ROOT = Path(dp.__file__).parents[3]
spec = importlib.util.spec_from_file_location("import_nist_cryo", ROOT / "scripts" / "import_nist_cryo.py")
nist = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nist)

pytestmark = pytest.mark.usefixtures("no_user_packs")


def page(title="Test Alloy (UNS X00000)", k=("1", "0", "0", "0", "0", "0", "0", "0", "0"), cp=("2", "0.5", "0", "0", "0", "0", "0", "0", "0"),
         head=("Thermal Conductivity", "Specific Heat"), data=("4-300", "10-250"), eq=("1-300", "4-300")):
    rows = "".join(f"<tr><td>{c}</td><td>{k[i]}</td><td>{cp[i]}</td></tr>" for i, c in enumerate("abcdefghi"))
    return (f"<html><head><title>cryogenic material properties</title></head><body><h1>Material Properties: {title}</h1>"
            f"<table><tr><td></td><td>{head[0]}</td><td>{head[1]}</td></tr><tr><td>UNITS</td><td>W/(m-K)</td><td>J/(kg-K)</td></tr>{rows}"
            f"<tr><td>data range</td><td>{data[0]}</td><td>{data[1]}</td></tr><tr><td>equation range</td><td>{eq[0]}</td><td>{eq[1]}</td></tr>"
            f"<tr><td>curve fit % error relative to data</td><td>2</td><td>5</td></tr></table></body></html>")


def test_parse_reads_coefficients_ranges_and_error():
    got = nist.parse_page(page())
    assert got["name"] == "Test Alloy"
    k, cp = got["props"]["thermal_conductivity"], got["props"]["specific_heat"]
    assert k["coef"][0] == 1.0 and k["range"] == (4.0, 300.0) and k["err"] == pytest.approx(0.02)
    assert cp["range"] == (10.0, 250.0)                      # inside both the data and the equation range
    assert cp["unit"] == "J/(kg*K)"


def test_evaluate_is_the_log10_polynomial():
    assert nist.evaluate([1.0, 0, 0], 77.0) == pytest.approx(10.0)
    assert nist.evaluate([2.0, 0.5], 100.0) == pytest.approx(1000.0)        # 10^(2 + 0.5 * 2)
    assert nist.evaluate([0.0, 1.0, 1.0], 10.0) == pytest.approx(100.0)     # 10^(0 + 1 + 1)


def test_build_makes_a_valid_local_pack(tmp_path):
    manifest, data, skipped = nist.build({"A/a.htm": page(), "B/b.htm": page(title="Other"), "C/c.htm": "<html>no tables</html>"}, "2026-01-01")
    assert skipped == ["C/c.htm"] and len(data["records"]) == 2
    assert manifest["design_use"] is False
    assert "National Institute of Standards and Technology" in manifest["licence"] and "Changed by SlideRule" in manifest["licence"] and "AS IS" in manifest["licence"]
    folder = tmp_path / "nist-cryo"
    folder.mkdir()
    import json
    (folder / "manifest.json").write_text(json.dumps(manifest))
    (folder / "data.json").write_text(json.dumps(data))
    dp.seal(folder)
    pack, errs = dp.validate_pack(folder)
    assert pack is not None, errs
    cp = data["records"][0]["properties"]["specific_heat"]["curve"]
    assert cp["x"][0] == pytest.approx(10.0) and cp["y"][0] == pytest.approx(100 * 10 ** 0.5, rel=1e-5)


def test_unknown_columns_and_tables_without_all_coefficients_are_skipped():
    assert nist.parse_page(page(head=("Resistivity", "Magnetisation"))) is None
    assert nist.parse_page("<table><tr><td>Thermal Conductivity</td></tr><tr><td>a</td><td>1</td></tr></table>") is None


def test_categories():
    assert nist.category("6061-T6 Aluminum") == "aluminium"
    assert nist.category("304 Stainless") == "stainless steel"
    assert nist.category("Teflon") == "polymer"


def test_the_shipped_pack_is_valid_credited_and_matches_known_values():
    folder = dp.BUILTIN / "nist-cryo"
    pack, errs = dp.validate_pack(folder)
    assert pack is not None, errs
    assert len(pack["records"]) >= 20 and pack["manifest"]["design_use"] is False
    notice = (folder / "NOTICE.md").read_text(encoding="utf-8")
    assert "Change notice" in notice and "AS IS" in notice and "trc.nist.gov" in notice          # what NIST asks a redistribution to carry
    assert all(s["url"].startswith("https://trc.nist.gov/") and s["accessed"] for s in pack["manifest"]["sources"])
    k = dp.value("nist-cryo", "304-stainless", "thermal_conductivity", 293.0)["value"]
    cp = dp.value("nist-cryo", "304-stainless", "specific_heat", 293.0)["value"]
    assert k == pytest.approx(15.1, rel=0.03) and cp == pytest.approx(470.0, rel=0.03)        # widely published values for 304 stainless at room temperature
    assert dp.value("nist-cryo", "304-stainless", "thermal_conductivity", 77.0)["value"] == pytest.approx(7.9, rel=0.05)
