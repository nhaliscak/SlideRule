"""Datapacks: the built-in pack is clean, bad packs are refused for the right reason, and the API and CLI expose the records with their sources."""

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sliderule import api
from sliderule.core import datapack as dp
from sliderule.server import create_app
from sliderule.units import default_registry

BUILTIN_PACK = dp.BUILTIN / "materials-typical"

pytestmark = pytest.mark.usefixtures("no_user_packs")

client = TestClient(create_app(serve_frontend=False))


@pytest.fixture
def pack_copy(tmp_path):
    """A writable copy of the built-in pack, returned with helpers to edit and re-seal it."""
    dst = tmp_path / "p"
    shutil.copytree(BUILTIN_PACK, dst)

    def edit(fn, seal=True):
        d = json.loads((dst / "data.json").read_text())
        fn(d)
        (dst / "data.json").write_text(json.dumps(d))
        if seal:
            dp.seal(dst)
        return dp.validate_pack(dst)

    return dst, edit


def test_builtin_pack_is_valid_and_loaded():
    pack, errs = dp.validate_pack(BUILTIN_PACK)
    assert errs == [] and pack is not None
    assert "materials-typical" in dp.packs() and dp.problems() == {}
    assert pack["manifest"]["design_use"] is False        # the starter pack must never claim to be design data


def test_every_property_has_a_source_a_basis_and_a_consistent_unit():
    reg = default_registry()
    for rec in dp.packs()["materials-typical"]["records"]:
        for name, p in rec["properties"].items():
            _, canon, lo, hi = dp.VOCABULARY[name]
            assert reg.parse(p["unit"]).dim == reg.parse(canon).dim
            assert p["basis"] in dp.BASES and p["source"] in dp.packs()["materials-typical"]["sources"]
            si = reg.parse(p["unit"]).to_si(p["value"])
            assert lo <= reg.parse(canon).from_si(si) <= hi


def test_stored_values_match_the_pages_they_cite():
    """Golden values typed independently of the data file from the cited pages (guards against an accidental edit that keeps the checksum).
    Printed values: NASA CR-123772 (6061) and CR-123775 (Ti-6Al-4V), NISTIR 7401 Table 5 (mild steel), Wyoming DOT Bridge Design Manual page 1-4."""
    gold = {("aluminium-6061-t6", "density"): 2700, ("aluminium-6061-t6", "youngs_modulus"): 68.9, ("aluminium-6061-t6", "poisson_ratio"): 0.33,
            ("aluminium-6061-t6", "yield_strength"): 275.8, ("aluminium-6061-t6", "ultimate_strength"): 310.3,        # 40 and 45 ksi
            ("aluminium-6061-t6", "thermal_conductivity"): 167.0, ("aluminium-6061-t6", "specific_heat"): 962.0,     # 0.40 cal/(cm s C), 0.23 cal/(g C)
            ("titanium-ti6al4v-annealed", "density"): 4424, ("titanium-ti6al4v-annealed", "youngs_modulus"): 113.8,   # 4.424 g/cc, 16.5e3 ksi
            ("titanium-ti6al4v-annealed", "poisson_ratio"): 0.342, ("titanium-ti6al4v-annealed", "yield_strength"): 882.5,     # 128 ksi
            ("titanium-ti6al4v-annealed", "ultimate_strength"): 951.5, ("titanium-ti6al4v-annealed", "specific_heat"): 565.0,  # 138 ksi, 0.135 cal/(g C)
            ("steel-carbon-structural", "density"): 7860, ("steel-carbon-structural", "youngs_modulus"): 199.9,       # 29,000,000 psi
            ("steel-carbon-structural", "thermal_conductivity"): 48.8, ("steel-carbon-structural", "specific_heat"): 435,
            ("steel-carbon-structural", "poisson_ratio"): 0.265}                                                       # mean of 0.256 0.265 0.270 0.265 0.260 0.271, NBS RP 1742 Table 2
    for (rid, prop), v in gold.items():
        assert dp.record("materials-typical", rid)["properties"][prop]["value"] == pytest.approx(v, rel=1e-9)
    assert dp.record("materials-typical", "steel-carbon-structural")["properties"]["thermal_expansion"]["value"] == pytest.approx(6.5e-6 * 1.8, rel=0.005)   # 6.5e-6 per degF


def test_the_low_end_is_the_printed_minimum_and_never_above_the_typical_value():
    al = dp.record("materials-typical", "aluminium-6061-t6")["properties"]
    ti = dp.record("materials-typical", "titanium-ti6al4v-annealed")["properties"]
    assert al["yield_strength"]["low"] == pytest.approx(241.3) and al["ultimate_strength"]["low"] == pytest.approx(289.6)       # 35 and 42 ksi, A basis
    assert ti["yield_strength"]["low"] == pytest.approx(827.4) and ti["ultimate_strength"]["low"] == pytest.approx(896.3)       # 120 and 130 ksi, specification minimum
    for rec in dp.packs()["materials-typical"]["records"]:
        for name, p in rec["properties"].items():
            assert "low" not in p or p["low"] <= p["value"], (rec["id"], name)


