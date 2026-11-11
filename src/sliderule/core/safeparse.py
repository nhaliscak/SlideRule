"""Restricted checker for equation text that comes from users (typed in the editor or read from a shared file).

SymPy's ``parse_expr`` evaluates its input with Python's ``eval``, so text from outside the library is checked first:
it must parse as a plain Python *expression* built only from numbers, the calculation's own variable names, a short
list of mathematical functions, arithmetic/comparison/boolean operators and tuples (for ``Piecewise``). Attribute
access, subscripts, lambdas, comprehensions, strings, dunder names and calls to anything else are refused, as are
numeric literals and constant powers large enough to stall the solver.
"""

from __future__ import annotations

import ast
import math

MAX_TEXT = 300          # characters per expression
MAX_NODES = 300         # syntax-tree nodes per expression
MAX_LITERAL = 1e15      # largest number that may be written literally
MAX_CONST_POW = 1000    # largest exponent in a purely numeric power
MAX_FACTORIAL_ARG = 170
CALCULUS = ("diff", "integrate", "summation", "product")
MAX_SUM_TERMS = 500
MAX_CALCULUS_CALLS = 4
MAX_DERIVATIVE_ORDER = 4

_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.BitAnd, ast.BitOr)
_UNARY = (ast.UAdd, ast.USub, ast.Invert)
_COMPARE = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)


class UnsafeExpression(ValueError):
    pass


def _numeric_only(node: ast.AST) -> bool:
    return not any(isinstance(n, (ast.Name, ast.Call)) for n in ast.walk(node))


