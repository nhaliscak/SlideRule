"""Math blocks (add, subtract, multiply, divide) in System Design."""

import pytest

from sliderule import api, design, design_export

TURBINE = {"id": "b1", "calc": "energy.wind.turbine_power",
           "values": {"rho": "1.225 kg/m^3", "Dr": "100 m", "v": "10 m/s", "Cp": "0.45", "eg": "94 %", "CF": "35 %", "Pr": "3000 kW"}}
ELECTROLYZER = {"id": "b2", "calc": "energy.hydrogen.electrolyzer", "values": {"eta": "70 %", "t": "24 h"}}


def w(i, sb, sk, db, dk):
    return {"id": i, "from": {"block": sb, "key": sk}, "to": {"block": db, "key": dk}}


def math(bid, op, values=None, n=2):
    return {"id": bid, "kind": "math", "op": op, "n": n, "values": values or {}}


def graph(blocks, wires=()):
    return {"version": 1, "blocks": blocks, "wires": list(wires)}


def out(res, bid, key="y"):
    return next(o for o in res["blocks"][bid]["outputs"] if o["key"] == key)


def types(g, bid):
    return design.math_info(g)["blocks"][bid]


def test_add_block_locks_to_the_first_wire_and_adds_in_si():
    g = graph([TURBINE, math("m1", "add", {"x2": "500 kW"}), ELECTROLYZER], [w("w1", "b1", "Pe", "m1", "x1"), w("w2", "m1", "y", "b2", "P")])
    assert design.validate_graph(g) == []
    info = types(g, "m1")
    assert info["locked"] and {t["kind"] for t in info["types"].values()} == {"power"}
    r = design.solve_system(g)
    assert r["ok"], r["diagnostics"]
    pe = out(r, "b1", "Pe")["si_value"]
    assert out(r, "m1")["si_value"] == pytest.approx(pe + 500e3)                 # kW typed, W carried
    assert out(r, "b2", "mH")["si_value"] == pytest.approx(0.70 * (pe + 500e3) * 24 * 3600 / 141.8e6, rel=1e-9)


def test_the_lock_follows_the_earliest_wire_and_rejects_other_types():
    g = graph([TURBINE, math("m1", "add")], [w("w1", "b1", "Pe", "m1", "x1"), w("w2", "b1", "Ar", "m1", "x2")])
    assert "TYPE_MISMATCH" in [e["code"] for e in design.validate_graph(g)]      # area into a block locked to power
    swapped = graph([TURBINE, math("m1", "add")], [w("w2", "b1", "Ar", "m1", "x2"), w("w1", "b1", "Pe", "m1", "x1")])
    assert types(swapped, "m1")["types"]["y"]["kind"] == "area"                    # now the area wire is first


def test_the_lock_comes_from_a_wire_on_the_output_side_too_and_releases_when_unwired():
    g = graph([TURBINE, math("m1", "sub"), ELECTROLYZER], [w("w1", "m1", "y", "b2", "P")])
    assert types(g, "m1")["locked"] and types(g, "m1")["types"]["x1"]["kind"] == "power"
    released = graph([TURBINE, math("m1", "sub"), ELECTROLYZER], [])
    info = types(released, "m1")
    assert not info["locked"] and all(t is None for t in info["types"].values())


def test_one_of_two_wires_removed_keeps_the_lock_and_the_last_removal_releases_it():
    both = graph([TURBINE, math("m1", "add"), ELECTROLYZER], [w("w1", "b1", "Pe", "m1", "x1"), w("w2", "m1", "y", "b2", "P")])
    only_out = graph(both["blocks"], [both["wires"][1]])
    assert types(only_out, "m1")["locked"]
    assert not types(graph(both["blocks"], []), "m1")["locked"]


def test_subtract_is_ordered_and_adding_unlike_typed_values_is_reported():
    g = graph([math("m", "sub", {"x1": "10 m", "x2": "3 m"})])
    assert out(design.solve_system(g), "m")["si_value"] == pytest.approx(7)
    bad = graph([math("m", "add", {"x1": "10 m", "x2": "3 s"})])
    r = design.solve_system(bad)
    assert not r["ok"] and any(d["block"] == "m" for d in r["diagnostics"])


def test_multiply_combines_and_divide_cancels_units():
    g = graph([math("m", "mul", {"x1": "5 N", "x2": "2 m"})])
    o = out(design.solve_system(g), "m")
    assert o["si_value"] == pytest.approx(10) and o["si_unit"] == "J"
    assert types(g, "m")["types"]["y"]["kind"] == "energy"
    d = graph([math("m", "div", {"x1": "5 N", "x2": "2 N"})])
    o = out(design.solve_system(d), "m")
    assert o["si_value"] == pytest.approx(2.5) and o["si_unit"] == "1"
    v = graph([math("m", "div", {"x1": "100 m", "x2": "4 s"})])
    assert types(v, "m")["types"]["y"]["kind"] == "velocity" and out(design.solve_system(v), "m")["si_value"] == pytest.approx(25)


def test_multiply_takes_the_input_types_from_its_wires_and_feeds_a_typed_port():
    g = graph([TURBINE, math("m", "mul", {"x2": "2"}), ELECTROLYZER], [w("w1", "b1", "Pe", "m", "x1"), w("w2", "m", "y", "b2", "P")])
    assert design.validate_graph(g) == [] and types(g, "m")["types"]["y"]["kind"] == "power"
    # power x time is energy, which the electrolyzer's power input must refuse
    wrong = graph([TURBINE, math("m", "mul", {"x2": "3 s"}), ELECTROLYZER], [w("w1", "b1", "Pe", "m", "x1"), w("w2", "m", "y", "b2", "P")])
    assert "TYPE_MISMATCH" in [e["code"] for e in design.validate_graph(wrong)]
    assert types(wrong, "m")["types"]["y"]["kind"] == "energy"


def test_math_blocks_chain_and_pass_their_type_along():
    g = graph([TURBINE, math("a", "add", {"x2": "1 MW"}), math("b", "sub", {"x2": "1 MW"}), ELECTROLYZER],
              [w("w1", "b1", "Pe", "a", "x1"), w("w2", "a", "y", "b", "x1"), w("w3", "b", "y", "b2", "P")])
    assert design.validate_graph(g) == []
    r = design.solve_system(g)
    assert r["ok"] and out(r, "b", "y")["si_value"] == pytest.approx(out(r, "b1", "Pe")["si_value"])


def test_more_inputs_and_unknown_operations():
    g = graph([math("m", "add", {"x1": "1 m", "x2": "2 m", "x3": "3 m", "x4": "4 m"}, n=4)])
    assert out(design.solve_system(g), "m")["si_value"] == pytest.approx(10)
    assert len(types(g, "m")["detail"]["variables"]) == 5
    assert "UNKNOWN_CALC" in [e["code"] for e in design.validate_graph(graph([math("m", "pow")]))]


def test_math_blocks_use_the_normal_rpc_and_export_in_every_format():
    g = graph([TURBINE, math("m", "add", {"x2": "500 kW"}), ELECTROLYZER], [w("w1", "b1", "Pe", "m", "x1"), w("w2", "m", "y", "b2", "P")])
    assert api.handle("design_math", {"graph": g})["result"]["blocks"]["m"]["locked"]
    for fmt in ("latex", "markdown", "html", "python"):
        res = design_export.export_system(g, fmt, "both", 5, True)
        assert res["ok"], (fmt, res.get("diagnostics"))
    assert "Add" in design_export.export_system(g, "markdown", "both", 5, True)["content"]
