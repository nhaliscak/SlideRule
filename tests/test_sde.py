import math

import pytest
from scipy.stats import norm

from sliderule import usercalcs
from sliderule.core import Calculation, V, solve
from sliderule.core.custom import calc_from_dict, calc_to_dict
from sliderule.library import all_calculations

_ALL = {c.id: c for c in all_calculations()}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def run(c, given, keys):
    s = solve(c, given, keys)
    assert s.ok, [d.message for d in s.diagnostics]
    return {o["key"]: o["si_value"] for o in s.to_dict()["outputs"]}, s


def ou(extra=None, paths=20000):
    return Calculation(id="custom.ou", name="o", disciplines=["mechanical"], description="", custom=True, outputs=["xm", "xs"], equations=[],
                       variables=[V("x", "x", "m", signed=True), V("t", "t", "s"), V("th", "th", "1/s"), V("mu", "mu", "m", signed=True), V("sg", "sg", "m/s^0.5"), V("x0", "x0", "m", signed=True),
                                  V("xm", "xm", "m", signed=True), V("xs", "xs", "m"), V("pe", "pe", "1"), V("xc", "xc", "m", signed=True), V("x95", "x95", "m", signed=True)],
                       odes=[{"independent": "t", "start": "0", "equations": ["diff(x, t) = -th*(x - mu) + sg*xi1"], "initial": ["x = x0"], "paths": paths,
                              "statistics": [{"of": "x", "kind": "mean", "var": "xm"}, {"of": "x", "kind": "std", "var": "xs"},
                                             {"of": "x", "kind": "above", "level": "xc", "var": "pe"}, {"of": "x", "kind": "quantile", "p": "0.95", "var": "x95"}], **(extra or {})}])


G = {"th": "0.5 1/s", "mu": "2 m", "sg": "0.8 m/s^0.5", "x0": "0 m", "xc": "3 m", "t": "3 s"}


def test_ornstein_uhlenbeck_statistics_agree_with_theory_within_their_errors():
    c = ou()
    v, s = run(c, G, ["xm", "xs", "pe", "x95"])
    th, mu, sg, t = 0.5, 2.0, 0.8, 3.0
    mean = mu * (1 - math.exp(-th * t))
    sd = math.sqrt(sg**2 / (2 * th) * (1 - math.exp(-2 * th * t)))
    assert v["xm"] == pytest.approx(mean, abs=4 * sd / math.sqrt(20000) + 5e-3)
    assert v["xs"] == pytest.approx(sd, rel=0.03)
    assert v["pe"] == pytest.approx(1 - norm.cdf((3 - mean) / sd), abs=0.004)
    assert v["x95"] == pytest.approx(mean + 1.6449 * sd, abs=0.06)
    assert any("sampling" in d.message for d in s.diagnostics if d.code == "MONTE_CARLO")
    assert any("mean" in q["series"][0]["label"] for q in s.to_dict()["series"])


def test_results_are_reproducible_and_the_seed_matters():
    a = run(ou(), G, ["xm"])[0]["xm"]
    assert run(ou(), G, ["xm"])[0]["xm"] == a
    assert run(ou({"seed": 7}), G, ["xm"])[0]["xm"] != a


def test_state_dependent_noise_geometric_brownian_motion():
    c = Calculation(id="custom.gbm", name="g", disciplines=["industrial"], description="", custom=True, outputs=["m"], equations=[],
                    variables=[V("S", "S", "1"), V("t", "t", "s"), V("mu", "mu", "1/s"), V("sg", "sg", "1/s^0.5"), V("S0", "S0", "1"), V("m", "m", "1")],
                    odes=[{"independent": "t", "start": "0", "equations": ["diff(S, t) = mu*S + sg*S*xi1"], "initial": ["S = S0"], "paths": 40000, "steps": 800,
                           "statistics": [{"of": "S", "kind": "mean", "var": "m"}]}])
    v, _ = run(c, {"mu": "0.2 1/s", "sg": "0.3 1/s^0.5", "S0": "1", "t": "2 s"}, ["m"])
    sd = math.sqrt((math.exp(0.09 * 2) - 1)) * math.exp(0.2 * 2)          # std of S_T
    assert v["m"] == pytest.approx(math.exp(0.4), abs=4 * sd / math.sqrt(40000) + 5e-3)         # E[S_T] = S0 e^{mu T}