def _literal(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _literal(node.operand)
    return None


def _eval_numeric(node: ast.AST) -> float:
    """Evaluate a purely numeric subtree with bounded magnitudes, so a constant power cannot blow up."""
    v = _literal(node)
    if v is not None:
        return v
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        a, b = _eval_numeric(node.left), _eval_numeric(node.right)
        try:
            if isinstance(node.op, ast.Add):
                r = a + b
            elif isinstance(node.op, ast.Sub):
                r = a - b
            elif isinstance(node.op, ast.Mult):
                r = a * b
            elif isinstance(node.op, ast.Div):
                r = a / b
            else:
                if abs(b) > MAX_CONST_POW or abs(a) > 1e6:
                    raise UnsafeExpression("a purely numeric power is too large to evaluate")
                r = a ** b
        except (ZeroDivisionError, OverflowError):
            raise UnsafeExpression("a purely numeric part divides by zero or overflows") from None
        if isinstance(r, complex) or not math.isfinite(r) or abs(r) > 1e300:
            raise UnsafeExpression("a purely numeric part is out of range")
        return r
    raise UnsafeExpression("this numeric expression is not allowed in a power")


def _calculus_calls(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in CALCULUS]


def bound_names(text: str) -> set[str]:
    """Names introduced as the variable of a ``diff(...)`` or ``integrate(..., (x, a, b))`` call in ``text``."""
    try:
        tree = ast.parse(text.strip().replace("^", "**"), mode="eval")
    except SyntaxError:
        return set()
    out: set[str] = set()
    for call in _calculus_calls(tree):
        for a in call.args[1:]:
            if isinstance(a, ast.Name):
                out.add(a.id)
            elif isinstance(a, ast.Tuple) and a.elts and isinstance(a.elts[0], ast.Name):
                out.add(a.elts[0].id)
    return out


def _check_calculus(call: ast.Call, names: dict) -> None:
    fn, args = call.func.id, call.args
    if fn == "diff":
        if len(args) < 2 or not isinstance(args[1], ast.Name):
            raise UnsafeExpression("diff needs an expression and the variable to differentiate by: diff(f, t) or diff(f, t, 2)")
        var = args[1].id
        if var not in names or callable(names[var]):
            raise UnsafeExpression(f"diff(…, {var}): {var!r} must be one of the calculation's variables")
        if len(args) == 3 and isinstance(args[2], ast.Name):          # a mixed derivative, diff(u, x, y)
            if args[2].id not in names or callable(names[args[2].id]):
                raise UnsafeExpression(f"diff(…, {var}, {args[2].id}): {args[2].id!r} must be one of the calculation's variables")
            return
        if len(args) > 3 or (len(args) == 3 and not (isinstance(args[2], ast.Constant) and isinstance(args[2].value, int)
                                                       and 1 <= args[2].value <= MAX_DERIVATIVE_ORDER)):
            raise UnsafeExpression(f"the order of a derivative must be a whole number from 1 to {MAX_DERIVATIVE_ORDER} (or a second variable for a mixed derivative: diff(u, x, y))")
        return
    if fn in ("summation", "product"):
        if len(args) != 2 or not (isinstance(args[1], ast.Tuple) and len(args[1].elts) == 3 and isinstance(args[1].elts[0], ast.Name)):
            raise UnsafeExpression(f"a {'sum' if fn == 'summation' else 'product'} is written {fn}(term, (n, first, last)), e.g. summation(sin(n*x)/n, (n, 1, 50))")
        ints = []
        for k, e in enumerate(args[1].elts[1:]):
            if k == 1 and isinstance(e, ast.Name) and e.id == "oo" and fn == "summation":
                ints.append(None)                     # an infinite series: summation(term, (n, 1, oo))
                continue
            neg = isinstance(e, ast.UnaryOp) and isinstance(e.op, ast.USub)
            c = e.operand if neg else e
            if not (isinstance(c, ast.Constant) and isinstance(c.value, int) and not isinstance(c.value, bool)):
                raise UnsafeExpression("the first and last index of a sum must be whole-number literals (or oo for the last), e.g. (n, 1, 50) or (n, 1, oo)")
            ints.append(-c.value if neg else c.value)
        limit = MAX_SUM_TERMS if fn == "summation" else 50
        if ints[1] is not None and (ints[1] < ints[0] or ints[1] - ints[0] + 1 > limit):
            raise UnsafeExpression(f"a {'sum' if fn == 'summation' else 'product'} needs last >= first and at most {limit} terms" + (" (use oo as the last index for an infinite series)" if fn == "summation" else ""))
        return
    if len(args) < 2:
        raise UnsafeExpression("integrate needs the integrand and the limits: integrate(f, (x, a, b))")
    for lim in args[1:]:
        if not (isinstance(lim, ast.Tuple) and len(lim.elts) == 3 and isinstance(lim.elts[0], ast.Name)):
            raise UnsafeExpression("integrals must be definite: integrate(f, (x, lower, upper))")
        dummy = lim.elts[0].id
        if any(isinstance(n, ast.Name) and n.id == dummy for e in lim.elts[1:] for n in ast.walk(e)):
            raise UnsafeExpression(f"the limits of an integral over {dummy} cannot depend on {dummy}")


def check_expression(text: str, names: dict) -> None:
    """Raise :class:`UnsafeExpression` unless ``text`` is a permitted expression. ``names`` maps allowed identifiers.

    ``diff`` and ``integrate`` are allowed (see :func:`bound_names`); the variable an integral runs over need not be one of ``names``."""
    if len(text) > MAX_TEXT:
        raise UnsafeExpression(f"expression is longer than {MAX_TEXT} characters")
    try:
        tree = ast.parse(text.strip().replace("^", "**"), mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpression(f"cannot read {text.strip()!r}: {exc.msg}") from None
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise UnsafeExpression("expression is too complicated")
    calculus = _calculus_calls(tree)
    if len(calculus) > MAX_CALCULUS_CALLS:
        raise UnsafeExpression(f"more than {MAX_CALCULUS_CALLS} derivatives/integrals in one expression")
    for call in calculus:
        _check_calculus(call, names)
    names = {**names, **{n: None for n in bound_names(text)}}
    called = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
    for n in nodes:
        if isinstance(n, (ast.Expression, ast.Load, ast.Tuple, ast.operator, ast.unaryop, ast.cmpop, ast.boolop)):
            if isinstance(n, ast.operator) and not isinstance(n, _BINOPS):
                raise UnsafeExpression(f"operator {type(n).__name__} is not allowed")
            if isinstance(n, ast.unaryop) and not isinstance(n, _UNARY):
                raise UnsafeExpression("this unary operator is not allowed")
            if isinstance(n, ast.cmpop) and not isinstance(n, _COMPARE):
                raise UnsafeExpression("this comparison is not allowed")
        elif isinstance(n, (ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp)):
            pass
        elif isinstance(n, ast.Constant):
            v = n.value
            if isinstance(v, bool):
                continue
            if not isinstance(v, (int, float)):
                raise UnsafeExpression("only numbers may appear as literals")
            if not math.isfinite(v) or abs(v) > MAX_LITERAL:
                raise UnsafeExpression(f"number {v!r} is out of range")
        elif isinstance(n, ast.Name):
            if n.id.startswith("_") or n.id not in names:
                what = "function" if id(n) in called else "name"
                raise UnsafeExpression(f"unknown {what} {n.id!r}")
        elif isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.keywords or any(isinstance(a, ast.Starred) for a in n.args):
                raise UnsafeExpression("only plain function calls such as sqrt(x) are allowed")
            if n.func.id == "factorial":
                for a in n.args:
                    if _numeric_only(a):
                        v = _literal(a)
                        if v is None or abs(v) > MAX_FACTORIAL_ARG:
                            raise UnsafeExpression("factorial argument is too large")
        else:
            raise UnsafeExpression(f"{type(n).__name__} expressions are not allowed")
    for n in nodes:
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow) and _numeric_only(n):
            _eval_numeric(n)
