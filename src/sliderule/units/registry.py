"""Unit registry: parse unit expressions, resolve prefixes, convert, classify unit systems."""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache

from .dimension import DIMENSIONLESS, Dimension, compose

# Unit systems. "any" = no system preference (time, angle, electrical, dimensionless).
# "oilfield" = conventional mixed units (cP, mD, bbl) that legitimately appear next to USC and metric.
SYSTEMS = ("SI", "metric", "USC", "oilfield", "any")

# Deliberately excludes h (hecto), d (deci), da (deca): they collide with hour/day/darcy.
PREFIXES: dict[str, float] = {
    "Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3,
    "c": 1e-2, "m": 1e-3, "µ": 1e-6, "μ": 1e-6, "u": 1e-6, "n": 1e-9, "p": 1e-12,
    "f": 1e-15, "a": 1e-18, "z": 1e-21, "y": 1e-24,
}

# Bare names that are too ambiguous to guess at.
AMBIGUOUS: dict[str, str] = {
    "lb": "pound is ambiguous: use 'lbm' (mass) or 'lbf' (force)",
    "ton": "ton is ambiguous: use 't' (metric tonne), 'ton_US' (2000 lbm) or 'ton_UK' (2240 lbm)",
    "oz": "ounce is ambiguous: use 'ozm' (mass) or 'ozf' (force)",
    "psia": "enter absolute pressure as 'psi'",
}


class UnitError(ValueError):
    """Raised for unparsable units, unknown units or dimension mismatches."""

    def __init__(self, message: str, code: str = "UNIT_ERROR"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class UnitDef:
    symbol: str
    dim: Dimension
    factor: float            # SI = (x + shift) * factor
    shift: float = 0.0
    system: str = "SI"
    prefixable: bool = False
    suggest: str = ""        # prefixes worth offering in UI dropdowns
    note: str = ""
    label: str = ""          # human-readable name
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Unit:
    """A resolved unit expression."""

    terms: tuple[tuple[str, Fraction], ...]
    dim: Dimension
    factor: float
    shift: float = 0.0
    systems: frozenset[str] = frozenset()
    notes: tuple[str, ...] = ()
    scale_literal: bool = False  # expression contained a bare numeric factor

    @property
    def symbol(self) -> str:
        return compose(self.terms) or "1"

    @property
    def is_affine(self) -> bool:
        return self.shift != 0.0

    @property
    def is_identity(self) -> bool:
        return self.factor == 1.0 and self.shift == 0.0

    def to_si(self, x: float) -> float:
        return (x + self.shift) * self.factor

    def from_si(self, y: float) -> float:
        return y / self.factor - self.shift

    def __str__(self) -> str:
        return self.symbol


# ---------------------------------------------------------------- parsing

_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+)|(?P<name>°[A-Za-z]*|%|[^\W\d][\w°µμΩÅΔ]*)|(?P<op>\*\*|[*/^()·+\-])|(?P<bad>.))"
)


@dataclass
class _Partial:
    terms: dict[str, Fraction] = field(default_factory=dict)
    factor: float = 1.0
    shift: float = 0.0
    dim: Dimension = DIMENSIONLESS
    systems: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    atoms: int = 0           # number of unit atoms combined (affine shift survives only for exactly one)
    literal: bool = False

    def mul(self, o: "_Partial", sign: int = 1) -> "_Partial":
        terms = dict(self.terms)
        for k, e in o.terms.items():
            terms[k] = terms.get(k, Fraction(0)) + sign * e
            if terms[k] == 0:
                del terms[k]
        f = self.factor * (o.factor if sign > 0 else 1.0 / o.factor)
        dim = self.dim * o.dim if sign > 0 else self.dim / o.dim
        return _Partial(terms, f, 0.0, dim, self.systems | o.systems, self.notes + o.notes,
                        self.atoms + o.atoms, self.literal or o.literal)

    def pow(self, p: Fraction) -> "_Partial":
        return _Partial({k: e * p for k, e in self.terms.items()}, self.factor ** float(p), 0.0,
                        self.dim ** p, set(self.systems), list(self.notes), self.atoms, self.literal)


