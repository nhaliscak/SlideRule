"""Derivatives and definite integrals inside equations.

An equation may be written with ``diff(f, t)``, ``diff(f, t, 2)`` and ``integrate(f, (x, a, b))``. They are kept unevaluated
long enough to be shown "as written" and dimension-checked (d^n f/dx^n has the units of f/x^n; an integral gains the units
of its variable), then evaluated symbolically so that the rest of the engine, which rearranges and evaluates *algebraic*
equations, works unchanged. An integral SymPy cannot do by textbook methods is kept and integrated numerically when the equation
is evaluated (so that quantity can be found but not rearranged for), and evaluation obeys the user's time limit (``sliderule.settings``) so a hard integrand cannot hang the program.
"""

from __future__ import annotations

import sympy as sp

from .. import settings
from .timeout import TimeLimitExceeded, time_limit

class CalculusError(ValueError):
    pass


def plain_integrals(expr: sp.Basic) -> sp.Basic:
    """SymPy marks integrals it gave up on as NonElementaryIntegral, which its numeric evaluator does not recognise: use the plain class."""
    return expr.replace(lambda e: isinstance(e, sp.Integral) and type(e) is not sp.Integral, lambda e: sp.Integral(*e.args))


def has_calculus(expr: sp.Basic) -> bool:
    return expr.has(sp.Derivative) or expr.has(sp.Integral) or expr.has(sp.Sum)


def evaluate(expr: sp.Basic, limited: bool = True) -> tuple[sp.Basic, bool]:
    """Evaluate every derivative and definite integral in ``expr`` in closed form where possible.

    Returns ``(expression, numeric)``. A definite integral with no closed form stays in the expression (``numeric`` is True): the
    engine integrates it numerically (adaptive quadrature) once the other quantities have values. Derivatives must always be closed form.

    ``limited``: obey the user's time limit. The built-in library passes False (it is trusted, and a small limit must not stop the catalog loading)."""
    for d in expr.atoms(sp.Derivative):
        for var, _n in d.variable_count:
            if var not in d.expr.free_symbols:
                raise CalculusError(f"{d.expr} does not depend on {var}, so its derivative with respect to {var} is zero; "
                                    f"write the quantity as an explicit expression of {var}")
    # a sum is kept as a sum (evaluated term by term when the numbers are known): expanding fifty terms symbolically would only slow everything down
    held: dict = {}
    for k, s in enumerate(sorted(expr.atoms(sp.Sum), key=str)):
        if s.function.has(sp.Derivative) or s.function.has(sp.Integral):
            raise CalculusError("derivatives and integrals inside a sum are not supported")
        held[s] = sp.Symbol(f"_sum{k}")
    try:
        with time_limit(settings.limit() if limited else None):
            out = expr.xreplace(held).doit(manual=True).xreplace({v: k for k, v in held.items()})
    except TimeLimitExceeded as exc:
        raise CalculusError(f"evaluating the derivative/integral took longer than {exc.seconds:g} s; simplify the integrand, write its closed form "
                            "directly, or raise the time limit in Settings") from None
    out = plain_integrals(out)
    if out.has(sp.Derivative):
        raise CalculusError("cannot evaluate this derivative in closed form")
    if out.xreplace({t: sp.Integer(0) for t in out.atoms(sp.Sum)}).has(sp.zoo, sp.nan, sp.oo, -sp.oo):
        raise CalculusError("the derivative/integral is undefined or infinite (check the limits)")
    return out, out.has(sp.Integral) or out.has(sp.Sum)
