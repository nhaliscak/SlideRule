import math

import pytest

from sliderule import api, design_export, usercalcs
from sliderule.core import C, Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict
from sliderule.core.numeric_ode import EventSpec, rk45, solve_ivp, stiff

G = 9.80665


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


# ---------------------------------------------------------------- the solvers

def fall(t, y):
    return [y[1], -G]


def test_a_terminal_event_stops_exactly_at_the_crossing():
    r = rk45(fall, 0, [10.0, 5.0], 10, events=[EventSpec(lambda t, y: y[0], -1, True)])
    exact = (5 + math.sqrt(25 + 2 * G * 10)) / G
    assert r.stopped_by == 0 and r.ts[-1] == pytest.approx(exact, abs=1e-12) and r.ys[-1][0] == 0.0     # the crossing quantity reads zero
    assert r.ys[-1][1] == pytest.approx(-math.sqrt(25 + 2 * G * 10), rel=1e-10)


def test_non_terminal_events_are_recorded_in_order_and_integration_continues():
    r = rk45(fall, 0, [10.0, 5.0], 10, events=[EventSpec(lambda t, y: y[1], 0, False), EventSpec(lambda t, y: y[0], -1, True)])
    assert [h.index for h in r.events] == [0, 1] and r.events[0].t == pytest.approx(5 / G, abs=1e-10)
    assert r.events[0].y[0] == pytest.approx(10 + 25 / (2 * G), rel=1e-10)                              # apex height
    r2 = rk45(fall, 0, [10.0, 5.0], 1.0, events=[EventSpec(lambda t, y: y[1], 0, False)])
    assert r2.ts[-1] == 1.0 and len(r2.events) == 1 and r2.stopped_by is None


def test_direction_filters_and_events_that_are_already_true_at_the_start():
    assert rk45(fall, 0, [10.0, 5.0], 10, events=[EventSpec(lambda t, y: y[0], +1, True)]).events == []        # it only ever falls through zero
    assert rk45(fall, 0, [0.0, 5.0], 2.0, events=[EventSpec(lambda t, y: y[0], -1, True)]).stopped_by == 0    # starts at 0 rising; falls back through it
    r = rk45(lambda t, y: [-y[0]], 0, [1.0], 5, events=[EventSpec(lambda t, y: y[0] - 1.0, 0, True)])          # true at the start: not an event
    assert r.events == [] and r.ts[-1] == 5


def test_events_in_the_stiff_solver():
    f = lambda t, y: [-1000 * (y[0] - math.cos(t))]       # noqa: E731
    r = stiff(f, 0, [1.0], 10, events=[EventSpec(lambda t, y: y[0], -1, True)])
    assert r.stopped_by == 0 and r.ts[-1] == pytest.approx(math.pi / 2 + 0.001, abs=1e-4)             # the lag behind cos t is sin t / 1000
    r = solve_ivp(lambda t, y: [-y[0]], 0, [1.0], 5, events=[EventSpec(lambda t, y: y[0] - 0.5, -1, True)])
    assert r.ts[-1] == pytest.approx(math.log(2), abs=1e-8)


# ---------------------------------------------------------------- in a calculation

def ball(**changes):
    ev = {"title": "ground", "when": "h = 0", "direction": "falling", "terminal": True, "time": "th", "values": {"v": "vh"}}
    ev.update(changes.pop("event", {}))
    odes = [{"independent": "t", "equations": ["diff(h, t) = v", "diff(v, t) = -g"], "initial": ["h = h0", "v = v0"], "events": [ev], **changes}]
    return Calculation(id="custom.ball", name="b", disciplines=["mechanical"], description="", custom=True, equations=[], outputs=["h", "th", "vh"],
                       variables=[V("h", "Height", "m", signed=True), V("v", "Velocity", "m/s", signed=True), V("h0", "h0", "m"), V("v0", "v0", "m/s", signed=True),
                                  C("g", "g", G, "m/s^2"), V("t", "Horizon", "s"), V("th", "Impact time", "s"), V("vh", "Impact velocity", "m/s", signed=True)], odes=odes)


IN = {"h0": "10 m", "v0": "5 m/s", "t": "10 s"}


def vals(c, inputs=IN, solve_for=None, **kw):
    r = solve(c, inputs, solve_for, **kw).to_dict()
    assert r["ok"], r["diagnostics"]
    return {o["key"]: o["si_value"] for o in r["outputs"]}


def test_event_time_and_state_become_outputs():
    o = vals(ball())
    assert o["th"] == pytest.approx((5 + math.sqrt(25 + 2 * G * 10)) / G, rel=1e-10) and o["vh"] == pytest.approx(-math.sqrt(25 + 2 * G * 10), rel=1e-9)
    assert o["h"] == 0.0                    # quantities are reported at the event when it stops the integration first
    assert ball().parsed_odes[0].numeric and "events" in ball().parsed_odes[0].why_numeric


def test_no_event_before_the_horizon_is_a_clear_error():
    r = solve(ball(), {**IN, "t": "1 s"}).to_dict()
    assert not r["ok"] and "does not occur" in r["diagnostics"][0]["message"]


def test_a_non_terminal_event_only_marks_and_the_run_continues_to_t():
    c = ball(event={"title": "apex", "when": "v", "direction": "falling", "terminal": False})
    r = solve(c, {**IN, "t": "1 s"}, ["h", "th", "vh"], ode_times=["0.2 s"]).to_dict()
    assert r["ok"] and r["outputs"][0]["si_value"] == pytest.approx(10 + 5 - 0.5 * G, rel=1e-9)         # h(1 s), not stopped
    assert r["series"][0]["stopped_at_event"] is False and r["series"][0]["t"][-1] == pytest.approx(1.0)
    assert [e["title"] for e in r["series"][0]["events"]] == ["apex"] and r["series"][0]["events"][0]["t"] == pytest.approx(5 / G, rel=1e-9)


