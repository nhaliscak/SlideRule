"""Tabulated data in equations: ``pump_curve(Q)`` looks a value up in a table of measured or published points and interpolates.

A calculation lists its tables (name, x and y units, the points, an interpolation method); each becomes a SymPy function usable in any equation, ODE or
integral. The function is differentiable (so Newton iterations and sensitivity work), is dimension-checked (the argument must have the dimension of the
table's x column; the value has that of the y column) and, because it cannot be rearranged symbolically, is inverted numerically when the unknown sits
inside it (the operating point where a pump curve meets a system curve, say).

Interpolation: ``linear`` (straight lines between points), ``pchip`` (monotone cubic: smooth, never overshoots the data) or ``loglog`` (straight lines on
log-log axes, the usual form for power-law data such as S-N curves; needs positive values).
Outside the tabulated range: ``error`` (default: the answer is outside the data, so no answer), ``clamp`` (hold the end value) or ``extrapolate``
(continue the end segment).
"""

from __future__ import annotations

import hashlib
import inspect
import math
from typing import Any

import numpy as np
import sympy as sp
from scipy.interpolate import PchipInterpolator

METHODS = ("linear", "pchip", "loglog")
OUTSIDE = ("error", "clamp", "extrapolate")
MAX_POINTS = 500

#: callables for the fast ``lambdify`` paths, by function name (names are derived from the data, so equal names mean equal tables)
REGISTRY: dict[str, Any] = {}


class TableError(ValueError):
    pass


def check_data(xs, ys, method: str, outside: str) -> tuple[list[float], list[float]]:
    if method not in METHODS:
        raise TableError(f"interpolation must be one of {', '.join(METHODS)}")
    if outside not in OUTSIDE:
        raise TableError(f"'outside' must be one of {', '.join(OUTSIDE)}")
    if not isinstance(xs, (list, tuple)) or not isinstance(ys, (list, tuple)) or len(xs) != len(ys):
        raise TableError("x and y must be lists with the same number of points")
    if not 2 <= len(xs) <= MAX_POINTS:
        raise TableError(f"a table needs 2 to {MAX_POINTS} points")
    try:
        x, y = [float(v) for v in xs], [float(v) for v in ys]
    except (TypeError, ValueError):
        raise TableError("the table entries must be numbers") from None
    if not all(math.isfinite(v) for v in x + y):
        raise TableError("the table entries must be finite numbers")
    if any(b <= a for a, b in zip(x, x[1:])):
        raise TableError("the x values must increase strictly (sort the points and remove duplicates)")
    if method == "loglog" and (min(x) <= 0 or min(y) <= 0):
        raise TableError("log-log interpolation needs positive x and y values")
    return x, y


def interpolator(xs, ys, method: str, outside: str):
    """``(f, df)``: the interpolant and its derivative as functions of one float, in the table's own (SI) numbers."""
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    lo, hi = float(x[0]), float(x[-1])
    lx, ly = (np.log(x), np.log(y)) if method == "loglog" else (x, y)
    spline = PchipInterpolator(x, y) if method == "pchip" else None
    slopes = np.diff(ly) / np.diff(lx)

    def inside(v: float):
        """(value, slope) at v within [lo, hi] (or extrapolated along the end segment)."""
        if method == "pchip" and lo <= v <= hi:
            return float(spline(v)), float(spline(v, 1))
        k = int(np.clip(np.searchsorted(x, v) - 1, 0, len(x) - 2))
        if method == "loglog":
            s = slopes[k]
            val = math.exp(ly[k] + s * (math.log(v) - lx[k]))
            return val, s * val / v
        s = slopes[k]
        return float(y[k] + s * (v - x[k])), float(s)

    def both(v: float):
        v = float(v)
        if not math.isfinite(v):
            raise ArithmeticError("the table was asked for a value that is not a finite number")
        if v < lo or v > hi:
            if outside == "error":
                raise ArithmeticError(f"{v:.6g} is outside the tabulated range {lo:.6g} to {hi:.6g}")
            if outside == "clamp":
                return float(y[0] if v < lo else y[-1]), 0.0
            if method == "pchip":                  # continue the end tangent
                edge = lo if v < lo else hi
                val, s = float(spline(edge)), float(spline(edge, 1))
                return val + s * (v - edge), s
            if method == "loglog" and v <= 0:
                raise ArithmeticError("log-log extrapolation needs a positive value")
        return inside(v)

    return (lambda v: both(v)[0]), (lambda v: both(v)[1])


def _fingerprint(xs, ys, method, outside) -> str:
    return hashlib.sha1(repr((tuple(xs), tuple(ys), method, outside)).encode()).hexdigest()[:10]


def make_functions(name: str, xs, ys, method: str, outside: str, value_result: tuple, slope_result: tuple, arg_dim, display: str | None = None):
    """The SymPy function classes ``(table, table_derivative)`` for one table (values and the argument in SI)."""
    f, df = interpolator(xs, ys, method, outside)
    uid = _fingerprint(xs, ys, method, outside)
    fname, dname = f"tbl_{uid}_{name}", f"tbl_{uid}_{name}__d"
    REGISTRY[fname], REGISTRY[dname] = f, df
    shown = display or name

    def evaluator(fn):
        def _eval_evalf(self, prec):
            if not getattr(self.args[0], "is_number", False):
                return None
            return sp.Float(fn(float(self.args[0])), 17)
        return _eval_evalf

    deriv = type(dname, (sp.Function,), {
        "nargs": 1, "_eval_evalf": evaluator(df), "_eval_is_real": lambda self: True, "_sliderule_result": slope_result, "_sliderule_arg": arg_dim,
        "_latex": lambda self, printer, *a, **k: rf"\mathrm{{{shown}}}'\left({printer._print(self.args[0])}\right)"})

    def fdiff(self, argindex=1):
        return deriv(self.args[0])

    func = type(fname, (sp.Function,), {
        "nargs": 1, "_eval_evalf": evaluator(f), "_eval_is_real": lambda self: True, "fdiff": fdiff, "_sliderule_result": value_result, "_sliderule_arg": arg_dim,
        "_sliderule_table": (name, tuple(xs), tuple(ys), method, outside),
        "_latex": lambda self, printer, *a, **k: rf"\mathrm{{{shown}}}\left({printer._print(self.args[0])}\right)"})
    return func, deriv


def script_support(tables: list[tuple[str, list[float], list[float], str, str]]) -> str:
    """Python source for a standalone exported script: the interpolator plus a definition of each table's function (SI numbers)."""
    parts = ["import math", "import numpy as np", "from scipy.interpolate import PchipInterpolator", ""]
    parts.append(inspect.getsource(interpolator))
    parts.append(inspect.getsource(_fingerprint))
    parts.append('''
def _table(name, xs, ys, method, outside):
    """A SymPy function that looks up (and differentiates) the table; evaluated numerically."""
    f, df = interpolator(xs, ys, method, outside)
    def ev(fn):
        return lambda self, prec: sp.Float(fn(float(self.args[0])), 17) if getattr(self.args[0], "is_number", False) else None
    d = type(name + "__d", (sp.Function,), {"nargs": 1, "_eval_evalf": ev(df), "_eval_is_real": lambda self: True})
    return type(name, (sp.Function,), {"nargs": 1, "_eval_evalf": ev(f), "_eval_is_real": lambda self: True, "fdiff": lambda self, argindex=1: d(self.args[0])})
''')
    for name, xs, ys, method, outside in tables:
        parts.append(f"NS[{name!r}] = _table({name!r}, {list(xs)!r}, {list(ys)!r}, {method!r}, {outside!r})")
    return "\n".join(parts)
