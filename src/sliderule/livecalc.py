"""LiveCalc: a unit-aware scratchpad calculator.

Each line of input is one statement, evaluated in order with the lines before it:

    5 m + 30 cm                  an expression (units are carried through and checked)
    120 km/h to m/s              a conversion (``to`` or ``in``)
    m = 5 kg                     a variable        F = m * 9.81 m/s^2     a variable computed from others
    f(x) = 3*x^2 - 2             a function         f(4)                   called later
    F = m*a                      an equation (while ``m`` or ``a`` have no value, nothing is evaluated)
    plot sin(x), cos(x) from 0 to 2*pi        a graph (the unknown name is the independent variable;
                                              ``plot 0.5*m*v^2 for v from 0 m/s to 20 m/s`` names it)

Anything that does not read as a calculation is returned as ``text`` so the front end can show it as Markdown.

There is no ``eval`` anywhere: the text is tokenised and parsed here, with limits on length, nesting and
number size, and the arithmetic is done on a small ``Q`` (quantity) type. Values are kept in SI base units
together with a *display* unit, so ``5 m + 30 cm`` prints as ``5.3 m`` and ``3 kN * 2 m`` as ``6 kN*m``.
"""

from __future__ import annotations

import itertools
import json
import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

import numpy as np

from .core.units_expr import fmt_number, unit_tex
from .units import DIMENSIONLESS, Dimension, Unit, UnitError, compose, default_registry

MAX_LINE = 400            # characters per line
MAX_LINES = 1500
MAX_ENTRIES = 200
MAX_TOKENS = 250          # tokens per statement
MAX_DEPTH = 40            # nesting of parentheses / powers
MAX_CALL_DEPTH = 20       # user functions calling user functions
PLOT_POINTS = 300
MAX_FACTORIAL = 170
MAX_LIST = 500             # values in a list

_NORMALISE = str.maketrans({"×": "*", "·": "*", "÷": "/", "−": "-", "–": "-", "²": "^2", "³": "^3", " ": " ", "“": '"', "”": '"'})
_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)"
    r"|(?P<id>(?:[^\W\d]|[°µμΩÅΔ])[\w°µμΩÅΔ]*)"
    r"|(?P<str>\"[^\"\n]*\"|'[^'\n]*')"
    r"|(?P<op>\*\*|[*/^()+\-,=\[\]:])"
    r"|(?P<bad>\S))"
)
_KEYWORDS = {"to", "from", "for", "plot"}
_MARKDOWN = re.compile(r"^\s*(#{1,6}\s|>|[-*+]\s|\d+[.)]\s|```|---|\*\*\*|\||!?\[[^\]\n]*\]\()")
GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu", "nu", "xi",
         "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi",
         "Pi", "Sigma", "Phi", "Psi", "Omega"}


class LiveError(ValueError):
    """The line reads as a calculation but cannot be evaluated."""


class SyntaxErr(LiveError):
    """The text does not read as an expression (so it may just be prose)."""


class Undefined(LiveError):
    """A name has no value, is not a unit and is not a function."""

    def __init__(self, name: str):
        super().__init__(f"‘{name}’ has no value yet")
        self.name = name


# ------------------------------------------------------------------ quantities

@dataclass(frozen=True)
class Q:
    """A value in SI base units (a float or, while plotting, a numpy array), its dimension and the unit to show it in."""

    v: Any
    dim: Dimension = DIMENSIONLESS
    unit: Unit | None = None

    @property
    def affine(self) -> bool:
        return self.unit is not None and self.unit.shift != 0.0

    @property
    def shown(self) -> Any:
        """The number in the display unit."""
        return self.v if self.unit is None else self.unit.from_si(self.v)


@dataclass
class Func:
    params: tuple[str, ...]
    body: tuple
    text: str


def _reg():
    return default_registry()


def _desc(dim: Dimension) -> str:
    return "a plain number" if dim.is_dimensionless else _reg().describe(dim) or str(dim)


_LITERAL = ("num", "qty", "unit", "imag")      # an expression that is just a written quantity has no working to show
_BASE_SYMBOLS = {"kg", "m", "s", "A", "K", "mol", "cd"}


def _tidy(u: Unit | None) -> Unit | None:
    """kg*m/s^2 (built from nothing but SI base units) is a newton: use the named unit. N*m, kN*m, m/s ... stay as written."""
    if u is None or u.factor != 1.0 or u.shift or not u.terms or any(sym not in _BASE_SYMBOLS for sym, _ in u.terms):
        return u
    if len(u.terms) < 2:         # m^2, 1/s ... stay as they are
        return u
    sym = _reg().si_symbol(u.dim)
    if re.fullmatch(r"[A-Za-zΩµ°]+", sym) and sym not in _BASE_SYMBOLS:
        try:
            return _reg().parse(sym)
        except UnitError:
            return u
    return u


def _terms_unit(terms: dict[str, Fraction], dim: Dimension, factor: float, systems: frozenset[str]) -> Unit | None:
    terms = {k: e for k, e in terms.items() if e}
    if not terms:
        return None
    return Unit(tuple(terms.items()), dim, factor, 0.0, systems)


def _merge(a: Unit | None, b: Unit | None, sign: int, dim: Dimension) -> Unit | None:
    """Unit of a*b (sign +1) or a/b (sign -1), kept symbolic so 5 m * 3 m shows m^2 and 10 m / 2 s shows m/s."""
    terms: dict[str, Fraction] = {}
    factor = 1.0
    systems: frozenset[str] = frozenset()
    for u, s in ((a, 1), (b, sign)):
        if u is None:
            continue
        for sym, p in u.terms:
            terms[sym] = terms.get(sym, Fraction(0)) + p * s
        factor *= u.factor if s == 1 else 1.0 / u.factor
        systems |= u.systems
    return _tidy(_terms_unit(terms, dim, factor, systems))


def _unit_pow(u: Unit | None, p: Fraction, dim: Dimension) -> Unit | None:
    if u is None:
        return None
    return _terms_unit({k: e * p for k, e in u.terms}, dim, u.factor ** float(p), u.systems)


def _real(x: Any) -> np.ndarray:
    """The values as a float array; complex numbers are refused with a reason rather than losing their imaginary part."""
    arr = np.asarray(x)
    if arr.dtype.kind == "c":
        raise LiveError("This needs real numbers: a complex value cannot be used here (use abs(), real() or imag() first)")
    return arr.astype(float, copy=False)


def _num(x: Any) -> np.ndarray:
    """The values as a float array, or a complex array if any is complex."""
    arr = np.asarray(x)
    return arr if arr.dtype.kind == "c" else arr.astype(float, copy=False)


def _demote(v: Any) -> Any:
    """A complex result whose imaginary part is exactly zero everywhere (5 + 0i, (2i)^2) is an ordinary real number again."""
    arr = np.asarray(v)
    if arr.dtype.kind == "c" and not np.any(arr.imag):
        return arr.real if arr.ndim else float(arr.real)
    return v


def _is_complex(q: "Q") -> bool:
    return np.asarray(q.v).dtype.kind == "c"


def _finite(v: Any, what: str = "the result") -> None:
    arr = np.asarray(v)
    if arr.ndim == 0 and not bool(np.isfinite(arr)):
        raise LiveError(f"{what} is not a finite number (division by zero, or a value too large?)")


def _no_affine(*qs: Q, op: str) -> None:
    for q in qs:
        if q.affine:
            raise LiveError(f"{q.unit.symbol} is an offset temperature scale and cannot be used with ‘{op}’: convert to K first, or work with temperature differences")


def add(a: Q, b: Q, sign: int) -> Q:
    if (a.affine or b.affine) and (_is_complex(a) or _is_complex(b)):
        raise LiveError("Complex numbers cannot be used with an offset temperature scale: convert to K first")
    if a.dim != b.dim:
        verb = "add" if sign > 0 else "subtract"
        raise LiveError(f"Cannot {verb} {_desc(a.dim)} ({a.unit.symbol if a.unit else 'no unit'}) and {_desc(b.dim)} ({b.unit.symbol if b.unit else 'no unit'})")
    v = a.v + sign * b.v
    if a.affine and b.affine:
        if sign > 0:
            raise LiveError(f"Cannot add two temperatures on the {a.unit.symbol} scale: add a temperature difference (K) instead")
        return Q(v, a.dim, _reg().parse("K"))
    unit = a.unit if a.unit is not None and not (b.affine and not a.affine) else b.unit
    if sign < 0 and b.affine and not a.affine:
        raise LiveError("A temperature difference minus a temperature on an offset scale makes no physical sense")
    _finite(v)
    return Q(v, a.dim, unit)                      # (not demoted: 5 + 0i is written as a complex number on purpose, e.g. sqrt(-4 + 0i))


def mul(a: Q, b: Q, sign: int = 1) -> Q:
    _no_affine(a, b, op="*" if sign > 0 else "/")
    if sign < 0 and np.any(np.asarray(b.v) == 0):
        raise LiveError("Division by zero")
    dim = a.dim * b.dim if sign > 0 else a.dim / b.dim
    v = a.v * b.v if sign > 0 else a.v / b.v
    _finite(v)
    return Q(_demote(v), dim, _merge(a.unit, b.unit, sign, dim))


def power(a: Q, b: Q) -> Q:
    if not b.dim.is_dimensionless or np.ndim(b.v) != 0:
        raise LiveError("An exponent must be a plain number")
    _no_affine(a, op="^")
    if _is_complex(b):                                                   # e^(j*x), (1+j)^(1+j): a complex exponent needs a plain-number base
        if not a.dim.is_dimensionless:
            raise LiveError("A quantity with units cannot be raised to a complex power")
        with np.errstate(all="ignore"):
            v = np.power(np.asarray(a.v).astype(complex), complex(b.v))
        _finite(v)
        return Q(_demote(v), DIMENSIONLESS, None)
    p = float(b.v)
    if not a.dim.is_dimensionless:
        fr = Fraction(p).limit_denominator(1000)
        if abs(float(fr) - p) > 1e-9:
            raise LiveError("A quantity with units can only be raised to a rational power (such as 2, 3 or 1/2)")
        dim, unit = a.dim ** fr, _unit_pow(a.unit, fr, a.dim ** fr)
    else:
        dim, unit = DIMENSIONLESS, None
        fr = None
    with np.errstate(all="ignore"):
        if _is_complex(a):
            v = _demote(np.power(np.asarray(a.v), p))
        else:
            v = np.power(_real(a.v), p) if np.ndim(a.v) else _scalar_pow(float(a.v), p)
    _finite(v)
    return Q(v, dim, unit)


def _scalar_pow(x: float, p: float) -> float:
    if x < 0 and not float(p).is_integer():
        raise LiveError("A negative number cannot be raised to a fractional power (the result is not real)")
    if x == 0 and p < 0:
        raise LiveError("Division by zero")
    try:
        return math.pow(x, p)
    except OverflowError:
        raise LiveError("The result is too large") from None


# ------------------------------------------------------------------ functions

def _dimless(q: Q, fn: str) -> np.ndarray:
    if not q.dim.is_dimensionless:
        raise LiveError(f"{fn}() needs a plain number or an angle, not {_desc(q.dim)}")
    return np.asarray(q.v) if _is_complex(q) else _real(q.v)


def _unary(fn, name, domain=None):
    def run(q: Q) -> Q:
        x = _dimless(q, name)
        if domain is not None and not _is_complex(q) and np.any(~domain(x)):
            raise LiveError(f"{name}() is not defined for that value")
        with np.errstate(all="ignore"):
            out = fn(x)
        res = Q(out if np.ndim(out) else (complex(out) if np.iscomplexobj(out) else float(out)))
        _finite(res.v)
        return res
    return run


def _root(n: int, name: str):
    def run(q: Q) -> Q:
        cplx = _is_complex(q)
        if cplx and n != 2:
            raise LiveError("cbrt() does not work with complex numbers")
        a = np.asarray(q.v) if cplx else _real(q.v)
        if n == 2 and not cplx and np.any(a < 0):
            raise LiveError("sqrt() of a negative number is not real (write it as a complex number, e.g. sqrt(-4 + 0i), if that is what you want)")
        with np.errstate(all="ignore"):
            v = np.sqrt(a) if n == 2 else np.cbrt(a)
        fr = Fraction(1, n)
        dim = q.dim ** fr
        res = Q(v if np.ndim(v) else (complex(v) if cplx else float(v)), dim, _unit_pow(q.unit, fr, dim))
        _no_affine(q, op=name)
        return res
    return run


def _shape(fn, name):
    """abs / floor / ceil / round keep dimension and unit."""
    def run(q: Q) -> Q:
        if fn is np.abs:
            v = np.abs(np.asarray(q.v))                       # the magnitude of a complex number
            return Q(v if np.ndim(v) else float(v), q.dim, q.unit)
        shown = _real(q.shown)
        out = fn(shown)
        si = q.unit.to_si(out) if q.unit is not None else out
        return Q(si if np.ndim(si) else float(si), q.dim, q.unit)
    return run


def _minmax(fn, name):
    def run(*qs: Q) -> Q:
        if not qs:
            raise LiveError(f"{name}() needs at least one value")
        for q in qs[1:]:
            if q.dim != qs[0].dim:
                raise LiveError(f"{name}() cannot compare {_desc(qs[0].dim)} with {_desc(q.dim)}")
        vals = [_real(q.v) for q in qs]
        out = vals[0]
        for t in vals[1:]:
            out = fn(out, t)
        return Q(out if np.ndim(out) else float(out), qs[0].dim, qs[0].unit)
    return run


def _atan2(y: Q, x: Q) -> Q:
    if y.dim != x.dim:
        raise LiveError("atan2() needs two values with the same units")
    return Q(np.arctan2(np.asarray(y.v, float), np.asarray(x.v, float)))


def _factorial(q: Q) -> Q:
    x = _dimless(q, "factorial")
    if np.ndim(x) or x < 0 or x != int(x) or x > MAX_FACTORIAL:
        raise LiveError(f"factorial() needs a whole number from 0 to {MAX_FACTORIAL}")
    return Q(float(math.factorial(int(x))))


def _round(q: Q) -> Q:
    return _shape(np.round, "round")(q)


def _stack(qs: tuple, name: str, same_unit_check: bool = True):
    if not qs:
        raise LiveError(f"{name}() needs at least one value")
    for q in qs[1:]:
        if q.dim != qs[0].dim:
            raise LiveError(f"{name}() cannot combine {_desc(qs[0].dim)} with {_desc(q.dim)}")
    return np.stack(np.broadcast_arrays(*[_num(q.v) for q in qs]))


def _agg(name: str, fn, affine_ok: bool, minimum: int = 1):
    """sum / mean / median / stdev of several values with the same dimension (the first value's unit is used for the result)."""
    def run(*qs: Q) -> Q:
        if len(qs) < minimum:
            raise LiveError(f"{name}() needs at least {minimum} values")
        if not affine_ok:
            _no_affine(*qs, op=name)
        out = fn(_stack(qs, name))
        res = Q(out if np.ndim(out) else np.asarray(out).item(), qs[0].dim, qs[0].unit)
        _finite(res.v)
        return res
    return run


def _hypot(*qs: Q) -> Q:
    st = _stack(qs, "hypot")
    _no_affine(*qs, op="hypot")
    out = np.sqrt(np.sum(np.abs(st) ** 2, axis=0))
    return Q(out if np.ndim(out) else float(out), qs[0].dim, qs[0].unit)


def _sign(q: Q) -> Q:
    out = np.sign(_real(q.v) - (q.unit.to_si(0.0) if q.affine else 0.0))
    return Q(out if np.ndim(out) else float(out))


def _mod(a: Q, b: Q) -> Q:
    if a.dim != b.dim:
        raise LiveError("mod() needs two values with the same units")
    _no_affine(a, b, op="mod")
    bv = _real(b.v)
    if np.any(bv == 0):
        raise LiveError("mod() by zero")
    out = np.mod(_real(a.v), bv)
    return Q(out if np.ndim(out) else float(out), a.dim, a.unit)


def _real_part(q: Q) -> Q:
    v = np.real(np.asarray(q.v))
    return Q(v if np.ndim(v) else float(v), q.dim, q.unit)


def _imag_part(q: Q) -> Q:
    v = np.imag(np.asarray(q.v))
    return Q(v if np.ndim(v) else float(v), q.dim, q.unit)


def _conj(q: Q) -> Q:
    v = np.conj(np.asarray(q.v))
    return Q(v if np.ndim(v) else v.item(), q.dim, q.unit)


def _arg(q: Q) -> Q:
    """The angle of a complex number in radians (from -pi to pi); ‘to deg’ converts."""
    v = np.angle(np.asarray(q.v))
    return Q(v if np.ndim(v) else float(v))


def _polar(mag: Q, ang: Q) -> Q:
    """polar(r, theta): the complex number r at angle theta (radians, or write 30 deg), keeping the unit of r."""
    if not ang.dim.is_dimensionless:
        raise LiveError("polar() needs the angle as a plain number or an angle such as 30 deg")
    if _is_complex(mag) or _is_complex(ang):
        raise LiveError("polar() takes real values")
    v = _real(mag.v) * np.exp(1j * _real(ang.v))
    return Q(v if np.ndim(v) else complex(v), mag.dim, mag.unit)


#: functions that accept complex arguments (everything else says so instead of dropping the imaginary part)
COMPLEX_OK = {"abs", "sqrt", "exp", "ln", "log", "log10", "log2", "sin", "cos", "tan", "sinh", "cosh", "tanh", "asin", "acos", "atan", "real", "imag", "conj", "arg", "sum", "mean", "prod",
              "len", "reverse", "cumsum", "transpose", "matmul", "det", "inv", "solve", "trace", "identity", "rows", "cols", "norm", "dot", "cross", "eigvals", "eigvecs", "hypot"}


def _needs_function(name: str):
    def run(*_qs: Q) -> Q:
        raise LiveError(f"{name}() works on a function you defined: first write f(x) = ..., then {name}(f, ...)")
    return run


def _vec(q: Q, name: str) -> np.ndarray:
    a = _num(q.v)
    if a.ndim != 1:
        raise LiveError(f"{name}() needs a list, for example {name}([1, 2, 3])")
    return a


def _same_list_dim(a: Q, b: Q, name: str) -> None:
    if a.dim != b.dim:
        raise LiveError(f"{name}() cannot combine {_desc(a.dim)} with {_desc(b.dim)}")


def _as_list(a: np.ndarray, like: Q, dim=None, unit=None) -> Q:
    if a.size > MAX_LIST * 2:
        raise LiveError(f"That list would have more than {MAX_LIST * 2} values")
    _finite(a)
    return Q(a, like.dim if dim is None else dim, like.unit if unit is None and dim is None else unit)


