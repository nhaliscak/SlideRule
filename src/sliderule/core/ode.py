"""Ordinary differential equations (initial-value problems) inside a calculation.

An ODE entry looks like::

    {"title": "Newton cooling", "independent": "t", "start": "0", "method": "auto",
     "equations": ["diff(T, t) = -k*(T - Tamb)"], "initial": ["T = T0"]}

``diff(T, t)`` is the derivative of the quantity ``T`` (one of the calculation's variables) with respect to ``t`` (another);
``diff(x, t, 2)`` is a second derivative. ``initial`` gives the value of ``T`` and of each lower derivative at ``t = start``.
The quantity ``T`` then means *its value at the time* ``t`` the user supplies.

How it is solved:

1. SymPy's ``dsolve`` is tried (``method`` "auto" or "symbolic"). If it finds an explicit closed form, ``T = f(t, k, T0, ...)`` becomes an
   ordinary algebraic equation, so the engine can solve for *any* variable (the time to reach a temperature, the rate constant, ...).
2. Otherwise (or for ``"numeric"``) the problem is integrated numerically (:mod:`.numeric_ode`). ``T = ODE(t, k, T0, ...)`` is then a function node that
   the engine can only evaluate forward: given the parameters and the time, find the state.

The equations are dimension-checked (``[d^n y/dt^n] = [y]/[t]^n``), the initial values must carry the right units, and everything inside is SI.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import sympy as sp
from sympy.core.function import AppliedUndef
from sympy.parsing.sympy_parser import parse_expr

from .. import settings
from ..units import DIMENSIONLESS
from .special import fast_lambdify
from .calculus import CalculusError, evaluate as evaluate_calculus
from .dimcheck import DimensionError, analyze, check_equation
from . import bvp as _bvp
from .numeric_ode import EventSpec, OdeError, OdeResult, dde, solve_ivp
from .timeout import TimeLimitExceeded, time_limit

MAX_EQUATIONS = 12
MAX_ORDER = 6
MAX_STATE = 24
MAX_ALGEBRAIC = 4
MAX_EVENTS = 3
DSOLVE_BUDGET = 3.0          # seconds a closed-form attempt on a user equation may take before falling back to numerics
METHODS = ("auto", "numeric", "symbolic")


class OdeSpecError(ValueError):
    pass


@dataclass
class EventDef:
    """Stop (or mark) the integration where ``when`` crosses zero; the event time and the state there can be exposed as variables."""
    title: str
    g: sp.Expr                                   # in state symbols, t and parameters
    written: tuple[sp.Expr, sp.Expr]             # as entered (dependents shown as plain symbols)
    direction: str                               # "either" | "rising" | "falling"
    terminal: bool
    time_var: sp.Symbol | None
    value_vars: dict                             # dependent symbol -> variable that receives its value at the event
    reset: dict = field(default_factory=dict)    # state symbol -> expression (state, t, parameters) it jumps to at the event; empty = no jump


@dataclass
class BvpDef:
    """Conditions at positions of the interval instead of initial values: the problem is a boundary-value problem on [start, end]."""
    end: sp.Expr
    conditions: list                             # (position, residual in the state symbols, (lhs, rhs) as written)
    texts: list[str]
    guess: dict                                  # state index -> expression (starting guess for the numerical solution)
    guess_texts: list[str]
    unknowns: list = field(default_factory=list)        # parameters (variables) found together with the solution: eigenvalues, fitted constants
    theta_guess: dict = field(default_factory=dict)     # unknown -> starting guess
    free_end: Any = None                                # the unknown parameter that is the end of the interval (a free-boundary problem), else None
    where: list = field(default_factory=list)           # "start", "end" or "other" for each condition


@dataclass
class OdeSystem:
    title: str
    texts: list[str]
    initial_texts: list[str]
    method: str
    t: sp.Symbol
    start: sp.Expr
    dependents: list[sp.Symbol]
    orders: dict[sp.Symbol, int]
    state: list[sp.Symbol]                      # dummy symbols for y, y', ..., per dependent
    state_index: dict[tuple[sp.Symbol, int], int]
    rhs: list[sp.Expr]                          # d(state)/dt in terms of state, t and parameters
    ics: list[sp.Expr]                          # initial value of each state entry (in the calculation's variables)
    written: list[tuple[sp.Expr, sp.Expr]]      # the equations as entered, dependents shown as plain symbols
    params: list[sp.Symbol]
    inputs: list[sp.Symbol]                     # every declared symbol the solution depends on (including t)
    closed: dict[sp.Symbol, sp.Expr] | None = None
    events: list = field(default_factory=list)                        # EventDef
    bvp: BvpDef | None = None
    pre: dict[sp.Symbol, sp.Expr] = field(default_factory=dict)      # integrals without a closed form that do not involve the unknowns: evaluated once per run
    aux_count: int = 0                                               # hidden states standing for integrals of the unknowns (see _extract_integrals)
    why_numeric: str = ""
    fns: dict[sp.Symbol, Any] = field(default_factory=dict)
    lag_syms: list = field(default_factory=list)                      # symbols standing for delayed states y(t - tau) in the right-hand sides
    lag_info: list = field(default_factory=list)                      # (state index, tau expression) for each of them
    hidden: set = field(default_factory=set)                          # algebraic variables eliminated from the equations (still counted as used)
    fallback: dict[sp.Symbol, Any] = field(default_factory=dict)     # numerical-solution nodes for closed-form systems, used when the formula is singular at the given values
    _cache: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------ numbers

    @property
    def numeric(self) -> bool:
        return self.closed is None

    def _key(self, values: Mapping[sp.Symbol, float]) -> tuple:
        return tuple(float(values[s]) for s in self.inputs)

    def _compiled(self):
        if "f" not in self._cache:
            self._cache["f"] = fast_lambdify([self.t, *self.state, *self.lag_syms, *self.params], self.rhs)
            self._cache["tau"] = [fast_lambdify(self.inputs, tau) for _i, tau in self.lag_info]
            self._cache["g"] = [fast_lambdify([self.t, *self.state, *self.params], e.g) for e in self.events]
            self._cache["reset"] = [fast_lambdify([self.t, *self.state, *self.params], [e.reset.get(st, st) for st in self.state]) if e.reset else None for e in self.events]
            self._cache["ic"] = fast_lambdify(self.inputs, self.ics)
            self._cache["start"] = fast_lambdify(self.inputs, self.start)
            if self.bvp is not None:
                args = [self.t, *self.state, *self.params]
                self._cache["jac"] = fast_lambdify(args, sp.Matrix(self.rhs).jacobian(self.state).tolist())
                self._cache["end"] = fast_lambdify(self.inputs, self.bvp.end) if self.bvp.free_end is None else (lambda *a: math.nan)
                self._cache["ft"] = fast_lambdify(args, [sp.diff(e, self.t) for e in self.rhs]) if self.bvp.free_end is not None else None
                sa = [*self.state, *self.params]
                self._cache["bc"] = [(fast_lambdify(self.inputs, pos), fast_lambdify(sa, res),
                                      fast_lambdify(sa, [sp.diff(res, st) for st in self.state])) for pos, res, _w in self.bvp.conditions]
                self._cache["guess"] = fast_lambdify(self.inputs, [self.bvp.guess.get(i, sp.Integer(0)) for i in range(len(self.state))])
                tpos = self.inputs.index(self.t)
                profile: dict = {}
                for idx in range(len(self.state)):          # a guess that depends on the independent variable is a whole starting profile (derivatives follow from it)
                    g = self.bvp.guess.get(idx)
                    if g is None and idx > 0 and (idx - 1) in profile and self.state_index_rev[idx][0] == self.state_index_rev[idx - 1][0]:
                        g = sp.diff(profile[idx - 1], self.t)
                    if g is not None and g.has(self.t):
                        profile[idx] = g
                self._cache["profile"] = ({i: fast_lambdify(self.inputs, e) for i, e in profile.items()}, tpos) if profile else None
                us = self.bvp.unknowns
                self._cache["fth"] = fast_lambdify(args, sp.Matrix(self.rhs).jacobian(us).tolist() if us else [])
                self._cache["bcth"] = [fast_lambdify(sa, [sp.diff(res, u) for u in us]) for _p, res, _w in self.bvp.conditions]
                self._cache["theta0"] = fast_lambdify(self.inputs, [self.bvp.theta_guess[u] for u in us])
        return self._cache["f"], self._cache["ic"], self._cache["start"]

    @property
    def state_index_rev(self) -> dict:
        return {idx: key for key, idx in self.state_index.items()}

    def _initial(self, values: Mapping[sp.Symbol, float]) -> tuple[float, list[float]]:
        _f, ic, start = self._compiled()
        args = [float(values[s]) for s in self.inputs]
        return float(start(*args)), [float(v) for v in ic(*args)]

    def run(self, values: Mapping[sp.Symbol, float], outputs=()) -> OdeResult:
        """Integrate numerically from the start to ``t`` (memoised)."""
        key = (self._key(values), tuple(outputs))
        hit = self._cache.get(("run", key))
        if hit is not None:
            return hit
        if self.bvp is not None:
            res = self._run_bvp(values, outputs)
            if len(self._cache) > 40:
                self._cache.clear()
            self._cache[("run", key)] = res
            self._cache["last"] = res
            return res
        f, _ic, _start = self._compiled()
        t0, y0 = self._initial(values)
        params = [self._param(s, values) for s in self.params]
        t_end = float(values[self.t])
        if self.lag_syms:                                 # a delay equation: the method of steps keeps its own history
            args = [float(values[s]) for s in self.inputs]
            lags = [(i, float(g(*args))) for (i, _tau), g in zip(self.lag_info, self._cache["tau"])]
            res = dde(lambda tt, yy, lg: f(tt, *yy, *lg, *params), t0, y0, t_end, lags, outputs=outputs)
            if len(self._cache) > 40:
                self._cache.clear()
            self._cache[("run", key)] = res
            self._cache["last"] = res
            return res
        specs = [EventSpec((lambda tt, yy, gf=gf: float(gf(tt, *yy, *params))), {"either": 0, "rising": 1, "falling": -1}[e.direction], e.terminal,
                           (lambda tt, yy, rf=rf: list(rf(tt, *yy, *params))) if rf is not None else None)
                 for gf, rf, e in zip(self._cache["g"], self._cache["reset"], self.events)]
        t_run, y_run = t0, y0
        if t_end != t0 and _singular_at(lambda x, y: f(x, *y, *params), t0, y0):           # an axis or centre at the start: begin from the series there
            t_run, y_run = self._series_start(f, t0, y0, params, t_end)
        res = solve_ivp(lambda tt, yy: f(tt, *yy, *params), t_run, y_run, t_end, outputs=outputs, events=specs)
        if t_run != t0 and (not res.ts or res.ts[0] != t0):
            res.ts.insert(0, t0)
            res.ys.insert(0, list(y0))
        if len(self._cache) > 40:
            self._cache.clear()
        self._cache[("run", key)] = res
        self._cache["last"] = res
        return res

    def interval(self, values: Mapping[sp.Symbol, float]) -> tuple[float, float]:
        """The span the solution is computed over: start to the evaluation point for an initial-value problem, start to end for a boundary-value problem."""
        _f, _ic, start = self._compiled()
        args = [float(values[s]) for s in self.inputs]
        lo = float(start(*args))
        if self.bvp is not None and self.bvp.free_end is not None:
            return lo, self.unknown_value(self.bvp.unknowns.index(self.bvp.free_end), values)
        return lo, (float(self._cache["end"](*args)) if self.bvp is not None else float(values[self.t]))

    def _bvp_nodes(self, values: Mapping[sp.Symbol, float]):
        key = ("bvp", tuple(float(values[s]) for s in self.inputs if s != self.t))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        f, _ic, _start = self._compiled()
        jac, bc = self._cache["jac"], self._cache["bc"]
        args = [float(values[s]) for s in self.inputs]
        # the independent variable's own value is not part of the problem; any number will do for the lambdas that take all inputs
        unk = set(self.bvp.unknowns)
        params = [0.0 if s in unk else self._param(s, values) for s in self.params]       # unknown parameters are supplied by the solver
        n = len(self.state)
        us = self.bvp.unknowns
        pidx = [self.params.index(u) for u in us]

        def plist(th):
            out = list(params)
            for i, v in zip(pidx, th):
                out[i] = v
            return out
        fth_l, bcth = self._cache["fth"], self._cache["bcth"]
        if self.bvp.free_end is not None:
            sol = self._bvp_free(f, jac, plist, args, n)
            self._cache[key] = sol
            return sol
        lo, hi = float(self._cache["start"](*args)), float(self._cache["end"](*args))
        conds = [(float(p(*args)), (lambda y, th, r=r: float(r(*y, *plist(th)))), (lambda y, th, g=g: [float(v) for v in g(*y, *plist(th))]),
                  (lambda y, th, q=q: [float(v) for v in q(*y, *plist(th))])) for (p, r, g), q in zip(bc, bcth)]
        for pos, _r, _g, _q in conds:
            if not lo - 1e-12 * abs(hi - lo) <= pos <= hi + 1e-12 * abs(hi - lo):
                raise OdeError(f"a boundary condition is imposed at {pos:g} (SI), outside the interval from {lo:g} to {hi:g}")
        guess = [float(v) for v in self._cache["guess"](*args)]
        lo_user = lo
        theta0 = [float(v) for v in self._cache["theta0"](*args)]
        theta_probe = theta0
        # an axis or centre at the start (cylindrical, spherical: terms like y'/r) makes the equations 0/0 there: begin a hair inside, where the symmetry
        # condition y' = 0 differs from the true y' = y'' r by a negligible amount
        if _singular_at(lambda x, y: f(x, *y, *plist(theta_probe)), lo, guess):
            lo = lo + 1e-7 * (hi - lo)
            conds = [(lo if abs(pos - lo_user) <= 1e-12 * abs(hi - lo_user) else pos, r, g_, q) for pos, r, g_, q in conds]
        prof = self._cache["profile"]
        guess_fn = None
        if prof is not None:
            pf, tpos = prof

            def guess_fn(x, pf=pf, tpos=tpos, base=guess, args=args):
                a = list(args)
                a[tpos] = x
                return [float(pf[i](*a)) if i in pf else base[i] for i in range(n)]
        try:
            sol = _bvp.solve((lambda x, y, th: f(x, *y, *plist(th))), (lambda x, y, th: jac(x, *y, *plist(th))),
                             (lambda x, y, th: [[float(v) for v in row] for row in fth_l(x, *y, *plist(th))]), lo, hi, n, conds, guess, theta0, 8, guess_fn)
        except _bvp.BvpError as exc:
            raise OdeError(str(exc)) from None
        sol.start_user = lo_user
        self._cache[key] = sol
        return sol

    def _bvp_free(self, f, jac, plist, args, n):
        """A free-boundary problem: the end of the interval is one of the unknown parameters. With ``x = start + (L - start) s`` the problem lives on the fixed
        interval ``0 <= s <= 1``: ``dy/ds = (L - start) f(x, y)``, and L is found by the same Newton iteration as any unknown parameter (it needs one extra condition)."""
        fth_l, bcth, bc, ft = self._cache["fth"], self._cache["bcth"], self._cache["bc"], self._cache["ft"]
        kL = self.bvp.unknowns.index(self.bvp.free_end)
        lo = float(self._cache["start"](*args))
        conds = [(0.0 if w == "start" else 1.0, (lambda y, th, r=r: float(r(*y, *plist(th)))), (lambda y, th, g=g: [float(v) for v in g(*y, *plist(th))]),
                  (lambda y, th, q=q: [float(v) for v in q(*y, *plist(th))])) for (_p, r, g), q, w in zip(bc, bcth, self.bvp.where)]
        guess = [float(v) for v in self._cache["guess"](*args)]
        theta0 = [float(v) for v in self._cache["theta0"](*args)]
        if not theta0[kL] > lo:
            raise OdeError(f"the starting guess for the end of the interval ({theta0[kL]:g}) must be beyond the start ({lo:g})")

        def span(th):
            return max(th[kL] - lo, 1e-12 * max(abs(lo), 1.0))

        def f_s(s, y, th):
            d = span(th)
            return [d * float(v) for v in f(lo + d * s, *y, *plist(th))]

        def jac_s(s, y, th):
            d = span(th)
            return [[d * float(v) for v in row] for row in jac(lo + d * s, *y, *plist(th))]

        def fth_s(s, y, th):
            d = span(th)
            x, p = lo + d * s, plist(th)
            base, fx, fv = fth_l(x, *y, *p), self._cache["ft"](x, *y, *p), f(x, *y, *p)
            out = [[d * float(base[i][j]) for j in range(len(th))] for i in range(n)]
            for i in range(n):
                out[i][kL] += float(fv[i]) + d * s * float(fx[i])        # d/dL of (L - start) f(start + (L - start) s, y)
            return out
        try:
            sol = _bvp.solve(f_s, jac_s, fth_s, 0.0, 1.0, n, conds, guess, theta0, 8, None)
        except _bvp.BvpError as exc:
            raise OdeError(str(exc)) from None
        sol.start_user = lo
        sol.free_k = kL
        _ = ft
        return sol

    def unknown_value(self, k: int, values: Mapping[sp.Symbol, float]) -> float:
        """The k-th unknown parameter of a boundary-value problem (an eigenvalue, a fitted constant)."""
        return self._bvp_nodes(values).theta[k]

    def _run_bvp(self, values: Mapping[sp.Symbol, float], outputs=()) -> OdeResult:
        sol = self._bvp_nodes(values)
        x = float(values[self.t])
        if self.bvp.free_end is not None:                       # the solution lives on 0 <= s <= 1: map the positions both ways
            lo, hi = sol.start_user, sol.theta[sol.free_k]
            if not lo - 1e-9 * abs(hi - lo) <= x <= hi + 1e-9 * abs(hi - lo):
                raise OdeError(f"{self.t.name} = {x:g} (SI) lies outside the interval of the free-boundary problem, {lo:g} to {hi:g} (the end was found, not given)")
            to_s = lambda v: min(max((v - lo) / (hi - lo), 0.0), 1.0)
            ss = sorted({to_s(x), *[to_s(o) for o in outputs if lo <= o <= hi]})
            pts, ys, steps = sol.sample(ss)
            xs = [lo + (hi - lo) * p for p in pts]
            k = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
            xs.append(xs.pop(k))
            ys.append(ys.pop(k))
            return OdeResult(xs, ys, f"free-boundary problem: multiple shooting on a scaled interval (end found: {hi:g})", steps, 0, _bvp.RTOL, _bvp.ATOL,
                             notes=[f"Newton converged in {sol.iterations} iteration{'s' if sol.iterations != 1 else ''}, residual {sol.residual:.1e}"])
        lo, hi = getattr(sol, "start_user", sol.xs[0]), sol.xs[-1]
        if not lo - 1e-9 * abs(hi - lo) <= x <= hi + 1e-9 * abs(hi - lo):
            raise OdeError(f"{self.t.name} = {x:g} (SI) lies outside the interval of the boundary-value problem, {lo:g} to {hi:g}")
        x = min(max(x, lo), hi)
        inner = sol.xs[0]
        pts, ys, steps = sol.sample(sorted({max(x, inner), *[max(o, inner) for o in outputs if lo <= o <= hi]}))
        if inner > lo:                                  # the solution was started a hair inside the axis: label that point with the axis position
            pts = [lo if abs(p - inner) <= 1e-15 * max(abs(inner), 1.0) else p for p in pts]
            x = lo if abs(x - inner) <= 1e-7 * (hi - lo) * 1.0001 and x <= inner else x
        # the state at the requested point must come last for ``final``
        k = min(range(len(pts)), key=lambda i: abs(pts[i] - x))
        pts.append(pts.pop(k))
        ys.append(ys.pop(k))
        return OdeResult(pts, ys, f"multiple shooting over {sol.segments} segment{'s' if sol.segments != 1 else ''} (Newton, adaptive RK45 inside)", steps, 0, _bvp.RTOL, _bvp.ATOL,
                         notes=[f"Newton converged in {sol.iterations} iteration{'s' if sol.iterations != 1 else ''}, residual {sol.residual:.1e}"])

    def _series_start(self, f, t0: float, y0: list[float], params: list[float], t_end: float):
        """Start slightly off a singular point (y'/r terms at r = 0, as in the Lane–Emden equation): for each second-order quantity the series
        y = y0 + a d^2/2, y' = a d, with the curvature a found from the equation itself (it appears on both sides, since y'/r -> a)."""
        d = 1e-6 * (t_end - t0)
        y = list(y0)
        for (dep, j), idx in self.state_index.items():
            if j != 0 or self.orders[dep] != 2:
                continue

            def g(a, idx=idx):
                yt = list(y)
                yt[idx] = y0[idx] + a * d * d / 2
                yt[idx + 1] = a * d
                try:
                    return float(f(t0 + d, *yt, *params)[idx + 1]) - a
                except (ZeroDivisionError, ValueError, OverflowError):
                    return math.nan
            a0, a1 = 0.0, 1.0
            g0, g1 = g(a0), g(a1)
            for _ in range(30):
                if not (math.isfinite(g0) and math.isfinite(g1)) or g1 == g0:
                    break
                a2 = a1 - g1 * (a1 - a0) / (g1 - g0)
                a0, g0, a1, g1 = a1, g1, a2, g(a2)
                if abs(g1) <= 1e-14 * max(1.0, abs(a1)):
                    break
            if math.isfinite(a1):
                y[idx] = y0[idx] + a1 * d * d / 2
                y[idx + 1] = a1 * d
        return t0 + d, y

    def _param(self, s: sp.Symbol, values: Mapping[sp.Symbol, float]) -> float:
        if s in self.pre:       # an integral that has no closed form but does not involve the unknowns: integrate it numerically once
            try:
                return float(sp.N(self.pre[s].subs({k: sp.Float(v, 20) for k, v in values.items()}), 17))
            except (TypeError, ValueError) as exc:
                raise OdeError(f"could not evaluate an integral in the equations: {exc}") from None
        return float(values[s])

    def value(self, dependent: sp.Symbol, values: Mapping[sp.Symbol, float]) -> float:
        """Value of ``dependent`` at ``t`` (numeric solution)."""
        res = self.run(values)
        return res.final[self.state_index[(dependent, 0)]]

    def _bvp_event(self, k: int, values: Mapping[sp.Symbol, float]):
        """First position along the solved interval where event ``k``'s condition crosses zero (the way ``direction`` allows): ``(position, state)``."""
        from .numeric_ode import _crossing

        sol = self._bvp_nodes(values)
        f, _ic, _start = self._compiled()
        args = [float(values[s]) for s in self.inputs]
        free = self.bvp.free_end is not None
        lo = float(sol.start_user if hasattr(sol, "start_user") else sol.xs[0])
        hi = float(sol.theta[sol.free_k]) if free else sol.xs[-1]
        unk = list(self.bvp.unknowns)
        params = [self._param(s, values) if s not in unk else float(sol.theta[unk.index(s)]) for s in self.params]
        gf = self._cache["g"][k]
        direction = {"either": 0, "rising": 1, "falling": -1}[self.events[k].direction]

        def state_at(x):
            sx = (x - lo) / (hi - lo) if free else x
            pts, ys, _ = sol.sample([sx])
            return ys[0]

        def g(x):
            return float(gf(x, *state_at(x), *params))
        n = 400
        xs = [lo + (hi - lo) * i / n for i in range(n + 1)]
        gs = [g(x) for x in xs]
        for i in range(n):
            if gs[i] == 0:
                continue
            if _crossing(gs[i], gs[i + 1], direction):
                a, b, ga = xs[i], xs[i + 1], gs[i]
                for _ in range(60):                                 # bisection on the solved solution
                    m = 0.5 * (a + b)
                    gm = g(m)
                    if (gm < 0) == (ga < 0) and gm != 0:
                        a, ga = m, gm
                    else:
                        b = m
                    if abs(b - a) <= 1e-13 * max(abs(hi - lo), 1e-300):
                        break
                x = 0.5 * (a + b)
                return x, state_at(x)
        raise OdeError(f"the event '{self.events[k].title}' does not occur between {lo:g} and {hi:g} (SI) on the solved interval; check the condition")

    def event_value(self, k: int, kind: str, dep, values: Mapping[sp.Symbol, float]) -> float:
        """Time (``kind`` "time") or the value of ``dep`` at the first occurrence of event ``k`` between the start and ``t``."""
        if self.bvp is not None:
            pos, state = self._bvp_event(k, values)
            return pos if kind == "time" else state[self.state_index[(dep, 0)]]
        res = self.run(values)
        hit = next((h for h in res.events if h.index == k), None)
        if hit is None:
            raise OdeError(f"the event '{self.events[k].title}' does not occur between the start and {self.t.name} = {float(values[self.t]):g} (SI); "
                           f"increase {self.t.name} or check the condition")
        return hit.t if kind == "time" else hit.y[self.state_index[(dep, 0)]]

    def last_result(self) -> OdeResult | None:
        return self._cache.get("last")

    def trajectory(self, values: Mapping[sp.Symbol, float], n: int = 200, extra_times=()) -> tuple[list[float], dict[sp.Symbol, list[float]], dict]:
        """Times (SI) from the start to ``t`` and each dependent's value there; also the times in ``extra_times`` if they lie in between."""
        t0, t_end = self.interval(values)
        if self.events and self.bvp is None:                       # a terminal event ends the run early
            t_end = self.run(values).ts[-1]
        grid = [t0 + (t_end - t0) * i / n for i in range(n + 1)] if t_end != t0 else [t0]
        extra = list(extra_times) + ([float(values[self.t])] if self.bvp is not None else [])
        wanted = sorted(set(grid) | {x for x in extra if min(t0, t_end) <= x <= max(t0, t_end)}, reverse=t_end < t0)
        if self.closed is not None:
            try:
                return self._closed_trajectory(values, wanted)
            except (ZeroDivisionError, OverflowError, ValueError, ArithmeticError, OdeError):
                pass          # the formula is singular at these values (e.g. critical damping): integrate numerically instead
        return self._numeric_trajectory(values, wanted)

    def _closed_trajectory(self, values, wanted):
        syms = [self.t, *[s for s in self.inputs if s != self.t]]
        out: dict[sp.Symbol, list[float]] = {}
        for dep, expr in self.closed.items():
            fn = sp.lambdify(syms, expr, modules="mpmath")
            col = []
            for tv in wanted:
                z = complex(fn(tv, *[float(values[s]) for s in syms[1:]]))
                if abs(z.imag) > 1e-9 * max(abs(z.real), 1e-300) + 1e-12:
                    raise OdeError(f"the closed-form solution is complex at t = {tv:g}")
                col.append(z.real)
            out[dep] = col
        return wanted, out, {"method": "closed form (SymPy dsolve)", "steps": 0}

    def _numeric_trajectory(self, values, wanted):
        res = self.run(values, outputs=wanted)
        index = {round(t, 14): y for t, y in zip(res.ts, res.ys)}
        info_events = [{"index": h.index, "t": h.t, "values": {d.name: h.y[self.state_index[(d, 0)]] for d in self.dependents}} for h in res.events]
        cols: dict[sp.Symbol, list[float]] = {d: [] for d in self.dependents}
        times = []
        for tv in wanted:
            y = index.get(round(tv, 14))
            if y is None:
                continue
            times.append(tv)
            for d in self.dependents:
                cols[d].append(y[self.state_index[(d, 0)]])
        return times, cols, {"method": res.method, "steps": res.steps, "nfev": res.nfev, "rtol": res.rtol, "atol": res.atol, "notes": res.notes,
                             "events": info_events, "stopped_by": res.stopped_by}

    # ------------------------------------------------------------ display

    @property
    def condition_note(self) -> str:
        return "boundary condition" if self.bvp is not None else "initial condition"

    def condition_latex(self, names: dict) -> list[str]:
        out = []
        if self.bvp is not None:
            tn = names.get(self.t, str(self.t))
            out.append(rf"{tn} \in \left[{sp.latex(self.start, symbol_names=names)},\; {sp.latex(self.bvp.end, symbol_names=names)}\right]")
            for u in self.bvp.unknowns:
                out.append(rf"{names.get(u, str(u))}\ \text{{is found together with the solution}}")
            for pos, _res, written in self.bvp.conditions:
                if written is None:
                    continue
                a, b = written
                out.append(rf"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)} \quad \text{{at }}\; {tn} = {sp.latex(pos, symbol_names=names)}")
            return out
        start_tex = sp.latex(self.start, symbol_names=names)
        for (dep, j), idx in self.state_index.items():
            d = names.get(dep, str(dep))
            lhs = rf"{d}\left({start_tex}\right)" if j == 0 else rf"{d}^{{({j})}}\left({start_tex}\right)"
            out.append(rf"{lhs} = {sp.latex(self.ics[idx], symbol_names=names)}")
        return out

    def event_latex(self, names: dict) -> list[tuple[str, str]]:
        out = []
        for e in self.events:
            how = {"either": "crosses zero", "rising": "rising through zero", "falling": "falling through zero"}[e.direction]
            out.append((f"{sp.latex(e.written[0], symbol_names=names)} = {sp.latex(e.written[1], symbol_names=names)}",
                        f"event {e.title}: {how}" + ("; the integration stops here" if e.terminal else "")))
        return out

    def written_latex(self, names: dict) -> list[str]:
        return [f"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)}" for a, b in self.written]