def test_every_value_has_a_cited_source_and_the_steel_poisson_ratio_is_the_measured_spread():
    pack = dp.packs()["materials-typical"]
    refs = {s["id"]: s["ref"] for s in pack["manifest"]["sources"]}
    assert "NASA CR-123772" in refs["nasa-al6061"] and "NASA CR-123775" in refs["nasa-ti64"] and "NISTIR 7401" in refs["nistir7401"]
    assert "RP 1742" in refs["nbs-rp1742"] and "citation needed" not in refs.values()
    unsourced = [(r["id"], k) for r in pack["records"] for k, p in r["properties"].items() if "citation needed" in refs[p["source"]]]
    assert unsourced == []
    nu = next(r for r in pack["records"] if r["id"] == "steel-carbon-structural")["properties"]["poisson_ratio"]
    assert (nu["low"], nu["high"]) == (0.256, 0.271)                                                                   # the extremes printed in Table 2 for structural steel


def test_record_is_returned_in_si_with_provenance():
    r = dp.record("materials-typical", "titanium-ti6al4v-annealed")
    e = r["properties"]["youngs_modulus"]
    assert e["si_value"] == pytest.approx(113.8e9) and e["si_unit"] == "Pa"
    assert e["source_ref"].startswith("R. F. Muraca") and "NASA CR-123775" in e["source_ref"] and r["pack_version"] == "0.2.1" and r["design_use"] is False
    assert r["properties"]["yield_strength"]["si_value"] == pytest.approx(882.5e6)


def test_search_matches_every_word_and_filters():
    assert [r["id"] for r in dp.search("titanium annealed")] == ["titanium-ti6al4v-annealed"]
    assert {r["category"] for r in dp.search("")} >= {"steel", "aluminium", "titanium", "water", "air"}
    assert {r["category"] for r in dp.search("", pack="fluids-water-air")} == {"water", "air"}
    assert [r["id"] for r in dp.search("", pack="materials-typical")] == ["steel-carbon-structural", "aluminium-6061-t6", "titanium-ti6al4v-annealed"]
    assert dp.search("steel", category="aluminium") == [] and dp.search("zzz") == []
    assert dp.search("6061", pack="nope") == []


@pytest.mark.parametrize("change, message", [
    (lambda d: d["records"][0]["properties"]["density"].update(unit="m"), "not a unit of density"),
    (lambda d: d["records"][0]["properties"]["density"].update(value=7.85), "plausible range"),          # g/cm3 typed as kg/m3
    (lambda d: d["records"][0]["properties"]["youngs_modulus"].update(unit="bogus"), "unit"),
    (lambda d: d["records"][0]["properties"]["density"].update(basis="guess"), "basis"),
    (lambda d: d["records"][0]["properties"]["density"].update(source="nowhere"), "not listed in the manifest"),
    (lambda d: d["records"][0]["properties"]["density"].update(low=8000, high=9000), "between low and high"),
    (lambda d: d["records"][0]["properties"]["density"].update(value=float("nan")), "finite"),
    (lambda d: d["records"][0]["properties"].update(strength_of_thought={"value": 1}), "unknown property"),
    (lambda d: d["records"][1].update(id=d["records"][0]["id"]), "duplicate record"),
    (lambda d: d["records"][0].update(properties={}), "at least one property"),
])
def test_bad_data_is_refused(pack_copy, change, message):
    _, edit = pack_copy
    pack, errs = edit(change)
    assert pack is None and any(message in e for e in errs), errs


def test_editing_without_sealing_is_caught(pack_copy):
    dst, edit = pack_copy
    pack, errs = edit(lambda d: d["records"][0].update(note="changed"), seal=False)
    assert pack is None and any("checksum" in e for e in errs)
    dp.seal(dst)
    assert dp.validate_pack(dst)[1] == []


def test_manifest_problems_are_reported(pack_copy):
    dst, _ = pack_copy
    m = json.loads((dst / "manifest.json").read_text())
    for key, bad, text in [("id", "a b", "manifest.id"), ("kind", "gases", "manifest.kind"), ("design_use", "no", "design_use"),
                           ("sources", [], "at least one source"), ("licence", "", "licence")]:
        (dst / "manifest.json").write_text(json.dumps({**m, key: bad}))
        assert any(text in e for e in dp.validate_pack(dst)[1]), key
    (dst / "data.json").write_text("{not json")
    assert dp.validate_pack(dst)[0] is None


