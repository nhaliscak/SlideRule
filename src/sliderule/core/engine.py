"""Solve a :class:`Calculation` and narrate the solution (symbolic and numeric, with units).

Strategy
--------
1. Validate inputs and convert everything to coherent SI (the *standardization* step).
2. Decide which equation determines which unknown by repeatedly picking an equation that has
   exactly one unknown left ("causal ordering", the same trick Modelica/bond-graph tools use
   to turn acausal equations into an executable sequence). This handles both explicit chains
   (Re -> f -> head loss) and rearrangement (solve the stress equation for area instead).
3. Isolate each unknown symbolically with sympy, evaluate numerically, and convert results to
   the requested output units.
4. Record every stage as steps in two parallel narratives: symbolic and numeric.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import sympy as sp
from sympy.core.function import AppliedUndef

from ..units import Unit, UnitError, default_registry
from .special import fast_lambdify
from .calculus import plain_integrals
from . import series, simul
from .rootfind import NoBracket, brackets, brent, grid
from .dimcheck import DimensionError, analyze
from .model import Calculation, Equation, Variable, log2, log10
from .units_expr import (
    base_expr_of, expr_tex, fmt_number, quantity_tex, unit_expr_of, unit_tex,
)

_QTY = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*?)\s*$")


def parse_quantity(text: str) -> tuple[float, str]:
    """Parse ``'250 kN'`` into ``(250.0, 'kN')``."""
    m = _QTY.match(text)
    if not m:
        raise UnitError(f"cannot read a number from {text!r}", "BAD_NUMBER")
    return float(m.group(1)), m.group(2)


# ---------------------------------------------------------------- result types

@dataclass
class Diagnostic:
    level: str       # "error" | "warning" | "info"
    code: str
    message: str
    variable: str | None = None

    def to_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message, "variable": self.variable}


@dataclass
class Line:
    latex: str
    note: str = ""


@dataclass
class Step:
    title: str
    lines: list[Line] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"title": self.title, "lines": [{"latex": l.latex, "note": l.note} for l in self.lines]}


@dataclass
class Solution:
    calc_id: str
    ok: bool
    outputs: list[dict] = field(default_factory=list)
    intermediates: list[dict] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    steps: dict[str, list[Step]] = field(default_factory=lambda: {"symbolic": [], "numeric": []})
    series: list[dict] = field(default_factory=list)      # differential equations: the solution over time, for plotting
    table: list[dict] = field(default_factory=list)       # ... and its values at the requested times

    def to_dict(self) -> dict:
        return {
            "calc_id": self.calc_id,
            "ok": self.ok,
            "series": self.series,
            "table": self.table,
            "outputs": self.outputs,
            "intermediates": self.intermediates,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "steps": {k: [s.to_dict() for s in v] for k, v in self.steps.items()},
        }


@dataclass
class _Given:
    var: Variable
    value: float
    unit_text: str
    unit: Unit
    si: float


@dataclass
class _Solved:
    eq: Equation
    sym: sp.Symbol
    expr: sp.Expr            # sym = expr (isolated)
    rearranged: bool
    si: float = math.nan
    numeric_ode: bool = False     # evaluated by numerical integration although the equation has a closed form (the formula was singular here)
    inverse: Any = None           # (value, info) when the unknown was found by numerical root-finding instead of rearranging the equation
    block: Any = None             # a _BlockInfo when the unknown was found together with others (coupled equations)


@dataclass
class _BlockInfo:
    block: Any
    result: Any


def _block_node(calc: Calculation, block, s: sp.Symbol):
    """A placeholder ``solve_s(known quantities)`` for an unknown found by solving coupled equations numerically: it carries the unknown's dimension
    for unit lines and dependency tracking."""
    v = calc.by_key[s.name]
    others = list(block.external)
    latex_name = v.latex or v.key

    def _latex(self, printer, *a, **k):
        inner = ", ".join(printer._print(x) for x in self.args)
        return rf"\mathrm{{solve}}_{{{latex_name}}}\left({inner}\right)"

    cls = type(f"BLOCK_{s.name}", (sp.Function,), {"_latex": _latex, "_sliderule_result": (v.dim, unit_expr_of(v.si_parsed)), "nargs": len(others)})
    return cls(*others) if others else cls()


def _solve_coupled(calc: Calculation, remaining: list, known: dict, solved: list, targets: list, search_si: dict, diag: list):
    """Solve one needed, ready block of coupled equations. Returns "none" (nothing to do), "solved" or "error" (a diagnostic was added)."""
    kset = set(known)
    target_syms = {calc.by_key[t].symbol for t in targets if calc.by_key[t].symbol not in known}
    if not target_syms:
        return "none"
    blocks = simul.find_blocks(remaining, kset)
    need = simul.needed_unknowns(remaining, kset, target_syms)
    for block in blocks:
        if not set(block.unknowns) & need or not simul.is_ready(block, kset):
            continue
        names = ", ".join(u.name for u in block.unknowns)
        try:
            result = simul.solve_block(block, known, calc, _evaluate, search_si, _isolate)
        except simul.BlockError as exc:
            diag.append(Diagnostic("error", "COUPLED_FAILED", f"the coupled equations for {names} could not be solved: {exc}", block.unknowns[0].name))
            return "error"
        except ArithmeticError as exc:
            diag.append(Diagnostic("error", "COUPLED_FAILED", f"the coupled equations for {names} could not be evaluated: {exc}", block.unknowns[0].name))
            return "error"
        info = _BlockInfo(block, result)
        for eq, sym in zip(block.eqs, block.unknowns):
            expr = result.exprs[sym] if result.exprs else _block_node(calc, block, sym)
            item = _Solved(eq, sym, expr, True, result.values[sym])
            item.block = info
            known[sym] = item.si
            solved.append(item)
            remaining.remove(eq)
        if result.method == "tearing":
            how = f"by tearing: {result.info['tear']} was found by root-finding, the other equations then follow one after another ({result.info['evaluations']} evaluations)"
        elif result.method == "Newton":
            how = f"Newton's method ({result.info['iterations']} iterations from start {result.info['starts']}, residual {result.info['residual']:.1e})"
        else:
            how = "as a linear system, " + ("exactly" if result.method == "linear (exact)" else "numerically")
        diag.append(Diagnostic("info", "COUPLED_SYSTEM", f"{len(block.unknowns)} coupled equations were solved simultaneously for {names}: {how}.", block.unknowns[0].name))
        sols = result.info.get("solutions") or []
        if len(sols) > 1:
            diag.append(Diagnostic("warning", "MULTIPLE_SOLUTIONS", f"the coupled equations for {names} have more than one solution in the allowed ranges; the first found was used "
                                   f"({'; '.join(', '.join(f'{k} = {v:.6g}' for k, v in sol.items()) for sol in sols[:3])} in SI). Give search ranges for the unknowns to choose.", block.unknowns[0].name))
        return "solved"
    return "none"


# ---------------------------------------------------------------- helpers

def _norm_inputs(inputs: Mapping[str, Any]) -> dict[str, tuple[float, str]]:
    out: dict[str, tuple[float, str]] = {}
    for k, v in inputs.items():
        if isinstance(v, str):
            out[k] = parse_quantity(v)
        elif isinstance(v, Mapping):
            out[k] = (float(v["value"]), str(v.get("unit", "")))
        else:
            val, unit = v
            out[k] = (float(val), str(unit))
    return out


def _combine_logs(expr: sp.Expr) -> sp.Expr:
    """Merge ``c*log(a) - c*log(b)`` into ``c*log(a/b)`` (valid for positive symbols). Unlike ``logcombine`` it leaves ``log(a)/k`` alone."""
    def merge(add: sp.Add):
        groups: dict = {}
        rest = []
        for term in add.args:
            coeff, factor = term.as_independent(sp.log, as_Add=False)
            if not isinstance(factor, sp.log):
                rest.append(term)
                continue
            sign = -1 if coeff.could_extract_minus_sign() else 1
            groups.setdefault(sign * coeff, []).append((sign, factor.args[0]))
        if not any(len(v) > 1 for v in groups.values()):
            return add
        out = list(rest)
        for coeff, items in groups.items():
            if len(items) == 1:
                out.append(items[0][0] * coeff * sp.log(items[0][1]))
            else:
                out.append(coeff * sp.log(sp.Mul(*[a ** s for s, a in items])))
        return sp.Add(*out)
    return expr.replace(lambda e: isinstance(e, sp.Add), merge)


class InversionError(ValueError):
    pass


def _inverse_node(calc: Calculation, eq: Equation, s: sp.Symbol):
    """A placeholder ``root_s(other quantities)`` standing for a numerically inverted unknown: it carries the unknown's dimension so the unit
    lines and dependency tracking work, and prints as such in the steps."""
    v = calc.by_key[s.name]
    others = sorted(eq.symbols - {s}, key=lambda x: x.name)
    latex_name = v.latex or v.key

    def _latex(self, printer, *a, **k):
        inner = ", ".join(printer._print(x) for x in self.args)
        return rf"\mathrm{{root}}_{{{latex_name}}}\left({inner}\right)"

    cls = type(f"NUMINV_{s.name}", (sp.Function,), {"_latex": _latex, "_sliderule_result": (v.dim, unit_expr_of(v.si_parsed)), "nargs": len(others)})
    return cls(*others)


#: the automatic scan for a numerical inversion: first a quick pass over a plain range, then, if that finds nothing, a wide and finer one
_QUICK = (1e-9, 1e9, 73)
_WIDE = (1e-40, 1e40, 321)
_WIDE_SECONDS = 4.0              # the wide pass stops after this long (a slow equation, for example a numerically integrated field, is not scanned for ever)


def _invert_numeric(calc: Calculation, eq: Equation, s: sp.Symbol, known: dict, search: tuple[float, float] | None) -> tuple[float, dict]:
    """Find the value of ``s`` (SI) that satisfies ``eq`` given the other quantities, by bracketing and Brent's method.

    Without a search range the variable's own limits (or 1e-9 to 1e9) are scanned; if no sign change is found there the scan is repeated over a much wider
    range (atomic lengths, astronomical masses). A sign change that turns out to be a pole or a jump is skipped and the scan goes on; the first genuine root
    from the small end is returned."""
    v = calc.by_key[s.name]
    expr = eq.lhs - eq.rhs

    seen: list[tuple[float, float]] = []             # every finite value tried, for the touching-root fallback below

    def f(x: float) -> float:
        y = _evaluate(expr, {**known, s: x})
        if len(seen) < 6000 and math.isfinite(y):
            seen.append((x, y))
        return y

    def scans_for(lo: float, hi: float, points: int) -> list[list[float]]:
        out = [grid(lo, hi, points)]
        if v.signed:
            out.append([-x for x in grid(lo, hi, points)])
        return out

    if search is not None:
        lo, hi = search
        stages = [(lo, hi, [grid(lo, hi, 61)], "in the search range you gave")]
    else:
        lo = v.to_si(v.min) if v.min is not None and v.to_si(v.min) > 0 else _QUICK[0]
        hi = v.to_si(v.max) if v.max is not None else _QUICK[1]
        stages = [(lo, hi, scans_for(lo, hi, _QUICK[2]), "by scanning automatically")]
        wlo = v.to_si(v.min) if v.min is not None and v.to_si(v.min) > 0 else _WIDE[0]
        whi = v.to_si(v.max) if v.max is not None else _WIDE[1]
        if (wlo, whi) != (lo, hi):
            stages.append((wlo, whi, scans_for(wlo, whi, _WIDE[2]), "by scanning automatically over a wide range"))
    evaluations = 0
    pole = None
    started = time.monotonic()
    for stage, (lo, hi, scans, how) in enumerate(stages):
        for xs in scans:
            try:
                for a, b, fa, fb, n in brackets(f, xs):
                    if stage and time.monotonic() - started > _WIDE_SECONDS:
                        raise NoBracket("out of time")
                    root = brent(f, a, b, fa, fb, xtol=1e-15 * max(abs(a), abs(b), 1e-300))
                    scale = max(abs(_evaluate(eq.lhs, {**known, s: root.x})), abs(_evaluate(eq.rhs, {**known, s: root.x})), 1e-300)
                    if abs(root.residual) / scale > 1e-6:
                        pole = pole if pole is not None else root.x          # a pole or a jump, not a root: look further along
                        continue
                    return root.x, {"bracket": (a, b), "evaluations": evaluations + n + root.evaluations, "residual": root.residual, "scale": scale, "how": how,
                                    "range": (lo, hi), "auto": search is None}
            except NoBracket:
                pass
            evaluations += len(xs)
    hidden = _hidden_root(f, seen, eq, s, known)
    if hidden is not None:
        x, residual, scale, cell = hidden
        return x, {"bracket": cell, "evaluations": evaluations, "residual": residual, "scale": scale, "range": (min(p[0] for p in seen), max(p[0] for p in seen)),
                   "how": "by scanning automatically, then looking inside the interval where the equation comes closest to zero (two roots lay close together)", "auto": search is None}
    touching = _touching_root(f, seen, eq, s, known)
    if touching is not None:
        x, residual, scale = touching
        return x, {"bracket": (x, x), "evaluations": evaluations, "residual": residual, "scale": scale, "range": (seen[0][0], seen[-1][0]) if seen else (0.0, 0.0),
                   "how": "by scanning automatically; the equation only touches zero here (a double root: an extremum such as a peak or a minimum), so there is no sign change",
                   "auto": search is None}
    if pole is not None:
        raise InversionError(f"the equation changes sign near {pole:g} (SI) without a root there (a discontinuity)")
    where = f"between {v.parsed.from_si(lo):g} and {v.parsed.from_si(hi):g} {v.parsed.symbol}" if search is not None else "in the automatic range"
    near = ""
    if seen:                                    # the closest the equation comes to zero: a peak or a minimum that the given value just misses (typed rounded, say)
        xb, yb = min(seen, key=lambda p: abs(p[1]))
        try:
            sc_ = max(abs(_evaluate(eq.lhs, {**known, s: xb})), abs(_evaluate(eq.rhs, {**known, s: xb})), 1e-300)
            gap = abs(yb) / sc_
            if gap < 0.05 and xb not in (min(p[0] for p in seen), max(p[0] for p in seen)):
                near = (f". The equation comes closest to zero (a relative gap of {gap:.2g}) near {s.name} = {v.parsed.from_si(xb):.6g} {v.parsed.symbol}: if the value you "
                        "gave is a peak or a minimum of the formula it may just miss it, for example when it was typed rounded")
        except (ArithmeticError, ValueError, OverflowError):
            pass
    raise InversionError(f"no value of {s.name} {where} satisfies the equation (no sign change found){near}"
                         + ("; give a search range for it (Advanced → search range, or `search` in the API) that contains the answer" if search is None else ""))


def _hidden_root(f, seen: list[tuple[float, float]], eq: Equation, s: sp.Symbol, known: dict):
    """Two roots closer together than the scan's spacing leave the same sign at both grid points of the interval that holds them. For the intervals where
    |f| is smallest, find the extreme value of f inside (a minimum if f > 0, a maximum if f < 0): if it has the other sign there is a root between the grid
    point and the extremum, found by Brent's method."""
    if len(seen) < 5:
        return None
    from scipy.optimize import minimize_scalar

    pts = sorted(seen)
    cells = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        if x1 > x0 and (y0 < 0) == (y1 < 0):
            cells.append((min(abs(y0), abs(y1)), x0, y0, x1, y1))
    cells.sort(key=lambda c: c[0])
    for _, x0, y0, x1, y1 in cells[:8]:
        sign = 1.0 if y0 > 0 else -1.0
        try:
            res = minimize_scalar(lambda x, sg=sign: sg * f(x), bounds=(x0, x1), method="bounded", options={"xatol": 1e-13 * max(abs(x1), 1e-300), "maxiter": 120})
            xe, ye = float(res.x), f(float(res.x))
            if (ye > 0) == (y0 > 0):
                continue
            root = brent(f, x0, xe, y0, ye, xtol=1e-15 * max(abs(x0), abs(xe), 1e-300))
            scale = max(abs(_evaluate(eq.lhs, {**known, s: root.x})), abs(_evaluate(eq.rhs, {**known, s: root.x})), 1e-300)
        except (ArithmeticError, ValueError, OverflowError, NoBracket):
            continue
        if abs(root.residual) / scale <= 1e-6:
            return root.x, root.residual, scale, (x0, xe)
    return None


