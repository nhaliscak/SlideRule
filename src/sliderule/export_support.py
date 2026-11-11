"""Source text pasted into exported Python scripts: SciPy/NumPy re-solutions of the differential-equation systems SlideRule solves numerically.

An exported script has to stand on its own (SymPy, plus SciPy/NumPy where a differential equation is solved), so these helpers are *text* that
:mod:`sliderule.design_export` writes into the script. Each system is described by a plain dictionary (``spec``) of expression strings, and ``_system(name, spec, role)``
turns it into a SymPy function of the system's inputs whose value is one result of the solution (a state at the evaluation point, the time or the state at an
event, an unknown parameter of a boundary-value problem, a field of a partial differential equation).

* initial-value problems with events (``terminal``: the path stops; ``reset``: the state jumps) -- SciPy ``solve_ivp`` with event detection and restarts;
* delay equations -- the method of steps, one ``solve_ivp`` segment at a time with the history interpolated from the segments already computed;
* two-point boundary-value problems, with unknown parameters and a free end -- SciPy ``solve_bvp``;
* partial differential equations -- the same second-order finite differences as SlideRule, integrated in time with SciPy's BDF (see ``PDE_SUPPORT``).
"""

from __future__ import annotations

SYSTEM_SUPPORT = '''
_SYSTEM_RUNS = {}
_SYSTEM_COMPILED = {}


def _compile(spec):
    """The system's expressions as callables (SymPy -> NumPy)."""
    key = id(spec)
    if key in _SYSTEM_COMPILED:
        return _SYSTEM_COMPILED[key]
    inputs, tname, state, lags = spec["inputs"], spec["t"], spec["state"], spec.get("lags", [])
    unknowns = [u for u in spec.get("bvp", {}).get("unknowns", []) if u not in inputs]          # parameters found together with the solution
    local = {n: sp.Symbol(n, real=True) for n in [*inputs, *unknowns, *state, *lags]}
    S = lambda text: sp.sympify(text, locals={**NS, **local})
    L = lambda args, exprs: sp.lambdify(args, exprs, modules=["scipy", "numpy", "math"])
    names = [n for n in inputs if n != tname] + unknowns
    c = {"names": names, "inputs": inputs, "t": tname}
    base = [local[tname], *[local[s] for s in state]]
    c["f"] = L([*base, *[local[l] for l in lags], *[local[n] for n in names]], [S(r) for r in spec["rhs"]])
    c["ic"] = L([local[n] for n in inputs], [S(q) for q in spec["ics"]])
    c["t0"] = L([local[n] for n in inputs], S(spec["start"]))
    if lags:
        c["tau"] = [L([local[n] for n in inputs], S(tau)) for _i, tau in spec["lag_info"]]
    c["g"] = [L([*base, *[local[n] for n in names]], S(ev["g"])) for ev in spec.get("events", [])]
    c["reset"] = [L([*base, *[local[n] for n in names]], [S(r) for r in ev["reset"]]) if ev["reset"] else None for ev in spec.get("events", [])]
    _SYSTEM_COMPILED[key] = c
    return c


def _ivp(spec, c, a, rest, t0, t1, y0):
    """Initial-value problem, with events: a terminal event stops the path, a reset event restarts it from the jumped state."""
    from scipy.integrate import solve_ivp

    rhs = lambda t, y: c["f"](t, *y, *rest)
    events = spec.get("events", [])
    if not events:
        sol = solve_ivp(rhs, (t0, t1), y0, method="LSODA", rtol=1e-10, atol=1e-13)
        if not sol.success:
            raise ArithmeticError("the integration failed: " + sol.message)
        return {"t": t1, "y": [float(v) for v in sol.y[:, -1]], "hits": {}}
    funs = []
    for k, ev in enumerate(events):
        def fn(tt, yy, k=k):
            return float(c["g"][k](tt, *yy, *rest))
        fn.direction = {"either": 0, "rising": 1, "falling": -1}[ev["dir"]]
        fn.terminal = bool(ev["terminal"] or ev["reset"])
        funs.append(fn)
    hits, t, y = {}, t0, list(y0)
    for _ in range(100000):
        sol = solve_ivp(rhs, (t, t1), y, method="LSODA", rtol=1e-10, atol=1e-13, events=funs)
        if not sol.success:
            raise ArithmeticError("the integration failed: " + sol.message)
        stop = None
        for k, ev in enumerate(events):
            for te, ye in zip(sol.t_events[k], sol.y_events[k]):
                hits.setdefault(k, (float(te), [float(v) for v in ye]))
                if (ev["terminal"] or ev["reset"]) and (stop is None or te < stop[1]):
                    stop = (k, float(te), [float(v) for v in ye])
        if stop is None:
            return {"t": t1, "y": [float(v) for v in sol.y[:, -1]], "hits": hits}
        k, te, ye = stop
        if events[k]["terminal"]:
            return {"t": te, "y": ye, "hits": hits}
        y = [float(v) for v in c["reset"][k](te, *ye, *rest)]
        dt = 1e-12 * max(1.0, abs(te))                         # restart a hair after the jump so the event is not found again at once
        y = [yi + dt * float(fi) for yi, fi in zip(y, rhs(te, y))]
        t = te + dt
        if t >= t1:
            return {"t": t1, "y": y, "hits": hits}
    raise ArithmeticError("too many events")


def _series_start(c, rest, second, t0, y0, t1):
    """Start slightly off a singular point (a term u'/r at r = 0, as in the Lane-Emden equation): for each second-order quantity y = y0 + a d^2/2, y' = a d,
    with the curvature a found from the equation itself (it appears on both sides, since y'/r -> a)."""
    import math

    d = 1e-6 * (t1 - t0)
    y = list(y0)
    for idx in second:
        def g(av, idx=idx):
            yt = list(y)
            yt[idx] = y0[idx] + av * d * d / 2
            yt[idx + 1] = av * d
            try:
                return float(c["f"](t0 + d, *yt, *rest)[idx + 1]) - av
            except (ZeroDivisionError, ValueError, OverflowError):
                return math.nan
        a0, a1 = 0.0, 1.0
        g0, g1 = g(a0), g(a1)
        for _ in range(30):
            if not (math.isfinite(g0) and math.isfinite(g1)) or g1 == g0:
                break
            a2 = a1 - g1 * (a1 - a0) / (g1 - g0)
            a0, g0, a1, g1 = a1, g1, a2, g(a2)
            if abs(g1) <= 1e-14 * max(1.0, abs(a1)):
                break
        if math.isfinite(a1):
            y[idx] = y0[idx] + a1 * d * d / 2
            y[idx + 1] = a1 * d
    return t0 + d, y


def _dde(spec, c, a, rest, t0, t1, y0):
    """Delay equation by the method of steps: the history before the start is the initial state; segments never exceed the shortest delay."""
    import bisect
    from scipy.integrate import solve_ivp

    lags = [(i, float(g(*a))) for (i, _tau), g in zip(spec["lag_info"], c["tau"])]
    tau_min = min(tau for _i, tau in lags)
    if not tau_min > 0:
        raise ArithmeticError("the delays must be positive")
    starts, sols = [], []

    def lagged(t):
        out = []
        for idx, tau in lags:
            tt = t - tau
            if tt <= t0 or not starts:
                out.append(y0[idx])
                continue
            seg = sols[min(max(bisect.bisect_right(starts, tt) - 1, 0), len(starts) - 1)]
            out.append(float(seg.sol(min(max(tt, seg.t[0]), seg.t[-1]))[idx]))
        return out

    rhs = lambda t, y: c["f"](t, *y, *lagged(t), *rest)
    span = t1 - t0
    breaks = sorted({t0 + k * tau for _i, tau in lags for k in range(1, 400) if t0 + k * tau < t1}) if span / tau_min <= 400 else []
    stops = breaks + [t1]
    t, y = t0, list(y0)
    for stop in stops:
        while stop - t > 1e-14 * max(1.0, abs(stop)):
            t_next = min(t + tau_min, stop)
            sol = solve_ivp(rhs, (t, t_next), y, method="DOP853", rtol=1e-10, atol=1e-13, dense_output=True)
            if not sol.success:
                raise ArithmeticError("the integration failed: " + sol.message)
            starts.append(t)
            sols.append(sol)
            t, y = t_next, [float(v) for v in sol.y[:, -1]]
    return {"t": t1, "y": y, "hits": {}}


def _bvp(spec, c, a, vals, x_eval):
    """Boundary-value problem with SciPy's collocation solver: unknown parameters, a free end, conditions at interior points (the interval is split there and the pieces are
    joined by continuity) and events (the first place where a condition crosses zero) are all handled."""
    import numpy as np
    from scipy.integrate import solve_bvp, solve_ivp

    b = spec["bvp"]
    inputs, tname, state = spec["inputs"], spec["t"], spec["state"]
    n, unknowns = len(state), b["unknowns"]
    kfree = b["free"]
    base = [vals.get(nm, 0.0) for nm in c["names"]]
    pos = {nm: i for i, nm in enumerate(c["names"])}
    uidx = [pos[u] for u in unknowns]
    mods = ["scipy", "numpy", "math"]

    def plist(p):
        out = list(base)
        for i, v in zip(uidx, p):
            out[i] = v
        return out
    lo = float(c["t0"](*a))
    local = {nm: sp.Symbol(nm, real=True) for nm in [*c["names"], tname, *state]}
    S = lambda text: sp.sympify(text, locals={**NS, **local})
    ins = [local[nm] for nm in inputs]
    cond_args = [*[local[s] for s in state], *[local[nm] for nm in c["names"]]]
    conds = [(sp.lambdify(cond_args, S(r), modules=mods), w, (float(sp.lambdify(ins, S(pp), modules=mods)(*a)) if kfree is None else 0.0)) for r, w, pp in zip(b["residuals"], b["where"], b["positions"])]
    guess = np.array([float(v) for v in sp.lambdify(ins, [S(g) for g in b["guess"]], modules=mods)(*a)])
    theta0 = [float(v) for v in sp.lambdify(ins, [S(g) for g in b["theta"]], modules=mods)(*a)] if unknowns else []
    prof = {i: sp.lambdify(ins, S(e), modules=mods) for i, e in b["profile"].items()} if kfree is None else {}
    tpos = inputs.index(tname)
    if kfree is None:
        hi = float(sp.lambdify(ins, S(b["end"]), modules=mods)(*a))
        x0, x1 = lo, hi
        centre = False
        try:
            centre = not all(np.isfinite(np.asarray(c["f"](lo, *guess, *plist(theta0)), float)))
        except (ZeroDivisionError, ValueError, OverflowError, FloatingPointError):
            centre = True
        if centre:                         # an axis or centre at the start: begin a hair inside
            x0 = lo + 1e-7 * (hi - lo)
        interior = sorted({pp for _r, w, pp in conds if w == "other"})
        knots = [x0, *interior, x1]
    else:
        x0, x1, knots = 0.0, 1.0, [0.0, 1.0]
    m = len(knots) - 1

    def width(j, p):
        return (knots[j + 1] - knots[j]) if kfree is None else max(p[kfree] - lo, 1e-12 * max(abs(lo), 1.0))

    def xat(j, tau, p):
        return knots[j] + tau * width(j, p) if kfree is None else lo + width(j, p) * tau

    def fun(tau, Y, p):
        q = plist(p)
        return np.vstack([np.array([np.broadcast_to(width(j, p) * np.asarray(v, float), tau.shape) for v in c["f"](xat(j, tau, p), *Y[j * n:(j + 1) * n], *q)]) for j in range(m)])

    def bc(ya, yb, p):
        q = plist(p)
        out = []
        for r, w, pp in conds:
            if w == "start":
                out.append(float(r(*ya[0:n], *q)))
            elif w == "end":
                out.append(float(r(*yb[(m - 1) * n:m * n], *q)))
            else:
                j = min(range(m + 1), key=lambda i: abs(knots[i] - pp))
                out.append(float(r(*ya[j * n:(j + 1) * n], *q)))
        for j in range(m - 1):
            out += list(yb[j * n:(j + 1) * n] - ya[(j + 1) * n:(j + 2) * n])
        return np.array(out)
    tau_mesh = np.linspace(0.0, 1.0, 60)
    y_guess = np.tile(np.tile(guess, m)[:, None], (1, tau_mesh.size))
    try:                                  # the starting profile: the equations integrated from the guessed start state with the guessed parameters (a profile that obeys them)
        p_start = np.array(theta0, float)
        xs_all = [xat(j, tau_mesh, p_start) for j in range(m)]
        shot = solve_ivp(lambda x, y: np.array(c["f"](x, *y, *plist(p_start)), float) * (1.0 if kfree is None else width(0, p_start)), (xs_all[0][0] if kfree is None else 0.0, xs_all[-1][-1] if kfree is None else 1.0),
                         guess, dense_output=True, rtol=1e-6, atol=1e-9)
        if kfree is None and shot.success:
            cand = np.vstack([shot.sol(np.clip(xs_all[j], x0, x1)) for j in range(m)])
            if np.all(np.isfinite(cand)):
                y_guess = cand
        elif shot.success:
            cand = np.vstack([shot.sol(tau_mesh) for _j in range(m)])
            if np.all(np.isfinite(cand)):
                y_guess = cand
    except (ArithmeticError, ValueError, FloatingPointError):
        pass
    for i, fn_ in prof.items():
        for j in range(m):
            for q_, tau in enumerate(tau_mesh):
                aa = list(a)
                aa[tpos] = knots[j] + tau * (knots[j + 1] - knots[j])
                y_guess[j * n + i, q_] = float(fn_(*aa))
    if unknowns:
        sol = solve_bvp(fun, bc, tau_mesh, y_guess, p=np.array(theta0, float), tol=1e-9, max_nodes=100000)
    else:
        sol = solve_bvp(lambda x, y: fun(x, y, []), lambda ya, yb: bc(ya, yb, []), tau_mesh, y_guess, tol=1e-9, max_nodes=100000)
    if not sol.success:
        raise ArithmeticError("the boundary-value problem did not converge: " + sol.message)
    theta = [float(v) for v in sol.p] if unknowns else []
    p_fin = np.array(theta, float)
    hi_user = (lo + max(theta[kfree] - lo, 0.0)) if kfree is not None else hi

    def state_at(x):
        if kfree is None:
            j = min(max(int(np.searchsorted(knots, x, side="right")) - 1, 0), m - 1)
            tau = (x - knots[j]) / (knots[j + 1] - knots[j])
        else:
            j, tau = 0, (x - lo) / (hi_user - lo)
        return [float(v) for v in sol.sol(min(max(tau, 0.0), 1.0))[j * n:(j + 1) * n]]
    xe = x_eval if not (kfree is None and x_eval == lo and x0 != lo) else x0
    y = state_at(xe)
    hits = {}
    for k, ev in enumerate(spec.get("events", [])):
        direction = {"either": 0, "rising": 1, "falling": -1}[ev["dir"]]
        q = plist(p_fin)
        g = lambda x: float(c["g"][k](x, *state_at(x), *q))
        xs = [lo + (hi_user - lo) * i / 400 for i in range(401)]
        gs = [g(x) for x in xs]
        for i in range(400):
            if gs[i] == 0:
                continue
            ga, gb = gs[i], gs[i + 1]
            if (ga < 0 <= gb and direction >= 0) or (ga > 0 >= gb and direction <= 0):
                lo_, hi_ = xs[i], xs[i + 1]
                for _ in range(60):
                    mid = 0.5 * (lo_ + hi_)
                    gm = g(mid)
                    if (gm < 0) == (ga < 0) and gm != 0:
                        lo_, ga = mid, gm
                    else:
                        hi_ = mid
                    if abs(hi_ - lo_) <= 1e-13 * max(abs(hi_user - lo), 1e-300):
                        break
                xh = 0.5 * (lo_ + hi_)
                hits[k] = (xh, state_at(xh))
                break
    return {"y": y, "theta": theta, "hits": hits}


def _system(name, spec, role):
    """A SymPy function of the system's inputs whose value is one result of the numerical solution of ``spec`` (see ``role``)."""
    inputs, tname = spec["inputs"], spec["t"]

    def _eval_evalf(self, prec):
        if not all(getattr(a, "is_number", False) for a in self.args):
            return None
        vals = dict(zip(inputs, [float(v) for v in self.args]))
        key = (id(spec), tuple(vals[nm] for nm in inputs))
        if key not in _SYSTEM_RUNS:
            _SYSTEM_RUNS.clear() if len(_SYSTEM_RUNS) > 50 else None
            _SYSTEM_RUNS[key] = _run_system(spec, vals)
        res = _SYSTEM_RUNS[key]
        kind = role[0]
        if kind == "state":
            return sp.Float(res["y"][role[1]], 17)
        if kind == "unknown":
            return sp.Float(res["theta"][role[1]], 17)
        if kind in ("event_time", "event_value"):
            hit = res["hits"].get(role[1])
            if hit is None:
                raise ArithmeticError("the event does not occur before the evaluation point")
            return sp.Float(hit[0] if kind == "event_time" else hit[1][role[2]], 17)
        if kind == "field":
            return sp.Float(res["fields"][role[1]], 17)
        if kind == "front":
            return sp.Float(res["front"], 17)
        raise ArithmeticError("unknown result")
    return type(name, (sp.Function,), {"nargs": len(inputs), "_eval_evalf": _eval_evalf, "_eval_is_real": lambda self: True})


def _run_system(spec, vals):
    kind = spec["kind"]
    if kind == "pde":
        return _run_pde(spec, vals)
    c = _compile(spec)
    a = [vals[nm] for nm in spec["inputs"]]
    t0, t1 = float(c["t0"](*a)), vals[spec["t"]]
    y0 = [float(v) for v in c["ic"](*a)]
    rest = [vals[nm] for nm in c["names"]] if kind != "bvp" else []
    if kind == "bvp":
        return _bvp(spec, c, a, vals, t1)
    if t1 == t0:
        return {"t": t0, "y": y0, "hits": {}}
    if kind == "dde":
        return _dde(spec, c, a, rest, t0, t1, y0)
    ts, ys = t0, y0
    try:
        import numpy as np
        singular = not all(np.isfinite(np.asarray(c["f"](t0, *y0, *rest), float)))
    except (ZeroDivisionError, ValueError, OverflowError):
        singular = True
    if singular and spec.get("second"):
        ts, ys = _series_start(c, rest, spec["second"], t0, y0, t1)
    return _ivp(spec, c, a, rest, ts, t1, ys)
'''