# ---------------------------------------------------------------- numeric function node

def _make_fn(system: OdeSystem, dep: sp.Symbol, result: tuple, latex_name: str, index: int, evaluate=None, role=None):
    """A SymPy function ``ODE_k(inputs...)`` whose numerical value is the dependent at ``t`` (or, with ``evaluate``, another number derived
    from the integration, such as an event time); the engine evaluates it like any other expression."""
    evaluate_given = evaluate
    evaluate = evaluate or (lambda vals: system.value(dep, vals))

    def _eval_evalf(self, prec):
        vals = {}
        for s, a in zip(system.inputs, self.args):
            if not getattr(a, "is_number", False):
                return None
            vals[s] = float(a)
        try:
            return sp.Float(evaluate(vals), 17)
        except OdeError as exc:
            raise ArithmeticError(str(exc)) from None
        except (ArithmeticError, ValueError, TypeError) as exc:
            raise ArithmeticError(f"could not integrate the differential equation: {exc}") from None

    def _latex(self, printer, *args, **kw):
        inner = ", ".join(printer._print(a) for a in self.args)
        return rf"{{{latex_name}}}_{{\mathrm{{ODE}}}}\left({inner}\right)"

    attrs = {"_eval_evalf": _eval_evalf, "_latex": _latex, "_sliderule_result": result, "_sliderule_ode": system, "_sliderule_dep": dep, "_sliderule_plain": evaluate_given is None, "_sliderule_role": role or ("state",),
             "nargs": len(system.inputs), "_eval_is_real": lambda self: True}
    return type(f"ODE{index}_{dep.name}", (sp.Function,), attrs)