def _touching_root(f, seen: list[tuple[float, float]], eq: Equation, s: sp.Symbol, known: dict) -> tuple[float, float, float] | None:
    """A value where f reaches zero without changing sign (a double root, the top of a peak): the smallest |f| tried is refined by a bounded minimisation
    of |f| between its neighbours and accepted only if it is zero to 1e-9 of the size of the two sides of the equation."""
    if len(seen) < 5:
        return None
    from scipy.optimize import minimize_scalar

    pts = sorted(seen)
    xs = [p[0] for p in pts]
    i = min(range(len(pts)), key=lambda k: abs(pts[k][1]))
    lo, hi = xs[max(i - 1, 0)], xs[min(i + 1, len(xs) - 1)]
    if not lo < hi:
        return None
    try:
        res = minimize_scalar(lambda x: abs(f(x)), bounds=(lo, hi), method="bounded", options={"xatol": 1e-14 * max(abs(hi), 1e-300), "maxiter": 200})
        x = float(res.x)
        scale = max(abs(_evaluate(eq.lhs, {**known, s: x})), abs(_evaluate(eq.rhs, {**known, s: x})), 1e-300)
        residual = _evaluate(eq.lhs - eq.rhs, {**known, s: x})
    except (ArithmeticError, ValueError, OverflowError):
        return None
    return (x, residual, scale) if abs(residual) / scale <= 1e-9 else None


def _isolate(eq: Equation, sym: sp.Symbol) -> tuple[sp.Expr, bool]:
    if eq.ode is not None and eq.ode.numeric and sym != eq.lhs:
        raise ValueError(f"the differential equation has no closed-form solution (it is integrated numerically), so {sym.name} cannot be isolated by rearranging; "
                         f"it is found by numerical root-finding instead")
    if eq.numeric_integral and any(sym in i.free_symbols for i in (eq.lhs.atoms(sp.Integral) | eq.rhs.atoms(sp.Integral))):
        raise ValueError(f"{sym} appears inside an integral that has no closed form, which is evaluated numerically and cannot be rearranged; "
                         "solve for a quantity outside the integral")
    if eq.numeric_integral and any(sym in i.free_symbols for i in (eq.lhs.atoms(sp.Sum) | eq.rhs.atoms(sp.Sum))):
        raise ValueError(f"{sym} appears inside a sum, which is evaluated term by term and cannot be rearranged; it is found by numerical root-finding instead")
    if eq.lhs == sym and sym not in eq.rhs.free_symbols:
        return eq.rhs, False
    if eq.rhs == sym and sym not in eq.lhs.free_symbols:
        return eq.lhs, True
    relation = sp.Eq(eq.lhs, eq.rhs)
    poly = sp.Poly(sp.expand(eq.lhs - eq.rhs), sym) if (eq.lhs - eq.rhs).is_polynomial(sym) else None
    if poly is not None and poly.degree() >= 3:
        # a cubic or higher polynomial has several roots and SymPy's list of them says nothing about which one lies in the variable's allowed range:
        # the numerical inversion (bounds-aware, bracketed) picks the physical one
        raise ValueError(f"{sym} is a root of a polynomial of degree {poly.degree()}: it is found numerically, within its allowed range")
    for t in relation.atoms(sp.exp, sp.log):
        # the unknown as a cubic or higher polynomial inside an exp or log (the PPD of a comfort model): SymPy's attempt can spend minutes in a single
        # arithmetic operation that nothing can interrupt, and the answer is a numerical one anyway
        arg = t.args[0]
        if sym in arg.free_symbols and arg.is_polynomial(sym) and sp.degree(arg, sym) >= 3:
            raise ValueError(f"{sym} appears as a polynomial of degree {sp.degree(arg, sym)} inside {t.func.__name__}: it is found numerically, within its allowed range")
    logs = relation.atoms(log10, log2)
    if logs and sym in relation.free_symbols and not relation.xreplace({x: sp.Dummy() for x in logs}).has(sym):
        # the unknown only occurs inside logarithms of a fixed base (a level in dB, say): SymPy knows natural logarithms, so rewrite them for it
        # (when the unknown also appears outside, as in Colebrook, SymPy cannot finish and the numerical inversion takes over)
        relation = relation.xreplace({x: sp.log(x.args[0]) / sp.log(10 if isinstance(x, log10) else 2) for x in logs})
    sols = sp.solve(relation, sym)
    sols = [s for s in sols if not s.has(sp.I)]
    if not sols:
        raise ValueError(f"no real solution for {sym} in {eq.text}")
    # log(b**e) -> e*log(b) (valid for positive symbols): SymPy's form can carry a dimensional exponent, e.g. log((V/(R*i))**(R*C)) for t,
    # which the unit check would reject although e*log(b) is perfectly consistent
    sol = sols[0].replace(lambda x: isinstance(x, sp.log) and isinstance(x.args[0], sp.Pow), lambda x: x.args[0].exp * sp.log(x.args[0].base))
    if sol.has(sp.log):          # log(a) - log(b) -> log(a/b): a ratio of two like quantities is dimensionless even though a and b are not
        sol = _combine_logs(sol)
    return plain_integrals(sol) if sol.has(sp.Integral) else sol, True


_SUM_FUNCS: dict = {}


def _evaluate_sum(expr: sp.Expr, values: dict[sp.Symbol, float]):
    """Fast path for an expression containing sums: compile to a Python loop (``math``); None where that cannot be used (overflow, special cases)."""
    if expr.has(sp.Integral) or expr.atoms(AppliedUndef):
        return None
    try:
        syms = sorted(expr.free_symbols, key=lambda s: s.name)
        fn = _SUM_FUNCS.get((expr, tuple(syms)))
        if fn is None:
            if len(_SUM_FUNCS) > 64:
                _SUM_FUNCS.clear()
            fn = _SUM_FUNCS[(expr, tuple(syms))] = fast_lambdify(syms, expr)
        out = fn(*[values[s] for s in syms])
        return float(out) if isinstance(out, (int, float)) and math.isfinite(out) else None
    except (OverflowError, ValueError, ZeroDivisionError, TypeError, KeyError, NameError):
        return None


