"""Numerical solution of initial-value problems ``y' = f(t, y)`` (own integrators, so that events and exact landing on output times work; NumPy only for the dense linear algebra).

* :func:`rk45` — adaptive Dormand–Prince 5(4), the default.
* :func:`stiff` — implicit Euler with Richardson extrapolation and step-size control (L-stable, second order), used
  automatically when the explicit method needs too many steps, which is the signature of a stiff problem.
* :func:`solve_ivp` — chooses between them and returns a :class:`OdeResult`.

The state is a list of floats; ``f`` takes ``(t, y)`` and returns a list. Both directions of time work. Outputs at requested
times are hit exactly (the step is shortened to land on them). Failures raise :class:`OdeError` with a plain-language message.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

Vector = list[float]
Rhs = Callable[[float, Vector], Vector]
Guard = Callable[[float, Vector], float]


@dataclass
class EventSpec:
    """An event is the moment ``g(t, y)`` crosses zero. ``direction``: +1 rising, -1 falling, 0 either; ``terminal`` stops the integration."""
    g: Guard
    direction: int = 0
    terminal: bool = False
    reset: Callable[[float, Vector], Vector] | None = None     # impulsive event: the state jumps to reset(t, y) and the integration continues


@dataclass
class EventHit:
    index: int          # which EventSpec
    t: float
    y: Vector

RK_MAX_STEPS = 20_000        # beyond this the explicit method is abandoned for the stiff one
STIFF_MAX_STEPS = 200_000


class OdeError(RuntimeError):
    pass


@dataclass
class OdeResult:
    ts: list[float]
    ys: list[Vector]                 # state at each time in ts (ts[0] is the start, ts[-1] the end)
    method: str
    steps: int
    nfev: int
    rtol: float
    atol: float
    notes: list[str] = field(default_factory=list)
    events: list[EventHit] = field(default_factory=list)
    stopped_by: int | None = None       # index of the terminal event that ended the integration, if any

    @property
    def final(self) -> Vector:
        return self.ys[-1]


# ---------------------------------------------------------------- Dormand-Prince 5(4)

_C = (0.0, 1 / 5, 3 / 10, 4 / 5, 8 / 9, 1.0, 1.0)
_A = (
    (),
    (1 / 5,),
    (3 / 40, 9 / 40),
    (44 / 45, -56 / 15, 32 / 9),
    (19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729),
    (9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656),
    (35 / 384, 0.0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84),
)
_B5 = (35 / 384, 0.0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84, 0.0)
_B4 = (5179 / 57600, 0.0, 7571 / 16695, 393 / 640, -92097 / 339200, 187 / 2100, 1 / 40)


def _check_finite(y: Vector, t: float) -> None:
    for v in y:
        if not math.isfinite(v):
            raise OdeError(f"the solution is not finite at t = {t:g} (it may blow up, or the equations leave the domain of a function there)")


def _err_norm(err: Vector, y0: Vector, y1: Vector, rtol: float, atol: float) -> float:
    s = 0.0
    for e, a, b in zip(err, y0, y1):
        r = e / (atol + rtol * max(abs(a), abs(b)))
        s += r * r                          # a product, not a power: a huge ratio becomes inf (the step is rejected) instead of raising OverflowError
    return math.sqrt(s / max(len(err), 1)) if math.isfinite(s) else math.inf


def _initial_step(f: Rhs, t0: float, y0: Vector, f0: Vector, direction: float, rtol: float, atol: float, span: float) -> float:
    sc = [atol + rtol * abs(v) for v in y0]

    def rms(vs):
        tot = 0.0
        for v, s_ in zip(vs, sc):
            r = v / s_
            tot += r * r
        return math.sqrt(tot / len(y0)) if math.isfinite(tot) else math.inf
    d0, d1 = rms(y0), rms(f0)
    h0 = 1e-6 if d0 < 1e-5 or d1 < 1e-5 else 0.01 * d0 / d1
    h0 = min(h0, span)
    if not (math.isfinite(d1) and h0 > 0):
        return span * 1e-6
    y1 = [a + direction * h0 * b for a, b in zip(y0, f0)]
    f1 = f(t0 + direction * h0, y1)
    d2 = rms([a - b for a, b in zip(f1, f0)]) / h0
    big = max(d1, d2)
    if not math.isfinite(big):
        return min(h0, span * 1e-6)
    h1 = 10 ** (-(2 + math.log10(big)) / 6) if big > 1e-15 else max(1e-6, h0 * 1e-3)
    return min(100 * h0, h1, span)


def _hermite(t0: float, y0: Vector, f0: Vector, t1: float, y1: Vector, f1: Vector, t: float) -> Vector:
    h = t1 - t0
    s = (t - t0) / h
    h00, h10, h01, h11 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
    return [h00 * a + h10 * h * da + h01 * b + h11 * h * db for a, da, b, db in zip(y0, f0, y1, f1)]


def _crossing(ga: float, gb: float, direction: int) -> bool:
    rising, falling = ga < 0 <= gb, ga > 0 >= gb
    return (rising and direction >= 0) or (falling and direction <= 0)


def _locate(spec: EventSpec, f: Rhs, advance, t0: float, y0: Vector, f0: Vector, t1: float, y1: Vector, f1: Vector) -> tuple[float, Vector]:
    """Time and state of the zero of ``g`` inside one step: bisection on the cubic Hermite interpolant, then refined against the real integration."""
    ga = spec.g(t0, y0)
    lo, hi = t0, t1
    glo = ga
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        gm = spec.g(mid, _hermite(t0, y0, f0, t1, y1, f1, mid))
        if (glo < 0) == (gm < 0) and gm != 0:
            lo, glo = mid, gm
        else:
            hi = mid
        if abs(hi - lo) <= 1e-15 * max(abs(t0), abs(t1), 1.0):
            break
    te = 0.5 * (lo + hi)
    ye = advance(t0, y0, te)
    for _ in range(4):                           # polish with the integrated state (the interpolant is only third order)
        ge = spec.g(te, ye)
        dt = 1e-6 * max(abs(t1 - t0), 1e-12)
        slope = (spec.g(te + dt, advance(t0, y0, te + dt)) - ge) / dt if te + dt <= t1 + 1e-12 else (ge - ga) / (te - t0 or 1.0)
        if slope == 0 or abs(ge) <= 1e-13 * (abs(ga) + abs(ge) + 1e-300):
            break
        step = -ge / slope
        te2 = min(max(te + step, t0), t1)
        if te2 == te:
            break
        te, ye = te2, advance(t0, y0, te2)
    return te, ye


def rk45(f: Rhs, t0: float, y0: Sequence[float], t1: float, rtol: float = 1e-8, atol: float = 1e-12,
         outputs: Sequence[float] = (), max_steps: int = RK_MAX_STEPS, events: Sequence[EventSpec] = ()) -> OdeResult:
    y = [float(v) for v in y0]
    ts, ys = [t0], [list(y)]
    nfev = 0
    hits: list[EventHit] = []
    gprev = [e.g(t0, y) for e in events]
    if t1 == t0:
        return OdeResult(ts, ys, "RK45", 0, 0, rtol, atol)
    direction = 1.0 if t1 > t0 else -1.0
    span = abs(t1 - t0)
    stops = sorted({t for t in outputs if min(t0, t1) < t < max(t0, t1)}, reverse=direction < 0) + [t1]
    stops = sorted(stops, key=lambda v: direction * v)
    k1 = f(t0, y)
    nfev += 1
    h = _initial_step(f, t0, y, k1, direction, rtol, atol, span)
    t, steps, i = t0, 0, 0
    while i < len(stops):
        stop = stops[i]
        if steps >= max_steps:
            raise _TooManySteps(f"more than {max_steps} steps")
        hs = min(h, abs(stop - t))
        last = hs >= abs(stop - t) * (1 - 1e-12)
        ks = [k1]
        for s in range(1, 7):
            yi = [y[j] + direction * hs * sum(_A[s][m] * ks[m][j] for m in range(s)) for j in range(len(y))]
            ks.append(f(t + direction * _C[s] * hs, yi))
        nfev += 6
        y5 = [y[j] + direction * hs * sum(_B5[m] * ks[m][j] for m in range(6)) for j in range(len(y))]
        k7 = ks[6]
        y4 = [y[j] + direction * hs * sum(_B4[m] * ks[m][j] for m in range(7)) for j in range(len(y))]
        _check_finite(y5, t)
        err = _err_norm([a - b for a, b in zip(y5, y4)], y, y5, rtol, atol)
        if err <= 1.0:
            t_prev, y_prev, f_prev = t, y, k1
            t_new = stop if last else t + direction * hs
            if events:
                stop_now = _scan_events(events, f, lambda a, ya, b: rk45(f, a, ya, b, rtol * 1e-4, atol * 1e-4).final, gprev, t_prev, y_prev, f_prev, t_new, y5, ks[6], hits)
                if stop_now is not None:
                    ts.append(hits[-1].t)
                    ys.append(list(hits[-1].y))
                    return OdeResult(ts, ys, "RK45 (Dormand–Prince, adaptive)", steps + 1, nfev, rtol, atol, events=hits, stopped_by=stop_now)
            t = t_new
            y = y5
            k1 = ks[6]       # FSAL: the last stage is the first of the next step
            steps += 1
            if last:
                ts.append(t)
                ys.append(list(y))
                i += 1
            h = hs * min(10.0, 0.9 * err ** -0.2) if err > 0 else hs * 10.0
        else:
            h = hs * max(0.2, 0.9 * err ** -0.2)
            if h < 1e-14 * max(abs(t), 1.0):
                raise _TooManySteps("the step size collapsed")
        _ = k7
    return OdeResult(ts, ys, "RK45 (Dormand–Prince, adaptive)", steps, nfev, rtol, atol, events=hits)


def dde(f: Callable[[float, Vector, Vector], Vector], t0: float, y0: Sequence[float], t1: float, lags: Sequence[tuple[int, float]],
        outputs: Sequence[float] = (), rtol: float = 1e-8, atol: float = 1e-12, max_steps: int = RK_MAX_STEPS) -> OdeResult:
    """Delay differential equation ``y' = f(t, y, lagged)`` by the method of steps with Dormand–Prince 5(4) and cubic Hermite history.

    ``lags``: pairs ``(state index, delay)``; ``f`` receives, in that order, the values ``y_index(t - delay)``. Before ``t0`` the state is held at its initial value
    (constant history). The step never exceeds a twentieth of the shortest delay, so every delayed value lies in the part of the solution already computed and the cubic Hermite history is accurate, and the solution is
    stopped at ``t0 + k*delay`` where its derivative jumps (a delay equation's smoothness grows one derivative per delay). Forward in time only."""
    if t1 < t0:
        raise OdeError("a delay equation is integrated forward in time")
    y = [float(v) for v in y0]
    tau_min = min(tau for _i, tau in lags)
    if not tau_min > 0:
        raise OdeError("the delays must be positive")
    ht, hy, hf = [t0], [list(y)], []
    nfev = 0

    def lagged(t: float) -> Vector:
        out = []
        for idx, tau in lags:
            tt = t - tau
            if tt <= t0:
                out.append(y0[idx])
                continue
            k = min(max(bisect.bisect_right(ht, tt) - 1, 0), len(ht) - 2)
            if k < 0 or tt >= ht[-1]:
                out.append(hy[-1][idx])
                continue
            out.append(_hermite(ht[k], hy[k], hf[k], ht[k + 1], hy[k + 1], hf[k + 1], tt)[idx])
        return out

    def rhs(t: float, yy: Vector) -> Vector:
        return f(t, yy, lagged(t))

    k1 = rhs(t0, y)
    hf.append(k1)
    nfev += 1
    ts, ys = [t0], [list(y)]
    if t1 == t0:
        return OdeResult(ts, ys, "delay equation", 0, nfev, rtol, atol)
    span = t1 - t0
    wanted = {t for t in outputs if t0 < t < t1}
    breaks = {t0 + k * tau for _i, tau in lags for k in range(1, 400) if t0 + k * tau < t1} if span / tau_min <= 400 else set()
    stops = sorted(wanted | breaks) + [t1]
    h = min(_initial_step(rhs, t0, y, k1, 1.0, rtol, atol, span), tau_min)
    t, steps, i = t0, 0, 0
    while i < len(stops):
        stop = stops[i]
        if steps >= max_steps:
            raise _TooManySteps(f"more than {max_steps} steps")
        hs = min(h, tau_min / 20, stop - t)            # the history between two steps is a cubic Hermite interpolant; its error (not seen by the embedded estimate) falls with the fourth power of the step
        last = hs >= (stop - t) * (1 - 1e-12)
        ks = [k1]
        for st in range(1, 7):
            yi = [y[j] + hs * sum(_A[st][m] * ks[m][j] for m in range(st)) for j in range(len(y))]
            ks.append(rhs(t + _C[st] * hs, yi))
        nfev += 6
        y5 = [y[j] + hs * sum(_B5[m] * ks[m][j] for m in range(6)) for j in range(len(y))]
        y4 = [y[j] + hs * sum(_B4[m] * ks[m][j] for m in range(7)) for j in range(len(y))]
        _check_finite(y5, t)
        err = _err_norm([a - b for a, b in zip(y5, y4)], y, y5, rtol, atol)
        if err <= 1.0:
            t_new = stop if last else t + hs
            f_new = rhs(t_new, y5)
            nfev += 1
            ht.append(t_new)
            hy.append(list(y5))
            hf.append(f_new)
            t, y, k1 = t_new, y5, f_new
            steps += 1
            if last:
                if stop in wanted or stop == t1:
                    ts.append(t)
                    ys.append(list(y))
                i += 1
            h = hs * min(10.0, 0.9 * err ** -0.2) if err > 0 else hs * 10.0
        else:
            h = hs * max(0.2, 0.9 * err ** -0.2)
            if h < 1e-14 * max(abs(t), 1.0):
                raise _TooManySteps("the step size collapsed")
    return OdeResult(ts, ys, "delay equation: method of steps, Dormand–Prince with Hermite history", steps, nfev, rtol, atol)


def _scan_events(events: Sequence[EventSpec], f: Rhs, advance, gprev: list[float], t0: float, y0: Vector, f0: Vector, t1: float, y1: Vector, f1: Vector,
                 hits: list[EventHit]) -> int | None:
    """Look for crossings in the step ``t0 -> t1``; record them (earliest first) and return the index of a terminal event that stops the run."""
    found: list[tuple[float, int, Vector]] = []
    gnew = [e.g(t1, y1) for e in events]
    for k, e in enumerate(events):
        if gprev[k] == 0:
            gprev[k] = gnew[k]                      # an event that is already true at the start is not an event
            continue
        if _crossing(gprev[k], gnew[k], e.direction):
            te, ye = _locate(e, f, advance, t0, y0, f0, t1, y1, f1)
            found.append((te, k, ye))
    for k in range(len(events)):
        gprev[k] = gnew[k]
    found.sort(key=lambda x: (x[0] - t0) * (1 if t1 >= t0 else -1))
    for te, k, ye in found:
        scale = max((abs(v) for v in ye), default=0.0)
        ye = [0.0 if abs(v) < 1e-13 * scale else v for v in ye]      # the quantity that crossed zero should read zero, not 7e-15
        hits.append(EventHit(k, te, ye))
        if events[k].terminal:
            return k
    return None


class _TooManySteps(OdeError):
    """The explicit method is not suitable (stiff problem); caught by solve_ivp."""


# ---------------------------------------------------------------- implicit Euler + extrapolation

def _lu_solve(a: list[list[float]], b: Vector) -> Vector:
    try:
        x = np.linalg.solve(np.asarray(a, dtype=float), np.asarray(b, dtype=float))
    except np.linalg.LinAlgError:
        raise OdeError("singular matrix in the implicit solver") from None
    if not np.all(np.isfinite(x)):
        raise OdeError("singular matrix in the implicit solver")
    return x.tolist()


def _jacobian(f: Rhs, t: float, y: Vector, fy: Vector) -> list[list[float]]:
    n = len(y)
    jac = [[0.0] * n for _ in range(n)]
    for j in range(n):
        eps = 1.5e-8 * max(1.0, abs(y[j]))
        yp = list(y)
        yp[j] += eps
        fp = f(t, yp)
        for i in range(n):
            jac[i][j] = (fp[i] - fy[i]) / eps
    return jac


def _dense_factor(h: float, jac: list[list[float]]) -> Callable[[Vector], Vector]:
    """Solver for (I - h J) dz = rhs with a dense Jacobian."""
    n = len(jac)
    m = [[(1.0 if i == j else 0.0) - h * jac[i][j] for j in range(n)] for i in range(n)]
    return lambda b: _lu_solve(m, b)


def _backward_euler(f: Rhs, t: float, y: Vector, h: float, jac, factor=None) -> tuple[Vector, int]:
    """One implicit Euler step of size h (may be negative): z = y + h f(t+h, z), simplified Newton with a fixed Jacobian.
    ``factor(h, jac)`` returns a function solving (I - h J) dz = rhs; the default is a dense LU."""
    n = len(y)
    solve = (factor or _dense_factor)(h, jac)
    z = list(y)
    nfev = 0
    for _ in range(12):
        fz = f(t + h, z)
        nfev += 1
        g = [z[i] - y[i] - h * fz[i] for i in range(n)]
        dz = solve([-v for v in g])
        z = [z[i] + dz[i] for i in range(n)]
        if all(abs(dz[i]) <= 1e-12 * (1.0 + abs(z[i])) for i in range(n)):
            return z, nfev
    raise OdeError("the implicit solver's Newton iteration did not converge")


def stiff(f: Rhs, t0: float, y0: Sequence[float], t1: float, rtol: float = 1e-6, atol: float = 1e-9,
          outputs: Sequence[float] = (), max_steps: int = STIFF_MAX_STEPS, events: Sequence[EventSpec] = (),
          jacobian=None, factor=None) -> OdeResult:
    """``jacobian(f, t, y, fy)`` and ``factor(h, jac)`` replace the dense Jacobian and LU, e.g. with banded versions for method-of-lines problems."""
    y = [float(v) for v in y0]
    ts, ys = [t0], [list(y)]
    hits: list[EventHit] = []
    gprev = [e.g(t0, y) for e in events]
    if t1 == t0:
        return OdeResult(ts, ys, "implicit Euler with extrapolation (stiff)", 0, 0, rtol, atol)
    direction = 1.0 if t1 > t0 else -1.0
    stops = sorted({t for t in outputs if min(t0, t1) < t < max(t0, t1)}, key=lambda v: direction * v) + [t1]
    t, steps, nfev, i = t0, 0, 0, 0
    h = abs(t1 - t0) * 1e-4
    while i < len(stops):
        stop = stops[i]
        if steps >= max_steps:
            raise OdeError(f"more than {max_steps} steps in the stiff solver; the problem may be unbounded or too demanding")
        hs = min(h, abs(stop - t))
        last = hs >= abs(stop - t) * (1 - 1e-12)
        hv = direction * hs
        fy = f(t, y)
        nfev += 1
        jac = (jacobian or _jacobian)(f, t, y, fy)
        nfev += len(y) if jacobian is None else 3
        try:
            y1, n1 = _backward_euler(f, t, y, hv, jac, factor)
            ya, n2 = _backward_euler(f, t, y, hv / 2, jac, factor)
            y2, n3 = _backward_euler(f, t + hv / 2, ya, hv / 2, jac, factor)
        except OdeError:
            h = hs / 4
            if h < 1e-14 * max(abs(t), 1.0):
                raise
            continue
        nfev += n1 + n2 + n3
        err = _err_norm([a - b for a, b in zip(y2, y1)], y, y2, rtol, atol)
        if err <= 1.0:
            y_new = [2 * b - a for a, b in zip(y1, y2)]       # Richardson extrapolation: second order
            _check_finite(y_new, t)
            t_new = stop if last else t + hv
            if events:
                stop_now = _scan_events(events, f, lambda a, ya, b: stiff(f, a, ya, b, rtol * 1e-3, atol * 1e-3).final, gprev, t, y, fy, t_new, y_new, f(t_new, y_new), hits)
                if stop_now is not None:
                    ts.append(hits[-1].t)
                    ys.append(list(hits[-1].y))
                    return OdeResult(ts, ys, "implicit Euler with extrapolation (stiff)", steps + 1, nfev, rtol, atol, events=hits, stopped_by=stop_now)
            y = y_new
            t = t_new
            steps += 1
            if last:
                ts.append(t)
                ys.append(list(y))
                i += 1
        base = h if (err <= 1.0 and hs < h) else hs       # a step shortened only to land on an output does not say the step size should shrink
        h = base * min(5.0, max(0.2, 0.9 * err ** -0.5)) if err > 0 else base * 5.0
    return OdeResult(ts, ys, "implicit Euler with extrapolation (stiff)", steps, nfev, rtol, atol, events=hits)


# ---------------------------------------------------------------- front door

MAX_RESETS = 500


def solve_ivp(f: Rhs, t0: float, y0: Sequence[float], t1: float, outputs: Sequence[float] = (), rtol: float = 1e-8, atol: float = 1e-12,
              events: Sequence[EventSpec] = ()) -> OdeResult:
    """Integrate from ``t0`` to ``t1``; events with a ``reset`` make the state jump (a bounce, a switch) and the integration carries on from the new state."""
    if not any(e.reset for e in events):
        return _solve_segment(f, t0, y0, t1, outputs, rtol, atol, events)
    inner = [EventSpec(e.g, e.direction, True, None) if e.reset else e for e in events]      # a reset event ends a segment; the driver restarts after it
    direction = 1.0 if t1 >= t0 else -1.0
    t, y = t0, [float(v) for v in y0]
    ts, ys, hits = [t0], [list(y)], []
    steps = nfev = jumps = 0
    notes: list[str] = []
    method = ""
    while True:
        rest = [o for o in outputs if direction * (o - t) > 0 and direction * (t1 - o) >= 0]
        res = _solve_segment(f, t, y, t1, rest, rtol, atol, inner)
        steps, nfev, method = steps + res.steps, nfev + res.nfev, res.method
        notes += [n for n in res.notes if n not in notes]
        ts += res.ts[1:]
        ys += res.ys[1:]
        hits += res.events
        k = res.stopped_by
        if k is None or not events[k].reset:
            return OdeResult(ts, ys, method + (f"; {jumps} impulsive event{'s' if jumps != 1 else ''}" if jumps else ""), steps, nfev, rtol, atol, notes, hits, k)
        jumps += 1
        if jumps > MAX_RESETS:
            raise OdeError(f"more than {MAX_RESETS} impulsive events: the state may be accumulating at one time (Zeno behaviour, such as a ball bouncing ever lower); "
                           "stop the run at an earlier time or with a terminal event")
        t, y = res.ts[-1], [float(v) for v in events[k].reset(res.ts[-1], res.ys[-1])]
        if not all(math.isfinite(v) for v in y):
            raise OdeError("the state after an impulsive event is not finite")
        ts.append(t)                                  # the state just after the jump, at the same time as the one just before it
        ys.append(list(y))
        if direction * (t1 - t) <= 0:
            return OdeResult(ts, ys, method, steps, nfev, rtol, atol, notes, hits, None)


def _solve_segment(f: Rhs, t0: float, y0: Sequence[float], t1: float, outputs: Sequence[float] = (), rtol: float = 1e-8, atol: float = 1e-12,
                   events: Sequence[EventSpec] = ()) -> OdeResult:
    """Integrate from ``t0`` to ``t1``, recording the state at ``outputs`` too. Explicit RK45 first; stiff fallback if it needs too many steps."""
    try:
        return rk45(f, t0, y0, t1, rtol, atol, outputs, events=events)
    except _TooManySteps as exc:
        res = stiff(f, t0, y0, t1, max(rtol, 1e-6), max(atol, 1e-11), outputs, events=events)
        res.notes.append(f"the explicit RK45 method was abandoned ({exc}), which indicates a stiff problem; the implicit method was used instead")
        res.method = "implicit Euler with extrapolation (stiff), after RK45 proved inefficient"
        return res
    except (ZeroDivisionError, OverflowError, ValueError) as exc:
        raise OdeError(f"the equations could not be evaluated during integration: {exc}") from exc
