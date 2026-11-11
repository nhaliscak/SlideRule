"""Worked steps for LiveCalc's statistics, vector and matrix functions: the definition with the numbers put in, so ``mean(2 m, 4 m, 9 m)`` shows
(2 + 4 + 9)/3 and not just 5 m.

Each explainer takes the evaluated arguments and the result and returns the middle steps (the line's own Expression and closing Result are added by
the caller). Numbers are shown in the unit the values were typed in (the first argument's unit for lists); every number shown is recomputed here with
numpy from the arguments, and the tests compare them with an independent calculation. An explainer that does not apply raises ``NoExplanation`` and
the line keeps its plain steps.
"""

from __future__ import annotations

import numpy as np

from . import livecalc as L

MAX_SHOWN = 10         # terms listed before the rest is abbreviated


class NoExplanation(Exception):
    pass


# ------------------------------------------------------------------ helpers

class _Fmt:
    def __init__(self, sig: int):
        self.sig = sig

    def n(self, x) -> str:
        return L._num_tex(float(np.real(x)), self.sig)

    def q(self, q: L.Q) -> str:
        return L.qty_texts(q, self.sig)[2]

    @staticmethod
    def u(q: L.Q, power: int = 1) -> str:
        """The unit of ``q`` as a LaTeX suffix (empty when it has none), raised to ``power``."""
        if q.unit is None or q.unit.symbol in ("", "1"):
            return ""
        t = L.unit_tex(q.unit)
        return rf"\,{t}" if power == 1 else rf"\,\left({t}\right)^{{{power}}}"

    def terms(self, xs: list[str], joiner: str = " + ", limit: int = MAX_SHOWN) -> str:
        if len(xs) > limit:
            xs = xs[: limit - 2] + [r"\cdots"] + xs[-1:]
        return joiner.join(xs)


def _scalars(args: list[L.Q]) -> list[L.Q]:
    """The values an aggregate works on: the single list given, or the separate values."""
    if len(args) == 1 and np.ndim(args[0].v) == 1:
        a = args[0]
        return [L.Q(float(v), a.dim, a.unit) for v in np.real(a.v)]
    if all(np.ndim(a.v) == 0 for a in args):
        return list(args)
    raise NoExplanation


def _shown(q: L.Q) -> float:
    return float(q.unit.from_si(q.v)) if q.unit is not None else float(q.v)


def _vals(args: list[L.Q], unit_of: L.Q | None = None) -> list[float]:
    """The values in the unit of ``unit_of`` (default: the first value's own unit)."""
    xs = _scalars(args)
    ref = unit_of or xs[0]
    return [float(ref.unit.from_si(x.v)) if ref.unit is not None else float(x.v) for x in xs]


def _arr(q: L.Q) -> np.ndarray:
    a = np.asarray(q.shown, dtype=float if np.isrealobj(q.shown) else complex)
    if np.iscomplexobj(a):
        raise NoExplanation
    return a


def _matrix(rows: np.ndarray, f: _Fmt) -> str:
    return r"\begin{bmatrix}" + r" \\ ".join(" & ".join(f.n(c) for c in r) for r in rows) + r"\end{bmatrix}"


def _step(label: str, *lines: str) -> dict:
    return {"label": label, "latex": list(lines) if len(lines) > 1 else lines[0]}


# ------------------------------------------------------------------ aggregates over several values

def _sum(args, res, f):
    xs = _vals(args, res)
    return [_step("Add the values", rf"{f.terms([f.n(x) for x in xs])} = {f.n(sum(xs))}{f.u(res)}")]


def _mean(args, res, f):
    xs = _vals(args, res)
    return [_step("Add the values", rf"{f.terms([f.n(x) for x in xs])} = {f.n(sum(xs))}{f.u(res)}"),
            _step("Divide by the number of values", rf"\frac{{{f.n(sum(xs))}{f.u(res)}}}{{{len(xs)}}} = {f.n(sum(xs) / len(xs))}{f.u(res)}")]


