"""Bridges between units and sympy/LaTeX: unit expressions as sympy products, number formatting."""

from __future__ import annotations

import math
from fractions import Fraction

import sympy as sp

from ..units import Dimension, Unit

_BASE_SYMBOL = {"cur": "USD"}


def usym(name: str) -> sp.Symbol:
    return sp.Symbol(name, positive=True)


def unit_expr_of(u: Unit) -> sp.Expr:
    e: sp.Expr = sp.Integer(1)
    for sym, p in u.terms:
        e *= usym(sym) ** sp.Rational(p.numerator, p.denominator)
    return e


def base_expr_of(dim: Dimension) -> sp.Expr:
    e: sp.Expr = sp.Integer(1)
    for b, p in dim.items():
        e *= usym(_BASE_SYMBOL.get(b, b)) ** sp.Rational(p.numerator, p.denominator)
    return e


def sym_tex(sym: str) -> str:
    t = (sym.replace("µ", r"\mu ").replace("Ω", r"\Omega ").replace("°", r"^{\circ}")
            .replace("Δ", r"\Delta ").replace("%", r"\%").replace("_", r"\_"))
    return r"\mathrm{%s}" % t


def expr_tex(e: sp.Expr) -> str:
    """LaTeX for a unit expression (free symbols are unit names)."""
    names = {s: sym_tex(s.name) for s in e.free_symbols}
    return sp.latex(e, symbol_names=names, mul_symbol="dot", fold_short_frac=False)


def unit_tex(u: Unit | str) -> str:
    from ..units import parse_unit

    if isinstance(u, str):
        u = parse_unit(u, as_delta=True)
    return expr_tex(unit_expr_of(u)) if u.terms else ""


def fmt_number(x: float, sig: int = 5) -> tuple[str, str]:
    """Return ``(plain, latex)`` for a number at ``sig`` significant figures."""
    if x == 0:
        return "0", "0"
    if not math.isfinite(x):
        return str(x), str(x)
    m, e = f"{x:.{sig - 1}e}".split("e")
    exp = int(e)
    if -3 <= exp < 6:
        s = f"{x:.{max(sig - 1 - exp, 0)}f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s, s
    m = m.rstrip("0").rstrip(".") if "." in m else m
    return f"{m}e{exp}", rf"{m}\times10^{{{exp}}}"


def quantity_tex(x: float, unit: Unit | str, sig: int = 5) -> str:
    _, n = fmt_number(x, sig)
    u = unit_tex(unit)
    return rf"{n}\,{u}" if u else n


def frac(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"