def _len(q: Q) -> Q:
    return Q(float(np.shape(q.v)[0]) if np.ndim(q.v) else 1.0)            # values of a list, rows of a matrix


def _mat(q: Q, name: str, square: bool = False) -> np.ndarray:
    a = _num(q.v)
    if a.ndim != 2:
        raise LiveError(f"{name}() needs a matrix, for example {name}([[1, 2], [3, 4]])")
    if square and a.shape[0] != a.shape[1]:
        raise LiveError(f"{name}() needs a square matrix, not {a.shape[0]} × {a.shape[1]}")
    return a


def _rows(q: Q) -> Q:
    return Q(float(_mat(q, "rows").shape[0]))


def _cols(q: Q) -> Q:
    return Q(float(_mat(q, "cols").shape[1]))


def _transpose(q: Q) -> Q:
    a = _num(q.v)
    if a.ndim == 0:
        raise LiveError("transpose() needs a list or a matrix")
    return Q(a.T.copy(), q.dim, q.unit)


def _identity(n: Q) -> Q:
    if not n.dim.is_dimensionless or np.ndim(n.v) or n.v != int(n.v) or not 1 <= n.v <= 22:
        raise LiveError("identity() needs a whole number of rows from 1 to 22")
    return Q(np.eye(int(n.v)), DIMENSIONLESS, None)


def _checked(a: np.ndarray, name: str) -> np.ndarray:
    if not np.all(np.isfinite(a)):
        raise LiveError(f"{name}() produced a value that is not finite")
    big = float(np.max(np.abs(a))) if np.size(a) else 0.0
    return np.where(np.abs(a) < 1e-13 * big, 0.0, a) if np.ndim(a) else a             # rounding noise such as -5.6e-17 beside a 1 is a zero


def _det(q: Q) -> Q:
    a = _mat(q, "det", square=True)
    _no_affine(q, op="det")
    n = Fraction(a.shape[0])
    return Q(np.linalg.det(a).item(), q.dim ** n, _unit_pow(q.unit, n, q.dim ** n))


def _trace(q: Q) -> Q:
    a = _mat(q, "trace", square=True)
    _no_affine(q, op="trace")
    return Q(np.trace(a).item(), q.dim, q.unit)


def _inv(q: Q) -> Q:
    a = _mat(q, "inv", square=True)
    _no_affine(q, op="inv")
    if abs(np.linalg.cond(a)) > 1e13:
        raise LiveError("inv() of a matrix that is singular (or nearly so)")
    dim = q.dim ** Fraction(-1)
    return Q(_checked(np.linalg.inv(a), "inv"), dim, _unit_pow(q.unit, Fraction(-1), dim))


def _matmul(a: Q, b: Q) -> Q:
    x, y = _num(a.v), _num(b.v)
    if x.ndim not in (1, 2) or y.ndim not in (1, 2):
        raise LiveError("matmul() needs lists or matrices")
    _no_affine(a, b, op="matmul")
    try:
        out = np.matmul(x, y)
    except ValueError:
        raise LiveError(f"matmul() cannot multiply {x.shape[0]}{'' if x.ndim == 1 else f' × {x.shape[1]}'} by {y.shape[0]}{'' if y.ndim == 1 else f' × {y.shape[1]}'}: the inner sizes differ") from None
    t = mul(Q(1.0, a.dim, a.unit), Q(1.0, b.dim, b.unit))
    return Q(_checked(out, "matmul") if np.ndim(out) else out.item(), t.dim, t.unit)


def _solve_linear(a: Q, b: Q) -> Q:
    """solve(A, b): the x with A x = b; the unit of x is the unit of b over that of A."""
    m = _mat(a, "solve", square=True)
    y = _num(b.v)
    if y.ndim not in (1, 2) or y.shape[0] != m.shape[0]:
        raise LiveError(f"solve() needs b with {m.shape[0]} rows, the size of A")
    _no_affine(a, b, op="solve")
    if abs(np.linalg.cond(m)) > 1e13:
        raise LiveError("solve() of a system whose matrix is singular (or nearly so): the equations are not independent")
    t = mul(Q(1.0, b.dim, b.unit), Q(1.0, a.dim, a.unit), -1)
    return Q(_checked(np.linalg.solve(m, y), "solve"), t.dim, t.unit)


def _lstsq(a: Q, b: Q) -> Q:
    """lstsq(A, b): the x that makes A x as close to b as possible (least squares) for a system with more equations than unknowns; the unit of x is that of b over A."""
    m = _mat(a, "lstsq")
    y = _num(b.v)
    if y.ndim not in (1, 2) or y.shape[0] != m.shape[0]:
        raise LiveError(f"lstsq() needs b with {m.shape[0]} rows, the number of rows of A")
    if m.shape[0] < m.shape[1]:
        raise LiveError("lstsq() needs at least as many equations (rows) as unknowns (columns)")
    _no_affine(a, b, op="lstsq")
    sv = np.linalg.svd(m, compute_uv=False)
    if sv[-1] <= 1e-12 * sv[0]:
        raise LiveError("lstsq() of a matrix whose columns are not independent: the unknowns cannot be told apart")
    t = mul(Q(1.0, b.dim, b.unit), Q(1.0, a.dim, a.unit), -1)
    return Q(_checked(np.linalg.lstsq(m, y, rcond=None)[0], "lstsq"), t.dim, t.unit)


def _rank(q: Q) -> Q:
    return Q(float(np.linalg.matrix_rank(_mat(q, "rank"))))


def _cond(q: Q) -> Q:
    """Condition number: how much errors in the data can grow in solve() (1 is ideal; above about 1e10 the answer has no reliable digits)."""
    a = _mat(q, "cond", square=True)
    c = float(np.linalg.cond(a))
    if not math.isfinite(c):
        raise LiveError("The matrix is singular, so its condition number is infinite")
    return Q(c)


def _pinv(q: Q) -> Q:
    a = _mat(q, "pinv")
    _no_affine(q, op="pinv")
    dim = q.dim ** Fraction(-1)
    return Q(_checked(np.linalg.pinv(a), "pinv"), dim, _unit_pow(q.unit, Fraction(-1), dim))


def _svdvals(q: Q) -> Q:
    a = _mat(q, "svdvals")
    _no_affine(q, op="svdvals")
    return Q(np.linalg.svd(a, compute_uv=False), q.dim, q.unit)


def _qr_part(which: int):
    def run(q: Q) -> Q:
        name = "qr_q" if which == 0 else "qr_r"
        a = _mat(q, name)
        _no_affine(q, op=name)
        out = np.linalg.qr(a)[which]                              # A = Q R with Q orthonormal (no unit) and R upper triangular (the unit of A)
        return Q(_checked(out, name), DIMENSIONLESS if which == 0 else q.dim, None if which == 0 else q.unit)
    return run


def _lu_part(which: int):
    def run(q: Q) -> Q:
        name = ("lu_p", "lu_l", "lu_u")[which]
        a = _mat(q, name)
        _no_affine(q, op=name)
        from scipy.linalg import lu

        out = lu(a)[which]                                         # A = P L U: P a permutation, L unit lower triangular (no unit), U upper triangular (the unit of A)
        return Q(_checked(out, name), q.dim if which == 2 else DIMENSIONLESS, q.unit if which == 2 else None)
    return run


def _chol(q: Q) -> Q:
    """Lower-triangular L with A = L Lᵀ for a symmetric positive-definite matrix; its unit is the square root of A's."""
    a = _mat(q, "chol", square=True)
    _no_affine(q, op="chol")
    if not np.allclose(a, a.T, rtol=1e-10, atol=1e-12 * (np.max(np.abs(a)) or 1.0)):
        raise LiveError("chol() needs a symmetric matrix")
    try:
        low = np.linalg.cholesky(a)
    except np.linalg.LinAlgError:
        raise LiveError("chol() needs a positive-definite matrix (all eigenvalues above zero)") from None
    fr = Fraction(1, 2)
    dim = q.dim ** fr
    return Q(_checked(low, "chol"), dim, _unit_pow(q.unit, fr, dim))


def _shape_of(q: Q) -> Q:
    return Q(np.array([float(n) for n in np.shape(q.v)]) if np.ndim(q.v) else np.array([1.0]))


def _outer(a: Q, b: Q) -> Q:
    x, y = _vec(a, "outer"), _vec(b, "outer")
    _no_affine(a, b, op="outer")
    t = mul(Q(1.0, a.dim, a.unit), Q(1.0, b.dim, b.unit))
    return Q(_checked(np.outer(x, y), "outer"), t.dim, t.unit)


def _var(q: Q) -> Q:
    a = _vec(q, "var")
    if a.dtype.kind == "c" or a.size < 2:
        raise LiveError("var() needs a list of at least two real values")
    _no_affine(q, op="var")
    dim = q.dim ** Fraction(2)
    return Q(float(np.var(a, ddof=1)), dim, _unit_pow(q.unit, Fraction(2), dim))


def _percentile(q: Q, p: Q) -> Q:
    """percentile(v, p): the value below which p percent of the list lies (p from 0 to 100, interpolating between values)."""
    a = _vec(q, "percentile")
    if a.dtype.kind == "c" or a.size == 0:
        raise LiveError("percentile() needs a list of real values")
    if not p.dim.is_dimensionless or np.any(_real(p.v) < 0) or np.any(_real(p.v) > 100):
        raise LiveError("percentile() needs p from 0 to 100")
    out = np.percentile(a, _real(p.v))
    return Q(out if np.ndim(out) else float(out), q.dim, q.unit)


def _norm_any(q: Q) -> Q:
    a = _num(q.v)
    if a.ndim == 0:
        raise LiveError("norm() needs a list or a matrix")
    _no_affine(q, op="norm")
    return Q(float(np.sqrt(np.sum(np.abs(a) ** 2))), q.dim, q.unit)


def _sorted(q: Q) -> Q:
    return Q(np.sort(_vec(q, "sort")), q.dim, q.unit)


def _reversed(q: Q) -> Q:
    return Q(_vec(q, "reverse")[::-1].copy(), q.dim, q.unit)


def _cumsum(q: Q) -> Q:
    _no_affine(q, op="cumsum")
    return Q(np.cumsum(_vec(q, "cumsum")), q.dim, q.unit)


def _diff(q: Q) -> Q:
    a = _vec(q, "diff")
    if a.size < 2:
        raise LiveError("diff() needs at least two values")
    return Q(np.diff(a), q.dim, q.unit if not q.affine else None)


def _prod(q: Q) -> Q:
    a = _vec(q, "prod")
    _no_affine(q, op="prod")
    dim = q.dim ** Fraction(int(a.size))
    res = Q(np.prod(a).item(), dim, _unit_pow(q.unit, Fraction(int(a.size)), dim))
    _finite(res.v)
    return res


def _range(*qs: Q) -> Q:
    """range(stop), range(start, stop) or range(start, stop, step): start, start+step, ... below stop (stop is not included)."""
    if not 1 <= len(qs) <= 3:
        raise LiveError("range() takes range(stop), range(start, stop) or range(start, stop, step)")
    vals = list(qs) if len(qs) > 1 else [Q(0.0, qs[0].dim, qs[0].unit), qs[0]]
    for q in vals[1:]:
        _same_list_dim(vals[0], q, "range")
    if len(qs) == 3 and qs[2].dim != qs[0].dim:
        raise LiveError("range() needs the start, stop and step in the same units")
    lo, hi = float(vals[0].v), float(vals[1].v)
    st = float(qs[2].v) if len(qs) == 3 else (1.0 if vals[0].dim.is_dimensionless else float(vals[1].v) - float(vals[0].v))
    if st == 0 or (hi - lo) / st < 0 or abs((hi - lo) / st) > MAX_LIST:
        raise LiveError(f"range() would have no values or more than {MAX_LIST}")
    n = int(np.ceil((hi - lo) / st - 1e-12))
    return Q(lo + st * np.arange(max(n, 0)), vals[0].dim, vals[0].unit)


def _linspace(a: Q, b: Q, n: Q) -> Q:
    _same_list_dim(a, b, "linspace")
    if not n.dim.is_dimensionless or n.v != int(n.v) or not 2 <= n.v <= MAX_LIST:
        raise LiveError(f"linspace() needs a whole number of points from 2 to {MAX_LIST}")
    return Q(np.linspace(float(a.v), float(b.v), int(n.v)), a.dim, a.unit)


def _dot(a: Q, b: Q) -> Q:
    x, y = _vec(a, "dot"), _vec(b, "dot")
    if x.size != y.size:
        raise LiveError("dot() needs two lists of the same length")
    _no_affine(a, b, op="dot")
    t = mul(Q(1.0, a.dim, a.unit), Q(1.0, b.dim, b.unit))
    res = Q(np.dot(x, y).item(), t.dim, t.unit)
    _finite(res.v)
    return res


def _cross(a: Q, b: Q) -> Q:
    x, y = _vec(a, "cross"), _vec(b, "cross")
    if x.size != 3 or y.size != 3:
        raise LiveError("cross() needs two lists of three values")
    _no_affine(a, b, op="cross")
    t = mul(Q(1.0, a.dim, a.unit), Q(1.0, b.dim, b.unit))
    return Q(np.cross(x, y), t.dim, t.unit)


def _pair(xs: Q, ys: Q, name: str, minimum: int = 2) -> tuple[np.ndarray, np.ndarray]:
    x, y = _vec(xs, name), _vec(ys, name)
    if x.size != y.size:
        raise LiveError(f"{name}() needs two lists of the same length ({x.size} and {y.size} values)")
    if x.size < minimum:
        raise LiveError(f"{name}() needs at least {minimum} points")
    return x, y


def _per(y: Q, x: Q, sign: int = 1) -> Q:
    """The unit of y times (sign 1) or divided by (sign -1) the unit of x, as a template with value 1."""
    return mul(Q(1.0, y.dim, None if y.affine else y.unit), Q(1.0, x.dim, None if x.affine else x.unit), sign)


def _trapz(xs: Q, ys: Q) -> Q:
    x, y = _pair(xs, ys, "trapz")
    _no_affine(xs, ys, op="trapz")
    t = _per(ys, xs)
    return Q(_checked(np.array(np.trapezoid(y, x) if hasattr(np, "trapezoid") else np.trapz(y, x)), "trapz").item(), t.dim, t.unit)


def _cumtrapz(xs: Q, ys: Q) -> Q:
    x, y = _pair(xs, ys, "cumtrapz")
    _no_affine(xs, ys, op="cumtrapz")
    t = _per(ys, xs)
    steps = np.concatenate([[0.0], np.cumsum(np.diff(x) * (y[1:] + y[:-1]) / 2)])
    return Q(_checked(steps, "cumtrapz"), t.dim, t.unit)


def _interp(at: Q, xs: Q, ys: Q) -> Q:
    x, y = _pair(xs, ys, "interp")
    if at.dim != xs.dim:
        raise LiveError("interp() needs the point in the same units as the x list")
    if np.any(np.diff(x) <= 0):
        raise LiveError("interp() needs the x list to increase (use sort first, and no repeated values)")
    a = _real(at.v)
    if np.any(a < x[0] - 1e-12 * abs(x[-1] - x[0])) or np.any(a > x[-1] + 1e-12 * abs(x[-1] - x[0])):
        raise LiveError("interp() will not extrapolate: the point is outside the range of the x list")
    out = np.interp(a, x, y)
    return Q(out if np.ndim(out) else float(out), ys.dim, ys.unit)


