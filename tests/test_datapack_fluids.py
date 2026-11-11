"""Water and air curves: computed from published correlations, checked against an independent reference table, and refused outside their range."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sliderule import api
from sliderule.core import datapack as dp
from sliderule.server import create_app

ROOT = Path(dp.__file__).parents[3]
PACK = dp.BUILTIN / "fluids-water-air"

pytestmark = pytest.mark.usefixtures("no_user_packs")

client = TestClient(create_app(serve_frontend=False))
spec = importlib.util.spec_from_file_location("build_fluid_pack", ROOT / "scripts" / "build_fluid_pack.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

# Rows of Cengel and Cimbala, Fluid Mechanics, 3rd ed. (2014): Table A-3 (saturated water) and Table A-9 (air at 1 atm), typed from the printed tables.
# water: T degC -> (Psat kPa, density kg/m3, cp J/kg K, k W/m K, viscosity Pa s); air: T degC -> (density, cp, k, viscosity)
W = {  # T degC: (Psat kPa, rho, cp, k, mu)
 0.01:(0.6113,999.8,4217,0.561,1.792e-3), 5:(0.8721,999.9,4205,0.571,1.519e-3), 10:(1.2276,999.7,4194,0.580,1.307e-3), 15:(1.7051,999.1,4186,0.589,1.138e-3),
 20:(2.339,998.0,4182,0.598,1.002e-3), 25:(3.169,997.0,4180,0.607,0.891e-3), 30:(4.246,996.0,4178,0.615,0.798e-3), 35:(5.628,994.0,4178,0.623,0.720e-3),
 40:(7.384,992.1,4179,0.631,0.653e-3), 45:(9.593,990.1,4180,0.637,0.596e-3), 50:(12.35,988.1,4181,0.644,0.547e-3), 55:(15.76,985.2,4183,0.649,0.504e-3),
 60:(19.94,983.3,4185,0.654,0.467e-3), 65:(25.03,980.4,4187,0.659,0.433e-3), 70:(31.19,977.5,4190,0.663,0.404e-3), 75:(38.58,974.7,4193,0.667,0.378e-3),
 80:(47.39,971.8,4197,0.670,0.355e-3), 85:(57.83,968.1,4201,0.673,0.333e-3), 90:(70.14,965.3,4206,0.675,0.315e-3), 95:(84.55,961.5,4212,0.677,0.297e-3),
 100:(101.33,957.9,4217,0.679,0.282e-3)}
A = {  # T degC: (rho, cp, k, mu)
 -50:(1.582,999,0.01979,1.474e-5), -40:(1.514,1002,0.02057,1.527e-5), -30:(1.451,1004,0.02134,1.579e-5), -20:(1.394,1005,0.02211,1.630e-5),
 -10:(1.341,1006,0.02288,1.680e-5), 0:(1.292,1006,0.02364,1.729e-5), 5:(1.269,1006,0.02401,1.754e-5), 10:(1.246,1006,0.02439,1.778e-5),
 15:(1.225,1007,0.02476,1.802e-5), 20:(1.204,1007,0.02514,1.825e-5), 25:(1.184,1007,0.02551,1.849e-5), 30:(1.164,1007,0.02588,1.872e-5),
 35:(1.145,1007,0.02625,1.895e-5), 40:(1.127,1007,0.02662,1.918e-5), 45:(1.109,1007,0.02699,1.941e-5), 50:(1.092,1007,0.02735,1.963e-5),
 60:(1.059,1007,0.02808,2.008e-5), 70:(1.028,1007,0.02881,2.052e-5), 80:(0.9994,1008,0.02953,2.096e-5), 90:(0.9718,1008,0.03024,2.139e-5),
 100:(0.9458,1009,0.03095,2.181e-5), 120:(0.8977,1011,0.03235,2.264e-5), 140:(0.8542,1013,0.03374,2.345e-5), 160:(0.8148,1016,0.03511,2.420e-5),
 180:(0.7788,1019,0.03646,2.504e-5), 200:(0.7459,1023,0.03779,2.577e-5), 250:(0.6746,1033,0.04104,2.760e-5), 300:(0.6158,1044,0.04418,2.934e-5),
 350:(0.5664,1056,0.04721,3.101e-5), 400:(0.5243,1069,0.05015,3.261e-5), 450:(0.4880,1081,0.05298,3.415e-5), 500:(0.4565,1093,0.05572,3.563e-5),
 600:(0.4042,1115,0.06093,3.846e-5), 700:(0.3627,1135,0.06581,4.111e-5), 800:(0.3289,1153,0.07037,4.362e-5), 900:(0.3008,1169,0.07465,4.600e-5),
 1000:(0.2772,1184,0.07868,4.826e-5)}

WATER_REF = {0.01, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100}          # temperatures used as reference points for the water cp and k curves
AIR_REF = {-50, 0, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000}


def val(rec, prop, T, unit=None):
    return dp.value("fluids-water-air", rec, prop, T, "degC", unit)["value"]


def worst(rec, prop, rows, idx, scale=1.0, skip=()):
    return max(abs(val(rec, prop, T) - row[idx] * scale) / (row[idx] * scale) for T, row in rows.items() if T not in skip)


CASES = [("water-liquid", "density", W, 1, 1.0, ()), ("water-liquid", "dynamic_viscosity", W, 4, 1.0, ()), ("water-liquid", "vapour_pressure", W, 0, 1000.0, ()),
         ("water-liquid", "specific_heat", W, 2, 1.0, WATER_REF), ("water-liquid", "thermal_conductivity", W, 3, 1.0, WATER_REF),
         ("air-dry", "density", A, 0, 1.0, ()), ("air-dry", "dynamic_viscosity", A, 3, 1.0, ()), ("air-dry", "thermal_conductivity", A, 2, 1.0, ()),
         ("air-dry", "specific_heat", A, 1, 1.0, AIR_REF)]


def test_pack_is_valid_and_not_for_design():
    pack, errs = dp.validate_pack(PACK)
    assert errs == [] and pack["manifest"]["kind"] == "fluids" and pack["manifest"]["design_use"] is False


@pytest.mark.parametrize("rec, prop, rows, idx, scale, skip", CASES)
def test_curves_agree_with_the_reference_table_within_the_stated_uncertainty(rec, prop, rows, idx, scale, skip):
    """Every table row the curve was NOT built from must agree within rel_uncertainty, and that stated figure must not be wildly loose."""
    stated = dp.record("fluids-water-air", rec)["properties"][prop]["rel_uncertainty"]
    measured = worst(rec, prop, rows, idx, scale, skip)
    assert measured <= stated, f"{rec}.{prop}: measured {measured:.4%} exceeds the stated {stated:.4%}"
    assert stated <= 3 * measured + 1e-4, f"{rec}.{prop}: stated {stated:.4%} is far looser than the measured {measured:.4%}"


def test_if97_saturation_pressure_matches_the_official_verification_points():
    """IAPWS-IF97 verification values for the region-4 equation (500 K also seen in a CoolProp example, 2638897.7562732203 Pa)."""
    for T, p_mpa in [(300.0, 0.353658941e-2), (500.0, 0.263889776e1), (600.0, 0.123443146e2)]:
        assert gen.if97_psat(T) == pytest.approx(p_mpa * 1e6, rel=1e-8)


def test_kell_density_matches_published_values():
    """g/cm3 at 0, 10, 20, 50 and 100 degC listed for 101.325 kPa (Saylor appendix F) and the 20 degC value 998.2 kg/m3."""
    for T, rho in [(0.01, 999.84), (10, 999.70), (20, 998.21), (50, 988.03), (100, 958.40)]:
        assert val("water-liquid", "density", T) == pytest.approx(rho, rel=1e-4)


def test_vogel_viscosity_matches_the_iapws_based_table():
    for T, mu_mpas in [(0.01, 1.787), (10, 1.307), (20, 1.002), (25, 0.890), (100, 0.2822)]:
        assert val("water-liquid", "dynamic_viscosity", T, "mPa*s") == pytest.approx(mu_mpas, rel=0.025)


def test_air_density_is_the_ideal_gas_value_and_falls_with_temperature():
    for T in (-50, 20, 300, 1000):
        assert val("air-dry", "density", T) == pytest.approx(101325 / (287.05 * (T + 273.15)), rel=2e-4)
    ds = [val("air-dry", "density", T) for T in range(-50, 1001, 50)]
    assert all(b < a for a, b in zip(ds, ds[1:]))


def test_water_density_peaks_near_four_degrees_and_viscosity_falls():
    rho = {t / 10: val("water-liquid", "density", t / 10) for t in range(1, 101)}
    assert 3.0 <= max(rho, key=rho.get) <= 5.0
    mu = [val("water-liquid", "dynamic_viscosity", T) for T in range(1, 101, 5)]
    assert all(b < a for a, b in zip(mu, mu[1:]))


def test_temperature_units_and_output_units_agree():
    a = dp.value("fluids-water-air", "water-liquid", "dynamic_viscosity", 293.15, "K")
    b = dp.value("fluids-water-air", "water-liquid", "dynamic_viscosity", 20, "degC")
    c = dp.value("fluids-water-air", "water-liquid", "dynamic_viscosity", 68, "degF")
    assert a["value"] == pytest.approx(b["value"], rel=1e-9) == pytest.approx(c["value"], rel=1e-9)
    m = dp.value("fluids-water-air", "water-liquid", "dynamic_viscosity", 20, "degC", "mPa*s")
    assert m["value"] == pytest.approx(a["value"] * 1000) and m["unit"] == "mPa*s" and m["basis"] == "computed" and m["at"] == {"pressure": "101.325 kPa"}


def test_no_answer_outside_the_stored_range_or_without_a_temperature():
    with pytest.raises(dp.DataPackError, match="outside the stored range"):
        dp.value("fluids-water-air", "water-liquid", "density", 120, "degC")
    with pytest.raises(dp.DataPackError, match="outside the stored range"):
        dp.value("fluids-water-air", "air-dry", "density", 100, "K")
    with pytest.raises(dp.DataPackError, match="depends on temperature"):
        dp.value("fluids-water-air", "air-dry", "density")
    with pytest.raises(dp.DataPackError, match="not a unit of"):
        dp.value("fluids-water-air", "air-dry", "density", 20, "degC", "Pa")
    with pytest.raises(dp.DataPackError, match="not a temperature unit"):
        dp.value("fluids-water-air", "air-dry", "density", 20, "m")
    with pytest.raises(dp.DataPackError, match="no property"):
        dp.value("fluids-water-air", "air-dry", "youngs_modulus", 20, "degC")


def test_scalar_properties_still_work_through_value():
    r = dp.value("materials-typical", "aluminium-6061-t6", "youngs_modulus", unit="Pa")
    assert r["value"] == pytest.approx(68.9e9) and r["design_use"] is False


def test_stored_pack_is_exactly_what_the_generator_produces():
    manifest, data = gen.build()
    stored_m = json.loads((PACK / "manifest.json").read_text())
    stored_m["checksum"] = ""
    assert stored_m == manifest
    assert json.loads((PACK / "data.json").read_text()) == json.loads(json.dumps(data))


@pytest.fixture
def edit(tmp_path):
    dst = tmp_path / "f"
    shutil.copytree(PACK, dst)

    def run(fn):
        d = json.loads((dst / "data.json").read_text())
        fn(d["records"][0]["properties"])
        (dst / "data.json").write_text(json.dumps(d))
        dp.seal(dst)
        return dp.validate_pack(dst)[1]
    return run


@pytest.mark.parametrize("change, message", [
    (lambda p: p["density"]["curve"].update(x=list(reversed(p["density"]["curve"]["x"]))), "increase"),
    (lambda p: p["density"]["curve"].update(x_unit="m"), "not a temperature unit"),
    (lambda p: p["density"]["curve"].update(method="loglog"), "curve.method"),
    (lambda p: p["density"].update(value=1000.0), "either a value or a curve"),
    (lambda p: p["density"]["curve"].update(y=p["density"]["curve"]["y"][:-1]), "same number of points"),
    (lambda p: p["density"]["curve"]["y"].__setitem__(3, 1.0e6), "plausible range"),
    (lambda p: p["density"]["curve"].update(x=[x + 6000 for x in p["density"]["curve"]["x"]]), "between 0 K and 6000 K"),
    (lambda p: p["density"].update(rel_uncertainty=1.5), "rel_uncertainty"),
    (lambda p: p["density"].update(at={"pressure": "101.325 m"}), "at.pressure"),
    (lambda p: p.update(youngs_modulus=dict(p["density"])), "unknown property for a fluids pack"),
])
def test_bad_curves_are_refused(edit, change, message):
    errs = edit(change)
    assert any(message in e for e in errs), errs


def test_api_http_and_cli_give_curve_values():
    r = api.handle("data_value", {"pack": "fluids-water-air", "record_id": "air-dry", "prop": "dynamic_viscosity", "x": 20, "x_unit": "degC"})
    assert r["ok"] and r["result"]["value"] == pytest.approx(1.82e-5, rel=0.02)
    j = client.get("/api/data/fluids-water-air/water-liquid/density", params={"x": 4, "x_unit": "degC"}).json()
    assert j["value"] == pytest.approx(999.97, rel=1e-4) and j["rel_uncertainty"] == 0.001
    bad = client.get("/api/data/fluids-water-air/water-liquid/density", params={"x": 130, "x_unit": "degC"})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "OUT_OF_RANGE"
    assert client.get("/api/data/fluids-water-air/nothing/density", params={"x": 20, "x_unit": "degC"}).status_code == 404
    rec = client.get("/api/data/fluids-water-air/water-liquid").json()
    assert rec["kind"] == "fluids" and rec["properties"]["density"]["range"] == {"min": 0.01, "max": 100.0, "unit": "degC"} and "si_value" not in rec["properties"]["density"]
    run = lambda *a: subprocess.run([sys.executable, "-m", "sliderule.cli", "data", *a], capture_output=True, text=True,  # noqa: E731
                                    env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})
    out = run("value", "fluids-water-air", "water-liquid", "dynamic_viscosity", "--at", "20", "--at-unit", "degC", "--unit", "mPa*s")
    assert out.returncode == 0 and out.stdout.startswith("1.00") and "computed" in out.stdout
    assert run("value", "fluids-water-air", "water-liquid", "density", "--at", "200", "--at-unit", "degC").returncode == 2
    assert "curve 0.01 to 100 degC" in run("show", "fluids-water-air", "water-liquid").stdout