def test_user_packs_load_and_a_bad_one_does_not_hide_the_good(tmp_path, monkeypatch):
    home = tmp_path / "home"
    good, bad = home / "datapacks" / "mine", home / "datapacks" / "broken"
    shutil.copytree(BUILTIN_PACK, good)
    m = json.loads((good / "manifest.json").read_text())
    (good / "manifest.json").write_text(json.dumps({**m, "id": "mine", "title": "My materials"}))
    shutil.copytree(BUILTIN_PACK, bad)
    (bad / "data.json").write_text('{"records": []}')
    monkeypatch.setenv("SLIDERULE_HOME", str(home))
    try:
        dp.reload()
        assert dp.packs()["mine"]["custom"] is True and dp.packs()["materials-typical"]["custom"] is False
        assert "user:broken" in dp.problems() and "materials-typical" in dp.packs()
        monkeypatch.undo()
        shutil.rmtree(home / "datapacks" / "mine")
        monkeypatch.setenv("SLIDERULE_HOME", str(home))
        shutil.copytree(BUILTIN_PACK, home / "datapacks" / "dup")                       # same id as the built-in pack
        dp.reload()
        assert any("already loaded" in e for errs in dp.problems().values() for e in errs)
    finally:
        monkeypatch.undo()
        dp.reload()


def test_api_and_http_expose_packs_search_and_records():
    meta = api.data_packs()
    assert {p["id"] for p in meta["packs"]} == {"fluids-water-air", "fluids-coolprop", "materials-typical", "nist-cryo"} and meta["refused"] == {}
    assert {(p["kind"], p["name"]) for p in meta["properties"]} == {(k, n) for k, voc in dp.VOCABULARIES.items() for n in voc}
    assert {p["id"]: p["records"] for p in client.get("/api/data").json()["packs"]} == {"fluids-water-air": 2, "fluids-coolprop": 59, "materials-typical": 3, "nist-cryo": 23}
    hits = client.get("/api/data/search", params={"q": "6061", "pack": "materials-typical"}).json()
    assert hits["count"] == 1 and hits["results"][0]["properties"]["density"]["source_ref"].startswith("R. F. Muraca")
    assert client.get("/api/data/search", params={"q": "6061"}).json()["count"] == 2                 # the NIST cryogenic record for 6061 aluminium too
    assert client.get("/api/data/materials-typical/aluminium-6061-t6").json()["name"].startswith("Aluminium")
    assert client.get("/api/data/materials-typical/nothing").status_code == 404
    out = json.loads(api.handle_json("data_record", json.dumps({"pack": "materials-typical", "record_id": "steel-carbon-structural"})))
    assert out["ok"] and out["result"]["properties"]["density"]["si_value"] == 7860


def test_cli_lists_shows_and_validates():
    run = lambda *a: subprocess.run([sys.executable, "-m", "sliderule.cli", "data", *a], capture_output=True, text=True,  # noqa: E731
                                    env={**__import__("os").environ, "PYTHONPATH": str(Path(dp.__file__).parents[2])})
    out = run("list")
    assert out.returncode == 0 and "materials-typical" in out.stdout and "fluids-water-air" in out.stdout and "[not for design]" in out.stdout
    assert "Ti-6Al-4V" in run("show", "materials-typical", "titanium-ti6al4v-annealed").stdout
    assert run("show", "materials-typical", "nothing").returncode == 2
    assert run("validate").returncode == 0


def test_web_bundle_and_package_data_include_the_datapacks(tmp_path):
    out = tmp_path / "site"
    root = Path(dp.__file__).parents[3]
    subprocess.run([sys.executable, str(root / "scripts" / "build_web.py"), "--out", str(out)], check=True, capture_output=True)
    names = zipfile.ZipFile(out / "sliderule_pkg.zip").namelist()
    assert "sliderule/datapacks/materials-typical/data.json" in names and "sliderule/datapacks/materials-typical/manifest.json" in names
    assert "datapacks/**/*" in (root / "pyproject.toml").read_text()


def test_the_shipped_materials_pack_equals_a_fresh_run_of_its_builder():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_materials_typical_pack", dp.BUILTIN.parents[2] / "scripts" / "build_materials_typical_pack.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    manifest, data = gen.build()
    shipped = dp.packs()["materials-typical"]
    assert [s["ref"] for s in shipped["manifest"]["sources"]] == [s["ref"] for s in manifest["sources"]]
    for a, b in zip(shipped["records"], data["records"]):
        assert a["id"] == b["id"] and {k: p["value"] for k, p in a["properties"].items()} == {k: p["value"] for k, p in b["properties"].items()}