# ---------------------------------------------------------------- parsing

def _friendly(message: str) -> str:
    """Show the internal state symbols (T__0, x__1) as the quantity and its derivative."""
    import re

    return re.sub(r"\b(\w+?)__(\d+)\b", lambda m: m.group(1) if m.group(2) == "0" else f"d{m.group(2) if m.group(2) != '1' else ''}{m.group(1)}/dt{m.group(2) if m.group(2) != '1' else ''}", message)


def _calls(tree: ast.AST, name: str):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name]


def _dependents(texts: list[str], ind: str) -> list[str]:
    seen: list[str] = []
    from .model import _EQ_SPLIT

    for text in texts:
        for side in _EQ_SPLIT.split(text):
            try:
                tree = ast.parse(side.strip().replace("^", "**"), mode="eval")
            except SyntaxError:
                continue
            for call in _calls(tree, "diff"):
                a = call.args
                if len(a) >= 2 and isinstance(a[0], ast.Name) and isinstance(a[1], ast.Name) and a[1].id == ind and a[0].id not in seen:
                    seen.append(a[0].id)
    return seen


def _split(text: str) -> tuple[str, str]:
    from .model import _EQ_SPLIT

    parts = _EQ_SPLIT.split(text)
    if len(parts) != 2:
        raise OdeSpecError(f"an equation needs exactly one '=': {text!r}")
    return parts[0], parts[1]