def _evaluate(expr: sp.Expr, values: dict[sp.Symbol, float]) -> float:
    try:
        return _evaluate_value(expr, values)
    except (RuntimeError, np.linalg.LinAlgError) as exc:      # a numerical solver inside the expression (a PDE, an ODE) gave up at these values, e.g. a singular matrix
        raise ArithmeticError(f"a numerical solver failed at these values ({exc})") from None


def _evaluate_value(expr: sp.Expr, values: dict[sp.Symbol, float]) -> float:
    if expr.has(sp.Sum):
        infinite = series.infinite_sums(expr)
        if infinite:                      # an infinite series is summed (and checked for convergence) first; the rest is evaluated as usual
            expr = expr.xreplace({t: sp.Float(series.evaluate(t, values), 17) for t in infinite})
    if expr.has(sp.Sum):
        fast = _evaluate_sum(expr, values)
        if fast is not None:
            return fast
    val = expr.subs({s: sp.Float(v, 20) for s, v in values.items()})
    val = sp.N(val, 17)
    if val.has(sp.erfinv, sp.erfcinv):              # SymPy leaves these inverse error functions unevaluated for a float argument: SciPy has them
        from scipy import special as _special

        val = sp.N(val.replace(lambda e: isinstance(e, (sp.erfinv, sp.erfcinv)) and e.args[0].is_number,
                               lambda e: sp.Float((_special.erfinv if isinstance(e, sp.erfinv) else _special.erfcinv)(float(e.args[0])), 17)), 17)
    if val.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
        raise ArithmeticError("division by zero or undefined result")
    if not val.is_real and val.is_number:   # complex arithmetic inside closed forms (e.g. sqrt of a negative) can leave a rounding-sized imaginary part
        re, im = val.as_real_imag()
        if abs(im) <= 1e-9 * max(abs(re), 1e-300):
            val = re
    if not val.is_real:
        raise ArithmeticError("no real-valued result (e.g. square root or logarithm of a negative number)")
    out = float(val)
    if not math.isfinite(out):
        raise ArithmeticError("result is not finite")
    return out


def _tex(expr: sp.Expr, names: dict, **kw) -> str:
    return sp.latex(expr, symbol_names=names, **kw)


class _Ctx:
    """Everything the step writers need."""

    def __init__(self, calc: Calculation, sig: int):
        self.calc, self.sig = calc, sig
        self.names = calc.latex_names()
        self.env = {v.symbol: (v.dim, unit_expr_of(v.si_parsed)) for v in calc.variables}

    def sym(self, s: sp.Symbol) -> str:
        return self.names[s]

    values: dict = {}                # SI values of the known quantities, set once the solution is complete (see ``solve``)

    def unit_line(self, rhs: sp.Expr, var: Variable) -> str:
        """The unit reduction of a right-hand side down to the variable's SI unit. A symbolic exponent (the 1/n of a Freundlich isotherm, a Weibull m)
        has no unit of its own, so it is replaced by its given value for the check; if the units still cannot be tracked through the rearranged form,
        the line says so and shows the unit the result is known to have (the numbers themselves are converted to SI and checked separately)."""
        try:
            _, uexpr = analyze(rhs, self.env)
        except DimensionError:
            sub = {s: sp.nsimplify(v, rational=True, tolerance=1e-12) for s, v in self.values.items() if s in rhs.free_symbols and self.env[s][0].is_dimensionless}
            uexpr = None
            if sub:
                try:
                    _, uexpr = analyze(rhs.xreplace(sub), self.env)
                except DimensionError:
                    uexpr = None
            if uexpr is None:
                return rf"{expr_tex(unit_expr_of(var.si_parsed))}\ \text{{(expected; not reduced symbolically for this rearrangement)}}"
        chain = [expr_tex(uexpr)]
        base = base_expr_of(var.dim)
        for e in (base, unit_expr_of(var.si_parsed)):
            t = expr_tex(e)
            if t not in chain:
                chain.append(t)
        return " = ".join(chain)


def _conversion_factor_tex(unit: Unit, si_unit_tex: str, sig: int) -> str:
    _, f = fmt_number(unit.factor, sig + 1)
    return rf"\frac{{{f}\,{si_unit_tex}}}{{1\,{unit_tex(unit)}}}"


# ---------------------------------------------------------------- main entry point