class _Parser:
    def __init__(self, reg: "UnitRegistry", text: str, as_delta: bool):
        self.reg, self.text, self.as_delta = reg, text, as_delta
        self.toks: list[tuple[str, str]] = []
        pos = 0
        s = text.strip()
        if not s:
            raise UnitError("empty unit expression", "UNIT_PARSE")
        while pos < len(s):
            m = _TOKEN.match(s, pos)
            if not m or m.end() == pos:
                break
            pos = m.end()
            kind = m.lastgroup
            if kind == "bad":
                raise UnitError(
                    f"unexpected character {m.group('bad')!r} in unit {text!r} "
                    "(use '*' between units, e.g. 'N*m', not 'N m')", "UNIT_PARSE")
            self.toks.append((kind, m.group(kind)))
        self.i = 0

    def peek(self) -> tuple[str, str] | tuple[None, None]:
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self) -> tuple[str, str]:
        t = self.toks[self.i]
        self.i += 1
        return t

    def parse(self) -> _Partial:
        p = self.expr()
        if self.i != len(self.toks):
            raise UnitError(f"unexpected {self.peek()[1]!r} in unit {self.text!r} "
                            "(use '*' between units, e.g. 'N*m', not 'N m')", "UNIT_PARSE")
        return p

    def expr(self) -> _Partial:
        left = self.term()
        while self.peek()[1] in ("*", "·", "/"):
            op = self.take()[1]
            right = self.term()
            left = left.mul(right, -1 if op == "/" else 1)
        return left

    def term(self) -> _Partial:
        base = self.factor()
        if self.peek()[1] in ("^", "**"):
            self.take()
            return base.pow(self.exponent())
        return base

    def exponent(self) -> Fraction:
        k, v = self.peek()
        if v == "(":
            self.take()
            e = self._signed_number()
            if self.peek()[1] == "/":
                self.take()
                e = e / self._signed_number()
            if self.peek()[1] != ")":
                raise UnitError(f"missing ')' in exponent of {self.text!r}", "UNIT_PARSE")
            self.take()
            return e
        return self._signed_number()

    def _signed_number(self) -> Fraction:
        sign = 1
        while self.peek()[1] in ("-", "+"):  # '-' never tokenises (bad char) so handle via text
            sign = -sign if self.take()[1] == "-" else sign
        k, v = self.peek()
        if k != "num":
            raise UnitError(f"expected a number in exponent of {self.text!r}", "UNIT_PARSE")
        self.take()
        return sign * Fraction(v)

    def factor(self) -> _Partial:
        k, v = self.peek()
        if k is None:
            raise UnitError(f"unit {self.text!r} ends unexpectedly", "UNIT_PARSE")
        if v == "(":
            self.take()
            p = self.expr()
            if self.peek()[1] != ")":
                raise UnitError(f"missing ')' in unit {self.text!r}", "UNIT_PARSE")
            self.take()
            return p
        if k == "num":
            self.take()
            return _Partial(factor=float(v), literal=True)
        if k == "name":
            self.take()
            return self.reg._atom(v, self.as_delta)
        raise UnitError(f"unexpected {v!r} in unit {self.text!r}", "UNIT_PARSE")


_NORM_PREFIX = {"u": "µ", "μ": "µ"}


