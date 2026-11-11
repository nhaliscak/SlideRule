"""The CoolProp pack: valid, spot-checked against textbook values taken from widely published tables, and equal to a fresh CoolProp evaluation."""

import importlib.util
from pathlib import Path

import pytest

from sliderule.core import datapack as dp

ROOT = Path(dp.__file__).parents[3]
PACK = dp.BUILTIN / "fluids-coolprop"

pytestmark = pytest.mark.usefixtures("no_user_packs")


def value(record: str, prop: str, T_K: float) -> float:
    return dp.value("fluids-coolprop", record, prop, x=T_K, x_unit="K")["value"]


def test_pack_is_valid_and_not_for_design():
    pack, errs = dp.validate_pack(PACK)
    assert pack is not None, errs
    assert pack["manifest"]["design_use"] is False
    assert len(pack["records"]) >= 55
    assert {r["category"] for r in pack["records"]} >= {"water", "gas", "hydrocarbon", "refrigerant", "solvent"}


@pytest.mark.parametrize("record, prop, T, want, rel", [
    ("water-liquid", "density", 293.15, 998.2, 0.002),              # 20 degC, any steam table
    ("water-liquid", "dynamic_viscosity", 293.15, 1.002e-3, 0.01),
    ("water-liquid", "thermal_conductivity", 293.15, 0.598, 0.01),
    ("water-liquid", "specific_heat", 293.15, 4182.0, 0.005),
    ("water-liquid", "vapour_pressure", 373.0, 101.0e3, 0.01),      # boils near 100 degC
    ("air-gas", "density", 300.0, 1.177, 0.005),                    # 1 atm, 300 K
    ("air-gas", "dynamic_viscosity", 300.0, 1.846e-5, 0.01),
    ("air-gas", "thermal_conductivity", 300.0, 0.0263, 0.02),
    ("air-gas", "specific_heat", 300.0, 1007.0, 0.005),
    ("nitrogen-liquid", "density", 77.35, 807.0, 0.005),            # normal boiling point
    ("methane-liquid", "density", 111.6, 422.4, 0.01),
    ("helium-gas", "specific_heat", 300.0, 5193.0, 0.002),
])
def test_values_match_published_figures(record, prop, T, want, rel):
    assert value(record, prop, T) == pytest.approx(want, rel=rel)


def test_curves_refuse_to_extrapolate():
    with pytest.raises(dp.DataPackError):
        value("nitrogen-liquid", "density", 300.0)


def test_pack_equals_a_fresh_coolprop_run():
    pytest.importorskip("CoolProp")
    spec = importlib.util.spec_from_file_location("build_coolprop_pack", ROOT / "scripts" / "build_coolprop_pack.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    manifest, data = gen.build()
    shipped = dp.validate_pack(PACK)[0]["records"]
    assert [r["id"] for r in shipped] == [r["id"] for r in data["records"]]
    for a, b in zip(shipped, data["records"]):
        for prop in b["properties"]:
            ya, yb = a["properties"][prop]["curve"]["y"], b["properties"][prop]["curve"]["y"]
            assert ya == pytest.approx(yb, rel=1e-3), (a["id"], prop)