def solve(
    calc: Calculation,
    inputs: Mapping[str, Any],
    solve_for: list[str] | None = None,
    output_units: Mapping[str, str] | None = None,
    sig_figs: int = 5,
    ode_times: Sequence[Any] | None = None,
    search: Mapping[str, Sequence[Any]] | None = None,
) -> Solution:
    reg = default_registry()
    sol = Solution(calc.id, ok=False)
    diag = sol.diagnostics
    output_units = dict(output_units or {})
    sig = max(2, min(int(sig_figs), 12))

    def err(code: str, msg: str, var: str | None = None) -> None:
        diag.append(Diagnostic("error", code, msg, var))

    def hint_validity() -> None:
        """A result that cannot be computed (the root of a negative number ...) is often a stated limit of the calculation: say which one the inputs break."""
        for cond, message in calc.parsed_validity:
            if cond.free_symbols <= known.keys():
                try:
                    holds = bool(cond.subs({sy: sp.Float(x, 20) for sy, x in known.items()}))
                except TypeError:
                    continue
                if not holds:
                    diag.append(Diagnostic("info", "VALIDITY", f"{message} (violated: {cond})"))

    # ---- 1. inputs -> SI -------------------------------------------------------------
    try:
        raw = _norm_inputs(inputs)
    except (UnitError, KeyError, TypeError, ValueError) as exc:
        err("BAD_INPUT", f"could not read inputs: {exc}")
        return sol

    givens: dict[str, _Given] = {}
    for key, (val, unit_text) in raw.items():
        v = calc.by_key.get(key)
        if v is None:
            err("UNKNOWN_VARIABLE", f"{calc.id} has no variable {key!r}", key)
            continue
        if v.is_constant:
            err("CONSTANT_OVERRIDE", f"{key} is a fixed constant and cannot be an input", key)
            continue
        if not math.isfinite(val):
            err("BAD_NUMBER", f"{v.label}: value must be a finite number", key)
            continue
        if v.units and (unit_text or v.unit).strip() not in v.units:
            err("UNIT_NOT_ALLOWED", f"{v.label} ({key}) must be given in {', '.join(v.units)}", key)
            continue
        try:
            unit = reg.parse(unit_text or v.unit, as_delta=v.delta)
        except UnitError as exc:
            err(exc.code, f"{v.label} ({key}): {exc}", key)
            continue
        if unit.dim != v.dim:
            err("DIM_MISMATCH",
                f"{v.label} ({key}) expects {reg.describe(v.dim)} (e.g. {v.si}), but "
                f"'{unit.symbol}' is {reg.describe(unit.dim)}", key)
            continue
        si = unit.to_si(val)
        if not v.signed and si < 0:
            err("NEGATIVE_VALUE", f"{v.label} ({key}) cannot be negative (got {val:g} {unit.symbol})", key)
            continue
        for bound, test, word in ((v.min, lambda a, b: a < b, "below its minimum"),
                                  (v.max, lambda a, b: a > b, "above its maximum")):
            if bound is not None and test(si, v.to_si(bound)):
                err("OUT_OF_RANGE", f"{v.label} ({key}) = {val:g} {unit.symbol} is {word} "
                    f"of {bound:g} {v.unit}", key)
        givens[key] = _Given(v, val, unit_text or v.unit, unit, si)
    if diag:
        return sol

    # ---- 2. what are we solving for? --------------------------------------------------
    if solve_for:
        targets = list(dict.fromkeys(solve_for))
        for t in targets:
            if t not in calc.by_key or calc.by_key[t].is_constant:
                err("UNKNOWN_VARIABLE", f"cannot solve for {t!r}", t)
            elif t in givens:
                err("TARGET_GIVEN", f"{t} was supplied as an input; leave it blank to solve for it", t)
    else:
        targets = [o for o in calc.outputs if o not in givens]
        if not targets:
            err("NOTHING_TO_SOLVE", "every default output was supplied; leave one blank or choose what to solve for")
    if diag:
        return sol

    search_si: dict[str, tuple[float, float]] = {}
    for key, pair in (search or {}).items():
        v = calc.by_key.get(key)
        try:
            if v is None or v.is_constant or not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("a search range is two values [from, to] for one of the variables")
            ends = []
            for item in pair:
                val, unit_text = parse_quantity(item) if isinstance(item, str) else (float(item), "")
                unit = reg.parse(unit_text or v.unit, as_delta=v.delta)
                if unit.dim != v.dim:
                    raise ValueError(f"'{unit.symbol}' is {reg.describe(unit.dim)}, but {key} is {reg.describe(v.dim)}")
                ends.append(unit.to_si(val))
            if not ends[0] < ends[1]:
                raise ValueError("the search range must increase")
            search_si[key] = (ends[0], ends[1])
        except (ValueError, TypeError, UnitError) as exc:
            err("BAD_SEARCH", f"search range for {key}: {exc}", key)
    if diag:
        return sol
    consts = {v.key: v for v in calc.constants}
    known: dict[sp.Symbol, float] = {g.var.symbol: g.si for g in givens.values()}
    known.update({v.symbol: v.to_si(v.constant) for v in consts.values()})  # type: ignore[arg-type]

    # ---- 3. causal ordering + isolate + evaluate -------------------------------------
    remaining = list(calc.parsed)
    solved: list[_Solved] = []
    checks: list[Equation] = []
    second_chance: set[int] = set()       # equations for which numerical root-finding may be tried although they were not asked for directly
    while True:
        progress = True
        while progress and remaining:
            progress = False
            for eq in remaining:
                unknown = eq.symbols - known.keys()
                if len(unknown) == 1:
                    (s,) = unknown
                    inverse = None
                    try:
                        expr, rearranged = _isolate(eq, s)
                    except Exception as exc:  # sympy cannot invert this equation for s: look for the value numerically instead
                        if s.name not in targets and id(eq) not in second_chance:
                            continue
                        try:
                            inverse = _invert_numeric(calc, eq, s, known, search_si.get(s.name))
                        except InversionError as inv_exc:
                            err("CANNOT_ISOLATE", f"cannot rearrange '{eq.text}' for {s.name}: {exc}. Looking for the value numerically also failed: {inv_exc}", s.name)
                            return sol
                        except ArithmeticError as inv_exc:
                            err("EVAL_ERROR", f"{eq.title}: cannot evaluate {s.name} numerically: {inv_exc}", s.name)
                            return sol
                        expr, rearranged = _inverse_node(calc, eq, s), True
                    item = _Solved(eq, s, expr, rearranged)
                    if inverse is not None:
                        item.si, item.inverse = inverse[0], inverse
                        info = inverse[1]
                        diag.append(Diagnostic("info", "NUMERIC_INVERSION",
                                               f"{calc.by_key[s.name].label} ({s.name}) was found numerically (no closed-form rearrangement of '{eq.text}' exists or it was not "
                                               f"attempted): root-finding {info['how']}, {info['evaluations']} evaluations, bracket [{info['bracket'][0]:.6g}, {info['bracket'][1]:.6g}] (SI). "
                                               + ("If you expected a different solution, give a search range." if info["auto"] else ""), s.name))
                        known[s] = item.si
                        solved.append(item)
                        remaining.remove(eq)
                        progress = True
                        break
                    try:
                        item.si = _evaluate(expr, known)
                    except ArithmeticError as exc:
                        alt = _ode_fallback(eq, s, known)
                        if alt is not None:
                            item.expr, item.si, item.numeric_ode, item.rearranged = alt[0], alt[1], True, False
                            diag.append(Diagnostic("info", "ODE_NUMERIC_FALLBACK", f"the closed-form solution of '{eq.ode.title}' is singular at these values "
                                                   f"({exc}); the equation was integrated numerically instead", s.name))
                            known[s] = item.si
                            solved.append(item)
                            remaining.remove(eq)
                            progress = True
                            break
                        if eq.ode is not None and eq.ode.numeric and s == eq.lhs and (s.name in targets or _needed(solved + [item], targets, s)):
                            err("EVAL_ERROR", f"{eq.title}: cannot evaluate {s.name}: {exc}", s.name)       # a failed numerical solution is reported, not "inverted"
                            return sol
                        if s.name in targets or _needed(solved + [item], targets, s):
                            try:       # the closed form exists but cannot be evaluated here (complex intermediates, a root of a negative number): search for the value
                                inverse = _invert_numeric(calc, eq, s, known, search_si.get(s.name))
                            except InversionError as inv_exc:
                                err("EVAL_ERROR", f"{eq.title}: cannot evaluate {s.name}: {exc}. Looking for the value numerically also failed: {inv_exc}", s.name)
                                hint_validity()
                                return sol
                            except ArithmeticError:
                                err("EVAL_ERROR", f"{eq.title}: cannot evaluate {s.name}: {exc}", s.name)
                                hint_validity()
                                return sol
                            item = _Solved(eq, s, _inverse_node(calc, eq, s), True)
                            item.si, item.inverse = inverse[0], inverse
                            info = inverse[1]
                            diag.append(Diagnostic("info", "NUMERIC_INVERSION", f"{calc.by_key[s.name].label} ({s.name}) was found numerically because the closed-form solution "
                                                   f"could not be evaluated ({exc}): root-finding {info['how']}, {info['evaluations']} evaluations, bracket "
                                                   f"[{info['bracket'][0]:.6g}, {info['bracket'][1]:.6g}] (SI). " + ("If you expected a different solution, give a search range." if info["auto"] else ""), s.name))
                            known[s] = item.si
                            solved.append(item)
                            remaining.remove(eq)
                            progress = True
                            break
                        continue
                    known[s] = item.si
                    solved.append(item)
                    remaining.remove(eq)
                    progress = True
                    break
                if not unknown:
                    checks.append(eq)
                    remaining.remove(eq)
                    progress = True
                    break
        done = {it.sym.name for it in solved}
        if all(t in done for t in targets):
            break
        retry = next((eq for eq in remaining if len(eq.symbols - known.keys()) == 1 and id(eq) not in second_chance), None)
        if retry is None:
            status = _solve_coupled(calc, remaining, known, solved, targets, search_si, diag)       # equations that share several unknowns are solved together
            if status == "error":
                return sol
            if status == "solved":
                continue
            break
        second_chance.add(id(retry))      # a target is still missing: let numerical root-finding have a go at this equation

    solved_keys = {it.sym.name for it in solved}
    missing_targets = [t for t in targets if t not in solved_keys]
    if missing_targets:
        for t in missing_targets:
            blockers = sorted({u.name for eq in calc.parsed if calc.by_key[t].symbol in eq.symbols
                               for u in eq.symbols if u not in known and u.name != t})
            err("MISSING_INPUTS",
                f"cannot determine {calc.by_key[t].label} ({t}): " +
                (f"also need values for {', '.join(blockers)}" if blockers
                 else "the equations are coupled in a way that cannot be solved: they do not form a square system (fewer equations than unknowns), or an unknown lies outside every block"), t)
        return sol

    needed = _prune(solved, targets)
    for eq in checks:
        try:
            diff = _evaluate(eq.lhs - eq.rhs, known)
            scale = max(abs(_evaluate(eq.lhs, known)), abs(_evaluate(eq.rhs, known)), 1e-300)
            if abs(diff) / scale > 1e-3:
                diag.append(Diagnostic("warning", "OVERSPECIFIED",
                                       f"supplied values are inconsistent with '{eq.text}' "
                                       f"(relative mismatch {abs(diff) / scale:.2g})"))
        except ArithmeticError:
            pass

    for cond, message in calc.parsed_validity:
        if cond.free_symbols <= known.keys():
            try:
                holds = bool(cond.subs({s: sp.Float(x, 20) for s, x in known.items()}))
            except TypeError:
                continue
            if not holds:
                diag.append(Diagnostic("warning", "VALIDITY", f"{message} (violated: {cond})"))

    used_syms = set().union(*(it.eq.symbols for it in needed)) if needed else set()
    for g in givens.values():
        if g.var.symbol not in used_syms:
            diag.append(Diagnostic("info", "UNUSED_INPUT",
                                   f"{g.var.label} ({g.var.key}) was not needed for this result", g.var.key))

    # ---- 4. standardization diagnostics ----------------------------------------------
    _standardization_diagnostics(givens, diag)

    # ---- 5. output conversion ---------------------------------------------------------
    out_units: dict[str, Unit] = {}
    for it in needed:
        v = calc.by_key[it.sym.name]
        text = output_units.get(v.key) if it.sym.name in targets else None
        if text and v.units and text.strip() not in v.units:
            err("UNIT_NOT_ALLOWED", f"{v.label} ({v.key}) must be expressed in {', '.join(v.units)}", v.key)
            continue
        try:
            u = reg.parse(text, as_delta=v.delta) if text else v.parsed
        except UnitError as exc:
            err(exc.code, f"output unit for {v.key}: {exc}", v.key)
            continue
        if u.dim != v.dim:
            err("DIM_MISMATCH", f"output unit '{u.symbol}' for {v.label} is {reg.describe(u.dim)}, "
                f"expected {reg.describe(v.dim)}", v.key)
            continue
        out_units[v.key] = u
    if any(d.level == "error" for d in diag):
        return sol

    for it in needed:
        v = calc.by_key[it.sym.name]
        u = out_units[v.key]
        shown = u.from_si(it.si)
        plain, tex = fmt_number(shown, sig)
        rec = {
            "key": v.key, "label": v.label, "latex": v.latex, "value": shown, "value_text": plain,
            "unit": u.symbol, "unit_latex": unit_tex(u), "si_value": it.si, "si_unit": v.si,
            "result_latex": rf"{v.latex} = {quantity_tex(shown, u, sig)}",
        }
        (sol.outputs if v.key in targets else sol.intermediates).append(rec)
    sol.outputs.sort(key=lambda r: targets.index(r["key"]))

    ctx = _Ctx(calc, sig)
    ctx.values = known
    sol.steps["symbolic"] = _symbolic_steps(ctx, givens, consts, needed, targets, out_units)
    sol.steps["numeric"] = _numeric_steps(ctx, givens, consts, needed, targets, out_units, known)
    if calc.parsed_odes:
        _ode_extras(sol, calc, known, givens, out_units, sig, ode_times)
    sol.ok = True
    return sol


def _ode_fallback(eq: Equation, s: sp.Symbol, known: dict):
    """A closed-form ODE solution can be singular at special parameter values (critical damping, ...): evaluate the numerical solution instead."""
    system = eq.ode
    if system is None or system.closed is None or s != eq.lhs or s not in system.fallback:
        return None
    expr = system.fallback[s](*system.inputs)
    try:
        return expr, _evaluate(expr, known)
    except ArithmeticError:
        return None


def _ode_extras(sol: Solution, calc: Calculation, known: dict, givens: dict, out_units: dict, sig: int, times_req: Sequence[Any] | None) -> None:
    """Plot data (the solution from the start to t) and a table at the requested times for each differential-equation system."""
    from .ode import OdeError

    reg = default_registry()
    for system in calc.parsed_odes:
        if any(s not in known for s in system.inputs):
            continue
        if getattr(system, "stochastic", False):
            _sde_extras(sol, calc, system, known, givens, out_units, sig)
            continue
        if getattr(system, "pde", False):
            if getattr(system, "multi", False):
                _pdemulti_extras(sol, calc, system, known, givens, out_units, sig, times_req)
                continue
            (_pde2d_extras if getattr(system, "dim", 1) == 2 else _pde_extras)(sol, calc, system, known, givens, out_units, sig, times_req)
            continue
        tv = calc.by_key[system.t.name]
        t_unit = givens[tv.key].unit if tv.key in givens else tv.parsed
        vals = {s: known[s] for s in system.inputs}
        req_si: list[float] = []
        for item in times_req or []:
            try:
                value, unit_text = parse_quantity(item) if isinstance(item, str) else (float(item), "")
                req_si.append(reg.parse(unit_text, as_delta=tv.delta).to_si(value) if unit_text.strip() else t_unit.to_si(value))
            except (UnitError, ValueError, TypeError) as exc:
                sol.diagnostics.append(Diagnostic("warning", "BAD_TIME", f"requested time {item!r} ignored: {exc}"))
        try:
            times, cols, info = system.trajectory(vals, 200, req_si)
        except (OdeError, ArithmeticError, ValueError, OverflowError) as exc:
            sol.diagnostics.append(Diagnostic("warning", "NO_PLOT", f"could not compute the solution over time: {exc}"))
            continue
        if system.bvp is not None:
            t_end = float(vals[system.t])                                  # the position asked for; the plot covers the whole interval
            a, b = system.interval(vals)
            lo, hi = min(a, b), max(a, b)
            if system.closed is not None and not lo - 1e-9 * (hi - lo) <= t_end <= hi + 1e-9 * (hi - lo):
                sol.diagnostics.append(Diagnostic("warning", "OUTSIDE_INTERVAL", f"{tv.label} = {t_unit.from_si(t_end):g} {t_unit.symbol} lies outside the interval "
                                                  f"[{t_unit.from_si(lo):g}, {t_unit.from_si(hi):g}] {t_unit.symbol} on which the boundary conditions apply; the formula is extrapolated"))
        else:
            t_end = times[-1] if times else float(vals[system.t])          # a terminal event ends the integration early
            lo, hi = min(system.start.subs(vals), t_end), max(system.start.subs(vals), t_end)
        stopped = info.get("stopped_by") is not None
        for x in req_si:
            if not (float(lo) <= x <= float(hi)):
                sol.diagnostics.append(Diagnostic("warning", "TIME_OUTSIDE",
                                                  f"a requested time ({t_unit.from_si(x):g} {t_unit.symbol}) lies outside the integration interval "
                                                  f"[{t_unit.from_si(float(lo)):g}, {t_unit.from_si(float(hi)):g}] {t_unit.symbol}"
                                                  + (" (the integration stops at an event)" if stopped else "") + " and was skipped"))
        dep_units = {d: out_units.get(d.name) or calc.by_key[d.name].parsed for d in system.dependents}
        shown_t = [t_unit.from_si(x) for x in times]
        series = [{"key": d.name, "label": calc.by_key[d.name].label, "latex": calc.by_key[d.name].latex, "unit": dep_units[d].symbol,
                   "values": [dep_units[d].from_si(v) for v in cols[d]]} for d in system.dependents]
        events = [{"title": system.events[h["index"]].title, "terminal": system.events[h["index"]].terminal, "t": t_unit.from_si(h["t"]),
                   "values": {k: dep_units[next(d for d in system.dependents if d.name == k)].from_si(v) for k, v in h["values"].items()}}
                  for h in info.get("events", [])]
        sol.series.append({"title": system.title, "method": {k: v for k, v in info.items() if k != "events"}, "independent": {"key": tv.key, "label": tv.label, "latex": tv.latex, "unit": t_unit.symbol},
                           "t": shown_t, "series": series, "why_numeric": system.why_numeric, "events": events, "stopped_at_event": stopped})
        rows_t = sorted({t_end, *[x for x in req_si if float(lo) <= x <= float(hi)]}, key=lambda x: (x - float(lo)))
        for x in rows_t:
            i = min(range(len(times)), key=lambda j: abs(times[j] - x))
            sol.table.append({"system": system.title, "t": fmt_number(t_unit.from_si(x), sig)[0], "t_unit": t_unit.symbol,
                              "values": {d.name: fmt_number(dep_units[d].from_si(cols[d][i]), sig)[0] for d in system.dependents},
                              "units": {d.name: dep_units[d].symbol for d in system.dependents}, "is_evaluation_time": x == t_end, "stopped_at_event": stopped and x == t_end})