def _median(args, res, f):
    xs = sorted(_vals(args, res))
    n = len(xs)
    srt = _step("Put the values in order", rf"{f.terms([f.n(x) for x in xs])}")
    if n % 2:
        return [srt, _step("Take the middle one", rf"\text{{value {n // 2 + 1} of {n}}} = {f.n(xs[n // 2])}{f.u(res)}")]
    a, b = xs[n // 2 - 1], xs[n // 2]
    return [srt, _step("Average the two middle ones", rf"\frac{{{f.n(a)} + {f.n(b)}}}{{2}} = {f.n((a + b) / 2)}{f.u(res)}")]


def _variance_steps(xs: list[float], res: L.Q, f: _Fmt, root: bool) -> list[dict]:
    n = len(xs)
    m = sum(xs) / n
    d = [x - m for x in xs]
    steps = [_step("Mean", rf"\bar x = \frac{{{f.terms([f.n(x) for x in xs])}}}{{{n}}} = {f.n(m)}"),
             _step("Deviations from the mean", rf"x_i - \bar x:\ {f.terms([f.n(x) for x in d], ',\\ ')}"),
             _step("Sum of the squared deviations", rf"{f.terms([f.n(x * x) for x in d])} = {f.n(sum(x * x for x in d))}"),
             _step(f"Divide by n − 1 = {n - 1}", rf"s^2 = \frac{{{f.n(sum(x * x for x in d))}}}{{{n - 1}}} = {f.n(sum(x * x for x in d) / (n - 1))}")]
    if root:
        steps.append(_step("Square root", rf"s = \sqrt{{{f.n(sum(x * x for x in d) / (n - 1))}}} = {f.n(np.sqrt(sum(x * x for x in d) / (n - 1)))}{f.u(res)}"))
    return steps


def _stdev(args, res, f):
    return _variance_steps(_vals(args, res), res, f, True)


def _var(args, res, f):
    xs = _vals([L.Q(a, args[0].dim, args[0].unit) for a in np.real(args[0].v)] if np.ndim(args[0].v) == 1 else args, args[0])
    return _variance_steps(xs, res, f, False)


def _prod(args, res, f):
    xs = _vals(args, args[0] if np.ndim(args[0].v) == 0 else _scalars(args)[0])
    return [_step("Multiply the values", rf"{f.terms([f.n(x) for x in xs], r' \cdot ')} = {f.n(np.prod(xs))}")]


def _minmax(name):
    def run(args, res, f):
        xs = _vals(args, res)
        pick = (min if name == "min" else max)(xs)
        word = "smallest" if name == "min" else "largest"
        return [_step(f"The {word} of the values", rf"{f.terms([f.n(x) for x in xs], ',\\ ')} \;\Rightarrow\; {f.n(pick)}{f.u(res)}")]
    return run


def _hypot(args, res, f):
    xs = _vals(args, res)
    return [_step("Square and add", rf"{f.terms([f.n(x) + '^2' for x in xs])} = {f.n(sum(x * x for x in xs))}{f.u(res, 2)}"),
            _step("Square root", rf"\sqrt{{{f.n(sum(x * x for x in xs))}}} = {f.n(np.sqrt(sum(x * x for x in xs)))}{f.u(res)}")]


def _norm(args, res, f):
    a = _arr(args[0]).ravel()
    return [_step("Square and add the entries", rf"{f.terms([f.n(x) + '^2' for x in a])} = {f.n(np.sum(a * a))}{f.u(res, 2)}"),
            _step("Square root", rf"\sqrt{{{f.n(np.sum(a * a))}}} = {f.n(np.sqrt(np.sum(a * a)))}{f.u(res)}")]


def _mod(args, res, f):
    a, b = (_shown(args[0]), float(args[1].unit.from_si(args[1].v)) if args[1].unit is not None else float(args[1].v))
    return [_step("a − b · ⌊a/b⌋", rf"{f.n(a)} - {f.n(b)} \cdot \left\lfloor \frac{{{f.n(a)}}}{{{f.n(b)}}} \right\rfloor = {f.n(a)} - {f.n(b)} \cdot {int(np.floor(a / b))} = {f.n(a - b * np.floor(a / b))}{f.u(res)}")]


def _factorial(args, res, f):
    n = int(round(float(args[0].v)))
    chain = " \\cdot ".join(str(k) for k in range(n, 0, -1)) if n <= 10 else " \\cdot ".join([str(n), str(n - 1), str(n - 2), r"\cdots", "2", "1"])
    return [_step("Multiply down to 1", rf"{n}! = {chain} = {f.n(res.v)}")] if n >= 2 else None


# ------------------------------------------------------------------ vectors

def _dot(args, res, f):
    a, b = _arr(args[0]).ravel(), _arr(args[1]).ravel()
    return [_step("Multiply component by component and add", rf"{f.terms([f'({f.n(x)})({f.n(y)})' for x, y in zip(a, b)])} = {f.n(np.dot(a, b))}{f.u(res)}")]


def _cross(args, res, f):
    a, b = _arr(args[0]).ravel(), _arr(args[1]).ravel()
    if a.size != 3 or b.size != 3:
        raise NoExplanation
    c = np.cross(a, b)
    return [_step("Components", r"\left(a_2 b_3 - a_3 b_2,\ a_3 b_1 - a_1 b_3,\ a_1 b_2 - a_2 b_1\right)"),
            _step("With the values", rf"\left(({f.n(a[1])})({f.n(b[2])}) - ({f.n(a[2])})({f.n(b[1])}),\ ({f.n(a[2])})({f.n(b[0])}) - ({f.n(a[0])})({f.n(b[2])}),\ "
                                      rf"({f.n(a[0])})({f.n(b[1])}) - ({f.n(a[1])})({f.n(b[0])})\right) = \left({f.n(c[0])},\ {f.n(c[1])},\ {f.n(c[2])}\right)")]


def _outer(args, res, f):
    a, b = _arr(args[0]).ravel(), _arr(args[1]).ravel()
    return [_step("Entry (i, j) is aᵢ · bⱼ", rf"\left(\text{{first row}}\right):\ {f.terms([f'({f.n(a[0])})({f.n(y)})' for y in b], ',\\ ')}")]


def _cumsum(args, res, f):
    a = _arr(args[0]).ravel()
    run = np.cumsum(a)
    return [_step("Running totals", rf"{f.terms([f.n(x) for x in run], ',\\ ')}")]


def _diff(args, res, f):
    a = _arr(args[0]).ravel()
    return [_step("Differences of neighbours", rf"{f.terms([f'{f.n(b)} - {f.n(c)}' for c, b in zip(a[:-1], a[1:])], ',\\ ')} = {f.terms([f.n(x) for x in np.diff(a)], ',\\ ')}")]


def _sort(args, res, f):
    return [_step("Smallest first", rf"{f.terms([f.n(x) for x in np.sort(_arr(args[0]).ravel())], ',\\ ')}")]


def _reverse(args, res, f):
    return [_step("Last to first", rf"{f.terms([f.n(x) for x in _arr(args[0]).ravel()[::-1]], ',\\ ')}")]


# ------------------------------------------------------------------ tables and fits

def _trapz(args, res, f):
    xs, ys = _arr(args[0]).ravel(), _arr(args[1]).ravel()
    areas = [(x2 - x1) * (y1 + y2) / 2 for x1, x2, y1, y2 in zip(xs[:-1], xs[1:], ys[:-1], ys[1:])]
    terms = [rf"\frac{{({f.n(x2)} - {f.n(x1)})({f.n(y1)} + {f.n(y2)})}}{{2}}" for x1, x2, y1, y2 in zip(xs[:-1], xs[1:], ys[:-1], ys[1:])]
    return [_step("Area of each trapezoid, width × average height", rf"{f.terms(terms, ',\\ ', 4)}"),
            _step("Add them", rf"{f.terms([f.n(a) for a in areas])} = {f.n(sum(areas))}")]


def _interp(args, res, f):
    at, xs, ys = _shown(args[0]), _arr(args[1]).ravel(), _arr(args[2]).ravel()
    k = int(np.clip(np.searchsorted(xs, at) - 1, 0, len(xs) - 2))
    x1, x2, y1, y2 = xs[k], xs[k + 1], ys[k], ys[k + 1]
    return [_step("The point lies between two table entries", rf"{f.n(x1)} \le {f.n(at)} \le {f.n(x2)}"),
            _step("Straight line between them", rf"y = y_1 + \frac{{(x - x_1)(y_2 - y_1)}}{{x_2 - x_1}} = {f.n(y1)} + \frac{{({f.n(at)} - {f.n(x1)})({f.n(y2)} - {f.n(y1)})}}{{{f.n(x2)} - {f.n(x1)}}} = {f.n(y1 + (at - x1) * (y2 - y1) / (x2 - x1))}")]


def _fit_sums(args):
    x, y = _arr(args[0]).ravel(), _arr(args[1]).ravel()
    mx, my = x.mean(), y.mean()
    return x, y, mx, my, float(np.sum((x - mx) ** 2)), float(np.sum((x - mx) * (y - my))), float(np.sum((y - my) ** 2))


def _fit_head(x, y, mx, my, sxx, sxy, f):
    return [_step("Means", rf"\bar x = {f.n(mx)},\quad \bar y = {f.n(my)}"),
            _step("Sums of squares and products", rf"S_{{xx}} = \sum (x_i - \bar x)^2 = {f.n(sxx)},\quad S_{{xy}} = \sum (x_i - \bar x)(y_i - \bar y) = {f.n(sxy)}")]


def _slope(args, res, f):
    x, y, mx, my, sxx, sxy, _ = _fit_sums(args)
    return _fit_head(x, y, mx, my, sxx, sxy, f) + [_step("Least-squares slope", rf"m = \frac{{S_{{xy}}}}{{S_{{xx}}}} = \frac{{{f.n(sxy)}}}{{{f.n(sxx)}}} = {f.n(sxy / sxx)}")]


def _intercept(args, res, f):
    x, y, mx, my, sxx, sxy, _ = _fit_sums(args)
    m = sxy / sxx
    return _fit_head(x, y, mx, my, sxx, sxy, f) + [_step("Slope", rf"m = \frac{{S_{{xy}}}}{{S_{{xx}}}} = {f.n(m)}"),
                                                    _step("Intercept, so that the line passes through the means", rf"b = \bar y - m \bar x = {f.n(my)} - ({f.n(m)})({f.n(mx)}) = {f.n(my - m * mx)}")]


def _rsquared(args, res, f):
    x, y, mx, my, sxx, sxy, syy = _fit_sums(args)
    return _fit_head(x, y, mx, my, sxx, sxy, f) + [_step("Spread of y", rf"S_{{yy}} = \sum (y_i - \bar y)^2 = {f.n(syy)}"),
                                                    _step("Share of the spread the line explains", rf"R^2 = \frac{{S_{{xy}}^2}}{{S_{{xx}} S_{{yy}}}} = \frac{{({f.n(sxy)})^2}}{{({f.n(sxx)})({f.n(syy)})}} = {f.n(sxy * sxy / (sxx * syy))}")]


def _corr(args, res, f):
    x, y, mx, my, sxx, sxy, syy = _fit_sums(args)
    return _fit_head(x, y, mx, my, sxx, sxy, f) + [_step("Spread of y", rf"S_{{yy}} = {f.n(syy)}"),
                                                    _step("Correlation coefficient", rf"r = \frac{{S_{{xy}}}}{{\sqrt{{S_{{xx}} S_{{yy}}}}}} = \frac{{{f.n(sxy)}}}{{\sqrt{{({f.n(sxx)})({f.n(syy)})}}}} = {f.n(sxy / np.sqrt(sxx * syy))}")]


def _percentile(args, res, f):
    a = np.sort(_arr(args[0]).ravel())
    ps = np.atleast_1d(np.real(args[1].v)).astype(float)[:3]
    steps = [_step("Put the values in order", rf"{f.terms([f.n(x) for x in a], ',\\ ')}")]
    for p in ps:
        h = p / 100 * (len(a) - 1)
        lo, hi = int(np.floor(h)), int(np.ceil(h))
        steps.append(_step(f"Position of the {f.n(p)}th percentile (0 is the smallest)", rf"h = \frac{{p}}{{100}}(n - 1) = \frac{{{f.n(p)}}}{{100}}({len(a)} - 1) = {f.n(h)}"))
        if lo == hi:
            steps.append(_step("The position is a whole number, so take that entry", rf"v_{{{lo}}} = {f.n(a[lo])}{f.u(res)}"))
        else:
            steps.append(_step("Interpolate between the neighbours", rf"v_{{{lo}}} + (h - {lo})(v_{{{hi}}} - v_{{{lo}}}) = {f.n(a[lo])} + ({f.n(h - lo)})({f.n(a[hi])} - {f.n(a[lo])}) = {f.n(a[lo] + (h - lo) * (a[hi] - a[lo]))}{f.u(res)}"))
    return steps


def _cumtrapz(args, res, f):
    xs, ys = _arr(args[0]).ravel(), _arr(args[1]).ravel()
    areas = np.diff(xs) * (ys[1:] + ys[:-1]) / 2
    return [_step("Area of each trapezoid, width × average height", rf"{f.terms([f.n(a) for a in areas], ',\\ ')}"),
            _step("Running total", rf"0,\ {f.terms([f.n(a) for a in np.cumsum(areas)], ',\\ ')}")]


def _range(args, res, f):
    vals = np.atleast_1d(np.real(res.v)).astype(float)
    return [_step("Start, then add the step until the stop value is reached (it is not included)", rf"{f.terms([f.n(x) for x in vals], ',\\ ')}")]


def _linspace(args, res, f):
    vals = np.atleast_1d(np.real(res.v)).astype(float)
    n = len(vals)
    return [_step("Equal steps from the first value to the last", rf"\Delta = \frac{{b - a}}{{n - 1}} = \frac{{{f.n(vals[-1])} - {f.n(vals[0])}}}{{{n - 1}}} = {f.n((vals[-1] - vals[0]) / (n - 1))}"),
            _step("The values a + kΔ", rf"{f.terms([f.n(x) for x in vals], ',\\ ')}")]


# ------------------------------------------------------------------ matrices

def _square(q: L.Q) -> np.ndarray:
    a = _arr(q)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise NoExplanation
    return a


def _det(args, res, f):
    a = _square(args[0])
    n = a.shape[0]
    if n == 1:
        raise NoExplanation
    if n == 2:
        return [_step("Product of the diagonal minus the cross product", rf"ad - bc = ({f.n(a[0, 0])})({f.n(a[1, 1])}) - ({f.n(a[0, 1])})({f.n(a[1, 0])}) = {f.n(np.linalg.det(a))}")]
    if n == 3:
        t = [rf"({f.n(a[0, j])})\left(({f.n(a[1, (j + 1) % 3])})({f.n(a[2, (j + 2) % 3])}) - ({f.n(a[1, (j + 2) % 3])})({f.n(a[2, (j + 1) % 3])})\right)" for j in range(3)]
        return [_step("Expand along the first row (cyclic cofactors)", r"a_{11}(a_{22}a_{33} - a_{23}a_{32}) + a_{12}(a_{23}a_{31} - a_{21}a_{33}) + a_{13}(a_{21}a_{32} - a_{22}a_{31})"),
                _step("With the values", rf"{' + '.join(t)} = {f.n(np.linalg.det(a))}")]
    from scipy.linalg import lu

    p, _lo, u = lu(a)
    piv = np.diag(u)
    sign = round(float(np.linalg.det(p)))
    return [_step("LU factorisation with row exchanges", r"\det A = \pm\prod u_{ii}"),
            _step("Pivots and the sign of the exchanges", rf"{f.terms([f.n(x) for x in piv], ' \\cdot ')} \cdot ({sign:+d}) = {f.n(sign * np.prod(piv))}")]


def _trace(args, res, f):
    a = _square(args[0])
    d = np.diag(a)
    return [_step("Add the diagonal", rf"{f.terms([f.n(x) for x in d])} = {f.n(d.sum())}")]


def _inv(args, res, f):
    a = _square(args[0])
    if a.shape[0] == 2:
        det = float(np.linalg.det(a))
        adj = np.array([[a[1, 1], -a[0, 1]], [-a[1, 0], a[0, 0]]])
        return [_step("Determinant", rf"ad - bc = {f.n(det)}"),
                _step("Swap the diagonal, change the sign of the others, divide by the determinant", rf"A^{{-1}} = \frac{{1}}{{{f.n(det)}}}{_matrix(adj, f)} = {_matrix(np.linalg.inv(a), f)}")]
    return [_step("Determinant", rf"\det A = {f.n(np.linalg.det(a))}"), _step("Method", r"\text{solve } A X = I \text{ column by column (LU factorisation)}"),
            _step("Check", rf"A A^{{-1}} \approx {_matrix(np.round(a @ np.linalg.inv(a), 10) + 0.0, f)}")]


def _solve(args, res, f):
    a, b = _square(args[0]), _arr(args[1])
    x = np.linalg.solve(a, b)
    if a.shape[0] == 2 and b.ndim == 1:
        d = float(np.linalg.det(a))
        d1 = float(np.linalg.det(np.column_stack([b, a[:, 1]])))
        d2 = float(np.linalg.det(np.column_stack([a[:, 0], b])))
        return [_step("Cramer's rule: determinants", rf"\det A = {f.n(d)},\quad \det A_1 = {f.n(d1)},\quad \det A_2 = {f.n(d2)}"),
                _step("Unknowns", rf"x_1 = \frac{{{f.n(d1)}}}{{{f.n(d)}}} = {f.n(d1 / d)},\quad x_2 = \frac{{{f.n(d2)}}}{{{f.n(d)}}} = {f.n(d2 / d)}")]
    return [_step("Method", r"\text{Gaussian elimination with row exchanges (LU factorisation), then back-substitution}"),
            _step("Check: A x reproduces b", rf"A x = {_matrix((a @ x).reshape(-1, 1) if x.ndim == 1 else a @ x, f)}")]


def _matmul(args, res, f):
    a, b = _arr(args[0]), _arr(args[1])
    a2 = a.reshape(1, -1) if a.ndim == 1 else a
    if b.ndim == 1:
        row = a2[0] if a2.shape[0] else a2
        prod = a2 @ b
        terms = [rf"({f.n(x)})({f.n(y)})" for x, y in zip(a2[0], b)]
        return [_step("Row of A times the vector, entry by entry", rf"c_1 = {f.terms(terms)} = {f.n(prod[0])}")] if a2.shape[1] == b.shape[0] else None
    terms = [rf"({f.n(a2[0, k])})({f.n(b[k, 0])})" for k in range(a2.shape[1])]
    return [_step("Entry (i, j) is row i of A times column j of B", r"c_{ij} = \sum_k a_{ik} b_{kj}"),
            _step("First entry", rf"c_{{11}} = {f.terms(terms)} = {f.n((a2 @ b)[0, 0])}")]


def _transpose(args, res, f):
    return [_step("Rows become columns", r"\left(A^{T}\right)_{ij} = A_{ji}")]


def _eigvals(args, res, f):
    a = _square(args[0])
    if a.shape[0] == 2:
        tr, det = float(np.trace(a)), float(np.linalg.det(a))
        disc = tr * tr - 4 * det
        return [_step("Characteristic equation", rf"\lambda^2 - (\operatorname{{tr}} A)\lambda + \det A = \lambda^2 - ({f.n(tr)})\lambda + ({f.n(det)}) = 0"),
                _step("Quadratic formula", rf"\lambda = \frac{{{f.n(tr)} \pm \sqrt{{({f.n(tr)})^2 - 4({f.n(det)})}}}}{{2}} = \frac{{{f.n(tr)} \pm \sqrt{{{f.n(disc)}}}}}{{2}}")]
    w = np.linalg.eigvals(a)
    return [_step("Eigenvalues are the roots of", r"\det(A - \lambda I) = 0"),
            _step("Checks", rf"\sum \lambda = {f.n(np.sum(w).real)} = \operatorname{{tr}} A = {f.n(np.trace(a))},\quad \prod \lambda = {f.n(np.prod(w).real)} = \det A = {f.n(np.linalg.det(a))}")]


def _svdvals(args, res, f):
    a = _arr(args[0])
    return [_step("Singular values", r"\sigma_i = \sqrt{\text{eigenvalues of } A^{T}A}"),
            _step("Eigenvalues of AᵀA", rf"{f.terms([f.n(x) for x in np.sort(np.linalg.eigvalsh(a.T @ a))[::-1]], ',\\ ')}")]


def _cond(args, res, f):
    s = np.linalg.svd(_arr(args[0]), compute_uv=False)
    return [_step("Singular values", rf"\sigma = {f.terms([f.n(x) for x in s], ',\\ ')}"),
            _step("Largest over smallest", rf"\kappa = \frac{{\sigma_{{max}}}}{{\sigma_{{min}}}} = \frac{{{f.n(s[0])}}}{{{f.n(s[-1])}}} = {f.n(s[0] / s[-1])}")]


def _rank(args, res, f):
    a = _arr(args[0])
    s = np.linalg.svd(a, compute_uv=False)
    return [_step("Singular values", rf"\sigma = {f.terms([f.n(x) for x in s], ',\\ ')}"),
            _step("Count those that are not zero (relative to the largest)", rf"\operatorname{{rank}} = {int(np.sum(s > max(a.shape) * np.finfo(float).eps * s[0]))}")]


def _lstsq(args, res, f):
    a, b = _arr(args[0]), _arr(args[1])
    if a.shape[1] > 4:
        raise NoExplanation
    ata, atb = a.T @ a, a.T @ b
    return [_step("Normal equations", r"A^{T}A\,x = A^{T}b"), _step("With the values", rf"{_matrix(ata, f)} x = {_matrix(atb.reshape(-1, 1) if atb.ndim == 1 else atb, f)}")]


def _polyfit(args, res, f):
    x, y = _arr(args[0]).ravel(), _arr(args[1]).ravel()
    n = int(args[2].v)
    if n > 3:
        raise NoExplanation
    scale = float(np.max(np.abs(x))) or 1.0
    coef = np.polyfit(x / scale, y, n)
    at = np.atleast_1d(_arr(args[3])).ravel().astype(float)
    return [_step("Least-squares polynomial of degree n", rf"y = \sum_{{k=0}}^{{{n}}} c_k (x/{f.n(scale)})^k"),
            _step("Coefficients (highest power first, x scaled by the largest |x|)", rf"{f.terms([f.n(c) for c in coef], ',\\ ')}"),
            _step("Evaluate at the point" + ("s" if at.size > 1 else ""), rf"{f.terms([f.n(np.polyval(coef, a / scale)) for a in at], ',\\ ')}")]


def _pinv(args, res, f):
    return [_step("Pseudo-inverse of a tall full-rank matrix", r"A^{+} = (A^{T}A)^{-1}A^{T}")]


def _lu_part(name):
    def run(args, res, f):
        return [_step("Factorisation with row exchanges", r"P A = L U\quad (L \text{ unit lower triangular},\ U \text{ upper triangular})")]
    return run


def _qr_part(args, res, f):
    return [_step("Orthogonal–triangular factorisation", r"A = Q R,\quad Q^{T}Q = I,\ R \text{ upper triangular}")]


def _chol(args, res, f):
    return [_step("Cholesky factorisation of a symmetric positive-definite matrix", r"A = L L^{T}\quad (L \text{ lower triangular})")]


def _eigvecs(args, res, f):
    return [_step("Eigenvectors solve", r"(A - \lambda I)\,v = 0,\ \text{each scaled to length 1}")]


# ------------------------------------------------------------------ small definitions

def _shape(args, res, f):
    a = _arr(args[0])
    return [_step("Rows and columns", rf"{a.shape[0]} \times {a.shape[1] if a.ndim > 1 else 1}")]


def _identity(args, res, f):
    return [_step("Ones on the diagonal, zeros elsewhere", rf"I_{{{int(args[0].v)}}}")]


def _count(args, res, f):
    return [_step("Count the entries", rf"{int(np.asarray(res.v))}")]


EXPLAINERS = {
    "sum": _sum, "mean": _mean, "median": _median, "stdev": _stdev, "var": _var, "prod": _prod, "min": _minmax("min"), "max": _minmax("max"),
    "hypot": _hypot, "norm": _norm, "mod": _mod, "factorial": _factorial, "dot": _dot, "cross": _cross, "outer": _outer, "cumsum": _cumsum,
    "diff": _diff, "sort": _sort, "reverse": _reverse, "trapz": _trapz, "interp": _interp, "slope": _slope, "intercept": _intercept,
    "rsquared": _rsquared, "corr": _corr, "percentile": _percentile, "det": _det, "trace": _trace, "inv": _inv, "solve": _solve, "matmul": _matmul,
    "transpose": _transpose, "eigvals": _eigvals, "eigvecs": _eigvecs, "svdvals": _svdvals, "cond": _cond, "rank": _rank, "lstsq": _lstsq,
    "polyfit": _polyfit, "cumtrapz": _cumtrapz, "range": _range, "linspace": _linspace, "pinv": _pinv, "lu_l": _lu_part("l"), "lu_u": _lu_part("u"), "lu_p": _lu_part("p"), "qr_q": _qr_part, "qr_r": _qr_part,
    "chol": _chol, "shape": _shape, "identity": _identity, "len": _count, "rows": _count, "cols": _count,
}


def explain(name: str, args: list[L.Q], res: L.Q, sig: int) -> list[dict] | None:
    """The middle steps for ``name(args) = res``, or ``None``."""
    fn = EXPLAINERS.get(name)
    if fn is None:
        return None
    try:
        return fn(args, res, _Fmt(sig))
    except (NoExplanation, ValueError, IndexError, KeyError, TypeError, AttributeError, np.linalg.LinAlgError, ZeroDivisionError, ArithmeticError):
        return None


# ------------------------------------------------------------------ elementary functions of one value (top-level calls only)

_ELEMENTARY = {
    "sqrt": "the number whose square is the argument (the unit is rooted too)", "cbrt": "the number whose cube is the argument (the unit is rooted too)",
    "exp": "e raised to the argument", "ln": "the natural logarithm: the power of e that gives the argument", "log": "the natural logarithm: the power of e that gives the argument",
    "log10": "the power of 10 that gives the argument", "log2": "the power of 2 that gives the argument",
    "sin": "the sine of an angle (radians, or write the unit: 30 deg)", "cos": "the cosine of an angle (radians, or write the unit: 30 deg)",
    "tan": "the tangent of an angle (radians, or write the unit: 30 deg)",
    "asin": "the angle whose sine is the argument (answer in radians; ‘to deg’ converts)", "acos": "the angle whose cosine is the argument (answer in radians; ‘to deg’ converts)",
    "atan": "the angle whose tangent is the argument (answer in radians; ‘to deg’ converts)",
    "sinh": "the hyperbolic sine, (eˣ − e⁻ˣ)/2", "cosh": "the hyperbolic cosine, (eˣ + e⁻ˣ)/2", "tanh": "the hyperbolic tangent, sinh/cosh",
    "abs": "the distance from zero (the sign is dropped)", "floor": "the largest whole number not above the argument", "ceil": "the smallest whole number not below the argument",
    "round": "the nearest whole number", "sign": "−1, 0 or +1: the sign of the argument",
}
_ELEMENTARY_FORMULA = {"sinh": r"\frac{e^{x} - e^{-x}}{2}", "cosh": r"\frac{e^{x} + e^{-x}}{2}", "tanh": r"\frac{e^{x} - e^{-x}}{e^{x} + e^{-x}}"}


def explain_elementary(name: str, arg: L.Q, res: L.Q, angle_deg: bool, sig: int) -> list[dict] | None:
    """Steps for ``name(arg)`` of one real value: what the function is, the argument as the function sees it, and the value."""
    if name not in _ELEMENTARY or np.ndim(arg.v) or np.ndim(res.v) or L._is_complex(arg) or L._is_complex(res):
        return None
    f = _Fmt(sig)
    steps = [_step("The function", rf"{L.tex(('call', name, [('name', 'x')]))} = \text{{{_ELEMENTARY[name]}}}")]
    if name in _ELEMENTARY_FORMULA:
        steps.append(_step("Definition", rf"{L.tex(('call', name, [('name', 'x')]))} = {_ELEMENTARY_FORMULA[name]}"))
    lines = []
    shown_arg = f.q(arg)
    if name in ("sin", "cos", "tan"):
        rad = float(np.radians(float(arg.v))) if (angle_deg and arg.unit is None) else float(arg.v)
        if angle_deg and arg.unit is None:
            lines.append(rf"x = {f.n(float(arg.shown))}^\circ = {f.n(float(arg.shown))} \cdot \frac{{\pi}}{{180}} = {f.n(rad)}\ \mathrm{{rad}}")
        elif arg.unit is not None and arg.unit.symbol not in ("", "1", "rad"):
            lines.append(rf"x = {shown_arg} = {f.n(rad)}\ \mathrm{{rad}}")
        else:
            lines.append(rf"x = {f.n(rad)}\ \mathrm{{rad}}")
        lines.append(rf"{L.tex(('call', name, [('name', 'x')]))} = {L.tex(('call', name, [('num', rad, '')]))} = {f.q(res)}")
    else:
        lines.append(rf"x = {shown_arg}")
        lines.append(rf"{L.tex(('call', name, [('name', 'x')]))} = {f.q(res)}")
    steps.append(_step("Evaluate", *lines))
    return steps


# ------------------------------------------------------------------ complex numbers

def _z(q: L.Q) -> complex:
    return complex(np.asarray(q.shown).item())


def _rect(z: complex, f: _Fmt) -> str:
    sign = "+" if z.imag >= 0 else "-"
    return rf"{f.n(z.real)} {sign} {f.n(abs(z.imag))}\,i"


def explain_complex_function(name: str, args: list[L.Q], res: L.Q, sig: int) -> list[dict] | None:
    f = _Fmt(sig)
    if name == "real" and len(args) == 1:
        z = _z(args[0])
        return [_step("The real part is the number without the i", rf"z = {_rect(z, f)} \;\Rightarrow\; \operatorname{{Re}}\,z = {f.n(z.real)}")]
    if name == "imag" and len(args) == 1:
        z = _z(args[0])
        return [_step("The imaginary part is the coefficient of i", rf"z = {_rect(z, f)} \;\Rightarrow\; \operatorname{{Im}}\,z = {f.n(z.imag)}")]
    if name == "conj" and len(args) == 1:
        z = _z(args[0])
        return [_step("Change the sign of the imaginary part", rf"\overline{{{_rect(z, f)}}} = {_rect(z.conjugate(), f)}")]
    if name == "abs" and len(args) == 1 and L._is_complex(args[0]):
        z = _z(args[0])
        return [_step("Magnitude", rf"|z| = \sqrt{{(\operatorname{{Re}}\,z)^2 + (\operatorname{{Im}}\,z)^2}} = \sqrt{{({f.n(z.real)})^2 + ({f.n(z.imag)})^2}} = \sqrt{{{f.n(z.real ** 2 + z.imag ** 2)}}} = {f.n(abs(z))}")]
    if name == "arg" and len(args) == 1:
        z = _z(args[0])
        return [_step("Angle from the real axis", rf"\theta = \operatorname{{atan2}}(\operatorname{{Im}}\,z,\ \operatorname{{Re}}\,z) = \operatorname{{atan2}}({f.n(z.imag)},\ {f.n(z.real)}) = {f.n(np.angle(z))}\ \mathrm{{rad}} = {f.n(np.degrees(np.angle(z)))}^\circ")]
    if name == "polar" and len(args) == 2 and L._is_complex(res):
        r, th = float(args[0].shown), float(args[1].v)
        z = _z(res)
        return [_step("Magnitude and angle to rectangular form", r"r(\cos\theta + i\sin\theta) = r\cos\theta + i\,r\sin\theta"),
                _step("With the values", rf"\theta = {f.n(th)}\ \mathrm{{rad}}:\quad {f.n(r)}\cos({f.n(th)}) + i\,{f.n(r)}\sin({f.n(th)}) = {f.n(r * np.cos(th))} + {f.n(r * np.sin(th))}\,i = {_rect(z, f)}")]
    return None


def explain_complex_value(res: L.Q, sig: int) -> list[dict]:
    """Any complex result: its rectangular and polar forms."""
    f = _Fmt(sig)
    z = _z(res)
    unit = f.u(res)
    return [_step("Rectangular form", rf"{_rect(z, f)}{unit}"),
            _step("Magnitude and angle (polar form)", rf"|z| = \sqrt{{({f.n(z.real)})^2 + ({f.n(z.imag)})^2}} = {f.n(abs(z))}{unit},\quad \theta = {f.n(np.angle(z))}\ \mathrm{{rad}} = {f.n(np.degrees(np.angle(z)))}^\circ")]
