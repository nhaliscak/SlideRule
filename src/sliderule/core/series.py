"""Infinite sums: ``summation(term, (n, 1, oo))``.

A series is evaluated numerically, and only when the evidence says the answer is right:

1. The terms are added directly (up to 20 000 of them). If they have shrunk to nothing by then (geometric, exponential and factorial decay, fast Fourier series), the
   partial sum is the answer.
2. Otherwise the series converges slowly (a ``1/n²`` tail) or conditionally (``sin(n)/n``), and a direct sum would be wrong in the 4th digit. Three different
   acceleration methods from mpmath (Richardson + Shanks, Euler–Maclaurin, alternating-series) are tried and the value is accepted only where two of them agree to
   1e-7 relative; for a series of non-negative terms it must also not be smaller than the partial sum already added (so the harmonic series, which Richardson will
   happily "sum" to a finite number, is rejected). Where nothing can be established the series is reported as not converging to a number the program can trust.
3. A series whose terms do not die away (``n``, ``2**n``, ``(-1)**n * n``) is rejected outright.
"""

from __future__ import annotations

import math

import mpmath as mp
import sympy as sp

NMAX = 20000
_CACHE: dict = {}


def _terms(term: sp.Expr, n: sp.Symbol, lo: int):
    from .special import fast_lambdify

    f = fast_lambdify([n], term)
    out = []
    for k in range(lo, lo + NMAX):
        try:
            out.append(float(f(k)))
        except OverflowError:
            raise ArithmeticError("the series diverges: its terms grow without bound") from None
        except (ValueError, ZeroDivisionError, TypeError) as exc:
            raise ArithmeticError(f"a term of the series cannot be evaluated at n = {k}: {exc}") from None
        if not math.isfinite(out[-1]):
            raise ArithmeticError(f"a term of the series is not finite at n = {k}")
        if len(out) % 250 == 0 and _vanished(out):
            break                                                  # the terms are already negligible: no need for 20 000 of them
    return out


def _vanished(a: list[float]) -> bool:
    partial = math.fsum(a)
    return _window(a, len(a)) <= 1e-18 * max(abs(partial), 1e-300) and _window(a, len(a)) <= _window(a, len(a) - 200) + 0.0


def _window(a: list[float], end: int, width: int = 200) -> float:
    return max(abs(x) for x in a[max(0, end - width):end])


def evaluate(total: sp.Sum, values: dict) -> float:
    """The value of an infinite sum with the given values of its other symbols."""
    (n, lo, hi), = total.limits
    if hi is not sp.oo or not lo.is_Integer:
        raise ArithmeticError("only sums to +oo with a whole-number start are infinite sums")
    term = total.function.xreplace({s: sp.Float(v, 20) for s, v in values.items() if s in total.function.free_symbols})
    if term.free_symbols - {n}:
        raise ArithmeticError(f"the series needs values for {', '.join(sorted(map(str, term.free_symbols - {n})))}")
    if term.has(sp.Sum):
        raise ArithmeticError("a sum nested inside an infinite sum is not supported")
    key = (term, int(lo))
    hit = _CACHE.get(key)
    if hit is None:
        if len(_CACHE) > 256:
            _CACHE.clear()
        try:
            hit = _CACHE[key] = _sum(term, n, int(lo))
        except ArithmeticError as exc:
            hit = _CACHE[key] = str(exc)        # a refusal is remembered too: root-finding asks about the same series again and again
    if isinstance(hit, str):
        raise ArithmeticError(hit)
    return hit


def _sum(term: sp.Expr, n: sp.Symbol, lo: int) -> float:
    a = _terms(term, n, lo)
    partial = math.fsum(a)
    tail = _window(a, len(a))
    if tail <= 1e-18 * max(abs(partial), 1e-300) or tail == 0.0:
        return partial                                                   # the terms have vanished: nothing left to add
    # terms must be dying away on the scale of the data (a window of 200, one decade apart)
    if not tail < _window(a, len(a) // 10) * 0.999:
        raise ArithmeticError("the series diverges: its terms do not tend to zero")
    candidates = []
    f = sp.lambdify(n, term, "mpmath")
    mp.mp.dps = 25
    for method in ("r+s", "e", "a"):
        try:
            candidates.append(float(mp.nsum(f, [lo, mp.inf], method=method)))
        except Exception:                                                # a method may simply not apply (Euler–Maclaurin on an oscillating term ...)
            continue
    nonneg = min(a) >= 0.0
    agreed = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            x, y = candidates[i], candidates[j]
            if abs(x - y) <= 1e-7 * max(abs(x), abs(y), 1e-300):
                agreed.append(0.5 * (x + y))
    for v in agreed:
        if nonneg and v < partial - 1e-9 * abs(partial):
            continue                                                     # the sum of non-negative terms cannot be less than a partial sum
        return v
    raise ArithmeticError("the series converges too slowly (or conditionally) for its sum to be established reliably; "
                          "sum a finite number of terms and add an estimate of the tail, or rewrite the series")


def infinite_sums(expr: sp.Basic) -> list[sp.Sum]:
    return [s for s in expr.atoms(sp.Sum) if s.limits and s.limits[0][2] is sp.oo]
