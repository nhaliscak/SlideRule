"""Standalone-script export of partial differential equations.

SlideRule solves its PDE systems with the method of lines on a uniform grid (second-order finite differences, ghost nodes at slope conditions, SciPy's BDF in time,
Newton's method for steady problems). An exported script repeats exactly that discretisation in a compact NumPy kernel (``PDE_SUPPORT``) driven by a plain-data
description (:func:`pde_spec`), so the numbers agree to the time-integration tolerance. The older single-field classes (a 1-D equation, a steady 2-D equation) are written
as the general system they are a special case of: a second-order-in-time equation becomes two first-order fields ``u`` and ``u_t``.
"""

from __future__ import annotations

import sympy as sp


def _kind(system) -> str | None:
    name = type(system).__name__
    if name == "PdeSystem":
        return "legacy1d"
    if name == "Pde2dSystem":
        return "legacy2d"
    if name == "PdeMulti":
        return "multi"
    if name == "FluxSystem":
        return "flux"
    return None


def pde_exportable(system) -> bool:
    return _kind(system) is not None


def pde_role(system, dep):
    if _kind(system) in ("multi", "flux"):
        if getattr(system, "moving", None) and dep == system.moving[0]:
            return ("front",)
        return ("field", system.fields.index(dep))
    return ("field", 0)


def _s(e) -> str:
    return sp.sstr(sp.sympify(e))


def pde_spec(system) -> dict:
    k = _kind(system)
    if k == "multi":
        return _spec_multi(system)
    if k == "flux":
        return _spec_flux(system)
    if k == "legacy1d":
        return _spec_legacy1d(system)
    return _spec_legacy2d(system)


def _spec_multi(sy) -> dict:
    coords = [q for q in (sy.x, sy.y, sy.z) if q is not None]
    names = [f.name for f in sy.fields]
    syms = [{role: s.name for role, s in dd.items()} for dd in sy.syms]
    bcs = []
    for (k, side), (kind, expr, _w) in sy.bcs.items():
        refs = [kk for kk in range(len(sy.fields)) if kk != k and expr.has(sy.syms[kk]["U"])]
        bcs.append([k, side, kind, _s(expr), refs])
    spans = [_s(e) for e in (sy.start, sy.end)] + ([_s(sy.y0), _s(sy.y1)] if sy.y is not None else []) + ([_s(sy.z0), _s(sy.z1)] if sy.z is not None else [])
    allnames = list(sy.inputs and [q.name for q in sy.inputs]) + [q.name for q in coords] + [sy.t.name] + [n for dd in syms for n in dd.values()]
    spec = {"kind": "pde", "inputs": [q.name for q in sy.inputs], "t": sy.t.name, "steady": bool(sy.steady), "dim": sy.dim, "coords": [q.name for q in coords],
            "fields": names, "syms": syms, "rhs": [_s(r) for r in sy.rhs], "u0": [_s(e) for e in sy.u0], "bcs": bcs, "spans": spans, "periodic": list(sy.periodic),
            "sources": [[k, [_s(p) for p in ps], _s(rate)] for k, ps, rate in sy.sources], "params": [q.name for q in sy.params], "N": sy.nodes + (sy.nodes % 2),
            "symbols": sorted(set(allnames)), "nonstiff": False}
    if getattr(sy, "cutouts", None):
        spec["cutouts"] = []
        for cut in sy.cutouts:
            cb = []
            for (k, side), (kind, expr, _w) in cut["bcs"].items():
                refs = [kk for kk in range(len(sy.fields)) if kk != k and expr.has(sy.syms[kk]["U"])]
                cb.append([k, side, kind, _s(expr), refs])
            spec["cutouts"].append({"box": [_s(e) for e in cut["box"]], "bcs": cb})
        spec["symbols"] = sorted(set(spec["symbols"]) | {q.name for cut in sy.cutouts for e in cut["box"] for q in e.free_symbols})
    if getattr(sy, "moving", None):
        spec["moving"] = {"front": sy.moving[0].name, "rate": _s(sy.moving[1])}
        spec["symbols"] = sorted(set(spec["symbols"]) | {sy.moving[0].name})
    return spec


def _spec_flux(sy) -> dict:
    U = [dd["U"] for dd in sy.syms]
    bcs = [[k, side, kind, _s(expr)] for (k, side), (kind, expr, _w) in sy.bcs.items()]
    names = [sy.x.name, sy.t.name] + [u.name for u in U] + [q.name for q in sy.inputs]
    return {"kind": "pde", "flux": True, "inputs": [q.name for q in sy.inputs], "t": sy.t.name, "x": sy.x.name, "fields": [f.name for f in sy.fields], "U": [u.name for u in U],
            "flux_expr": [_s(e) for e in sy.flux], "viscous": [_s(e) for e in sy.viscous], "source": [_s(e) for e in sy.source], "bcs": bcs, "periodic": sy.x.name in sy.periodic,
            "u0": [_s(e) for e in sy.u0], "spans": [_s(sy.start), _s(sy.end)], "params": [q.name for q in sy.params], "N": sy.nodes,
            "dry": [sy.dry_depth, list(sy.dry_zero), sy.dry_tol] if sy.dry_depth >= 0 else None, "symbols": sorted(set(names))}