def test_library_calc_validation_and_round_trip():
    c = _ALL["mechanical.hvac.room_temperature_noise_statistics"]
    v, _ = run(c, c.example, c.outputs)
    tau, t, sg = 1200.0, 3600.0, 0.02
    assert v["Tmean"] == pytest.approx(295.15 - math.exp(-t / tau), abs=0.02)
    assert v["Tstd"] == pytest.approx(math.sqrt(sg**2 * tau / 2 * (1 - math.exp(-2 * t / tau))), rel=0.03)
    back = calc_from_dict({**calc_to_dict(c), "id": "custom.rt"})
    assert run(back, back.example, ["Tmean"])[0]["Tmean"] == v["Tmean"]
    with pytest.raises(ValueError, match="dimension"):
        Calculation(id="custom.bad", name="b", disciplines=["mechanical"], description="", custom=True, outputs=["xm"], equations=[],
                    variables=[V("x", "x", "m", signed=True), V("t", "t", "s"), V("sg", "sg", "m/s"), V("x0", "x0", "m", signed=True), V("xm", "xm", "m", signed=True)],
                    odes=[{"independent": "t", "start": "0", "equations": ["diff(x, t) = sg*xi1"], "initial": ["x = x0"], "statistics": [{"of": "x", "kind": "mean", "var": "xm"}]}])
    with pytest.raises(ValueError, match="no white noise"):
        Calculation(id="custom.bad2", name="b", disciplines=["mechanical"], description="", custom=True, outputs=["xm"], equations=[],
                    variables=[V("x", "x", "m", signed=True), V("t", "t", "s"), V("k", "k", "m/s"), V("x0", "x0", "m", signed=True), V("xm", "xm", "m", signed=True)],
                    odes=[{"independent": "t", "start": "0", "equations": ["diff(x, t) = k + 0*xi1"], "initial": ["x = x0"], "statistics": [{"of": "x", "kind": "mean", "var": "xm"}]}])


def barrier(mu_unit="m/s", extra_stats=None, event=None, equation="diff(x, t) = mu + sg*xi1"):
    used = {q["var"] for q in (extra_stats or [{"var": "pf"}])}
    units = {"pf": "1", "tm": "s", "tq": "s", "nh": "1"}
    return Calculation(id="custom.fp", name="f", disciplines=["mechanical"], description="", custom=True, outputs=sorted(used), equations=[],
                       variables=[V("x", "x", "m", signed=True), V("t", "t", "s"), V("mu", "mu", mu_unit, signed=True), V("sg", "sg", "m/s^0.5"), V("b", "b", "m"), *[V(n, n, units[n]) for n in sorted(used)]],
                       odes=[{"independent": "t", "start": "0", "equations": [equation], "initial": ["x = 0*mu*t"], "paths": 40000, "steps": 400,
                              "events": [event or {"title": "failure", "when": "x = b", "terminal": True}],
                              "statistics": extra_stats or [{"event": "failure", "kind": "hit_probability", "var": "pf"}]}])


