"""One-dimensional root finding for numerical inversion: find x with f(x) = 0 when f can only be evaluated, not rearranged.

* :func:`brent` — Brent's method (bisection safety, secant/inverse-quadratic speed) on a bracket where f changes sign.
* :func:`find_bracket` — scan a grid (log-spaced for positive ranges) for the first sign change.

``f`` may raise ``ArithmeticError``/``ValueError``/``OverflowError`` where it is undefined; such grid points are skipped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable

Fn = Callable[[float], float]
_BAD = (ArithmeticError, ValueError, OverflowError)


@dataclass
class Root:
    x: float
    residual: float
    evaluations: int
    bracket: tuple[float, float]
    converged: bool


class NoBracket(ValueError):
    pass


def brent(f: Fn, a: float, b: float, fa: float | None = None, fb: float | None = None, xtol: float = 1e-14, rtol: float = 4e-15, maxiter: int = 200) -> Root:
    n = 0
    if fa is None:
        fa = f(a)
        n += 1
    if fb is None:
        fb = f(b)
        n += 1
    if fa == 0:
        return Root(a, 0.0, n, (a, b), True)
    if fb == 0:
        return Root(b, 0.0, n, (a, b), True)
    if (fa < 0) == (fb < 0):
        raise NoBracket("f has the same sign at both ends of the interval")
    lo, hi = a, b
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa
    c, fc = a, fa
    d = e = b - a
    for _ in range(maxiter):
        if (fb > 0) == (fc > 0):
            c, fc = a, fa
            d = e = b - a
        if abs(fc) < abs(fb):
            a, b, c = b, c, b
            fa, fb, fc = fb, fc, fb
        tol = 2 * rtol * abs(b) + 0.5 * xtol
        m = 0.5 * (c - b)
        if abs(m) <= tol or fb == 0:
            return Root(b, fb, n, (lo, hi), True)
        if abs(e) < tol or abs(fa) <= abs(fb):
            d = e = m
        else:
            s = fb / fa
            if a == c:
                p, q = 2 * m * s, 1 - s
            else:
                q, r = fa / fc, fb / fc
                p = s * (2 * m * q * (q - r) - (b - a) * (r - 1))
                q = (q - 1) * (r - 1) * (s - 1)
            if p > 0:
                q = -q
            p = abs(p)
            if 2 * p < min(3 * m * q - abs(tol * q), abs(e * q)):
                e, d = d, p / q
            else:
                d = e = m
        a, fa = b, fb
        b += d if abs(d) > tol else math.copysign(tol, m)
        fb = f(b)
        n += 1
    return Root(b, fb, n, (lo, hi), False)


def grid(lo: float, hi: float, points: int) -> list[float]:
    """``points`` values from lo to hi: geometric when both are positive and span more than a decade, linear otherwise."""
    if points < 2 or lo == hi:
        return [lo]
    if lo > 0 and hi / lo > 10:
        r = (hi / lo) ** (1 / (points - 1))
        return [lo * r ** i for i in range(points)]
    return [lo + (hi - lo) * i / (points - 1) for i in range(points)]


def brackets(f: Fn, xs: Iterable[float]):
    """Every adjacent pair of grid points where f changes sign (or touches zero), in order: yields ``(a, b, fa, fb, evaluations_so_far)``.

    A sign change is not always a root (a pole, a jump), so the caller may reject one and ask for the next.
    """
    prev = None
    n = 0
    for x in xs:
        try:
            fx = f(x)
        except _BAD:
            prev = None
            n += 1
            continue
        n += 1
        if not math.isfinite(fx):
            prev = None
            continue
        if fx == 0:
            yield x, x, 0.0, 0.0, n
            prev = (x, fx)
            continue
        if prev is not None and prev[1] != 0 and (prev[1] < 0) != (fx < 0):
            yield prev[0], x, prev[1], fx, n
        prev = (x, fx)


def find_bracket(f: Fn, xs: Iterable[float]) -> tuple[float, float, float, float, int]:
    """First adjacent pair of grid points where f changes sign (or touches zero). Returns ``(a, b, fa, fb, evaluations)``."""
    n = 0
    for br in brackets(f, xs):
        return br
    raise NoBracket("no sign change found")
