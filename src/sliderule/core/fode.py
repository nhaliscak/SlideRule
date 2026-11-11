"""Fractional-order differential equations (Caputo derivatives) by the Adams-Bashforth-Moulton predictor-corrector method.

An ``odes`` entry whose equations contain ``fdiff(y, t, alpha)`` -- the Caputo derivative of order ``alpha`` (0 < alpha <= 3) of ``y`` with respect to ``t`` -- is handled
here, alone or as a system (integer-order ``diff(y, t)`` terms count as order 1)::

    {"title": "Fractional relaxation", "independent": "t", "start": "0",
     "equations": ["fdiff(y, t, 0.6) = -k*y"], "initial": ["y = y0"]}

Orders above 1 need one initial value per integer below the order (``m = ceil(alpha)`` of them): ``y``, ``diff(y, t)`` and ``diff(y, t, 2)`` at the start, e.g. a fractional
oscillator ``fdiff(y, t, 1.5) = -k*y`` with ``initial: ["y = 1", "diff(y, t) = 0"]``. Between 1 and 2 the equation interpolates between diffusion-like relaxation (order 1) and
wave-like oscillation (order 2): the Mittag-Leffler solution ``E_alpha(-k t^alpha)`` oscillates and decays for 1 < alpha < 2.

The unknown ``y`` then means its value at the time ``t`` the user supplies. A fractional derivative has memory: its value at ``t`` depends on the whole history
of ``y`` since the start (a power-law kernel), which is why viscoelastic materials, anomalous diffusion and some dampers are modelled this way. The relaxation
equation ``D^alpha y = -k y`` has the Mittag-Leffler solution ``y = y0 E_alpha(-k t^alpha)`` (not an exponential: it decays like a power law ``t^-alpha`` for large t).

Numerics: the Diethelm-Ford-Freed predictor-corrector on a uniform grid (the whole history is summed at every step: O(N^2) work); the number of steps is
``nodes`` (default 800, 50 to 8000). The solution of a fractional equation is not smooth at the start (it behaves like ``t^alpha``), so the order of convergence
is only about ``1 + alpha`` at best: the run is repeated with half the steps and the difference is reported as an error estimate.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Mapping

import numpy as np
import sympy as sp
from sympy.core.function import AppliedUndef

from .dimcheck import DimensionError, analyze
from .numeric_ode import OdeError, OdeResult
from .special import fast_lambdify

MAX_ORDER = 3
DEFAULT_STEPS = 800
MIN_STEPS, MAX_STEPS = 50, 8000


class FracD(sp.Function):
    """Marker for the Caputo derivative ``fdiff(y, t, alpha)``; replaced by a symbol while the equations are analysed."""
    nargs = 2


def fdiff(f, t, alpha):
    return FracD(f, sp.nsimplify(alpha, rational=True))


@dataclass
class FractionalSystem:
    title: str
    texts: list[str]
    t: sp.Symbol
    start: sp.Expr
    dependents: list
    orders: dict                                  # dependent symbol -> order alpha (Fraction)
    state: list                                   # internal symbols of the dependents
    rhs: list                                     # D^alpha_i y_i = rhs_i(t, state, params)
    ics: list
    written: list
    params: list
    inputs: list
    nodes: int = DEFAULT_STEPS
    dics: list = field(default_factory=list)       # per dependent: initial values of diff(y, t), diff(y, t, 2), ... (one per integer below the order)
    why_numeric: str = "a fractional derivative has memory and is integrated numerically (Adams-Bashforth-Moulton predictor-corrector)"
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
    _cache: dict = field(default_factory=dict, repr=False)

    numeric = True
    fractional = True
    pde = False

    @property
    def state_index(self) -> dict:
        return {(d, 0): i for i, d in enumerate(self.dependents)}

    @property
    def condition_note(self) -> str:
        return "initial condition"

    @property
    def initial_texts(self) -> list[str]:
        out = [f"{d.name} = {sp.sstr(e)}" for d, e in zip(self.dependents, self.ics)]
        for d, ds in zip(self.dependents, self.dics):
            out += [f"diff({d.name}, {self.t.name}{'' if k == 1 else f', {k}'}) = {sp.sstr(e)}" for k, e in enumerate(ds, start=1)]
        return out

    def last_result(self):
        return self._cache.get("last")

    def event_latex(self, names: dict) -> list:
        return []

    def written_latex(self, names: dict) -> list[str]:
        return [f"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)}" for a, b in self.written]

    def condition_latex(self, names: dict) -> list[str]:
        t = names.get(self.t, str(self.t))
        out = [rf"{names.get(d, str(d))}\left({sp.latex(self.start, symbol_names=names)}\right) = {sp.latex(e, symbol_names=names)} \quad \text{{(initial value; Caputo derivatives of order {a})}}"
               for d, e, a in zip(self.dependents, self.ics, self.orders.values())]
        for d, ds in zip(self.dependents, self.dics):
            out += [rf"{names.get(d, str(d))}^{{({k})}}\left({sp.latex(self.start, symbol_names=names)}\right) = {sp.latex(e, symbol_names=names)}" for k, e in enumerate(ds, start=1)]
        return out + [rf"{t} \ge {sp.latex(self.start, symbol_names=names)}"]

    # ---- numbers
    def _compiled(self):
        if "f" not in self._cache:
            self._cache["f"] = fast_lambdify([self.t, *self.state, *self.params], self.rhs)
            self._cache["ic"] = fast_lambdify(self.inputs, self.ics)
            self._cache["dic"] = fast_lambdify(self.inputs, [e for ds in self.dics for e in ds]) if any(self.dics) else None
            self._cache["start"] = fast_lambdify(self.inputs, self.start)
        return self._cache["f"], self._cache["ic"], self._cache["start"]

    def _lead(self, args, ts, t0, y0):
        """The initial polynomial y(0) + y'(0) t + y''(0) t^2/2 of each component on the time grid (the Caputo definition's starting term)."""
        T = np.tile(np.asarray(y0, float), (len(ts), 1))
        if self._cache["dic"] is not None:
            flat = [float(v) for v in self._cache["dic"](*args)]
            pos = 0
            for i, ds in enumerate(self.dics):
                for k in range(1, len(ds) + 1):
                    T[:, i] += flat[pos] * (ts - t0) ** k / math.factorial(k)
                    pos += 1
        return T

    def _march(self, f, y0, alphas, t0, t1, N, params, lead=None):
        """Adams-Bashforth-Moulton on N uniform steps; returns the times and the states (rows are steps)."""
        m = len(y0)
        h = (t1 - t0) / N
        ts = t0 + h * np.arange(N + 1)
        Y = np.zeros((N + 1, m))
        Fh = np.zeros((N + 1, m))                                      # f at every grid point so far
        Y[0] = y0
        if lead is not None:
            lead = lead(ts)
        Fh[0] = f(ts[0], *Y[0], *params)
        al = np.array(alphas, float)
        gam = np.array([math.gamma(a) for a in al])
        gam2 = np.array([math.gamma(a + 2) for a in al])
        hp = h ** al
        n_idx = np.arange(0, N + 1, dtype=float)
        for n in range(N):
            j = np.arange(0, n + 1, dtype=float)
            # predictor weights b_{j,n+1} and corrector weights a_{j,n+1}, per component (they depend on alpha)
            b = ((n + 1 - j)[:, None] ** al - (n - j)[:, None] ** al) / al * hp
            base = y0 if lead is None else lead[n + 1]
            pred = base + (b * Fh[:n + 1]).sum(axis=0) / gam
            a = np.empty((n + 1, m))
            a[0] = n ** (al + 1) - (n - al) * (n + 1) ** al
            if n >= 1:
                k = (n - j[1:])[:, None]
                a[1:] = (k + 2) ** (al + 1) + k ** (al + 1) - 2 * (k + 1) ** (al + 1)
            fp = np.asarray(f(ts[n + 1], *pred, *params), float)
            Y[n + 1] = base + hp / gam2 * (fp + (a * Fh[:n + 1]).sum(axis=0))
            if not np.all(np.isfinite(Y[n + 1])):
                raise OdeError(f"the fractional solution is not finite at t = {ts[n + 1]:g}")
            Fh[n + 1] = f(ts[n + 1], *Y[n + 1], *params)
        _ = n_idx
        return ts, Y

    def run(self, values: Mapping[sp.Symbol, float], outputs=()) -> OdeResult:
        key = tuple(float(values[s]) for s in self.inputs)
        hit = self._cache.get(("run", key))
        if hit is not None:
            self._cache["last"] = hit
            return hit
        f, ic, start = self._compiled()
        args = [float(values[s]) for s in self.inputs]
        t0, t1 = float(start(*args)), float(values[self.t])
        y0 = np.array([float(v) for v in ic(*args)])
        params = [float(values[s]) for s in self.params]
        alphas = [float(a) for a in self.orders.values()]
        if t1 < t0:
            raise OdeError("a fractional equation is integrated forward in time")
        if t1 == t0:
            res = OdeResult([t0], [list(y0)], "Adams-Bashforth-Moulton", 0, 0, 0.0, 0.0)
            self._cache[("run", key)] = res
            return res
        N = self.nodes + (self.nodes % 2)
        try:
            lead = lambda grid: self._lead(args, grid, t0, y0)                  # noqa: E731
            ts, Y = self._march(lambda t, *a: np.asarray(f(t, *a), float), y0, alphas, t0, t1, N, params, lead)
        except (ZeroDivisionError, OverflowError, ValueError) as exc:
            raise OdeError(f"the fractional equations could not be evaluated: {exc}") from None
        notes = []
        if N >= 2 * MIN_STEPS:
            tc, Yc = self._march(lambda t, *a: np.asarray(f(t, *a), float), y0, alphas, t0, t1, N // 2, params, lead)
            err = float(np.max(np.abs(Y[::2] - Yc))) / (2 ** min(1.0 + min(alphas), 2.0) - 1)
            scale = max(float(np.max(np.abs(Y))), 1e-300)
            notes.append(f"{N} steps; estimated error {err:.1e} ({err / scale:.1e} relative), from comparison with {N // 2} steps")
            if err / scale > 1e-2:
                notes.append("the estimated error is above 1 %: increase the number of steps ('nodes')")
        res = OdeResult(ts.tolist(), Y.tolist(), "Adams-Bashforth-Moulton predictor-corrector (fractional, with memory)", N, N * N, 0.0, 0.0, notes)
        if len(self._cache) > 30:
            self._cache.clear()
        self._cache[("run", key)] = res
        self._cache["last"] = res
        return res

    def value(self, dependent: sp.Symbol, values: Mapping[sp.Symbol, float]) -> float:
        return self.run(values).ys[-1][self.dependents.index(dependent)]

    def interval(self, values):
        _f, _ic, start = self._compiled()
        return float(start(*[float(values[s]) for s in self.inputs])), float(values[self.t])

    def trajectory(self, values, n: int = 200, extra_times=()):
        res = self.run(values)
        ts = np.array(res.ts)
        t0, t1 = float(ts[0]), float(ts[-1])
        want = sorted({t0 + (t1 - t0) * i / n for i in range(n + 1)} | {x for x in extra_times if t0 <= x <= t1}) if t1 > t0 else [t0]
        cols = {d: [] for d in self.dependents}
        arr = np.array(res.ys)
        for i, d in enumerate(self.dependents):
            col = np.interp(want, ts, arr[:, i]) if len(ts) > 1 else [arr[0, i]] * len(want)
            cols[d] = [float(v) for v in col]
        return want, cols, {"method": res.method, "steps": res.steps, "nfev": res.nfev, "rtol": res.rtol, "atol": res.atol, "notes": res.notes, "events": [], "stopped_by": None}


def build(spec: Mapping[str, Any], calc, ns: dict, env: dict, custom: bool, index: int):
    from .model import Equation
    from .ode import OdeSpecError, _friendly, _make_fn, _parse, _split
    from .safeparse import bound_names

    title = str(spec.get("title") or "Fractional differential equation").strip()[:100]
    ind = spec.get("independent")
    if not isinstance(ind, str) or ind not in calc.by_key or calc.by_key[ind].is_constant:
        raise OdeSpecError(f"'independent' must name one of the variables (time), got {ind!r}")
    if any(spec.get(k) for k in ("boundary", "events", "second", "time", "unknowns", "algebraic")):
        raise OdeSpecError("fractional equations are initial-value problems: no boundary conditions, events, space variables, unknown parameters or algebraic constraints")
    t = calc.by_key[ind].symbol
    texts = spec.get("equations")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not texts or not all(isinstance(q, str) and q.strip() for q in texts) or len(texts) > 6:
        raise OdeSpecError("give 1 to 6 equations such as 'fdiff(y, t, 0.6) = -k*y'")
    texts = [q.strip() for q in texts]
    steps = spec.get("nodes", DEFAULT_STEPS)
    if not isinstance(steps, int) or isinstance(steps, bool) or not MIN_STEPS <= steps <= MAX_STEPS:
        raise OdeSpecError(f"'nodes' (the number of steps) must be a whole number from {MIN_STEPS} to {MAX_STEPS}")
    # the dependents: whatever is differentiated (fractionally or of order one)
    names: list[str] = []
    for text in texts:
        for side in _split(text):
            try:
                tree = ast.parse(side.strip().replace("^", "**"), mode="eval")
            except SyntaxError:
                raise OdeSpecError(f"cannot read the equation {text!r}") from None
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("fdiff", "diff") and len(n.args) >= 2 and isinstance(n.args[0], ast.Name) \
                        and isinstance(n.args[1], ast.Name) and n.args[1].id == ind and n.args[0].id in calc.by_key and n.args[0].id not in names:
                    names.append(n.args[0].id)
    if len(names) != len(texts):
        raise OdeSpecError(f"{len(texts)} equation(s) but {len(names)} differentiated quantit{'y' if len(names) == 1 else 'ies'} ({', '.join(names) or 'none'}): one equation per unknown")
    deps = [calc.by_key[n].symbol for n in names]
    for n, d in zip(names, deps):
        if calc.by_key[n].is_constant or d == t:
            raise OdeSpecError(f"{n!r} is differentiated but is not a (non-constant) variable")
    funcs = {n: sp.Function(n)(t) for n in names}
    local = {**ns, **funcs, "fdiff": lambda f, tt, alpha: FracD(f, sp.nsimplify(alpha, rational=True))}
    ns2 = {**ns, "fdiff": fdiff}
    state = [sp.Symbol(f"{n}__0", real=True) for n in names]
    top = [sp.Symbol(f"{n}__D", real=True) for n in names]
    orders: dict = {}
    residuals, written = [], []
    for text in texts:
        lt, rt = _split(text)
        loc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(text) if n not in local}}
        a, b = _parse(lt, loc, custom, ns2), _parse(rt, loc, custom, ns2)
        e = a - b
        rep = {}
        for d in e.atoms(FracD):
            fn_, alpha = d.args
            if not (isinstance(fn_, AppliedUndef) and fn_.func.__name__ in names):
                raise OdeSpecError(f"fdiff(y, {ind}, alpha): y must be one of the unknowns ({', '.join(names)})")
            if not (alpha.is_number and 0 < alpha <= MAX_ORDER):
                raise OdeSpecError(f"the order of a fractional derivative must be a number with 0 < alpha <= {MAX_ORDER} (got {alpha})")
            k = names.index(fn_.func.__name__)
            if k in orders and orders[k] != Fraction(int(alpha.p), int(alpha.q)):
                raise OdeSpecError(f"{names[k]} is differentiated with two different orders")
            orders[k] = Fraction(int(alpha.p), int(alpha.q))
            rep[d] = top[k]
        for d in e.atoms(sp.Derivative):
            vc = dict(d.variable_count)
            if not (isinstance(d.expr, AppliedUndef) and set(vc) == {t} and 1 <= vc[t] <= MAX_ORDER and d.expr.func.__name__ in names):
                raise OdeSpecError(f"{d}: use diff({names[0]}, {ind}) (order 1, or diff({names[0]}, {ind}, 2)) or fdiff({names[0]}, {ind}, alpha) with 0 < alpha <= {MAX_ORDER}")
            k = names.index(d.expr.func.__name__)
            if k in orders and orders[k] != vc[t]:
                raise OdeSpecError(f"{names[k]} is differentiated with two different orders")
            orders[k] = Fraction(int(vc[t]))
            rep[d] = top[k]
        r = e.xreplace(rep).xreplace({funcs[n]: state[i] for i, n in enumerate(names)})
        if r.atoms(AppliedUndef) or r.atoms(FracD) or r.atoms(sp.Derivative):
            raise OdeSpecError(f"the equation {text!r} uses a derivative in a way that cannot be handled")
        residuals.append(r)
        written.append((a, b))
    if set(orders) != set(range(len(names))):
        raise OdeSpecError("every unknown needs a fractional or first-order derivative in its own equation")
    try:
        sols = sp.solve(residuals, top, dict=True)
    except Exception as exc:  # noqa: BLE001
        raise OdeSpecError(f"cannot solve the equations for the derivatives: {exc}") from None
    if len(sols) != 1 or any(q not in sols[0] for q in top) or any(sols[0][q].has(*top) for q in top):
        raise OdeSpecError("each equation must be solvable for the derivative of its unknown, with the other terms not containing derivatives")
    rhs = [sols[0][q] for q in top]
    initial = spec.get("initial") or []
    if isinstance(initial, str):
        initial = [q.strip() for q in initial.split("\n") if q.strip()]
    ics: list = [None] * len(names)
    need = [math.ceil(orders[i]) for i in range(len(names))]                 # initial values per unknown: y, y', ... up to the integer below the order
    dvals: list = [dict() for _ in names]
    lhs_re = re.compile(rf"^\s*(?:(\w+)|diff\(\s*(\w+)\s*,\s*{re.escape(ind)}\s*(?:,\s*(\d+)\s*)?\))\s*$")
    for itxt in initial:
        il, ir = _split(itxt)
        mm = lhs_re.match(il)
        nm = (mm.group(1) or mm.group(2)) if mm else None
        k = int(mm.group(3) or 1) if mm and mm.group(2) else 0
        if nm not in names or (k == 0 and ics[names.index(nm)] is not None) or (k > 0 and k in dvals[names.index(nm)]):
            raise OdeSpecError(f"an initial condition's left side must be one of {', '.join(names)} or diff(name, {ind}[, n]), once each; got {il.strip()!r}")
        i = names.index(nm)
        if k >= need[i]:
            raise OdeSpecError(f"{nm} has order {orders[i]}, so it needs initial values up to the derivative of order {need[i] - 1} only (got {il.strip()!r})")
        val = _parse(ir, {**ns}, custom, ns)
        if k == 0:
            ics[i] = val
        else:
            dvals[i][k] = val
    miss = [names[i] for i in range(len(names)) if ics[i] is None]
    if miss:
        raise OdeSpecError(f"missing initial value for {', '.join(miss)}")
    for i in range(len(names)):
        lack = [k for k in range(1, need[i]) if k not in dvals[i]]
        if lack:
            raise OdeSpecError(f"{names[i]} has order {orders[i]}: give also the initial value of diff({names[i]}, {ind}{'' if lack[0] == 1 else f', {lack[0]}'})")
    dics = [[dvals[i][k] for k in range(1, need[i])] for i in range(len(names))]
    start = _parse(str(spec.get("start", "0")), ns, custom, ns) if str(spec.get("start", "0")).strip() else sp.Integer(0)
    declared = {v.symbol for v in calc.variables}
    params = sorted({s for e in [*rhs, *ics, *[x for ds in dics for x in ds], start] for s in e.free_symbols if s not in state and s != t and s in declared}, key=lambda s: s.name)
    bad = [s for e in rhs for s in e.free_symbols if s not in state and s != t and s not in declared]
    if bad:
        raise OdeSpecError(f"{bad[0]} is not a variable of this calculation")
    dim_t, unit_t = env[t]
    genv = dict(env)
    for i, d in enumerate(deps):
        genv[state[i]] = env[d]
    try:
        for i, d in enumerate(deps):
            alpha = orders[i]
            want = env[d][0] / dim_t ** alpha
            dr, _ = analyze(rhs[i], genv)
            if dr != want and rhs[i] != 0:
                raise DimensionError(f"the equation for {names[i]} gives its derivative of order {alpha} the dimension [{dr}], expected [{want}]")
            if ics[i] != 0:
                di, _ = analyze(ics[i], genv)
                if di != env[d][0]:
                    raise DimensionError(f"the initial value of {names[i]} has dimension [{di}], expected [{env[d][0]}]")
            for k, e in enumerate(dics[i], start=1):
                if e != 0:
                    di, _ = analyze(e, genv)
                    if di != env[d][0] / dim_t ** k:
                        raise DimensionError(f"the initial value of the derivative of order {k} of {names[i]} has dimension [{di}], expected [{env[d][0] / dim_t ** k}]")
        if start != 0:
            ds, _ = analyze(start, env)
            if ds != dim_t:
                raise DimensionError(f"the start has dimension [{ds}], expected [{dim_t}]")
    except DimensionError as exc:
        raise OdeSpecError(f"{title}: {_friendly(str(exc))}") from None
    inputs = sorted({t, *params, *[s for e in (*ics, *[x for ds in dics for x in ds], start) for s in e.free_symbols]}, key=lambda s: s.name)
    system = FractionalSystem(title, texts, t, start, deps, {deps[i]: orders[i] for i in range(len(deps))}, state, rhs, ics, written, params, inputs, steps, dics)
    eqs = []
    for i, d in enumerate(deps):
        dim, unit = env[d]
        node = _make_fn(system, d, (dim, unit), calc.by_key[d.name].latex or d.name, index * 10 + i)
        system.fns[d] = node
        eq = Equation(f"{title}: {d.name}" if len(deps) > 1 else title, f"{d.name} = numerical solution of {'; '.join(texts)}", d, node(*system.inputs), frozenset({d, *system.inputs}), None)
        eq.ode = system
        eqs.append(eq)
    return system, eqs