class UnitRegistry:
    def __init__(self) -> None:
        self._defs: dict[str, UnitDef] = {}
        self._canonical: list[UnitDef] = []
        self._compounds: list[str] = []
        self._named_si: list[tuple[str, str]] = []   # (kind, si unit expression)

    # ---- registration
    def add(self, d: UnitDef) -> None:
        for name in (d.symbol, *d.aliases):
            if name in self._defs:
                raise ValueError(f"duplicate unit name {name!r}")
            self._defs[name] = d
        self._canonical.append(d)

    def define(self, names: str, expr: str, system: str = "SI", prefixable: bool = False,
               suggest: str = "", note: str = "", label: str = "", shift: float = 0.0) -> None:
        """Define a unit as a multiple of an already-defined expression, e.g. ``psi = 1 lbf/in^2``."""
        sym, *aliases = [n.strip() for n in names.split("|")]
        p = _Parser(self, expr, False).parse()
        self.add(UnitDef(sym, p.dim, p.factor, shift, system, prefixable, suggest, note, label,
                         tuple(aliases)))

    def define_base(self, sym: str, dim: Dimension, factor: float = 1.0, system: str = "SI",
                    prefixable: bool = True, suggest: str = "", label: str = "") -> None:
        self.add(UnitDef(sym, dim, factor, 0.0, system, prefixable, suggest, label=label))

    # ---- resolution
    def _atom(self, name: str, as_delta: bool) -> _Partial:
        d, pre, mult = self._resolve(name)
        if d.shift and pre:
            raise UnitError(f"prefixes cannot be applied to temperature scale {d.symbol!r}", "UNIT_PREFIX")
        shift = 0.0 if as_delta else d.shift
        sym = ("Δ" if (d.shift and as_delta) else "") + _NORM_PREFIX.get(pre, pre) + d.symbol
        notes = [d.note] if d.note else []
        return _Partial({sym: Fraction(1)}, d.factor * mult, shift, d.dim, {d.system}, notes, 1)

    def _resolve(self, name: str) -> tuple[UnitDef, str, float]:
        d = self._defs.get(name)
        if d:
            return d, "", 1.0
        if name in AMBIGUOUS:
            raise UnitError(f"{name!r}: {AMBIGUOUS[name]}", "UNIT_AMBIGUOUS")
        # SI prefix + unit (prefer the longest known remainder)
        for i in (1, 2):
            pre, rest = name[:i], name[i:]
            if pre in PREFIXES and rest in self._defs and self._defs[rest].prefixable:
                return self._defs[rest], pre, PREFIXES[pre]
        # 'm2' / 'ft3' shorthand for squares and cubes is intentionally NOT supported:
        # silently reinterpreting digits is the kind of convenience that causes unit bugs.
        hint = difflib.get_close_matches(name, list(self._defs), n=3, cutoff=0.6)
        msg = f"unknown unit {name!r}"
        if re.search(r"\d$", name):
            suggestion = re.sub(r"(\d+)$", r"^\1", name)
            msg += f" (write exponents with '^', e.g. {suggestion!r})"
        elif hint:
            msg += f" (did you mean {', '.join(repr(h) for h in hint)}?)"
        raise UnitError(msg, "UNIT_UNKNOWN")

    # ---- public API
    @lru_cache(maxsize=4096)
    def parse(self, expr: str, as_delta: bool = False) -> Unit:
        """Parse a unit expression. With ``as_delta`` temperature scales are treated as differences."""
        expr = expr.strip()
        if expr in ("", "1", "-", "dimensionless"):
            return Unit((), DIMENSIONLESS, 1.0, 0.0, frozenset({"any"}))
        p = _Parser(self, expr, as_delta).parse()
        return Unit(tuple(p.terms.items()), p.dim, p.factor, p.shift, frozenset(p.systems),
                    tuple(dict.fromkeys(p.notes)), p.literal)

    def convert(self, value: float, src: str | Unit, dst: str | Unit) -> float:
        a = self.parse(src) if isinstance(src, str) else src
        b = self.parse(dst) if isinstance(dst, str) else dst
        if a.dim != b.dim:
            raise UnitError(f"cannot convert {a.symbol} ({self.describe(a.dim)}) to {b.symbol} "
                            f"({self.describe(b.dim)})", "DIM_MISMATCH")
        return b.from_si(a.to_si(value))

    def system_of(self, u: Unit) -> frozenset[str]:
        return u.systems

    # ---- naming helpers
    def add_kind(self, kind: str, si_expr: str) -> None:
        self._named_si.append((kind, si_expr))

    def add_compound(self, expr: str) -> None:
        self._compounds.append(expr)

    @lru_cache(maxsize=None)
    def _kind_table(self) -> dict[Dimension, list[tuple[str, str]]]:
        table: dict[Dimension, list[tuple[str, str]]] = {}
        for kind, si in self._named_si:
            table.setdefault(self.parse(si).dim, []).append((kind, si))
        return table

    def kinds(self, dim: Dimension) -> list[str]:
        return [k for k, _ in self._kind_table().get(dim, [])]

    def describe(self, dim: Dimension) -> str:
        ks = self.kinds(dim)
        if ks:
            return ks[0]
        return "dimensionless" if dim.is_dimensionless else str(dim)

    def si_symbol(self, dim: Dimension) -> str:
        """Preferred coherent-SI unit string for a dimension (e.g. kg*m/s^2 -> N)."""
        row = self._kind_table().get(dim)
        if row:
            return row[0][1]
        return compose(dim.items()) or "1"

    def units_for(self, dim: Dimension, delta: bool = False) -> list[dict]:
        """Units of a given dimension for UI pickers, SI first."""
        out: list[dict] = []
        seen: set[str] = set()

        def push(sym: str, system: str, label: str = "", note: str = "") -> None:
            if sym not in seen:
                seen.add(sym)
                out.append({"symbol": sym, "system": system, "label": label, "note": note})

        si = self.si_symbol(dim)
        for d in self._canonical:
            if d.dim != dim:
                continue
            if delta and d.shift:
                continue
            if not delta and d.symbol.startswith("Δ"):
                continue
            push(d.symbol, d.system, d.label, d.note)
            for pre in d.suggest:
                push(pre + d.symbol, d.system, d.label, d.note)
        for expr in self._compounds:
            u = self.parse(expr, as_delta=delta)
            if u.dim == dim:
                push(expr, "/".join(sorted(u.systems - {"any"})) or "any")
        order = {"SI": 0, "metric": 1, "oilfield": 2, "USC": 3, "any": 1}
        out.sort(key=lambda r: (r["symbol"] != si, order.get(r["system"].split("/")[0], 4)))
        return out

    def all_units(self) -> list[dict]:
        return [
            {"symbol": d.symbol, "aliases": list(d.aliases), "label": d.label, "system": d.system,
             "prefixable": d.prefixable, "note": d.note,
             "dimension": self.describe(d.dim), "factor_to_si": d.factor, "shift": d.shift}
            for d in self._canonical
        ]


@lru_cache(maxsize=1)
def default_registry() -> UnitRegistry:
    from . import defs

    reg = UnitRegistry()
    defs.populate(reg)
    return reg


def convert(value: float, src: str, dst: str) -> float:
    return default_registry().convert(value, src, dst)


def parse_unit(expr: str, as_delta: bool = False) -> Unit:
    return default_registry().parse(expr, as_delta)


def is_finite(x: float) -> bool:
    return not (math.isnan(x) or math.isinf(x))
