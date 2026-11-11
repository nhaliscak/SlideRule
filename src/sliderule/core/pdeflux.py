"""Conservation laws (advection, Burgers' equation, gas dynamics, shallow water) with shocks: finite volumes with a limited, shock-capturing flux.

An ``odes`` entry with ``time``, ``independent`` (space) and ``"scheme": "conservative"`` is handled here. Each equation is written in conservation form::

    {"title": "Burgers", "independent": "x", "start": "0", "end": "L", "time": "t", "scheme": "conservative",
     "equations": ["diff(u, t) + diff(u**2/2, x) = 0"],
     "boundary": ["start: diff(u, x) = 0", "end: diff(u, x) = 0"], "initial": ["u = Piecewise((ul, x < L/2), (ur, True))"]}

    {"title": "Dam break", "equations": ["diff(h, t) + diff(q, x) = 0", "diff(q, t) + diff(q**2/h + g*h**2/2, x) = 0"], ...}

``diff(F, x)`` is the divergence of a flux ``F`` of the fields; the other terms may contain the fields, ``x``, ``t`` and parameters (a source), and ``diff(u, x, 2)`` adds a
viscous term. The unknowns are the conserved quantities. Conditions on each side of each field: a value (``u = g``: the boundary state, which for a wall condition such as
``q = 0`` makes the wall reflect), ``diff(u, x) = 0`` (outflow), or the space variable listed under ``periodic``.

Numerics: cell averages on a uniform grid, second-order MUSCL reconstruction with the minmod limiter, the Rusanov (local Lax-Friedrichs) flux, strong-stability-preserving
Runge-Kutta 3 in time with the step set by the fastest wave. Shocks are captured within about two cells and the scheme never creates new extrema. The grid is solved
twice (N and N/2 cells) and the difference is reported as an estimate of the discretisation error; with a shock the error of the cell values converges only as the
first power of the cell size, which is the nature of the problem.

Dry bed (shallow water over a bed that is initially dry, a wetting front, a flood advancing over dry land): ``"dry": {"depth": "h", "zero": ["q"], "tol": "1e-6"}`` marks the depth
field and the fields (momentum) that must vanish where the depth is below ``tol`` times its largest initial value. The depth is kept non-negative, the momentum is set
to zero in dry cells and at dry interface states, fluxes, wave speeds and sources are evaluated with the depth floored at that tolerance (so ``q**2/h`` and friction terms
``q*abs(q)/h`` stay finite), and the time step is cut to a quarter-cell Courant number so that the depth cannot go negative from the fluxes alone. Mass is conserved
except for the clipping of round-off negatives, which is negligible at that step size.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import sympy as sp
from sympy.core.function import AppliedUndef

from .dimcheck import DIMENSIONLESS, DimensionError, analyze
from .numeric_ode import OdeError
from .pde import PdeResult
from .pdemulti import MAX_FIELDS, MultiFields, PdeMulti, _lam

DEFAULT_CELLS = 200
MIN_CELLS, MAX_CELLS = 20, 2000
CFL = 0.4
MAX_STEPS = 400_000


def _stack(res, shape):
    """A list (or nested list) of arrays and scalars from ``lambdify`` as one array, each entry broadcast to ``shape``."""
    if isinstance(res, (list, tuple)):
        return np.array([_stack(r, shape) for r in res], float)
    return np.broadcast_to(np.asarray(res, float), shape)


def _minmod(a, b):
    return np.where(a * b > 0, np.where(np.abs(a) < np.abs(b), a, b), 0.0)


@dataclass
class FluxSystem(PdeMulti):
    flux: list = None                  # per field: flux expression Phi_k(fields, x, t) with u_t + d(Phi_k)/dx = source
    viscous: list = None               # per field: coefficient of u_xx (or 0)
    source: list = None                # per field: source expression
    why_numeric: str = "the conservation law is solved numerically by a shock-capturing finite-volume method"
    dry_depth: int = -1                # index of the depth field when a dry bed is allowed (-1: none)
    dry_zero: tuple = ()               # indices of the fields set to zero where the depth is below the tolerance
    dry_tol: float = 1e-6              # tolerance relative to the largest initial depth
    cell_centered = True

    def _bound(self, vals: dict):
        key = ("flux", tuple(vals[s] for s in self.params))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        sub = {s: sp.Float(vals[s], 17) for s in self.params}
        U = [d["U"] for d in self.syms]
        args = [self.x, self.t, *U]
        phi = _lam(args, [e.xreplace(sub) for e in self.flux])
        speeds = sp.Matrix(self.flux).jacobian(U).xreplace(sub)
        jac = _lam(args, speeds.tolist())
        src = _lam(args, [e.xreplace(sub) for e in self.source])
        visc = _lam(args, [e.xreplace(sub) for e in self.viscous])
        bcs = {}
        for (k, side), (kind, expr, _w) in self.bcs.items():
            bcs[(k, side)] = (kind, _lam([self.t], expr.xreplace(sub)) if kind == "value" else None)
        u0 = [_lam([self.x], e.xreplace(sub)) for e in self.u0]
        out = (phi, jac, src, visc, bcs, u0)
        for kk in [kk for kk in self._cache if isinstance(kk, tuple) and kk and kk[0] == "flux"][3:]:
            del self._cache[kk]
        self._cache[key] = out
        return out

    def _integrate(self, vals: dict, times: list[float], N: int, t_end: float):
        phi, jacf, srcf, viscf, bcs, u0f = self._bound(vals)
        lo, hi = self.span({s: vals[s] for s in self.inputs})
        h = (hi - lo) / N
        xc = lo + h * (np.arange(N) + 0.5)
        nf = len(self.fields)
        per = self.x.name in self.periodic
        kinds = [{s: ("periodic" if per else self.bcs[(k, s)][0]) for s in ("start", "end")} for k in range(nf)]

        def initial():
            U = np.empty((nf, N))
            for k in range(nf):
                U[k] = np.broadcast_to(np.asarray(u0f[k](xc), float), (N,))
            return U
        U0 = initial()
        if not np.all(np.isfinite(U0)):
            raise OdeError("the initial condition is not finite at every cell")
        dry = self.dry_depth >= 0
        eps = 0.0
        if dry:
            if np.any(U0[self.dry_depth] < 0):
                raise OdeError("the initial depth is negative somewhere")
            eps = self.dry_tol * max(float(np.max(U0[self.dry_depth])), 1e-300)

        def fix(S):
            """Non-negative depth, and zero momentum where the depth is below the tolerance."""
            if not dry:
                return S
            S = S.copy()
            S[self.dry_depth] = np.maximum(S[self.dry_depth], 0.0)
            wet = S[self.dry_depth] >= eps
            for kz in self.dry_zero:
                S[kz] = np.where(wet, S[kz], 0.0)
            return S

        def floored(S):
            """The states with the depth floored at the tolerance: what the flux, wave speed and source formulas may be evaluated at."""
            if not dry:
                return S
            S = S.copy()
            S[self.dry_depth] = np.maximum(S[self.dry_depth], eps)
            return S
        U0 = fix(U0)

        def ghosts(U, t, w=2):
            """Two ghost cells on each side from the boundary conditions."""
            G = np.empty((nf, N + 2 * w))
            G[:, w:-w] = U
            for k in range(nf):
                if per:
                    G[k, :w], G[k, -w:] = U[k, -w:], U[k, :w]
                    continue
                for side, sl, edge in (("start", slice(0, w), U[k, 0]), ("end", slice(-w, None), U[k, -1])):
                    kind, g = bcs[(k, side)]
                    if kind == "value":
                        G[k, sl] = 2.0 * float(g(t)) - edge        # the boundary-state value g lies half a cell outside the first cell: ghost = 2 g - u
                    else:
                        G[k, sl] = edge                            # outflow / zero gradient
            return G

        def numerics(U, t):
            G = ghosts(U, t)
            d_l, d_r = G[:, 1:-1] - G[:, :-2], G[:, 2:] - G[:, 1:-1]
            slope = _minmod(d_l, d_r)                              # for cells -1 .. N (one ghost layer each side)
            left_state = G[:, 1:-1] + 0.5 * slope                   # value at the right edge of each of those cells
            right_state = G[:, 1:-1] - 0.5 * slope                  # value at the left edge
            UL, UR = fix(left_state[:, :-1]), fix(right_state[:, 1:])         # states on each side of the N + 1 interfaces
            xi = lo + h * np.arange(N + 1)
            ULs, URs = floored(UL), floored(UR)
            FL = _stack(phi(xi, t, *ULs), (N + 1,))
            FR = _stack(phi(xi, t, *URs), (N + 1,))
            # the fastest wave at each interface: spectral radius of the flux Jacobian at either state
            def radius(S):
                J = _stack(jacf(xi, t, *S), (N + 1,))
                if nf == 1:
                    return np.abs(J[0, 0])
                return np.max(np.abs(np.linalg.eigvals(np.moveaxis(J, -1, 0))), axis=1)
            a = np.maximum(radius(ULs), radius(URs))
            F = 0.5 * (FL + FR) - 0.5 * a * (UR - UL)
            rhs = -(F[:, 1:] - F[:, :-1]) / h
            Us = floored(U)
            rhs = rhs + _stack(srcf(xc, t, *Us), (N,))
            vis = _stack(viscf(xc, t, *Us), (N,))
            if np.any(vis != 0):
                rhs = rhs + vis * (G[:, 2:] - 2 * G[:, 1:-1] + G[:, :-2])[:, 1:-1] / (h * h)
            return rhs, float(np.max(a)), (float(np.max(np.abs(vis))) if np.any(vis != 0) else 0.0)

        want = sorted({tt for tt in times if 0.0 < tt < t_end} | ({t_end} if t_end > 0 else set()))
        U, t = U0.copy(), 0.0
        ts, snaps = [0.0], [U0.copy()]
        steps = 0
        nxt = 0
        while nxt < len(want):
            rhs0, amax, nu = numerics(U, t)
            if not np.all(np.isfinite(rhs0)):
                raise OdeError("the solution became non-finite (a negative depth or density? an unstable state?)")
            dt = (0.25 if dry else CFL) * h / max(amax, 1e-300)
            if nu > 0:
                dt = min(dt, 0.25 * h * h / nu)
            target = want[nxt]
            if t + dt >= target * (1 - 1e-12):
                dt, hit = target - t, True
            else:
                hit = False
            steps += 1
            if steps > MAX_STEPS:
                raise OdeError("the time integration needs too many steps (a very fast wave or a very fine grid); use fewer cells or a shorter time")
            u1 = fix(U + dt * rhs0)
            u2 = fix(0.75 * U + 0.25 * (u1 + dt * numerics(u1, t + dt)[0]))
            U = fix(U / 3.0 + 2.0 / 3.0 * (u2 + dt * numerics(u2, t + 0.5 * dt)[0]))
            t = target if hit else t + dt
            if hit:
                ts.append(t)
                snaps.append(U.copy())
                nxt += 1
        fields_t = [[snap[k][None, :] for k in range(nf)] for snap in snaps]
        return ts, fields_t, steps * 3, steps * 3, xc, (np.array([0.0]), np.array([0.0]))


def build(spec: Mapping[str, Any], calc, ns: dict, env: dict, custom: bool, index: int):
    from .model import Equation
    from .ode import OdeSpecError, _friendly, _make_fn, _parse, _split
    from .safeparse import bound_names

    title = str(spec.get("title") or "Conservation law").strip()[:100]
    xn, tn = spec.get("independent"), spec.get("time")
    for what, n in (("independent (space)", xn), ("time", tn)):
        if not isinstance(n, str) or n not in calc.by_key or calc.by_key[n].is_constant:
            raise OdeSpecError(f"'{what}' must name one of the variables, got {n!r}")
    if xn == tn:
        raise OdeSpecError("the space and time variables must differ")
    if spec.get("second") or spec.get("events") or spec.get("sources"):
        raise OdeSpecError("a conservation law is solved in one space dimension, without events or point sources (write a source term in the equation)")
    x, t = calc.by_key[xn].symbol, calc.by_key[tn].symbol
    texts = spec.get("equations")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not texts or not all(isinstance(q, str) and q.strip() for q in texts) or len(texts) > MAX_FIELDS:
        raise OdeSpecError(f"give 1 to {MAX_FIELDS} equations in conservation form, e.g. 'diff(u, t) + diff(u**2/2, x) = 0'")
    texts = [q.strip() for q in texts]
    cells = spec.get("nodes", DEFAULT_CELLS)
    if not isinstance(cells, int) or isinstance(cells, bool) or not MIN_CELLS <= cells <= MAX_CELLS:
        raise OdeSpecError(f"'nodes' (the number of cells) must be a whole number from {MIN_CELLS} to {MAX_CELLS}")
    field_names: list[str] = []
    for text in texts:
        for side in _split(text):
            try:
                tree = ast.parse(side.strip().replace("^", "**"), mode="eval")
            except SyntaxError:
                raise OdeSpecError(f"cannot read the equation {text!r}") from None
            for n in ast.walk(tree):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "diff" and len(n.args) == 2 and isinstance(n.args[0], ast.Name)
                        and isinstance(n.args[1], ast.Name) and n.args[1].id == tn and n.args[0].id in calc.by_key and n.args[0].id not in field_names):
                    field_names.append(n.args[0].id)
    if len(field_names) != len(texts):
        raise OdeSpecError(f"{len(texts)} equation(s) but {len(field_names)} quantit{'y' if len(field_names) == 1 else 'ies'} differentiated with respect to {tn} "
                           f"({', '.join(field_names) or 'none'}): give one conservation equation per field")
    fields = [calc.by_key[n].symbol for n in field_names]
    for n, f in zip(field_names, fields):
        if calc.by_key[n].is_constant or f in (x, t):
            raise OdeSpecError(f"{n!r} is differentiated but is not a (non-constant) field variable")
    nf = len(fields)
    fn = {n: sp.Function(n)(x, t) for n in field_names}
    local = {**ns, **fn}
    syms = [{"U": sp.Symbol(f"{n}__0", real=True)} for n in field_names]
    UT = [sp.Symbol(f"{n}__t", real=True) for n in field_names]
    UXX = [sp.Symbol(f"{n}__xx", real=True) for n in field_names]

    def to_u(e):
        return e.xreplace({fn[n]: syms[k]["U"] for k, n in enumerate(field_names)})

    flux_syms: list = []
    resids, written = [], []
    flux_exprs: list = []
    for text in texts:
        lt, rt = _split(text)
        loc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(text) if n not in local}}
        lhs, rhs_ = _parse(lt, loc, custom, ns), _parse(rt, loc, custom, ns)
        written.append((lhs, rhs_))
        e = lhs - rhs_
        rep = {}
        for d in sorted(e.atoms(sp.Derivative), key=lambda q: -len(str(q))):
            counts = dict(d.variable_count)
            if counts == {t: 1} and isinstance(d.expr, AppliedUndef) and d.expr.func.__name__ in field_names:
                rep[d] = UT[field_names.index(d.expr.func.__name__)]
            elif counts == {x: 1}:
                fs = sp.Symbol(f"FX__{len(flux_exprs)}", real=True)
                flux_syms.append(fs)
                flux_exprs.append(to_u(d.expr.doit()))
                rep[d] = fs
            elif counts == {x: 2} and isinstance(d.expr, AppliedUndef) and d.expr.func.__name__ in field_names:
                rep[d] = UXX[field_names.index(d.expr.func.__name__)]
            else:
                raise OdeSpecError(f"{d}: a conservation law has the time derivative of a field, divergences diff(flux, {xn}) and, optionally, diff(field, {xn}, 2)")
        r = to_u(e.xreplace(rep))
        if r.atoms(AppliedUndef) or r.atoms(sp.Derivative) or r.has(sp.Integral):
            raise OdeSpecError(f"the equation {text!r} must be in conservation form: the time derivative, divergences diff(flux, {xn}), and terms without derivatives")
        resids.append(r)
    try:
        sols = sp.solve(resids, UT, dict=True)
    except Exception as exc:  # noqa: BLE001
        raise OdeSpecError(f"cannot solve the equations for the time derivatives: {exc}") from None
    if len(sols) != 1 or any(u not in sols[0] for u in UT):
        raise OdeSpecError("each equation must be solvable for the time derivative of its field")
    rhs_all = [sols[0][u] for u in UT]
    flux, viscous, source = [], [], []
    for k, r in enumerate(rhs_all):
        phi = sp.Integer(0)
        for fs, fe in zip(flux_syms, flux_exprs):
            c = sp.diff(r, fs)
            if c.has(*flux_syms) or c.has(*UT):
                raise OdeSpecError("the flux divergences must enter each equation linearly")
            phi += -c * fe
        v = sp.diff(r, UXX[k])
        rest = r.xreplace({fs: 0 for fs in flux_syms}).xreplace({u: 0 for u in UXX})
        if any(rest.has(s) for s in UXX) or v.has(*UXX):
            raise OdeSpecError("a viscous term is a coefficient times diff(field, x, 2) of the same field")
        flux.append(phi)
        viscous.append(v)
        source.append(rest)
    if all(f == 0 for f in flux):
        raise OdeSpecError("the equations contain no flux divergence diff(flux, x): for diffusion or other smooth problems use the ordinary partial-differential-equation form")
    periodic = spec.get("periodic") or []
    if isinstance(periodic, str):
        periodic = [q.strip() for q in periodic.replace(",", " ").split() if q.strip()]
    if not isinstance(periodic, list) or any(q != xn for q in periodic):
        raise OdeSpecError(f"'periodic' may list only the space variable {xn}")
    boundary = spec.get("boundary") or []
    if isinstance(boundary, str):
        boundary = [q.strip() for q in boundary.split("\n") if q.strip()]
    need = 0 if periodic else 2 * nf
    if not isinstance(boundary, list) or len(boundary) != need:
        raise OdeSpecError(f"{need} boundary condition{'s' if need != 1 else ''} needed (one for each field at 'start' and 'end'), or list the space variable under 'periodic'")
    bcs: dict = {}
    condition_texts: list = []
    for btxt in boundary:
        m = re.match(r"^\s*(start|end)\s*:\s*(.+)$", btxt)
        if not m:
            raise OdeSpecError(f"boundary conditions are written 'start: …' and 'end: …'; got {btxt!r}")
        side, cond = m.groups()
        cl, cr = _split(cond)
        loc2 = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(cond) if n not in local}}
        a, b = _parse(cl, loc2, custom, ns), _parse(cr, loc2, custom, ns)
        res = (a - b).doit()
        used = {f.func.__name__ for f in res.atoms(AppliedUndef)} & set(field_names)
        if len(used) != 1:
            raise OdeSpecError(f"the condition {btxt!r} must involve exactly one field")
        k = field_names.index(next(iter(used)))
        UX = sp.Symbol(f"{field_names[k]}__x", real=True)
        rep2 = {}
        for d in res.atoms(sp.Derivative):
            if not (isinstance(d.expr, AppliedUndef) and dict(d.variable_count) == {x: 1}):
                raise OdeSpecError(f"the condition {btxt!r} may use the field or its slope diff({field_names[k]}, {xn})")
            rep2[d] = UX
        res = res.xreplace(rep2).xreplace({fn[field_names[k]]: syms[k]["U"]})
        if res.has(UX):
            sol = sp.solve(res, UX)
            if len(sol) != 1 or sol[0] != 0:
                raise OdeSpecError(f"the condition {btxt!r}: a slope condition must be an outflow condition, diff({field_names[k]}, {xn}) = 0 (the boundary state of a hyperbolic problem is a value)")
            kind, expr = "slope", sp.Integer(0)
        else:
            sol = sp.solve(res, syms[k]["U"])
            if len(sol) != 1 or sol[0].has(syms[k]["U"]) or sol[0].has(x):
                raise OdeSpecError(f"the condition {btxt!r} must give the value of {field_names[k]} (a function of {tn} and parameters)")
            kind, expr = "value", sol[0]
        if (k, side) in bcs:
            raise OdeSpecError(f"{field_names[k]} has two conditions at {side}")
        bcs[(k, side)] = (kind, expr, (a, b))
        condition_texts.append((a, b, f"{field_names[k]} at {side}"))
    if not periodic:
        for k in range(nf):
            for side in ("start", "end"):
                if (k, side) not in bcs:
                    raise OdeSpecError(f"{field_names[k]} needs a condition at {side}")
    initial = spec.get("initial") or []
    if isinstance(initial, str):
        initial = [q.strip() for q in initial.split("\n") if q.strip()]
    u0: list = [None] * nf
    for itxt in initial:
        il, ir = _split(itxt)
        il = il.strip()
        if il not in field_names or u0[field_names.index(il)] is not None:
            raise OdeSpecError(f"an initial condition's left side must be a field, once each ({', '.join(field_names)}); got {il!r}")
        u0[field_names.index(il)] = _parse(ir, {**ns}, custom, ns)
    miss = [field_names[k] for k in range(nf) if u0[k] is None]
    if miss:
        raise OdeSpecError(f"missing initial value for {', '.join(miss)} (it may depend on {xn})")
    start = _parse(str(spec.get("start", "0")), ns, custom, ns) if str(spec.get("start", "0")).strip() else sp.Integer(0)
    end = _parse(str(spec.get("end") or ""), ns, custom, ns) if str(spec.get("end") or "").strip() else None
    if end is None:
        raise OdeSpecError("a conservation law needs an 'end' (where the interval ends)")
    if any(s in e.free_symbols for e in (start, end) for s in (x, t)):
        raise OdeSpecError("the ends of the interval cannot depend on the space or time variable")
    dry_depth, dry_zero, dry_tol = -1, (), 1e-6
    dry_in = spec.get("dry")
    if dry_in:
        if not isinstance(dry_in, Mapping) or dry_in.get("depth") not in field_names:
            raise OdeSpecError(f"'dry' is an object such as {{\"depth\": \"h\", \"zero\": [\"q\"], \"tol\": \"1e-6\"}} where depth names one of the fields ({', '.join(field_names)})")
        zero = dry_in.get("zero") or []
        if isinstance(zero, str):
            zero = [q.strip() for q in zero.replace(",", " ").split() if q.strip()]
        if not isinstance(zero, list) or any(q not in field_names or q == dry_in["depth"] for q in zero):
            raise OdeSpecError(f"'dry.zero' lists the other fields (momentum) that vanish where the depth does: {', '.join(q for q in field_names if q != dry_in['depth']) or 'none'}")
        try:
            dry_tol = float(dry_in.get("tol", 1e-6))
        except (TypeError, ValueError):
            raise OdeSpecError("'dry.tol' must be a number between 1e-12 and 0.1") from None
        if not 1e-12 <= dry_tol <= 0.1:
            raise OdeSpecError("'dry.tol' must be a number between 1e-12 and 0.1")
        dry_depth, dry_zero = field_names.index(dry_in["depth"]), tuple(field_names.index(q) for q in zero)
    internal = {s["U"] for s in syms}
    exprs = [*flux, *viscous, *source, *u0, start, end, *[e for _k, e, _w in bcs.values()]]
    declared = {v.symbol for v in calc.variables}
    params = sorted({s for e in exprs for s in e.free_symbols if s not in internal and s not in (x, t)}, key=lambda s: s.name)
    for s in params:
        if s not in declared:
            raise OdeSpecError(f"{s} is not a variable of this calculation")
    if any(t in e.free_symbols for e in u0):
        raise OdeSpecError("the initial state cannot depend on time")

    dim_t, unit_t = env[t]
    dim_x, unit_x = env[x]
    genv = dict(env)
    for k, f in enumerate(fields):
        genv[syms[k]["U"]] = env[f]
    try:
        for k, f in enumerate(fields):
            du = env[f][0]
            if flux[k] != 0:
                df, _ = analyze(flux[k], genv)
                if df != du * dim_x / dim_t:
                    raise DimensionError(f"the flux of {field_names[k]} has dimension [{df}], expected [{du * dim_x / dim_t}] (the field times length per time)")
            if viscous[k] != 0:
                dv, _ = analyze(viscous[k], genv)
                if dv != dim_x ** 2 / dim_t:
                    raise DimensionError(f"the coefficient of the viscous term of {field_names[k]} has dimension [{dv}], expected [{dim_x ** 2 / dim_t}]")
            if source[k] != 0:
                ds, _ = analyze(source[k], genv)
                if ds != du / dim_t:
                    raise DimensionError(f"the source of {field_names[k]} has dimension [{ds}], expected [{du / dim_t}]")
            if u0[k] != 0:
                di, _ = analyze(u0[k], genv)
                if di != du:
                    raise DimensionError(f"the initial value of {field_names[k]} has dimension [{di}], expected [{du}]")
        for e, what in ((start, "start"), (end, "end")):
            if e != 0:
                de, _ = analyze(e, genv)
                if de != dim_x:
                    raise DimensionError(f"the {what} of the interval has dimension [{de}], expected [{dim_x}]")
        for (k, side), (kind, expr, _w) in bcs.items():
            if kind == "value" and expr != 0:
                db, _ = analyze(expr, genv)
                if db != env[fields[k]][0]:
                    raise DimensionError(f"the {side} condition of {field_names[k]} has dimension [{db}], expected [{env[fields[k]][0]}]")
    except DimensionError as exc:
        raise OdeSpecError(f"{title}: {_friendly(str(exc))}") from None

    inputs = sorted({x, t, *params, *[s for e in (start, end) for s in e.free_symbols]}, key=lambda s: s.name)
    cond_shown = condition_texts + [(sp.Function(n)(x, 0), u0[k], "initial") for k, n in enumerate(field_names)]
    system = FluxSystem(title, texts, x, None, t, start, end, None, None, fields, syms, [-f for f in flux], bcs, list(periodic), u0, [], cells, written, cond_shown, params, inputs,
                        flux=flux, viscous=viscous, source=source, dry_depth=dry_depth, dry_zero=dry_zero, dry_tol=dry_tol)
    for k, f in enumerate(fields):
        node = _make_fn(system, f, env[f], calc.by_key[field_names[k]].latex or field_names[k], index * 10 + k)
        system.fns[f] = node
    eqs = []
    for k, f in enumerate(fields):
        eq = Equation(f"{title}: {field_names[k]}" if nf > 1 else title, f"{field_names[k]} = numerical solution of {'; '.join(texts)}", f, system.fns[f](*system.inputs),
                      frozenset({f, *system.inputs}), None)
        eq.ode = system
        eqs.append(eq)
    _ = (DIMENSIONLESS, math, PdeResult, MultiFields, OdeError)
    return system, eqs
