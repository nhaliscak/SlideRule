"""Declarative definition of a calculation: variables with units + governing equations."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field, replace
from typing import Any

import sympy as sp
from sympy.parsing.sympy_parser import convert_xor, parse_expr, standard_transformations

from ..units import Dimension, Unit, default_registry
from .taxonomy import DISCIPLINES, SUBDISCIPLINES
from .calculus import evaluate as evaluate_calculus, has_calculus
from .dimcheck import _check_condition, check_equation

def _log_base(name: str, base: int):
    """Logarithm in a fixed base that stays symbolic but prints and evaluates sensibly."""

    def _eval_evalf(self, prec):
        return (sp.log(self.args[0]) / sp.log(base))._eval_evalf(prec)

    def _latex(self, printer, exp=None):
        power = "" if exp is None else "^{%s}" % exp
        return r"\log_{%d}%s\left(%s\right)" % (base, power, printer._print(self.args[0]))

    def fdiff(self, argindex=1):
        return 1 / (self.args[0] * sp.log(base))

    return type(name, (sp.Function,), {"nargs": 1, "_eval_evalf": _eval_evalf, "_latex": _latex, "fdiff": fdiff})


log10 = _log_base("log10", 10)
log2 = _log_base("log2", 2)


def _derivative(f, *args):
    """``diff(f, t)`` / ``diff(f, t, 2)`` as an unevaluated :class:`sympy.Derivative` (evaluated later, so the equation can be shown as written)."""
    if len(args) == 2 and isinstance(args[1], (int, sp.Integer)):
        return sp.Derivative(f, (args[0], int(args[1])))
    return sp.Derivative(f, *args)


def _integral(f, *limits):
    return sp.Integral(f, *limits)


def _summation(f, limits):
    """``summation(term, (n, first, last))`` as an unevaluated :class:`sympy.Sum` with whole-number limits; it is evaluated term by term, never expanded symbolically."""
    n, lo, hi = limits
    return sp.Sum(f, (n, sp.Integer(lo), sp.oo if hi == sp.oo else sp.Integer(hi)))


def _product(f, limits):
    """``product(term, (n, first, last))``: the factors written out (at most 50), so units and derivatives work as in any product."""
    n, lo, hi = limits
    lo, hi = int(lo), int(hi)
    if hi < lo or hi - lo + 1 > 50:
        raise ValueError("a product needs last >= first and at most 50 factors")
    return sp.Mul(*[sp.sympify(f).subs(n, sp.Integer(k)) for k in range(lo, hi + 1)])


def _split(z):
    """Real and imaginary parts of an expression of real symbols, with ``j`` the imaginary unit."""
    return sp.expand_complex(sp.sympify(z)).as_real_imag()


def _components(wl, wr):
    """The scalar equations a vector or matrix equation stands for: ``[(suffix, lhs, rhs), ...]`` (``None`` where the shapes disagree)."""
    lm, rm = isinstance(wl, sp.MatrixBase), isinstance(wr, sp.MatrixBase)
    if not lm and not rm:
        return [("", wl, wr)]
    if lm and rm and wl.shape != wr.shape or not (lm and rm):
        return None
    cols = wl.shape[1]
    out = []
    for i in range(wl.shape[0]):
        for j in range(cols):
            tag = f"[{i + 1}]" if cols == 1 else f"[{i + 1},{j + 1}]"
            out.append((f" {tag}", wl[i, j], wr[i, j]))
    return out


def _arg(z):
    re_, im_ = _split(z)
    return sp.atan2(im_, re_)


def _dot(a, b):
    return (sp.Matrix(a).T * sp.Matrix(b))[0, 0]


def _cross(a, b):
    a, b = sp.Matrix(a), sp.Matrix(b)
    if a.shape != (3, 1) or b.shape != (3, 1):
        raise ValueError("cross() needs two vectors of 3 components")
    return a.cross(b)


def _norm(a):
    return sp.sqrt(_dot(a, a))


def _det(a):
    a = sp.Matrix(a)
    if a.shape[0] != a.shape[1]:
        raise ValueError("det() needs a square matrix")
    return a.det(method="berkowitz")


_FUNCS = {
    "dot": _dot, "cross": _cross, "norm": _norm, "det": _det, "transpose": lambda a: sp.Matrix(a).T, "inv": lambda a: sp.Matrix(a).inv(),
    "trace": lambda a: sp.Matrix(a).trace(),
    "j": sp.I, "oo": sp.oo, "product": _product, "Re": lambda z: _split(z)[0], "Im": lambda z: _split(z)[1], "arg": _arg, "conjugate": lambda z: _split(z)[0] - sp.I * _split(z)[1],
    "diff": _derivative, "integrate": _integral, "summation": _summation,
    "sqrt": sp.sqrt, "exp": sp.exp, "log": sp.log, "ln": sp.log, "log10": log10, "log2": log2,
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh, "asinh": sp.asinh, "acosh": sp.acosh, "atanh": sp.atanh, "pi": sp.pi, "Abs": sp.Abs, "Min": sp.Min,
    "Max": sp.Max, "Piecewise": sp.Piecewise, "sign": sp.sign, "Eq": sp.Eq,
    "Or": sp.Or, "And": sp.And, "Not": sp.Not, "erf": sp.erf, "erfinv": sp.erfinv, "floor": sp.floor,
    "ceiling": sp.ceiling, "uppergamma": sp.uppergamma, "gamma": sp.gamma, "factorial": sp.factorial, "atan2": sp.atan2,
}
from .special import FUNCTIONS as _SPECIAL  # noqa: E402  (Bessel, Airy, elliptic, Lambert W, eigenvalue helpers)

_FUNCS.update(_SPECIAL)
_EQ_SPLIT = re.compile(r"(?<![<>=!])=(?!=)")
_TRANSFORMS = standard_transformations + (convert_xor,)


@dataclass
class Variable:
    key: str
    label: str
    unit: str                      # default display unit; also defines the dimension
    latex: str | None = None
    si: str | None = None          # coherent SI unit used internally (defaults from dimension)
    default: float | None = None   # default value, expressed in ``unit``
    min: float | None = None       # hard physical bounds, expressed in ``unit``
    max: float | None = None
    delta: bool = False            # temperature *difference*
    signed: bool = False           # may legitimately be negative
    constant: float | None = None  # if set, a fixed physical constant (in ``unit``)
    note: str = ""
    units: list[str] | None = None  # restrict the unit picker (e.g. ["dB"] for logarithmic levels)
    shape: tuple[int, ...] | None = None   # (n,) for a vector, (m, n) for a matrix: expanded into component variables key_1, key_2 ... / key_1_1 ...
    # filled by Calculation:
    dim: Dimension = field(init=False, repr=False)
    parsed: Unit = field(init=False, repr=False)
    si_parsed: Unit = field(init=False, repr=False)
    kinds: list[str] = field(init=False, default_factory=list)
    symbol: sp.Symbol = field(init=False, repr=False)

    def bind(self) -> None:
        reg = default_registry()
        self.parsed = reg.parse(self.unit, as_delta=self.delta)
        self.dim = self.parsed.dim
        self.si = self.si or reg.si_symbol(self.dim)
        self.si_parsed = reg.parse(self.si, as_delta=True)
        if self.si_parsed.dim != self.dim:
            raise ValueError(f"{self.key}: si unit {self.si!r} does not match dimension of {self.unit!r}")
        self.kinds = reg.kinds(self.dim)
        self.latex = self.latex or self.key
        self.symbol = sp.Symbol(self.key, real=True) if self.signed else sp.Symbol(self.key, positive=True)

    @property
    def is_constant(self) -> bool:
        return self.constant is not None

    def to_si(self, x: float) -> float:
        return self.parsed.to_si(x)


def V(key: str, label: str, unit: str, latex: str | None = None, **kw) -> Variable:
    return Variable(key, label, unit, latex, **kw)


def C(key: str, label: str, value: float, unit: str, latex: str | None = None, **kw) -> Variable:
    return Variable(key, label, unit, latex, constant=value, **kw)


@dataclass
class Equation:
    title: str
    text: str
    lhs: sp.Expr
    rhs: sp.Expr
    symbols: frozenset[sp.Symbol]
    written: tuple[sp.Expr, sp.Expr] | None = None   # (lhs, rhs) with derivatives/integrals unevaluated, when the text has any
    numeric_integral: bool = False                   # an integral without a closed form remains and is evaluated numerically
    ode: Any = None                                  # the OdeSystem this equation stands for (closed form or numerical solution), if any
    part: str = ""                                   # "re"/"im" (halves of a complex equation), "c<i>" (one component of a vector equation), or both; text is the whole equation
    source: str = ""                                 # the title of the written equation when it was split into several


@dataclass
class Calculation:
    id: str
    name: str
    disciplines: list[str]
    description: str
    variables: list[Variable]
    equations: list[str | tuple[str, str]]
    outputs: list[str]
    tags: list[str] = field(default_factory=list)
    subdisciplines: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    example: dict[str, str] = field(default_factory=dict)
    validity: list[tuple[str, str]] = field(default_factory=list)  # (condition, warning if false)
    custom: bool = False           # user-defined (parsed with the restricted expression checker)
    author: str = ""
    odes: list[dict] = field(default_factory=list)   # differential equations (initial-value problems), see core/ode.py
    tables: list[dict] = field(default_factory=list)  # tabulated data usable as functions in equations, see core/tables.py
    functions: list[dict] = field(default_factory=list)  # user-defined functions {"name", "args": [...], "body"}, expanded where they are called

    parsed_odes: list = field(init=False, repr=False, default_factory=list)
    declared: list = field(init=False, repr=False, default_factory=list)   # the variables as written, before vectors and matrices became components
    declared_outputs: list = field(init=False, repr=False, default_factory=list)
    arrays: dict = field(init=False, repr=False, default_factory=dict)     # vector/matrix key -> sympy Matrix of its component symbols

    parsed: list[Equation] = field(init=False, repr=False, default_factory=list)
    by_key: dict[str, Variable] = field(init=False, repr=False, default_factory=dict)
    parsed_validity: list[tuple[sp.Basic, str]] = field(init=False, repr=False, default_factory=list)

    def __post_init__(self) -> None:
        for d in self.disciplines:
            if d not in DISCIPLINES:
                raise ValueError(f"{self.id}: unknown discipline {d!r}")
        for s in self.subdisciplines:
            if s not in SUBDISCIPLINES:
                raise ValueError(f"{self.id}: unknown sub-discipline {s!r}")
        self.declared = list(self.variables)
        flat: list[Variable] = []
        shapes: dict[str, tuple[int, ...]] = {}
        for v in self.declared:
            if v.shape is None:
                flat.append(v)
                continue
            if v.constant is not None or not (1 <= len(v.shape) <= 2) or any(not (1 <= n <= 6) for n in v.shape):
                raise ValueError(f"{self.id}: {v.key}: a vector or matrix has one or two dimensions of 1 to 6 entries and cannot be a constant")
            shapes[v.key] = v.shape
            for idx in itertools.product(*[range(1, n + 1) for n in v.shape]):
                tag = ",".join(map(str, idx))
                flat.append(replace(v, key=f"{v.key}_" + "_".join(map(str, idx)), label=f"{v.label} [{tag}]", latex=f"{{{v.latex or v.key}}}_{{{tag}}}", shape=None, default=v.default))
        self.variables = flat
        self.declared_outputs = list(self.outputs)       # a vector or matrix named as an output stands for all of its components
        if shapes:
            self.outputs = [k for out in self.declared_outputs for k in ([c.key for c in flat if c.key.startswith(out + "_") and c.key[len(out) + 1:].replace("_", "").isdigit()] if out in shapes else [out])]
        for v in self.variables:
            if v.key in self.by_key:
                raise ValueError(f"{self.id}: duplicate variable {v.key!r}")
            v.bind()
            self.by_key[v.key] = v
        ns = {k: v.symbol for k, v in self.by_key.items()}
        for key, shape in shapes.items():
            rows, cols = (shape[0], 1) if len(shape) == 1 else shape
            self.arrays[key] = ns[key] = sp.Matrix(rows, cols, lambda i, j: ns[f"{key}_{i + 1}" if len(shape) == 1 else f"{key}_{i + 1}_{j + 1}"])
        ns = {**_FUNCS, **ns}  # variables win over sympy names (E, I, S, N ...)
        env = {v.symbol: (v.dim, _unit_expr(v)) for v in self.variables}
        for spec in self.tables:
            ns[spec["name"]] = self._build_table(spec, ns)
        for spec in self.functions:
            ns[spec["name"]] = self._build_function(spec, ns)
        used: set[sp.Symbol] = set()
        for i, item in enumerate(self.equations):
            title, text = item if isinstance(item, tuple) else (f"Equation {i + 1}" if len(self.equations) > 1 else "Governing equation", item)
            parts = _EQ_SPLIT.split(text)
            if len(parts) != 2:
                raise ValueError(f"{self.id}: equation must contain exactly one '=': {text!r}")
            if self.custom:
                from .safeparse import check_expression

                for part in parts:
                    check_expression(part, ns)
            from .safeparse import bound_names

            # a name used only as the variable of an integral is a dummy: it is not one of the calculation's variables
            dummies = {n for p in parts for n in bound_names(p)} - set(ns)
            local = {**ns, **{n: sp.Symbol(n, real=True) for n in dummies}}
            wl = parse_expr(parts[0], local_dict=local, transformations=_TRANSFORMS, evaluate=True)
            wr = parse_expr(parts[1], local_dict=local, transformations=_TRANSFORMS, evaluate=True)
            pairs = _components(wl, wr)
            if pairs is None:
                raise ValueError(f"{self.id}: {title}: a vector or matrix equation needs a vector or matrix of the same shape on both sides")
            for suffix, wl_k, wr_k in pairs:
                t = title + suffix
                part = f"c{suffix.strip(' []')}" if suffix else ""
                written, numeric_integral = None, False
                if has_calculus(wl_k) or has_calculus(wr_k):
                    try:
                        check_equation(wl_k, wr_k, env)      # as written: catches mistakes the evaluation would hide, e.g. diff(1 + x, x)
                        (lhs, nl), (rhs, nr) = evaluate_calculus(wl_k, self.custom), evaluate_calculus(wr_k, self.custom)
                        numeric_integral = nl or nr
                    except Exception as exc:
                        raise ValueError(f"{self.id}: {t}: {exc}") from exc
                    written = (wl_k, wr_k)
                else:
                    lhs, rhs = wl_k, wr_k
                syms = frozenset(lhs.free_symbols | rhs.free_symbols)
                try:
                    check_equation(lhs, rhs, env)
                except Exception as exc:
                    raise ValueError(f"{self.id}: {t}: {exc}") from exc
                if lhs.has(sp.I) or rhs.has(sp.I):
                    # a complex equation stands for two real ones: equal real parts and equal imaginary parts
                    (lr, li), (rr, ri) = _split(lhs), _split(rhs)
                    halves = [(p, a, b) for p, a, b in (("re", lr, rr), ("im", li, ri)) if sp.simplify(a - b) != 0]
                    if not halves:
                        raise ValueError(f"{self.id}: {t}: the equation is trivially true")
                    for p, a, b in halves:
                        try:
                            check_equation(a, b, env)
                        except Exception as exc:
                            raise ValueError(f"{self.id}: {t}: {exc}") from exc
                        hs = frozenset(a.free_symbols | b.free_symbols)
                        used |= hs
                        name = {"re": "real part", "im": "imaginary part"}[p]
                        self.parsed.append(Equation(f"{t} ({name})", text.strip(), a, b, hs, None, False, None, (part + " " + p).strip(), title))
                    continue
                used |= syms
                self.parsed.append(Equation(t, text.strip(), lhs, rhs, syms, written, numeric_integral, None, part, title if part else ""))
        if self.odes:
            from . import ode as _ode

            if len(self.odes) > 4:
                raise ValueError(f"{self.id}: at most 4 differential-equation systems per calculation")
            for k, spec in enumerate(self.odes):
                try:
                    system, eqs = _ode.build(spec, self, ns, env, self.custom, k)
                except (_ode.OdeSpecError, ValueError) as exc:
                    raise ValueError(f"{self.id}: differential equation {k + 1}: {exc}") from exc
                self.parsed_odes.append(system)
                for eq in eqs:
                    self.parsed.append(eq)
                    used |= eq.symbols
                used |= set(system.inputs) | set(getattr(system, "hidden", ()))
        for cond, message in self.validity:
            if self.custom:
                from .safeparse import check_expression

                check_expression(cond, ns)
            c = parse_expr(cond, local_dict=ns, transformations=_TRANSFORMS, evaluate=False)
            if has_calculus(c):
                raise ValueError(f"{self.id}: validity checks cannot contain derivatives or integrals: {cond!r}")
            _check_condition(c, env)
            self.parsed_validity.append((c, message))
        unused = [v.key for v in self.variables if v.symbol not in used]
        if unused:
            raise ValueError(f"{self.id}: variables never used in an equation: {unused}")
        for k in self.outputs:
            if k not in self.by_key or self.by_key[k].is_constant:
                raise ValueError(f"{self.id}: bad output {k!r}")
        for k in self.example:
            if k not in self.by_key:
                raise ValueError(f"{self.id}: example refers to unknown variable {k!r}")

    def _build_function(self, spec: dict, ns: dict):
        """A user-defined function: ``f(a, b)`` is replaced by its body with the arguments substituted, so units are checked and the equations solved exactly as if the body had been written out."""
        name, args, body = spec.get("name", ""), spec.get("args") or [], spec.get("body", "")
        ident = r"[A-Za-z][A-Za-z0-9_]{0,23}"
        if not isinstance(name, str) or not re.fullmatch(ident, name):
            raise ValueError(f"{self.id}: function name {name!r} must be a letter followed by letters, digits or underscores (at most 24)")
        if name in ns or name in self.by_key:
            raise ValueError(f"{self.id}: function name {name!r} is already used by a variable, table or function")
        if not isinstance(args, list) or not 1 <= len(args) <= 4 or len(set(args)) != len(args) or not all(isinstance(a, str) and re.fullmatch(ident, a) for a in args):
            raise ValueError(f"{self.id}: function {name}: give 1 to 4 different argument names")
        if not isinstance(body, str) or "=" in body.replace("==", "").replace("<=", "").replace(">=", "") or not body.strip():
            raise ValueError(f"{self.id}: function {name}: the body is an expression (no '=')")
        if self.custom:
            from .safeparse import check_expression

            check_expression(body, {**ns, **{a: None for a in args}})
        from .safeparse import bound_names

        params = [sp.Dummy(a, real=True) for a in args]
        local = {**ns, **{n: sp.Symbol(n, real=True) for n in bound_names(body) - set(ns) - set(args)}, **dict(zip(args, params))}
        try:
            expr = parse_expr(body, local_dict=local, transformations=_TRANSFORMS, evaluate=True)
        except Exception as exc:
            raise ValueError(f"{self.id}: function {name}: cannot read the body: {exc}") from exc
        if has_calculus(expr):
            raise ValueError(f"{self.id}: function {name}: derivatives, integrals and sums are not allowed in a function body")

        def call(*vals):
            if len(vals) != len(params):
                raise ValueError(f"{name}() takes {len(params)} argument{'s' if len(params) != 1 else ''}, got {len(vals)}")
            return expr.xreplace(dict(zip(params, [sp.sympify(v) for v in vals])))

        call.__name__ = name
        return call

    def _build_table(self, spec: dict, ns: dict):
        """The SymPy function for one table (values converted to coherent SI, units attached to the function)."""
        from . import tables as T
        from .units_expr import unit_expr_of

        name = spec.get("name", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,23}", name):
            raise ValueError(f"{self.id}: table name {name!r} must be a letter followed by letters, digits or underscores (at most 24)")
        if name in ns or name in self.by_key:
            raise ValueError(f"{self.id}: table name {name!r} is already used by a variable or function")
        reg = default_registry()
        try:
            xu, yu = reg.parse(spec.get("x_unit") or "1"), reg.parse(spec.get("y_unit") or "1")
            x, y = T.check_data(spec.get("x"), spec.get("y"), spec.get("method", "linear"), spec.get("outside", "error"))
        except Exception as exc:
            raise ValueError(f"{self.id}: table {name}: {exc}") from exc
        xs, ys = [xu.to_si(v) for v in x], [yu.to_si(v) for v in y]
        xsi, ysi = reg.parse(reg.si_symbol(xu.dim), as_delta=True), reg.parse(reg.si_symbol(yu.dim), as_delta=True)
        xe, ye = unit_expr_of(xsi), unit_expr_of(ysi)
        value, slope = (yu.dim, ye), (yu.dim / xu.dim, ye / xe)
        func, _ = T.make_functions(name, xs, ys, spec.get("method", "linear"), spec.get("outside", "error"), value, slope, (xu.dim, xe), display=name)
        return func

    # ---- convenience views
    @property
    def inputs(self) -> list[Variable]:
        return [v for v in self.variables if not v.is_constant]

    @property
    def constants(self) -> list[Variable]:
        return [v for v in self.variables if v.is_constant]

    def latex_names(self) -> dict[sp.Symbol, str]:
        return {v.symbol: v.latex for v in self.variables}


def _unit_expr(v: Variable) -> sp.Expr:
    from .units_expr import unit_expr_of

    return unit_expr_of(v.si_parsed)
