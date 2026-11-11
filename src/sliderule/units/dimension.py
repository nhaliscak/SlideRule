"""Dimensional analysis: a dimension is a vector of rational exponents over base dimensions.

Exponents are ``Fraction`` so that things like Manning's roughness (s/m^(1/3)) stay exact.
This is the same idea as a state-space "units vector" in control/EE work: multiplying
quantities adds vectors, raising to a power scales them, and two quantities may only be
added or equated when their vectors are identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Mapping

# Seven SI base dimensions plus a pseudo-dimension for money (needed for industrial engineering).
BASE_DIMS: tuple[str, ...] = ("kg", "m", "s", "A", "K", "mol", "cd", "cur")


def _frac(x: int | float | str | Fraction) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, float):
        return Fraction(x).limit_denominator(1000)
    return Fraction(x)


@dataclass(frozen=True)
class Dimension:
    exps: tuple[Fraction, ...] = (Fraction(0),) * len(BASE_DIMS)

    @classmethod
    def of(cls, **kwargs: int | float | str | Fraction) -> "Dimension":
        bad = set(kwargs) - set(BASE_DIMS)
        if bad:
            raise KeyError(f"unknown base dimension(s): {sorted(bad)}")
        return cls(tuple(_frac(kwargs.get(b, 0)) for b in BASE_DIMS))

    @classmethod
    def from_mapping(cls, m: Mapping[str, Fraction]) -> "Dimension":
        return cls.of(**dict(m))

    def __mul__(self, other: "Dimension") -> "Dimension":
        return Dimension(tuple(a + b for a, b in zip(self.exps, other.exps)))

    def __truediv__(self, other: "Dimension") -> "Dimension":
        return Dimension(tuple(a - b for a, b in zip(self.exps, other.exps)))

    def __pow__(self, p: int | float | str | Fraction) -> "Dimension":
        p = _frac(p)
        return Dimension(tuple(a * p for a in self.exps))

    @property
    def is_dimensionless(self) -> bool:
        return not any(self.exps)

    def items(self) -> Iterable[tuple[str, Fraction]]:
        return ((b, e) for b, e in zip(BASE_DIMS, self.exps) if e)

    def __str__(self) -> str:
        return compose(self.items()) or "1"


DIMENSIONLESS = Dimension()


def fmt_exp(e: Fraction) -> str:
    return str(e.numerator) if e.denominator == 1 else f"({e.numerator}/{e.denominator})"


_DISPLAY = {"cur": "USD"}


def compose(terms: Iterable[tuple[str, Fraction]]) -> str:
    """Render ``[(symbol, exponent), ...]`` as a parseable unit string like ``kg/(m*s^2)``."""
    num: list[str] = []
    den: list[str] = []
    for sym, e in terms:
        sym = _DISPLAY.get(sym, sym)
        target, mag = (num, e) if e > 0 else (den, -e)
        target.append(sym if mag == 1 else f"{sym}^{fmt_exp(mag)}")
    if not num and not den:
        return ""
    top = "*".join(num) if num else "1"
    if not den:
        return top
    bottom = "*".join(den)
    return f"{top}/{bottom}" if len(den) == 1 else f"{top}/({bottom})"