def test_first_passage_probability_of_brownian_motion_matches_the_reflection_formula():
    c = barrier()
    g = {"mu": "0 m/s", "sg": "1 m/s^0.5", "b": "1 m", "t": "1 s"}
    got, s = run(c, g, ["pf"])
    exact = 2 * (1 - norm.cdf(1.0))                                         # P(max W_t >= b) = 2 (1 - Phi(b / sqrt(t)))
    assert got["pf"] == pytest.approx(exact, abs=0.012)                      # the Brownian-bridge correction removes the discrete-monitoring bias (~0.06 without it)
    d = {"mu": "0.5 m/s", "sg": "1 m/s^0.5", "b": "1 m", "t": "2 s"}
    got, _ = run(c, d, ["pf"])
    mu, sg, bb, T = 0.5, 1.0, 1.0, 2.0
    exact = norm.cdf((mu * T - bb) / (sg * math.sqrt(T))) + math.exp(2 * mu * bb / sg**2) * norm.cdf((-bb - mu * T) / (sg * math.sqrt(T)))
    assert got["pf"] == pytest.approx(exact, abs=0.012)


def test_hit_time_quantile_and_directions():
    stats = [{"event": "failure", "kind": "hit_probability", "var": "pf"}, {"event": 1, "kind": "hit_time_quantile", "p": "0.5", "var": "tq"}]
    c = barrier(extra_stats=stats)
    g = {"mu": "0 m/s", "sg": "1 m/s^0.5", "b": "1 m", "t": "2 s"}
    got, _ = run(c, g, ["pf", "tq"])
    F = lambda x: 2 * (1 - norm.cdf(1.0 / math.sqrt(x)))                     # noqa: E731  first-passage distribution function
    tq = got["tq"]
    assert F(tq) == pytest.approx(0.5 * F(2.0), abs=0.02)                    # the median of the hit time among the paths that hit
    down = barrier(event={"title": "failure", "when": "x = b", "direction": "falling", "terminal": True})
    got, _ = run(down, {"mu": "0.5 m/s", "sg": "0.1 m/s^0.5", "b": "1 m", "t": "1 s"}, ["pf"])
    assert got["pf"] == 0.0                                                  # a path that has not yet reached the barrier cannot cross it downwards
    up = barrier(event={"title": "failure", "when": "x = b", "direction": "rising", "terminal": True})
    assert run(up, {"mu": "1 m/s", "sg": "0.1 m/s^0.5", "b": "1 m", "t": "1.5 s"}, ["pf"])[0]["pf"] > 0.99          # drifting up through the barrier at t = 1


def test_reset_events_count_renewals():
    stats = [{"event": "failure", "kind": "hit_count_mean", "var": "nh"}]
    c = barrier(extra_stats=stats, event={"title": "failure", "when": "x = b", "reset": {"x": "0*b"}})
    got, _ = run(c, {"mu": "1 m/s", "sg": "0.05 m/s^0.5", "b": "1 m", "t": "40.5 s"}, ["nh"])
    assert got["nh"] == pytest.approx(40.0, abs=0.3)                         # one hit per second, state restarted each time


def test_event_validation_and_round_trip():
    with pytest.raises(ValueError, match="event"):
        barrier(extra_stats=[{"event": "nope", "kind": "hit_probability", "var": "pf"}])
    with pytest.raises(ValueError, match="terminal"):
        barrier(event={"title": "failure", "when": "x = b", "terminal": True, "reset": {"x": "0*b"}})
    with pytest.raises(ValueError, match="dimension"):
        barrier(event={"title": "failure", "when": "x = t", "terminal": True})
    c = barrier()
    back = calc_from_dict({**calc_to_dict(c), "id": "custom.rt"})
    g = {"mu": "0 m/s", "sg": "1 m/s^0.5", "b": "1 m", "t": "1 s"}
    assert run(back, g, ["pf"])[0]["pf"] == run(c, g, ["pf"])[0]["pf"]
    with pytest.raises(Exception, match="no path"):
        s = solve(barrier(extra_stats=[{"event": "failure", "kind": "hit_time_mean", "var": "tm"}]), {"mu": "0 m/s", "sg": "0.001 m/s^0.5", "b": "100 m", "t": "1 s"}, ["tm"])
        assert not s.ok
        raise Exception(" ".join(d.message for d in s.diagnostics))
