"""Solving one calculation over a range of one input."""

import time

import pytest
from fastapi.testclient import TestClient

from sliderule import api
from sliderule.server import create_app

client = TestClient(create_app())
BEAM = {"P": {"value": 5, "unit": "kN"}, "L": {"value": 2.5, "unit": "m"}, "E": {"value": 70, "unit": "GPa"}, "I": {"value": 2.4e6, "unit": "mm^4"}, "c": {"value": 60, "unit": "mm"}}


def test_sweep_matches_single_solves_and_the_cantilever_formula():
    xs = [1, 2, 3, 4, 5]
    r = api.sweep("civil.beam.cantilever_point", BEAM, "P", xs, ["delta"], {"delta": "mm"})
    assert r["ok"] and r["x"] == xs and r["x_unit"] == "kN" and r["failed"] == 0
    delta = next(s for s in r["series"] if s["key"] == "delta")
    assert delta["unit"] == "mm"
    for p, y in zip(xs, delta["y"]):
        assert y == pytest.approx(p * 1e3 * 2.5**3 / (3 * 70e9 * 2.4e6 * 1e-12) * 1e3, rel=1e-6)       # P L^3 / (3 E I), in mm
    one = api.solve("civil.beam.cantilever_point", {**BEAM, "P": {"value": 3, "unit": "kN"}}, ["delta"], {"delta": "mm"})
    assert delta["y"][2] == pytest.approx(one["outputs"][0]["value"], rel=1e-9)


def test_sweep_is_bounded_and_validates_input():
    with pytest.raises(api.ApiError):
        api.sweep("civil.beam.cantilever_point", BEAM, "P", [1], ["delta"])
    with pytest.raises(api.ApiError):
        api.sweep("civil.beam.cantilever_point", BEAM, "P", list(range(api.MAX_SWEEP + 1)), ["delta"])
    with pytest.raises(api.ApiError):
        api.sweep("civil.beam.cantilever_point", BEAM, "delta", [1, 2])                        # not one of the inputs
    with pytest.raises(api.ApiError):
        api.sweep("civil.beam.cantilever_point", BEAM, "P", [1, "x"])


def test_points_without_an_answer_are_gaps_and_http_agrees():
    r = api.sweep("civil.beam.cantilever_point", BEAM, "E", [-1, 0, 70], ["delta"])                 # a zero modulus is not allowed
    assert r["failed"] == 2 and r["series"][0]["y"][0] is None and r["series"][0]["y"][2] is not None
    http = client.post("/api/calculations/civil.beam.cantilever_point/sweep", json={"inputs": BEAM, "vary": "P", "values": [1, 2], "solve_for": ["delta"]}).json()
    assert http["ok"] and len(http["series"][0]["y"]) == 2
    assert api.handle("sweep", {"calc_id": "civil.beam.cantilever_point", "inputs": BEAM, "vary": "P", "values": [1, 2]})["ok"]


def test_a_sweep_of_sixty_points_is_quick():
    t = time.time()
    api.sweep("civil.beam.cantilever_point", BEAM, "P", [i + 1 for i in range(60)], ["delta"])
    assert time.time() - t < 15