def _parse(text: str, local: dict, custom: bool, ns: dict) -> sp.Expr:
    from .model import _TRANSFORMS

    if custom:
        from .safeparse import check_expression

        check_expression(text, ns)
    return parse_expr(text, local_dict=local, transformations=_TRANSFORMS, evaluate=True)


def build(spec: Mapping[str, Any], calc, ns: dict, env: dict, custom: bool, index: int) -> tuple[OdeSystem, list]:
    """Validate and build one ODE entry. Returns the system and the algebraic :class:`Equation` objects that stand for it."""
    from .model import Equation

    if not isinstance(spec, Mapping):
        raise OdeSpecError("each differential equation must be an object")
    if isinstance(spec.get("equations"), list) and any(__import__("re").search(r"\bxi[123]\b", str(q)) for q in spec["equations"]):
        from . import sde                               # white-noise terms: a stochastic differential equation, see sde.py

        return sde.build(spec, calc, ns, env, custom, index)
    if isinstance(spec.get("equations"), list) and any("fdiff(" in str(q) for q in spec["equations"]):
        from . import fode                              # Caputo fractional derivatives: see fode.py

        return fode.build(spec, calc, ns, env, custom, index)
    if spec.get("scheme") not in (None, "", "conservative"):
        raise OdeSpecError("'scheme' can only be \"conservative\" (shock-capturing finite volumes for equations in conservation form)")
    if spec.get("scheme") == "conservative" and spec.get("time") not in (None, ""):
        from . import pdeflux                           # conservation laws with shocks: see pdeflux.py

        return pdeflux.build(spec, calc, ns, env, custom, index)
    n_eq = len(spec.get("equations") or []) if isinstance(spec.get("equations"), list) else 1
    if (spec.get("time") in (None, "") and (spec.get("third") not in (None, "") or spec.get("cutouts"))) or (spec.get("time") not in (None, "") and (spec.get("second") not in (None, "") or spec.get("third") not in (None, "") or n_eq > 1 or spec.get("periodic") or spec.get("sources") or spec.get("moving"))):
        from . import pdemulti                          # coupled fields, or a time-dependent problem on a rectangle: see pdemulti.py

        return pdemulti.build(spec, calc, ns, env, custom, index)
    if spec.get("second") not in (None, ""):           # a steady problem on a rectangle: see pde2d.py
        from . import pde2d

        return pde2d.build(spec, calc, ns, env, custom, index)
    if spec.get("time") not in (None, ""):             # a partial differential equation in space and time: see pde.py
        from . import pde

        return pde.build(spec, calc, ns, env, custom, index)
    title = str(spec.get("title") or "Differential equation").strip()[:100]
    ind = spec.get("independent")
    if not isinstance(ind, str) or ind not in calc.by_key or calc.by_key[ind].is_constant:
        raise OdeSpecError(f"'independent' must name one of the variables (the quantity the equation differentiates by, such as time), got {ind!r}")
    t = calc.by_key[ind].symbol
    texts = spec.get("equations")
    if not isinstance(texts, list) or not texts or not all(isinstance(x, str) and x.strip() for x in texts):
        raise OdeSpecError("'equations' must be a non-empty list of equations such as 'diff(y, t) = -k*y'")
    if len(texts) > MAX_EQUATIONS:
        raise OdeSpecError(f"more than {MAX_EQUATIONS} equations in one system")
    method = spec.get("method", "auto") or "auto"
    if method not in METHODS:
        raise OdeSpecError(f"'method' must be one of {', '.join(METHODS)}")
    bvp_mode = spec.get("boundary") not in (None, [], "")
    if bvp_mode and spec.get("initial"):
        raise OdeSpecError("a boundary-value problem (with 'boundary' conditions) takes no 'initial' values")
    if bvp_mode and not str(spec.get("end") or "").strip():
        raise OdeSpecError("a boundary-value problem needs an 'end' (where the interval ends), e.g. 'L'")
    deps_names = _dependents(texts, ind)
    if not deps_names:
        raise OdeSpecError(f"no derivative of the form diff(y, {ind}) found; write the unknown quantity first, e.g. diff(y, {ind}) = -k*y")
    for n in deps_names:
        v = calc.by_key.get(n)
        if v is None or v.is_constant or n == ind:
            raise OdeSpecError(f"{n!r} is differentiated but is not a (non-constant) variable of this calculation")
    alg_names = spec.get("algebraic") or []
    if isinstance(alg_names, str):
        alg_names = [x.strip() for x in alg_names.split(",") if x.strip()]
    if not isinstance(alg_names, list) or len(alg_names) > MAX_ALGEBRAIC or not all(isinstance(n, str) for n in alg_names):
        raise OdeSpecError(f"'algebraic' lists up to {MAX_ALGEBRAIC} variable names that are fixed at every instant by an algebraic equation (a constraint without a derivative)")
    for n in alg_names:
        v = calc.by_key.get(n)
        if v is None or v.is_constant or n == ind or n in deps_names:
            raise OdeSpecError(f"algebraic variable {n!r} must be a (non-constant) variable of this calculation that is not differentiated or the independent variable")
    if len(deps_names) + len(alg_names) != len(texts):
        raise OdeSpecError(f"{len(texts)} equation(s) but {len(deps_names)} differentiated quantit{'y' if len(deps_names) == 1 else 'ies'} ({', '.join(deps_names)})"
                           + (f" and {len(alg_names)} algebraic variable{'s' if len(alg_names) != 1 else ''} ({', '.join(alg_names)})" if alg_names else "")
                           + ": give one equation per unknown" + ("" if alg_names else " (a constraint without a derivative needs its variable listed under 'algebraic')"))
    alg_syms = [calc.by_key[n].symbol for n in alg_names]
    deps = [calc.by_key[n].symbol for n in deps_names]
    funcs = {n: sp.Function(n)(t) for n in deps_names}
    start = _parse(str(spec.get("start", "0")), ns, custom, ns) if str(spec.get("start", "0")).strip() else sp.Integer(0)
    lag_classes: dict = {}

    def _delay(f, tau):
        """``delay(y, tau)``: the value of the unknown ``y`` a time ``tau`` ago (before the start it keeps its initial value)."""
        if not (isinstance(f, AppliedUndef) and f.func.__name__ in deps_names):
            raise OdeSpecError(f"delay(y, tau): y must be one of the differentiated quantities ({', '.join(deps_names)})")
        nm = f.func.__name__
        if nm not in lag_classes:
            lag_classes[nm] = type(f"{nm}__lag", (sp.Function,), {
                "nargs": 1, "_sliderule_result": env[calc.by_key[nm].symbol], "_sliderule_arg": env[t],
                "_latex": lambda self, printer, *a, _n=nm, **k: rf"{{{_n}}}\left({{{t.name}}} - {printer._print(self.args[0])}\right)"})
        return lag_classes[nm](sp.sympify(tau))

    ns = {**ns, "delay": _delay}
    local = {**ns, **funcs}
    lag_registry: dict = {}

    from .safeparse import bound_names

    sides: list[tuple[sp.Expr, sp.Expr]] = []
    for text in texts:
        lt, rt = _split(text)
        loc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(text) if n not in local}}   # integration variables are dummies
        sides.append((_parse(lt, loc, custom, ns), _parse(rt, loc, custom, ns)))
    original_sides = sides
    sides, aug, pre, pre_dims = _extract_integrals(sides, funcs, deps_names, t, start, custom, env, lag_classes)
    for a, b in sides:
        for d in (a - b).atoms(sp.Derivative):
            if not isinstance(d.expr, AppliedUndef) or any(v != t for v, _n in d.variable_count):
                raise OdeSpecError(f"{d}: differentiate the unknown quantities directly with respect to {ind}, e.g. diff(y, {ind})")
    orders: dict[sp.Symbol, int] = {}
    for dsym, n in zip(deps, deps_names):
        o = max([cnt for a, b in sides for d in (a - b).atoms(sp.Derivative) if d.expr.func.__name__ == n for _v, cnt in d.variable_count] or [0])
        if o < 1 or o > MAX_ORDER:
            raise OdeSpecError(f"{n}: order {o} not supported (1 to {MAX_ORDER})")
        orders[dsym] = o
    if sum(orders.values()) > MAX_STATE:
        raise OdeSpecError(f"too many state variables (limit {MAX_STATE})")

    # state symbols and the explicit form  d(highest)/dt = rhs(state, t, params)
    state: list[sp.Symbol] = []
    state_index: dict[tuple[sp.Symbol, int], int] = {}
    top = {}
    for dsym, n in zip(deps, deps_names):
        for j in range(orders[dsym]):
            s = sp.Symbol(f"{n}__{j}", real=True)
            state_index[(dsym, j)] = len(state)
            state.append(s)
        top[dsym] = sp.Symbol(f"{n}__top", real=True)
    aug_state = {zf: sp.Symbol(f"{zf.func.__name__}", real=True) for zf, _ in aug}      # hidden states: integrals of the unknowns
    if sum(orders.values()) + len(aug) > MAX_STATE:
        raise OdeSpecError(f"too many state variables (limit {MAX_STATE}, integrals of the unknowns count as one each)")

    def to_state(expr: sp.Expr) -> sp.Expr:
        for a in sorted((x for x in expr.atoms(sp.Function) if type(x) in lag_classes.values()), key=str):
            key = (a.func.__name__[:-5], a.args[0])
            if key not in lag_registry:
                lag_registry[key] = sp.Symbol(f"{key[0]}__lag{len(lag_registry)}", real=True)
            expr = expr.xreplace({a: lag_registry[key]})
        for dsym, n in zip(deps, deps_names):
            for d in sorted(expr.atoms(sp.Derivative), key=lambda e: -sum(c for _v, c in e.variable_count)):
                if d.expr.func.__name__ != n:
                    continue
                j = sum(c for _v, c in d.variable_count)
                expr = expr.xreplace({d: top[dsym] if j == orders[dsym] else state[state_index[(dsym, j)]]})
        for dsym, n in zip(deps, deps_names):
            expr = expr.xreplace({funcs[n]: state[state_index[(dsym, 0)]]})
        return expr.xreplace(aug_state)

    residuals = [to_state(a - b) for a, b in sides]
    for r in residuals:
        if r.atoms(AppliedUndef) or r.atoms(sp.Derivative):
            raise OdeSpecError("the equations use a differentiated quantity in a way that cannot be reduced to a first-order system")
    try:
        sols = sp.solve(residuals, [*[top[d] for d in deps], *alg_syms], dict=True)
    except Exception as exc:  # noqa: BLE001 - sympy raises many things for unsolvable input
        raise OdeSpecError(f"cannot solve the equations for the highest derivatives: {exc}") from None
    if len(sols) != 1 or any(top[d] not in sols[0] for d in deps) or any(a not in sols[0] for a in alg_syms):
        raise OdeSpecError("each equation must be solvable for the highest derivative of its quantity (e.g. diff(y, t) = ...) and each constraint for its algebraic variable, and the system must determine them uniquely"
                           + (" (a constraint with two solutions, such as a square root, is not unique)" if alg_syms else ""))
    sol = sols[0]
    rhs: list[sp.Expr] = []
    for dsym in deps:
        for j in range(orders[dsym]):
            rhs.append(state[state_index[(dsym, j + 1)]] if j + 1 < orders[dsym] else sol[top[dsym]])
    for e in rhs:
        if any(top[d] in e.free_symbols for d in deps):
            raise OdeSpecError("the equations are implicit in the highest derivatives")
    for zf, integrand in aug:                      # d(integral)/dt = integrand(t): a hidden state that starts at 0
        state.append(aug_state[zf])
        rhs.append(to_state(integrand))
    def parse_ic_lhs(text: str) -> tuple[sp.Symbol, int]:
        try:
            node = ast.parse(text.replace("^", "**"), mode="eval").body
        except SyntaxError:
            raise OdeSpecError(f"cannot read the initial condition {text!r}") from None
        if isinstance(node, ast.Name) and node.id in deps_names:
            return calc.by_key[node.id].symbol, 0
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "diff" and len(node.args) in (2, 3)
                and isinstance(node.args[0], ast.Name) and node.args[0].id in deps_names and isinstance(node.args[1], ast.Name) and node.args[1].id == ind):
            order = 1
            if len(node.args) == 3:
                a = node.args[2]
                if not (isinstance(a, ast.Constant) and isinstance(a.value, int)):
                    raise OdeSpecError(f"cannot read the order in {text!r}")
                order = a.value
            return calc.by_key[node.args[0].id].symbol, order
        raise OdeSpecError(f"an initial condition's left side must be one of {', '.join(deps_names)} or diff({deps_names[0]}, {ind}) style, got {text!r}")

    declared = {v.symbol for v in calc.variables}
    event_defs: list[EventDef] = []
    claimed: set = {t, *deps}                  # event outputs must be variables the equations do not already use
    for ke, ev in enumerate(spec.get("events") or []):
        if not isinstance(ev, Mapping) or not isinstance(ev.get("when"), str) or not ev["when"].strip():
            raise OdeSpecError("each event needs a 'when' condition such as 'h = 0' or 'T - Tmax'")
        if ke >= MAX_EVENTS:
            raise OdeSpecError(f"at most {MAX_EVENTS} events per system")
        direction = ev.get("direction") or "either"
        if direction not in ("either", "rising", "falling"):
            raise OdeSpecError("an event's 'direction' must be either, rising or falling")
        parts = [x for x in __import__("re").split(r"(?<![<>=!])=(?!=)", ev["when"]) if x.strip()]
        if len(parts) > 2:
            raise OdeSpecError(f"an event condition has at most one '=': {ev['when']!r}")
        loc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(ev["when"]) if n not in local}}
        sides_e = [_parse(p, loc, custom, ns) for p in parts]
        if len(sides_e) == 1:
            sides_e.append(sp.Integer(0))
        ge = to_state(sides_e[0] - sides_e[1])
        if ge.atoms(AppliedUndef) or ge.atoms(sp.Derivative) or ge.has(sp.Integral):
            raise OdeSpecError(f"the event condition {ev['when']!r} must use only the quantities, their derivatives (diff(y, {ind})) and parameters")
        show = {funcs[n]: calc.by_key[n].symbol for n in deps_names}
        tvar = ev.get("time")
        time_sym = None
        if tvar not in (None, ""):
            if tvar not in calc.by_key or calc.by_key[tvar].is_constant or calc.by_key[tvar].symbol in claimed:
                raise OdeSpecError(f"event {ke + 1}: 'time' must name a free variable of this calculation that is not used for anything else, got {tvar!r}")
            time_sym = calc.by_key[tvar].symbol
            claimed.add(time_sym)
        vvars: dict = {}
        for dn, vn in (ev.get("values") or {}).items():
            if dn not in deps_names:
                raise OdeSpecError(f"event {ke + 1}: values: {dn!r} is not one of the differentiated quantities ({', '.join(deps_names)})")
            if vn not in calc.by_key or calc.by_key[vn].is_constant or calc.by_key[vn].symbol in claimed:
                raise OdeSpecError(f"event {ke + 1}: values: {vn!r} must be a free variable of this calculation that is not used for anything else")
            vvars[calc.by_key[dn].symbol] = calc.by_key[vn].symbol
            claimed.add(calc.by_key[vn].symbol)
        if bvp_mode and ev.get("terminal"):
            raise OdeSpecError(f"event {ke + 1}: in a boundary-value problem an event marks the first position where the condition crosses zero; it cannot stop the run")
        resets: dict = {}
        if ev.get("reset"):
            if bvp_mode or not isinstance(ev["reset"], Mapping):
                raise OdeSpecError(f"event {ke + 1}: 'reset' is a mapping such as {{\"vy\": \"-e*vy\"}} (initial-value problems only)")
            if ev.get("terminal"):
                raise OdeSpecError(f"event {ke + 1}: an event either stops the run (terminal) or makes the state jump (reset), not both")
            for lhs_text, rhs_text in ev["reset"].items():
                dep_sym, order = parse_ic_lhs(str(lhs_text))
                idx = state_index.get((dep_sym, order))
                if idx is None:
                    raise OdeSpecError(f"event {ke + 1}: reset: {lhs_text} is not a state of the system (orders: " + ", ".join(f"{n} {orders[calc.by_key[n].symbol]}" for n in deps_names) + ")")
                new_pre = _parse(str(rhs_text), loc, custom, ns)
                shown_new = new_pre.xreplace(show)
                try:
                    dn, _un = analyze(shown_new, env)
                    dq = calc.by_key[dep_sym.name].dim / (env[t][0] ** order if order else DIMENSIONLESS)
                except Exception as exc:
                    raise OdeSpecError(f"event {ke + 1}: reset of {lhs_text}: {exc}") from None
                if dn != dq:
                    raise OdeSpecError(f"event {ke + 1}: reset of {lhs_text}: the new value has dimension [{dn}] but {lhs_text} is [{dq}]")
                new_state = to_state(new_pre)
                if new_state.atoms(AppliedUndef) or new_state.atoms(sp.Derivative) or new_state.has(sp.Integral):
                    raise OdeSpecError(f"event {ke + 1}: reset of {lhs_text} may use only the quantities, their derivatives and parameters")
                resets[state[idx]] = new_state
        event_defs.append(EventDef(str(ev.get("title") or f"event {ke + 1}")[:80], ge, (sides_e[0].xreplace(show), sides_e[1].xreplace(show)), direction,
                                   bool(ev.get("terminal", False)), time_sym, vvars, resets))
    if event_defs and method == "symbolic":
        raise OdeSpecError("events need numerical integration; use method 'auto' or 'numeric'")
    bvp_def: BvpDef | None = None
    if bvp_mode:
        unknown_names = spec.get("unknowns") or []
        if isinstance(unknown_names, str):
            unknown_names = [q.strip() for q in unknown_names.replace(",", "\n").split("\n") if q.strip()]
        if not isinstance(unknown_names, list) or not all(isinstance(q, str) for q in unknown_names) or len(unknown_names) > 4:
            raise OdeSpecError("'unknowns' must be a list of at most 4 variable names (parameters found together with the solution)")
        unknown_syms: dict = {}
        for un in unknown_names:
            v_ = calc.by_key.get(un)
            if v_ is None or v_.is_constant or v_.symbol in (t, *deps) or un in unknown_syms:
                raise OdeSpecError(f"unknown parameter {un!r} must be a free variable of this calculation that the equations do not differentiate")
            unknown_syms[un] = v_.symbol
        bvp_def = _parse_bvp(spec, calc, ns, custom, funcs, deps_names, deps, local, t, start, state, state_index, top, sol, to_state, parse_ic_lhs, aug, ind, unknown_syms)
    lag_syms = list(lag_registry.values())
    aug_by_name = {zf.func.__name__: aug_state[zf] for zf, _ in aug}
    lag_info = [((state_index[(calc.by_key[n].symbol, 0)] if n in calc.by_key else state.index(aug_by_name[n])), tau) for (n, tau) in lag_registry]
    if lag_registry:
        if event_defs or bvp_mode:
            raise OdeSpecError("delays (delay(y, tau)) are for initial-value problems without events")
        for (n, tau) in lag_registry:
            if tau.atoms(AppliedUndef) or any(s not in declared or s in deps or s == t for s in tau.free_symbols):
                raise OdeSpecError(f"the delay {tau} must be a constant: an expression of the calculation's parameters, not of the unknowns or {ind}")
    params = sorted({s for e in [*rhs, *[ev.g for ev in event_defs], *[x for ev in event_defs for x in ev.reset.values()], *[tau for _i, tau in lag_info], *(bvp_def_symbols(bvp_def) if bvp_def else [])]
                     for s in e.free_symbols if s not in state and s != t and s not in lag_syms}, key=lambda s: s.name)
    for s in params:
        if s not in declared and s not in pre:
            raise OdeSpecError(f"{s} is not a variable of this calculation")
    unknown_set = set(bvp_def.unknowns) if bvp_def is not None else set()

    # initial conditions and start
    initial_texts = spec.get("initial") or []
    if not isinstance(initial_texts, list) or not all(isinstance(x, str) for x in initial_texts):
        raise OdeSpecError("'initial' must be a list of conditions such as 'y = y0'")
    ics: dict[tuple[sp.Symbol, int], sp.Expr] = {}
    for text in ([] if bvp_mode else initial_texts):
        lt, rt = _split(text)
        key = parse_ic_lhs(lt.strip())
        if key not in state_index:
            raise OdeSpecError(f"{text!r}: {key[0]} has order {orders[key[0]]}, so its initial values are for derivatives 0 to {orders[key[0]] - 1}")
        if key in ics:
            raise OdeSpecError(f"initial value of {lt.strip()} given twice")
        ics[key] = _parse(rt, ns, custom, ns)
    missing = [k for k in state_index if k not in ics] if not bvp_mode else []
    if bvp_mode:
        ics = {k: sp.Integer(0) for k in state_index}          # placeholders: the numerical solution finds the starting state itself
    if missing:
        raise OdeSpecError("missing initial value for " + ", ".join(f"{d}" if j == 0 else f"diff({d}, {ind}{'' if j == 1 else f', {j}'})" for d, j in missing))
    ic_list = [ics[k] for k in state_index] + [sp.Integer(0)] * len(aug)

    # dimensions
    dim_t, unit_t = env[t]
    genv = dict(env)
    genv.update(pre_dims)
    for (dsym, j), idx in state_index.items():
        dd, ud = env[dsym]
        genv[state[idx]] = (dd / dim_t ** j, ud / unit_t ** j)
    for (n, _tau), sym in lag_registry.items():
        if n in calc.by_key:
            genv[sym] = env[calc.by_key[n].symbol]                  # a delayed value has the dimension of the quantity
    try:
        n_dep_states = len(state) - len(aug)
        for off in range(len(aug)):                # an integral of the unknowns has the dimension of its integrand times the independent variable
            di, ui = analyze(rhs[n_dep_states + off], genv)
            genv[state[n_dep_states + off]] = (di * dim_t, ui * unit_t)
        for (n, _tau), sym in lag_registry.items():
            if n not in calc.by_key:
                genv[sym] = genv[aug_by_name[n]]                    # a delayed copy of an integral state
        for (dsym, j), idx in state_index.items():
            if ic_list[idx] == 0:          # a literal zero is valid in any dimension
                continue
            di, _ = analyze(ic_list[idx], genv)
            if di != genv[state[idx]][0]:
                raise DimensionError(f"initial value of {dsym.name}{'' if j == 0 else f' derivative {j}'} has dimension [{di}], expected [{genv[state[idx]][0]}]")
        ds, _ = analyze(start, env)
        if start != 0 and ds != dim_t:
            raise DimensionError(f"the start of the independent variable has dimension [{ds}], expected [{dim_t}]")
        for (_n, tau) in lag_registry:
            dtau, _ = analyze(tau, env)
            if dtau != dim_t:
                raise DimensionError(f"a delay has dimension [{dtau}] but must be a [{dim_t}] (like {ind})")
        k = 0
        for dsym in deps:
            n = orders[dsym]
            dr, _ = analyze(rhs[k + n - 1], genv)
            want = env[dsym][0] / dim_t ** n
            if dr != want and rhs[k + n - 1] != 0:       # a literal zero rate (a quantity held constant between events) fits any dimension
                raise DimensionError(f"the right-hand side for the derivative of {dsym.name} has dimension [{dr}], expected [{want}]")
            k += n
        if bvp_def is not None:
            _check_bvp_dims(bvp_def, genv, env, state, dim_t, state_index)
        for ev in event_defs:
            analyze(ev.g, genv)                                 # the condition must be dimensionally consistent (its own dimension is free)
            if ev.time_var is not None and env[ev.time_var][0] != dim_t:
                raise DimensionError(f"the event time variable {ev.time_var.name} has dimension [{env[ev.time_var][0]}], expected [{dim_t}]")
            for dsym, vsym in ev.value_vars.items():
                if env[vsym][0] != env[dsym][0]:
                    raise DimensionError(f"{vsym.name} (state at the event) has dimension [{env[vsym][0]}] but {dsym.name} is [{env[dsym][0]}]")
    except DimensionError as exc:
        raise OdeSpecError(f"{title}: {_friendly(str(exc))}") from None

    inputs = sorted({t, *[s for s in params if s not in pre and s not in unknown_set], *[s for e in ic_list for s in e.free_symbols], *start.free_symbols,
                     *[s for e in pre.values() for s in e.free_symbols if s in declared],
                     *[s for ev in event_defs for s in ev.g.free_symbols if s in declared],
                     *[s for e in (bvp_def_symbols(bvp_def) if bvp_def else []) for s in e.free_symbols if s in declared and s not in unknown_set]}, key=lambda s: s.name)
    for s in inputs:
        if s not in declared:
            raise OdeSpecError(f"{s} is not a variable of this calculation")
    written = [(a.xreplace({funcs[n]: calc.by_key[n].symbol for n in deps_names}), b.xreplace({funcs[n]: calc.by_key[n].symbol for n in deps_names})) for a, b in original_sides]
    # the unevaluated Derivative of a plain symbol is only for display, so keep the original derivative objects but with symbols inside
    system = OdeSystem(title, [t_.strip() for t_ in texts], [x.strip() for x in initial_texts], method, t, start, deps, orders, state, state_index,
                       rhs, ic_list, written, params, inputs)
    system.pre = pre
    system.aux_count = len(aug)
    system.events = event_defs
    system.bvp = bvp_def
    system.hidden = set(alg_syms)                   # algebraic variables: eliminated, internal to the system
    system.lag_syms, system.lag_info = lag_syms, lag_info

    # ---- closed form attempt
    if bvp_def is not None and bvp_def.unknowns:
        if method == "symbolic":
            raise OdeSpecError(f"{title}: unknown parameters (eigenvalues, fitted constants) are found numerically; use method 'auto' or 'numeric'")
        system.why_numeric = "unknown parameters are found together with the solution (an eigenvalue or fitting problem), which needs the numerical solver"
    elif bvp_def is not None:
        if method == "numeric" or event_defs:
            system.why_numeric = "numerical solution was requested" if method == "numeric" else "events (a position where a condition is met) are located on the numerical solution"
        else:
            system.closed, system.why_numeric = _try_closed_form_bvp(system, sides, funcs, deps_names, calc, custom)
            if system.closed is None and method == "symbolic":
                raise OdeSpecError(f"{title}: no closed-form solution was found ({system.why_numeric}); use method 'auto' or 'numeric' to solve it numerically")
    elif event_defs:
        system.why_numeric = "events (stopping or marking where a condition is met) need numerical integration"
    elif lag_syms:
        if method == "symbolic":
            raise OdeSpecError(f"{title}: a delay equation is integrated numerically (method of steps); use method 'auto' or 'numeric'")
        system.why_numeric = "a delay differential equation is integrated numerically by the method of steps (the history is kept and interpolated)"
    elif alg_syms:
        if method == "symbolic":
            raise OdeSpecError(f"{title}: a system with algebraic constraints is integrated numerically; use method 'auto' or 'numeric'")
        system.why_numeric = "the algebraic constraints are eliminated and the remaining differential equations integrated numerically"
    elif method != "numeric":
        system.closed, system.why_numeric = _try_closed_form(system, sides, funcs, deps_names, calc, env, custom, aug)
        if system.closed is None and method == "symbolic":
            raise OdeSpecError(f"{title}: no closed-form solution was found ({system.why_numeric}); use method 'auto' or 'numeric' to integrate it numerically")
    else:
        system.why_numeric = "numerical integration was requested"

    # ---- the algebraic equations that stand for the system
    eqs: list = []
    for k, dsym in enumerate(deps):
        label = f"{title}: {dsym.name}" if len(deps) > 1 else title
        dim, unit = env[dsym]
        fn = _make_fn(system, dsym, (dim, unit), calc.by_key[dsym.name].latex or dsym.name, index * 10 + k)
        if system.closed is not None:
            rhs_expr = system.closed[dsym]
            system.fallback[dsym] = fn
        else:
            system.fns[dsym] = fn
            rhs_expr = fn(*system.inputs)
        text = f"{dsym.name} = " + ("closed form of " if system.closed is not None else "numerical solution of ") + f"{'; '.join(texts)}"
        eq = Equation(label, text, dsym, rhs_expr, frozenset({dsym, *rhs_expr.free_symbols}), None)
        eq.ode = system
        eqs.append(eq)
        if system.closed is not None:
            try:
                check_equation(dsym, rhs_expr, env)
            except DimensionError as exc:
                raise OdeSpecError(f"{title}: the closed-form solution is not dimensionally consistent ({exc})") from None
    if bvp_def is not None:
        for ku, u in enumerate(bvp_def.unknowns):
            dim, unit = env[u]
            fn = _make_fn(system, u, (dim, unit), calc.by_key[u.name].latex or u.name, index * 10 + 8 + ku, lambda vals, ku=ku: system.unknown_value(ku, vals), role=("unknown", ku))
            eq = Equation(f"{title}: {u.name}", f"{u.name} = unknown parameter found together with the solution of {'; '.join(texts)}", u, fn(*system.inputs),
                          frozenset({u, *system.inputs}), None)
            eq.ode = system
            eqs.append(eq)
    for ke, ev in enumerate(event_defs):
        if ev.time_var is not None:
            dim, unit = env[ev.time_var]
            fn = _make_fn(system, ev.time_var, (dim, unit), calc.by_key[ev.time_var.name].latex or ev.time_var.name, index * 10 + 5 + ke * 3,
                          lambda vals, ke=ke: system.event_value(ke, "time", None, vals), role=("event_time", ke))
            eq = Equation(f"{title}: {ev.title} (time)", f"{ev.time_var.name} = time of event {ev.title} in {'; '.join(texts)}", ev.time_var, fn(*system.inputs),
                          frozenset({ev.time_var, *system.inputs}), None)
            eq.ode = system
            eqs.append(eq)
        for dsym, vsym in ev.value_vars.items():
            dim, unit = env[vsym]
            fn = _make_fn(system, vsym, (dim, unit), calc.by_key[vsym.name].latex or vsym.name, index * 10 + 6 + ke * 3,
                          lambda vals, ke=ke, dsym=dsym: system.event_value(ke, "value", dsym, vals), role=("event_value", ke, dsym.name))
            eq = Equation(f"{title}: {ev.title} ({dsym.name})", f"{vsym.name} = {dsym.name} at event {ev.title} in {'; '.join(texts)}", vsym, fn(*system.inputs),
                          frozenset({vsym, *system.inputs}), None)
            eq.ode = system
            eqs.append(eq)
    return system, eqs


