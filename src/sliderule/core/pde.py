"""Time-dependent partial differential equations in one space dimension, by the method of lines.

A PDE entry is an ``odes`` entry with a ``time`` variable besides the ``independent`` (space) variable::

    {"title": "Heating of a slab", "independent": "x", "start": "0", "end": "L", "time": "t",
     "equations": ["diff(T, t) = a*diff(T, x, 2)"],
     "boundary": ["start: T = Ts", "end: -k*diff(T, x) = h*(T - Ti)"],
     "initial": ["T = Ti"]}

The unknown ``T`` then means *its value at the position* ``x`` *and time* ``t`` that the user supplies. The equation must be solvable for the highest
time derivative (first order: parabolic, e.g. diffusion; second order: hyperbolic, e.g. waves), may contain ``diff(T, x)`` and ``diff(T, x, 2)``
(including conservative forms such as ``diff(k*diff(T, x), x)``), the quantity itself, ``x``, ``t`` and parameters, and, for a second-order equation, the
first time derivative (damping). Exactly one condition is given at each end: a value (Dirichlet), or any relation involving the slope (Neumann, Robin).

Numerics: uniform grid, second-order central differences, a ghost node at a slope condition, then the resulting ordinary differential equations are
integrated in time: a banded implicit solver for first-order (stiff, diffusion-like) equations, explicit RK45 for second-order ones. The grid is
solved twice (N and N/2 intervals) and the difference is reported as an error estimate; evaluation between nodes is by cubic interpolation.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

import sympy as sp
from sympy.core.function import AppliedUndef

from .special import fast_lambdify
from .banded import BandedLU, SingularMatrix
from .dimcheck import DimensionError, analyze
from .numeric_ode import OdeError, _TooManySteps, rk45, stiff

DEFAULT_NODES = 100
MIN_NODES, MAX_NODES = 10, 400
RTOL = 1e-4                # explicit (second-order in time) integration
IMPLICIT_RTOL = 1e-5       # implicit (diffusion-type) integration: low order, and the grid error is of this size anyway


@dataclass
class PdeResult:
    method: str
    steps: int
    nfev: int
    rtol: float
    atol: float
    notes: list[str] = field(default_factory=list)


@dataclass
class Fields:
    xs: list[float]
    times: list[float]
    u: list[list[float]]                 # u[k][i]: value at time k, node i
    result: PdeResult
    error: float                          # estimated discretisation error (absolute), from the half-resolution run


def interpolate(xs: list[float], vals: list[float], x: float) -> float:
    """Cubic Lagrange interpolation on a uniform grid (4 nearest nodes)."""
    n = len(xs) - 1
    h = (xs[-1] - xs[0]) / n
    pos = (x - xs[0]) / h
    i = int(math.floor(pos))
    i = min(max(i, 0), n - 1)
    k0 = min(max(i - 1, 0), n - 3)
    pts = range(k0, k0 + 4)
    out = 0.0
    for a in pts:
        w = 1.0
        for b in pts:
            if a != b:
                w *= (pos - b) / (a - b)
        out += w * vals[a]
    return out


@dataclass
class PdeSystem:
    title: str
    texts: list[str]
    x: sp.Symbol
    t: sp.Symbol
    start: sp.Expr
    end: sp.Expr
    dependent: sp.Symbol
    order: int                                    # order in time: 1 or 2
    nodes: int
    symbols: tuple                                # internal symbols (U, UT, UX, UXX)
    rhs: sp.Expr                                  # d^order u / dt^order = rhs(x, t, U, UT, UX, UXX, params)
    bcs: list                                     # two (kind, expr, written) ; kind "value": u = expr ; "slope": u_x = expr (in U, UT, t, params)
    u0: sp.Expr                                   # initial value (in x and parameters)
    v0: sp.Expr | None                            # initial rate of change (second order)
    written: list                                 # [(lhs, rhs)] with u as a function u(x, t), for display
    condition_texts: list[tuple[Any, Any, str]]   # (lhs, rhs, note) for display and export
    params: list[sp.Symbol]
    inputs: list[sp.Symbol]
    why_numeric: str = "partial differential equations are solved numerically by the method of lines"
    method: str = "numeric"
    closed: None = None
    events: list = field(default_factory=list)
    bvp: None = None
    pre: dict = field(default_factory=dict)
    aux_count: int = 0
    fns: dict = field(default_factory=dict)
    fallback: dict = field(default_factory=dict)
    _cache: dict = field(default_factory=dict, repr=False)

    # ---- interface shared with OdeSystem (the engine treats both alike)
    numeric = True
    pde = True

    @property
    def dependents(self) -> list[sp.Symbol]:
        return [self.dependent]

    @property
    def initial_texts(self) -> list[str]:
        return []

    @property
    def condition_note(self) -> str:
        return "boundary and initial condition"

    def last_result(self) -> PdeResult | None:
        return self._cache.get("last")

    def event_latex(self, names: dict) -> list:
        return []

    def written_latex(self, names: dict) -> list[str]:
        return [f"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)}" for a, b in self.written]

    def condition_latex(self, names: dict) -> list[str]:
        out = []
        x = names.get(self.x, str(self.x))
        out.append(rf"{x} \in \left[{sp.latex(self.start, symbol_names=names)},\; {sp.latex(self.end, symbol_names=names)}\right]")
        for a, b, note in self.condition_texts:
            out.append(rf"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)} \quad \text{{({note})}}")
        return out

    # ---- numbers

    def _values(self, values: Mapping[sp.Symbol, float]) -> dict:
        return {s: float(values[s]) for s in self.inputs}

    def _compiled(self):
        if "lim" not in self._cache:
            self._cache["lim"] = fast_lambdify(self.inputs, [self.start, self.end])
        return self._cache

    def _bound(self, vals: dict):
        """The right-hand side, boundary and initial functions with the parameter values built in (constants fold, calls are cheaper)."""
        key = ("bound", tuple(vals[s] for s in self.params))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        U, UT, UX, UXX = self.symbols
        sub = {s: sp.Float(vals[s], 17) for s in self.params}
        F = fast_lambdify([self.x, self.t, U, UT, UX, UXX], self.rhs.xreplace(sub))
        bc = [(kind, fast_lambdify([self.t, U, UT], expr.xreplace(sub))) for kind, expr, _w in self.bcs]
        u0 = fast_lambdify([self.x], self.u0.xreplace(sub))
        v0 = fast_lambdify([self.x], self.v0.xreplace(sub)) if self.v0 is not None else None
        if len([k for k in self._cache if isinstance(k, tuple) and k and k[0] == "bound"]) > 6:
            for k in [k for k in self._cache if isinstance(k, tuple) and k and k[0] == "bound"]:
                del self._cache[k]
        self._cache[key] = (F, bc, u0, v0)
        return self._cache[key]

    def _params(self, vals: dict) -> list[float]:
        return [vals[s] for s in self.params]

    def span(self, values: Mapping[sp.Symbol, float]) -> tuple[float, float]:
        c = self._compiled()
        vals = self._values(values)
        lo, hi = c["lim"](*[vals[s] for s in self.inputs])
        if not hi > lo:
            raise OdeError(f"the end of the interval ({hi:g}) must be greater than its start ({lo:g}) (SI)")
        return float(lo), float(hi)

    def _integrate(self, vals: dict, times: list[float], N: int, t_end: float):
        """Integrate on N intervals; returns (ts, list of full node vectors, steps, nfev, method, notes)."""
        c = self._compiled()
        lo, hi = c["lim"](*[vals[s] for s in self.inputs])
        h = (hi - lo) / N
        xs = [lo + i * h for i in range(N + 1)]
        F, bc, u0f, v0f = self._bound(vals)
        p = self.order
        kind0, kind1 = bc[0][0], bc[1][0]
        g0 = bc[0][1]
        gN = bc[1][1]
        first = 1 if kind0 == "value" else 0
        last = N - 1 if kind1 == "value" else N
        unknown = list(range(first, last + 1))
        m = len(unknown)
        if m < 1:
            raise OdeError("the boundary conditions leave no unknown nodes; increase the number of nodes")
        ih2, i2h = 1.0 / (h * h), 1.0 / (2 * h)
        xr = list(xs[first:last + 1])
        # a centre (axis or point) at x = 0 with a symmetry condition: a term such as u_x/x is 0/0 there. Its limit is u_xx, so the centre node is evaluated at a tiny
        # x with u_x = u_xx x (the Taylor expansion of a function with zero slope at the centre)
        center = False
        if lo == 0.0 and kind0 == "slope" and first == 0:
            try:
                probe = F(0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
                center = not math.isfinite(probe)
            except (ZeroDivisionError, ValueError, OverflowError):
                center = True
        eps_x = 1e-9 * (hi - lo)
        if center:
            xr[0] = eps_x

        def expand(y, t):
            U = [0.0] * (N + 1)
            U[first:last + 1] = y if p == 1 else y[0::2]
            if kind0 == "value":
                U[0] = g0(t, 0.0, 0.0)
            if kind1 == "value":
                U[N] = gN(t, 0.0, 0.0)
            return U

        def rhs(t, y):
            U = expand(y, t)
            V = None if p == 1 else [0.0] * (N + 1)
            if p == 2:
                V[first:last + 1] = y[1::2]
            E = [0.0] + U + [0.0]                       # E[i + 1] is node i; the ends are ghost nodes
            if kind0 == "slope":
                E[0] = U[1] - 2 * h * g0(t, U[0], V[0] if V else 0.0)
            if kind1 == "slope":
                E[N + 2] = U[N - 1] + 2 * h * gN(t, U[N], V[N] if V else 0.0)
            left, mid, right = E[first:last + 1], E[first + 1:last + 2], E[first + 2:last + 3]
            if p == 1:
                res = [F(x, t, u, 0.0, (ur - ul) * i2h, (ur - 2 * u + ul) * ih2) for x, ul, u, ur in zip(xr, left, mid, right)] if not center else \
                    [F(xr[0], t, mid[0], 0.0, (right[0] - 2 * mid[0] + left[0]) * ih2 * eps_x, (right[0] - 2 * mid[0] + left[0]) * ih2)] + \
                    [F(x, t, u, 0.0, (ur - ul) * i2h, (ur - 2 * u + ul) * ih2) for x, ul, u, ur in zip(xr[1:], left[1:], mid[1:], right[1:])]
                return res
            vs = V[first:last + 1]
            fs = [F(x, t, u, v, (ur - ul) * i2h, (ur - 2 * u + ul) * ih2) for x, ul, u, ur, v in zip(xr, left, mid, right, vs)] if not center else \
                [F(xr[0], t, mid[0], vs[0], (right[0] - 2 * mid[0] + left[0]) * ih2 * eps_x, (right[0] - 2 * mid[0] + left[0]) * ih2)] + \
                [F(x, t, u, v, (ur - ul) * i2h, (ur - 2 * u + ul) * ih2) for x, ul, u, ur, v in zip(xr[1:], left[1:], mid[1:], right[1:], vs[1:])]
            out = [0.0] * (2 * m)
            out[0::2] = vs
            out[1::2] = fs
            return out

        y0 = []
        for i in unknown:
            y0.append(u0f(xs[i]))
            if p == 2:
                y0.append(v0f(xs[i]) if v0f is not None else 0.0)
        if any(not math.isfinite(v) for v in y0):
            raise OdeError("the initial condition is not finite at every node")
        scale = max([abs(v) for v in y0[::p]] + [abs(g0(0.0, 0.0, 0.0)) if kind0 == "value" else 0.0, abs(gN(0.0, 0.0, 0.0)) if kind1 == "value" else 0.0,
                      abs(g0(t_end, 0.0, 0.0)) if kind0 == "value" else 0.0, abs(gN(t_end, 0.0, 0.0)) if kind1 == "value" else 0.0, 1e-30])
        atol = 1e-6 * scale if p == 1 else 1e-7 * scale          # relative to the largest value of the field: tiny tails must not dictate the step
        b = p
        kb = 2 * b - 1

        if p == 1:
            def jacobian(f, t, y, fy):
                n = len(y)
                rows = [[0.0] * (2 * kb + 1) for _ in range(n)]
                for col in range(3):
                    yp = list(y)
                    eps = {}
                    for j in range(col, n, 3):
                        e = 1.5e-8 * max(1.0, abs(y[j]))
                        yp[j] += e
                        eps[j] = e
                    if not eps:
                        continue
                    fp = f(t, yp)
                    for j, e in eps.items():
                        for i in range(max(0, j - 1), min(n - 1, j + 1) + 1):
                            rows[i][j - (i - kb)] = (fp[i] - fy[i]) / e
                return rows

            def factor(hh, jac):
                n = len(jac)
                rows = [[-hh * v for v in r] for r in jac]
                for i in range(n):
                    rows[i][kb] += 1.0
                try:
                    lu = BandedLU(n, kb, kb, rows)
                except SingularMatrix:
                    raise OdeError("singular matrix in the implicit solver") from None
                return lu.solve

            res = stiff(rhs, 0.0, y0, t_end, rtol=IMPLICIT_RTOL, atol=atol, outputs=times, jacobian=jacobian, factor=factor)
            method = "implicit Euler with extrapolation, banded Newton (method of lines)"
        else:
            try:
                res = rk45(rhs, 0.0, y0, t_end, RTOL, atol, times)
            except _TooManySteps as exc:
                raise OdeError(f"the explicit time integration needs too many steps ({exc}); use fewer nodes or a shorter time") from None
            method = "Dormand–Prince RK45 (method of lines)"
        fields = [expand(y, t) for t, y in zip(res.ts, res.ys)]
        return res.ts, fields, res.steps, res.nfev, method, xs

    def run(self, values: Mapping[sp.Symbol, float], outputs=()) -> Fields:
        """Fields at the requested times and at the evaluation time ``t`` (memoised)."""
        vals = self._values(values)
        t_end = vals[self.t]
        if t_end < 0:
            raise OdeError(f"the time must not be negative (got {t_end:g} s)")
        # always land on 60 evenly spaced times (the plots and snapshots use them) plus any requested ones, so one run serves every purpose
        times = sorted({t_end * i / 60 for i in range(1, 60)} | {o for o in outputs if 0 < o < t_end}) if t_end > 0 else []
        key = (tuple(vals[s] for s in self.inputs if s != self.x), tuple(times))
        hit = self._cache.get(("run", key))
        if hit is not None:
            self._cache["last"] = hit.result
            return hit
        N = self.nodes + (self.nodes % 2)
        ts, fields, steps, nfev, method, xs = self._integrate(vals, times, N, t_end)
        notes = []
        err = 0.0
        if N >= 2 * MIN_NODES:
            ts_c, fields_c, steps_c, nfev_c, _m, _x = self._integrate(vals, [], N // 2, t_end)
            fine, coarse = fields[-1][::2], fields_c[-1]
            scale = max(max(abs(v) for v in fine), 1e-300)
            err = max(abs(a - b) for a, b in zip(fine, coarse)) / 3
            steps, nfev = steps + steps_c, nfev + nfev_c
            rel = err / scale
            notes.append(f"{N} intervals; estimated discretisation error {err:.2g} ({rel:.1e} relative), from comparison with {N // 2} intervals")
            if rel > 1e-2:
                notes.append("the estimated error is above 1 %: increase the number of nodes")
        res = PdeResult(method, steps, nfev, IMPLICIT_RTOL if self.order == 1 else RTOL, 0.0, notes)
        out = Fields(xs, ts, fields, res, err)
        if len(self._cache) > 30:
            self._cache.clear()
        self._cache[("run", key)] = out
        self._cache["last"] = res
        return out

    def value(self, dependent: sp.Symbol, values: Mapping[sp.Symbol, float]) -> float:
        vals = self._values(values)
        lo, hi = self.span(values)
        x = vals[self.x]
        if not lo - 1e-9 * (hi - lo) <= x <= hi + 1e-9 * (hi - lo):
            raise OdeError(f"{self.x.name} = {x:g} (SI) lies outside the interval {lo:g} to {hi:g}")
        f = self.run(values)
        return interpolate(f.xs, f.u[-1], min(max(x, lo), hi))

    def export_conditions(self) -> list[tuple[Any, Any, str]]:
        return list(self.condition_texts)


# ---------------------------------------------------------------- building

def build(spec: Mapping[str, Any], calc, ns: dict, env: dict, custom: bool, index: int):
    from .model import Equation
    from .ode import OdeSpecError, _friendly, _make_fn, _parse, _split
    from .safeparse import bound_names

    title = str(spec.get("title") or "Partial differential equation").strip()[:100]
    xn, tn = spec.get("independent"), spec.get("time")
    for what, n in (("independent (space)", xn), ("time", tn)):
        if not isinstance(n, str) or n not in calc.by_key or calc.by_key[n].is_constant:
            raise OdeSpecError(f"'{what}' must name one of the variables, got {n!r}")
    if xn == tn:
        raise OdeSpecError("the space and time variables must differ")
    x, t = calc.by_key[xn].symbol, calc.by_key[tn].symbol
    if spec.get("events"):
        raise OdeSpecError("events are not supported for partial differential equations")
    texts = spec.get("equations")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or len(texts) != 1 or not isinstance(texts[0], str) or not texts[0].strip():
        raise OdeSpecError("a partial differential equation entry takes exactly one equation, e.g. 'diff(T, t) = a*diff(T, x, 2)'")
    text = texts[0].strip()
    nodes = spec.get("nodes", DEFAULT_NODES)
    if not isinstance(nodes, int) or isinstance(nodes, bool) or not MIN_NODES <= nodes <= MAX_NODES:
        raise OdeSpecError(f"'nodes' must be a whole number from {MIN_NODES} to {MAX_NODES}")

    # the unknown: the quantity differentiated with respect to t
    found = []
    for side in _split(text):
        try:
            tree = ast.parse(side.strip().replace("^", "**"), mode="eval")
        except SyntaxError:
            raise OdeSpecError(f"cannot read the equation {text!r}") from None
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "diff" and len(n.args) >= 2 and isinstance(n.args[0], ast.Name):
                if n.args[0].id in calc.by_key and n.args[0].id not in found and n.args[0].id not in (xn, tn):
                    found.append(n.args[0].id)
    if len(found) != 1:
        raise OdeSpecError(f"exactly one quantity must be differentiated in a partial differential equation (found {', '.join(found) or 'none'}); "
                           f"coupled systems of PDEs are not supported")
    un = found[0]
    uv = calc.by_key[un]
    if uv.is_constant:
        raise OdeSpecError(f"{un!r} is differentiated but is a constant")
    u_sym = uv.symbol
    fn = sp.Function(un)(x, t)
    local = {**ns, un: fn}
    lt, rt = _split(text)
    loc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(text) if n not in local}}
    lhs, rhs_ = _parse(lt, loc, custom, ns), _parse(rt, loc, custom, ns)
    expanded = (lhs - rhs_).doit()

    U, UT, UTT, UX, UXX = (sp.Symbol(f"{un}__{s}", real=True) for s in ("0", "t", "tt", "x", "xx"))
    rep = {}
    for d in expanded.atoms(sp.Derivative):
        if not isinstance(d.expr, AppliedUndef) or d.expr.func.__name__ != un:
            raise OdeSpecError(f"{d}: differentiate {un} directly (e.g. diff({un}, {xn}, 2)); other derivatives are not supported")
        counts = dict((v, c) for v, c in d.variable_count)
        if set(counts) - {x, t}:
            raise OdeSpecError(f"{d}: the derivative must be with respect to {xn} or {tn}")
        a, b = counts.get(x, 0), counts.get(t, 0)
        sym = {(1, 0): UX, (2, 0): UXX, (0, 1): UT, (0, 2): UTT}.get((a, b))
        if sym is None:
            raise OdeSpecError(f"{d}: only first and second derivatives in space, and first (or second) in time, are supported — no mixed derivatives")
        rep[d] = sym
    resid = expanded.xreplace(rep).xreplace({fn: U})
    if resid.atoms(AppliedUndef) or resid.atoms(sp.Derivative) or resid.has(sp.Integral):
        raise OdeSpecError("the equation uses the unknown in a way that cannot be handled (only the quantity and its derivatives, not inside integrals)")
    order = 2 if resid.has(UTT) else 1 if resid.has(UT) else 0
    if order == 0:
        raise OdeSpecError(f"the equation has no time derivative of {un}: for a steady problem use boundary-value or 2-D steady PDE support")
    if not resid.has(UXX) and not resid.has(UX):
        raise OdeSpecError(f"the equation has no space derivative of {un}")
    top = UTT if order == 2 else UT
    try:
        sols = sp.solve(resid, top, dict=True)
    except Exception as exc:  # noqa: BLE001
        raise OdeSpecError(f"cannot solve the equation for the highest time derivative: {exc}") from None
    if len(sols) != 1 or top not in sols[0] or sols[0][top].has(top) or (order == 2 and sols[0][top].has(UTT)):
        raise OdeSpecError("the equation must be solvable for the highest time derivative, with the other terms not containing it")
    F = sols[0][top]
    declared = {v.symbol for v in calc.variables}
    internal = {U, UT, UX, UXX}

    # boundary conditions
    boundary = spec.get("boundary")
    if isinstance(boundary, str):
        boundary = [q.strip() for q in boundary.split("\n") if q.strip()]
    if not isinstance(boundary, list) or len(boundary) != 2 or not all(isinstance(b, str) for b in boundary):
        raise OdeSpecError("give exactly two boundary conditions, one 'start: …' and one 'end: …', e.g. 'start: T = Ts'")
    bcs: dict[str, tuple] = {}
    condition_texts = []
    for btxt in boundary:
        m = re.match(r"^\s*(start|end)\s*:\s*(.+)$", btxt)
        if not m or m.group(1) in bcs:
            raise OdeSpecError(f"boundary conditions are written 'start: …' and 'end: …' (one of each); got {btxt!r}")
        where, cond = m.groups()
        cl, cr = _split(cond)
        loc2 = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(cond) if n not in local}}
        a, b = _parse(cl, loc2, custom, ns), _parse(cr, loc2, custom, ns)
        res = (a - b).doit()
        rep2 = {}
        for d in res.atoms(sp.Derivative):
            counts = dict((v, c) for v, c in d.variable_count)
            sym = {(1, 0): UX, (0, 1): UT}.get((counts.get(x, 0), counts.get(t, 0)))
            if not isinstance(d.expr, AppliedUndef) or d.expr.func.__name__ != un or sym is None or set(counts) - {x, t}:
                raise OdeSpecError(f"the boundary condition {cond!r} may contain {un} and its first derivative in space{' and time' if order == 2 else ''}")
            if sym is UT and order != 2:
                raise OdeSpecError(f"the boundary condition {cond!r}: a time derivative is only allowed for second-order (wave-type) equations")
            rep2[d] = sym
        res = res.xreplace(rep2).xreplace({fn: U})
        if res.atoms(AppliedUndef) or res.atoms(sp.Derivative) or x in res.free_symbols:
            raise OdeSpecError(f"the boundary condition {cond!r} may involve {un}, its slope and parameters (and {tn}), but not {xn} itself")
        try:
            if res.has(UX):
                kind, sol = "slope", sp.solve(res, UX)
            else:
                kind, sol = "value", sp.solve(res, U)
        except Exception as exc:  # noqa: BLE001
            raise OdeSpecError(f"cannot use the boundary condition {cond!r}: {exc}") from None
        if len(sol) != 1 or sol[0].has(UX) or (kind == "value" and sol[0].has(U)):
            raise OdeSpecError(f"the boundary condition {cond!r} must determine the {'slope' if kind == 'slope' else 'value'} uniquely "
                               f"({'linear in the slope' if kind == 'slope' else 'a plain value such as T = Ts'})")
        bcs[where] = (kind, sol[0], (a, b))
        condition_texts.append((a, b, f"at {where}"))
    # the initial state
    initial = spec.get("initial") or []
    if isinstance(initial, str):
        initial = [q.strip() for q in initial.split("\n") if q.strip()]
    if not isinstance(initial, list) or not all(isinstance(q, str) for q in initial):
        raise OdeSpecError("'initial' must be a list such as 'T = Ti' (and 'diff(u, t) = 0' for a second-order equation)")
    u0 = v0 = None
    for itxt in initial:
        il, ir = _split(itxt)
        il = il.strip()
        value = _parse(ir, {**ns}, custom, ns)
        if il == un:
            if u0 is not None:
                raise OdeSpecError(f"initial value of {un} given twice")
            u0 = value
        elif re.fullmatch(rf"diff\(\s*{re.escape(un)}\s*,\s*{re.escape(tn)}\s*\)", il):
            if order != 2:
                raise OdeSpecError("an initial rate of change is only needed for a second-order (wave-type) equation")
            if v0 is not None:
                raise OdeSpecError("initial rate of change given twice")
            v0 = value
        else:
            raise OdeSpecError(f"an initial condition's left side must be {un}{f' or diff({un}, {tn})' if order == 2 else ''}, got {il!r}")
    if u0 is None:
        raise OdeSpecError(f"missing initial value: add '{un} = …' (it may depend on {xn})")
    if order == 2 and v0 is None:
        v0 = sp.Integer(0)
    start = _parse(str(spec.get("start", "0")), ns, custom, ns) if str(spec.get("start", "0")).strip() else sp.Integer(0)
    end = _parse(str(spec.get("end") or ""), ns, custom, ns) if str(spec.get("end") or "").strip() else None
    if end is None:
        raise OdeSpecError("a partial differential equation needs an 'end' (where the interval ends), e.g. 'L'")
    if x in start.free_symbols or x in end.free_symbols or t in start.free_symbols or t in end.free_symbols:
        raise OdeSpecError("the ends of the interval cannot depend on the space or time variable")

    exprs = [F, u0, start, end, *( [v0] if v0 is not None else []), *[b[1] for b in bcs.values()]]
    params = sorted({s for e in exprs for s in e.free_symbols if s not in internal and s not in (x, t)}, key=lambda s: s.name)
    for s in params:
        if s not in declared:
            raise OdeSpecError(f"{s} is not a variable of this calculation")
    if t in u0.free_symbols or t in (v0.free_symbols if v0 is not None else set()):
        raise OdeSpecError("the initial state cannot depend on time")

    # dimensions
    dim_t, unit_t = env[t]
    dim_x, unit_x = env[x]
    dim_u, unit_u = env[u_sym]
    genv = dict(env)
    genv[U] = (dim_u, unit_u)
    genv[UT] = (dim_u / dim_t, unit_u / unit_t)
    genv[UX] = (dim_u / dim_x, unit_u / unit_x)
    genv[UXX] = (dim_u / dim_x ** 2, unit_u / unit_x ** 2)
    try:
        dr, _ = analyze(F, genv)
        want = dim_u / dim_t ** order
        if dr != want:
            raise DimensionError(f"the equation gives {un}'s {'second ' if order == 2 else ''}time derivative the dimension [{dr}], expected [{want}]")
        for expr, what in ((u0, "initial value"), (v0, "initial rate of change")):
            if expr is None or expr == 0:
                continue
            di, _ = analyze(expr, genv)
            wanted = dim_u if what == "initial value" else dim_u / dim_t
            if di != wanted:
                raise DimensionError(f"the {what} has dimension [{di}], expected [{wanted}]")
        for e, what in ((start, "start"), (end, "end")):
            if e != 0:
                de, _ = analyze(e, genv)
                if de != dim_x:
                    raise DimensionError(f"the {what} of the interval has dimension [{de}], expected [{dim_x}]")
        for where, (kind, expr, _w) in bcs.items():
            if expr == 0:
                continue
            db, _ = analyze(expr, genv)
            wanted = dim_u if kind == "value" else dim_u / dim_x
            if db != wanted:
                raise DimensionError(f"the {where} condition gives the {'value' if kind == 'value' else 'slope'} the dimension [{db}], expected [{wanted}]")
    except DimensionError as exc:
        raise OdeSpecError(f"{title}: {_friendly(str(exc))}") from None

    inputs = sorted({x, t, *params, *[s for e in (start, end) for s in e.free_symbols]}, key=lambda s: s.name)
    ufun = sp.Function(un)
    initial_shown = [(ufun(x, 0), u0, "initial")] + ([(sp.Function(f"{un}_t")(x, 0), v0, "initial")] if v0 is not None else [])
    system = PdeSystem(title, [text], x, t, start, end, u_sym, order, nodes, (U, UT, UX, UXX), F,
                       [(bcs["start"][0], bcs["start"][1], bcs["start"][2]), (bcs["end"][0], bcs["end"][1], bcs["end"][2])], u0, v0,
                       [(lhs, rhs_)], condition_texts + initial_shown, params, inputs)
    dim, unit = env[u_sym]
    node = _make_fn(system, u_sym, (dim, unit), calc.by_key[un].latex or un, index * 10)
    system.fns[u_sym] = node
    eq = Equation(title, f"{un} = numerical solution of {text}", u_sym, node(*system.inputs), frozenset({u_sym, *system.inputs}), None)
    eq.ode = system
    return system, [eq]