def _line_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    if np.ptp(x) == 0:
        raise LiveError("The x values are all the same, so there is no line to fit")
    slope, icpt = np.polyfit(x, y, 1)
    ss_res = float(np.sum((y - (slope * x + icpt)) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return float(slope), float(icpt), (1.0 if ss_tot == 0 else 1 - ss_res / ss_tot)


def _clean_zero(value: float, scale: float) -> float:
    """A fitted value that is only rounding noise next to the data (4e-16 beside values of 8) is a zero."""
    return 0.0 if abs(value) < 1e-12 * (scale or 1.0) else value


def _slope(xs: Q, ys: Q) -> Q:
    x, y = _pair(xs, ys, "slope")
    _no_affine(xs, ys, op="slope")
    t = _per(ys, xs, -1)
    return Q(_clean_zero(_line_fit(x, y)[0], np.ptp(y) / (np.ptp(x) or 1.0)), t.dim, t.unit)


def _intercept(xs: Q, ys: Q) -> Q:
    x, y = _pair(xs, ys, "intercept")
    _no_affine(xs, op="intercept")
    return Q(_clean_zero(_line_fit(x, y)[1], float(np.max(np.abs(y)))), ys.dim, ys.unit)


def _rsquared(xs: Q, ys: Q) -> Q:
    x, y = _pair(xs, ys, "rsquared")
    return Q(_line_fit(x, y)[2])


def _corr(xs: Q, ys: Q) -> Q:
    x, y = _pair(xs, ys, "corr")
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        raise LiveError("corr() needs values that are not all the same")
    return Q(float(np.corrcoef(x, y)[0, 1]))


def _polyfit(xs: Q, ys: Q, deg: Q, at: Q) -> Q:
    """polyfit(xs, ys, n, at): the least-squares polynomial of degree n through the points, evaluated at ``at`` (the coefficients have a different unit each, so the fit is returned as values)."""
    x, y = _pair(xs, ys, "polyfit")
    if not deg.dim.is_dimensionless or np.ndim(deg.v) or deg.v != int(deg.v) or not 1 <= deg.v <= 8:
        raise LiveError("polyfit() needs a whole degree from 1 to 8")
    n = int(deg.v)
    if x.size <= n:
        raise LiveError(f"A degree {n} polynomial needs at least {n + 1} points")
    if at.dim != xs.dim:
        raise LiveError("polyfit() needs the points to evaluate at in the same units as the x list")
    scale = float(np.max(np.abs(x))) or 1.0
    coef = np.polyfit(x / scale, y, n)
    out = np.polyval(coef, _real(at.v) / scale)
    return Q(_checked(out, "polyfit") if np.ndim(out) else float(out), ys.dim, ys.unit)


def _eigen(q: Q, name: str):
    a = _mat(q, name, square=True)
    _no_affine(q, op=name)
    if a.dtype.kind != "c" and np.allclose(a, a.T, rtol=1e-10, atol=1e-12 * (np.max(np.abs(a)) or 1.0)):
        return np.linalg.eigh(a)
    vals, vecs = np.linalg.eig(a)
    if a.dtype.kind != "c" and np.all(np.abs(vals.imag) <= 1e-9 * (np.max(np.abs(vals)) or 1.0)):     # a real matrix whose eigenvalues are all real
        vals, vecs = vals.real, vecs.real
    order = np.lexsort((np.imag(vals), np.real(vals)))
    return vals[order], vecs[:, order]


def _eigvals(q: Q) -> Q:
    return Q(_checked(_eigen(q, "eigvals")[0], "eigvals"), q.dim, q.unit)


def _eigvecs(q: Q) -> Q:
    """The eigenvectors as the columns of a dimensionless matrix, each of length 1, in the order of eigvals (smallest first)."""
    vecs = _eigen(q, "eigvecs")[1]
    return Q(_checked(vecs, "eigvecs"), DIMENSIONLESS, None)


#: reductions that treat a single list argument as the values to combine (while plotting an array is one value per point, so they stay elementwise)
_LIST_REDUCE = {"sum": np.sum, "mean": np.mean, "median": np.median, "stdev": lambda a: np.std(a, ddof=1), "min": np.min, "max": np.max, "hypot": lambda a: np.sqrt(np.sum(a * a))}


def _reduce_list(name: str, q: Q) -> Q:
    a = _vec(q, name)
    if a.size == 0 or (name == "stdev" and a.size < 2):
        raise LiveError(f"{name}() needs {'at least two' if name == 'stdev' else 'at least one'} value{'s' if name == 'stdev' else ''} in the list")
    if name in ("sum", "stdev", "hypot"):
        _no_affine(q, op=name)
    if a.dtype.kind == "c" and name in ("median", "stdev", "min", "max"):
        raise LiveError(f"{name}() does not work with complex numbers")
    out = np.asarray(_LIST_REDUCE[name](a) if not (name == "hypot" and a.dtype.kind == "c") else np.sqrt(np.sum(np.abs(a) ** 2))).item()
    _finite(out)
    return Q(out, q.dim, q.unit)


#: functions that take the *name* of a user-defined function as their first value
CALCULUS = ("integrate", "derivative", "findroot", "sumover")

FUNCTIONS: dict[str, Any] = {
    "sqrt": _root(2, "sqrt"), "cbrt": _root(3, "cbrt"),
    "exp": _unary(np.exp, "exp"), "ln": _unary(np.log, "ln", lambda x: x > 0), "log": _unary(np.log, "log", lambda x: x > 0),
    "log10": _unary(np.log10, "log10", lambda x: x > 0), "log2": _unary(np.log2, "log2", lambda x: x > 0),
    "sin": _unary(np.sin, "sin"), "cos": _unary(np.cos, "cos"), "tan": _unary(np.tan, "tan"),
    "asin": _unary(np.arcsin, "asin", lambda x: np.abs(x) <= 1), "acos": _unary(np.arccos, "acos", lambda x: np.abs(x) <= 1),
    "atan": _unary(np.arctan, "atan"), "sinh": _unary(np.sinh, "sinh"), "cosh": _unary(np.cosh, "cosh"), "tanh": _unary(np.tanh, "tanh"),
    "atan2": _atan2, "abs": _shape(np.abs, "abs"), "floor": _shape(np.floor, "floor"), "ceil": _shape(np.ceil, "ceil"), "round": _round,
    "min": _minmax(np.minimum, "min"), "max": _minmax(np.maximum, "max"), "factorial": _factorial,
    "sum": _agg("sum", lambda st: np.sum(st, axis=0), affine_ok=False), "mean": _agg("mean", lambda st: np.mean(st, axis=0), affine_ok=True),
    "median": _agg("median", lambda st: np.median(st, axis=0), affine_ok=True), "stdev": _agg("stdev", lambda st: np.std(st, axis=0, ddof=1), affine_ok=False, minimum=2),
    "hypot": _hypot, "sign": _sign, "mod": _mod, **{n: _needs_function(n) for n in CALCULUS},
    "len": _len, "sort": _sorted, "reverse": _reversed, "cumsum": _cumsum, "diff": _diff, "prod": _prod, "range": _range, "linspace": _linspace,
    "dot": _dot, "cross": _cross, "norm": _norm_any, "transpose": _transpose, "matmul": _matmul, "det": _det, "inv": _inv, "solve": _solve_linear, "identity": _identity,
    "rows": _rows, "cols": _cols, "trace": _trace,
    "qr_q": _qr_part(0), "qr_r": _qr_part(1), "lu_p": _lu_part(0), "lu_l": _lu_part(1), "lu_u": _lu_part(2), "chol": _chol, "shape": _shape_of,
    "lstsq": _lstsq, "rank": _rank, "cond": _cond, "pinv": _pinv, "svdvals": _svdvals, "outer": _outer, "var": _var, "percentile": _percentile,
    "trapz": _trapz, "cumtrapz": _cumtrapz, "interp": _interp, "slope": _slope, "intercept": _intercept, "rsquared": _rsquared, "corr": _corr, "polyfit": _polyfit,
    "eigvals": _eigvals, "eigvecs": _eigvecs, "real": _real_part, "imag": _imag_part, "conj": _conj, "arg": _arg, "polar": _polar, "calc": _needs_function("calc"),
}
def _per_layer(fn):
    """Let a matrix function take a 3-D list: it is applied to every layer, and the answers are stacked (a number per layer gives a list)."""
    def run(q: Q) -> Q:
        if np.ndim(q.v) != 3:
            return fn(q)
        outs = [fn(Q(layer, q.dim, q.unit)) for layer in np.asarray(q.v)]
        first = outs[0]
        if any(o.dim != first.dim for o in outs):
            raise LiveError("The layers give answers with different units")
        return Q(np.array([o.v for o in outs], dtype=complex if any(_is_complex(o) for o in outs) else float), first.dim, first.unit)
    return run


for _name in ("det", "trace", "inv", "eigvals", "rank", "cond", "transpose"):
    FUNCTIONS[_name] = _per_layer(FUNCTIONS[_name])

CONSTANTS = {"pi": math.pi, "e": math.e}
#: physical constants (CODATA 2018 / SI 2019) with their units; a variable of the same name takes precedence
QCONSTANTS: dict[str, tuple[float, str, str]] = {
    "c0": (299792458.0, "m/s", "speed of light in vacuum"), "g0": (9.80665, "m/s^2", "standard gravity"), "Gnewton": (6.67430e-11, "m^3/(kg*s^2)", "Newtonian constant of gravitation"),
    "hP": (6.62607015e-34, "J*s", "Planck constant"), "hbar": (1.054571817e-34, "J*s", "reduced Planck constant"), "kBoltz": (1.380649e-23, "J/K", "Boltzmann constant"),
    "NA": (6.02214076e23, "1/mol", "Avogadro constant"), "Rgas": (8.314462618, "J/(mol*K)", "molar gas constant"), "qe": (1.602176634e-19, "C", "elementary charge"),
    "eps0": (8.8541878128e-12, "F/m", "vacuum permittivity"), "mu0": (1.25663706212e-6, "H/m", "vacuum permeability"), "sigmaSB": (5.670374419e-8, "W/(m^2*K^4)", "Stefan–Boltzmann constant"),
    "me": (9.1093837015e-31, "kg", "electron mass"), "mp": (1.67262192369e-27, "kg", "proton mass"),
}
RESERVED = set(FUNCTIONS) | set(CONSTANTS) | _KEYWORDS | {"ans"}      # (the physical constants may be redefined as variables)
#: how a function must be spelled in My equations (None: not available there)
NOT_IN_CUSTOM = {"sum", "mean", "median", "stdev", "hypot", "sign", "mod", *CALCULUS, "len", "sort", "reverse", "cumsum", "diff", "prod", "range", "linspace", "dot", "cross", "norm", "calc", "transpose", "matmul", "det", "inv", "solve", "identity", "rows", "cols", "trace", "trapz", "cumtrapz", "interp", "slope", "intercept", "rsquared", "corr", "polyfit", "eigvals", "eigvecs", "real", "imag", "conj", "arg", "polar", "lstsq", "rank", "cond", "pinv", "svdvals", "outer", "var", "percentile", "qr_q", "qr_r", "lu_p", "lu_l", "lu_u", "chol", "shape"}
CUSTOM_NAME = {"abs": "Abs", "min": "Min", "max": "Max", "ceil": "ceiling"}


# ------------------------------------------------------------------ tokens

@dataclass
class Tok:
    kind: str     # num | id | op | end
    text: str
    pos: int
    end: int


def tokenize(text: str) -> list[Tok]:
    out: list[Tok] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            break
        if m.lastgroup is None or m.end() == pos:
            break
        kind = m.lastgroup
        out.append(Tok(kind, m.group(kind), m.start(kind), m.end(kind)))
        pos = m.end()
        if len(out) > MAX_TOKENS:
            raise SyntaxErr("That line is too long")
    out.append(Tok("end", "", len(text), len(text)))
    return out


# ------------------------------------------------------------------ parser
# AST nodes are tuples: ("num", float, text) ("name", n) ("unit", n) ("qty", num, unit) ("neg", a) ("bin", op, a, b)
#                       ("pow", a, b) ("call", name, [args])

class Parser:
    def __init__(self, text: str, toks: list[Tok], known: set[str], funcs: set[str], extra_vars: set[str] = frozenset(), bare_units: bool = True):
        self.text, self.t, self.i = text, toks, 0
        self.known, self.funcs, self.extra = known, funcs, set(extra_vars)
        #: may a bare name (not after a number) be a unit? Off in equations and assignments, where bare names are variables.
        self.bare_units = bare_units
        self.notes: list[str] = []
        self.depth = 0
        self.closing = False     # was the previous primary a number or ')' (allows implicit multiplication)

    # -- helpers
    @property
    def cur(self) -> Tok:
        return self.t[self.i]

    def take(self) -> Tok:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def at_op(self, *ops: str) -> bool:
        return self.cur.kind == "op" and self.cur.text in ops

    def _conversion_in(self) -> bool:
        """`in` followed by something is the conversion keyword (5 cm in inch); a lone trailing `in` is the unit."""
        return self.cur.kind == "id" and self.cur.text == "in" and self.t[self.i + 1].kind != "end"

    def at_kw(self, *kws: str) -> bool:
        return self.cur.kind == "id" and self.cur.text in kws

    def expect(self, op: str) -> None:
        if not self.at_op(op):
            raise SyntaxErr(f"Expected ‘{op}’" + (f" before ‘{self.cur.text}’" if self.cur.kind != "end" else " at the end"))
        self.i += 1

    def is_var(self, name: str) -> bool:
        return name in self.known or name in self.extra

    def unit_of(self, name: str, allow_var: bool = False, allow_func: bool = False) -> Unit | None:
        if (self.is_var(name) and not allow_var) or name in CONSTANTS or (name in RESERVED and not (allow_func and name in FUNCTIONS and name not in self.funcs)):
            return None
        try:
            return _reg().parse(name)
        except UnitError as exc:
            if getattr(exc, "code", "") == "UNIT_AMBIGUOUS":
                raise LiveError(str(exc)) from None
            return None

    # -- grammar
    def expr(self) -> tuple:
        node = self.term()
        while self.at_op("+", "-"):
            op = self.take().text
            node = ("bin", op, node, self.term())
        return node

    def term(self) -> tuple:
        node = self.unary()
        while True:
            if self.at_op("*", "/"):
                op = self.take().text
                node = ("bin", op, node, self.unary())
            elif self.closing and (self.at_op("(") or (self.cur.kind == "id" and self.cur.text not in _KEYWORDS and not self._conversion_in())):
                node = ("bin", "*", node, self.unary())          # 2x, 3(x+1), (a+b)c
            else:
                return node

    def unary(self) -> tuple:
        if self.at_op("-", "+"):
            neg = self.take().text == "-"
            inner = self.unary()
            if neg and inner[0] == "num":
                return ("num", -inner[1], "-" + inner[2])
            if neg and inner[0] == "qty" and inner[1][0] == "num":            # -56.5 degC is a temperature, not the negation of one
                return ("qty", ("num", -inner[1][1], "-" + inner[1][2]), inner[2])
            return ("neg", inner) if neg else inner
        return self.power()

    def _index_spec(self) -> tuple:
        """One index: an expression, or a slice a:b (either end may be left out)."""
        lo = None if self.at_op(":") else self.expr()
        if not self.at_op(":"):
            return lo
        self.take()
        hi = None if self.at_op(",", "]") else self.expr()
        return ("slice", lo, hi)

    def power(self) -> tuple:
        base = self.primary()
        while self.at_op("["):                                   # v[2], v[2:4], A[1, 2], A[:, 2]: counted from 1, ends included, -1 is the last
            self.take()
            specs = [self._index_spec()]
            while self.at_op(","):
                self.take()
                specs.append(self._index_spec())
            self.expect("]")
            if len(specs) > 3:
                raise SyntaxErr("At most three indices: T[layer, row, column]")
            self.closing = True
            base = ("index", base, specs)
        if self.at_op("^", "**"):
            self.take()
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise SyntaxErr("That expression is nested too deeply")
            exp = self.unary()
            self.depth -= 1
            self.closing = True
            return ("pow", base, exp)
        return base

    def unit_atom(self) -> tuple | None:
        """After a number: a unit name (with optional ^n) that is not a variable, e.g. the `m/s` of `9.81 m/s^2` starts here."""
        node = self._one_unit(allow_var=True)      # 5 m is five metres even when a variable m exists (write 5*m to multiply)
        if node is None:
            return None
        if node[0] == "unit" and self.is_var(node[1]):
            self.notes.append(f"‘{node[1]}’ right after a number was read as the unit ({node[1]}), not your variable {node[1]}; write the number, ‘*’, then the variable to multiply.")
        while self.at_op("/") and self.t[self.i + 1].kind == "op" and self.t[self.i + 1].text == "(" and self._unit_group_ahead():   # 0.2 L/(mg*min)
            self.take()
            self.take()
            group = self._unit_chain()
            self.expect(")")
            node = ("bin", "/", node, group)
        while self.at_op("/", "*") and self.t[self.i + 1].kind == "id":     # 9.81 m/s^2, 5 N*m: the unit goes on
            nxt = self._one_unit(allow_var=self.cur.text == "/", skip=1)     # ‘/s’ is a unit even if a variable s exists; ‘*s’ only if it is not
            if nxt is None:
                break
            node = ("bin", self._chain_op, node, nxt)
        return node

    def _unit_group_ahead(self) -> bool:
        """Is the text after ‘/’ a bracketed group made only of units, operators and whole-number exponents, e.g. (mg*min)?"""
        j = self.i + 2
        depth, seen_unit = 1, False
        while j < len(self.t) and depth:
            t = self.t[j]
            if t.kind == "op" and t.text == "(":
                depth += 1
            elif t.kind == "op" and t.text == ")":
                depth -= 1
            elif t.kind == "id":
                if t.text in _KEYWORDS or self.unit_of(t.text, allow_var=True, allow_func=True) is None:
                    return False
                seen_unit = True
            elif t.kind == "num":
                prev = self.t[j - 1]
                if not re.fullmatch(r"\d+", t.text) or not (prev.kind == "op" and prev.text in ("^", "**", "-")):
                    return False            # a number belongs in a unit group only as an exponent
            elif not (t.kind == "op" and t.text in ("*", "/", "^", "**", "-")):
                return False
            j += 1
        return depth == 0 and seen_unit

    def _unit_chain(self) -> tuple:
        node = self._one_unit(allow_var=True)
        if node is None:
            raise SyntaxErr("Expected a unit")
        while self.at_op("*", "/"):
            op = self.cur.text
            nxt = self._one_unit(allow_var=True, skip=1)
            if nxt is None:
                raise SyntaxErr("Expected a unit")
            node = ("bin", op, node, nxt)
        return node

    def _one_unit(self, allow_var: bool, skip: int = 0) -> tuple | None:
        """A unit name with an optional whole-number exponent, starting `skip` tokens ahead (the operator is consumed on success)."""
        tok = self.t[self.i + skip]
        if tok.kind != "id" or (tok.text in _KEYWORDS):
            return None
        if tok.text == "in" and skip and self.t[self.i + skip + 1].kind != "end":
            return None
        nxt = self.t[self.i + skip + 1]
        as_unit = not (nxt.kind == "op" and nxt.text == "(")            # 20 L/min: ‘min’ is the minute unless it is called like a function
        if self.unit_of(tok.text, allow_var=allow_var, allow_func=as_unit) is None:
            return None
        if skip and self.is_var(tok.text):
            self.notes.append(f"‘{tok.text}’ after ‘/’ was read as the unit ({tok.text}), not your variable {tok.text}; write (…)/({tok.text}) to divide by the variable.")
        if skip:
            self._chain_op = self.take().text
        self.take()
        node: tuple = ("unit", tok.text)
        if self.at_op("^", "**"):
            save = self.i
            self.take()
            sign = 1
            if self.at_op("-", "+"):
                sign = -1 if self.take().text == "-" else 1
            if self.cur.kind == "num" and re.fullmatch(r"\d+(\.\d+)?", self.cur.text):        # s^2, s^0.5
                node = ("pow", node, ("num", sign * float(self.take().text), ""))
            elif (self.at_op("(") and self.t[self.i + 1].kind == "num" and self.t[self.i + 2].kind == "op" and self.t[self.i + 2].text == "/"
                  and self.t[self.i + 3].kind == "num" and self.t[self.i + 4].kind == "op" and self.t[self.i + 4].text == ")"):          # s^(1/2)
                self.take()
                top = float(self.take().text)
                self.take()
                bottom = float(self.take().text)
                self.take()
                if bottom == 0:
                    raise SyntaxErr("A unit exponent cannot have a zero denominator")
                node = ("pow", node, ("num", sign * top / bottom, ""))
            else:
                self.i = save
        return node

    def primary(self) -> tuple:
        tok = self.cur
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise SyntaxErr("That expression is nested too deeply")
        try:
            if tok.kind == "num":
                self.take()
                num = ("num", float(tok.text), tok.text)
                if self.cur.kind == "id" and self.cur.text in ("i", "j") and not self.is_var(self.cur.text) and not (self.t[self.i + 1].kind == "op" and self.t[self.i + 1].text == "("):
                    num = ("imag", float(tok.text), tok.text + self.take().text)          # 4i or 4j: an imaginary number
                u = self.unit_atom()
                self.closing = True
                return ("qty", num, u) if u else num
            if tok.kind == "op" and tok.text == "(":
                self.take()
                inner = self.expr()
                self.expect(")")
                self.closing = True
                return inner
            if tok.kind == "op" and tok.text == "[":                 # [1, 2, 3] or [1 m, 2 m]; a unit may follow: [1, 2, 3] m
                self.take()
                items = []
                if not self.at_op("]"):
                    items.append(self.expr())
                    while self.at_op(","):
                        self.take()
                        items.append(self.expr())
                self.expect("]")
                if len(items) > MAX_LIST:
                    raise SyntaxErr(f"A list can have at most {MAX_LIST} values")
                node = ("list", items)
                u = self.unit_atom()
                self.closing = True
                return ("qty", node, u) if u else node
            if tok.kind == "str":
                self.take()
                self.closing = False
                return ("str", tok.text[1:-1])
            if tok.kind == "id":
                if tok.text in _KEYWORDS:
                    raise SyntaxErr(f"Unexpected ‘{tok.text}’")
                self.take()
                name = tok.text
                is_fn = (name in FUNCTIONS or name in self.funcs) and not self.is_var(name)
                if is_fn and self.at_op("("):
                    self.take()
                    args = []

                    def argument() -> tuple:
                        if name == "calc" and self.cur.kind == "id" and self.t[self.i + 1].kind == "op" and self.t[self.i + 1].text == "=":
                            key = self.take().text
                            self.take()
                            return ("kw", key, self.expr())                  # calc("id", "out", v = 5 m/s): a named input
                        return self.expr()

                    if not self.at_op(")"):
                        args.append(argument())
                        while self.at_op(","):
                            self.take()
                            args.append(argument())
                    self.expect(")")
                    self.closing = True
                    return ("call", name, args)
                self.closing = False
                if (name in CONSTANTS or name in QCONSTANTS) and not self.is_var(name):
                    return ("name", name)
                if name in ("i", "j") and not self.is_var(name) and not self.at_op("("):
                    return ("imag", 1.0, name)                                              # the imaginary unit, unless you defined a variable called i or j
                if self.bare_units and not self.is_var(name) and name not in self.funcs and self.unit_of(name, allow_func=True) is not None and (name not in RESERVED or name in FUNCTIONS):
                    return ("unit", name)               # a bare unit (0.1/min); min and max are units when not called
                return ("name", name)
            if tok.kind == "end":
                raise SyntaxErr("The expression ends too early")
            raise SyntaxErr(f"Unexpected ‘{tok.text}’")
        finally:
            self.depth -= 1

    def finish(self) -> None:
        if self.cur.kind != "end":
            raise SyntaxErr(f"Unexpected ‘{self.cur.text}’")


def names_in(node: tuple) -> list[str]:
    """Plain names (not units) used by an expression, in order of first use."""
    out: list[str] = []

    def walk(n: tuple) -> None:
        k = n[0]
        if k == "name":
            if n[1] not in out and n[1] not in CONSTANTS and n[1] not in QCONSTANTS:
                out.append(n[1])
        elif k == "qty" or k in ("neg",):
            walk(n[1])
        elif k == "bin":
            walk(n[2]); walk(n[3])
        elif k == "pow":
            walk(n[1]); walk(n[2])
        elif k == "list":
            for a in n[1]:
                walk(a)
        elif k == "index":
            walk(n[1])
            for sp_ in n[2]:
                if sp_ is not None:
                    for part in ((sp_[1], sp_[2]) if sp_[0] == "slice" else (sp_,)):
                        if part is not None:
                            walk(part)
        elif k == "kw":
            walk(n[2])
        elif k == "call":
            for i, a in enumerate(n[2]):
                if i == 0 and n[1] in CALCULUS and a[0] == "name":
                    continue                                    # the name of a function, not a variable
                if n[1] == "calc" and a[0] in ("name", "str"):
                    continue                                    # which calculation, which output: text, not variables
                walk(a)
    walk(node)
    return out


# ------------------------------------------------------------------ LaTeX

def name_tex(name: str) -> str:
    if name in GREEK:
        return "\\" + name
    m = re.fullmatch(r"([A-Za-z])(\d+)", name)
    if m:
        return f"{m.group(1)}_{{{m.group(2)}}}"
    base, _, sub = name.partition("_")
    head = base if len(base) == 1 else (("\\" + base) if base in GREEK else rf"\mathrm{{{base}}}")
    return head + (f"_{{{sub}}}" if sub else "")


def _num_tex(x: float, sig: int = 6) -> str:
    return fmt_number(x, sig)[1]


_FUNC_TEX = {"sin", "cos", "tan", "sinh", "cosh", "tanh", "exp", "ln", "log"}
_PREC = {"+": 1, "-": 1, "*": 2, "/": 2}


def tex(node: tuple, subst: dict[str, str] | None = None, parent: int = 0) -> str:
    """LaTeX of an expression. ``subst`` replaces variable names by ready-made LaTeX (their values)."""
    k = node[0]
    if k == "num":
        return _num_tex(node[1])
    if k == "imag":
        return "i" if node[1] == 1 and node[2] in ("i", "j") else rf"{_num_tex(node[1])}\,{node[2][-1]}"
    if k == "name":
        if node[1] == "pi":
            return r"\pi"
        if node[1] in CONSTANTS:
            return node[1]
        if subst and node[1] in subst:
            s = subst[node[1]]
            return rf"\left({s}\right)" if parent >= 3 else s
        return name_tex(node[1])
    if k == "unit":
        return unit_tex(_reg().parse(node[1]))
    if k == "qty":
        return rf"{tex(node[1])}\,{tex(node[2])}"
    if k == "neg":
        inner = tex(node[1], subst, 3)
        return rf"-{inner}" if node[1][0] not in ("bin",) or _PREC[node[1][1]] > 1 else rf"-\left({inner}\right)"
    if k == "pow":
        base = tex(node[1], subst, 3)
        if node[1][0] in ("bin", "neg") or (node[1][0] == "num" and node[1][1] < 0):
            base = rf"\left({base}\right)"
        return rf"{base}^{{{tex(node[2], subst)}}}"
    if k == "bin":
        op, a, b = node[1], node[2], node[3]
        if op == "/":
            return rf"\frac{{{tex(a, subst)}}}{{{tex(b, subst)}}}"
        prec = _PREC[op]
        left = tex(a, subst, prec)
        right = tex(b, subst, prec + (1 if op in "-" else 0))
        if op == "*":
            valued = b[0] == "name" and bool(subst) and b[1] in subst           # a name that is being shown as its value: 2 \cdot 3 m, not "2 3 m"
            sep = r"\,"if (a[0] in ("num", "qty") and b[0] in ("name", "call") and not valued) else r" \cdot "
            s = f"{left}{sep}{right}"
        else:
            s = f"{left} {op} {right}"
        if prec < parent or (prec == parent and op == "-" and parent):
            return rf"\left({s}\right)"
        return s
    if k == "list":
        if node[1] and all(a[0] == "list" and a[1] and all(b[0] == "list" for b in a[1]) for a in node[1]):
            return r"\left[" + r",\ ".join(tex(a, subst) for a in node[1]) + r"\right]"                 # a list of matrices
        if node[1] and all(a[0] == "list" for a in node[1]):
            rows = r" \\ ".join(" & ".join(tex(c, subst) for c in a[1]) for a in node[1])
            return r"\begin{bmatrix}" + rows + r"\end{bmatrix}"
        inner = r",\ ".join(tex(a, subst) for a in node[1])
        return rf"\left[{inner}\right]"
    if k == "index":
        def one(sp_):
            if sp_[0] == "slice":
                return f"{tex(sp_[1], subst) if sp_[1] else ''}:{tex(sp_[2], subst) if sp_[2] else ''}"
            return tex(sp_, subst)
        return rf"{tex(node[1], subst, 9)}_{{{', '.join(one(x) for x in node[2])}}}"
    if k == "str":
        return r"\text{" + re.sub(r"([_%&#{}$])", r"\\\1", node[1]).replace("^", r"\^{}").replace("~", r"\~{}") + "}"
    if k == "kw":
        return rf"{name_tex(node[1])} = {tex(node[2], subst)}"
    if k == "call":
        name, args = node[1], [tex(a, subst) for a in node[2]]
        if name == "sqrt":
            return rf"\sqrt{{{args[0]}}}"
        if name == "cbrt":
            return rf"\sqrt[3]{{{args[0]}}}"
        if name == "abs":
            return rf"\left|{args[0]}\right|"
        if name == "factorial":
            return rf"{args[0]}!"
        if name not in FUNCTIONS:
            return rf"{name_tex(name)}\left({', '.join(args)}\right)"
        head = rf"\{name}" if name in _FUNC_TEX else {"asin": r"\arcsin", "acos": r"\arccos", "atan": r"\arctan"}.get(name, rf"\mathrm{{{name}}}")
        return rf"{head}\left({', '.join(args)}\right)"
    return "?"


# ------------------------------------------------------------------ evaluation

class Scope:
    def __init__(self) -> None:
        self.vars: dict[str, Q] = {}
        self.funcs: dict[str, Func] = {}
        self.angle = "rad"           # "deg": a bare number given to sin/cos/tan/polar is degrees, and asin/acos/atan/atan2/arg answer in degrees
        self.plotting = False        # arrays are plot samples (one value per point), not lists: sum(x) stays elementwise
        self.work: list[dict] = []   # what library calls and calculus functions did while this line was evaluated (shown as worked steps)

    def copy(self) -> Scope:
        s = Scope()
        s.vars, s.funcs, s.plotting, s.angle = dict(self.vars), dict(self.funcs), self.plotting, self.angle
        s.work = self.work
        return s


def evaluate(node: tuple, sc: Scope, depth: int = 0) -> Q:
    k = node[0]
    if k == "num":
        return Q(node[1])
    if k == "imag":
        return Q(complex(0.0, node[1]))
    if k == "unit":
        u = _reg().parse(node[1])
        return Q(u.to_si(1.0) if u.shift else u.factor, u.dim, u)
    if k == "qty":
        n, u = evaluate(node[1], sc, depth), node[2]
        base = _unit_of_node(u)
        if base is not None and base.shift:           # 20 degC: an absolute temperature on an offset scale
            return Q(base.to_si(n.v), base.dim, base)
        return mul(n, evaluate(u, sc, depth))
    if k == "name":
        name = node[1]
        if name in sc.vars:
            return sc.vars[name]
        if name in CONSTANTS:
            return Q(CONSTANTS[name])
        if name in QCONSTANTS:
            val, unit_text, _label = QCONSTANTS[name]
            u = _reg().parse(unit_text)
            return Q(val, u.dim, _coherent(u) or u)
        raise Undefined(name)
    if k == "list":
        items = [evaluate(a, sc, depth) for a in node[1]]
        for q in items:
            if q.dim != items[0].dim:
                raise LiveError(f"A list needs values with the same units, not {_desc(items[0].dim)} and {_desc(q.dim)}")
        first = items[0] if items else Q(0.0)
        if any(np.ndim(q.v) for q in items):                         # a list of lists is a matrix (one row per inner list); a list of matrices is a 3-D list
            rows = [_num(q.v) for q in items]
            if any(r.ndim not in (1, 2) for r in rows) or len({r.ndim for r in rows}) != 1 or len({r.shape for r in rows}) != 1:
                raise LiveError("A matrix needs rows that are lists of the same length, e.g. [[1, 2], [3, 4]]; a 3-D list needs matrices of the same size")
            if len(rows) * rows[0].size > MAX_LIST:
                raise LiveError(f"A matrix can have at most {MAX_LIST} values")
            return Q(np.array(rows, dtype=complex if any(r.dtype.kind == "c" for r in rows) else float), first.dim, first.unit)
        return Q(np.array([q.v for q in items], dtype=complex if any(_is_complex(q) for q in items) else float), first.dim, first.unit)
    if k == "index":
        base = evaluate(node[1], sc, depth)
        arr = _num(base.v)
        if arr.ndim not in (1, 2, 3):
            raise LiveError("Only a list, a matrix or a 3-D list can be indexed")
        specs = node[2]
        if len(specs) > arr.ndim:
            raise LiveError(("A list has one index; use A[row, column] for a matrix", "A matrix has two indices: A[row, column]; use T[layer, row, column] for a 3-D list", "")[arr.ndim - 1] if arr.ndim < 3 else "")

        def position(sp_, size: int, axis: str):
            def one(e, default):
                if e is None:
                    return default
                idx = evaluate(e, sc, depth)
                if not idx.dim.is_dimensionless or np.ndim(idx.v) or idx.v != int(idx.v):
                    raise LiveError("An index is a whole number")
                i = int(idx.v)
                if i == 0 or abs(i) > size:
                    raise LiveError(f"Index {i} is outside the {axis} (it has {size}, counted from 1; -1 is the last)")
                return i if i > 0 else size + 1 + i
            if sp_[0] == "slice":
                lo, hi = one(sp_[1], 1), one(sp_[2], size)
                if lo > hi:
                    raise LiveError(f"The slice {lo}:{hi} is empty (it runs from the first to the last number given, both included)")
                return slice(lo - 1, hi)
            return one(sp_, 1) - 1

        names = ("list",) if arr.ndim == 1 else ("rows", "columns") if arr.ndim == 2 else ("layers", "rows", "columns")
        pos = [position(sp_, arr.shape[i], names[i]) for i, sp_ in enumerate(specs)]
        out = arr[tuple(pos)] if pos else arr
        return Q(out if np.ndim(out) else np.asarray(out).item(), base.dim, base.unit)
    if k == "slice":
        raise LiveError("A range a:b is only used inside [ ]")
    if k == "str":
        raise LiveError("Text is only used inside calc(...)")
    if k == "kw":
        raise LiveError("A named value (name = value) is only used inside calc(...)")
    if k == "neg":
        q = evaluate(node[1], sc, depth)
        _no_affine(q, op="-")
        return Q(-q.v, q.dim, q.unit)
    if k == "bin":
        a, b = evaluate(node[2], sc, depth), evaluate(node[3], sc, depth)
        if node[1] in "+-":
            return add(a, b, 1 if node[1] == "+" else -1)
        return mul(a, b, 1 if node[1] == "*" else -1)
    if k == "pow":
        return power(evaluate(node[1], sc, depth), evaluate(node[2], sc, depth))
    if k == "call":
        name, args = node[1], node[2]
        if name in CALCULUS and name not in sc.funcs:
            return _calculus(name, args, sc, depth)
        if name == "calc" and name not in sc.funcs:
            return _library_call(args, sc, depth)
        vals = [evaluate(a, sc, depth) for a in args]
        if sc.angle == "deg" and name in FUNCTIONS and name not in sc.funcs and (name in _ANGLE_IN or name in _ANGLE_OUT):
            return _call_in_degrees(name, vals)
        if name in FUNCTIONS and name not in sc.funcs and name not in COMPLEX_OK and any(_is_complex(v) for v in vals):
            raise LiveError(f"{name}() does not work with complex numbers")
        if name in _LIST_REDUCE and len(vals) == 1 and np.ndim(vals[0].v) == 1 and not sc.plotting and name not in sc.funcs:
            return _reduce_list(name, vals[0])
        if name in sc.funcs and name not in sc.vars:
            return call_user(sc.funcs[name], name, vals, sc, depth)
        fn = FUNCTIONS[name]
        try:
            return fn(*vals)
        except TypeError:
            raise LiveError(f"{name}() was given the wrong number of values") from None
    raise LiveError("Cannot evaluate that")


#: in degree mode: functions whose angle argument is read as degrees when it is a bare number (the position of the angle among the arguments), and functions that answer with an angle
_ANGLE_IN = {"sin": 0, "cos": 0, "tan": 0, "polar": 1}
_ANGLE_OUT = {"asin", "acos", "atan", "atan2", "arg"}


def _call_in_degrees(name: str, vals: list) -> Q:
    """Degree mode: ``sin(30)`` is the sine of 30 degrees and ``asin(0.5)`` is 30 deg. A value that already has an angle unit (``30 deg``, ``0.5 rad``) is not changed."""
    if name in _ANGLE_IN:
        i = _ANGLE_IN[name]
        if i < len(vals):
            q = vals[i]
            if q.unit is None and q.dim.is_dimensionless and not _is_complex(q):
                vals = [*vals[:i], Q(np.asarray(q.v) * (math.pi / 180) if np.ndim(q.v) else float(q.v) * (math.pi / 180), q.dim, None), *vals[i + 1:]]
    try:
        res = FUNCTIONS[name](*vals)
    except TypeError:
        raise LiveError(f"{name}() was given the wrong number of values") from None
    if name in _ANGLE_OUT:
        return Q(res.v, DIMENSIONLESS, _reg().parse("deg"))
    return res


MAX_CALCULUS_CALLS = 200000


def _calculus(name: str, args: list, sc: Scope, depth: int) -> Q:
    """integrate(f, a, b), derivative(f, x), findroot(f, a, b), sumover(f, first, last): f is the name of a function of one value that you defined."""
    want = {"integrate": 3, "derivative": 2, "findroot": 3, "sumover": 3}[name]
    if len(args) != want:
        raise LiveError(f"{name}() takes {want} values: " + {"integrate": "integrate(f, from, to)", "derivative": "derivative(f, x)", "findroot": "findroot(f, low, high)", "sumover": "sumover(f, first, last)"}[name])
    head = args[0]
    fname = head[1] if head[0] == "name" else None
    if fname is None or fname not in sc.funcs or fname in sc.vars:
        raise LiveError(f"{name}() works on a function you defined: first write f(x) = ..., then {name}(f, ...)")
    fn = sc.funcs[fname]
    if len(fn.params) != 1:
        raise LiveError(f"{name}() needs a function of one value, but {fname} takes {len(fn.params)}")
    pts = [evaluate(a, sc, depth) for a in args[1:]]
    calls = [0]

    def f(x: float, like: Q) -> Q:
        calls[0] += 1
        if calls[0] > MAX_CALCULUS_CALLS:
            raise LiveError(f"{name}() needed more than {MAX_CALCULUS_CALLS} evaluations of {fname}")
        y = call_user(fn, fname, [Q(float(x), like.dim, like.unit)], sc, depth + 1)
        if np.ndim(y.v):
            raise LiveError(f"{fname} did not return a single value")
        _no_affine(y, op=name)
        return y

    info: dict = {}

    def core(pts: list[Q]) -> Q:
        a = pts[0]
        if name == "sumover":
            b = pts[1]
            if not (a.dim.is_dimensionless and b.dim.is_dimensionless) or a.v != int(a.v) or b.v != int(b.v) or not 0 <= b.v - a.v <= 10000:
                raise LiveError("sumover() needs whole numbers, at most 10 000 terms apart")
            total = [f(i, Q(0.0)) for i in range(int(a.v), int(b.v) + 1)]
            for t in total[1:]:
                if t.dim != total[0].dim:
                    raise LiveError(f"{fname} returns different units for different values")
            res = Q(float(sum(float(t.v) for t in total)), total[0].dim, total[0].unit)
            _finite(res.v)
            info.update(first=int(a.v), last=int(b.v), terms=[Q(float(t.v), t.dim, t.unit) for t in total])
            return res
        if name == "derivative":
            x0, h = float(a.v), 1e-4 * max(abs(float(a.v)), 1.0)
            vals = [float(f(x0 + k * h, a).v) for k in (-2, -1, 1, 2)]
            slope = (vals[0] - 8 * vals[1] + 8 * vals[2] - vals[3]) / (12 * h)                      # five-point central difference
            y0 = f(x0, a)
            t = mul(Q(1.0, y0.dim, y0.unit), Q(1.0, a.dim, a.unit), -1)
            res = Q(slope, t.dim, t.unit)
            _finite(res.v)
            info.update(x0=x0, h=h, vals=vals, y0=y0)
            return res
        b = pts[1]
        if b.dim != a.dim:
            raise LiveError(f"{name}() needs both limits in the same units")
        lo, hi = float(a.v), float(b.v)
        if name == "integrate":
            from scipy import integrate as _integrate

            y0 = f(lo, a)
            t = mul(Q(1.0, y0.dim, y0.unit), Q(1.0, a.dim, a.unit))
            before = calls[0]
            val, _err = _integrate.quad(lambda x: float(f(x, a).v), lo, hi, limit=100)
            res = Q(float(val), t.dim, t.unit)
            _finite(res.v)
            info.update(lo=lo, hi=hi, evals=calls[0] - before, err=float(_err), y0=y0)
            return res
        from scipy import optimize as _optimize                                                      # findroot

        flo, fhi = float(f(lo, a).v), float(f(hi, a).v)
        if flo == 0 or fhi == 0:
            info.update(lo=lo, hi=hi, flo=flo, fhi=fhi, root=lo if flo == 0 else hi, iters=0, trivial=True)
            return Q(lo if flo == 0 else hi, a.dim, a.unit)
        if (flo > 0) == (fhi > 0):
            raise LiveError(f"findroot() needs {fname} to change sign between the two limits; it has the same sign at both")
        root, rinfo = _optimize.brentq(lambda x: float(f(x, a).v), lo, hi, xtol=1e-14, rtol=1e-13, maxiter=200, full_output=True)
        info.update(lo=lo, hi=hi, flo=flo, fhi=fhi, root=float(root), iters=int(rinfo.iterations), trivial=False)
        return Q(float(root), a.dim, a.unit)

    if not any(np.ndim(q.v) for q in pts):
        res = core(pts)
        sc.work.append({"kind": "calculus", "name": name, "fname": fname, "fn": fn, "pts": pts, "q": res, "info": info})
        return res
    # an array of limits (while plotting, e.g. the area up to x): one calculation per point
    arrs = np.broadcast_arrays(*[_real(q.v) for q in pts])
    if arrs[0].size > 400:
        raise LiveError(f"{name}() over more than 400 points is too slow")
    first, vals = None, []
    for idx in np.ndindex(arrs[0].shape):
        r = core([Q(float(arr[idx]), q.dim, q.unit) for arr, q in zip(arrs, pts)])
        first = first or r
        vals.append(r.v)
    return Q(np.array(vals, dtype=float).reshape(arrs[0].shape), first.dim, first.unit)


MAX_LIBRARY_POINTS = 400


def _find_calculation(text: str):
    """A library calculation from its full id, the end of its id (``turbine_power``) or, failing that, a unique match on its name."""
    from .core.catalog import default_catalog

    cat = default_catalog()
    text = text.strip()
    try:
        return cat.get(text)
    except KeyError:
        pass
    low = text.lower()
    tail = [c for c in cat if c.id.lower().endswith("." + low)]
    if len(tail) == 1:
        return tail[0]
    pool = tail or [c for c in cat if low in c.id.lower() or low in c.name.lower()]
    if len(pool) == 1:
        return pool[0]
    if not pool:
        raise LiveError(f"No library calculation matches “{text}”. Search the Library in the function search box.")
    raise LiveError(f"“{text}” matches {len(pool)} calculations: " + "; ".join(c.id for c in pool[:6]) + ("; …" if len(pool) > 6 else "") + ". Use the full id.")


def _library_call(args: list, sc: Scope, depth: int) -> Q:
    """calc("id", "output", name = value, ...): solve a library calculation for one output. A list given for an input gives a list of results, one per value."""
    from .core import solve as _solve

    pos = [a for a in args if a[0] != "kw"]
    kws = [a for a in args if a[0] == "kw"]
    if not pos or len(pos) > 2:
        raise LiveError('calc() takes the calculation and, optionally, the output: calc("energy.wind.turbine_power", "Pe", v = 10 m/s, ...)')

    def text_of(node: tuple) -> str:
        if node[0] == "str":
            return node[1]
        if node[0] == "name" and node[1] not in sc.vars:
            return node[1]
        raise LiveError("Write the calculation (and the output) as text in quotes, e.g. calc(\"turbine_power\", ...)")

    calc = _find_calculation(text_of(pos[0]))
    out_key = text_of(pos[1]) if len(pos) == 2 else (calc.outputs[0] if calc.outputs else "")
    if out_key not in calc.by_key or calc.by_key[out_key].is_constant:
        raise LiveError(f"{calc.id} has no output ‘{out_key}’; its variables are {', '.join(v.key for v in calc.variables if not v.is_constant)}")
    given: dict[str, Q] = {}
    for _kw, key, node in kws:
        if key not in calc.by_key or calc.by_key[key].is_constant:
            raise LiveError(f"{calc.id} has no input ‘{key}’; its variables are {', '.join(v.key for v in calc.variables if not v.is_constant)}")
        if key == out_key:
            raise LiveError(f"‘{key}’ is the output asked for, so it cannot also be given")
        if key in given:
            raise LiveError(f"‘{key}’ is given twice")
        given[key] = evaluate(node, sc, depth)
    sizes = {int(np.size(q.v)) for q in given.values() if np.ndim(q.v)}
    if len(sizes) > 1:
        raise LiveError("The lists given to calc() must all have the same length")
    n = sizes.pop() if sizes else 0
    if n > MAX_LIBRARY_POINTS:
        raise LiveError(f"calc() over more than {MAX_LIBRARY_POINTS} values is too slow; use a shorter list")

    kept: list = []

    def one(i: int | None) -> tuple[float, str]:
        inputs = {}
        for key, q in given.items():
            v = float(_real(q.v)[i]) if (np.ndim(q.v) and i is not None) else float(q.v)
            u = q.unit if q.unit is not None else _si_unit(q)
            inputs[key] = (u.from_si(v), u.symbol or "1")
        sol = _solve(calc, inputs, solve_for=[out_key])
        if not sol.ok:
            msg = next((d.message for d in sol.diagnostics if d.level == "error"), "it could not be solved")
            raise LiveError(f"{calc.name}: {msg}" + (f" (for value {i + 1})" if i is not None else ""))
        o = next((o for o in sol.outputs if o["key"] == out_key), None)
        if o is None:
            raise LiveError(f"{calc.name}: no value for ‘{out_key}’")
        kept.append(sol)
        return float(o["si_value"]), str(o["unit"])

    if not n:
        si, unit_text = one(None)
        vals: Any = si
    else:
        res = [one(i) for i in range(n)]
        vals, unit_text = np.array([r[0] for r in res], dtype=float), res[0][1]
    u = _reg().parse(unit_text) if unit_text and unit_text != "1" else None
    result = Q(vals, calc.by_key[out_key].dim, u)
    sc.work.append({"kind": "library", "calc": calc, "out": out_key, "given": list(given.items()), "q": result, "sol": kept[0] if not n else None})
    return result


def _unit_of_node(u: tuple) -> Unit | None:
    if u[0] == "unit":
        return _reg().parse(u[1])
    return None


def call_user(fn: Func, name: str, args: list[Q], sc: Scope, depth: int) -> Q:
    if depth >= MAX_CALL_DEPTH:
        raise LiveError(f"{name}() calls itself or other functions too deeply")
    if len(args) != len(fn.params):
        raise LiveError(f"{name}() takes {len(fn.params)} value{'s' if len(fn.params) != 1 else ''} ({', '.join(fn.params)}), not {len(args)}")
    inner = Scope()
    inner.vars, inner.funcs, inner.plotting, inner.angle = {**sc.vars, **dict(zip(fn.params, args))}, sc.funcs, sc.plotting, sc.angle
    inner.work = sc.work
    return evaluate(fn.body, inner, depth + 1)


# ------------------------------------------------------------------ presentation

def _coherent(u: Unit) -> Unit | None:
    """The same unit written in coherent SI: kN*m -> N*m, km/h -> m/s, lbf*ft -> N*m (so a moment is not called a joule)."""
    terms: dict[str, Fraction] = {}
    reg = _reg()
    try:
        for sym, p in u.terms:
            single = reg.parse(sym.replace("Δ", ""))
            for s2, p2 in reg.parse(reg.si_symbol(single.dim)).terms:
                terms[s2] = terms.get(s2, Fraction(0)) + p * p2
        terms = {k: e for k, e in terms.items() if e}
        return reg.parse(compose(terms.items())) if terms else None
    except UnitError:
        return None


def _si_for(u: Unit | None, dim: Dimension) -> Unit:
    """The coherent SI unit for a quantity written in ``u`` (compound units keep their named parts: kN*m -> N*m)."""
    if dim.is_dimensionless:
        return _reg().parse("1")
    if u is not None and len(u.terms) >= 2:
        c = _coherent(u)
        if c is not None and c.dim == dim:
            return c
    return _reg().parse(_reg().si_symbol(dim))


def _si_unit(q: Q) -> Unit:
    return _si_for(q.unit, q.dim)


def fmt_value(v: Any, sig: int) -> tuple[str, str]:
    """(plain, LaTeX) of a real or complex number: ``3 + 4i``, ``-2i``, ``0.5``."""
    if not isinstance(v, (complex, np.complexfloating)):
        return fmt_number(float(v), sig)
    re_, im = float(v.real), float(v.imag)
    scale = max(abs(re_), abs(im))
    re_ = 0.0 if abs(re_) <= 1e-12 * scale else re_
    im = 0.0 if abs(im) <= 1e-12 * scale else im
    if im == 0:
        return fmt_number(re_, sig)

    def coefficient(x: float) -> tuple[str, str]:
        if abs(x) == 1:
            return "", ""
        return fmt_number(abs(x), sig)

    cp, cl = coefficient(im)
    if re_ == 0:
        sign = "-" if im < 0 else ""
        return f"{sign}{cp}i", f"{sign}{cl}i"
    rp, rl = fmt_number(re_, sig)
    op = "-" if im < 0 else "+"
    return f"{rp} {op} {cp}i", f"{rl} {op} {cl}i"


def polar_text(v: complex, sig: int, unit_symbol: str = "") -> str:
    r, ang = abs(v), math.degrees(math.atan2(v.imag, v.real))
    return f"{fmt_number(r, sig)[0]}{(' ' + unit_symbol) if unit_symbol else ''} ∠ {fmt_number(ang, sig)[0]}°"


def _list_parts(arr: np.ndarray, sig: int) -> tuple[list[str], list[str]]:
    """Plain and LaTeX text of each value of a list, long lists shortened to the first five and last three with the count between."""
    vals = [fmt_value(v, sig) for v in arr]
    plain, ltx = [p for p, _ in vals], [t for _, t in vals]
    if len(vals) > 12:
        plain = [*plain[:5], f"… {len(vals) - 8} more …", *plain[-3:]]
        ltx = [*ltx[:5], rf"\ldots\,({len(vals) - 8}\ \text{{more}})\,\ldots", *ltx[-3:]]
    return plain, ltx


def qty_texts(q: Q, sig: int) -> tuple[str, str, str, str]:
    """(value text, unit symbol, LaTeX of 'value unit', LaTeX of the unit)."""
    if np.ndim(q.v) == 3:                                           # a 3-D list: layers of matrices, in full up to 4 x 4 x 4, otherwise only its size
        arr = _num(q.shown)
        sym = q.unit.symbol if q.unit is not None else ""
        ut = unit_tex(q.unit) if q.unit is not None else ""
        if max(arr.shape) > 4:
            label = " × ".join(str(n) for n in arr.shape) + " array"
            return f"[{label}]", sym, (rf"\text{{{label}}}\,{ut}" if ut else rf"\text{{{label}}}"), ut
        cells = [[[fmt_value(v, sig) for v in row] for row in layer] for layer in arr]
        plain = "[" + ", ".join("[" + ", ".join("[" + ", ".join(c[0] for c in row) + "]" for row in layer) + "]" for layer in cells) + "]"
        mats = [r"\begin{bmatrix}" + r" \\ ".join(" & ".join(c[1] for c in row) for row in layer) + r"\end{bmatrix}" for layer in cells]
        body = r"\left[" + r",\ ".join(mats) + r"\right]"
        return plain, sym, (rf"{body}\,{ut}" if ut else body), ut
    if np.ndim(q.v) == 2:                                           # a matrix: rows of values, shown in full up to 8 x 8
        arr = _num(q.shown)
        sym = q.unit.symbol if q.unit is not None else ""
        ut = unit_tex(q.unit) if q.unit is not None else ""
        if arr.shape[0] > 8 or arr.shape[1] > 8:
            label = f"{arr.shape[0]} × {arr.shape[1]} matrix"
            return f"[{label}]", sym, (rf"\text{{{label}}}\,{ut}" if ut else rf"\text{{{label}}}"), ut
        cells = [[fmt_value(v, sig) for v in row] for row in arr]
        plain = "[" + ", ".join("[" + ", ".join(c[0] for c in row) + "]" for row in cells) + "]"
        body = r"\begin{bmatrix}" + r" \\ ".join(" & ".join(c[1] for c in row) for row in cells) + r"\end{bmatrix}"
        return plain, sym, (rf"{body}\,{ut}" if ut else body), ut
    if np.ndim(q.v):
        plain, ltx = _list_parts(_num(q.shown), sig)
        sym = q.unit.symbol if q.unit is not None else ""
        ut = unit_tex(q.unit) if q.unit is not None else ""
        joined = r",\ ".join(ltx)
        body = rf"\left[{joined}\right]"
        return "[" + ", ".join(plain) + "]", sym, (rf"{body}\,{ut}" if ut else body), ut
    x = np.asarray(q.shown).item() if _is_complex(q) else float(q.shown)
    plain, ltx = fmt_value(x, sig)
    if _is_complex(q) and q.unit is not None and (" + " in plain or " - " in plain):
        plain, ltx = f"({plain})", rf"\left({ltx}\right)"                   # a number with a unit: (3 + 4i) ohm
    sym = q.unit.symbol if q.unit is not None else ""
    ut = unit_tex(q.unit) if q.unit is not None else ""
    return plain, sym, (rf"{ltx}\,{ut}" if ut else ltx), ut


def _leaf_quantities(node: tuple, sc: Scope, out: list[tuple[float, Unit]]) -> None:
    k = node[0]
    if k == "qty":
        n = evaluate(node[1], sc)
        u = _unit_of_node(node[2])
        if u is not None:
            out.append((float(n.v), u))
        else:
            _leaf_quantities(node[2], sc, out)
    elif k == "unit":
        out.append((1.0, _reg().parse(node[1])))
    elif k == "name" and node[1] in sc.vars:
        q = sc.vars[node[1]]
        if q.unit is not None:
            out.append((float(q.shown), q.unit))
    elif k == "neg":
        _leaf_quantities(node[1], sc, out)
    elif k in ("bin", "pow"):
        a, b = (node[2], node[3]) if k == "bin" else (node[1], node[2])
        _leaf_quantities(a, sc, out)
        _leaf_quantities(b, sc, out)
    elif k == "call":
        for a in node[2]:
            _leaf_quantities(a, sc, out)


def _constants_in(node: tuple) -> list[str]:
    """The physical constants (c0, hP, Gnewton ...) an expression uses, in order of first use."""
    out: list[str] = []

    def walk(n) -> None:
        if not isinstance(n, tuple):
            return
        if n[0] == "name" and n[1] in QCONSTANTS and n[1] not in out:
            out.append(n[1])
        for c in n[1:]:
            if isinstance(c, tuple):
                walk(c)
            elif isinstance(c, list):
                for x in c:
                    walk(x)

    walk(node)
    return out


def _has_special(node: tuple) -> bool:
    """Does the expression contain a list, an index or a library call (whose working is not shown step by step)?"""
    if not isinstance(node, tuple):
        return False
    if node[0] in ("list", "index", "str", "kw") or (node[0] == "call" and node[1] in ("calc", *CALCULUS)):
        return True
    return any(_has_special(c) for c in node[1:] if isinstance(c, tuple)) or any(_has_special(x) for c in node[1:] if isinstance(c, list) for x in c)


def make_steps(node: tuple, sc: Scope, q: Q, sig: int, conversion: list[dict] | None = None) -> list[dict]:
    """The working. Library calls (``calc``), the calculus functions and your own functions are opened up (their own formulas, values and
    method); anything else goes through :func:`_plain_steps`."""
    from .livecalc_work import worked_steps

    return worked_steps(node, sc, q, sig, conversion) or _plain_steps(node, sc, q, sig, conversion)


def _plain_steps(node: tuple, sc: Scope, q: Q, sig: int, conversion: list[dict] | None = None) -> list[dict]:
    """The working: the expression, the values substituted, what is converted to SI, and the result
    (``conversion`` are the steps of a requested ``to unit``, which replace the plain ‘express in’ step)."""
    steps = [{"label": "Expression", "latex": tex(node)}]
    if np.ndim(q.v) or _is_complex(q) or _has_special(node) or any(np.ndim(sc.vars[n].v) or _is_complex(sc.vars[n]) for n in names_in(node) if n in sc.vars):
        return steps + [{"label": "Result", "latex": rf"= {qty_texts(q, sig)[2]}"}]
    subst: dict[str, str] = {}
    for n in names_in(node):
        if n in sc.vars:
            subst[n] = qty_texts(sc.vars[n], sig)[2]
    consts = [n for n in _constants_in(node) if n not in sc.vars]
    if consts:
        lines = []
        for n in consts:
            cq = evaluate(("name", n), sc)
            subst[n] = qty_texts(cq, sig)[2]
            lines.append(rf"{name_tex(n)} = {subst[n]}\quad \text{{({QCONSTANTS[n][2]})}}")
        steps.append({"label": "Constants", "latex": lines})
    if subst:
        steps.append({"label": "Substitute the values", "latex": tex(node, subst)})
    leaves: list[tuple[float, Unit]] = []
    _leaf_quantities(node, sc, leaves)
    seen: set[str] = set()
    conv: list[str] = []
    for x, u in leaves:
        if u.is_identity:
            continue
        key = f"{x}|{u.symbol}"
        if key in seen:
            continue
        seen.add(key)
        si_u = _si_for(u, u.dim)
        conv.append(rf"{_num_tex(x, sig)}\,{unit_tex(u)} = {_num_tex(u.to_si(x), sig)}\,{unit_tex(si_u)}")
    if conv:
        steps.append({"label": "Convert to SI base units", "latex": conv[:8]})
    si_u = _si_unit(q)
    si_val = float(q.v)
    si_tex = rf"{_num_tex(si_val, sig)}\,{unit_tex(si_u)}".rstrip(r"\, ")
    if conversion:
        steps.append({"label": "Result in SI base units", "latex": rf"= {si_tex}"})
        steps.extend(conversion)
    elif q.unit is None or (q.unit.is_identity and q.unit.symbol == si_u.symbol):
        steps.append({"label": "Result", "latex": rf"= {si_tex}"})
    else:
        steps.append({"label": "Result in SI base units", "latex": rf"= {si_tex}"})
        steps.append({"label": f"Express in {q.unit.symbol}", "latex": rf"{si_tex} \to {qty_texts(q, sig)[2]}"})
    return steps


# ------------------------------------------------------------------ statements

def _is_ident(toks: list[Tok]) -> bool:
    return len(toks) == 2 and toks[0].kind == "id" and toks[0].text not in RESERVED


def _function_head(toks: list[Tok]) -> tuple[str, list[str]] | None:
    """`f(a, b)` as the left side of `=`: returns the name and parameter names."""
    if len(toks) < 4 or toks[0].kind != "id" or toks[1].text != "(" or toks[-1].text != ")":
        return None
    inner = toks[2:-1]
    params, expect_id = [], True
    for t in inner:
        if expect_id:
            if t.kind != "id" or t.text in RESERVED:
                return None
            params.append(t.text)
        elif t.text != ",":
            return None
        expect_id = not expect_id
    if (not inner) or expect_id:
        return None
    return toks[0].text, params


def _result(kind: str, line: int, text: str, **kw) -> dict:
    return {"line": line, "text": text, "kind": kind, **kw}


def _value_payload(q: Q, sig: int) -> dict:
    plain, sym, res_tex, _ = qty_texts(q, sig)
    if _is_complex(q):
        shown, si = np.asarray(q.shown), np.asarray(q.v)
        cap = (lambda a: np.asarray(a)[:MAX_LIST * 2].tolist()) if np.ndim(q.v) else (lambda a: float(a))
        d = {"value": cap(np.real(shown)), "value_im": cap(np.imag(shown)), "value_text": plain, "unit": sym, "result_latex": res_tex, "complex": True,
             "si_value": cap(np.real(si)), "si_value_im": cap(np.imag(si)), "si_unit": _si_unit(q).symbol if not q.dim.is_dimensionless else ""}
        if np.ndim(q.v):
            d.update({"is_list": True, "length": int(np.size(q.v)), "shape": list(np.shape(q.v))})
        elif (z := shown.item()) and min(abs(z.real), abs(z.imag)) > 1e-12 * abs(z):
            d["polar"] = polar_text(z, sig, sym)
        if not q.dim.is_dimensionless:
            d["kind_of_quantity"] = _reg().describe(q.dim)
        return d
    if np.ndim(q.v):
        d = {"value": _real(q.shown)[:MAX_LIST * 2].tolist(), "value_text": plain, "unit": sym, "result_latex": res_tex, "is_list": True, "length": int(np.size(q.v)),
             "shape": list(np.shape(q.v)), "si_value": _real(q.v)[:MAX_LIST * 2].tolist(), "si_unit": _si_unit(q).symbol if not q.dim.is_dimensionless else ""}
        if not q.dim.is_dimensionless:
            d["kind_of_quantity"] = _reg().describe(q.dim)
        return d
    d = {"value": float(q.shown), "value_text": plain, "unit": sym, "result_latex": res_tex,
         "si_value": float(q.v), "si_unit": _si_unit(q).symbol if not q.dim.is_dimensionless else ""}
    if not q.dim.is_dimensionless:
        d["kind_of_quantity"] = _reg().describe(q.dim)
    return d


class Session:
    """Evaluates statements in order, sharing one scope."""

    def __init__(self, sig: int = 6, angle: str = "rad"):
        self.sc = Scope()
        self.sc.angle = "deg" if angle == "deg" else "rad"
        self.sig = sig
        self.ans: Q | None = None

    def run_block(self, block: str) -> list[dict]:
        """Run one history entry (one or more lines; lines inside ``` fences are text) and return the result of each line."""
        out, fenced = [], False
        for i, line in enumerate(block.replace("\r\n", "\n").split("\n")):
            if line.strip().startswith("```"):
                fenced = not fenced
                out.append({"line": i + 1, "text": line, "kind": "text"})
            elif fenced:
                out.append({"line": i + 1, "text": line, "kind": "text"})
            else:
                out.append(self.run_line(line, i + 1))
        return out

    def _set_ans(self, q: Q) -> None:
        self.ans = q
        self.sc.vars["ans"] = q

    # parser factory: names that already mean something
    def parser(self, text: str, toks: list[Tok], extra: set[str] = frozenset(), bare_units: bool = True) -> Parser:
        return Parser(text, toks, set(self.sc.vars), set(self.sc.funcs), extra, bare_units)

    def run_line(self, raw: str, n: int) -> dict:
        text = raw.translate(_NORMALISE).strip()
        if not text:
            return _result("blank", n, raw)
        if len(text) > MAX_LINE:
            return _result("error", n, raw, error={"message": f"A line can have at most {MAX_LINE} characters"})
        if _MARKDOWN.match(text):
            return _result("text", n, raw)
        try:
            toks = tokenize(text)
        except LiveError as exc:
            if re.search(r"[\d=]", text):
                return _result("error", n, raw, error={"message": str(exc)})
            return _result("text", n, raw)
        if toks[0].text == "plot" and toks[0].kind == "id":
            return self._plot(raw, text, toks, n)
        try:
            res = self._statement(raw, text, toks, n)
            if res.get("polar"):
                res["notes"] = [*res.get("notes", []), f"Polar form: {res['polar']}"]
            return res
        except Undefined as exc:
            if not re.search(r"[\d=]", text) and "(" not in text:
                return _result("text", n, raw)
            return _result("error", n, raw, error={"message": str(exc), "name": exc.name})
        except SyntaxErr as exc:
            if self._prose(toks):
                return _result("text", n, raw)
            return _result("error", n, raw, error={"message": str(exc)})
        except (LiveError, UnitError) as exc:
            return _result("error", n, raw, error={"message": str(exc)})
        except ValueError as exc:
            if "broadcast" in str(exc):
                return _result("error", n, raw, error={"message": "These lists have different lengths"})
            raise
        except TypeError as exc:
            if "complex" in str(exc):
                return _result("error", n, raw, error={"message": "That does not work with complex numbers"})
            raise

    @staticmethod
    def _prose(toks: list[Tok]) -> bool:
        """A line that does not parse is prose unless it contains a number or an ‘=’ (it was meant as a calculation)."""
        if not any(t.kind == "num" or (t.kind == "op" and t.text == "=") for t in toks):
            return True
        words = [t for t in toks if t.kind != "end"]
        return any(a.kind == "id" and b.kind == "id" and a.text not in _KEYWORDS and b.text not in _KEYWORDS for a, b in itertools.pairwise(words))

    def _statement(self, raw: str, text: str, toks: list[Tok], n: int) -> dict:
        eqs, depth = [], 0
        for i, t in enumerate(toks):                       # an ‘=’ inside brackets is a named value, as in calc("id", v = 5 m/s)
            if t.kind == "op":
                depth += (t.text in "([") - (t.text in ")]")
                if t.text == "=" and depth == 0:
                    eqs.append(i)
        if len(eqs) > 1:
            raise LiveError("Only one ‘=’ can appear in a line")
        if eqs:
            return self._equation(raw, text, toks, eqs[0], n)
        return self._expression(raw, text, toks, n)

    # ---- expression, with optional conversion
    def _expression(self, raw: str, text: str, toks: list[Tok], n: int, name: str | None = None) -> dict:
        p = self.parser(text, toks)
        node = p.expr()
        target = None
        target_text = ""
        if p.at_kw("to") or p._conversion_in():
            kw = p.take()
            target_text = text[kw.end:].strip()
            if not target_text:
                raise LiveError("Say which unit to convert to, e.g. ‘to km/h’")
            try:
                target = _reg().parse(target_text)
            except UnitError as exc:
                raise LiveError(str(exc)) from None
            p.i = len(p.t) - 1
        p.finish()
        self.sc.work.clear()
        q = evaluate(node, self.sc)
        notes: list[str] = list(p.notes)
        conv: list[dict] = []
        steps_q = q
        if target is not None:
            q, conv, more = self._convert(q, target)
            notes += more
        steps = make_steps(node, self.sc, steps_q, self.sig, conv or None) if (conv or node[0] not in _LITERAL) else []
        payload = _value_payload(q, self.sig)
        expr_tex = tex(node)
        if target is not None:
            disp = rf"{expr_tex} \;\to\; {payload['result_latex']}"
        elif node[0] in ("num", "qty", "unit", "imag") or self._same_text(expr_tex, payload["result_latex"]):
            disp = payload["result_latex"]
        else:
            disp = rf"{expr_tex} = {payload['result_latex']}"
        self._set_ans(q)
        return _result("value", n, raw, display_latex=disp, expr_latex=expr_tex, steps=steps, notes=notes, **payload)

    @staticmethod
    def _same_text(a: str, b: str) -> bool:
        return re.sub(r"[\\,\s]", "", a) == re.sub(r"[\\,\s]", "", b)

    def _convert(self, q: Q, target: Unit) -> tuple[Q, list[dict], list[str]]:
        if q.dim != target.dim:
            raise LiveError(f"Cannot convert {_desc(q.dim)} ({q.unit.symbol if q.unit else 'no unit'}) to {_desc(target.dim)} ({target.symbol})")
        out = Q(q.v, q.dim, target)
        if np.ndim(q.v) or _is_complex(q):
            return out, [], list(target.notes)
        sig = self.sig
        si_u = _si_unit(q)
        si_tex = rf"{_num_tex(float(q.v), sig)}\,{unit_tex(si_u)}".rstrip(r"\, ")
        lines = []
        if not target.is_identity:
            if target.shift:
                lines.append(rf"{si_tex} \to \frac{{{_num_tex(float(q.v), sig)}}}{{{_num_tex(target.factor, sig)}}} - {_num_tex(target.shift, sig)} = {_num_tex(float(out.shown), sig)}\,{unit_tex(target)}")
            else:
                lines.append(rf"{si_tex} \times \frac{{1\,{unit_tex(target)}}}{{{_num_tex(target.factor, sig)}\,{unit_tex(si_u)}}} = {_num_tex(float(out.shown), sig)}\,{unit_tex(target)}")
        else:
            lines.append(rf"{si_tex} = {_num_tex(float(out.shown), sig)}\,{unit_tex(target)}")
        return out, [{"label": f"Convert to {target.symbol}", "latex": lines}], list(target.notes)

    # ---- assignments, functions, equations
    def _equation(self, raw: str, text: str, toks: list[Tok], eq: int, n: int) -> dict:
        lhs, rhs = toks[:eq] + [Tok("end", "", toks[eq].pos, toks[eq].pos)], toks[eq + 1:]
        if not rhs or rhs[0].kind == "end":
            raise LiveError("Nothing after ‘=’")
        head = _function_head(toks[:eq])
        if head is not None:
            return self._define_function(raw, text, head, rhs, n)
        if _is_ident(lhs):
            return self._assign(raw, text, lhs[0].text, rhs, n)
        return self._two_sided(raw, text, toks[:eq], rhs, n)

    def _define_function(self, raw: str, text: str, head: tuple[str, list[str]], rhs: list[Tok], n: int) -> dict:
        name, params = head
        if name in FUNCTIONS or name in CONSTANTS or name in self.sc.vars:
            raise LiveError(f"‘{name}’ is already taken; pick another name for the function")
        funcs = set(self.sc.funcs) | {name}
        p = Parser(text, rhs, set(self.sc.vars) | set(params), funcs, set(params), bare_units=False)
        body = p.expr()
        p.finish()
        fn = Func(tuple(params), body, text)
        self.sc.funcs[name] = fn
        latex = rf"{name_tex(name)}\left({', '.join(name_tex(a) for a in params)}\right) = {tex(body)}"
        return _result("function", n, raw, display_latex=latex, name=name, params=params)

    def _assign(self, raw: str, text: str, name: str, rhs: list[Tok], n: int) -> dict:
        if name in self.sc.funcs:
            raise LiveError(f"‘{name}’ is a function; pick another name")
        p = self.parser(text, rhs, bare_units=False)
        node = p.expr()
        target = None
        if p.at_kw("to") or p._conversion_in():
            kw = p.take()
            try:
                target = _reg().parse(text[kw.end:].strip())
            except UnitError as exc:
                raise LiveError(str(exc)) from None
            p.i = len(p.t) - 1
        p.finish()
        self.sc.work.clear()
        try:
            q = evaluate(node, self.sc)
        except Undefined:
            # not computable yet: keep it as an equation (a candidate for My equations)
            free = [x for x in names_in(node) if x not in self.sc.vars]
            return _result("equation", n, raw, display_latex=rf"{name_tex(name)} = {tex(node)}", name=name, free=free, formula=True,
                           notes=[f"Not evaluated: no value yet for {', '.join(free)}. Give them values, or send this equation to My equations."])
        notes: list[str] = list(p.notes)
        steps_q, conv = q, []
        if target is not None:
            q, conv, more = self._convert(q, target)
            notes += more
        steps = make_steps(node, self.sc, steps_q, self.sig, conv or None) if (conv or node[0] not in _LITERAL) else []
        self.sc.vars[name] = q
        self._set_ans(q)
        payload = _value_payload(q, self.sig)
        lhs = name_tex(name)
        expr_tex = tex(node)
        if node[0] in ("num", "qty", "unit", "imag") or self._same_text(expr_tex, payload["result_latex"]):
            disp = rf"{lhs} = {payload['result_latex']}"
        else:
            disp = rf"{lhs} = {expr_tex} = {payload['result_latex']}"
        return _result("assign", n, raw, display_latex=disp, expr_latex=expr_tex, name=name, steps=steps, notes=notes, formula=bool(names_in(node)), **payload)

    def _two_sided(self, raw: str, text: str, lhs: list[Tok], rhs: list[Tok], n: int) -> dict:
        lp = self.parser(text, lhs + [Tok("end", "", 0, 0)], bare_units=False)
        ln = lp.expr()
        lp.finish()
        rp = self.parser(text, rhs, bare_units=False)
        rn = rp.expr()
        rp.finish()
        notes = []
        try:
            a, b = evaluate(ln, self.sc), evaluate(rn, self.sc)
            if a.dim != b.dim:
                raise LiveError(f"The two sides have different units: {_desc(a.dim)} and {_desc(b.dim)}")
            tol = 1e-9 * max(abs(float(a.v)), abs(float(b.v)), 1e-300)
            same = abs(float(a.v) - float(b.v)) <= tol
            notes.append(("Both sides are equal: " if same else "The sides differ: ") + f"{qty_texts(a, self.sig)[0]} {qty_texts(a, self.sig)[1]} and {qty_texts(b, self.sig)[0]} {qty_texts(b, self.sig)[1]}".replace("  ", " "))
        except Undefined:
            free = [x for x in dict.fromkeys(names_in(ln) + names_in(rn)) if x not in self.sc.vars]
            notes.append(f"Not evaluated: no value yet for {', '.join(free)}.")
        free = [x for x in dict.fromkeys(names_in(ln) + names_in(rn)) if x not in self.sc.vars]
        return _result("equation", n, raw, display_latex=rf"{tex(ln)} = {tex(rn)}", formula=True, free=free, notes=notes)

    # ---- plots
    def _plot(self, raw: str, text: str, toks: list[Tok], n: int) -> dict:
        try:
            return self._plot_inner(raw, text, toks, n)
        except Undefined as exc:
            return _result("error", n, raw, error={"message": str(exc), "name": exc.name})
        except (LiveError, UnitError) as exc:
            return _result("error", n, raw, error={"message": str(exc)})

    def _plot_data(self, raw: str, text: str, body: list[Tok], n: int, logx: bool, logy: bool, equal: bool = False) -> dict:
        """plot data ys, or plot data xs, ys1, ys2: points from lists, joined by lines and marked."""
        p = Parser(text, [*body], set(self.sc.vars), set(self.sc.funcs), frozenset())
        nodes = [p.expr()]
        while p.at_op(","):
            p.take()
            nodes.append(p.expr())
        p.finish()
        if len(nodes) > 6:
            raise LiveError("A plot can show at most 5 curves")
        qs = [evaluate(nd, self.sc) for nd in nodes]
        for q in qs:
            if np.ndim(q.v) != 1:
                raise LiveError("plot data needs lists, e.g. plot data xs, ys")
        if len(qs) == 1:
            ys_q, x_q, x_nodes = qs, Q(np.arange(1, np.size(qs[0].v) + 1, dtype=float)), None
        else:
            x_q, ys_q, x_nodes = qs[0], qs[1:], nodes[0]
        for q in ys_q:
            if np.size(q.v) != np.size(x_q.v):
                raise LiveError("The lists must have the same length")
            if q.dim != ys_q[0].dim:
                raise LiveError(f"The curves have different units ({_desc(ys_q[0].dim)} and {_desc(q.dim)}) and cannot share one graph")
        xs = _real(x_q.v)
        if logx and not np.all(xs > 0):
            raise LiveError("A logarithmic x axis needs positive x values")
        xu, yu = x_q.unit, ys_q[0].unit
        series = []
        for nd, q in zip(nodes[(1 if x_nodes else 0):], ys_q):
            y = _real(q.v)
            if logy:
                y = np.where(y > 0, y, np.nan)
            series.append({"label_latex": tex(nd), "y": _clean(yu.from_si(y) if yu is not None else y)})
        if not any(v is not None for ser in series for v in ser["y"]):
            raise LiveError("There are no values to draw" + (" (a logarithmic axis needs positive values)" if logy else ""))
        plot = {"var": "x" if x_nodes else "index", "x": _clean(xu.from_si(xs) if xu is not None else xs), "x_unit": xu.symbol if xu is not None else "",
                "y_unit": yu.symbol if yu is not None else "", "series": series, "logx": logx, "logy": logy, "markers": True}
        _set_equal(plot, equal, xu, yu)
        return _result("plot", n, raw, plot=plot, display_latex=r",\;".join(s["label_latex"] for s in series),
                       steps=[{"label": "Plot of list values", "latex": [rf"{len(xs)}\ \text{{points}}"]}])

    def _plot_argand(self, raw: str, text: str, body: list[Tok], n: int) -> dict:
        """The complex plane: a complex number, or each number of a list, as a point (real part across, imaginary part up)."""
        if not body or body[0].kind == "end":
            raise LiveError("Give a complex number or a list of them: plot argand [1 + 2i, -1 + 0.5i]")
        p = Parser(text, [*body], set(self.sc.vars), set(self.sc.funcs), set())
        nd = p.expr()
        p.finish()
        q = evaluate(nd, self.sc)
        if q.affine:
            raise LiveError("Use K (or a temperature difference) here")
        z = np.atleast_1d(np.asarray(q.v)).astype(complex).ravel()
        u = q.unit
        re_s, im_s = (u.from_si(z.real), u.from_si(z.imag)) if u is not None else (z.real, z.imag)
        px, py = _clean(re_s), _clean(im_s)
        keep = [i for i in range(len(px)) if px[i] is not None and py[i] is not None]
        if not keep:
            raise LiveError("There are no finite values to draw")
        sym = u.symbol if u is not None else ""
        plot = {"var": "Re", "x": [px[i] for i in keep], "x_unit": sym, "y_unit": sym, "y_label": "Im", "series": [{"label_latex": tex(nd), "y": [py[i] for i in keep]}],
                "logx": False, "logy": False, "equal": True, "points": True, "markers": True}
        return _result("plot", n, raw, plot=plot, display_latex=plot["series"][0]["label_latex"], steps=[{"label": "Complex plane", "latex": [rf"{len(keep)}\ \text{{point{'s' if len(keep) != 1 else ''}}}"]}])

    def _plot_inner(self, raw: str, text: str, toks: list[Tok], n: int) -> dict:
        body = toks[1:]
        logx = logy = equal = twin = False
        while True:                                                             # plot ... from 1 to 1000 loglog equal twin: options at the end, in any order
            last = len(body) - 2 if body and body[-1].kind == "end" else len(body) - 1
            if not (last >= 0 and body[last].kind == "id" and body[last].text in ("logx", "logy", "loglog", "equal", "twin")):
                break
            word = body[last].text
            logx, logy = logx or word in ("logx", "loglog"), logy or word in ("logy", "loglog")
            equal, twin = equal or word == "equal", twin or word == "twin"
            body = body[:last] + body[last + 1:]
        parametric = bool(body) and body[0].kind == "id" and body[0].text == "parametric" and body[0].text not in self.sc.vars
        if parametric:
            body = body[1:]
        mode = body[0].text if body and body[0].kind == "id" and body[0].text in ("nyquist", "argand") and body[0].text not in self.sc.vars and body[0].text not in self.sc.funcs else None
        if mode:
            body = body[1:]
        if mode == "argand":
            return self._plot_argand(raw, text, body, n)
        nyquist = mode == "nyquist"
        if body and body[0].kind == "id" and body[0].text == "data" and "data" not in self.sc.vars and "data" not in self.sc.funcs:
            return self._plot_data(raw, text, body[1:], n, logx, logy, equal)
        var = None
        for i, t in enumerate(body):
            if t.kind == "id" and t.text == "for":
                if i + 1 >= len(body) or body[i + 1].kind != "id" or body[i + 1].text in RESERVED:
                    raise SyntaxErr("Write ‘for’ followed by the name of the variable, e.g. ‘for t’")
                var = body[i + 1].text
                break
        extra = {var} if var else set()
        p = Parser(text, [*body], set(self.sc.vars) | extra, set(self.sc.funcs), extra)
        nodes = [p.expr()]
        while p.at_op(","):
            p.take()
            nodes.append(p.expr())
        if p.at_kw("for"):
            p.take()
            p.take()
        lo = hi = None
        if p.at_kw("from"):
            p.take()
            lo = p.expr()
            if not p.at_kw("to"):
                raise LiveError("Write the range as ‘from A to B’")
            p.take()
            hi = p.expr()
        p.finish()
        if len(nodes) > 6:
            raise LiveError("A plot can show at most 6 curves")
        if parametric and len(nodes) != 2:
            raise LiveError("A parametric plot needs two expressions: plot parametric x(t), y(t) for t from 0 to 1")
        if nyquist and len(nodes) != 1:
            raise LiveError("A Nyquist plot takes one expression of the frequency, e.g. plot nyquist H(i*w) for w from 0.1 to 100")
        # a bare function name plots that function
        for i, nd in enumerate(nodes):
            if nd[0] == "name" and nd[1] in self.sc.funcs and len(self.sc.funcs[nd[1]].params) == 1:
                var = var or "x"
                nodes[i] = ("call", nd[1], [("name", var)])
        free: list[str] = []
        for nd in nodes:
            for nm in names_in(nd):
                if nm in self.sc.funcs and nm not in self.sc.vars and nm != var:
                    raise LiveError(f"‘{nm}’ is a function: write {nm}({', '.join(self.sc.funcs[nm].params)}) to plot something made from it")
                if nm not in self.sc.vars and nm not in free:
                    free.append(nm)
        if var is None:
            if len(free) == 1:
                var = free[0]
            elif not free:
                raise LiveError("Nothing to plot: use an unknown name such as x, or name the variable with ‘for’, e.g. ‘plot 0.5*a*t^2 for t from 0 s to 4 s’")
            elif "x" in free and len(free) > 1:
                raise LiveError(f"The plot depends on {', '.join(free)}: give all but one of them a value first")
            else:
                raise LiveError(f"The plot depends on {', '.join(free)}: give all but one of them a value first")
        elif var in self.sc.vars:
            raise LiveError(f"‘{var}’ already has a value; use another name for the plot variable")
        others = [f for f in free if f != var]
        if others:
            raise LiveError(f"No value yet for {', '.join(others)}")
        if lo is None and nyquist:
            a, b, logx = Q(0.01), Q(100.0), True                           # frequencies from 0.01 to 100, spaced logarithmically, unless a range is given
        elif lo is None:
            a, b = Q(-10.0), Q(10.0)
        else:
            a, b = evaluate(lo, self.sc), evaluate(hi, self.sc)
            if a.dim != b.dim:
                raise LiveError("The two ends of the range need the same units")
            if a.affine or b.affine:
                raise LiveError("Use K (or a temperature difference) for a plot range")
        if not (float(a.v) < float(b.v)):
            raise LiveError("The range must run from a smaller to a larger value")
        if logx and not float(a.v) > 0:
            raise LiveError("A logarithmic x axis needs a range that starts above zero")
        xs = np.geomspace(float(a.v), float(b.v), PLOT_POINTS) if logx else np.linspace(float(a.v), float(b.v), PLOT_POINTS)
        xunit = a.unit if a.unit is not None else None
        xq = Q(xs, a.dim, xunit)
        inner = self.sc.copy()
        inner.plotting = True
        inner.vars[var] = xq
        if nyquist:
            q = evaluate(nodes[0], inner)
            if q.affine:
                raise LiveError("A Nyquist plot needs a value without an offset unit")
            z = np.broadcast_to(np.asarray(q.v), xs.shape).astype(complex)
            u = q.unit
            re_s, im_s = (u.from_si(z.real), u.from_si(z.imag)) if u is not None else (z.real, z.imag)
            px = _clean(np.concatenate([re_s, re_s[::-1]]))                # the mirror image (negative frequencies) of a real system is added: the same real part, the opposite imaginary part
            py = _clean(np.concatenate([im_s, -im_s[::-1]]))
            if not any(v is not None for v in py):
                raise LiveError("The expression has no values on that range")
            sym = u.symbol if u is not None else ""
            plot = {"var": "Re", "param": var, "x": px, "x_unit": sym, "y_unit": sym, "y_label": "Im", "series": [{"label_latex": tex(nodes[0]), "y": py}], "logx": False, "logy": False, "equal": True}
            notes = []
            if q.dim.is_dimensionless:
                plot["marks"] = [{"x": -1.0, "y": 0.0, "label": "−1"}]                 # the critical point
                notes = _stability_margins(nodes[0], inner, var, xs, z, a)
            return _result("plot", n, raw, plot=plot, display_latex=plot["series"][0]["label_latex"], notes=notes,
                           steps=[{"label": "Nyquist plot", "latex": [rf"{name_tex(var)} \in [{_num_tex(float(a.shown))},\,{_num_tex(float(b.shown))}]", r"\text{and the mirror image for negative values of the variable; the critical point is } -1 + 0i"]}])
        if parametric:
            qx, qy = (evaluate(nd, inner) for nd in nodes)
            ux, uy = qx.unit, qy.unit
            vx, vy = (np.broadcast_to(_real(q.v), xs.shape) for q in (qx, qy))
            px, py = _clean(ux.from_si(vx) if ux is not None else vx), _clean(uy.from_si(vy) if uy is not None else vy)
            if not any(v is not None for v in py) or not any(v is not None for v in px):
                raise LiveError("The expression has no real values on that range")
            keep = [i for i in range(len(px)) if px[i] is not None]
            plot = {"var": "x", "param": var, "x": [px[i] for i in keep], "x_unit": ux.symbol if ux is not None else "", "y_unit": uy.symbol if uy is not None else "",
                    "series": [{"label_latex": rf"\left({tex(nodes[0])},\ {tex(nodes[1])}\right)", "y": [py[i] for i in keep]}], "logx": logx, "logy": logy}
            _set_equal(plot, equal, ux, uy)
            return _result("plot", n, raw, plot=plot, display_latex=plot["series"][0]["label_latex"],
                           steps=[{"label": "Parametric plot", "latex": [rf"{name_tex(var)} \in [{_num_tex(float(a.shown))},\,{_num_tex(float(b.shown))}]"]}])
        if twin and len(nodes) < 2:
            raise LiveError("‘twin’ needs at least two expressions: the last one is drawn against a second axis on the right")
        series, yunit, ydim, y2unit, y2dim = [], None, None, None, None
        for idx, nd in enumerate(nodes):
            q = evaluate(nd, inner)
            right = twin and idx == len(nodes) - 1
            if right:
                y2dim, y2unit = q.dim, q.unit
                unit_here = q.unit
            else:
                if ydim is None:
                    ydim, yunit = q.dim, q.unit
                elif q.dim != ydim:
                    raise LiveError(f"The curves have different units ({_desc(ydim)} and {_desc(q.dim)}) and cannot share one axis; add ‘twin’ to draw the last one against a second axis")
                unit_here = yunit
            yv = np.broadcast_to(_real(q.v), xs.shape)
            shown = unit_here.from_si(yv) if unit_here is not None else yv
            if logy:
                shown = np.where(_real(shown) > 0, shown, np.nan)                  # no point on a logarithmic axis at or below zero
            series.append({"label_latex": tex(nd), "y": _clean(shown), **({"axis": "right"} if right else {})})
        shown_x = xunit.from_si(xs) if xunit is not None else xs
        finite = [v for s in series for v in s["y"] if v is not None]
        if not finite:
            raise LiveError("The expression has no positive values on that range" if logy else "The expression has no real values on that range")
        plot = {"var": var, "x": _clean(shown_x), "x_unit": xunit.symbol if xunit is not None else "",
                "y_unit": yunit.symbol if yunit is not None else "", "series": series, "logx": logx, "logy": logy}
        if twin:
            plot["twin"] = True
            plot["y2_unit"] = y2unit.symbol if y2unit is not None else ""
        _set_equal(plot, equal, xunit, yunit)
        if equal and twin:
            raise LiveError("‘equal’ cannot be used with a second axis")
        return _result("plot", n, raw, plot=plot, display_latex=r",\;".join(s["label_latex"] for s in series),
                       steps=[{"label": "Plot", "latex": [rf"{name_tex(var)} \in [{_num_tex(float(a.shown))},\,{_num_tex(float(b.shown))}]" + (rf"\,{unit_tex(xunit)}" if xunit else ""),
                                                       rf"{PLOT_POINTS}\ \text{{points}}"]}])


def _stability_margins(node: tuple, sc: Scope, var: str, ws: np.ndarray, z: np.ndarray, a: Q) -> list[str]:
    """Gain and phase margin of a loop transfer function from its frequency response: where the curve crosses the negative real axis (gain margin) and the unit circle (phase margin)."""
    from scipy import optimize

    def at(w: float) -> complex:
        inner = sc.copy()
        inner.vars[var] = Q(float(w), a.dim, a.unit)
        return complex(np.asarray(evaluate(node, inner).v))

    def refine(f, i):                                                               # the root of f between samples i and i + 1
        try:
            return optimize.brentq(f, float(ws[i]), float(ws[i + 1]), xtol=1e-12 * float(ws[i + 1]), rtol=1e-12)
        except Exception:  # noqa: BLE001 - leave the margin out rather than guess
            return None

    out = []
    im = z.imag
    for i in range(len(ws) - 1):                                                    # phase crossover: the imaginary part changes sign while the real part is negative
        if im[i] == 0 or im[i] * im[i + 1] < 0:
            w = refine(lambda x: at(x).imag, i)
            if w is not None and at(w).real < 0:
                g = at(w).real
                out.append(f"Gain margin {fmt_number(1 / abs(g), 4)[0]} ({fmt_number(-20 * math.log10(abs(g)), 4)[0]} dB) at {var} = {fmt_number(w, 4)[0]}" if abs(g) < 1 else
                           f"Gain margin {fmt_number(1 / abs(g), 4)[0]} (below 1: the curve passes beyond −1, unstable as a closed loop) at {var} = {fmt_number(w, 4)[0]}")
                break
    mag = np.abs(z) - 1
    for i in range(len(ws) - 1):                                                    # gain crossover: the curve crosses the unit circle
        if mag[i] * mag[i + 1] < 0:
            w = refine(lambda x: abs(at(x)) - 1, i)
            if w is not None:
                pm = 180 + math.degrees(math.atan2(at(w).imag, at(w).real))
                pm = (pm + 180) % 360 - 180
                out.append(f"Phase margin {fmt_number(pm, 4)[0]}° at {var} = {fmt_number(w, 4)[0]}")
                break
    return out


def _set_equal(plot: dict, equal: bool, xu: Unit | None, yu: Unit | None) -> None:
    """``equal``: one unit of x is as long on the screen as one unit of y (needs the same unit on both axes)."""
    if not equal:
        return
    if plot.get("logx") or plot.get("logy"):
        raise LiveError("‘equal’ cannot be used with a logarithmic axis")
    if (xu.symbol if xu is not None else "") != (yu.symbol if yu is not None else ""):
        raise LiveError("‘equal’ needs the same unit on both axes")
    plot["equal"] = True


def _clean(arr: np.ndarray) -> list[float | None]:
    out: list[float | None] = []
    for v in _real(arr).tolist():
        out.append(float(f"{v:.7g}") if math.isfinite(v) else None)
    return out


def _variables(sess: Session) -> list[dict]:
    rows = []
    for name, q in sess.sc.vars.items():
        plain, sym, res_tex, _ = qty_texts(q, sess.sig)
        rows.append({"name": name, "latex": name_tex(name), "value_text": plain, "unit": sym, "result_latex": res_tex})
    for name, fn in sess.sc.funcs.items():
        rows.append({"name": f"{name}({', '.join(fn.params)})", "latex": rf"{name_tex(name)}\left({', '.join(name_tex(a) for a in fn.params)}\right)",
                     "value_text": "", "unit": "", "result_latex": tex(fn.body), "function": True})
    return rows


# ------------------------------------------------------------------ API

def livecalc_eval(entries: list | None = None, draft: str = "", sig_figs: int = 6, angle: str = "rad") -> dict:
    """Evaluate ``entries`` (earlier submissions, oldest first) and then ``draft`` (what is being typed), sharing one scope.

    Each entry is a string of one or more lines. Returns the result of every line of every entry and of the draft,
    plus the variables and functions that are defined at the end.
    """
    from .api import ApiError

    entries = [str(e) for e in (entries or [])]
    draft = str(draft or "")
    if len(entries) > MAX_ENTRIES:
        raise ApiError("Too many entries", "BAD_REQUEST")
    sig = max(3, min(12, int(sig_figs)))
    sess = Session(sig, angle)
    total = 0

    def run(block: str) -> list[dict]:
        nonlocal total
        out = []
        lines = block.replace("\r\n", "\n").split("\n")
        total += len(lines)
        if total > MAX_LINES:
            raise ApiError(f"At most {MAX_LINES} lines are evaluated at once", "BAD_REQUEST")
        fenced = False                      # lines inside ``` fences are text, never calculations
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                fenced = not fenced
                out.append({"line": i + 1, "text": line, "kind": "text"})
            elif fenced:
                out.append({"line": i + 1, "text": line, "kind": "text"})
            else:
                out.append(sess.run_line(line, i + 1))
        return out

    res_entries = [{"lines": run(e)} for e in entries]
    res_draft = {"lines": run(draft)} if draft.strip() else {"lines": []}
    return {"entries": res_entries, "draft": res_draft, "variables": _variables(sess)}


# ------------------------------------------------------------------ the library, as seen from LiveCalc

def _live_value(text: str) -> str:
    """An example value written the way LiveCalc reads it (a percentage is a plain fraction here)."""
    from .core.engine import parse_quantity

    try:
        val, unit = parse_quantity(str(text))
    except Exception:  # noqa: BLE001 - leave an example we cannot read as it is
        return str(text)
    unit = unit.strip()
    if unit == "%":
        return fmt_number(val / 100, 8)[0]
    if unit.startswith("1/"):                       # LiveCalc writes 5 1/s as 5/s
        return f"{fmt_number(val, 10)[0]}/{unit[2:]}"
    return str(text).strip()


def library_example(calc, out_key: str | None = None) -> str:
    """A ready-to-run ``calc(...)`` line for a calculation: its worked example's inputs and its first output."""
    out = out_key or (calc.outputs[0] if calc.outputs else "")
    args = ", ".join(f"{k} = {_live_value(calc.example[k])}" for k in calc.example if k != out and k in calc.by_key and not calc.by_key[k].is_constant)
    return f'calc("{calc.id}", "{out}", {args})'


def livecalc_library(query: str = "", limit: int = 12, sig_figs: int = 6) -> dict:
    """Library calculations that match ``query``, each with the variables you can give and an example ``calc(...)`` line that has been run."""
    from .core.catalog import default_catalog

    q = str(query or "").strip()[:80]
    if len(q) < 2:
        return {"items": [], "total": 0}
    found = default_catalog().search(q)
    items = []
    for c in found[: max(1, min(int(limit), 25))]:
        out = c.outputs[0] if c.outputs else ""
        line = library_example(c)
        ex = _run_example_line(line, sig_figs)
        items.append({"id": c.id, "name": c.name, "description": c.description[:240], "disciplines": c.disciplines[:3],
                      "inputs": [{"key": v.key, "label": v.label, "unit": v.unit} for v in c.variables if not v.is_constant and v.key != out],
                      "outputs": [{"key": k, "label": c.by_key[k].label, "unit": c.by_key[k].unit} for k in c.outputs],
                      "example": line, **ex})
    return {"items": items, "total": len(found)}


def _run_example_line(line: str, sig: int) -> dict:
    r = Session(max(3, min(12, int(sig)))).run_line(line, 1)
    if r["kind"] == "error":
        return {"ok": False, "error": r["error"]["message"]}
    return {"ok": True, "result_text": f"{r.get('value_text', '')} {r.get('unit', '')}".strip()}


# ------------------------------------------------------------------ exporting the history

def livecalc_export(entries: list | None = None, fmt: str = "markdown", title: str = "LiveCalc session", sig_figs: int = 6, angle: str = "rad", steps: bool = False) -> dict:
    """The history as a document. ``markdown``: text as typed, every calculation as a display equation with its result (with ``steps``, followed by its worked steps),
    errors marked; ``text``: the entries exactly as typed (one blank line between them), which LiveCalc can read back in."""
    from .api import ApiError

    entries = [str(e) for e in (entries or [])]
    if fmt == "text":
        return {"ok": True, "format": "text", "filename": "livecalc-session.txt", "content": "\n\n".join(e.rstrip() for e in entries) + ("\n" if entries else "")}
    if fmt in ("python", "notebook"):
        return _export_code(entries, fmt, str(title).strip()[:120] or "LiveCalc session", max(3, min(12, int(sig_figs))), "deg" if angle == "deg" else "rad")
    if fmt != "markdown":
        raise ApiError("Unknown export format", "BAD_REQUEST")
    res = livecalc_eval(entries=entries, draft="", sig_figs=sig_figs, angle=angle)
    out = [f"# {str(title).strip()[:120] or 'LiveCalc session'}", ""] + (["*Angles in degrees: a bare number given to sin, cos or tan is degrees.*", ""] if angle == "deg" else [])
    for e in res["entries"]:
        block: list[str] = []
        for ln in e["lines"]:
            k = ln["kind"]
            if k in ("text", "blank"):
                block.append(ln["text"] if k == "text" else "")
            elif k == "error":
                block += ["", f"`{ln['text'].strip()}` — **{ln['error']['message']}**", ""]
            elif k == "plot":
                block += ["", f"`{ln['text'].strip()}` (a graph; type the line in LiveCalc to draw it)", ""]
            else:
                block += ["", f"$$ {ln['display_latex']} $$", ""]
                if steps and ln.get("steps"):
                    block += _steps_markdown(ln["steps"])
        out += [*block, ""]
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"
    return {"ok": True, "format": "markdown", "filename": "livecalc-session.md", "content": text}


def _steps_markdown(steps: list[dict]) -> list[str]:
    """A numbered list of the worked steps: each label, then its equations as display maths."""
    out = ["**Working**", ""]
    for i, st in enumerate(steps, 1):
        lines = st["latex"] if isinstance(st["latex"], list) else [st["latex"]]
        out.append(f"{i}. *{st['label']}*")
        for t in lines:
            out += ["", f"   $$ {t} $$"]
        out.append("")
    return out


def result_line(ln: dict) -> str:
    """One evaluated line as plain text, the way the exported script and notebook print it."""
    k, text = ln["kind"], ln["text"].strip()
    if k in ("text", "blank"):
        return ""
    if k == "error":
        return f"{text}    ->  error: {ln['error']['message']}"
    if k == "plot":
        return f"{text}    ->  (a graph: run it in LiveCalc to see it)"
    if k == "function":
        return text
    val = ln.get("value_text", "")
    unit = ln.get("unit", "")
    shown = f"{val} {unit}".strip()
    return f"{ln.get('name')} = {shown}" if k == "assign" else f"{text}  =  {shown}"


_RUNNER = '''from sliderule.livecalc import Session, result_line

session = Session({sig}, "{angle}")


def show(entry):
    """Run one entry (one or more lines) in the shared session and print each result."""
    for ln in session.run_block(entry):
        if result_line(ln):
            print(result_line(ln))
'''


def _export_code(entries: list[str], fmt: str, title: str, sig: int, angle: str) -> dict:
    """The history as a Python script or a Jupyter notebook that re-runs it with SlideRule's own evaluator (so every number is the one LiveCalc showed).

    The notebook is saved with its outputs, computed here by the same evaluator. Neither is a translation into plain Python: the lines still go through
    LiveCalc, so units, library calls and plots behave exactly as they do there (plots are not drawn).
    """
    runner = _RUNNER.format(sig=sig, angle=angle)
    sess = Session(sig, angle)
    if fmt == "python":
        body = "\n".join(f"show({e.rstrip()!r})" for e in entries)
        head = f'"""{title}\n\nRe-runs a LiveCalc session with SlideRule\'s evaluator (pip install sliderule), so units, calc(...) library calls and every number are those LiveCalc showed.\nEdit, add lines with show("...") or run it as it is.\n"""\n'
        return {"ok": True, "format": "python", "filename": "livecalc-session.py", "content": f"{head}{runner}\n\n{body}\n"}
    cells: list[dict] = [{"cell_type": "markdown", "metadata": {}, "source": [f"# {title}\n", "\n", "A LiveCalc session re-run with SlideRule's own evaluator (`pip install sliderule`): units, `calc(...)` library calls and every number are those LiveCalc showed. Plots are not drawn here."]},
                         {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": runner.rstrip().splitlines(keepends=True)}]
    count = 0
    for e in entries:
        lines = sess.run_block(e)
        printed = [t for t in (result_line(ln) for ln in lines) if t]
        if not printed and all(ln["kind"] in ("text", "blank") for ln in lines):
            cells.append({"cell_type": "markdown", "metadata": {}, "source": e.rstrip().splitlines(keepends=True)})
            continue
        count += 1
        out = [{"output_type": "stream", "name": "stdout", "text": [t + "\n" for t in printed]}] if printed else []
        cells.append({"cell_type": "code", "execution_count": count, "metadata": {}, "outputs": out, "source": [f"show({e.rstrip()!r})"]})
    nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    return {"ok": True, "format": "notebook", "filename": "livecalc-session.ipynb", "content": json.dumps(nb, indent=1, ensure_ascii=False) + "\n"}


# ------------------------------------------------------------------ plotting the functions defined in the history

GRID_3D = 41                # points per axis of a surface
MAX_PLOTTED = 6             # functions in one plot


def _session_after(entries: list[str], sig: int, angle: str = "rad") -> Session:
    """A session that has run ``entries`` (nothing is reported; used to know which functions and variables exist)."""
    from .api import ApiError

    if len(entries) > MAX_ENTRIES:
        raise ApiError("Too many entries", "BAD_REQUEST")
    sess = Session(sig, angle)
    total = 0
    for block in entries:
        lines = block.replace("\r\n", "\n").split("\n")
        total += len(lines)
        if total > MAX_LINES:
            raise ApiError(f"At most {MAX_LINES} lines are evaluated at once", "BAD_REQUEST")
        fenced = False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                fenced = not fenced
            elif not fenced:
                sess.run_line(line, i + 1)
    return sess


def _range_end(sess: Session, text: str, what: str) -> Q:
    text = str(text or "").translate(_NORMALISE).strip()
    if not text:
        raise LiveError(f"Give the {what} of the range")
    toks = tokenize(text)
    p = sess.parser(text, toks)
    node = p.expr()
    p.finish()
    return evaluate(node, sess.sc)


def _axis(sess: Session, pair, name: str) -> tuple[np.ndarray, Q, Unit | None]:
    """The grid of an axis from ``[from, to]`` (quantities such as ‘-10’ or ‘0 s’)."""
    lo_t, hi_t = (list(pair or []) + ["", ""])[:2]
    a, b = _range_end(sess, lo_t, f"start of the {name} range"), _range_end(sess, hi_t, f"end of the {name} range")
    if a.dim != b.dim:
        raise LiveError(f"The two ends of the {name} range need the same units")
    if a.affine or b.affine:
        raise LiveError("Use K (or a temperature difference) for a plot range")
    if not float(a.v) < float(b.v):
        raise LiveError(f"The {name} range must run from a smaller to a larger value")
    return np.asarray([float(a.v), float(b.v)]), a, a.unit


def livecalc_plot(entries: list | None = None, functions: list | None = None, x: list | None = None, y: list | None = None, sig_figs: int = 6, angle: str = "rad") -> dict:
    """Plot functions defined in the history together: functions of one value as curves, of two values as surfaces.

    ``x`` and ``y`` are ``[from, to]`` ranges written like quantities (``"-10"``, ``"0 s"``); curves share ``x``, surfaces use ``x`` and ``y``.
    Curves with different units go into separate graphs (``curves``); surfaces likewise (``surfaces``). A function that cannot be plotted is
    listed in ``errors`` and does not stop the others.
    """
    entries = [str(e) for e in (entries or [])]
    names = [str(n) for n in (functions or [])][:MAX_PLOTTED]
    sig = max(3, min(12, int(sig_figs)))
    sess = _session_after(entries, sig, angle)
    sess.sc.plotting = True
    errors: list[dict] = []
    ones, twos = [], []
    for nm in names:
        fn = sess.sc.funcs.get(nm)
        if fn is None:
            errors.append({"name": nm, "message": "This function is no longer defined in the history"})
        elif len(fn.params) == 1:
            ones.append((nm, fn))
        elif len(fn.params) == 2:
            twos.append((nm, fn))
        else:
            errors.append({"name": nm, "message": "Only functions of one value (a curve) or two values (a surface) can be plotted"})
    curves, surfaces = [], []

    def label(nm: str, fn: Func) -> str:
        return rf"{name_tex(nm)}\left({', '.join(name_tex(a) for a in fn.params)}\right)"

    def run(nm: str, fn: Func, args: list[Q]) -> Q:
        try:
            return call_user(fn, nm, args, sess.sc, 0)
        except Undefined as exc:
            raise LiveError(f"No value yet for {exc.name}: give it one in the history first") from None

    if ones:
        try:
            ends, a, xunit = _axis(sess, x or ["-10", "10"], "x")
            xs = np.linspace(ends[0], ends[1], PLOT_POINTS)
            xq = Q(xs, a.dim, xunit)
            shown_x = xunit.from_si(xs) if xunit is not None else xs
            groups: dict = {}
            for nm, fn in ones:
                try:
                    q = run(nm, fn, [xq])
                    yv = np.broadcast_to(_real(q.v), xs.shape)
                    if not np.isfinite(yv).any():
                        raise LiveError("It has no real values on that range")
                    g = groups.setdefault(str(q.dim), {"unit": q.unit, "series": [], "vars": []})
                    shown = g["unit"].from_si(yv) if g["unit"] is not None else yv
                    g["series"].append({"name": nm, "label_latex": label(nm, fn), "y": _clean(shown)})
                    g["vars"].append(fn.params[0])
                except (LiveError, UnitError) as exc:
                    errors.append({"name": nm, "message": str(exc)})
            for g in groups.values():
                var = g["vars"][0] if len(set(g["vars"])) == 1 else "x"
                curves.append({"var": var, "x": _clean(shown_x), "x_unit": xunit.symbol if xunit is not None else "",
                               "y_unit": g["unit"].symbol if g["unit"] is not None else "", "series": g["series"]})
        except (LiveError, UnitError) as exc:
            errors += [{"name": nm, "message": str(exc)} for nm, _ in ones]
    if twos:
        try:
            xe, a, xunit = _axis(sess, x or ["-10", "10"], "x")
            ye, b, yunit = _axis(sess, y or ["-10", "10"], "y")
            xs, ys = np.linspace(xe[0], xe[1], GRID_3D), np.linspace(ye[0], ye[1], GRID_3D)
            gx, gy = np.meshgrid(xs, ys)
            groups = {}
            for nm, fn in twos:
                try:
                    q = run(nm, fn, [Q(gx, a.dim, xunit), Q(gy, b.dim, yunit)])
                    zv = np.broadcast_to(_real(q.v), gx.shape)
                    if not np.isfinite(zv).any():
                        raise LiveError("It has no real values on that range")
                    g = groups.setdefault(str(q.dim), {"unit": q.unit, "surfaces": [], "vars": []})
                    shown = g["unit"].from_si(zv) if g["unit"] is not None else zv
                    g["surfaces"].append({"name": nm, "label_latex": label(nm, fn), "z": [_clean(row) for row in shown]})
                    g["vars"].append(tuple(fn.params))
                except (LiveError, UnitError) as exc:
                    errors.append({"name": nm, "message": str(exc)})
            for g in groups.values():
                xv, yv = g["vars"][0] if len(set(g["vars"])) == 1 else ("x", "y")
                finite = [v for s in g["surfaces"] for row in s["z"] for v in row if v is not None]
                surfaces.append({"x_var": xv, "y_var": yv, "x": _clean(xunit.from_si(xs) if xunit is not None else xs), "y": _clean(yunit.from_si(ys) if yunit is not None else ys),
                                 "x_unit": xunit.symbol if xunit is not None else "", "y_unit": yunit.symbol if yunit is not None else "",
                                 "z_unit": g["unit"].symbol if g["unit"] is not None else "", "zmin": min(finite), "zmax": max(finite), "surfaces": g["surfaces"]})
        except (LiveError, UnitError) as exc:
            errors += [{"name": nm, "message": str(exc)} for nm, _ in twos]
    return {"curves": curves, "surfaces": surfaces, "errors": errors, "functions": [{"name": n, "params": list(f.params)} for n, f in sess.sc.funcs.items()]}


def _custom_text(text: str, toks: list[Tok], warnings: list[str]) -> str:
    """Rewrite function names the way My equations spells them, keeping the rest of the text as typed."""
    out, last = [], 0
    for t in toks:
        if t.kind == "id" and t.text in FUNCTIONS and t.text not in CONSTANTS:
            new = CUSTOM_NAME.get(t.text, t.text)
            if t.text in ("cbrt", "round"):
                warnings.append(f"{t.text}() is not available in My equations; rewrite it (for cbrt use ^(1/3)).")
            elif t.text in NOT_IN_CUSTOM:
                warnings.append(f"{t.text}() is not available in My equations; write out what it does (for hypot: sqrt(a^2 + b^2)).")
            if new != t.text:
                out.append(text[last:t.pos])
                out.append(new)
                last = t.end
    out.append(text[last:])
    return "".join(out)


def livecalc_to_equation(text: str, entries: list | None = None, sig_figs: int = 6, angle: str = "rad") -> dict:
    """Turn a typed equation (``F = m*a``) into a draft for the My equations editor, with units from the variables defined so far."""
    from .api import ApiError

    raw = str(text or "").strip()
    norm = raw.translate(_NORMALISE)
    if not norm:
        raise ApiError("Select an equation first", "BAD_REQUEST")
    if "\n" in norm:
        raise ApiError("Select one equation (a single line)", "BAD_REQUEST")
    if len(norm) > MAX_LINE:
        raise ApiError(f"An equation can have at most {MAX_LINE} characters", "BAD_REQUEST")
    try:
        toks = tokenize(norm)
    except LiveError as exc:
        raise ApiError(str(exc), "BAD_REQUEST") from None
    eqs = [i for i, t in enumerate(toks) if t.kind == "op" and t.text == "="]
    if len(eqs) != 1 or eqs[0] == 0 or toks[eqs[0] + 1].kind == "end":
        raise ApiError("Select an equation with one ‘=’, such as F = m*a", "NOT_AN_EQUATION")
    sess = Session(max(3, min(12, int(sig_figs))), angle)
    for e in (entries or [])[:60]:
        for line in str(e).replace("\r\n", "\n").split("\n")[:MAX_LINES]:
            sess.run_line(line, 0)
    warnings: list[str] = []
    if sess.sc.angle == "deg" and any(t.kind == "id" and (t.text in _ANGLE_IN or t.text in _ANGLE_OUT) for t in toks):
        warnings.append("LiveCalc is in degree mode, but My equations work in radians: angles in this equation must be radians (write 30 deg as a variable with the unit deg, or multiply a number by pi/180).")
    # names that appear in the equation, left side first
    names: list[str] = []
    for i, t in enumerate(toks):
        if t.kind == "id" and t.text not in FUNCTIONS and t.text not in CONSTANTS and t.text not in _KEYWORDS and t.text not in names:
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if nxt is not None and nxt.kind == "op" and nxt.text == "(" and t.text in sess.sc.funcs:
                warnings.append(f"{t.text}() is a LiveCalc function; write its formula into the equation instead.")
                continue
            names.append(t.text)
    # a number directly followed by a name is a unit literal in LiveCalc (5 m) but has no meaning inside an equation
    for a, b in itertools.pairwise(toks):
        if a.kind == "num" and b.kind == "id" and b.text not in _KEYWORDS and b.text not in sess.sc.vars:
            try:
                _reg().parse(b.text)
                warnings.append(f"‘{a.text} {b.text}’ looks like a quantity with a unit; My equations has no unit literals inside equations. Make it a variable (with that unit) or a constant.")
                break
            except UnitError:
                pass
    lhs_tokens = toks[:eqs[0]]
    out_name = lhs_tokens[0].text if len(lhs_tokens) == 1 and lhs_tokens[0].kind == "id" and lhs_tokens[0].text not in RESERVED else None
    variables = []
    for nm in names:
        v: dict[str, Any] = {"key": nm, "label": nm, "unit": ""}
        q = sess.sc.vars.get(nm)
        if q is not None:
            plain, sym, _, _ = qty_texts(q, sess.sig)
            v["unit"] = sym
            if nm != out_name:
                v["example"] = f"{plain} {sym}".strip()
        variables.append(v)
    # a result variable without a value: take the unit from the right-hand side when it can be evaluated
    if out_name and out_name not in sess.sc.vars:
        try:
            p = sess.parser(norm, toks[eqs[0] + 1:], set())
            node = p.expr()
            p.finish()
            q = evaluate(node, sess.sc)
            for v in variables:
                if v["key"] == out_name:
                    v["unit"] = q.unit.symbol if q.unit is not None else ""
        except (LiveError, UnitError):
            warnings.append("Some variables have no value in LiveCalc, so their units are blank: fill them in.")
    elif any(not v["unit"] for v in variables):
        pass
    if any(not v["unit"] for v in variables if v["key"] != out_name) and not any("blank" in w for w in warnings):
        blanks = [v["key"] for v in variables if not v["unit"]]
        if blanks and any(v["key"] not in sess.sc.vars for v in variables):
            warnings.append(f"No unit known for {', '.join(blanks)}: choose them in the editor (leave empty for a plain number).")
    if not out_name:
        warnings.append("The left side is not a single variable: in the editor, mark the variable(s) this equation can solve for.")
    text_out = _custom_text(norm, toks, warnings)
    calc = {
        "name": "", "description": f"From LiveCalc: {norm}",
        "disciplines": [], "variables": variables,
        "equations": [{"title": "", "text": text_out.strip()}],
        "outputs": [out_name] if out_name else [],
    }
    return {"calculation": calc, "warnings": list(dict.fromkeys(warnings))}
