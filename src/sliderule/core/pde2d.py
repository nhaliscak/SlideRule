"""Steady partial differential equations on a rectangle (Laplace, Poisson, Helmholtz, steady conduction with sources, nonlinear variants).

An ``odes`` entry with a ``second`` space variable and no ``time``::

    {"title": "Plate", "independent": "x", "start": "0", "end": "a", "second": "y", "second_start": "0", "second_end": "b",
     "equations": ["k*(diff(T, x, 2) + diff(T, y, 2)) + q = 0"],
     "boundary": ["left: T = T0", "right: diff(T, x) = 0", "bottom: T = T0", "top: -k*diff(T, y) = h*(T - Tinf)"]}

The unknown means its value at the point (x, y) you supply. The equation may be nonlinear and may contain the quantity, ``diff(T, x)``, ``diff(T, y)``,
``diff(T, x, 2)``, ``diff(T, y, 2)``, x, y and parameters (no mixed derivatives). Each of the four sides takes one condition: a value (which may depend on
the coordinate along the side) or a relation involving the slope normal to the side.

Numerics: uniform grid, five-point second-order differences, ghost nodes at slope conditions, Newton's method with a banded Jacobian (five colour
groups) and a banded LU factorisation. A second solve on half the intervals gives an error estimate; evaluation between nodes is bicubic.
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
from .numeric_ode import OdeError
from .pde import PdeResult, interpolate

DEFAULT_NODES = 40
MIN_NODES, MAX_NODES = 8, 100
SIDES = ("left", "right", "bottom", "top")


@dataclass
class Fields2D:
    xs: list[float]
    ys: list[float]
    u: list[list[float]]                  # u[j][i]
    result: PdeResult
    error: float
    hole: list | None = None              # cutouts: True at the nodes inside one (those values are only a fill)


def interpolate2d(f: Fields2D, x: float, y: float) -> float:
    rows = [interpolate(f.xs, row, x) for row in f.u]
    return interpolate(f.ys, rows, y)


@dataclass
class Pde2dSystem:
    title: str
    texts: list[str]
    x: sp.Symbol
    y: sp.Symbol
    x0: sp.Expr
    x1: sp.Expr
    y0: sp.Expr
    y1: sp.Expr
    dependent: sp.Symbol
    nodes: int
    symbols: tuple                         # (U, UX, UY, UXX, UYY)
    resid: sp.Expr                         # = 0
    bcs: dict                              # side -> (kind, expr, written); kind "value": u = expr ; "slope": normal slope = expr
    guess: sp.Expr | None
    written: list
    condition_texts: list
    params: list[sp.Symbol]
    inputs: list[sp.Symbol]
    guess_texts: list[str] = field(default_factory=list)
    why_numeric: str = "the steady partial differential equation is solved numerically on a grid (finite differences and Newton's method)"
    method: str = "numeric"
    closed: None = None
    events: list = field(default_factory=list)
    bvp: None = None
    pre: dict = field(default_factory=dict)
    aux_count: int = 0
    fns: dict = field(default_factory=dict)
    fallback: dict = field(default_factory=dict)
    _cache: dict = field(default_factory=dict, repr=False)

    numeric = True
    pde = True
    dim = 2

    @property
    def dependents(self) -> list[sp.Symbol]:
        return [self.dependent]

    @property
    def initial_texts(self) -> list[str]:
        return []

    @property
    def condition_note(self) -> str:
        return "boundary condition"

    def last_result(self) -> PdeResult | None:
        return self._cache.get("last")

    def event_latex(self, names: dict) -> list:
        return []

    def written_latex(self, names: dict) -> list[str]:
        return [f"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)}" for a, b in self.written]

    def condition_latex(self, names: dict) -> list[str]:
        x, y = names.get(self.x, str(self.x)), names.get(self.y, str(self.y))
        out = [rf"{x} \in \left[{sp.latex(self.x0, symbol_names=names)},\; {sp.latex(self.x1, symbol_names=names)}\right],\quad "
               rf"{y} \in \left[{sp.latex(self.y0, symbol_names=names)},\; {sp.latex(self.y1, symbol_names=names)}\right]"]
        for a, b, note in self.condition_texts:
            out.append(rf"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)} \quad \text{{({note})}}")
        return out

    def export_conditions(self) -> list:
        return list(self.condition_texts)

    # ---- numbers

    def _values(self, values: Mapping[sp.Symbol, float]) -> dict:
        return {s: float(values[s]) for s in self.inputs}

    def span(self, values: Mapping[sp.Symbol, float]):
        if "lim" not in self._cache:
            self._cache["lim"] = fast_lambdify(self.inputs, [self.x0, self.x1, self.y0, self.y1])
        vals = self._values(values)
        a, b, c, d = self._cache["lim"](*[vals[s] for s in self.inputs])
        if not (b > a and d > c):
            raise OdeError("the ends of each interval must be increasing (end greater than start)")
        return (float(a), float(b)), (float(c), float(d))

    def _bound(self, vals: dict):
        key = ("bound", tuple(vals[s] for s in self.params))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        U, UX, UY, UXX, UYY = self.symbols
        sub = {s: sp.Float(vals[s], 17) for s in self.params}
        R = fast_lambdify([self.x, self.y, U, UX, UY, UXX, UYY], self.resid.xreplace(sub))
        bc = {}
        for side, (kind, expr, _w) in self.bcs.items():
            coord = self.y if side in ("left", "right") else self.x
            bc[side] = (kind, fast_lambdify([coord, U], expr.xreplace(sub)))
        guess = fast_lambdify([self.x, self.y], self.guess.xreplace(sub)) if self.guess is not None else None
        for k in [k for k in self._cache if isinstance(k, tuple) and k and k[0] == "bound"][5:]:
            del self._cache[k]
        self._cache[key] = (R, bc, guess)
        return self._cache[key]

    def _solve(self, vals: dict, N: int) -> tuple[list[float], list[float], list[list[float]], int, int]:
        (xa, xb), (ya, yb) = self.span({s: vals[s] for s in self.inputs})
        hx, hy = (xb - xa) / N, (yb - ya) / N
        xs = [xa + i * hx for i in range(N + 1)]
        ys = [ya + j * hy for j in range(N + 1)]
        R, bc, guessf = self._bound(vals)
        kinds = {s: bc[s][0] for s in SIDES}
        g = {s: bc[s][1] for s in SIDES}
        i0 = 1 if kinds["left"] == "value" else 0
        i1 = N - 1 if kinds["right"] == "value" else N
        j0 = 1 if kinds["bottom"] == "value" else 0
        j1 = N - 1 if kinds["top"] == "value" else N
        Wd, Ht = i1 - i0 + 1, j1 - j0 + 1
        if Wd < 1 or Ht < 1:
            raise OdeError("the boundary conditions leave no unknown nodes; increase the number of nodes")
        n = Wd * Ht
        # fixed values on value sides (the first listed side wins at a corner)
        fixed: dict[tuple[int, int], float] = {}
        for side in reversed(SIDES):
            if kinds[side] != "value":
                continue
            if side in ("left", "right"):
                i = 0 if side == "left" else N
                for j in range(N + 1):
                    fixed[(i, j)] = g[side](ys[j], 0.0)
            else:
                j = 0 if side == "bottom" else N
                for i in range(N + 1):
                    fixed[(i, j)] = g[side](xs[i], 0.0)
        ihx2, ihy2, i2hx, i2hy = 1 / (hx * hx), 1 / (hy * hy), 1 / (2 * hx), 1 / (2 * hy)

        def pad(z):
            P = [[0.0] * (N + 3) for _ in range(N + 3)]
            for (i, j), v in fixed.items():
                P[j + 1][i + 1] = v
            for jj in range(Ht):
                row = P[j0 + jj + 1]
                row[i0 + 1:i1 + 2] = z[jj * Wd:(jj + 1) * Wd]
            if kinds["left"] == "slope":
                for j in range(j0, j1 + 1):
                    P[j + 1][0] = P[j + 1][2] - 2 * hx * g["left"](ys[j], P[j + 1][1])
            if kinds["right"] == "slope":
                for j in range(j0, j1 + 1):
                    P[j + 1][N + 2] = P[j + 1][N] + 2 * hx * g["right"](ys[j], P[j + 1][N + 1])
            if kinds["bottom"] == "slope":
                for i in range(i0, i1 + 1):
                    P[0][i + 1] = P[2][i + 1] - 2 * hy * g["bottom"](xs[i], P[1][i + 1])
            if kinds["top"] == "slope":
                for i in range(i0, i1 + 1):
                    P[N + 2][i + 1] = P[N][i + 1] + 2 * hy * g["top"](xs[i], P[N + 1][i + 1])
            return P

        # an axis at x = 0 with a symmetry condition (axisymmetric cylindrical problems: u_x/x terms): evaluate the axis nodes at a tiny x with u_x = u_xx x
        axis = False
        if xs[0] == 0.0 and kinds["left"] == "slope":
            try:
                axis = not math.isfinite(R(0.0, ys[0], 1.0, 0.0, 0.0, 1.0, 1.0))
            except (ZeroDivisionError, ValueError, OverflowError):
                axis = True
        eps_x = 1e-9 * (xb - xa)

        def residual(z):
            P = pad(z)
            out = []
            for j in range(j0, j1 + 1):
                up, mid, dn = P[j + 2], P[j + 1], P[j]
                yj = ys[j]
                for i in range(i0, i1 + 1):
                    u = mid[i + 1]
                    ul, ur = mid[i], mid[i + 2]
                    if axis and i == 0:
                        uxx = (ur - 2 * u + ul) * ihx2
                        out.append(R(eps_x, yj, u, uxx * eps_x, (up[i + 1] - dn[i + 1]) * i2hy, uxx, (up[i + 1] - 2 * u + dn[i + 1]) * ihy2))
                    else:
                        out.append(R(xs[i], yj, u, (ur - ul) * i2hx, (up[i + 1] - dn[i + 1]) * i2hy, (ur - 2 * u + ul) * ihx2, (up[i + 1] - 2 * u + dn[i + 1]) * ihy2))
            return out

        z = [0.0] * n
        if guessf is not None:
            z = [guessf(xs[i], ys[j]) for j in range(j0, j1 + 1) for i in range(i0, i1 + 1)]
        elif fixed:
            m = sum(fixed.values()) / len(fixed)
            z = [m] * n
        kb = Wd

        def jacobian(z0, f0):
            rows = [[0.0] * (2 * kb + 1) for _ in range(n)]
            for color in range(5):
                zp = list(z0)
                eps = {}
                for jj in range(Ht):
                    for ii in range(Wd):
                        if (ii + 2 * jj) % 5 == color:
                            k = jj * Wd + ii
                            e = 1.5e-8 * max(1.0, abs(z0[k]))
                            zp[k] += e
                            eps[k] = e
                if not eps:
                    continue
                fp = residual(zp)
                for k, e in eps.items():
                    jj, ii = divmod(k, Wd)
                    for dj, di in ((0, 0), (0, -1), (0, 1), (-1, 0), (1, 0)):
                        j2, i2 = jj + dj, ii + di
                        if 0 <= j2 < Ht and 0 <= i2 < Wd:
                            r = j2 * Wd + i2
                            rows[r][k - (r - kb)] = (fp[r] - f0[r]) / e
            return rows

        f = residual(z)
        scale = max([abs(v) for v in z] + [abs(v) for v in fixed.values()] + [1e-30])
        lu = None
        prev = None
        iters = 0
        for iters in range(1, 41):
            if lu is None:
                try:
                    lu = BandedLU(n, kb, kb, jacobian(z, f))
                except SingularMatrix:
                    raise OdeError("the discretised problem is singular: the boundary conditions may not determine the solution (e.g. slope conditions on every side)") from None
            dz = lu.solve([-v for v in f])
            step = max(abs(v) for v in dz)
            lam = 1.0
            fn_old = max(abs(v) for v in f)
            while True:
                zt = [a + lam * b for a, b in zip(z, dz)]
                ft = residual(zt)
                if all(math.isfinite(v) for v in ft) and (max(abs(v) for v in ft) <= fn_old * (1 + 1e-9) or step * lam <= 1e-12 * scale):
                    break
                lam /= 2
                if lam < 1 / 64:
                    raise OdeError("Newton's method stalled; give a starting guess closer to the solution ('guess')")
            z, f = zt, ft
            scale = max([abs(v) for v in z] + [abs(v) for v in fixed.values()] + [1e-30])
            if step * lam <= 1e-10 * scale or max(abs(v) for v in f) == 0.0:
                break
            if prev is not None and step > 0.5 * prev:
                lu = None                           # the old Jacobian converges too slowly: refresh it
            prev = step
        else:
            raise OdeError("Newton's method did not converge; give a starting guess ('guess') or check that the problem has a solution")
        P = pad(z)
        field = [[P[j + 1][i + 1] for i in range(N + 1)] for j in range(N + 1)]
        return xs, ys, field, iters, n

    def run(self, values: Mapping[sp.Symbol, float]) -> Fields2D:
        vals = self._values(values)
        key = ("run", tuple(vals[s] for s in self.inputs if s not in (self.x, self.y)))
        hit = self._cache.get(key)
        if hit is not None:
            self._cache["last"] = hit.result
            return hit
        N = self.nodes + (self.nodes % 2)
        xs, ys, field, iters, unknowns = self._solve(vals, N)
        notes = []
        err = 0.0
        if N >= 2 * MIN_NODES:
            _x, _y, coarse, it2, _n = self._solve(vals, N // 2)
            fine = [row[::2] for row in field[::2]]
            scale = max(max(abs(v) for row in field for v in row), 1e-300)
            err = max(abs(a - b) for ra, rb in zip(fine, coarse) for a, b in zip(ra, rb)) / 3
            rel = err / scale
            notes.append(f"{N} × {N} intervals ({unknowns} unknowns); Newton converged in {iters} iteration{'s' if iters != 1 else ''}; estimated discretisation error {err:.2g} ({rel:.1e} relative), "
                         f"from comparison with {N // 2} × {N // 2} intervals")
            if rel > 1e-2:
                notes.append("the estimated error is above 1 %: increase the number of nodes")
        res = PdeResult("five-point finite differences, Newton with banded LU", iters, 0, 1e-10, 0.0, notes)
        out = Fields2D(xs, ys, field, res, err)
        if len(self._cache) > 20:
            self._cache.clear()
        self._cache[key] = out
        self._cache["last"] = res
        return out

    def value(self, dependent: sp.Symbol, values: Mapping[sp.Symbol, float]) -> float:
        vals = self._values(values)
        (xa, xb), (ya, yb) = self.span(values)
        x, y = vals[self.x], vals[self.y]
        tolx, toly = 1e-9 * (xb - xa), 1e-9 * (yb - ya)
        if not (xa - tolx <= x <= xb + tolx and ya - toly <= y <= yb + toly):
            raise OdeError(f"the point ({self.x.name}, {self.y.name}) = ({x:g}, {y:g}) (SI) lies outside the rectangle [{xa:g}, {xb:g}] × [{ya:g}, {yb:g}]")
        f = self.run(values)
        return interpolate2d(f, min(max(x, xa), xb), min(max(y, ya), yb))


# ---------------------------------------------------------------- building

def build(spec: Mapping[str, Any], calc, ns: dict, env: dict, custom: bool, index: int):
    from .model import Equation
    from .ode import OdeSpecError, _friendly, _make_fn, _parse, _split
    from .safeparse import bound_names

    title = str(spec.get("title") or "Steady partial differential equation").strip()[:100]
    xn, yn = spec.get("independent"), spec.get("second")
    for what, n in (("independent (first space)", xn), ("second (second space)", yn)):
        if not isinstance(n, str) or n not in calc.by_key or calc.by_key[n].is_constant:
            raise OdeSpecError(f"'{what}' must name one of the variables, got {n!r}")
    if xn == yn:
        raise OdeSpecError("the two space variables must differ")
    x, y = calc.by_key[xn].symbol, calc.by_key[yn].symbol
    if spec.get("events") or spec.get("initial"):
        raise OdeSpecError("a steady partial differential equation takes neither 'initial' values nor 'events'")
    texts = spec.get("equations")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or len(texts) != 1 or not isinstance(texts[0], str) or not texts[0].strip():
        raise OdeSpecError("a partial differential equation entry takes exactly one equation, e.g. 'diff(T, x, 2) + diff(T, y, 2) = 0'")
    text = texts[0].strip()
    nodes = spec.get("nodes", DEFAULT_NODES)
    if not isinstance(nodes, int) or isinstance(nodes, bool) or not MIN_NODES <= nodes <= MAX_NODES:
        raise OdeSpecError(f"'nodes' must be a whole number from {MIN_NODES} to {MAX_NODES}")
    found: list[str] = []
    for side in _split(text):
        try:
            tree = ast.parse(side.strip().replace("^", "**"), mode="eval")
        except SyntaxError:
            raise OdeSpecError(f"cannot read the equation {text!r}") from None
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "diff" and len(n.args) >= 2 and isinstance(n.args[0], ast.Name):
                nm = n.args[0].id
                if nm in calc.by_key and nm not in found and nm not in (xn, yn):
                    found.append(nm)
    if len(found) != 1:
        raise OdeSpecError(f"exactly one quantity must be differentiated (found {', '.join(found) or 'none'}); coupled systems of PDEs are not supported")
    un = found[0]
    uv = calc.by_key[un]
    if uv.is_constant:
        raise OdeSpecError(f"{un!r} is differentiated but is a constant")
    fn = sp.Function(un)(x, y)
    local = {**ns, un: fn}
    lt, rt = _split(text)
    loc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(text) if n not in local}}
    lhs, rhs_ = _parse(lt, loc, custom, ns), _parse(rt, loc, custom, ns)
    expanded = (lhs - rhs_).doit()
    U, UX, UY, UXX, UYY = (sp.Symbol(f"{un}__{s}", real=True) for s in ("0", "x", "y", "xx", "yy"))
    rep = {}
    for d in expanded.atoms(sp.Derivative):
        counts = dict(d.variable_count)
        sym = {(1, 0): UX, (0, 1): UY, (2, 0): UXX, (0, 2): UYY}.get((counts.get(x, 0), counts.get(y, 0)))
        if not isinstance(d.expr, AppliedUndef) or d.expr.func.__name__ != un or set(counts) - {x, y} or sym is None:
            raise OdeSpecError(f"{d}: only first and second derivatives of {un} in {xn} and {yn}, with no mixed derivatives, are supported")
        rep[d] = sym
    resid = expanded.xreplace(rep).xreplace({fn: U})
    if resid.atoms(AppliedUndef) or resid.atoms(sp.Derivative) or resid.has(sp.Integral):
        raise OdeSpecError("the equation uses the unknown in a way that cannot be handled")
    if not (resid.has(UXX) or resid.has(UYY)):
        raise OdeSpecError(f"the equation needs a second derivative of {un} in space")

    boundary = spec.get("boundary")
    if isinstance(boundary, str):
        boundary = [q.strip() for q in boundary.split("\n") if q.strip()]
    if not isinstance(boundary, list) or len(boundary) != 4 or not all(isinstance(b, str) for b in boundary):
        raise OdeSpecError("give exactly four boundary conditions, one each for left, right, bottom and top, e.g. 'left: T = T0'")
    bcs: dict[str, tuple] = {}
    condition_texts = []
    for btxt in boundary:
        m = re.match(r"^\s*(left|right|bottom|top)\s*:\s*(.+)$", btxt)
        if not m or m.group(1) in bcs:
            raise OdeSpecError(f"boundary conditions are written 'left: …', 'right: …', 'bottom: …' and 'top: …' (one of each); got {btxt!r}")
        side, cond = m.groups()
        normal, along = (x, y) if side in ("left", "right") else (y, x)
        nsym, SL = (UX, UY) if side in ("left", "right") else (UY, UX)
        cl, cr = _split(cond)
        loc2 = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(cond) if n not in local}}
        a, b = _parse(cl, loc2, custom, ns), _parse(cr, loc2, custom, ns)
        res = (a - b).doit()
        rep2 = {}
        for d in res.atoms(sp.Derivative):
            counts = dict(d.variable_count)
            if not isinstance(d.expr, AppliedUndef) or d.expr.func.__name__ != un or counts != {normal: 1}:
                raise OdeSpecError(f"the {side} condition may contain {un} and its first derivative across the side, diff({un}, {normal.name}); got {d}")
            rep2[d] = nsym
        res = res.xreplace(rep2).xreplace({fn: U})
        if res.atoms(AppliedUndef) or res.atoms(sp.Derivative) or normal in res.free_symbols:
            raise OdeSpecError(f"the {side} condition cannot involve {normal.name} (it is fixed on that side); it may involve {along.name}")
        try:
            kind, sol = ("slope", sp.solve(res, nsym)) if res.has(nsym) else ("value", sp.solve(res, U))
        except Exception as exc:  # noqa: BLE001
            raise OdeSpecError(f"cannot use the {side} condition {cond!r}: {exc}") from None
        if len(sol) != 1 or sol[0].has(nsym) or (kind == "value" and sol[0].has(U)):
            raise OdeSpecError(f"the {side} condition {cond!r} must determine the {'slope' if kind == 'slope' else 'value'} uniquely")
        bcs[side] = (kind, sol[0], (a, b))
        condition_texts.append((a, b, f"on the {side} side"))
    if all(k == "slope" for k, _e, _w in bcs.values()):
        raise OdeSpecError("a value must be given on at least one side, otherwise the solution is not unique")

    def interval(k0, k1, dflt):
        a_ = _parse(str(spec.get(k0, dflt)), ns, custom, ns) if str(spec.get(k0, dflt)).strip() else sp.Integer(0)
        b_ = _parse(str(spec.get(k1) or ""), ns, custom, ns) if str(spec.get(k1) or "").strip() else None
        return a_, b_
    x0, x1 = interval("start", "end", "0")
    y0, y1 = interval("second_start", "second_end", "0")
    if x1 is None or y1 is None:
        raise OdeSpecError("a steady partial differential equation needs 'end' and 'second_end' (where the two intervals end)")
    if any(s in e.free_symbols for e in (x0, x1, y0, y1) for s in (x, y)):
        raise OdeSpecError("the ends of the intervals cannot depend on the space variables")
    guess = None
    gt = spec.get("guess") or []
    if isinstance(gt, str):
        gt = [q.strip() for q in gt.split("\n") if q.strip()]
    if not isinstance(gt, list) or len(gt) > 1 or not all(isinstance(q, str) for q in gt):
        raise OdeSpecError("'guess' is one line such as 'T = 300 K' (it may depend on the space variables)")
    if gt:
        gl, gr = _split(gt[0])
        if gl.strip() != un:
            raise OdeSpecError(f"the guess must be for {un}, e.g. '{un} = 300 K'")
        guess = _parse(gr, {**ns}, custom, ns)

    internal = {U, UX, UY, UXX, UYY}
    exprs = [resid, x0, x1, y0, y1, *[e for _k, e, _w in bcs.values()], *( [guess] if guess is not None else [])]
    declared = {v.symbol for v in calc.variables}
    params = sorted({s for e in exprs for s in e.free_symbols if s not in internal and s not in (x, y)}, key=lambda s: s.name)
    for s in params:
        if s not in declared:
            raise OdeSpecError(f"{s} is not a variable of this calculation")

    dim_x, unit_x = env[x]
    dim_y, unit_y = env[y]
    dim_u, unit_u = env[uv.symbol]
    genv = dict(env)
    genv[U] = (dim_u, unit_u)
    genv[UX], genv[UY] = (dim_u / dim_x, unit_u / unit_x), (dim_u / dim_y, unit_u / unit_y)
    genv[UXX], genv[UYY] = (dim_u / dim_x ** 2, unit_u / unit_x ** 2), (dim_u / dim_y ** 2, unit_u / unit_y ** 2)
    try:
        analyze(resid, genv)                                       # every term of the equation must have the same dimension
        for e, d_, what in ((x0, dim_x, "first start"), (x1, dim_x, "first end"), (y0, dim_y, "second start"), (y1, dim_y, "second end")):
            if e != 0:
                de, _ = analyze(e, genv)
                if de != d_:
                    raise DimensionError(f"the {what} of the interval has dimension [{de}], expected [{d_}]")
        for side, (kind, expr, _w) in bcs.items():
            if expr == 0:
                continue
            normal_dim = dim_x if side in ("left", "right") else dim_y
            db, _ = analyze(expr, genv)
            want = dim_u if kind == "value" else dim_u / normal_dim
            if db != want:
                raise DimensionError(f"the {side} condition gives the {'value' if kind == 'value' else 'slope'} the dimension [{db}], expected [{want}]")
        if guess is not None and guess != 0:
            dg, _ = analyze(guess, genv)
            if dg != dim_u:
                raise DimensionError(f"the guess has dimension [{dg}], expected [{dim_u}]")
    except DimensionError as exc:
        raise OdeSpecError(f"{title}: {_friendly(str(exc))}") from None

    inputs = sorted({x, y, *params, *[s for e in (x0, x1, y0, y1) for s in e.free_symbols]}, key=lambda s: s.name)
    system = Pde2dSystem(title, [text], x, y, x0, x1, y0, y1, uv.symbol, nodes, (U, UX, UY, UXX, UYY), resid, bcs, guess, [(lhs, rhs_)], condition_texts, params, inputs,
                         guess_texts=[q.strip() for q in gt])
    dim, unit = env[uv.symbol]
    node = _make_fn(system, uv.symbol, (dim, unit), uv.latex or un, index * 10)
    system.fns[uv.symbol] = node
    eq = Equation(title, f"{un} = numerical solution of {text}", uv.symbol, node(*system.inputs), frozenset({uv.symbol, *system.inputs}), None)
    eq.ode = system
    return system, [eq]