def _extract_integrals(sides, funcs, deps_names, t, start, custom: bool, env, lag_classes=None):
    """Deal with ``integrate(...)`` inside the equations.

    * not involving the unknowns and not depending on ``t``: evaluate (closed form, or numerically once per run -> a parameter symbol);
    * from the start to ``t``: closed form if SymPy finds one, otherwise a hidden extra state ``z' = integrand, z(start) = 0`` (works even
      when the integrand contains the unknowns, e.g. an integral controller);
    * a sliding window ``integrate(f, (s, t - a, t - b))`` with constant ``a`` and ``b``: the hidden state ``z`` of the integral from the start, written ``z(t - b) - z(t - a)``
      (delayed copies of the state, see ``delay``); the integrand is taken as zero before the start;
    * anything else (variable limits that are not of the form ``t - constant``) is refused.
    Returns ``(sides, aug, pre, pre_dims)``; ``aug`` is a list of ``(function z(t), integrand(t))``.
    """
    aug: list[tuple[Any, sp.Expr]] = []
    pre: dict[sp.Symbol, sp.Expr] = {}
    pre_dims: dict[sp.Symbol, tuple] = {}
    counter = [0]

    def replace_in(expr: sp.Expr) -> sp.Expr:
        for integral in sorted(expr.atoms(sp.Integral), key=lambda e: -len(str(e))):
            if integral.function.has(sp.Integral) or len(integral.limits) > 1:      # SymPy merges nested integrals into one with several limits
                raise OdeSpecError("nested (multiple) integrals inside a differential equation are not supported")
            if len(integral.limits) != 1 or len(integral.limits[0]) != 3:
                raise OdeSpecError("an integral inside a differential equation must be definite: integrate(f, (s, lower, upper))")
            s, lo, hi = integral.limits[0]
            funcs_in = {f.func.__name__ for f in integral.function.atoms(AppliedUndef)}
            unknown = bool(funcs_in & set(deps_names))
            time_limits = lo.has(t) or hi.has(t)
            k = counter[0]
            counter[0] += 1
            if not unknown and not time_limits:
                try:
                    value, numeric = evaluate_calculus(integral, custom)
                except CalculusError as exc:
                    raise OdeSpecError(str(exc)) from None
                if numeric:
                    p = sp.Symbol(f"I__{k}", real=True)
                    try:
                        pre_dims[p] = analyze(integral, env)
                    except DimensionError as exc:
                        raise OdeSpecError(_friendly(str(exc))) from None
                    pre[p] = value
                    expr = expr.xreplace({integral: p})
                else:
                    expr = expr.xreplace({integral: value})
                continue
            if not (lo == start and hi == t):
                a, b = sp.simplify(t - lo), sp.simplify(t - hi)
                if lag_classes is None or a.has(t) or b.has(t) or a.atoms(AppliedUndef) or b.atoms(AppliedUndef):
                    raise OdeSpecError(f"an integral that involves the unknowns or the independent variable must run from the start to {t.name}, integrate(f, ({s}, {start}, {t.name})), "
                                       f"or be a sliding window integrate(f, ({s}, {t.name} - a, {t.name} - b)) with constants a and b; other variable limits are not supported")
                zf = sp.Function(f"int__{len(aug)}")(t)
                aug.append((zf, integral.function.subs(s, t)))
                nm = f"int__{len(aug) - 1}"
                if nm not in lag_classes:
                    lag_classes[nm] = type(f"{nm}__lag", (sp.Function,), {"nargs": 1, "_latex": lambda self, printer, *a_, _n=nm, **k: rf"z\left({t.name} - {printer._print(self.args[0])}\right)"})
                at = lambda off: zf if off == 0 else lag_classes[nm](off)          # noqa: E731
                expr = expr.xreplace({integral: at(b) - at(a)})
                continue
            if not unknown:
                try:
                    value, numeric = evaluate_calculus(integral, custom)
                except CalculusError:
                    value, numeric = None, True
                if not numeric:
                    expr = expr.xreplace({integral: value})
                    continue
            zf = sp.Function(f"int__{len(aug)}")(t)
            aug.append((zf, integral.function.subs(s, t)))
            expr = expr.xreplace({integral: zf})
        return expr

    out = [(replace_in(a), replace_in(b)) for a, b in sides]
    return out, aug, pre, pre_dims