def _spec_legacy1d(sy) -> dict:
    U, UT, UX, UXX = sy.symbols
    second = sy.order == 2
    names = [sy.dependent.name] + (["_v"] if second else [])
    syms = [{"U": U.name, "UX": UX.name, "UXX": UXX.name}]
    f = sy.rhs if second else sy.rhs.xreplace({UT: 0})
    rhs = [UT.name, _s(f)] if second else [_s(f)]                       # u_t = v, v_t = F for a second-order equation
    if second:
        syms.append({"U": UT.name, "UX": "_v__x", "UXX": "_v__xx"})
    bcs = []
    sides = ("start", "end")
    for side, (kind, expr, _w) in zip(sides, sy.bcs):
        e = expr if second else expr.xreplace({UT: 0})
        refs = [1] if second and e.has(UT) else []
        bcs.append([0, side, kind, _s(e), refs])
        if second:
            bcs.append([1, side, "value" if kind == "value" else "slope", "0", []])           # the velocity is 0 on a node held by a value condition (as in SlideRule)
    u0 = [_s(sy.u0)] + ([_s(sy.v0) if sy.v0 is not None else "0"] if second else [])
    names_all = [q.name for q in sy.inputs] + [sy.x.name, sy.t.name] + [n for dd in syms for n in dd.values()]
    return {"kind": "pde", "inputs": [q.name for q in sy.inputs], "t": sy.t.name, "steady": False, "dim": 1, "coords": [sy.x.name], "fields": names, "syms": syms, "rhs": rhs, "u0": u0,
            "bcs": bcs, "spans": [_s(sy.start), _s(sy.end)], "periodic": [], "sources": [], "params": [q.name for q in sy.params], "N": sy.nodes + (sy.nodes % 2),
            "symbols": sorted(set(names_all)), "nonstiff": second}


def _spec_legacy2d(sy) -> dict:
    U, UX, UY, UXX, UYY = sy.symbols
    syms = [{"U": U.name, "UX": UX.name, "UXX": UXX.name, "UY": UY.name, "UYY": UYY.name}]
    bcs = [[0, side, kind, _s(expr), []] for side, (kind, expr, _w) in sy.bcs.items()]
    guess = _s(sy.guess) if sy.guess is not None else "0"
    names_all = [q.name for q in sy.inputs] + [sy.x.name, sy.y.name, "t__steady"] + list(syms[0].values())
    return {"kind": "pde", "inputs": [q.name for q in sy.inputs], "t": "t__steady", "steady": True, "dim": 2, "coords": [sy.x.name, sy.y.name], "fields": [sy.dependent.name], "syms": syms,
            "rhs": [_s(sy.resid)], "u0": [guess], "bcs": bcs, "spans": [_s(sy.x0), _s(sy.x1), _s(sy.y0), _s(sy.y1)], "periodic": [], "sources": [], "params": [q.name for q in sy.params],
            "N": sy.nodes + (sy.nodes % 2), "symbols": sorted(set(names_all)), "nonstiff": False}


