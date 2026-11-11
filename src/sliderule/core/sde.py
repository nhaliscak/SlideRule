"""Stochastic differential equations: Monte Carlo statistics of the solution (mean, spread, exceedance probability, quantiles).

An ``odes`` entry with white-noise terms ``xi1``, ``xi2``, ``xi3`` (independent, unit-intensity white noises; Ito interpretation) is a stochastic differential equation::

    {"title": "Ornstein-Uhlenbeck", "independent": "t", "start": "0",
     "equations": ["diff(x, t) = -theta*(x - mu) + sigma*xi1"], "initial": ["x = x0"],
     "statistics": [{"of": "x", "kind": "mean", "var": "xm"}, {"of": "x", "kind": "std", "var": "xs"},
                    {"of": "x", "kind": "above", "level": "xc", "var": "pexc"}, {"of": "x", "kind": "quantile", "p": "0.95", "var": "x95"}]}

Events act on each simulated path (``"events": [{"title": "failure", "when": "x = xc", "direction": "rising", "terminal": true}]``): a *terminal* event absorbs the
path where its condition crosses zero (a barrier, a failure limit, a first-passage problem), a ``reset`` event makes the state jump (``"reset": {"x": "x0"}``: a
renewal or restart) and any event can be counted. Crossings between two time steps are detected with the Brownian-bridge probability
``exp(-2 g0 g1 / (sigma_g^2 dt))``, which removes most of the bias that checking only at the steps would give. Event statistics (``"event": "failure"`` or its number,
``kind``: ``hit_probability``, ``hit_time_mean``, ``hit_time_std``, ``hit_time_quantile`` with ``p``, ``hit_count_mean``) report the fraction of paths that reached the event,
the statistics of the time they did so (among those paths), and the mean number of occurrences; the ordinary statistics of an absorbed path use the state where it was stopped.

The solution at a given time is a random variable, so the outputs are statistics of it, each delivered to the variable named in ``var``. ``xi`` has the dimension
``time^-1/2``, so a noise coefficient has the dimension ``[x]/[time]^(1/2)``. ``kind`` is ``mean``, ``std``, ``above`` (the probability that the quantity exceeds
``level``), ``below`` or ``quantile`` (the value that a fraction ``p`` of the paths stays below).

Numerics: Euler-Maruyama on ``steps`` time steps for ``paths`` independent paths, with a *fixed seed* (default 12345) so that the same inputs always give the same
numbers. The estimates carry two errors that are reported next to the result: the Monte Carlo sampling error (about 1/sqrt(paths) of the spread) and the
time-discretisation error, from the same Brownian paths integrated with half the steps. Increase ``paths`` to shrink the first and ``steps`` the second.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import sympy as sp

from .dimcheck import DIMENSIONLESS, DimensionError, analyze
from .numeric_ode import OdeError
from .special import fast_lambdify

NOISES = ("xi1", "xi2", "xi3")
DEFAULT_PATHS, MAX_PATHS = 20000, 200000
DEFAULT_STEPS, MAX_STEPS = 400, 20000
KINDS = ("mean", "std", "above", "below", "quantile")
EVENT_KINDS = ("hit_probability", "hit_time_mean", "hit_time_std", "hit_time_quantile", "hit_count_mean")
MAX_EVENTS = 3
SNAPSHOTS = 60


@dataclass
class SdeResult:
    times: list
    mean: np.ndarray                  # (snapshots, m)
    std: np.ndarray
    sample: np.ndarray                # (snapshots, m, n_sample) a few sample paths
    stats: list                       # per statistic: (value, sampling error, discretisation difference)
    notes: list
    steps: int
    paths: int


@dataclass
class SdeEvent:
    """A condition ``g(t, x) = 0`` that is watched on every path: absorbing (terminal), a jump of the state (reset) or just counted."""
    title: str
    g: sp.Expr
    direction: str                    # "either" | "rising" | "falling"
    terminal: bool
    reset: dict                       # state symbol -> expression it jumps to
    written: tuple


@dataclass
class SdeSystem:
    title: str
    texts: list[str]
    t: sp.Symbol
    start: sp.Expr
    dependents: list
    state: list
    drift: list
    diffusion: list                   # per equation, a list of coefficients (one per noise used)
    noises: list                      # the noise symbols in use
    ics: list
    statistics: list                  # (kind, dependent index, target variable symbol, level expr or None, p expr or None)
    written: list
    params: list
    inputs: list
    paths: int = DEFAULT_PATHS
    steps: int = DEFAULT_STEPS
    seed: int = 12345
    why_numeric: str = "the solution of a stochastic differential equation is random: its statistics are estimated by Monte Carlo (Euler-Maruyama, fixed seed)"
    method: str = "numeric"
    closed: None = None
    events: list = field(default_factory=list)
    bvp: None = None
    pre: dict = field(default_factory=dict)
    aux_count: int = 0
    fns: dict = field(default_factory=dict)
    fallback: dict = field(default_factory=dict)
    lag_syms: list = field(default_factory=list)
    hidden: set = field(default_factory=set)
    sde_events: list = field(default_factory=list)
    _cache: dict = field(default_factory=dict, repr=False)

    numeric = True
    pde = False
    stochastic = True

    @property
    def state_index(self) -> dict:
        return {(d, 0): i for i, d in enumerate(self.dependents)}

    @property
    def initial_texts(self) -> list[str]:
        return [f"{d.name} = {sp.sstr(e)}" for d, e in zip(self.dependents, self.ics)]

    @property
    def condition_note(self) -> str:
        return "initial condition"

    def last_result(self):
        return None

    def event_latex(self, names: dict) -> list:
        return []

    def written_latex(self, names: dict) -> list[str]:
        return [f"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)}" for a, b in self.written]

    def condition_latex(self, names: dict) -> list[str]:
        ev = []
        for e in self.sde_events:
            a, b = e.written
            what = "absorbs the path" if e.terminal else ("resets " + ", ".join(sp.latex(k, symbol_names=names) for k in e.reset) if e.reset else "is counted")
            ev.append(rf"\text{{event '{e.title}': }} {sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)} \quad \text{{({e.direction}; {what})}}")
        return [rf"{names.get(d, str(d))}\left({sp.latex(self.start, symbol_names=names)}\right) = {sp.latex(e, symbol_names=names)} \quad \text{{(initial value)}}" for d, e in zip(self.dependents, self.ics)] \
            + ev + [rf"\text{{{self.paths} paths, {self.steps} steps, seed {self.seed}}}"]

    # ---- numbers
    def _compiled(self):
        if "f" not in self._cache:
            args = [self.t, *self.state, *self.params]
            self._cache["drift"] = _lam(args, self.drift)
            self._cache["diff"] = _lam(args, self.diffusion)
            self._cache["ic"] = fast_lambdify(self.inputs, self.ics)
            self._cache["start"] = fast_lambdify(self.inputs, self.start)
            self._cache["g"] = [_lam(args, e.g) for e in self.sde_events]
            self._cache["gs"] = [_lam(args, sum(sum((sp.diff(e.g, st) * self.diffusion[i][k] for i, st in enumerate(self.state)), sp.Integer(0)) ** 2 for k in range(len(self.noises)))) for e in self.sde_events]
            self._cache["reset"] = [_lam(args, [e.reset.get(st, st) for st in self.state]) if e.reset else None for e in self.sde_events]
            self._cache["level"] = [fast_lambdify(self.inputs, lv) if lv is not None else None for _k, _d, _v, lv, _p in self.statistics]
            self._cache["p"] = [fast_lambdify(self.inputs, p) if p is not None else None for _k, _d, _v, _lv, p in self.statistics]
            self._cache["f"] = True
        return self._cache

    def _simulate(self, args: list, params: list, t0: float, t1: float, y0: np.ndarray) -> SdeResult:
        c = self._compiled()
        m, nW = len(y0), len(self.noises)
        P, S = self.paths, self.steps + (self.steps % 2)
        rng = np.random.default_rng(self.seed)
        nE = len(self.sde_events)
        dt = (t1 - t0) / S
        events = self.sde_events

        def new_run():
            return {"X": np.repeat(y0[:, None], P, axis=1), "active": np.ones(P, bool),
                    "hit_t": [np.full(P, np.nan) for _ in range(nE)], "count": [np.zeros(P) for _ in range(nE)]}

        def advance(run, t, h, dW, u):
            """One Euler-Maruyama step of every path; then the events: hits (also between the two ends, by the Brownian-bridge probability), absorption and resets."""
            X = run["X"]
            f = np.array([np.broadcast_to(np.asarray(v, float), (P,)) for v in c["drift"](t, *X, *params)])
            g = c["diff"](t, *X, *params)
            Xn = X + f * h
            for i in range(m):
                for k in range(nW):
                    Xn[i] = Xn[i] + np.broadcast_to(np.asarray(g[i][k], float), (P,)) * dW[k]
            if not nE:
                run["X"] = Xn
                return
            Xn = np.where(run["active"], Xn, X)                         # absorbed paths stay where they were stopped
            for k, ev in enumerate(events):
                g0 = np.broadcast_to(np.asarray(c["g"][k](t, *X, *params), float), (P,))
                g1 = np.broadcast_to(np.asarray(c["g"][k](t + h, *Xn, *params), float), (P,))
                var = np.broadcast_to(np.asarray(c["gs"][k](t, *X, *params), float), (P,))
                with np.errstate(all="ignore"):
                    pb = np.where((g0 * g1 > 0) & (var > 0), np.exp(-2 * g0 * g1 / np.maximum(var * h, 1e-300)), 0.0)
                up, down = (g0 < 0) & (g1 >= 0), (g0 > 0) & (g1 <= 0)
                rise = up | ((g0 < 0) & (g1 < 0) & (u[k] < pb))
                fall = down | ((g0 > 0) & (g1 > 0) & (u[k] < pb))
                hit = {"rising": rise, "falling": fall, "either": rise | fall}[ev.direction] & run["active"]
                if not hit.any():
                    continue
                crossed = up | down
                with np.errstate(all="ignore"):
                    theta = np.where(crossed & (g0 != g1), g0 / (g0 - g1), np.where(crossed, 1.0, 0.0))
                first = hit & np.isnan(run["hit_t"][k])
                run["hit_t"][k][first] = (t + h * np.where(crossed, theta, 0.5))[first]
                run["count"][k] += hit
                if ev.terminal:
                    Xn = np.where(hit, X + (Xn - X) * theta, Xn)         # stopped where the condition crossed zero (on the barrier for a bridge crossing)
                    run["active"] = run["active"] & ~hit
                elif ev.reset:
                    th = np.where(crossed, theta, 0.5)                    # the jump happens where the condition crossed; the rest of the step is spent after it (drift only)
                    Xh = X + (Xn - X) * th
                    th_t = t + h * th
                    new = np.array([np.broadcast_to(np.asarray(v, float), (P,)) for v in c["reset"][k](th_t, *Xh, *params)])
                    rest = np.array([np.broadcast_to(np.asarray(v, float), (P,)) for v in c["drift"](th_t, *new, *params)]) * (1 - th) * h
                    Xn = np.where(hit, new + rest, Xn)
            run["X"] = Xn

        fine, coarse = new_run(), new_run()
        X, Xc = fine["X"], coarse["X"]
        snap_steps = sorted({round(i * S / SNAPSHOTS) for i in range(SNAPSHOTS + 1)})
        times = [t0 + s * dt for s in snap_steps]
        mean, std, sample = [], [], []
        n_sample = min(5, P)

        def record():
            X = fine["X"]
            mean.append(X.mean(axis=1))
            std.append(X.std(axis=1, ddof=1) if P > 1 else np.zeros(m))
            sample.append(X[:, :n_sample].copy())
        record()
        pend = np.zeros((nW, P))
        sq = math.sqrt(dt)
        for n in range(S):
            t = t0 + n * dt
            dW = rng.standard_normal((nW, P)) * sq
            u = rng.random((nE, P)) if nE else None
            advance(fine, t, dt, dW, u)
            pend += dW
            if n % 2 == 1:                                   # the same Brownian path with half the steps (strong coupling)
                advance(coarse, t0 + (n - 1) * dt, 2 * dt, pend, u)
                pend[:] = 0.0
            if not np.all(np.isfinite(fine["X"])):
                raise OdeError(f"the paths blew up (not finite) near t = {t + dt:g}: check the equations or use more steps")
            if (n + 1) in snap_steps and n + 1 < S:
                record()
        record()
        X, Xc = fine["X"], coarse["X"]
        stats = []
        for (kind, di, _var, _lv, _p), lvf, pf in zip(self.statistics, c["level"], c["p"]):
            level = float(lvf(*args)) if lvf is not None else None
            pq = float(pf(*args)) if pf is not None else None
            if kind in EVENT_KINDS:
                stats.append(self._event_stat(kind, di, fine, coarse, pq, P))
                continue
            x, xc = X[di], Xc[di]
            if kind == "mean":
                val, err, alt = float(x.mean()), float(x.std(ddof=1) / math.sqrt(P)), float(xc.mean())
            elif kind == "std":
                val, err, alt = float(x.std(ddof=1)), float(x.std(ddof=1) / math.sqrt(2 * (P - 1))), float(xc.std(ddof=1))
            elif kind in ("above", "below"):
                pr = (lambda a: float(np.mean(a > level))) if kind == "above" else (lambda a: float(np.mean(a < level)))
                val, alt = pr(x), pr(xc)
                err = math.sqrt(max(val * (1 - val), 1e-12) / P)
            else:
                if not (pq is not None and 0 < pq < 1):
                    raise OdeError("a quantile needs a probability p between 0 and 1")
                val, alt = float(np.quantile(x, pq)), float(np.quantile(xc, pq))
                dens = max(abs(np.quantile(x, min(pq + 0.02, 0.999)) - np.quantile(x, max(pq - 0.02, 0.001))) / 0.04, 1e-300)
                err = math.sqrt(pq * (1 - pq) / P) * dens
            stats.append((val, err, abs(val - alt) if kind not in ("above", "below") else abs(val - alt)))
        notes = [f"{P} paths, {S} steps (Euler–Maruyama, seed {self.seed}); sampling error and the difference from a run with {S // 2} steps are listed with each statistic"]
        if nE:
            notes.append("events: crossings between two steps are detected with the Brownian-bridge probability; event times are linearly interpolated within the step")
        return SdeResult(times, np.array(mean), np.array(std), np.array(sample), stats, notes, S, P)

    def _event_stat(self, kind, k, fine, coarse, pq, P):
        def one(run):
            ht = run["hit_t"][k]
            hit = ~np.isnan(ht)
            if kind == "hit_probability":
                return float(hit.mean()), None
            if kind == "hit_count_mean":
                return float(run["count"][k].mean()), float(run["count"][k].std(ddof=1) / math.sqrt(P))
            if not hit.any():
                return None, None
            h = ht[hit]
            if kind == "hit_time_mean":
                return float(h.mean()), float(h.std(ddof=1) / math.sqrt(len(h))) if len(h) > 1 else 0.0
            if kind == "hit_time_std":
                return float(h.std(ddof=1)) if len(h) > 1 else 0.0, float(h.std(ddof=1) / math.sqrt(2 * (len(h) - 1))) if len(h) > 1 else 0.0
            if not (pq is not None and 0 < pq < 1):
                raise OdeError("a quantile needs a probability p between 0 and 1")
            dens = max(abs(np.quantile(h, min(pq + 0.02, 0.999)) - np.quantile(h, max(pq - 0.02, 0.001))) / 0.04, 1e-300)
            return float(np.quantile(h, pq)), math.sqrt(pq * (1 - pq) / len(h)) * dens
        val, err = one(fine)
        if val is None:
            raise OdeError(f"no path reached the event '{self.sde_events[k].title}' before the evaluation time, so its hit-time statistics are undefined "
                           f"(use more paths, a longer time or a condition that is reached)")
        alt, _ = one(coarse)
        if err is None:
            err = math.sqrt(max(val * (1 - val), 1e-12) / P)
        return (val, err, abs(val - alt) if alt is not None else 0.0)

    def run(self, values: Mapping[sp.Symbol, float], outputs=()) -> SdeResult:
        key = tuple(float(values[s]) for s in self.inputs)
        hit = self._cache.get(("run", key))
        if hit is not None:
            return hit
        c = self._compiled()
        args = [float(values[s]) for s in self.inputs]
        t0, t1 = float(c["start"](*args)), float(values[self.t])
        if not t1 > t0:
            raise OdeError(f"the evaluation time must be after the start ({t0:g})")
        y0 = np.array([float(v) for v in c["ic"](*args)])
        params = [float(values[s]) for s in self.params]
        try:
            res = self._simulate(args, params, t0, t1, y0)
        except (ZeroDivisionError, OverflowError, ValueError, FloatingPointError) as exc:
            raise OdeError(f"the stochastic equations could not be evaluated: {exc}") from None
        if len(self._cache) > 12:
            for k in [k for k in self._cache if isinstance(k, tuple)]:
                del self._cache[k]
        self._cache[("run", key)] = res
        return res

    def statistic(self, index: int, values: Mapping[sp.Symbol, float]) -> float:
        return self.run(values).stats[index][0]


def _lam(args, expr):
    return sp.lambdify(args, expr, modules=["scipy", "numpy"])


def build(spec: Mapping[str, Any], calc, ns: dict, env: dict, custom: bool, index: int):
    from .model import Equation
    from .ode import OdeSpecError, _dependents, _friendly, _make_fn, _parse, _split

    title = str(spec.get("title") or "Stochastic differential equation").strip()[:100]
    ind = spec.get("independent")
    if not isinstance(ind, str) or ind not in calc.by_key or calc.by_key[ind].is_constant:
        raise OdeSpecError(f"'independent' must name one of the variables (time), got {ind!r}")
    if any(spec.get(k) for k in ("boundary", "second", "time", "unknowns", "algebraic")):
        raise OdeSpecError("stochastic equations are initial-value problems: no boundary conditions, space variables, unknown parameters or algebraic constraints")
    t = calc.by_key[ind].symbol
    texts = spec.get("equations")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not texts or not all(isinstance(q, str) and q.strip() for q in texts) or len(texts) > 4:
        raise OdeSpecError("give 1 to 4 equations such as 'diff(x, t) = -theta*x + sigma*xi1'")
    texts = [q.strip() for q in texts]
    names = _dependents(texts, ind)
    if len(names) != len(texts):
        raise OdeSpecError(f"{len(texts)} equation(s) but {len(names)} differentiated quantit{'y' if len(names) == 1 else 'ies'} ({', '.join(names) or 'none'}): one equation per unknown")
    deps = [calc.by_key[n].symbol for n in names]
    for n in names:
        if calc.by_key[n].is_constant or n == ind:
            raise OdeSpecError(f"{n!r} is differentiated but is not a (non-constant) variable")
    for nz in NOISES:
        if nz in calc.by_key:
            raise OdeSpecError(f"{nz!r} is reserved for white noise: rename that variable")
    noise_syms = {nz: sp.Symbol(nz, real=True) for nz in NOISES}
    funcs = {n: sp.Function(n)(t) for n in names}
    state = [sp.Symbol(f"{n}__0", real=True) for n in names]
    top = [sp.Symbol(f"{n}__D", real=True) for n in names]
    local = {**ns, **funcs, **noise_syms}
    ns2 = {**ns, **noise_syms}
    resid, written = [], []
    for text in texts:
        lt, rt = _split(text)
        a, b = _parse(lt, local, custom, ns2), _parse(rt, local, custom, ns2)
        written.append((a, b))
        e = a - b
        rep = {}
        for d in e.atoms(sp.Derivative):
            if not (isinstance(d.expr, sp.core.function.AppliedUndef) and dict(d.variable_count) == {t: 1} and d.expr.func.__name__ in names):
                raise OdeSpecError(f"{d}: stochastic equations are first order: diff(x, {ind})")
            rep[d] = top[names.index(d.expr.func.__name__)]
        r = e.xreplace(rep).xreplace({funcs[n]: state[i] for i, n in enumerate(names)})
        resid.append(r)
    try:
        sols = sp.solve(resid, top, dict=True)
    except Exception as exc:  # noqa: BLE001
        raise OdeSpecError(f"cannot solve the equations for the derivatives: {exc}") from None
    if len(sols) != 1 or any(q not in sols[0] for q in top):
        raise OdeSpecError("each equation must be solvable for the derivative of its unknown")
    rhs = [sols[0][q] for q in top]
    used_noise = [nz for nz in NOISES if any(r.has(noise_syms[nz]) for r in rhs)]
    if not used_noise:
        raise OdeSpecError("no white noise xi1, xi2 or xi3 appears in the equations: for a deterministic equation use an ordinary differential-equation entry")
    drift, diffusion = [], []
    zero = {noise_syms[nz]: 0 for nz in NOISES}
    for r in rhs:
        drift.append(r.xreplace(zero))
        row = []
        for nz in used_noise:
            gk = sp.diff(r, noise_syms[nz])
            if gk.has(*noise_syms.values()):
                raise OdeSpecError("white noise must enter linearly: the noise coefficient may depend on the state and time but not on the noise")
            row.append(gk)
        diffusion.append(row)
    initial = spec.get("initial") or []
    if isinstance(initial, str):
        initial = [q.strip() for q in initial.split("\n") if q.strip()]
    ics: list = [None] * len(names)
    for itxt in initial:
        il, ir = _split(itxt)
        il = il.strip()
        if il not in names or ics[names.index(il)] is not None:
            raise OdeSpecError(f"an initial condition's left side must be one of {', '.join(names)}, once each; got {il!r}")
        ics[names.index(il)] = _parse(ir, {**ns}, custom, ns)
    miss = [names[i] for i in range(len(names)) if ics[i] is None]
    if miss:
        raise OdeSpecError(f"missing initial value for {', '.join(miss)}")
    start = _parse(str(spec.get("start", "0")), ns, custom, ns) if str(spec.get("start", "0")).strip() else sp.Integer(0)
    paths, steps, seed = spec.get("paths", DEFAULT_PATHS), spec.get("steps", DEFAULT_STEPS), spec.get("seed", 12345)
    for nm, v, hi in (("paths", paths, MAX_PATHS), ("steps", steps, MAX_STEPS)):
        if not isinstance(v, int) or isinstance(v, bool) or not 10 <= v <= hi:
            raise OdeSpecError(f"'{nm}' must be a whole number from 10 to {hi}")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2 ** 32:
        raise OdeSpecError("'seed' must be a whole number from 0 to 4294967295")
    # events: watched on every path
    ev_in = spec.get("events") or []
    if not isinstance(ev_in, list) or len(ev_in) > MAX_EVENTS or not all(isinstance(e, Mapping) for e in ev_in):
        raise OdeSpecError(f"'events' is a list of at most {MAX_EVENTS} objects such as {{\"when\": \"x = xc\", \"terminal\": true}}")
    sde_events: list = []
    noise_set = set(noise_syms.values())
    for ke, ev in enumerate(ev_in):
        if not isinstance(ev.get("when"), str) or not ev["when"].strip():
            raise OdeSpecError("each event needs a 'when' condition such as 'x = xc' or 'x - xc'")
        direction = ev.get("direction") or "either"
        if direction not in ("either", "rising", "falling"):
            raise OdeSpecError("an event's 'direction' must be either, rising or falling")
        parts = [x for x in re.split(r"(?<![<>=!])=(?!=)", ev["when"]) if x.strip()]
        if len(parts) > 2:
            raise OdeSpecError(f"an event condition has at most one '=': {ev['when']!r}")
        sides_e = [_parse(q, local, custom, ns2) for q in parts]
        if len(sides_e) == 1:
            sides_e.append(sp.Integer(0))
        to_state = lambda e: e.xreplace({funcs[n]: state[i] for i, n in enumerate(names)})   # noqa: E731
        ge = to_state(sides_e[0] - sides_e[1])
        if ge.atoms(sp.core.function.AppliedUndef) or ge.atoms(sp.Derivative) or ge.has(sp.Integral) or ge.free_symbols & noise_set:
            raise OdeSpecError(f"the event condition {ev['when']!r} may use only the unknowns, time and parameters (no derivatives, integrals or noise)")
        if ev.get("terminal") and ev.get("reset"):
            raise OdeSpecError(f"event {ke + 1}: an event either absorbs the path (terminal) or makes the state jump (reset), not both")
        resets: dict = {}
        if ev.get("reset"):
            if not isinstance(ev["reset"], Mapping):
                raise OdeSpecError(f"event {ke + 1}: 'reset' is a mapping such as {{\"x\": \"x0\"}}")
            for lhs_text, rhs_text in ev["reset"].items():
                if str(lhs_text).strip() not in names:
                    raise OdeSpecError(f"event {ke + 1}: reset: {lhs_text!r} is not one of the unknowns ({', '.join(names)})")
                new = to_state(_parse(str(rhs_text), local, custom, ns2))
                if new.atoms(sp.core.function.AppliedUndef) or new.atoms(sp.Derivative) or new.free_symbols & noise_set:
                    raise OdeSpecError(f"event {ke + 1}: reset of {lhs_text} may use only the unknowns, time and parameters")
                resets[state[names.index(str(lhs_text).strip())]] = new
        show = {funcs[n]: calc.by_key[n].symbol for n in names}
        sde_events.append(SdeEvent(str(ev.get("title") or f"event {ke + 1}")[:80], ge, direction, bool(ev.get("terminal", False)), resets,
                                   (sides_e[0].xreplace(show), sides_e[1].xreplace(show))))
    ev_titles = [e.title for e in sde_events]
    # statistics: each delivers one number to a variable
    stats_in = spec.get("statistics")
    if not isinstance(stats_in, list) or not stats_in or len(stats_in) > 12 or not all(isinstance(q, Mapping) for q in stats_in):
        raise OdeSpecError("'statistics' lists what to report, e.g. {\"of\": \"x\", \"kind\": \"mean\", \"var\": \"xm\"} (kinds: " + ", ".join(KINDS) + ")")
    claimed = {*deps, t}
    statistics: list = []
    for q in stats_in:
        kind, of, var = q.get("kind"), q.get("of"), q.get("var")
        if kind in EVENT_KINDS:
            ref = q.get("event")
            idx = ev_titles.index(ref) if ref in ev_titles else (int(ref) - 1 if str(ref).isdigit() and 1 <= int(ref) <= len(sde_events) else None)
            if idx is None:
                raise OdeSpecError(f"a '{kind}' statistic needs 'event': the title or the number (from 1) of one of the events ({', '.join(ev_titles) or 'none defined'})")
            of = idx
        elif kind not in KINDS or of not in names:
            raise OdeSpecError(f"each statistic needs a 'kind' ({', '.join(KINDS + EVENT_KINDS)}) and 'of' one of {', '.join(names)}")
        if var not in calc.by_key or calc.by_key[var].is_constant or calc.by_key[var].symbol in claimed:
            raise OdeSpecError(f"statistic 'var' {var!r} must be a free variable of this calculation that is not used for anything else")
        claimed.add(calc.by_key[var].symbol)
        level = _parse(str(q["level"]), ns, custom, ns) if kind in ("above", "below") and str(q.get("level", "")).strip() else None
        pexp = _parse(str(q["p"]), ns, custom, ns) if kind in ("quantile", "hit_time_quantile") and str(q.get("p", "")).strip() else None
        if kind in ("above", "below") and level is None:
            raise OdeSpecError(f"a '{kind}' statistic needs a 'level'")
        if kind in ("quantile", "hit_time_quantile") and pexp is None:
            raise OdeSpecError("a quantile needs a probability 'p' (between 0 and 1)")
        statistics.append((kind, of if kind in EVENT_KINDS else names.index(of), calc.by_key[var].symbol, level, pexp))
    declared = {v.symbol for v in calc.variables}
    exprs = [*drift, *[g for row in diffusion for g in row], *ics, start, *[e.g for e in sde_events], *[x for e in sde_events for x in e.reset.values()], *[x for _k, _d, _v, lv, p in statistics for x in (lv, p) if x is not None]]
    params = sorted({s for e in exprs for s in e.free_symbols if s not in state and s != t and s in declared and s not in {st[2] for st in statistics}}, key=lambda s: s.name)
    bad = [s for e in exprs for s in e.free_symbols if s not in state and s != t and s not in declared]
    if bad:
        raise OdeSpecError(f"{bad[0]} is not a variable of this calculation")
    dim_t, unit_t = env[t]
    genv = dict(env)
    for i, d in enumerate(deps):
        genv[state[i]] = env[d]
    half = Fraction_half()
    try:
        for i, d in enumerate(deps):
            dd = env[d][0]
            if drift[i] != 0:
                dr, _ = analyze(drift[i], genv)
                if dr != dd / dim_t:
                    raise DimensionError(f"the drift of {names[i]} has dimension [{dr}], expected [{dd / dim_t}] (the quantity per time)")
            for g in diffusion[i]:
                if g != 0:
                    dg, _ = analyze(g, genv)
                    if dg != dd / dim_t ** half:
                        raise DimensionError(f"a noise coefficient of {names[i]} has dimension [{dg}], expected [{dd / dim_t ** half}] (the quantity over the square root of time)")
            if ics[i] != 0:
                di, _ = analyze(ics[i], genv)
                if di != dd:
                    raise DimensionError(f"the initial value of {names[i]} has dimension [{di}], expected [{dd}]")
        for e in sde_events:
            for sd in (e.written[0], e.written[1]):
                if sd != 0:
                    analyze(sd, genv)
            if e.written[1] != 0 and e.written[0] != 0 and analyze(e.written[0], genv)[0] != analyze(e.written[1], genv)[0]:
                raise DimensionError(f"event '{e.title}': the two sides of the condition have different dimensions")
            for st, new in e.reset.items():
                if new != 0:
                    dn, _ = analyze(new, genv)
                    if dn != genv[st][0]:
                        raise DimensionError(f"event '{e.title}': the reset value of {st.name.split('__')[0]} has dimension [{dn}], expected [{genv[st][0]}]")
        for kind, di_, var, level, pexp in statistics:
            if kind in EVENT_KINDS:
                want = dim_t if kind.startswith("hit_time") else DIMENSIONLESS
                if env[var][0] != want:
                    raise DimensionError(f"{var.name} receives a {kind} and must have dimension [{want}], not [{env[var][0]}]")
                continue
            want = DIMENSIONLESS if kind in ("above", "below") else env[deps[di_]][0]
            if env[var][0] != want:
                raise DimensionError(f"{var.name} receives a {kind} and must have dimension [{want}], not [{env[var][0]}]")
            if level is not None and level != 0:
                dl, _ = analyze(level, genv)
                if dl != env[deps[di_]][0]:
                    raise DimensionError(f"the level has dimension [{dl}], expected [{env[deps[di_]][0]}]")
        if start != 0:
            ds, _ = analyze(start, env)
            if ds != dim_t:
                raise DimensionError(f"the start has dimension [{ds}], expected [{dim_t}]")
    except DimensionError as exc:
        raise OdeSpecError(f"{title}: {_friendly(str(exc))}") from None
    inputs = sorted({t, *params, *[s for e in (*ics, start, *[x for _k, _d, _v, lv, p in statistics for x in (lv, p) if x is not None]) for s in e.free_symbols if s in declared]}, key=lambda s: s.name)
    system = SdeSystem(title, texts, t, start, deps, state, drift, diffusion, [noise_syms[nz] for nz in used_noise], ics, statistics, written, params, inputs, paths, steps, seed)
    system.sde_events = sde_events
    system.hidden = set(deps)                                  # the unknowns themselves are random: only the statistics are results
    eqs = []
    for k, (kind, di_, var, level, pexp) in enumerate(statistics):
        dim, unit = env[var]
        node = _make_fn(system, var, (dim, unit), calc.by_key[var.name].latex or var.name, index * 10 + k, evaluate=(lambda vals, k=k: system.statistic(k, vals)))
        system.fns[var] = node
        what = f"event '{sde_events[di_].title}'" if kind in EVENT_KINDS else names[di_]
        eq = Equation(f"{title}: {var.name} ({kind} of {what})", f"{var.name} = {kind} of {what} from {'; '.join(texts)}", var, node(*system.inputs), frozenset({var, *system.inputs}), None)
        eq.ode = system
        eqs.append(eq)
    return system, eqs


def Fraction_half():
    from fractions import Fraction

    return Fraction(1, 2)