def _try_closed_form(system: OdeSystem, sides, funcs, deps_names, calc, env, custom: bool, aug=()):
    t = system.t
    if system.pre:
        return None, "the equations contain an integral that has no closed form"
    eqs = [sp.Eq(a, b) for a, b in sides]
    ics = {}
    for zf, integrand in aug:                    # an integral of the unknowns is solved as one more equation: z' = integrand, z(start) = 0
        eqs.append(sp.Eq(sp.Derivative(zf, t), integrand))
        ics[zf.subs(t, system.start)] = 0
    for (dsym, j), idx in system.state_index.items():
        f = funcs[dsym.name]
        ics[f.subs(t, system.start) if j == 0 else sp.Derivative(f, (t, j)).subs(t, system.start)] = system.ics[idx]
    unknowns = [funcs[n] for n in deps_names] + [zf for zf, _ in aug]
    cap = DSOLVE_BUDGET if custom else None
    try:
        with time_limit(min(cap, settings.limit() or cap) if cap else None):
            res = sp.dsolve(eqs if len(eqs) > 1 else eqs[0], unknowns if len(unknowns) > 1 else unknowns[0], ics=ics)
    except TimeLimitExceeded:
        return None, f"SymPy's closed-form search stopped after {cap:g} s"
    except (NotImplementedError, ValueError, TypeError, AttributeError, KeyError, IndexError, RecursionError) as exc:
        return None, f"SymPy found no closed form: {str(exc)[:100]}"
    res = res if isinstance(res, list) else [res]
    closed: dict[sp.Symbol, sp.Expr] = {}
    for r in res:
        if not isinstance(r, sp.Equality) or not isinstance(r.lhs, AppliedUndef):
            return None, "SymPy's solution is implicit"
        name = r.lhs.func.__name__
        if name.startswith("int__"):             # the hidden integral state: not needed once the unknowns are solved
            continue
        if name not in deps_names:
            return None, "unexpected solution"
        expr = r.rhs
        if expr.has(sp.Piecewise, sp.Integral, sp.Derivative) or expr.atoms(AppliedUndef) or expr.atoms(sp.Dummy) or any(str(s).startswith("C") and s not in {v.symbol for v in calc.variables} for s in expr.free_symbols):
            return None, "SymPy's solution is not a plain closed form"
        closed[calc.by_key[name].symbol] = _realify_bessel(expr)
    if len(closed) != len(deps_names) or set(closed) != set(system.dependents):
        return None, "SymPy returned several solutions or too few"
    declared = {v.symbol for v in calc.variables}
    if any(s not in declared for e in closed.values() for s in e.free_symbols):
        return None, "SymPy's solution contains integration constants"
    return closed, ""


