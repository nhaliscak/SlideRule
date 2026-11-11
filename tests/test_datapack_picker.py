"""The property picker's engine side: which datapack properties can fill which input, and that every offer can actually be fulfilled."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sliderule import api
from sliderule.core import datapack as dp
from sliderule.server import create_app


pytestmark = pytest.mark.usefixtures("no_user_packs")

client = TestClient(create_app(serve_frontend=False))
WEB = Path(dp.__file__).parents[1] / "web" / "js"


def opts(unit, label, key="x"):
    return api.data_options([{"key": key, "unit": unit, "label": label}])["options"][key]


def test_a_density_input_is_offered_every_density_best_matches_first():
    o = opts("kg/m^3", "Fluid density")
    assert {(r["record"], r["property"]) for r in o if r["pack"] != "fluids-coolprop"} == {("steel-carbon-structural", "density"), ("aluminium-6061-t6", "density"),
                                                         ("titanium-ti6al4v-annealed", "density"), ("water-liquid", "density"), ("air-dry", "density")}
    assert all(r["match"] for r in o)
    assert any(r["pack"] == "fluids-coolprop" for r in o)             # the CoolProp pack adds its fluids
    assert {r["curve"] for r in o} == {True, False}                  # materials are single values, fluids are curves


def test_units_do_not_have_to_be_the_stored_ones():
    assert {r["record"] for r in opts("g/cm^3", "Density")} == {r["record"] for r in opts("kg/m^3", "Density")}
    assert {r["property"] for r in opts("psi", "Elastic modulus") if r["match"]} == {"youngs_modulus"}


def test_a_pressure_input_gets_label_matches_first_and_other_pressure_like_properties_after():
    o = opts("kPa", "Vapour pressure")
    assert o[0]["property"] == "vapour_pressure" and o[0]["match"] is True
    assert {r["property"] for r in o if not r["match"]} >= {"youngs_modulus", "yield_strength"}
    y = opts("MPa", "Yield stress")
    assert y[0]["property"] == "yield_strength" and y[0]["match"]


def test_dimensionless_inputs_are_only_offered_a_property_the_label_names():
    assert opts("1", "Efficiency") == [] and opts("1", "Mach number") == []
    assert {r["property"] for r in opts("1", "Poisson's ratio")} == {"poisson_ratio"}


def test_inputs_with_no_matching_dimension_or_a_bad_unit_get_nothing():
    assert opts("m", "Length") == [] and opts("not-a-unit", "Density") == []


def test_every_offer_can_be_fulfilled_in_the_asked_unit():
    for unit, label in [("kg/m^3", "Density"), ("GPa", "Modulus"), ("MPa", "Yield"), ("Pa*s", "Viscosity"), ("W/(m*K)", "Conductivity"),
                        ("J/(kg*K)", "Specific heat"), ("1/K", "Expansion"), ("Pa", "Pressure"), ("1", "Poisson")]:
        for o in opts(unit, label):
            args = {"pack": o["pack"], "record_id": o["record"], "prop": o["property"], "unit": unit}
            if o["curve"]:
                r = o["range"]
                args.update(x=(r["min"] + r["max"]) / 2, x_unit=r["unit"])
            res = api.data_value(**args)
            assert res["unit"] and res["value"] > 0 and res["basis"] in dp.BASES


def test_bad_requests_are_refused():
    for bad in ("x", [1], [{"key": "a", "unit": "m"}] * 201):
        with pytest.raises(api.ApiError):
            api.data_options(bad)


def test_the_rpc_route_and_json_wrapper_serve_it():
    r = client.post("/api/rpc", json={"method": "data_options", "params": {"variables": [{"key": "mu", "unit": "mPa*s", "label": "Viscosity"}]}}).json()
    assert r["ok"] and [o["record"] for o in r["result"]["options"]["mu"] if o["pack"] == "fluids-water-air"] == ["air-dry", "water-liquid"]
    j = json.loads(api.handle_json("data_options", json.dumps({"variables": []})))
    assert j == {"ok": True, "result": {"options": {}}}


def test_the_front_end_has_the_picker_wired_in():
    app = (WEB / "app.js").read_text()
    assert 'from "./data-picker.js"' in app and "data_options" in app and "openDataPicker" in app and "provenanceText" in app
    picker = (WEB / "data-picker.js").read_text()
    assert "data_value" in picker and "not for design" in picker and "export function openDataPicker" in picker
    assert ".data-prov" in (WEB.parent / "css" / "style.css").read_text()
