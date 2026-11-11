"""Simultaneous (coupled) algebraic equations.

The engine solves one unknown per equation in dependency order. When that stalls because several equations share several unknowns (Colebrook for the velocity
of a given head loss, node voltages, a heat balance with two unknown temperatures), those equations form a *block*:

* :func:`find_blocks` matches every equation to one of its unknowns (maximum bipartite matching) and takes the strongly connected components of the
  resulting dependency graph; a component with two or more equations is a block. A block is *ready* when its equations contain no unknowns outside it.
* :func:`solve_block` solves a ready block: exactly (symbolically) when the equations are linear in the unknowns, otherwise by damped Newton iteration with
  an exact Jacobian from several starting points, so that a second solution is noticed and reported. Variables keep to their physical domain (positive unless
  signed, their min/max, or a user search range).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import sympy as sp
from sympy.core.function import AppliedUndef

from .special import fast_lambdify

MAX_BLOCK = 12
MAX_SYMBOLIC = 4
MAX_ITER = 80


class BlockError(ValueError):
    pass


@dataclass
class Block:
    eqs: list                    # equations
    unknowns: list               # symbols; eqs[i] is matched with unknowns[i]
    external: list = field(default_factory=list)       # known symbols the block's equations use


@dataclass
class BlockResult:
    values: dict                 # symbol -> SI value
    method: str                  # "linear (exact)" | "linear (numerical)" | "Newton"
    exprs: dict | None           # symbol -> closed-form expression (linear systems), else None
    info: dict


# ---------------------------------------------------------------- structure

def find_blocks(equations: Sequence, known: set) -> list[Block]:
    """Coupled blocks (two or more equations) among ``equations``, in a valid solution order, ignoring which of them are ready."""
    eqs = [e for e in equations if e.symbols - known]
    unk = {id(e): sorted(e.symbols - known, key=lambda s: s.name) for e in eqs}
    match_eq: dict[int, sp.Symbol] = {}       # equation id -> unknown
    match_sym: dict[sp.Symbol, Any] = {}      # unknown -> equation

    def augment(e, seen: set) -> bool:
        for s in unk[id(e)]:
            if s in seen:
                continue
            seen.add(s)
            if s not in match_sym or augment(match_sym[s], seen):
                match_sym[s] = e
                match_eq[id(e)] = s
                return True
        return False

    for e in eqs:
        augment(e, set())
    matched = [e for e in eqs if id(e) in match_eq]
    # graph: e -> the equation that determines each other unknown of e
    graph = {id(e): [match_sym[s] for s in unk[id(e)] if s in match_sym and match_sym[s] is not e and id(match_sym[s]) in match_eq] for e in matched}
    by_id = {id(e): e for e in matched}
    order: list[list] = []
    index: dict[int, int] = {}
    low: dict[int, int] = {}
    stack: list[int] = []
    on: set[int] = set()
    counter = [0]

    def strong(v: int) -> None:                  # Tarjan; components come out in reverse topological order, i.e. dependencies first
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph[v]:
            wi = id(w)
            if wi not in index:
                strong(wi)
                low[v] = min(low[v], low[wi])
            elif wi in on:
                low[v] = min(low[v], index[wi])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            order.append(comp)

    for e in matched:
        if id(e) not in index:
            strong(id(e))
    blocks = []
    for comp in order:
        if len(comp) < 2:
            continue
        es = [by_id[i] for i in comp]
        us = [match_eq[i] for i in comp]
        ext = sorted({s for e in es for s in e.symbols if s in known}, key=lambda s: s.name)
        blocks.append(Block(es, us, ext))
    return blocks


def is_ready(block: Block, known: set) -> bool:
    inside = set(block.unknowns)
    return all((e.symbols - known) <= inside for e in block.eqs)


def needed_unknowns(equations: Sequence, known: set, targets: set) -> set:
    """Unknowns the targets depend on, following the matching (used to avoid solving blocks nobody asked for)."""
    eqs = [e for e in equations if e.symbols - known]
    owner: dict = {}
    blocks = find_blocks(eqs, known)
    for b in blocks:
        for s, e in zip(b.unknowns, b.eqs):
            owner[s] = b
    need = set(targets)
    changed = True
    while changed:
        changed = False
        for s in list(need):
            b = owner.get(s)
            if b is None:
                continue
            for e in b.eqs:
                for u in e.symbols - known:
                    if u not in need:
                        need.add(u)
                        changed = True
    return need


# ---------------------------------------------------------------- solving

def _linear_form(exprs: list, syms: list):
    try:
        a, b = sp.linear_eq_to_matrix(exprs, syms)
    except Exception:  # noqa: BLE001 - nonlinear in the unknowns
        return None
    if any(a.has(s) for s in syms) or any(b.has(s) for s in syms):
        return None
    return a, b


def _domain(calc, s: sp.Symbol, search: Mapping[str, tuple[float, float]] | None) -> tuple[float, float]:
    v = calc.by_key[s.name]
    if search and s.name in search:
        return search[s.name]
    lo = v.to_si(v.min) if v.min is not None else (-math.inf if v.signed else 0.0)
    hi = v.to_si(v.max) if v.max is not None else math.inf
    if not v.signed:
        lo = max(lo, 0.0)
    return lo, hi


def solve_block(block: Block, known: Mapping, calc, evaluate: Callable, search: Mapping[str, tuple[float, float]] | None = None, isolate: Callable | None = None) -> BlockResult:
    syms = block.unknowns
    m = len(syms)
    if m > MAX_BLOCK:
        raise BlockError(f"{m} equations are coupled; at most {MAX_BLOCK} can be solved simultaneously")
    resid = [e.lhs - e.rhs for e in block.eqs]
    # ---- linear in the unknowns: solve exactly
    lin = _linear_form(resid, syms) if not any(r.atoms(AppliedUndef) or r.has(sp.Integral) for r in resid) else None
    if lin is not None:
        a, b = lin
        env = {s: sp.Float(v, 20) for s, v in known.items()}
        try:
            an = np.array(a.subs(env).evalf(17).tolist(), dtype=float)
            bn = np.array(b.subs(env).evalf(17).tolist(), dtype=float).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise BlockError(f"cannot evaluate the linear system: {exc}") from None
        sing = np.linalg.svd(an, compute_uv=False)
        if sing.size == 0 or sing.min() <= 1e-12 * max(sing.max(), 1e-300):
            raise BlockError("the coupled linear equations are singular (dependent or contradictory) for these values; they do not determine a unique solution")
        x = np.linalg.solve(an, bn)
        vals = {s: float(v) for s, v in zip(syms, x)}
        exprs = None
        if m <= MAX_SYMBOLIC:
            try:
                sol = sp.linsolve((a, b), *syms)
                tup = next(iter(sol)) if sol else None
                if tup is not None and len(tup) == m:
                    exprs = {s: sp.together(e) for s, e in zip(syms, tup)}
                    check = {s: evaluate(e, known) for s, e in exprs.items()}
                    if any(abs(check[s] - vals[s]) > 1e-8 * max(abs(vals[s]), 1e-300) + 1e-14 for s in syms):
                        exprs = None
            except Exception:  # noqa: BLE001 - keep the numerical solution
                exprs = None
        return BlockResult(vals, "linear (exact)" if exprs else "linear (numerical)", exprs, {"unknowns": m, "condition": float(sing.max() / sing.min())})
    # ---- nonlinear: tear one unknown (the other equations then solve one after another) and find it by bracketing; Newton from many starting points as the fallback
    if isolate is not None:
        torn = _tear_block(block, known, calc, evaluate, isolate, search)
        if torn is not None:
            return torn
    return _newton_block(block, known, calc, evaluate, search)


def _compile(resid: list, syms: list, known: Mapping):
    ext = sorted({s for r in resid for s in r.free_symbols if s not in syms}, key=lambda s: s.name)
    plain = not any(r.atoms(AppliedUndef) or r.has(sp.Integral) for r in resid)
    if plain:
        try:
            f = fast_lambdify([*syms, *ext], resid)
            jac_expr = sp.Matrix(resid).jacobian(syms)
            j = fast_lambdify([*syms, *ext], jac_expr.tolist())
            args_ext = [float(known[s]) for s in ext]
            return (lambda x: np.array(f(*x, *args_ext), dtype=float)), (lambda x: np.array(j(*x, *args_ext), dtype=float))
        except Exception:  # noqa: BLE001 - a function that cannot be printed or differentiated: use the evaluating fallback
            pass
    return None, None


def _newton_block(block: Block, known: Mapping, calc, evaluate: Callable, search) -> BlockResult:
    syms, m = block.unknowns, len(block.unknowns)
    resid = [e.lhs - e.rhs for e in block.eqs]
    f, jac = _compile(resid, syms, known)
    if f is None:                                    # numerical nodes (ODE solutions, quadrature): evaluate through the engine, finite-difference Jacobian
        def f(x):                                    # noqa: F811
            env = {**known, **{s: float(v) for s, v in zip(syms, x)}}
            return np.array([evaluate(r, env) for r in resid], dtype=float)

        def jac(x):                                  # noqa: F811
            f0 = f(x)
            out = np.zeros((m, m))
            for k in range(m):
                h = 1.5e-8 * max(1.0, abs(x[k]))
                xp = np.array(x, dtype=float)
                xp[k] += h
                out[:, k] = (f(xp) - f0) / h
            return out
    dom = [_domain(calc, s, search) for s in syms]
    lhs_fns = None
    try:
        lf = fast_lambdify([*syms, *sorted({s for e in block.eqs for s in e.symbols if s not in syms}, key=lambda s: s.name)], [[e.lhs, e.rhs] for e in block.eqs])
        ext = sorted({s for e in block.eqs for s in e.symbols if s not in syms}, key=lambda s: s.name)
        ext_vals = [float(known[s]) for s in ext]
        lhs_fns = lambda x: np.array(lf(*x, *ext_vals), dtype=float)       # noqa: E731
    except (TypeError, ValueError, AttributeError):
        lhs_fns = None

    def scale_of(x: np.ndarray, fx: np.ndarray) -> np.ndarray:
        if lhs_fns is not None:
            try:
                return np.maximum(np.abs(lhs_fns(x)).max(axis=1), 1e-300)
            except (ValueError, TypeError, OverflowError, ZeroDivisionError):
                pass
        return np.maximum(np.abs(fx), 1.0)

    def inside(x: np.ndarray) -> bool:
        for v, (lo, hi) in zip(x, dom):
            if lo == 0.0:
                if not v > 0.0:
                    return False
            elif lo != -math.inf and v < lo:
                return False
            if hi != math.inf and v > hi:
                return False
        return True

    def run(x0: np.ndarray):
        x = x0.copy()
        try:
            fx = f(x)
        except (OverflowError, ValueError, ZeroDivisionError, ArithmeticError):
            return None
        if not np.all(np.isfinite(fx)):
            return None
        for it in range(1, MAX_ITER + 1):
            sc = scale_of(x, fx)
            if np.max(np.abs(fx) / sc) < 1e-12:
                for _ in range(3):                           # polish: Newton converges quadratically, so a few more steps reach full precision
                    try:
                        xn = x + np.linalg.solve(jac(x), -fx)
                        fn = f(xn)
                    except (np.linalg.LinAlgError, OverflowError, ValueError, ZeroDivisionError, ArithmeticError):
                        break
                    if not (inside(xn) and np.all(np.isfinite(fn)) and np.max(np.abs(fn) / scale_of(xn, fn)) <= np.max(np.abs(fx) / scale_of(x, fx))):
                        break
                    x, fx = xn, fn
                return x, it - 1, float(np.max(np.abs(fx) / scale_of(x, fx)))
            try:
                J = jac(x)
                dx = np.linalg.solve(J, -fx)
            except (np.linalg.LinAlgError, OverflowError, ValueError, ZeroDivisionError):
                try:
                    dx = np.linalg.lstsq(J, -fx, rcond=None)[0]
                except Exception:  # noqa: BLE001
                    return None
            if not np.all(np.isfinite(dx)):
                return None
            norm0 = float(np.max(np.abs(fx) / sc))
            lam = 1.0
            while True:
                xt = x + lam * dx
                if inside(xt):
                    try:
                        ft = f(xt)
                        if np.all(np.isfinite(ft)) and float(np.max(np.abs(ft) / scale_of(xt, ft))) < norm0 * (1 - 1e-4 * lam) + 1e-300:
                            break
                    except (OverflowError, ValueError, ZeroDivisionError, ArithmeticError):
                        pass
                lam /= 2
                if lam < 1e-5:
                    return None
            step = float(np.max(np.abs(xt - x) / np.maximum(np.abs(xt), 1e-300)))
            x, fx = xt, ft
            if step < 1e-13 and float(np.max(np.abs(fx) / scale_of(x, fx))) < 1e-8:
                return x, it, float(np.max(np.abs(fx) / scale_of(x, fx)))
        return None

    rng = random.Random(20240601)
    starts: list[np.ndarray] = []
    base = []
    for lo, hi in dom:
        if lo > 0 and math.isfinite(hi) and hi > lo:
            base.append(math.sqrt(lo * hi))
        elif math.isfinite(lo) and math.isfinite(hi):
            base.append((lo + hi) / 2 if hi > lo else 1.0)
        else:
            base.append(1.0)
    def clamp(v: float, lo: float, hi: float) -> float:
        if lo == 0.0:
            v = max(v, 1e-300)
        elif lo != -math.inf:
            v = max(v, lo)
        return min(v, hi) if hi != math.inf else v
    for k in (0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6):
        starts.append(np.array([clamp(b * 10.0 ** k * (1 + 0.37 * (i if k % 2 == 0 else m - 1 - i)), lo, hi) for i, (b, (lo, hi)) in enumerate(zip(base, dom))], dtype=float))   # staggered, so that symmetric systems are not singular at the start
    for _ in range(40):
        x0 = []
        for (lo, hi), b in zip(dom, base):
            a_lo = lo if lo > 0 else 1e-9
            a_hi = hi if math.isfinite(hi) else 1e9
            if lo == -math.inf or lo < 0:
                x0.append(rng.choice([-1, 1]) * 10 ** rng.uniform(-6, 6) if not (math.isfinite(lo) and math.isfinite(hi)) else rng.uniform(lo, hi))
            else:
                x0.append(math.exp(rng.uniform(math.log(a_lo), math.log(a_hi))) if a_hi > a_lo else a_lo)
        starts.append(np.array(x0, dtype=float))
    solutions: list[tuple[np.ndarray, int, float]] = []
    tried = 0
    first_found = None
    for k, x0 in enumerate(starts):
        tried += 1
        out = run(x0)
        if out is None:
            continue
        x, iters, res = out
        if not any(np.allclose(x, s[0], rtol=1e-6, atol=1e-300) for s in solutions):
            solutions.append((x, iters, res))
        if first_found is None and solutions:
            first_found = tried
        if len(solutions) >= 3 or (first_found is not None and tried >= first_found + 14):      # keep looking a little for a second solution, to be able to report it
            break
    if not solutions:
        raise BlockError("Newton's method found no solution of the coupled equations in the allowed ranges from any of the starting points tried; "
                         "check that the equations can be satisfied, or give search ranges (Advanced → search range) for the unknowns")
    x, iters, res = solutions[0]
    vals = {s: float(v) for s, v in zip(syms, x)}
    info = {"unknowns": m, "iterations": iters, "residual": res, "starts": tried, "solutions": [{s.name: float(v) for s, v in zip(syms, sx)} for sx, _i, _r in solutions]}
    return BlockResult(vals, "Newton", None, info)


# ---------------------------------------------------------------- tearing

def _sequence(eqs: list, known: set, isolate: Callable):
    """With the tear variable known, order the other equations so that each has one unknown. Returns (steps, residual equation) or None."""
    remaining = list(eqs)
    have = set(known)
    steps = []
    while True:
        zero = [e for e in remaining if not (e.symbols - have)]
        if len(zero) > 1:
            return None                                               # more equations than unknowns once the tear variable is known
        if len(zero) == 1 and len(remaining) == 1:
            return steps, zero[0]
        cands = [e for e in remaining if e not in zero and len(e.symbols - have) == 1]
        if not cands or len(remaining) == 1:
            return None

        def linear(e) -> bool:                                         # prefer an equation linear in its unknown: rearranging it has a single branch (no sign ambiguity of a root)
            (w,) = e.symbols - have
            try:
                return sp.diff(e.lhs - e.rhs, w, 2) == 0
            except Exception:  # noqa: BLE001
                return False
        one = sorted(cands, key=lambda e: not linear(e))[0]
        (u,) = one.symbols - have
        try:
            expr, _ = isolate(one, u)
        except Exception:  # noqa: BLE001 - cannot be isolated: this tear variable does not work
            return None
        steps.append((one, u, expr))
        have.add(u)
        remaining.remove(one)


def _tear_block(block: Block, known: Mapping, calc, evaluate: Callable, isolate: Callable, search) -> BlockResult | None:
    from .rootfind import brent, grid

    eqs, syms = block.eqs, block.unknowns
    uses = {s: sum(1 for e in eqs if s in e.symbols) for s in syms}
    for tear in sorted(syms, key=lambda s: (-uses[s], s.name)):
        plan = _sequence(eqs, set(known) | {tear}, isolate)
        if plan is None:
            continue
        steps, resid_eq = plan
        base = {s: float(v) for s, v in known.items()}
        compiled = []
        for _eq, u, expr in steps:
            args = sorted(expr.free_symbols, key=lambda a: a.name)
            plain = not (expr.atoms(AppliedUndef) or expr.has(sp.Integral))
            fn = None
            if plain:
                try:
                    fn = fast_lambdify(args, expr, runtime_functions=True)
                except Exception:  # noqa: BLE001
                    fn = None
            compiled.append((u, expr, args, fn))
        rexpr = resid_eq.lhs - resid_eq.rhs
        rargs = sorted(rexpr.free_symbols, key=lambda a: a.name)
        rfn = None
        if not (rexpr.atoms(AppliedUndef) or rexpr.has(sp.Integral)):
            try:
                rfn = fast_lambdify(rargs, rexpr, runtime_functions=True)
            except Exception:  # noqa: BLE001
                rfn = None
        count = [0]

        def chain(tv: float) -> dict | None:
            env = dict(base)
            env[tear] = tv
            try:
                for u, expr, args, fn in compiled:
                    val = fn(*[env[a] for a in args]) if fn is not None else evaluate(expr, env)
                    if isinstance(val, complex) or not math.isfinite(val):
                        return None
                    env[u] = float(val)
            except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError, TypeError):
                return None
            return env

        def g(tv: float) -> float:
            count[0] += 1
            env = chain(tv)
            if env is None:
                return math.nan
            try:
                val = rfn(*[env[a] for a in rargs]) if rfn is not None else evaluate(rexpr, env)
            except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError, TypeError):
                return math.nan
            return float(val) if not isinstance(val, complex) and math.isfinite(val) else math.nan

        lo, hi = _domain(calc, tear, search)
        a_lo = lo if lo > 0 else 1e-9
        a_hi = hi if math.isfinite(hi) else 1e9
        scans = [grid(a_lo, a_hi, 121)] if a_hi > a_lo else [[a_lo]]
        if lo < 0 or lo == -math.inf:
            neg_hi = -lo if math.isfinite(lo) else 1e9
            scans.append([-x for x in grid(1e-9, neg_hi, 121)])
        doms = {u: _domain(calc, u, search) for u, *_ in compiled}

        def acceptable(env: dict) -> bool:
            for u, (l_, h_) in doms.items():
                v = env[u]
                if (l_ == 0.0 and not v > 0.0) or (l_ not in (0.0, -math.inf) and v < l_) or (h_ != math.inf and v > h_):
                    return False
            return True

        roots: list[tuple[float, dict]] = []
        for xs in scans:
            prev = None
            for x in xs:
                gx = g(x)
                if math.isnan(gx):
                    prev = None
                    continue
                if gx == 0.0:
                    env = chain(x)
                    if env is not None and acceptable(env):
                        roots.append((x, env))
                elif prev is not None and prev[1] * gx < 0:
                    a, fa = prev
                    r = brent(g, a, x, fa, gx, xtol=1e-15 * max(abs(a), abs(x), 1e-300))
                    env = chain(r.x)
                    if env is not None:
                        scale = max(abs(float(evaluate(resid_eq.lhs, env))), abs(float(evaluate(resid_eq.rhs, env))), 1e-300)
                        if abs(r.residual) / scale < 1e-6 and acceptable(env) and not any(abs(r.x - q[0]) <= 1e-9 * abs(r.x) for q in roots):
                            roots.append((r.x, env))
                prev = (x, gx)
                if len(roots) >= 6:
                    break
        if not roots:
            continue
        env = roots[0][1]
        vals = {s: float(env[s]) for s in syms}
        sols = [{s.name: float(e[s]) for s in syms} for _x, e in roots]
        return BlockResult(vals, "tearing", None, {"unknowns": len(syms), "tear": tear.name, "evaluations": count[0], "solutions": sols, "residual": 0.0})
    return None