def test_plot_data_ends_at_a_terminal_event_and_says_so():
    s = solve(ball(), IN, ["h"], ode_times=["1 s", "5 s"])
    r = s.to_dict()
    ser = r["series"][0]
    exact = (5 + math.sqrt(25 + 2 * G * 10)) / G
    assert ser["stopped_at_event"] and ser["t"][-1] == pytest.approx(exact, rel=1e-10) and ser["events"][0]["values"]["h"] == 0.0
    assert [row["t"] for row in r["table"]] == ["1", "2.0262"] and r["table"][-1]["stopped_at_event"]
    assert any(d["code"] == "TIME_OUTSIDE" and "stops at an event" in d["message"] for d in r["diagnostics"])
    assert any("event ground: falling through zero; the integration stops here" in ln.note for st in s.steps["symbolic"] for ln in st.lines)


def test_event_outputs_can_be_inverted_by_root_finding():
    # which launch speed lands after exactly 2 s?  10 + 2 v0 - g*2 = 0
    r = solve(ball(), {"h0": "10 m", "th": "2 s", "t": "10 s"}, ["v0"]).to_dict()
    assert r["ok"] and r["outputs"][0]["si_value"] == pytest.approx((G * 2 ** 2 / 2 - 10) / 2, rel=1e-6) and "NUMERIC_INVERSION" in [d["code"] for d in r["diagnostics"]]


def test_event_definitions_are_validated():
    with pytest.raises(Exception, match="direction"):
        ball(event={"direction": "sideways"})
    with pytest.raises(Exception, match="not used for anything else"):
        ball(event={"time": "h"})                                       # h is a differentiated quantity
    with pytest.raises(Exception, match="has dimension"):
        ball(event={"time": "vh", "values": {}})                        # velocity cannot receive a time
    with pytest.raises(Exception, match="different dimensions"):
        ball(event={"when": "h = 5"})                                   # a literal 5 is dimensionless, h is a length
    with pytest.raises(Exception, match="not one of the differentiated"):
        ball(event={"values": {"zz": "vh"}})
    with pytest.raises(Exception, match="need numerical integration"):
        ball(method="symbolic")
    with pytest.raises(Exception, match="at most 3 events"):
        Calculation(id="custom.e", name="e", disciplines=["mechanical"], description="", custom=True, equations=[], outputs=["h"],
                    variables=[V("h", "h", "m", signed=True), V("h0", "h0", "m"), V("k", "k", "1/s"), V("t", "t", "s")],
                    odes=[{"independent": "t", "equations": ["diff(h, t) = -k*h"], "initial": ["h = h0"], "events": [{"when": "h"} for _ in range(4)]}])


def test_events_survive_the_file_format_and_exports():
    doc = calc_to_dict(ball())
    assert doc["odes"][0]["events"][0]["when"] == "h = 0" and doc["odes"][0]["events"][0]["values"] == {"v": "vh"}
    once = calc_to_dict(calc_from_dict({**doc, "id": "custom.ball2"}))
    assert calc_to_dict(calc_from_dict(once))["odes"] == once["odes"] and once["odes"][0]["events"] == doc["odes"][0]["events"]
    api.custom_save({**doc, "id": "custom.ball3"})
    g = {"version": 1, "blocks": [{"id": "b", "calc": "custom.ball3", "x": 0, "y": 0, "roles": {"v": "output"}, "values": dict(IN)}], "wires": []}
    for fmt in ("latex", "markdown", "html"):
        out = design_export.export_system(g, fmt)
        assert out["ok"] and "initial condition" in out["content"]
    py = design_export.export_system(g, "python")
    assert py["ok"]                                           # events are re-solved by the script (a terminal event stops the path)
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(py["content"], "s.py", "exec"), {"__name__": "__main__"})
    assert "matches the SlideRule reference values" in buf.getvalue()
    info = api.get_calculation("custom.ball3")["odes"][0]["events"][0]
    assert info["terminal"] and info["time"] == "th" and info["values"] == {"v": "vh"} and info["direction"] == "falling"


# ---------------------------------------------------------------- library calculations

def test_tank_drain_time_matches_torricelli():
    cid = "civil.hydraulics.tank_drain_time_to_level"
    ex = api.get_calculation(cid)["example"]
    r = api.solve(cid, dict(ex))
    exact = 2 * 2.0 / (20e-4 * math.sqrt(2 * G)) * (math.sqrt(3) - math.sqrt(0.5))
    assert r["outputs"][0]["si_value"] == pytest.approx(exact, rel=1e-8) and r["series"][0]["stopped_at_event"]


def test_projectile_with_drag_matches_an_independent_integration_and_the_drag_free_limit():
    cid = "mechanical.dynamics.projectile_with_drag_range"
    ex = api.get_calculation(cid)["example"]

    def out(inputs):
        r = api.solve(cid, inputs)
        assert not [d for d in r["diagnostics"] if d["level"] != "info"], r["diagnostics"]
        return {o["key"]: o["si_value"] for o in r["outputs"]}
    o = out(dict(ex))
    assert o["tf"] == pytest.approx(5.440829675882134, rel=1e-6) and o["R"] == pytest.approx(132.80569477925863, rel=1e-6) and o["vi"] == pytest.approx(-23.581427301157543, rel=1e-6)
    free = out({**ex, "cd": "1e-9 kg/m", "y0": "1e-9 m"})
    assert free["R"] == pytest.approx(50 ** 2 * math.sin(math.radians(80)) / G, rel=1e-5)