def _pde_extras(sol: Solution, calc: Calculation, system, known: dict, givens: dict, out_units: dict, sig: int, times_req: Sequence[Any] | None) -> None:
    """Plots of a time-dependent PDE: the profile along the space variable at several times, and the history at the chosen position."""
    from .ode import OdeError

    reg = default_registry()
    tv, xv, uv = calc.by_key[system.t.name], calc.by_key[system.x.name], calc.by_key[system.dependent.name]
    t_unit = givens[tv.key].unit if tv.key in givens else tv.parsed
    x_unit = givens[xv.key].unit if xv.key in givens else xv.parsed
    u_unit = out_units.get(uv.key) or uv.parsed
    vals = {s: known[s] for s in system.inputs}
    t_end, x_at = float(vals[system.t]), float(vals[system.x])
    req: list[float] = []
    for item in times_req or []:
        try:
            value, unit_text = parse_quantity(item) if isinstance(item, str) else (float(item), "")
            req.append(reg.parse(unit_text, as_delta=tv.delta).to_si(value) if unit_text.strip() else t_unit.to_si(value))
        except (UnitError, ValueError, TypeError) as exc:
            sol.diagnostics.append(Diagnostic("warning", "BAD_TIME", f"requested time {item!r} ignored: {exc}"))
    for x in [r for r in req if not 0 <= r <= t_end]:
        sol.diagnostics.append(Diagnostic("warning", "TIME_OUTSIDE", f"a requested time ({t_unit.from_si(x):g} {t_unit.symbol}) lies outside 0 to {t_unit.from_si(t_end):g} {t_unit.symbol} and was skipped"))
    req = [r for r in req if 0 <= r <= t_end]
    snaps = sorted({0.0, t_end / 4, t_end / 2, 3 * t_end / 4, t_end, *req})
    if len(snaps) > 9:
        keep = {0.0, t_end, *req}
        snaps = sorted(keep | set(snaps[:: max(1, len(snaps) // 6)]))[:12]
    hist = [t_end * i / 60 for i in range(61)] if t_end > 0 else [0.0]
    try:
        fields = system.run(vals, outputs=sorted({*snaps, *hist, *req}))
        lo, hi = system.span(vals)
    except (OdeError, ArithmeticError, ValueError, OverflowError) as exc:
        sol.diagnostics.append(Diagnostic("warning", "NO_PLOT", f"could not compute the solution over space and time: {exc}"))
        return
    from .pde import interpolate

    by_t = {round(tt, 12): row for tt, row in zip(fields.times, fields.u)}

    def at(tt: float) -> list[float]:
        row = by_t.get(round(tt, 12))
        if row is None:
            k = min(range(len(fields.times)), key=lambda i: abs(fields.times[i] - tt))
            row = fields.u[k]
        return row
    info = {"method": fields.result.method, "steps": fields.result.steps, "rtol": fields.result.rtol, "notes": fields.result.notes}
    xs_shown = [x_unit.from_si(v) for v in fields.xs]
    latex = uv.latex
    t_info = {"key": tv.key, "label": tv.label, "latex": tv.latex, "unit": t_unit.symbol}
    x_info = {"key": xv.key, "label": xv.label, "latex": xv.latex, "unit": x_unit.symbol}
    sol.series.append({"title": f"{system.title} — profile along {xv.label}", "method": info, "independent": x_info, "t": xs_shown, "overlay": True, "why_numeric": system.why_numeric,
                       "series": [{"key": f"{uv.key}@{k}", "label": f"{tv.key} = {fmt_number(t_unit.from_si(tt), sig)[0]} {t_unit.symbol}", "latex": latex, "unit": u_unit.symbol,
                                   "values": [u_unit.from_si(v) for v in at(tt)]} for k, tt in enumerate(snaps)], "events": [], "stopped_at_event": False})
    if t_end > 0:
        sol.series.append({"title": f"{system.title} — history at {xv.key} = {fmt_number(x_unit.from_si(x_at), sig)[0]} {x_unit.symbol}", "method": info, "independent": t_info,
                           "t": [t_unit.from_si(tt) for tt in hist], "why_numeric": system.why_numeric,
                           "series": [{"key": uv.key, "label": uv.label, "latex": latex, "unit": u_unit.symbol,
                                       "values": [u_unit.from_si(interpolate(fields.xs, at(tt), min(max(x_at, lo), hi))) for tt in hist]}], "events": [], "stopped_at_event": False})
    for tt in sorted({t_end, *req}):
        value = interpolate(fields.xs, at(tt), min(max(x_at, lo), hi))
        sol.table.append({"system": system.title, "t": fmt_number(t_unit.from_si(tt), sig)[0], "t_unit": t_unit.symbol,
                          "values": {uv.key: fmt_number(u_unit.from_si(value), sig)[0]}, "units": {uv.key: u_unit.symbol}, "is_evaluation_time": tt == t_end, "stopped_at_event": False})
    if fields.error > 0:
        for note in fields.result.notes:
            if "increase the number of nodes" in note:
                sol.diagnostics.append(Diagnostic("warning", "PDE_RESOLUTION", note))


def _sde_extras(sol: Solution, calc: Calculation, system, known: dict, givens: dict, out_units: dict, sig: int) -> None:
    """Mean and one standard deviation around it over time for each unknown, a few sample paths, and the statistics with their errors."""
    from .ode import OdeError

    tv = calc.by_key[system.t.name]
    t_unit = givens[tv.key].unit if tv.key in givens else tv.parsed
    vals = {s: known[s] for s in system.inputs}
    try:
        res = system.run(vals)
    except (OdeError, ArithmeticError, ValueError, OverflowError) as exc:
        sol.diagnostics.append(Diagnostic("warning", "NO_PLOT", f"could not simulate the paths: {exc}"))
        return
    shown_t = [t_unit.from_si(x) for x in res.times]
    info = {"method": "Monte Carlo (Euler–Maruyama)", "steps": res.steps, "paths": res.paths, "notes": res.notes}
    for i, d in enumerate(system.dependents):
        v = calc.by_key[d.name]
        u = out_units.get(v.key) or v.parsed
        series = [{"key": f"{v.key}_mean", "label": f"mean of {v.label}", "latex": v.latex, "unit": u.symbol, "values": [u.from_si(m) for m in res.mean[:, i]]},
                  {"key": f"{v.key}_lo", "label": "mean − 1 standard deviation", "latex": v.latex, "unit": u.symbol, "values": [u.from_si(m - s) for m, s in zip(res.mean[:, i], res.std[:, i])]},
                  {"key": f"{v.key}_hi", "label": "mean + 1 standard deviation", "latex": v.latex, "unit": u.symbol, "values": [u.from_si(m + s) for m, s in zip(res.mean[:, i], res.std[:, i])]}]
        for k in range(res.sample.shape[2]):
            series.append({"key": f"{v.key}_path{k + 1}", "label": f"sample path {k + 1}", "latex": v.latex, "unit": u.symbol, "values": [u.from_si(float(x)) for x in res.sample[:, i, k]]})
        sol.series.append({"title": f"{system.title} — {v.label}", "method": info, "independent": {"key": tv.key, "label": tv.label, "latex": tv.latex, "unit": t_unit.symbol},
                           "t": shown_t, "series": series, "why_numeric": system.why_numeric, "events": [], "stopped_at_event": False})
    for (kind, di, var, _lv, _p), (value, err, alt) in zip(system.statistics, res.stats):
        v = calc.by_key[var.name]
        u = out_units.get(v.key) or v.parsed
        plain = kind in ("above", "below") or kind in ("hit_probability", "hit_count_mean")
        of = f"event '{system.sde_events[di].title}'" if kind.startswith("hit_") else calc.by_key[system.dependents[di].name].label
        sol.diagnostics.append(Diagnostic("info", "MONTE_CARLO", f"{v.label} ({kind} of {of}): {fmt_number(u.from_si(value), sig)[0]} {u.symbol} "
                                          f"± {fmt_number(u.from_si(err) if not plain else err, 2)[0]} (sampling, 1σ); "
                                          f"discretisation difference {fmt_number(u.from_si(alt) if not plain else alt, 2)[0]}", var.name))


def _pdemulti_extras(sol: Solution, calc: Calculation, system, known: dict, givens: dict, out_units: dict, sig: int, times_req: Sequence[Any] | None) -> None:
    """Coupled fields in one dimension: the single-field plots for each field. A rectangle over time: the final field as a heat map and the history at the chosen point."""
    from .ode import OdeError
    from .pdemulti import FieldView

    if system.moving is not None:
        _moving_extras(sol, calc, system, known, givens, out_units, sig)
        return
    views = [FieldView(system, k) for k in range(len(system.fields))]
    if system.dim == 1:
        for v in views:
            v.title = f"{system.title} — {calc.by_key[v.dependent.name].label}" if len(views) > 1 else system.title
            _pde_extras(sol, calc, v, known, givens, out_units, sig, times_req)
        return
    if system.steady:                                        # no time: the field on the plane through the chosen z, and profiles through the chosen point
        zv = calc.by_key[system.z.name] if system.z is not None else None
        z_unit = (givens[zv.key].unit if zv.key in givens else zv.parsed) if zv is not None else None
        for v in views:
            uv = calc.by_key[v.dependent.name]
            at = ""
            if zv is not None:
                z_si = float(known[system.z])
                at = f" on the plane {zv.key} = {fmt_number(z_unit.from_si(z_si), sig)[0]} {z_unit.symbol}"
            v.title = f"{system.title} — {uv.label}{at}" if len(views) > 1 else f"{system.title}{at}"
            _pde2d_extras(sol, calc, v, known, givens, out_units, sig, times_req)
        return
    reg = default_registry()
    tv = calc.by_key[system.t.name]
    t_unit = givens[tv.key].unit if tv.key in givens else tv.parsed
    vals = {s: known[s] for s in system.inputs}
    t_end = float(vals[system.t])
    for v in views:
        uv = calc.by_key[v.dependent.name]
        v.title = f"{system.title} — {uv.label} at {tv.key} = {fmt_number(t_unit.from_si(t_end), sig)[0]} {t_unit.symbol}" if len(views) > 1 else f"{system.title} at {tv.key} = {fmt_number(t_unit.from_si(t_end), sig)[0]} {t_unit.symbol}"
        _pde2d_extras(sol, calc, v, known, givens, out_units, sig, times_req)
        if t_end > 0:
            try:
                spans = system.span(vals)
                (xa, xb), (ya, yb) = spans[:2]
                hist = [t_end * i / 60 for i in range(61)]
                x_at, y_at = min(max(float(vals[system.x]), xa), xb), min(max(float(vals[system.y]), ya), yb)
                z_at = min(max(float(vals[system.z]), spans[2][0]), spans[2][1]) if system.dim == 3 else None
                series = v.history(vals, x_at, y_at, hist, z_at)
            except (OdeError, ArithmeticError, ValueError, OverflowError) as exc:
                sol.diagnostics.append(Diagnostic("warning", "NO_PLOT", f"could not compute the history: {exc}"))
                continue
            xv, yv = calc.by_key[system.x.name], calc.by_key[system.y.name]
            xu = givens[xv.key].unit if xv.key in givens else xv.parsed
            yu = givens[yv.key].unit if yv.key in givens else yv.parsed
            u_unit = out_units.get(uv.key) or uv.parsed
            sol.series.append({"title": f"{system.title} — history of {uv.label} at ({xv.key}, {yv.key}{', ' + calc.by_key[system.z.name].key if z_at is not None else ''}) = ({fmt_number(xu.from_si(x_at), sig)[0]}, {fmt_number(yu.from_si(y_at), sig)[0]}{', ' + fmt_number((givens[calc.by_key[system.z.name].key].unit if calc.by_key[system.z.name].key in givens else calc.by_key[system.z.name].parsed).from_si(z_at), sig)[0] if z_at is not None else ''})",
                               "method": {"method": system.last_result().method if system.last_result() else "", "steps": 0, "rtol": 0.0, "notes": []},
                               "independent": {"key": tv.key, "label": tv.label, "latex": tv.latex, "unit": t_unit.symbol}, "t": [t_unit.from_si(tt) for tt in hist],
                               "why_numeric": system.why_numeric, "events": [], "stopped_at_event": False,
                               "series": [{"key": uv.key, "label": uv.label, "latex": uv.latex, "unit": u_unit.symbol, "values": [u_unit.from_si(q) for q in series]}]})
    _ = reg


def _moving_extras(sol: Solution, calc: Calculation, system, known: dict, givens: dict, out_units: dict, sig: int) -> None:
    """A region whose end moves: each field's profile over the region at the time asked for, and the position of the moving end against time."""
    from .ode import OdeError

    tv, xv = calc.by_key[system.t.name], calc.by_key[system.x.name]
    sv = calc.by_key[system.moving[0].name]
    t_unit = givens[tv.key].unit if tv.key in givens else tv.parsed
    x_unit = givens[xv.key].unit if xv.key in givens else xv.parsed
    s_unit = out_units.get(sv.key) or sv.parsed
    vals = {q: known[q] for q in system.inputs}
    try:
        f = system.run(vals)
    except (OdeError, ArithmeticError, ValueError, OverflowError) as exc:
        sol.diagnostics.append(Diagnostic("warning", "NO_PLOT", f"could not compute the field: {exc}"))
        return
    info = {"method": f.result.method, "steps": f.result.steps, "rtol": f.result.rtol, "notes": f.result.notes}
    t_end = float(vals[system.t])
    for dep in system.fields:
        uv = calc.by_key[dep.name]
        u_unit = out_units.get(uv.key) or uv.parsed
        sol.series.append({"title": f"{system.title} — profile of {uv.label} at {tv.key} = {fmt_number(t_unit.from_si(t_end), sig)[0]} {t_unit.symbol}", "method": info,
                           "independent": {"key": xv.key, "label": xv.label, "latex": xv.latex, "unit": x_unit.symbol}, "t": [x_unit.from_si(v) for v in f.xs],
                           "why_numeric": system.why_numeric, "events": [], "stopped_at_event": False,
                           "series": [{"key": uv.key, "label": uv.label, "latex": uv.latex, "unit": u_unit.symbol, "values": [u_unit.from_si(v) for v in f.u[dep][-1][0]]}]})
    times, fronts = f.front
    sol.series.append({"title": f"{system.title} — position of the moving boundary", "method": info,
                       "independent": {"key": tv.key, "label": tv.label, "latex": tv.latex, "unit": t_unit.symbol}, "t": [t_unit.from_si(v) for v in times],
                       "why_numeric": system.why_numeric, "events": [], "stopped_at_event": False,
                       "series": [{"key": sv.key, "label": sv.label, "latex": sv.latex, "unit": s_unit.symbol, "values": [s_unit.from_si(v) for v in fronts]}]})


def _pde2d_extras(sol: Solution, calc: Calculation, system, known: dict, givens: dict, out_units: dict, sig: int, times_req: Sequence[Any] | None) -> None:
    """A heat map of the field over the rectangle plus profiles along each axis through the chosen point."""
    from .ode import OdeError
    from .pde import interpolate
    from .pde2d import interpolate2d

    xv, yv, uv = calc.by_key[system.x.name], calc.by_key[system.y.name], calc.by_key[system.dependent.name]
    x_unit = givens[xv.key].unit if xv.key in givens else xv.parsed
    y_unit = givens[yv.key].unit if yv.key in givens else yv.parsed
    u_unit = out_units.get(uv.key) or uv.parsed
    vals = {s: known[s] for s in system.inputs}
    try:
        f = system.run(vals)
        (xa, xb), (ya, yb) = system.span(vals)
    except (OdeError, ArithmeticError, ValueError, OverflowError) as exc:
        sol.diagnostics.append(Diagnostic("warning", "NO_PLOT", f"could not compute the field: {exc}"))
        return
    x_at = min(max(float(vals[system.x]), xa), xb)
    y_at = min(max(float(vals[system.y]), ya), yb)
    info = {"method": f.result.method, "steps": f.result.steps, "rtol": f.result.rtol, "notes": f.result.notes}
    x_info = {"key": xv.key, "label": xv.label, "latex": xv.latex, "unit": x_unit.symbol}
    y_info = {"key": yv.key, "label": yv.label, "latex": yv.latex, "unit": y_unit.symbol}
    step = max(1, (len(f.xs) - 1) // 60)
    ix, iy = list(range(0, len(f.xs), step)), list(range(0, len(f.ys), step))
    if ix[-1] != len(f.xs) - 1:
        ix.append(len(f.xs) - 1)
    if iy[-1] != len(f.ys) - 1:
        iy.append(len(f.ys) - 1)
    hole = getattr(f, "hole", None)
    z = [[None if hole is not None and hole[j][i] else u_unit.from_si(f.u[j][i]) for i in ix] for j in iy]
    flat = [v for row in z for v in row if v is not None]
    sol.series.append({"title": f"{system.title} — field", "method": info, "independent": x_info, "t": [x_unit.from_si(f.xs[i]) for i in ix], "series": [], "events": [], "stopped_at_event": False,
                       "why_numeric": system.why_numeric,
                       "heatmap": {"x": [x_unit.from_si(f.xs[i]) for i in ix], "y": [y_unit.from_si(f.ys[j]) for j in iy], "z": z, "zmin": min(flat), "zmax": max(flat),
                                   "x_info": x_info, "y_info": y_info, "u": {"key": uv.key, "label": uv.label, "unit": u_unit.symbol},
                                   "point": {"x": x_unit.from_si(x_at), "y": y_unit.from_si(y_at)}}})
    row = [interpolate(f.ys, [r[i] for r in f.u], y_at) for i in range(len(f.xs))]
    col = [interpolate(f.xs, r, x_at) for r in f.u]
    row_axis, col_axis = list(f.xs), list(f.ys)
    if hole is not None:                                           # profiles through a cutout: only the nodes in the region
        jn, in_ = min(range(len(f.ys)), key=lambda j: abs(f.ys[j] - y_at)), min(range(len(f.xs)), key=lambda i: abs(f.xs[i] - x_at))
        keep_r, keep_c = [i for i in range(len(f.xs)) if not hole[jn][i]], [j for j in range(len(f.ys)) if not hole[j][in_]]
        row, row_axis = [row[i] for i in keep_r], [f.xs[i] for i in keep_r]
        col, col_axis = [col[j] for j in keep_c], [f.ys[j] for j in keep_c]
    for ind, axis, vals_si, unit, at, other, ounit in ((x_info, row_axis, row, x_unit, y_at, yv, y_unit), (y_info, col_axis, col, y_unit, x_at, xv, x_unit)):
        sol.series.append({"title": f"{system.title} — along {ind['key']} at {other.key} = {fmt_number(ounit.from_si(at), sig)[0]} {ounit.symbol}", "method": info, "independent": ind,
                           "t": [unit.from_si(v) for v in axis], "why_numeric": system.why_numeric, "events": [], "stopped_at_event": False,
                           "series": [{"key": uv.key, "label": uv.label, "latex": uv.latex, "unit": u_unit.symbol, "values": [u_unit.from_si(v) for v in vals_si]}]})
    if f.error > 0:
        for note in f.result.notes:
            if "increase the number of nodes" in note:
                sol.diagnostics.append(Diagnostic("warning", "PDE_RESOLUTION", note))
    _ = interpolate2d


def plan_structure(calc: Calculation, known: set[sp.Symbol], allow_numeric: bool = False):
    """Value-free version of the ordering loop in :func:`solve`.

    Returns ``(solved, checks, known_after, failures)``: the equations in executable order with their isolated
    expressions, equations that were fully determined by the givens (consistency checks), every symbol that
    could be determined, and symbols for which sympy could not rearrange an equation. With ``allow_numeric`` such an equation is
    planned as solvable by numerical root-finding (a ``root_s(...)`` placeholder), which is what :func:`solve` will try.
    """
    known = set(known)
    remaining = list(calc.parsed)
    solved: list[_Solved] = []
    checks: list[Equation] = []
    failures: dict[sp.Symbol, Exception] = {}
    progress = True
    while progress and remaining:
        progress = False
        for eq in remaining:
            unknown = eq.symbols - known
            if len(unknown) == 1:
                (s,) = unknown
                try:
                    expr, rearranged = _isolate(eq, s)
                except Exception as exc:  # sympy cannot invert this equation for s
                    if not allow_numeric:
                        failures[s] = exc
                        continue
                    expr, rearranged = _inverse_node(calc, eq, s), True
                solved.append(_Solved(eq, s, expr, rearranged))
                known.add(s)
                remaining.remove(eq)
                progress = True
                break
            if not unknown:
                checks.append(eq)
                remaining.remove(eq)
                progress = True
                break
        if not progress and remaining:
            for block in simul.find_blocks(remaining, known):          # coupled equations: linear ones have a closed form, nonlinear ones are solved numerically
                if not simul.is_ready(block, known):
                    continue
                lin = simul._linear_form([e.lhs - e.rhs for e in block.eqs], block.unknowns)
                if lin is None and not allow_numeric:
                    for u in block.unknowns:
                        failures[u] = ValueError("the equations are nonlinear and coupled (solved numerically)")
                    continue
                exprs = None
                if lin is not None and len(block.unknowns) <= simul.MAX_SYMBOLIC:
                    try:
                        sol_ = sp.linsolve(lin, *block.unknowns)
                        tup = next(iter(sol_)) if sol_ else None
                        exprs = dict(zip(block.unknowns, tup)) if tup is not None and len(tup) == len(block.unknowns) else None
                    except Exception:  # noqa: BLE001
                        exprs = None
                info = _BlockInfo(block, simul.BlockResult({}, "linear (exact)" if exprs else "Newton", exprs, {}))
                for eq_, sym_ in zip(block.eqs, block.unknowns):
                    item = _Solved(eq_, sym_, exprs[sym_] if exprs else _block_node(calc, block, sym_), True)
                    item.block = info
                    solved.append(item)
                    known.add(sym_)
                    remaining.remove(eq_)
                progress = True
                break
    return solved, checks, known, failures


def prune_plan(solved: list[_Solved], targets: list[str]) -> list[_Solved]:
    """Keep only the steps needed to determine ``targets``."""
    return _prune(solved, targets)


def _needed(solved: list[_Solved], targets: list[str], extra: sp.Symbol) -> bool:
    return extra.name in {t for t in targets} or any(extra in it.expr.free_symbols for it in solved if it.sym.name in targets)


def _prune(solved: list[_Solved], targets: list[str]) -> list[_Solved]:
    want = set(targets)
    keep: list[_Solved] = []
    for it in reversed(solved):
        if it.sym.name in want:
            keep.append(it)
            want |= {s.name for s in it.expr.free_symbols}
    keep.reverse()
    return keep


def _standardization_diagnostics(givens: dict[str, _Given], diag: list[Diagnostic]) -> None:
    usc, metric = [], []
    for key, g in givens.items():
        s = g.unit.systems
        if "USC" in s and (s & {"SI", "metric"}):
            diag.append(Diagnostic("warning", "MIXED_SYSTEMS_IN_UNIT",
                                   f"'{g.unit.symbol}' for {key} mixes US customary and metric components", key))
        if "USC" in s:
            usc.append(f"{key} [{g.unit.symbol}]")
        if s & {"SI", "metric"}:
            metric.append(f"{key} [{g.unit.symbol}]")
        for note in g.unit.notes:
            diag.append(Diagnostic("info", "UNIT_NOTE", f"{g.unit.symbol}: {note}", key))
        if g.var.delta and g.unit_text.strip() in ("degC", "°C", "degF", "°F"):
            diag.append(Diagnostic("info", "TEMPERATURE_DIFFERENCE",
                                   f"{key} is a temperature difference, so '{g.unit_text}' was read as a "
                                   "difference (no offset applied)", key))
    if usc and metric:
        diag.append(Diagnostic(
            "warning", "MIXED_UNIT_SYSTEMS",
            "inputs mix US customary (" + ", ".join(usc) + ") and metric (" + ", ".join(metric) + ") units. "
            "Everything is converted to SI before calculating, so the result is still consistent, "
            "but double-check that each value was entered in the unit you intended."))


# ---------------------------------------------------------------- step writers

def _symbolic_steps(ctx: _Ctx, givens, consts, needed: list[_Solved], targets, out_units) -> list[Step]:
    calc = ctx.calc
    steps: list[Step] = []
    used = set().union(*(it.eq.symbols for it in needed))

    s = Step("Known and unknown quantities")
    for g in givens.values():
        if g.var.symbol in used:
            s.lines.append(Line(g.var.latex, f"{g.var.label} (given) — SI unit: {g.var.si}"))
    for c in consts.values():
        if c.symbol in used:
            s.lines.append(Line(c.latex, f"{c.label} (constant) — SI unit: {c.si}"))
    for t in targets:
        v = calc.by_key[t]
        s.lines.append(Line(v.latex, f"{v.label} (unknown, to find) — SI unit: {v.si}"))
    steps.append(s)

    shown_odes: set[int] = set()
    shown_blocks: set[int] = set()
    for it in needed:
        v = calc.by_key[it.sym.name]
        if it.block is not None:
            steps.extend(_block_symbolic_steps(ctx, it, v, shown_blocks))
            continue
        if it.eq.ode is not None:
            steps.extend(_ode_symbolic_steps(ctx, it, v, shown_odes))
            continue
        if it.inverse is not None:
            st = Step(f"Solve numerically for {v.label}")
            eq_tex = f"{_tex(it.eq.written[0] if it.eq.written else it.eq.lhs, ctx.names)} = {_tex(it.eq.written[1] if it.eq.written else it.eq.rhs, ctx.names)}"
            st.lines.append(Line(eq_tex, "governing equation"))
            st.lines.append(Line(rf"F\left({v.latex}\right) = \left({_tex(it.eq.lhs, ctx.names)}\right) - \left({_tex(it.eq.rhs, ctx.names)}\right) = 0",
                                 f"{v.label} cannot be isolated in closed form, so it is the root of F, found by bracketing and Brent's method"))
            steps.append(st)
            continue
        st = Step(it.eq.title if len(needed) > 1 or it.rearranged else "Governing equation")
        if it.eq.written:
            wl, wr = it.eq.written
            st.lines.append(Line(f"{_tex(wl, ctx.names)} = {_tex(wr, ctx.names)}", "governing equation, as written"))
            ev = f"{_tex(it.eq.lhs, ctx.names)} = {_tex(it.eq.rhs, ctx.names)}"
            has_int = it.eq.lhs.has(sp.Integral) or it.eq.rhs.has(sp.Integral)
            has_sum = it.eq.lhs.has(sp.Sum) or it.eq.rhs.has(sp.Sum)
            numeric_note = ("the integral has no closed form and is integrated numerically (adaptive quadrature) once values are substituted" if has_int else "")
            if has_sum:
                numeric_note += ("; " if numeric_note else "") + "the sum is added term by term once values are substituted (it is not expanded)"
            if not it.eq.numeric_integral:
                st.lines.append(Line(ev, "derivatives and integrals evaluated symbolically"))
            elif st.lines[-1].latex == ev:
                st.lines[-1].note = "governing equation, as written; " + numeric_note
            else:
                st.lines.append(Line(ev, "derivatives evaluated symbolically; " + numeric_note))
        else:
            st.lines.append(Line(f"{_tex(it.eq.lhs, ctx.names)} = {_tex(it.eq.rhs, ctx.names)}", "governing equation"))
        if it.rearranged:
            st.lines.append(Line(f"{v.latex} = {_tex(it.expr, ctx.names)}", f"rearranged for {v.label}"))
        steps.append(st)

    closed = Step("Closed-form solution in terms of the given quantities")
    for t in targets:
        it = next(i for i in needed if i.sym.name == t)
        expr = it.expr
        for p in reversed(needed[:needed.index(it)]):
            if p.sym in expr.free_symbols:
                expr = expr.subs(p.sym, p.expr)
        if expr != it.expr:
            closed.lines.append(Line(f"{calc.by_key[t].latex} = {_tex(expr, ctx.names)}", "intermediate results substituted"))
    if closed.lines:
        steps.append(closed)

    chk = Step("Dimensional (unit) check")
    for it in needed:
        v = calc.by_key[it.sym.name]
        chain = ctx.unit_line(it.expr, v)
        chk.lines.append(Line(rf"\left[{v.latex}\right] = {chain}", "the units of this rearranged form could not be tracked symbolically; every value is converted to SI, so the result has the unit shown"
                              if "not reduced symbolically" in chain else "units of the right-hand side reduce to the expected SI unit"))
    steps.append(chk)

    conv = Step("Express the result in the requested unit")
    for t in targets:
        v = calc.by_key[t]
        u = out_units[t]
        if not u.is_identity:
            si_tex = unit_tex(v.si_parsed)
            if u.shift:
                body = rf"{{{v.latex}}}_{{{unit_tex(u)}}} = \frac{{{{{v.latex}}}_{{{si_tex}}}}}{{{fmt_number(u.factor, ctx.sig + 1)[1]}}} - {fmt_number(u.shift, ctx.sig + 1)[1]}"
            else:
                body = rf"{{{v.latex}}}_{{{unit_tex(u)}}} = {{{v.latex}}}_{{{si_tex}}}\times\frac{{1\,{unit_tex(u)}}}{{{fmt_number(u.factor, ctx.sig + 1)[1]}\,{si_tex}}}"
            conv.lines.append(Line(body, f"convert {v.label} from {v.si} to {u.symbol}"))
    if conv.lines:
        steps.append(conv)
    return steps


def _eq_display(ctx: _Ctx, eq: Equation) -> str:
    a, b = eq.written if eq.written else (eq.lhs, eq.rhs)
    return f"{_tex(a, ctx.names)} = {_tex(b, ctx.names)}"


def _block_symbolic_steps(ctx: _Ctx, it: _Solved, v: Variable, shown: set[int]) -> list[Step]:
    info = it.block
    block, result = info.block, info.result
    steps: list[Step] = []
    if id(info) not in shown:
        shown.add(id(info))
        names = ", ".join(ctx.calc.by_key[u.name].latex or u.name for u in block.unknowns)
        intro = Step(f"Coupled equations: {len(block.unknowns)} unknowns solved together")
        for eq in block.eqs:
            intro.lines.append(Line(_eq_display(ctx, eq), f"{eq.title}: shares unknowns with the others, so it cannot be solved on its own"))
        if result.method == "tearing":
            tear_name = ctx.calc.by_key[result.info["tear"]].latex or result.info["tear"]
            intro.lines.append(Line(rf"g\left({tear_name}\right) = 0",
                                    f"the equations are nonlinear. {result.info['tear']} is 'torn' (treated as known): each other equation then has one unknown and is solved in turn, leaving one equation as the residual g, "
                                    "whose root is found by bracketing and Brent's method (every sign change in the allowed range is examined, so a second solution is noticed)"))
        elif result.method == "Newton":
            intro.lines.append(Line(rf"\mathbf{{F}}\left({names}\right) = \mathbf{{0}}",
                                    "the equations are nonlinear, so they are solved simultaneously by Newton's method (exact Jacobian, damped steps, several starting points, unknowns kept in their allowed ranges)"))
        else:
            intro.lines.append(Line(rf"\mathbf{{A}}\,\left({names}\right)^{{T}} = \mathbf{{b}}",
                                    "the equations are linear in the unknowns, so they are solved as a linear system" + (" exactly (symbolically)" if result.exprs else " (numerically)")))
        steps.append(intro)
    st = Step(f"Solution for {v.label}")
    if result.exprs:
        st.lines.append(Line(f"{v.latex} = {_tex(it.expr, ctx.names)}", "solved from the linear system in terms of the given quantities"))
    else:
        st.lines.append(Line(rf"{v.latex} = \mathrm{{solve}}\left(\ldots\right)", "found together with the other unknowns of the block"))
    steps.append(st)
    return steps


def _ode_symbolic_steps(ctx: _Ctx, it: _Solved, v: Variable, shown: set[int]) -> list[Step]:
    system = it.eq.ode
    steps: list[Step] = []
    closed = system.closed is not None and not it.numeric_ode
    if id(system) not in shown:
        shown.add(id(system))
        intro = Step(f"Differential equation: {system.title}")
        for tex in system.written_latex(ctx.names):
            intro.lines.append(Line(tex, "governing differential equation, as written"))
        for tex in system.condition_latex(ctx.names):
            intro.lines.append(Line(tex, system.condition_note))
        for tex, note in system.event_latex(ctx.names):
            intro.lines.append(Line(tex, note))
        if closed:
            intro.lines.append(Line(rf"\text{{{system.method if system.method != 'auto' else 'dsolve'}}}", "a closed-form solution exists (found symbolically with SymPy's dsolve), so the equation is solved exactly and can be rearranged like any other"))
        else:
            how = ("by multiple shooting: the interval is cut into segments, each integrated with adaptive Dormand–Prince RK45 together with its sensitivities, "
                   "and Newton's method makes the segments join up and satisfy the boundary conditions" if system.bvp is not None else
                   "(adaptive Dormand–Prince RK45; an implicit method if the problem is stiff)")
            intro.lines.append(Line(r"\text{numerical solution}" if system.bvp is not None else r"\text{numerical integration}",
                                    f"{system.why_numeric or 'no closed form was found'}: the equation is solved numerically {how}. Other quantities are found by root-finding on it"))
        steps.append(intro)
    st = Step(f"Solution of the differential equation for {v.label}" if it.sym == it.eq.lhs else f"Rearranged for {v.label}")
    if it.inverse is not None:
        st.title = f"Solve numerically for {v.label}"
        st.lines.append(Line(f"{_tex(it.eq.lhs, ctx.names)} = {_tex(it.eq.rhs, ctx.names)}", "the differential equation's solution"))
        st.lines.append(Line(rf"F\left({v.latex}\right) = \left({_tex(it.eq.lhs, ctx.names)}\right) - \left({_tex(it.eq.rhs, ctx.names)}\right) = 0",
                             f"{v.label} cannot be isolated, so it is the root of F: each trial value requires solving the differential equation; found by bracketing and Brent's method"))
    elif closed:
        st.lines.append(Line(f"{_tex(it.eq.lhs, ctx.names)} = {_tex(it.eq.rhs, ctx.names)}", f"closed-form solution of the differential equation with its {system.condition_note}s"))
        if it.rearranged:
            st.lines.append(Line(f"{v.latex} = {_tex(it.expr, ctx.names)}", f"rearranged for {v.label}"))
    else:
        st.lines.append(Line(f"{_tex(it.eq.lhs, ctx.names)} = {_tex(it.eq.rhs, ctx.names)}", "numerical solution of the differential equation at this value of the independent variable"))
    steps.append(st)
    return steps


def _numeric_steps(ctx: _Ctx, givens, consts, needed: list[_Solved], targets, out_units, known) -> list[Step]:
    calc, sig = ctx.calc, ctx.sig
    steps: list[Step] = []
    used = set().union(*(it.eq.symbols for it in needed))

    s = Step("Given values and unit standardization (convert to SI)")
    for g in givens.values():
        v = g.var
        if v.symbol not in used:
            continue
        si_tex = unit_tex(v.si_parsed)
        given_tex = quantity_tex(g.value, g.unit, sig)
        si_val = quantity_tex(g.si, v.si_parsed, sig)
        if g.unit.is_identity:
            s.lines.append(Line(rf"{v.latex} = {given_tex}", "already in coherent SI units"))
        elif g.unit.shift:
            a, b = fmt_number(g.value, sig)[1], fmt_number(g.unit.shift, sig + 1)[1]
            fac = "" if g.unit.factor == 1 else rf"\times {fmt_number(g.unit.factor, sig + 1)[1]}"
            expr = rf"\left({a} + {b}\right){fac}" if g.unit.factor != 1 else rf"{a} + {b}"
            s.lines.append(Line(rf"{v.latex} = {given_tex} \;\Rightarrow\; {expr}\,{si_tex} = {si_val}",
                                "temperature scales differ by an offset as well as a factor"))
        else:
            s.lines.append(Line(
                rf"{v.latex} = {given_tex} \times {_conversion_factor_tex(g.unit, si_tex, sig)} = {si_val}",
                f"convert {g.unit.symbol} to {v.si}"))
    for c in consts.values():
        if c.symbol in used:
            s.lines.append(Line(rf"{c.latex} = {quantity_tex(known[c.symbol], c.si_parsed, sig)}", f"{c.label} (constant)"))
    steps.append(s)

    values_tex: dict[sp.Symbol, str] = {}
    for g in givens.values():
        values_tex[g.var.symbol] = rf"\left({quantity_tex(g.si, g.var.si_parsed, sig)}\right)"
    for c in consts.values():
        values_tex[c.symbol] = rf"\left({quantity_tex(known[c.symbol], c.si_parsed, sig)}\right)"

    shown_blocks_n: set[int] = set()
    for it in needed:
        v = calc.by_key[it.sym.name]
        st = Step(f"Calculate {v.label}" + (f" — {it.eq.title}" if len(calc.parsed) > 1 else ""))
        if it.block is not None and not it.block.result.exprs:
            res = it.block.result
            if id(it.block) not in shown_blocks_n:
                shown_blocks_n.add(id(it.block))
                if res.method == "tearing":
                    st.lines.append(Line(rf"\text{{tear variable {res.info['tear']}: {res.info['evaluations']} evaluations}}",
                                         f"the {len(it.block.block.unknowns)} coupled equations were reduced to one equation in {res.info['tear']}; Brent's method on a sign change, in SI"))
                elif res.method == "Newton":
                    st.lines.append(Line(rf"\text{{Newton: }}{res.info['iterations']}\text{{ iterations, residual }}{res.info['residual']:.2g}",
                                         f"the {len(it.block.block.unknowns)} coupled equations were solved together; {res.info['starts']} starting point(s) tried, in SI"))
                else:
                    st.lines.append(Line(rf"\text{{linear system, condition number }}{res.info['condition']:.3g}", "solved numerically as one linear system, in SI"))
            st.lines.append(Line(f"{v.latex} = {quantity_tex(it.si, v.si_parsed, sig)}", "result in SI"))
            values_tex[it.sym] = rf"\left({quantity_tex(it.si, v.si_parsed, sig)}\right)"
            steps.append(st)
            continue
        if it.inverse is not None:
            info = it.inverse[1]
            sub_eq = _tex(it.eq.lhs - it.eq.rhs, {**ctx.names, **values_tex}, mul_symbol="dot", fold_short_frac=False)
            st.lines.append(Line(rf"F\left({v.latex}\right) = {_tex(it.eq.lhs, ctx.names)} - \left({_tex(it.eq.rhs, ctx.names)}\right) = 0", f"{v.label} is the root of F"))
            st.lines.append(Line(rf"\text{{bracket}} = \left[{fmt_number(info['bracket'][0], sig)[1]},\, {fmt_number(info['bracket'][1], sig)[1]}\right]\,{unit_tex(v.si_parsed)},\;"
                                 rf"{info['evaluations']}\text{{ evaluations}}",
                                 f"Brent's method on a sign change of F, found {info['how']}; the residual is {abs(info['residual']):.2g} against a scale of {info['scale']:.3g}"))
            st.lines.append(Line(f"{v.latex} = {quantity_tex(it.si, v.si_parsed, sig)}", "result in SI"))
            values_tex[it.sym] = rf"\left({quantity_tex(it.si, v.si_parsed, sig)}\right)"
            _ = sub_eq
            steps.append(st)
            continue
        st.lines.append(Line(f"{v.latex} = {_tex(it.expr, ctx.names)}", "formula"))
        if it.eq.ode is not None and (it.eq.ode.numeric or it.numeric_ode):
            res = it.eq.ode.last_result()
            if res is not None:
                st.lines.append(Line(rf"\text{{{res.method}}},\; {res.steps}\text{{ steps}},\; \text{{rtol}} = {res.rtol:g}",
                                     ("numerical solution of the boundary-value problem, in SI" if it.eq.ode.bvp is not None else "numerical integration of the differential equation from its initial conditions, in SI")
                                     + ("; " + "; ".join(res.notes) if res.notes else "")))
        else:
            sub = _tex(it.expr, {**ctx.names, **values_tex}, mul_symbol="dot", fold_short_frac=False)
            st.lines.append(Line(f"{v.latex} = {sub}", "substitute SI values with units"))
        if it.eq.numeric_integral:
            for integral in sorted(it.expr.atoms(sp.Integral), key=str):
                try:
                    val = _evaluate(integral, known)
                except ArithmeticError:
                    continue
                itex = _tex(integral, {**ctx.names, **values_tex}, mul_symbol="dot", fold_short_frac=False)
                st.lines.append(Line(rf"{itex} \approx {fmt_number(val, sig)[1]}", "integral evaluated numerically (adaptive quadrature), in SI"))
            for total in sorted(it.expr.atoms(sp.Sum), key=str):
                try:
                    val = _evaluate(total, known)
                except ArithmeticError:
                    continue
                itex = _tex(total, {**ctx.names, **values_tex}, mul_symbol="dot", fold_short_frac=False)
                st.lines.append(Line(rf"{itex} \approx {fmt_number(val, sig)[1]}", "sum evaluated term by term, in SI"))
        chain = ctx.unit_line(it.expr, v)
        st.lines.append(Line(rf"\left[{v.latex}\right] = {chain}", "unit of the result (not reduced symbolically)" if "not reduced symbolically" in chain else "unit reduction"))
        st.lines.append(Line(f"{v.latex} = {quantity_tex(it.si, v.si_parsed, sig)}", "result in SI"))
        values_tex[it.sym] = rf"\left({quantity_tex(it.si, v.si_parsed, sig)}\right)"
        steps.append(st)

    conv = Step("Convert the result to the requested unit")
    for t in targets:
        v = calc.by_key[t]
        u = out_units[t]
        if u.is_identity:
            continue
        si_tex = unit_tex(v.si_parsed)
        it = next(i for i in needed if i.sym.name == t)
        shown = u.from_si(it.si)
        if u.shift:
            body = (rf"{v.latex} = \frac{{{quantity_tex(it.si, v.si_parsed, sig)}}}{{{fmt_number(u.factor, sig + 1)[1]}}}"
                    rf" - {fmt_number(u.shift, sig + 1)[1]} = {quantity_tex(shown, u, sig)}")
        else:
            body = (rf"{v.latex} = {quantity_tex(it.si, v.si_parsed, sig)} \times "
                    rf"\frac{{1\,{unit_tex(u)}}}{{{fmt_number(u.factor, sig + 1)[1]}\,{si_tex}}} = {quantity_tex(shown, u, sig)}")
        conv.lines.append(Line(body, f"{v.si} → {u.symbol}"))
    if conv.lines:
        steps.append(conv)

    res = Step("Result")
    for t in targets:
        v = calc.by_key[t]
        shown = out_units[t].from_si(next(i for i in needed if i.sym.name == t).si)
        res.lines.append(Line(rf"\boxed{{{v.latex} = {quantity_tex(shown, out_units[t], sig)}}}", v.label))
    steps.append(res)
    return steps
