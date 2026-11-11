import math

import pytest

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import CustomError, calc_from_dict, calc_to_dict
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def vals(sol):
    return {o["key"]: o["si_value"] for o in sol.to_dict()["outputs"]}


def run(cid, targets=None):
    c = _ALL[cid]
    return vals(solve(c, c.example, targets or c.outputs))


def test_cross_dot_and_norm():
    m = run("mechanical.statics.moment_of_force_cross_product")
    assert (m["M_1"], m["M_2"], m["M_3"]) == pytest.approx((2 * 6 - 3 * 5, 3 * 4 - 1 * 6, 1 * 5 - 2 * 4))
    assert run("mechanical.dynamics.work_of_constant_force_dot_product")["W"] == pytest.approx(10 * 3 - 5 * 4 + 2 * 1)
    r = run("mechanical.statics.concurrent_forces_resultant_3d")
    assert r["Rmag"] == pytest.approx(math.sqrt(130**2 + 10**2 + 60**2))
    f1, f2 = (100, 50, -20), (30, -40, 80)
    cos = sum(a * b for a, b in zip(f1, f2)) / (math.hypot(*f1) * math.hypot(*f2))
    assert r["theta"] == pytest.approx(math.acos(cos), rel=1e-9)      # SI value: radians


def test_matrix_equation_solves_both_ways():
    c = _ALL["mechanical.vibration.two_spring_chain_static_deflection"]
    assert [e.title for e in c.parsed] == ["Equilibrium K u = f [1]", "Equilibrium K u = f [2]"]
    u = vals(solve(c, c.example, ["u_1", "u_2"]))
    assert (u["u_1"], u["u_2"]) == pytest.approx((0.05, 0.15))
    k = {k: v for k, v in c.example.items() if k.startswith("K_")}
    f = vals(solve(c, {**k, "u_1": "50 mm", "u_2": "150 mm"}, ["f_1", "f_2"]))
    assert (f["f_1"], f["f_2"]) == pytest.approx((0, 10), abs=1e-9)


def test_outputs_may_name_a_whole_vector_and_labels_are_numbered():
    c = _ALL["mechanical.statics.moment_of_force_cross_product"]
    assert c.outputs == ["M_1", "M_2", "M_3"]
    assert c.by_key["r_2"].label == "Position vector [2]" and c.by_key["K_1_2" if "K_1_2" in c.by_key else "r_2"]
    assert [v.key for v in c.declared] == ["r", "F", "M"]


def test_shape_errors_and_dimension_checks():
    def mk(vs, eq):
        return Calculation(id="custom.v", name="v", disciplines=["mechanical"], description="", custom=True, variables=vs, equations=eq, outputs=[vs[-1].key])
    a, b = V("a", "a", "m", shape=(3,), signed=True), V("b", "b", "m", shape=(2,), signed=True)
    with pytest.raises(ValueError, match="same shape"):
        mk([a, b], ["b = a"])
    with pytest.raises(ValueError, match="dimension"):
        mk([a, V("c", "c", "s", shape=(3,), signed=True)], ["c = a"])
    with pytest.raises(ValueError, match="1 to 6"):
        mk([V("z", "z", "m", shape=(9,))], ["z = z"])


def test_vectors_round_trip_through_the_custom_format():
    c = _ALL["mechanical.statics.moment_of_force_cross_product"]
    doc = calc_to_dict(c)
    assert doc["variables"][0]["shape"] == [3] and doc["variables"][0]["example"] == ["1 m", "2 m", "3 m"]
    assert len(doc["equations"]) == 1 and doc["equations"][0]["text"] == "M = cross(r, F)"
    back = calc_from_dict({**doc, "id": "custom.cross"})
    assert back.example == c.example and [v.key for v in back.variables] == [v.key for v in c.variables]
    assert vals(solve(back, back.example, back.outputs)) == pytest.approx(vals(solve(c, c.example, c.outputs)))
    with pytest.raises(CustomError):
        calc_from_dict({**doc, "id": "custom.bad", "variables": [{**doc["variables"][0], "shape": [0]}, *doc["variables"][1:]]})
