"""Dimensional analysis of sympy expressions.

``analyze`` walks an expression tree and returns both the :class:`Dimension` and a sympy
*unit expression* (product of unit symbols), so the same pass powers the registration-time
homogeneity check and the "unit check" lines in solution steps.
"""

from __future__ import annotations

from fractions import Fraction

import sympy as sp
from sympy.core.relational import Relational

from ..units import DIMENSIONLESS, Dimension, UnitError

ONE = sp.Integer(1)


class DimensionError(UnitError):
    def __init__(self, message: str):
        super().__init__(message, "DIM_HOMOGENEITY")


def _as_fraction(e: sp.Expr) -> Fraction:
    r = sp.nsimplify(e)
    if r.is_Rational:
        return Fraction(int(r.p), int(r.q))
    raise DimensionError(f"exponent {e} is not a rational number, so units cannot be tracked through it")


def analyze(expr: sp.Basic, env: dict[sp.Symbol, tuple[Dimension, sp.Expr]]) -> tuple[Dimension, sp.Expr]:
    if isinstance(expr, sp.Symbol):
        if expr not in env:
            raise DimensionError(f"symbol {expr} has no declared dimension")
        return env[expr]
    if expr.is_number:
        return DIMENSIONLESS, ONE
    if isinstance(expr, sp.Add):
        parts = [analyze(a, env) for a in expr.args]
        d0, u0 = parts[0]
        for a, (d, _) in zip(expr.args[1:], parts[1:]):
            if d != d0:
                raise DimensionError(f"cannot add terms with different dimensions: {expr.args[0]} [{d0}] vs {a} [{d}]")
        return d0, u0
    if isinstance(expr, sp.Mul):
        dim, unit = DIMENSIONLESS, ONE
        for a in expr.args:
            d, u = analyze(a, env)
            dim, unit = dim * d, unit * u
        return dim, unit
    if isinstance(expr, sp.Pow):
        bd, bu = analyze(expr.base, env)
        ed, _ = analyze(expr.exp, env)
        if not ed.is_dimensionless:
            raise DimensionError(f"exponent of {expr} must be dimensionless")
        if bd.is_dimensionless:
            return DIMENSIONLESS, ONE
        p = _as_fraction(expr.exp)
        return bd ** p, bu ** sp.Rational(p.numerator, p.denominator)
    if isinstance(expr, sp.Piecewise):
        results = []
        for e, cond in expr.args:
            if e != 0 and not e.has(sp.nan, sp.zoo):  # a literal zero branch, or one that is undefined (nan, zoo: 'no solution here'), is valid in any dimension
                results.append(analyze(e, env))
            _check_condition(cond, env)
        if not results:
            return DIMENSIONLESS, ONE
        d0, u0 = results[0]
        if any(d != d0 for d, _ in results[1:]):
            raise DimensionError(f"branches of {expr} have different dimensions")
        return d0, u0
    if isinstance(expr, (sp.Abs, sp.Min, sp.Max, sp.sign)):
        parts = [analyze(a, env) for a in expr.args]
        d0, u0 = parts[0]
        if any(d != d0 for d, _ in parts[1:]):
            raise DimensionError(f"arguments of {expr} must share one dimension")
        return (DIMENSIONLESS, ONE) if isinstance(expr, sp.sign) else (d0, u0)
    if isinstance(expr, sp.Derivative):   # d^n f / dx^n has the dimension of f / x^n
        dim, unit = analyze(expr.expr, env)
        for var, n in expr.variable_count:
            dv, uv = analyze(var, env)
            dim, unit = dim / dv ** int(n), unit / uv ** int(n)
        return dim, unit
    if isinstance(expr, sp.Integral):     # the integration variable takes its dimension from the limits; the integral gains it
        inner = dict(env)
        gain_d, gain_u = DIMENSIONLESS, ONE
        for var, lo, hi in expr.limits:
            (dl, ul), (dh, uh) = analyze(lo, env), analyze(hi, env)
            if lo == 0:
                dl, ul = dh, uh
            elif hi == 0:
                dh, uh = dl, ul
            if dl != dh:
                raise DimensionError(f"the limits of the integral over {var} have different dimensions: [{dl}] vs [{dh}]")
            if var in env and env[var][0] != dl:
                raise DimensionError(f"the integral over {var} has limits of dimension [{dl}] but {var} is [{env[var][0]}]")
            inner[var] = (dl, ul)
            gain_d, gain_u = gain_d * dl, gain_u * ul
        di, ui = analyze(expr.function, inner)
        return di * gain_d, ui * gain_u
    if isinstance(expr, sp.Sum):          # the index is a pure number; the sum has the dimension of its term
        inner = dict(env)
        for var, _lo, _hi in expr.limits:
            inner[var] = (DIMENSIONLESS, ONE)
        return analyze(expr.function, inner)
    if isinstance(expr, sp.atan2):         # the angle of a vector: both components share a dimension, the result is an angle
        (dy, _), (dx, _) = analyze(expr.args[0], env), analyze(expr.args[1], env)
        if dy != dx:
            raise DimensionError(f"the arguments of atan2() must share one dimension, got [{dy}] and [{dx}] in {expr}")
        return DIMENSIONLESS, ONE
    arg = getattr(expr.func, "_sliderule_arg", None)
    if arg is not None:                    # a table lookup: the argument must have the dimension of the table's x column
        da, _ = analyze(expr.args[0], env)
        if da != arg[0]:
            raise DimensionError(f"the argument of {expr.func.__name__.split('_', 2)[-1]}() must be [{arg[0]}], got [{da}] in {expr}")
    res = getattr(expr.func, "_sliderule_result", None)
    if res is not None:                    # the numerical solution of a differential equation: its arguments were checked when it was built
        return res
    if isinstance(expr, sp.Function) or expr.is_Function:
        for a in expr.args:
            d, _ = analyze(a, env)
            if not d.is_dimensionless:
                raise DimensionError(f"argument of {expr.func.__name__}() must be dimensionless, got [{d}] in {expr}")
        return DIMENSIONLESS, ONE
    raise DimensionError(f"unsupported expression type {type(expr).__name__} in {expr}")


def _check_condition(cond: sp.Basic, env) -> None:
    if cond in (sp.true, sp.false):
        return
    if isinstance(cond, Relational):
        (dl, _), (dr, _) = analyze(cond.lhs, env), analyze(cond.rhs, env)
        if cond.lhs == 0 or cond.rhs == 0:  # comparing with literal zero is dimension-agnostic
            return
        if dl != dr:
            raise DimensionError(f"condition {cond} compares [{dl}] with [{dr}]")
        return
    for a in cond.args:
        _check_condition(a, env)


def check_equation(lhs: sp.Expr, rhs: sp.Expr, env) -> Dimension:
    dl, _ = analyze(lhs, env)
    dr, _ = analyze(rhs, env)
    if dl != dr:
        raise DimensionError(f"equation {lhs} = {rhs} is not dimensionally homogeneous: [{dl}] vs [{dr}]")
    return dl