# ---------------------------------------------------------------- boundary-value problems

def _realify_bessel(expr: sp.Expr) -> sp.Expr:
    """dsolve writes the solutions of x² y'' + x y' − (m x)² y = 0 with Bessel J and Y of an imaginary argument; rewrite them with the modified functions I and K
    (J_n(iz) = iⁿ I_n(z), Y_n(iz) = i^(n+1) I_n(z) − (2/π) i^(−n) K_n(z)) and simplify, so the result is the real textbook form."""
    def imaginary(b) -> bool:
        return isinstance(b, (sp.besselj, sp.bessely)) and b.args[0].is_Integer and b.args[1].has(sp.I)

    def convert(b):
        n, z = b.args
        zz = sp.simplify(-sp.I * z)
        if isinstance(b, sp.besselj):
            return sp.I ** n * sp.besseli(n, zz)
        return sp.I ** (n + 1) * sp.besseli(n, zz) - 2 / sp.pi * sp.I ** (-n) * sp.besselk(n, zz)
    if not expr.has(sp.besselj, sp.bessely) or not expr.has(sp.I):
        return expr
    try:
        out = sp.simplify(expr.replace(imaginary, convert))
    except Exception:  # noqa: BLE001
        return expr
    return out if not out.has(sp.I) else expr


def _singular_at(fn, x: float, y: Sequence[float]) -> bool:
    """True when the right-hand side cannot be evaluated at ``x`` (division by zero, log of zero: an axis or centre)."""
    try:
        v = fn(x, list(y))
        return any(not math.isfinite(float(z)) for z in v)
    except (ZeroDivisionError, ValueError, OverflowError, TypeError):
        return True


def bvp_def_symbols(b: BvpDef) -> list:
    return [b.end, *[pos for pos, _r, _w in b.conditions], *[r for _p, r, _w in b.conditions], *b.guess.values(), *b.theta_guess.values()]


