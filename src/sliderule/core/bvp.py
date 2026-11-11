"""Boundary-value problems ``y' = f(x, y)`` with conditions at the ends (or inside) of an interval, by multiple shooting.

The interval is cut at every position where a condition is imposed and subdivided further. The unknowns are the state vectors
``Y_0 ... Y_m`` at the nodes. They must satisfy

* continuity: integrating segment ``i`` from ``Y_i`` gives ``Y_{i+1}`` (``n`` equations per segment), and
* the boundary conditions ``r_j(Y_k) = 0`` (``n`` in all).

That is a square nonlinear system solved by damped Newton. The Jacobian is exact: each segment is integrated together with its
sensitivity matrix ``S' = (df/dy) S, S(x_i) = I`` (the variational equations), with the pure-Python adaptive integrator of :mod:`.numeric_ode`.
A linear problem is solved in one Newton step. Starting from a plain single shooting (``m = 1``) would amplify errors like ``e^{lambda L}``;
the segments keep that factor small, which is why the interval is subdivided.

Unknown parameters ``theta`` (an eigenvalue, a fitted constant) are extra unknowns of the same Newton system; they need as many extra conditions as there
are parameters (an eigenvalue problem needs a normalisation, since an eigenfunction can be scaled), and their sensitivities come from ``P' = (df/dy) P + df/dtheta``.
A nonlinear problem can have several solutions, and an eigenproblem has many eigenvalues: Newton finds the one nearest the guess.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from .numeric_ode import OdeError, OdeResult, solve_ivp

Vector = list[float]
MAX_SEGMENTS = 32
RTOL = 1e-9
ATOL = 1e-12


class BvpError(OdeError):
    pass


@dataclass
class Condition:
    node: int                                         # index of the node it applies to
    r: Callable                                       # residual r(y, theta) of the state at that node
    grad: Callable                                    # d r / d state
    gth: Callable                                     # d r / d theta


def _solve_dense(a: list[list[float]], b: Vector) -> tuple[Vector, float]:
    """LU solve with partial pivoting. Returns the solution and the ratio of the smallest to the largest pivot (0 if singular)."""
    try:
        lu, piv = lu_factor(np.asarray(a, dtype=float), check_finite=False)
    except (ValueError, np.linalg.LinAlgError):
        return [], 0.0
    d = np.abs(np.diag(lu))
    if d.size == 0 or d.max() == 0.0 or d.min() == 0.0 or not np.all(np.isfinite(lu)):
        return [], 0.0
    return lu_solve((lu, piv), np.asarray(b, dtype=float), check_finite=False).tolist(), float(d.min() / d.max())


def _solve_equilibrated(a: list[list[float]], b: Vector) -> tuple[Vector, float]:
    """Solve after scaling rows and columns to unit largest entry, so that quantities of very different size (a force of 1e7 next to a length of 1) do not look
    like a near-singular system; the pivot ratio is then a fair test of singularity."""
    m = np.asarray(a, dtype=float)
    r = np.abs(m).max(axis=1)
    r[r == 0.0] = 1.0
    m = m / r[:, None]
    c = np.abs(m).max(axis=0)
    c[c == 0.0] = 1.0
    m = m / c[None, :]
    x, ratio = _solve_dense(m.tolist(), (np.asarray(b, dtype=float) / r).tolist())
    if not x:
        return [], 0.0
    return (np.asarray(x) / c).tolist(), ratio


def _segment(f: Callable, jac: Callable, fth: Callable, th: Sequence[float], x0: float, y0: Vector, x1: float) -> OdeResult:
    """Integrate y, its sensitivity matrix S and its sensitivity to the parameters P over one segment."""
    n, mp = len(y0), len(th)

    def aug(x, z):
        y = z[:n]
        out = list(f(x, y, th))
        j = jac(x, y, th)
        for col in range(n):                           # S[:, col]' = J S[:, col]
            sc = z[n + col * n: n + (col + 1) * n]
            out.extend(sum(j[r][k] * sc[k] for k in range(n)) for r in range(n))
        if mp:
            g = fth(x, y, th)
            base = n + n * n
            for col in range(mp):                      # P[:, col]' = J P[:, col] + df/dtheta[:, col]
                pc = z[base + col * n: base + (col + 1) * n]
                out.extend(sum(j[r][k] * pc[k] for k in range(n)) + g[r][col] for r in range(n))
        return out

    z0 = list(y0) + [1.0 if r == col else 0.0 for col in range(n) for r in range(n)] + [0.0] * (n * mp)
    return solve_ivp(aug, x0, z0, x1, rtol=RTOL, atol=ATOL)


def _plain(f: Callable, x0: float, y0: Vector, x1: float, outputs: Sequence[float] = ()) -> OdeResult:
    return solve_ivp(f, x0, y0, x1, outputs=outputs, rtol=RTOL, atol=ATOL)


def _nodes(lo: float, hi: float, required: Sequence[float], segments: int) -> list[float]:
    """Sorted mesh points: the interval ends, every position a condition refers to, and a uniform subdivision."""
    pts = {lo, hi, *required}
    for i in range(1, segments):
        pts.add(lo + (hi - lo) * i / segments)
    xs = sorted(pts)
    out = [xs[0]]
    for x in xs[1:]:                              # merge points closer than a thousandth of a segment
        if x - out[-1] > 1e-9 * abs(hi - lo):
            out.append(x)
    return out


@dataclass
class BvpSolution:
    xs: list[float]
    nodes: list[Vector]
    f: Callable                      # f(x, y) with the solved parameters built in
    iterations: int
    segments: int
    residual: float
    theta: list[float]

    def sample(self, points: Sequence[float]) -> tuple[list[float], list[Vector], int]:
        """States at ``points`` (any order), integrating from the nearest node on the left within each segment."""
        out: dict[float, Vector] = {}
        steps = 0
        for i in range(len(self.xs) - 1):
            a, b = self.xs[i], self.xs[i + 1]
            inside = [p for p in points if a <= p <= b]
            if i == len(self.xs) - 2:
                inside = [p for p in points if a <= p <= b + 1e-12 * abs(b - a)]
            if not inside:
                continue
            res = _plain(self.f, a, self.nodes[i], b, outputs=inside)
            steps += res.steps
            table = {round(t, 14): y for t, y in zip(res.ts, res.ys)}
            for p in inside:
                y = table.get(round(p, 14))
                if y is None:                                 # a point that coincides with the end of the segment
                    y = res.ys[-1] if abs(p - b) <= 1e-12 * max(abs(b), 1.0) else res.ys[0]
                out.setdefault(p, y)
        pts = sorted(out)
        return pts, [out[p] for p in pts], steps


def solve(f: Callable, jac: Callable, fth: Callable, lo: float, hi: float, n: int, conditions: Sequence[tuple], guess: Vector,
          theta0: Sequence[float] = (), segments: int = 8, guess_fn: Callable | None = None) -> BvpSolution:
    """Solve for the node states and the unknown parameters. ``conditions``: ``(position, r(y, th), grad_y(y, th), grad_th(y, th))``;
    there must be ``n + len(theta0)`` of them. ``f``, ``jac`` and ``fth`` take ``(x, y, th)``."""
    mp = len(theta0)
    # work with scaled parameters phi = theta / scale (an energy of 1e-21 J or a load of 1e7 N would otherwise dominate the tolerances)
    scale = [abs(v) if abs(v) > 0 else 1.0 for v in theta0]
    if mp and any(sc != 1.0 for sc in scale):
        sc_th = lambda th: [a * b for a, b in zip(th, scale)]            # noqa: E731
        f0, jac0, fth0 = f, jac, fth
        f = lambda x, y, th: f0(x, y, sc_th(th))                         # noqa: E731
        jac = lambda x, y, th: jac0(x, y, sc_th(th))                     # noqa: E731
        fth = lambda x, y, th: [[v * sc for v, sc in zip(row, scale)] for row in fth0(x, y, sc_th(th))]      # noqa: E731
        conditions = [(pos, (lambda y, th, r=r: r(y, sc_th(th))), (lambda y, th, g=g: g(y, sc_th(th))),
                       (lambda y, th, q=q: [v * sc for v, sc in zip(q(y, sc_th(th)), scale)])) for pos, r, g, q in conditions]
        sol = solve(f, jac, fth, lo, hi, n, conditions, guess, [a / b for a, b in zip(theta0, scale)], segments, guess_fn)
        sol.theta = sc_th(sol.theta)
        return sol
    if len(conditions) != n + mp:
        raise BvpError(f"{n + mp} boundary conditions are needed ({n} for the order of the equations, {mp} for the unknown parameters), but {len(conditions)} were given")
    if not hi > lo:
        raise BvpError("the interval must have a positive length: 'end' must be greater than 'start'")
    last_error: Exception | None = None
    seg = segments
    while seg <= MAX_SEGMENTS:
        try:
            return _newton(f, jac, fth, lo, hi, n, conditions, guess, list(theta0), seg, guess_fn)
        except BvpError as exc:
            last_error = exc
            if "singular" in str(exc) or "no unique" in str(exc):
                raise
            seg *= 2
    raise BvpError(f"the boundary-value iteration did not converge ({last_error}); give a better guess for the unknown functions"
                   + (" and parameters" if mp else "")) from None


def _newton(f, jac, fth, lo, hi, n, conditions, guess, theta, segments, guess_fn=None) -> BvpSolution:
    xs = _nodes(lo, hi, [c[0] for c in conditions], segments)
    m = len(xs) - 1
    mp = len(theta)
    where = []
    for pos, r, g, gt in conditions:
        k = min(range(len(xs)), key=lambda i: abs(xs[i] - pos))
        where.append(Condition(k, r, g, gt))
    # start from the guess and carry it forward so that continuity holds from the start
    nodes: list[Vector] = [list(guess)]
    try:
        if guess_fn is not None:                           # a profile guess: the starting state at every node comes straight from it
            nodes = [[float(v) for v in guess_fn(x)] for x in xs]
            if any(not math.isfinite(v) for y in nodes for v in y):
                raise OdeError("not finite")
            raise StopIteration
        for i in range(m):
            nodes.append(_plain(lambda x, y: f(x, y, theta), xs[i], nodes[i], xs[i + 1]).final)
        if any(not math.isfinite(v) for y in nodes for v in y):
            raise OdeError("not finite")
    except StopIteration:
        pass
    except (OdeError, OverflowError, ValueError, ArithmeticError):
        nodes = [list(guess) for _ in xs]
    size = n * (m + 1) + mp
    th0 = n * (m + 1)

    def evaluate(nd: list[Vector], th: list[float]):
        res = [0.0] * size
        jm = [[0.0] * size for _ in range(size)]
        for i in range(m):
            seg = _segment(f, jac, fth, th, xs[i], nd[i], xs[i + 1])
            z = seg.final
            for r in range(n):
                res[i * n + r] = nd[i + 1][r] - z[r]
                jm[i * n + r][(i + 1) * n + r] = 1.0
                for c in range(n):
                    jm[i * n + r][i * n + c] = -z[n + c * n + r]
                for c in range(mp):
                    jm[i * n + r][th0 + c] = -z[n + n * n + c * n + r]
        for j, cond in enumerate(where):
            row = m * n + j
            y = nd[cond.node]
            res[row] = cond.r(y, th)
            for c, gv in enumerate(cond.grad(y, th)):
                jm[row][cond.node * n + c] = gv
            for c, gv in enumerate(cond.gth(y, th)):
                jm[row][th0 + c] = gv
        return res, jm

    def measure(res: Vector, nd: list[Vector], th: list[float]) -> float:
        worst = 0.0
        for i in range(m):
            worst = max(worst, max(abs(res[i * n + r]) / (1.0 + abs(nd[i + 1][r])) for r in range(n)))
        for j, cond in enumerate(where):
            y = nd[cond.node]
            ref = max([1.0] + [abs(g * v) for g, v in zip(cond.grad(y, th), y)] + [abs(g * v) for g, v in zip(cond.gth(y, th), th)])
            worst = max(worst, abs(res[m * n + j]) / ref)
        return worst

    try:
        res, jm = evaluate(nodes, theta)
    except (OdeError, OverflowError, ValueError, ArithmeticError) as exc:
        raise BvpError(f"the equations could not be integrated from the starting guess: {exc}") from None
    norm = measure(res, nodes, theta)
    for iteration in range(1, 61):
        step, ratio = _solve_equilibrated(jm, [-v for v in res])
        if not step:
            raise BvpError("the linearised boundary-value problem is singular"
                           + ("; for an eigenvalue problem, check the normalisation condition and give a starting guess near the eigenvalue you want (and a non-zero starting shape)" if mp else ""))
        if ratio < 1e-7:
            raise BvpError("the boundary-value problem has no unique solution (its linearisation is singular or nearly so): the conditions may "
                           "contradict each other, leave a constant undetermined, or sit at an eigenvalue of the equation (for example y'' = -y with y = 0 at both ends of a half period)"
                           + ("; for an eigenvalue problem, add a normalisation condition (such as the value of the mode at one point) and a starting guess near the eigenvalue you want" if mp else ""))
        if norm < 1e-9:
            return BvpSolution(xs, nodes, (lambda x, y, th=list(theta): f(x, y, th)), iteration - 1, m, norm, list(theta))
        # the residual cannot fall below the integration error, which a decaying solution amplifies; a Newton step that no longer changes anything is convergence
        rel_step = max([abs(step[k * n + r]) / (1.0 + abs(nodes[k][r])) for k in range(m + 1) for r in range(n)] + [abs(step[th0 + c]) / (abs(theta[c]) + 1e-300) for c in range(mp)])
        if norm < 1e-5 and rel_step < 1e-9:
            return BvpSolution(xs, nodes, (lambda x, y, th=list(theta): f(x, y, th)), iteration - 1, m, norm, list(theta))
        lam = 1.0
        while True:
            trial = [[nodes[k][r] + lam * step[k * n + r] for r in range(n)] for k in range(m + 1)]
            tth = [theta[c] + lam * step[th0 + c] for c in range(mp)]
            try:
                tres, tjm = evaluate(trial, tth)
                tnorm = measure(tres, trial, tth)
                if math.isfinite(tnorm) and (tnorm < norm or tnorm < 1e-9):
                    break
            except (OdeError, OverflowError, ValueError, ArithmeticError):
                pass
            lam /= 2
            if lam < 1 / 64:
                raise BvpError("Newton's method stalled")
        nodes, theta, res, jm, norm = trial, tth, tres, tjm, tnorm
    if norm < 1e-7:
        return BvpSolution(xs, nodes, (lambda x, y, th=list(theta): f(x, y, th)), 60, m, norm, list(theta))
    raise BvpError(f"Newton's method did not converge (residual {norm:.1e})")