PDE_SUPPORT = '''
def _pde_groups(pattern):
    """Column groups for finite-difference Jacobians: columns that share no row can be perturbed together."""
    import numpy as np

    csc = pattern.tocsc()
    csr = pattern.tocsr()
    n = csc.shape[1]
    group = -np.ones(n, int)
    for j in range(n):
        used = set()
        for r in csc.indices[csc.indptr[j]:csc.indptr[j + 1]]:
            for c2 in csr.indices[csr.indptr[r]:csr.indptr[r + 1]]:
                if group[c2] >= 0:
                    used.add(group[c2])
        g = 0
        while g in used:
            g += 1
        group[j] = g
    return group, csc


def _pde_newton(fun, y0, pattern, scale):
    """Newton's method, Jacobian by finite differences over column groups, sparse LU, damped step."""
    import numpy as np
    from scipy.sparse import csc_matrix
    from scipy.sparse.linalg import splu

    group, csc = _pde_groups(pattern)
    ng = int(group.max()) + 1
    y = np.array(y0, float)
    f = fun(y)
    n0 = max(float(np.linalg.norm(f)), 1e-300)
    sc = max(max(scale), 1e-30)
    for it in range(40):
        data = np.zeros(csc.nnz)
        for g in range(ng):
            cols = np.nonzero(group == g)[0]
            hstep = 1e-7 * np.maximum(1.0, np.abs(y[cols]))
            yp = y.copy()
            yp[cols] += hstep
            df = (fun(yp) - f)
            for c2, hh in zip(cols, hstep):
                lo, hi = csc.indptr[c2], csc.indptr[c2 + 1]
                data[lo:hi] = df[csc.indices[lo:hi]] / hh
        J = csc_matrix((data, csc.indices, csc.indptr), shape=csc.shape)
        lu = splu(J)
        piv = np.abs(lu.U.diagonal())
        if piv.size and float(piv.min()) <= 1e-12 * float(piv.max()):
            raise ArithmeticError("the linearised equations are singular (every side has a slope condition?)")
        dy = lu.solve(-f)
        lam, fn = 1.0, None
        while lam > 1e-4:
            fn = fun(y + lam * dy)
            if np.all(np.isfinite(fn)) and np.linalg.norm(fn) <= (1 - 1e-4 * lam) * np.linalg.norm(f) + 1e-300:
                break
            lam /= 2
        y = y + lam * dy
        f = fn
        if float(np.max(np.abs(lam * dy))) <= 1e-10 * (float(np.max(np.abs(y))) + sc) or float(np.linalg.norm(f)) <= 1e-13 * n0:
            return y
    raise ArithmeticError("Newton's method did not converge")


def _pde_weights(pos, n):
    """Cubic Lagrange weights on the four nearest nodes of a uniform grid (index 0..n, position in grid units)."""
    import math

    i = min(max(int(math.floor(pos)), 0), n - 1)
    k0 = min(max(i - 1, 0), n - 3) if n >= 3 else 0
    pts = list(range(k0, min(k0 + 4, n + 1)))
    out = []
    for a in pts:
        w = 1.0
        for b in pts:
            if a != b:
                w *= (pos - b) / (a - b)
        out.append((a, w))
    return out


def _run_flux(spec, vals):
    """Conservation laws with shocks: cell averages, MUSCL reconstruction with the minmod limiter, the Rusanov flux and SSP Runge-Kutta 3 (the same scheme as SlideRule)."""
    import numpy as np

    local = {n: sp.Symbol(n, real=True) for n in spec["symbols"]}
    S = lambda text: sp.sympify(text, locals={**NS, **local})
    mods = ["scipy", "numpy", "math"]
    sub = {local[n]: sp.Float(vals[n], 17) for n in spec["params"]}
    xs_, ts_, Us = local[spec["x"]], local[spec["t"]], [local[n] for n in spec["U"]]
    args = [xs_, ts_, *Us]
    flux = [S(e).subs(sub) for e in spec["flux_expr"]]
    phi = sp.lambdify(args, flux, modules=mods)
    jacf = sp.lambdify(args, sp.Matrix(flux).jacobian(Us).tolist(), modules=mods)
    srcf = sp.lambdify(args, [S(e).subs(sub) for e in spec["source"]], modules=mods)
    viscf = sp.lambdify(args, [S(e).subs(sub) for e in spec["viscous"]], modules=mods)
    bcs = {(k, side): (kind, sp.lambdify([ts_], S(e).subs(sub), modules=mods) if kind == "value" else None) for k, side, kind, e in spec["bcs"]}
    u0f = [sp.lambdify([xs_], S(e).subs(sub), modules=mods) for e in spec["u0"]]
    lim = sp.lambdify([local[n] for n in spec["inputs"]], [S(e) for e in spec["spans"]], modules=mods)(*[vals[n] for n in spec["inputs"]])
    lo, hi = float(lim[0]), float(lim[1])
    N, nf, per = spec["N"], len(spec["fields"]), spec["periodic"]
    h = (hi - lo) / N
    xc = lo + h * (np.arange(N) + 0.5)

    def stack(res, shape):
        if isinstance(res, (list, tuple)):
            return np.array([stack(r, shape) for r in res], float)
        return np.broadcast_to(np.asarray(res, float), shape)
    minmod = lambda a, b: np.where(a * b > 0, np.where(np.abs(a) < np.abs(b), a, b), 0.0)
    U0 = np.empty((nf, N))
    for k in range(nf):
        U0[k] = np.broadcast_to(np.asarray(u0f[k](xc), float), (N,))
    dry = spec.get("dry")
    eps = 0.0
    if dry:
        eps = dry[2] * max(float(np.max(U0[dry[0]])), 1e-300)

    def fix(Sx):
        if not dry:
            return Sx
        Sx = Sx.copy()
        Sx[dry[0]] = np.maximum(Sx[dry[0]], 0.0)
        wet = Sx[dry[0]] >= eps
        for kz in dry[1]:
            Sx[kz] = np.where(wet, Sx[kz], 0.0)
        return Sx

    def floored(Sx):
        if not dry:
            return Sx
        Sx = Sx.copy()
        Sx[dry[0]] = np.maximum(Sx[dry[0]], eps)
        return Sx
    U0 = fix(U0)

    def ghosts(U, t, w=2):
        G = np.empty((nf, N + 2 * w))
        G[:, w:-w] = U
        for k in range(nf):
            if per:
                G[k, :w], G[k, -w:] = U[k, -w:], U[k, :w]
                continue
            for side, sl, edge in (("start", slice(0, w), U[k, 0]), ("end", slice(-w, None), U[k, -1])):
                kind, g = bcs[(k, side)]
                G[k, sl] = 2.0 * float(g(t)) - edge if kind == "value" else edge
        return G

    def numerics(U, t):
        G = ghosts(U, t)
        d_l, d_r = G[:, 1:-1] - G[:, :-2], G[:, 2:] - G[:, 1:-1]
        slope = minmod(d_l, d_r)
        left_state = G[:, 1:-1] + 0.5 * slope
        right_state = G[:, 1:-1] - 0.5 * slope
        UL, UR = fix(left_state[:, :-1]), fix(right_state[:, 1:])
        xi = lo + h * np.arange(N + 1)
        ULs, URs = floored(UL), floored(UR)
        FL, FR = stack(phi(xi, t, *ULs), (N + 1,)), stack(phi(xi, t, *URs), (N + 1,))

        def radius(Sx):
            J = stack(jacf(xi, t, *Sx), (N + 1,))
            if nf == 1:
                return np.abs(J[0, 0])
            return np.max(np.abs(np.linalg.eigvals(np.moveaxis(J, -1, 0))), axis=1)
        a = np.maximum(radius(ULs), radius(URs))
        Fl = 0.5 * (FL + FR) - 0.5 * a * (UR - UL)
        rhs = -(Fl[:, 1:] - Fl[:, :-1]) / h
        Us_ = floored(U)
        rhs = rhs + stack(srcf(xc, t, *Us_), (N,))
        vis = stack(viscf(xc, t, *Us_), (N,))
        if np.any(vis != 0):
            rhs = rhs + vis * (G[:, 2:] - 2 * G[:, 1:-1] + G[:, :-2])[:, 1:-1] / (h * h)
        return rhs, float(np.max(a)), (float(np.max(np.abs(vis))) if np.any(vis != 0) else 0.0)
    t_end = vals[spec["t"]]
    U, t = U0.copy(), 0.0
    steps = 0
    while t_end > 0 and t < t_end:
        rhs0, amax, nu = numerics(U, t)
        if not np.all(np.isfinite(rhs0)):
            raise ArithmeticError("the solution became non-finite")
        dt = (0.25 if dry else 0.4) * h / max(amax, 1e-300)
        if nu > 0:
            dt = min(dt, 0.25 * h * h / nu)
        if t + dt >= t_end * (1 - 1e-12):
            dt, hit = t_end - t, True
        else:
            hit = False
        steps += 1
        if steps > 400000:
            raise ArithmeticError("too many time steps")
        u1 = fix(U + dt * rhs0)
        u2 = fix(0.75 * U + 0.25 * (u1 + dt * numerics(u1, t + dt)[0]))
        U = fix(U / 3.0 + 2.0 / 3.0 * (u2 + dt * numerics(u2, t + 0.5 * dt)[0]))
        t = t_end if hit else t + dt
    x = min(max(vals[spec["x"]], lo), hi)
    ws = _pde_weights((x - xc[0]) / h, N - 1)
    return {"fields": [float(sum(w * U[k, i] for i, w in ws)) for k in range(nf)]}


def _run_pde_moving(spec, vals):
    """One space dimension on [start, s(t)] with the end moving as ds/dt = speed: the coordinate is stretched to a fixed interval and the front is one more unknown."""
    import numpy as np
    from scipy.integrate import solve_ivp
    from scipy.sparse import coo_matrix

    nf, N = len(spec["fields"]), spec["N"]
    local = {n: sp.Symbol(n, real=True) for n in spec["symbols"]}
    S = lambda text: sp.sympify(text, locals={**NS, **local})
    mods = ["scipy", "numpy", "math"]
    sub = {local[n]: sp.Float(vals[n], 17) for n in spec["params"]}
    xsym, tsym, ssym, syms = local[spec["coords"][0]], local[spec["t"]], local[spec["moving"]["front"]], spec["syms"]
    allsyms = [local[n] for dd in syms for n in dd.values()]
    F = sp.lambdify([xsym, tsym, ssym, *allsyms], [S(r).subs(sub) for r in spec["rhs"]], modules=mods)
    rate_f = sp.lambdify([xsym, tsym, ssym, *allsyms], S(spec["moving"]["rate"]).subs(sub), modules=mods)
    bc = {(k, side): (kind, sp.lambdify([tsym, ssym, local[syms[k]["U"]]], S(e).subs(sub), modules=mods)) for k, side, kind, e, _r in spec["bcs"]}
    u0f = [sp.lambdify([xsym], S(e).subs(sub), modules=mods) for e in spec["u0"]]
    lim = sp.lambdify([local[n] for n in spec["inputs"]], [S(e) for e in spec["spans"]], modules=mods)(*[vals[n] for n in spec["inputs"]])
    lo, s0 = float(lim[0]), float(lim[1])
    xi = np.arange(N + 1) / N
    h = 1.0 / N
    i2h, ih2 = 1.0 / (2 * h), 1.0 / (h * h)
    kinds = [{sd: bc[(k, sd)][0] for sd in ("start", "end")} for k in range(nf)]
    masks = []
    for k in range(nf):
        m = np.ones(N + 1, bool)
        if kinds[k]["start"] == "value":
            m[0] = False
        if kinds[k]["end"] == "value":
            m[N] = False
        masks.append(m)
    counts = [int(m.sum()) for m in masks]
    offs = np.cumsum([0, *counts])
    n_tot = int(offs[-1])
    names1 = [list(dd.keys()) for dd in syms]

    def full(y, t, s):
        out = []
        for k in range(nf):
            A = np.zeros(N + 1)
            A[masks[k]] = y[offs[k]:offs[k + 1]]
            if kinds[k]["start"] == "value":
                A[0] = bc[(k, "start")][1](t, s, 0.0)
            if kinds[k]["end"] == "value":
                A[N] = bc[(k, "end")][1](t, s, 0.0)
            out.append(A)
        return out

    def rhs(t, y):
        s = float(y[-1])
        L = s - lo
        if not L > 1e-6 * max(abs(s0 - lo), 1e-300):
            raise ArithmeticError("the moving boundary has reached the fixed end of the interval")
        U = full(y, t, s)
        Xc = lo + xi * L
        args, fronts, convect = [], [], []
        for k in range(nf):
            A = U[k]
            E = np.empty(N + 3)
            E[1:-1] = A
            E[0] = A[1] - 2 * h * L * float(bc[(k, "start")][1](t, s, A[0])) if kinds[k]["start"] == "slope" else A[0]
            E[-1] = A[N - 1] + 2 * h * L * float(bc[(k, "end")][1](t, s, A[N])) if kinds[k]["end"] == "slope" else A[N]
            c, up, dn = E[1:-1], E[2:], E[:-2]
            vx = (up - dn) * i2h
            vals_k = {"U": c, "UX": vx / L, "UXX": (up - 2 * c + dn) * ih2 / (L * L)}
            args += [vals_k[nm] for nm in names1[k]]
            convect.append(vx)
            slope_f = (3 * A[N] - 4 * A[N - 1] + A[N - 2]) * i2h / L if kinds[k]["end"] == "value" else float(bc[(k, "end")][1](t, s, A[N]))
            curv_f = (2 * A[N] - 5 * A[N - 1] + 4 * A[N - 2] - A[N - 3]) * ih2 / (L * L) if N >= 3 else 0.0
            fv = {"U": A[N], "UX": slope_f, "UXX": curv_f}
            fronts += [fv[nm] for nm in names1[k]]
        with np.errstate(all="ignore"):
            res = F(Xc, t, s, *args)
            sdot = float(rate_f(s, t, s, *fronts))
        out = np.empty(n_tot + 1)
        for k in range(nf):
            fk = np.broadcast_to(np.asarray(res[k], float), (N + 1,)) + xi * (sdot / L) * convect[k]
            out[offs[k]:offs[k + 1]] = fk[masks[k]]
        out[-1] = sdot
        return out
    y0 = np.empty(n_tot + 1)
    X0 = lo + xi * (s0 - lo)
    for k in range(nf):
        y0[offs[k]:offs[k + 1]] = np.broadcast_to(np.asarray(u0f[k](X0), float), (N + 1,))[masks[k]]
    y0[-1] = s0
    rows, cols = [], []
    idx = [-np.ones(N + 1, int) for _ in range(nf)]
    for k in range(nf):
        idx[k][masks[k]] = offs[k] + np.arange(counts[k])
    for a in range(nf):
        for i in np.nonzero(masks[a])[0]:
            for dj in (-1, 0, 1):
                j = min(max(i + dj, 0), N)
                for b in range(nf):
                    if idx[b][j] >= 0:
                        rows.append(idx[a][i])
                        cols.append(idx[b][j])
            rows.append(idx[a][i])
            cols.append(n_tot)
    for b in range(nf):
        for j in range(max(N - 3, 0), N + 1):
            if idx[b][j] >= 0:
                rows.append(n_tot)
                cols.append(idx[b][j])
    rows.append(n_tot)
    cols.append(n_tot)
    pattern = coo_matrix((np.ones(len(rows), bool), (rows, cols)), shape=(n_tot + 1, n_tot + 1)).tocsc()
    scale = [max(float(np.max(np.abs(y0[offs[k]:offs[k + 1]]))), 1e-30) for k in range(nf)]
    atol = np.concatenate([np.full(counts[k], 1e-9 * scale[k]) for k in range(nf)] + [[1e-10 * max(abs(s0 - lo), 1e-30)]])
    t_end = vals[spec["t"]]
    if t_end > 0:
        sol = solve_ivp(rhs, (0.0, t_end), y0, method="BDF", t_eval=[t_end], rtol=1e-8, atol=atol, jac_sparsity=pattern)
        if not sol.success:
            raise ArithmeticError("the time integration failed: " + sol.message)
        y = sol.y[:, -1]
    else:
        y = y0
    s_end = float(y[-1])
    fields = full(y, t_end, s_end)
    x = vals[spec["coords"][0]]
    if not lo - 1e-9 * (s_end - lo) <= x <= s_end + 1e-9 * (s_end - lo):
        raise ArithmeticError("the point lies outside the region")
    ws = _pde_weights((min(max(x, lo), s_end) - lo) / (s_end - lo) * N, N)
    return {"fields": [float(sum(w * fields[k][i] for i, w in ws)) for k in range(nf)], "front": s_end}


def _run_pde(spec, vals):
    """Method of lines on a uniform grid (1 to 3 space dimensions), the same finite differences as SlideRule: transient with BDF, steady with Newton."""
    import numpy as np
    from scipy.integrate import solve_ivp
    from scipy.sparse import coo_matrix

    if spec.get("flux"):
        return _run_flux(spec, vals)
    if spec.get("moving"):
        return _run_pde_moving(spec, vals)
    d, steady, nf, N = spec["dim"], spec["steady"], len(spec["fields"]), spec["N"]
    local = {n: sp.Symbol(n, real=True) for n in spec["symbols"]}
    S = lambda text: sp.sympify(text, locals={**NS, **local})
    mods = ["scipy", "numpy", "math"]
    sub = {local[n]: sp.Float(vals[n], 17) for n in spec["params"]}
    coords, tsym, syms = [local[c] for c in spec["coords"]], local[spec["t"]], spec["syms"]
    allsyms = [local[n] for dd in syms for n in dd.values()]
    F = sp.lambdify([*coords, tsym, *allsyms], [S(r).subs(sub) for r in spec["rhs"]], modules=mods)
    normal_of = {"start": 0, "end": 0, "left": 0, "right": 0, "bottom": 1, "top": 1, "front": 2, "back": 2}
    bc = {}
    for k, side, kind, expr, refs in spec["bcs"]:
        others = [coords[i] for i in range(d) if i != normal_of[side]]
        bc[(k, side)] = (kind, sp.lambdify([*others, tsym, local[syms[k]["U"]], *[local[syms[kk]["U"]] for kk in refs]], S(expr).subs(sub), modules=mods), refs)
    u0f = [sp.lambdify(coords, S(e).subs(sub), modules=mods) for e in spec["u0"]]
    srcs = [(k, [float(S(p).subs(sub)) for p in ps], sp.lambdify([tsym], S(rate).subs(sub), modules=mods)) for k, ps, rate in spec["sources"]]
    lim = sp.lambdify([local[n] for n in spec["inputs"]], [S(e) for e in spec["spans"]], modules=mods)(*[vals[n] for n in spec["inputs"]])
    spans = [(float(lim[2 * i]), float(lim[2 * i + 1])) for i in range(d)]
    t_end = 0.0 if steady else vals[spec["t"]]
    order = (2, 1, 0)[:d]
    n_ax, h_ax, lo_ax = [0, 0, 0], [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]
    for a, ax in enumerate(order):
        n_ax[ax], lo_ax[ax], h_ax[ax] = N, spans[a][0], (spans[a][1] - spans[a][0]) / N
    shp = tuple(n + 1 for n in n_ax)
    Zc, Yc, Xc = np.meshgrid(*[lo_ax[ax] + h_ax[ax] * np.arange(n_ax[ax] + 1) for ax in (0, 1, 2)], indexing="ij")
    coord_of = {0: Zc, 1: Yc, 2: Xc}
    names = [("start", "end")] if d == 1 else [("left", "right"), ("bottom", "top"), ("front", "back")][:d]
    side_of = {ax: names[a] for a, ax in enumerate(order)}
    per = {ax: spec["coords"][a] in spec["periodic"] for a, ax in enumerate(order)}
    kinds = [{s: ("periodic" if per[ax] else bc[(k, s)][0]) for ax in order for s in side_of[ax]} for k in range(nf)]

    def face(ax, hi):
        idx = [slice(None)] * 3
        idx[ax] = n_ax[ax] if hi else 0
        return tuple(idx)

    def along(ax, hi):
        return [coord_of[o][face(ax, hi)] for o in order if o != ax]
    masks = []
    for k in range(nf):
        m = np.ones(shp, bool)
        for ax in order:
            lo_s, hi_s = side_of[ax]
            if kinds[k][lo_s] == "value":
                m[face(ax, False)] = False
            if kinds[k][hi_s] == "value" or per[ax]:
                m[face(ax, True)] = False
        masks.append(m)
    hole = np.zeros(shp, bool)
    cuts_geo, cut_bc = [], {}
    for ci, cut in enumerate(spec.get("cutouts", [])):
        bx0, bx1, by0, by1 = (float(v) for v in sp.lambdify([local[n] for n in spec["inputs"]], [S(e) for e in cut["box"]], modules=mods)(*[vals[n] for n in spec["inputs"]]))
        i0, i1 = (2 * int(round((bx - lo_ax[2]) / h_ax[2] / 2)) for bx in (bx0, bx1))
        j0, j1 = (2 * int(round((by - lo_ax[1]) / h_ax[1] / 2)) for by in (by0, by1))
        i0, i1, j0, j1 = max(i0, 0), min(i1, N), max(j0, 0), min(j1, N)
        hc = np.zeros(shp, bool)
        hc[0, (j0 + 1 if j0 > 0 else 0):(j1 if j1 < N else N + 1), (i0 + 1 if i0 > 0 else 0):(i1 if i1 < N else N + 1)] = True
        hole |= hc
        cuts_geo.append({"hc": hc, "i0": i0, "i1": i1, "j0": j0, "j1": j1, "box": (bx0, bx1, by0, by1)})
        for k, side, kind, expr, refs in cut["bcs"]:
            other = coords[1] if side in ("left", "right") else coords[0]
            cut_bc[(ci, k, side)] = (kind, sp.lambdify([other, tsym, local[syms[k]["U"]], *[local[syms[kk]["U"]] for kk in refs]], S(expr).subs(sub), modules=mods), refs)
    cut_dir_nodes = [np.zeros(shp, bool) for _ in range(nf)]
    for ci, g_ in enumerate(cuts_geo):
        i0, i1, j0, j1 = g_["i0"], g_["i1"], g_["j0"], g_["j1"]
        faces = {"left": (i0 > 0, (0, slice(j0, j1 + 1), i0)), "right": (i1 < N, (0, slice(j0, j1 + 1), i1)), "bottom": (j0 > 0, (0, j0, slice(i0, i1 + 1))), "top": (j1 < N, (0, j1, slice(i0, i1 + 1)))}
        g_["faces"] = {}
        for side, (exposed, sl) in faces.items():
            if exposed:
                nodes = np.zeros(shp, bool)
                nodes[sl] = True
                g_["faces"][side] = nodes & ~hole
        hc = g_["hc"]
        adj = {"left": np.zeros(shp, bool), "right": np.zeros(shp, bool), "bottom": np.zeros(shp, bool), "top": np.zeros(shp, bool)}
        adj["left"][:, :, :-1] = hc[:, :, 1:]
        adj["right"][:, :, 1:] = hc[:, :, :-1]
        adj["bottom"][:, :-1, :] = hc[:, 1:, :]
        adj["top"][:, 1:, :] = hc[:, :-1, :]
        g_["adj"] = {sd: m_ & ~hole for sd, m_ in adj.items()}
        for side, nodes in g_["faces"].items():
            for k in range(nf):
                if cut_bc[(ci, k, side)][0] == "value":
                    cut_dir_nodes[k] |= nodes
    for k in range(nf):
        masks[k] = masks[k] & ~hole & ~cut_dir_nodes[k]
    counts = [int(m.sum()) for m in masks]
    offs = np.cumsum([0, *counts])
    n_tot = int(offs[-1])
    if min(counts) < 1:
        raise ArithmeticError("the boundary conditions leave no unknown nodes")
    idx_map = []
    for k in range(nf):
        im = -np.ones(shp, int)
        im[masks[k]] = offs[k] + np.arange(counts[k])
        idx_map.append(im)
    mixed = any("UXY" in dd and any(S(r).has(local[dd["UXY"]]) for r in spec["rhs"]) for dd in syms)

    def dirichlet(t):
        out = []
        for k in range(nf):
            A = np.zeros(shp)
            for ax in order:
                for hi, side in ((False, side_of[ax][0]), (True, side_of[ax][1])):
                    if kinds[k][side] == "value" and not bc[(k, side)][2]:
                        A[face(ax, hi)] = bc[(k, side)][1](*along(ax, hi), t, 0.0)
            for ci, g_ in enumerate(cuts_geo):
                for side, nodes in g_["faces"].items():
                    if cut_bc[(ci, k, side)][0] == "value":
                        A[nodes] = cut_bc[(ci, k, side)][1]((Yc if side in ("left", "right") else Xc)[nodes], t, 0.0)
            out.append(A)
        return out
    coupled_vals = [(k, ax, hi, side) for k in range(nf) for ax in order for hi, side in ((False, side_of[ax][0]), (True, side_of[ax][1])) if kinds[k][side] == "value" and bc[(k, side)][2]]

    def full(y, base, t):
        U = []
        for k in range(nf):
            A = base[k].copy()
            A[masks[k]] = y[offs[k]:offs[k + 1]]
            for ax in order:
                if per[ax]:
                    A[face(ax, True)] = A[face(ax, False)]
            U.append(A)
        for k, ax, hi, side in coupled_vals:
            _kind, fn_, refs = bc[(k, side)]
            U[k][face(ax, hi)] = fn_(*along(ax, hi), t, 0.0, *[U[kk][face(ax, hi)] for kk in refs])
        return U
    pad = [1 if n_ax[ax] else 0 for ax in (0, 1, 2)]
    core = tuple(slice(p_, p_ + s_) for p_, s_ in zip(pad, shp))

    def extend(A, k, t, U):
        E = np.empty(tuple(s_ + 2 * p_ for s_, p_ in zip(shp, pad)))
        E[core] = A
        for ax in order:
            lo_s, hi_s = side_of[ax]
            n, h = n_ax[ax], h_ax[ax]
            lo_g, hi_g = list(core), list(core)
            lo_g[ax], hi_g[ax] = 0, n + 2

            def at(i, ax=ax):
                ix = [slice(None)] * 3
                ix[ax] = i
                return tuple(ix)
            if per[ax]:
                E[tuple(lo_g)], E[tuple(hi_g)] = A[at(n - 1)], A[at(1)]
                continue
            if kinds[k][lo_s] == "slope":
                g = bc[(k, lo_s)][1](*along(ax, False), t, A[at(0)], *[U[kk][at(0)] for kk in bc[(k, lo_s)][2]])
                E[tuple(lo_g)] = A[at(1)] - 2 * h * g
            else:
                E[tuple(lo_g)] = A[at(0)]
            if kinds[k][hi_s] == "slope":
                g = bc[(k, hi_s)][1](*along(ax, True), t, A[at(n)], *[U[kk][at(n)] for kk in bc[(k, hi_s)][2]])
                E[tuple(hi_g)] = A[at(n - 1)] + 2 * h * g
            else:
                E[tuple(hi_g)] = A[at(n)]
        if d == 2:
            E[:, 0, 0], E[:, 0, -1], E[:, -1, 0], E[:, -1, -1] = E[:, 0, 1], E[:, 0, -2], E[:, -1, 1], E[:, -1, -2]
        return E

    def shifted(E, shifts):
        return E[tuple(slice(p_ + shifts.get(ax, 0), p_ + shifts.get(ax, 0) + s_) for ax, (p_, s_) in enumerate(zip(pad, shp)))]
    ih2 = {ax: 1.0 / (h_ax[ax] ** 2) for ax in order}
    i2h = {ax: 1.0 / (2 * h_ax[ax]) for ax in order}
    cell = float(np.prod([h_ax[ax] for ax in order]))
    names_of = {2: ("UX", "UXX"), 1: ("UY", "UYY"), 0: ("UZ", "UZZ")}
    src_nodes = []
    for k, positions, rate in srcs:
        ix = [0, 0, 0]
        for a, ax in enumerate(order):
            ix[ax] = min(max(int(round((positions[a] - lo_ax[ax]) / h_ax[ax])), 0), n_ax[ax])
        src_nodes.append((k, tuple(ix), rate))
    eps_ax = {ax: 1e-9 * (h_ax[ax] * n_ax[ax]) for ax in order}
    axis_cand = [ax for a, ax in enumerate(order) if lo_ax[ax] == 0.0 and not per[ax] and all(kinds[k][side_of[ax][0]] == "slope" for k in range(nf))]
    centers = []
    if axis_cand:
        one = np.ones((1, 1, 1))
        pr = [one * (0.0 if nm in ("UX", "UY", "UZ", "UXY") else 1.0) for dd in syms for nm in dd]
        try:
            with np.errstate(all="ignore"):
                r0 = F(*([np.zeros((1, 1, 1))] * d), 0.0, *pr)
            centers = list(axis_cand) if not all(np.all(np.isfinite(np.asarray(v, float))) for v in r0) else []
        except (ZeroDivisionError, ValueError, FloatingPointError):
            centers = list(axis_cand)

    def rhs(t, y):
        base = dirichlet(t)
        U = full(y, base, t)
        args = []
        for k in range(nf):
            E = extend(U[k], k, t, U)
            c = shifted(E, {})
            vals_k = {"U": c}
            for ax in order:
                nu, nuu = names_of[ax]
                up, dn = shifted(E, {ax: 1}), shifted(E, {ax: -1})
                if cuts_geo and ax in (1, 2):
                    up, dn = up.copy(), dn.copy()
                    for ci, g_ in enumerate(cuts_geo):
                        for side in (("left", "right") if ax == 2 else ("bottom", "top")):
                            M = g_["adj"][side]
                            if not M.any() or cut_bc[(ci, k, side)][0] == "value":
                                continue
                            lam_c, refs_c = cut_bc[(ci, k, side)][1], cut_bc[(ci, k, side)][2]
                            g_val = lam_c((Yc if side in ("left", "right") else Xc)[M], t, U[k][M], *[U[kk][M] for kk in refs_c])
                            if side in ("left", "bottom"):
                                up[M] = dn[M] + 2 * h_ax[ax] * g_val
                            else:
                                dn[M] = up[M] - 2 * h_ax[ax] * g_val
                vals_k[nu] = (up - dn) * i2h[ax]
                vals_k[nuu] = (up - 2 * c + dn) * ih2[ax]
            if "UXY" in syms[k]:
                vals_k["UXY"] = ((shifted(E, {1: 1, 2: 1}) - shifted(E, {1: 1, 2: -1}) - shifted(E, {1: -1, 2: 1}) + shifted(E, {1: -1, 2: -1})) * (i2h[1] * i2h[2]) if mixed else np.zeros_like(c))
            for ax in centers:
                nu, nuu = names_of[ax]
                sel = [slice(None)] * 3
                sel[ax] = 0
                vals_k[nu][tuple(sel)] = vals_k[nuu][tuple(sel)] * eps_ax[ax]
            for name in syms[k]:
                args.append(vals_k[name])
        cs = [Xc, Yc, Zc][:d]
        if centers:
            cs = [c_.copy() for c_ in cs]
            for ax in centers:
                sel = [slice(None)] * 3
                sel[ax] = 0
                cs[order.index(ax)][tuple(sel)] = eps_ax[ax]
        with np.errstate(all="ignore"):
            res = F(*cs, t, *args)
        out = np.empty(n_tot)
        for k in range(nf):
            fk = np.broadcast_to(np.asarray(res[k], float), shp).copy()
            for (kk, ix, rate) in src_nodes:
                if kk == k:
                    fk[ix] += float(rate(t)) / cell
            out[offs[k]:offs[k + 1]] = fk[masks[k]]
        if not np.all(np.isfinite(out)):
            raise ArithmeticError("the right-hand side is not finite at some grid node")
        return out
    y0 = np.empty(n_tot)
    for k in range(nf):
        A = np.broadcast_to(np.asarray(u0f[k](*[Xc, Yc, Zc][:d]), float), shp)
        y0[offs[k]:offs[k + 1]] = A[masks[k]]
    rows, cols = [], []
    offsets = [{}] + [{ax: s_} for ax in order for s_ in (-1, 1)]
    if mixed:
        offsets += [{1: a_, 2: b_} for a_ in (-1, 1) for b_ in (-1, 1)]
    for a in range(nf):
        nz_ = np.nonzero(masks[a])
        row_idx = idx_map[a][nz_]
        for off in offsets:
            nb = []
            for ax in (0, 1, 2):
                q = nz_[ax] + off.get(ax, 0)
                if per.get(ax, False):
                    q = np.where(q < 0, n_ax[ax] - 1, np.where(q >= n_ax[ax], q - n_ax[ax], q))
                nb.append(np.clip(q, 0, n_ax[ax]))
            for b in range(nf):
                col_idx = idx_map[b][tuple(nb)]
                ok = col_idx >= 0
                rows.append(row_idx[ok])
                cols.append(col_idx[ok])
    pattern = coo_matrix((np.ones(sum(len(r) for r in rows), bool), (np.concatenate(rows), np.concatenate(cols))), shape=(n_tot, n_tot)).tocsc()
    scale = [max(float(np.max(np.abs(y0[offs[k]:offs[k + 1]]))), 1e-30) for k in range(nf)]
    for k in range(nf):
        scale[k] = max(scale[k], float(np.max(np.abs(dirichlet(0.0)[k]))), float(np.max(np.abs(dirichlet(t_end)[k]))))
    if steady:
        y = _pde_newton(lambda yy: rhs(0.0, yy), y0, pattern, scale)
    elif t_end == 0:
        y = y0
    else:
        atol = np.concatenate([np.full(counts[k], 1e-9 * scale[k]) for k in range(nf)])
        sol = solve_ivp(rhs, (0.0, t_end), y0, method="DOP853" if spec.get("nonstiff") else "BDF", t_eval=[t_end], rtol=1e-8, atol=atol, **({} if spec.get("nonstiff") else {"jac_sparsity": pattern}))
        if not sol.success:
            raise ArithmeticError("the time integration failed: " + sol.message)
        y = sol.y[:, -1]
    fields = full(y, dirichlet(t_end), t_end)
    if hole.any():                      # the nodes inside a cutout get a smooth continuation of their neighbours (only used by the interpolation near a face)
        filled = []
        for A in fields:
            B = A.copy()
            B[hole] = float(B[~hole].mean())
            for _ in range(80):
                P = np.pad(B, ((0, 0), (1, 1), (1, 1)), mode="edge")
                B = np.where(hole, 0.25 * (P[:, :-2, 1:-1] + P[:, 2:, 1:-1] + P[:, 1:-1, :-2] + P[:, 1:-1, 2:]), A)
            filled.append(B)
        fields = filled
        for bx0, bx1, by0, by1 in (g_["box"] for g_ in cuts_geo):
            if bx0 < vals[spec["coords"][0]] < bx1 and by0 < vals[spec["coords"][1]] < by1:
                raise ArithmeticError("the point lies inside a cutout")
    point = [vals[spec["coords"][a]] for a in range(d)]
    value = []
    for k in range(nf):
        acc = 0.0
        pos = [(min(max(point[a], spans[a][0]), spans[a][1]) - lo_ax[order[a]]) / h_ax[order[a]] for a in range(d)]
        ws = [_pde_weights(pos[a], N) for a in range(d)]
        grid = fields[k]
        for idx_w in __import__("itertools").product(*ws):
            w = 1.0
            ix = [0, 0, 0]
            for a, (i_, w_) in enumerate(idx_w):
                w *= w_
                ix[order[a]] = i_
            acc += w * grid[tuple(ix)]
        value.append(float(acc))
    return {"fields": value}
'''