def _parse_bvp(spec, calc, ns, custom, funcs, deps_names, deps, local, t, start, state, state_index, top, sol, to_state, parse_ic_lhs, aug, ind, unknowns=None) -> BvpDef:
    import re

    from .safeparse import bound_names

    end = _parse(str(spec["end"]), ns, custom, ns)
    boundary = spec["boundary"]
    if isinstance(boundary, str):
        boundary = [x for x in (q.strip() for q in boundary.split("\n")) if x]
    if not isinstance(boundary, list) or not all(isinstance(x, str) and x.strip() for x in boundary):
        raise OdeSpecError("'boundary' must be a list of conditions such as 'start: y = 0'")
    if t in end.free_symbols or t in start.free_symbols:
        raise OdeSpecError(f"the ends of the interval cannot depend on {ind} itself")
    show = {funcs[n]: calc.by_key[n].symbol for n in deps_names}
    conditions: list = []
    wheres: list = []
    free_end = None
    if unknowns and isinstance(end, sp.Symbol) and end in unknowns.values():
        free_end = end                  # the end of the interval is itself unknown (a free boundary): the problem is solved on a scaled interval
        if aug or any(o != 1 and o != 2 and False for o in ()):
            raise OdeSpecError("a free end cannot be combined with integrals of the unknowns")
    for text in boundary:
        m = re.match(r"^\s*([^:=]+?)\s*:\s*(.+)$", text)
        if not m:
            raise OdeSpecError(f"a boundary condition is written 'where: condition', e.g. 'start: y = 0' or 'end: diff(y, {ind}) = 0'; got {text!r}")
        where, cond = m.group(1).strip(), m.group(2)
        pos = start if where == "start" else end if where == "end" else _parse(where, ns, custom, ns)
        wheres.append(where if where in ("start", "end") else "other")
        lt, rt = _split(cond)
        loc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(cond) if n not in local}}
        a, b = _parse(lt, loc, custom, ns), _parse(rt, loc, custom, ns)
        res = to_state(a - b).xreplace({top[d]: sol[top[d]] for d in deps})
        if res.atoms(AppliedUndef) or res.atoms(sp.Derivative) or res.has(sp.Integral):
            raise OdeSpecError(f"the boundary condition {cond!r} may use only the quantities and their derivatives diff(y, {ind}) and parameters")
        if t in res.free_symbols or t in pos.free_symbols:
            raise OdeSpecError(f"a boundary condition cannot involve {ind} itself; its position is given before the colon, e.g. 'end: ...'")
        conditions.append((pos, res, (a.xreplace(show), b.xreplace(show))))
    unknowns = unknowns or {}
    n_dep = len(state) - len(aug)
    want = n_dep + len(unknowns)
    if len(conditions) != want:
        why = f" (the total order of the equations{f', plus one for each of the {len(unknowns)} unknown parameter' + ('s' if len(unknowns) != 1 else '') if unknowns else ''})"
        raise OdeSpecError(f"{want} boundary condition{'s' if want != 1 else ''} needed{why}, but {len(conditions)} given"
                           + ("; an eigenvalue problem needs a normalisation such as 'L/2: y = a'" if unknowns else ""))
    for k in range(len(aug)):                      # a hidden integral state starts at zero
        conditions.append((start, state[n_dep + k], None))
    guess: dict = {}
    guess_texts = spec.get("guess") or []
    if isinstance(guess_texts, str):
        guess_texts = [x for x in (q.strip() for q in guess_texts.split("\n")) if x]
    if not isinstance(guess_texts, list) or not all(isinstance(x, str) for x in guess_texts):
        raise OdeSpecError("'guess' must be a list such as 'y = 300 K' (a starting value for the numerical solution)")
    theta_guess: dict = {}
    for text in guess_texts:
        lt, rt = _split(text)
        if lt.strip() in unknowns:
            theta_guess[unknowns[lt.strip()]] = _parse(rt, ns, custom, ns)
            continue
        key = parse_ic_lhs(lt.strip())
        if key not in state_index:
            raise OdeSpecError(f"{text!r}: no such state or unknown parameter to give a starting guess for")
        guess[state_index[key]] = _parse(rt, ns, custom, ns)
    for name, sym in unknowns.items():
        if sym not in theta_guess:
            raise OdeSpecError(f"give a starting guess for the unknown parameter {name}, e.g. '{name} = …' in 'guess' (Newton's method finds the value nearest to it; for an eigenvalue, that picks the mode)")
    if free_end is not None and any(w == "other" for w in wheres):
        raise OdeSpecError("with an unknown end (a free boundary) the conditions can be placed only at 'start' and 'end'")
    return BvpDef(end, conditions, [x.strip() for x in boundary], guess, [x.strip() for x in guess_texts], list(unknowns.values()), theta_guess, free_end, wheres + ["start"] * len(aug))


def _check_bvp_dims(b: BvpDef, genv: dict, env: dict, state, dim_t, state_index) -> None:
    de, _ = analyze(b.end, env)
    if b.end != 0 and de != dim_t:
        raise DimensionError(f"the end of the interval has dimension [{de}], expected [{dim_t}]")
    for pos, res, _w in b.conditions:
        if pos != 0:
            dp, _ = analyze(pos, env)
            if dp != dim_t:
                raise DimensionError(f"a boundary position has dimension [{dp}], expected [{dim_t}]")
        analyze(res, genv)                                   # both sides of a condition must agree
    for idx, expr in b.guess.items():
        if expr != 0:
            dg, _ = analyze(expr, genv)
            if dg != genv[state[idx]][0]:
                raise DimensionError(f"a starting guess has dimension [{dg}], expected [{genv[state[idx]][0]}]")
    for u, expr in b.theta_guess.items():
        if expr != 0:
            dg, _ = analyze(expr, genv)
            if dg != env[u][0]:
                raise DimensionError(f"the starting guess for {u.name} has dimension [{dg}], expected [{env[u][0]}]")


def _try_closed_form_bvp(system: OdeSystem, sides, funcs, deps_names, calc, custom: bool):
    """dsolve gives the general solution with integration constants; the boundary conditions then fix the constants (a linear solve)."""
    t = system.t
    if system.pre or system.aux_count:
        return None, "the equations contain an integral that has no closed form"
    eqs = [sp.Eq(a, b) for a, b in sides]
    unknowns = [funcs[n] for n in deps_names]
    cap = DSOLVE_BUDGET if custom else None
    try:
        with time_limit(min(cap, settings.limit() or cap) if cap else None):
            res = sp.dsolve(eqs if len(eqs) > 1 else eqs[0], unknowns if len(unknowns) > 1 else unknowns[0])
    except TimeLimitExceeded:
        return None, f"SymPy's closed-form search stopped after {cap:g} s"
    except (NotImplementedError, ValueError, TypeError, AttributeError, KeyError, IndexError, RecursionError) as exc:
        return None, f"SymPy found no closed form: {str(exc)[:100]}"
    res = res if isinstance(res, list) else [res]
    general: dict[sp.Symbol, sp.Expr] = {}
    for r in res:
        if not isinstance(r, sp.Equality) or not isinstance(r.lhs, AppliedUndef) or r.lhs.func.__name__ not in deps_names:
            return None, "SymPy's solution is implicit"
        if r.rhs.has(sp.Piecewise, sp.Integral, sp.Derivative) or r.rhs.atoms(AppliedUndef):
            return None, "SymPy's solution is not a plain closed form"
        general[calc.by_key[r.lhs.func.__name__].symbol] = r.rhs
    if set(general) != set(system.dependents):
        return None, "SymPy returned several solutions or too few"
    declared = {v.symbol for v in calc.variables}
    consts = sorted({s for e in general.values() for s in e.free_symbols if s not in declared and s != t}, key=lambda s: s.name)
    if not consts:
        return None, "the general solution has no integration constants to fit the boundary conditions to"
    sub: dict = {}
    for (dep, j), idx in system.state_index.items():
        sub[system.state[idx]] = general[dep] if j == 0 else sp.diff(general[dep], t, j)
    conds = []
    for pos, resid, _w in system.bvp.conditions:
        conds.append((pos, resid.xreplace(sub).subs(t, pos)))
    bad = {pos for pos, c in conds if c.has(sp.zoo, sp.nan, sp.oo, -sp.oo)}
    if bad:
        # an axis or centre (cylindrical, spherical): terms such as log(r) or 1/r are infinite there, so the symmetry condition is really a regularity
        # condition that removes them; the constants multiplying them are zero and the conditions at that position are then satisfied
        try:
            with time_limit(min(cap, settings.limit() or cap) if cap else None):
                singular = {c for c in consts for pos in bad for e in general.values()
                            if sp.limit(sp.diff(e, c), t, pos, "+").has(sp.zoo, sp.oo, -sp.oo, sp.nan)}
        except (TimeLimitExceeded, NotImplementedError, ValueError, TypeError, AttributeError, RecursionError):
            return None, "SymPy could not examine the solution at the axis"
        if not singular:
            return None, "the general solution is singular at a boundary position"
        zero = {c: 0 for c in singular}
        general = {d: e.xreplace(zero) for d, e in general.items()}
        consts = [c for c in consts if c not in singular]
        sub = {k: v.xreplace(zero) for k, v in sub.items()}
        kept = []
        for pos, resid, _w in system.bvp.conditions:
            c = resid.xreplace(sub).subs(t, pos)
            if pos in bad and sp.simplify(c) == 0:
                continue                       # the regularity condition: used up by removing the singular terms
            kept.append(c)
        conds = [(None, c) for c in kept]
        if not consts:
            return (general if all(not e.free_symbols - declared - {t} for e in general.values()) else None), "" if all(not e.free_symbols - declared - {t} for e in general.values()) else "no constants left to fit"
    conds = [c for _p, c in conds]
    try:
        with time_limit(min(cap, settings.limit() or cap) if cap else None):
            solved = sp.solve(conds, consts, dict=True)
    except TimeLimitExceeded:
        return None, f"SymPy's search for the constants stopped after {cap:g} s"
    except (NotImplementedError, ValueError, TypeError, AttributeError, RecursionError) as exc:
        return None, f"SymPy could not fit the constants: {str(exc)[:100]}"
    if len(solved) != 1 or set(solved[0]) != set(consts):
        return None, "SymPy found no unique set of constants for these boundary conditions"
    closed = {dep: _realify_bessel(expr.xreplace(solved[0])) for dep, expr in general.items()}
    for expr in closed.values():
        if expr.has(sp.Piecewise, sp.Integral, sp.Derivative, sp.zoo, sp.nan) or expr.atoms(sp.Dummy) or any(s not in declared and s != t for s in expr.free_symbols):
            return None, "the fitted solution is not a plain closed form"
    return closed, ""
