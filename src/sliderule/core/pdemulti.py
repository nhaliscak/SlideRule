"""Coupled and two-dimensional time-dependent partial differential equations, by the method of lines.

An ``odes`` entry with a ``time`` variable and more than one equation (coupled fields in one space dimension), or with a ``second`` space variable (a
time-dependent problem on a rectangle), is handled here; a single equation in one space dimension is :mod:`.pde`. Examples::

    {"title": "Reaction-diffusion", "independent": "x", "start": "0", "end": "L", "time": "t",
     "equations": ["diff(u, t) = Du*diff(u, x, 2) - u*v**2 + F*(1 - u)", "diff(v, t) = Dv*diff(v, x, 2) + u*v**2 - (F + k)*v"],
     "boundary": ["start: diff(u, x) = 0", "end: diff(u, x) = 0", "start: diff(v, x) = 0", "end: diff(v, x) = 0"],
     "initial": ["u = 1", "v = 0.25*exp(-100*(x/L - 0.5)**2)"]}

    {"title": "Plate cooling", "independent": "x", "start": "0", "end": "a", "second": "y", "second_start": "0", "second_end": "b", "time": "t",
     "equations": ["diff(T, t) = al*(diff(T, x, 2) + diff(T, y, 2))"],
     "boundary": ["left: T = Ts", "right: -k*diff(T, x) = h*(T - Tinf)", "bottom: diff(T, y) = 0", "top: T = Ts"], "initial": ["T = Ti"]}

Each equation is first order in time and solvable for its time derivative; it may use every field and its first and second space derivatives (and, in
two dimensions, the mixed derivative ``diff(u, x, y)`` when all sides are value or periodic conditions). Every field has one condition at each end (a value, or a
relation involving its own slope: Neumann, Robin), or the space variable is listed under ``periodic``. ``sources`` add a concentrated source (a heater, an injection
point) of strength ``rate`` (the field's units times length (times length) per time) at a position.

Numerics: uniform grid, second-order central differences (ghost nodes at slope conditions), vectorised with NumPy; the resulting stiff system is integrated with
SciPy's variable-order BDF method using the sparsity pattern of the stencil for its Jacobian. The grid is solved twice (N and N/2 intervals) and the difference is
reported as an error estimate; evaluation between nodes is by cubic interpolation.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import sympy as sp
from scipy.integrate import solve_ivp
from scipy.sparse import coo_matrix
from sympy.core.function import AppliedUndef

from .dimcheck import DIMENSIONLESS, DimensionError, analyze
from .numeric_ode import OdeError
from .pde import PdeResult, interpolate

MAX_FIELDS = 4
DEFAULT_NODES_1D, DEFAULT_NODES_2D, DEFAULT_NODES_3D = 100, 40, 16
LIMITS = {1: (10, 400), 2: (8, 120), 3: (6, 40)}
RTOL = 1e-5
MAX_NEWTON = 40
STEADY_LIMITS = {2: (8, 120), 3: (6, 28)}
SIDES_1D = ("start", "end")
SIDES_2D = ("left", "right", "bottom", "top")
SIDES_3D = ("left", "right", "bottom", "top", "front", "back")
_NP = ["scipy", "numpy"]


@dataclass
class MultiFields:
    xs: list[float]
    ys: list[float] | None
    times: list[float]
    u: dict                                   # field symbol -> list over times of arrays: (nz+1, ny+1, nx+1) in 3-D, (ny+1, nx+1) in 2-D, one row (1, nx+1) in 1-D
    result: PdeResult
    error: dict                               # field symbol -> estimated absolute discretisation error
    zs: list | None = None                    # third coordinate (three space dimensions)
    hole: Any = None                          # cutouts: boolean array (ny+1, nx+1), True at nodes inside a cutout
    cuts: list | None = None                  # cutouts: the snapped boxes (x0, x1, y0, y1) in SI
    front: tuple | None = None                # moving boundary: (times, front positions)
    xs_t: list | None = None                  # moving boundary: the grid at each stored time


def _lam(args, expr):
    """Vectorised lambdify (NumPy arrays in, array or scalar out)."""
    return sp.lambdify(args, expr, modules=_NP)


@dataclass
class PdeMulti:
    title: str
    texts: list[str]
    x: sp.Symbol
    y: sp.Symbol | None
    t: sp.Symbol
    start: sp.Expr                            # first space interval (also x0)
    end: sp.Expr
    y0: sp.Expr | None
    y1: sp.Expr | None
    fields: list                              # field symbols (the calculation's variables)
    syms: list                                # per field: dict name -> internal symbol (U, UX, UXX, UY, UYY, UXY)
    rhs: list                                 # per field: expression for its time derivative
    bcs: dict                                 # (field index, side) -> (kind, expr, written), kind "value" | "slope"
    periodic: list                            # names of periodic space variables
    u0: list
    sources: list                             # (field index, [position expressions, one per space variable], rate expr)
    nodes: int
    written: list
    condition_texts: list
    params: list
    inputs: list
    why_numeric: str = "the coupled / multi-dimensional partial differential equations are solved numerically by the method of lines"
    method: str = "numeric"
    closed: None = None
    events: list = field(default_factory=list)
    bvp: None = None
    pre: dict = field(default_factory=dict)
    aux_count: int = 0
    fns: dict = field(default_factory=dict)
    fallback: dict = field(default_factory=dict)
    lag_syms: list = field(default_factory=list)
    hidden: set = field(default_factory=set)
    z: Any = None                             # third space variable (three dimensions)
    z0: Any = None
    z1: Any = None
    cutouts: list = field(default_factory=list)   # rectangles removed from the region: {"box": (x0, x1, y0, y1) expressions, "bcs": {(field, side): (kind, expr, written)}}
    moving: Any = None                        # (front symbol, front speed expression): the interval end moves as ds/dt = speed (a Stefan problem), see _integrate_moving
    steady: bool = False                      # no time: the equations are residuals R(u, derivatives) = 0 solved by Newton's method
    _cache: dict = field(default_factory=dict, repr=False)

    numeric = True
    pde = True
    multi = True
    order = 1
    cell_centered = False                     # finite-volume subclasses: fields live at cell centres (the error estimate averages pairs of cells)

    # ---- interface shared with the other systems
    @property
    def dim(self) -> int:
        return 3 if self.z is not None else 2 if self.y is not None else 1

    @property
    def x0(self):
        return self.start

    @property
    def x1(self):
        return self.end

    @property
    def dependents(self) -> list:
        return list(self.fields)

    @property
    def initial_texts(self) -> list[str]:
        return []

    @property
    def condition_note(self) -> str:
        return "boundary and initial conditions"

    def last_result(self) -> PdeResult | None:
        return self._cache.get("last")

    def event_latex(self, names: dict) -> list:
        return []

    def written_latex(self, names: dict) -> list[str]:
        return [f"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)}" for a, b in self.written]

    def condition_latex(self, names: dict) -> list[str]:
        x = names.get(self.x, str(self.x))
        out = [rf"{x} \in \left[{sp.latex(self.start, symbol_names=names)},\; {sp.latex(self.end, symbol_names=names)}\right]"
               + (rf",\quad {names.get(self.y, str(self.y))} \in \left[{sp.latex(self.y0, symbol_names=names)},\; {sp.latex(self.y1, symbol_names=names)}\right]" if self.y is not None else "")
               + (rf",\quad {names.get(self.z, str(self.z))} \in \left[{sp.latex(self.z0, symbol_names=names)},\; {sp.latex(self.z1, symbol_names=names)}\right]" if self.z is not None else "")]
        for a, b, note in self.condition_texts:
            out.append(rf"{sp.latex(a, symbol_names=names)} = {sp.latex(b, symbol_names=names)} \quad \text{{({note})}}")
        return out

    def export_conditions(self) -> list:
        return list(self.condition_texts)

    # ---- numbers
    def _values(self, values: Mapping[sp.Symbol, float]) -> dict:
        return {s: float(values[s]) for s in self.inputs}

    def span(self, values: Mapping[sp.Symbol, float]):
        if "lim" not in self._cache:
            exprs = [self.start, self.end] + ([self.y0, self.y1] if self.y is not None else []) + ([self.z0, self.z1] if self.z is not None else [])
            self._cache["lim"] = _lam(self.inputs, exprs)
        vals = self._values(values)
        lim = [float(v) for v in self._cache["lim"](*[vals[s] for s in self.inputs])]
        pairs = [(lim[i], lim[i + 1]) for i in range(0, len(lim), 2)]
        if any(not b > a for a, b in pairs):
            raise OdeError("the ends of each interval must be increasing (end greater than start) (SI)")
        return pairs[0] if len(pairs) == 1 else tuple(pairs)

    def _bound(self, vals: dict):
        key = ("bound", tuple(vals[s] for s in self.params))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        sub = {s: sp.Float(vals[s], 17) for s in self.params}
        allsyms = [s for d in self.syms for s in d.values()]
        space = [s for s in (self.x, self.y, self.z) if s is not None]
        sfront = [self.moving[0]] if self.moving else []
        args = [*space, self.t, *sfront, *allsyms]
        F = _lam(args, [r.xreplace(sub) for r in self.rhs])
        bc = {}
        for (k, side), (kind, expr, _w) in self.bcs.items():
            normal = {"start": self.x, "end": self.x, "left": self.x, "right": self.x, "bottom": self.y, "top": self.y, "front": self.z, "back": self.z}[side]
            others = [s for s in space if s is not normal]               # what the condition may depend on, in x, y, z order
            refs = [kk for kk in range(len(self.fields)) if kk != k and expr.has(self.syms[kk]["U"])]            # other fields whose boundary values the condition reads
            bc[(k, side)] = (kind, _lam([*others, self.t, *sfront, self.syms[k]["U"], *[self.syms[kk]["U"] for kk in refs]], expr.xreplace(sub)), refs)
        cut_bc = {}
        for ci, cut in enumerate(self.cutouts):
            for (k, side), (kind, expr, _w) in cut["bcs"].items():
                other = self.y if side in ("left", "right") else self.x
                refs = [kk for kk in range(len(self.fields)) if kk != k and expr.has(self.syms[kk]["U"])]
                cut_bc[(ci, k, side)] = (kind, _lam([other, self.t, self.syms[k]["U"], *[self.syms[kk]["U"] for kk in refs]], expr.xreplace(sub)), refs)
        self._cache[("cutbc", tuple(vals[s_] for s_ in self.params))] = cut_bc
        u0 = [_lam(space, e.xreplace(sub)) for e in self.u0]
        src = []
        for k, positions, rate in self.sources:
            src.append((k, [float(q.xreplace(sub)) for q in positions], _lam([self.t], rate.xreplace(sub))))
        for kk in [kk for kk in self._cache if isinstance(kk, tuple) and kk and kk[0] == "bound"][5:]:
            del self._cache[kk]
        self._cache[key] = (F, bc, u0, src)
        return self._cache[key]

    # ---- one integration on an N-interval grid (N per space direction)
    def _integrate(self, vals: dict, times: list[float], N: int, t_end: float):
        """Method of lines on a uniform grid. Arrays are always three-dimensional, ``(nz+1, ny+1, nx+1)``, with singleton axes for the space dimensions not in use."""
        if self.moving:
            return self._integrate_moving(vals, times, N, t_end)
        d = self.dim
        F, bc, u0f, srcs = self._bound(vals)
        spans = self.span({s: vals[s] for s in self.inputs})
        spans = [spans] if d == 1 else list(spans)
        # per array axis (0 = z, 1 = y, 2 = x): intervals, spacing, coordinates, side names
        order = (2, 1, 0)[:d]                                          # array axes of x, y, z in turn
        n_ax = [0, 0, 0]
        h_ax = [1.0, 1.0, 1.0]
        lo_ax = [0.0, 0.0, 0.0]
        for a, ax in enumerate(order):
            n_ax[ax] = N
            lo_ax[ax] = spans[a][0]
            h_ax[ax] = (spans[a][1] - spans[a][0]) / N
        shp = tuple(n + 1 for n in n_ax)
        grids = np.meshgrid(*[lo_ax[ax] + h_ax[ax] * np.arange(n_ax[ax] + 1) for ax in (0, 1, 2)], indexing="ij")     # Z, Y, X
        Zc, Yc, Xc = grids
        coord_of = {0: Zc, 1: Yc, 2: Xc}
        names = [("start", "end")] if d == 1 else [("left", "right"), ("bottom", "top"), ("front", "back")][:d]
        side_of = {ax: names[a] for a, ax in enumerate(order)}
        sym_axes = [self.x, self.y, self.z][:d]
        nf = len(self.fields)
        per = {ax: sym_axes[a].name in self.periodic for a, ax in enumerate(order)}
        kinds = [{s: ("periodic" if per[ax] else bc[(k, s)][0]) for ax in order for s in side_of[ax]} for k in range(nf)]

        def face(ax, hi):
            idx = [slice(None)] * 3
            idx[ax] = n_ax[ax] if hi else 0
            return tuple(idx)

        def along(ax, hi):
            """Coordinate arrays on a face, for the other space variables in x, y, z order (what a condition may depend on)."""
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
        # cutouts: rectangles removed from the region, with their edges on grid lines (snapped to every second line so that the half-resolution check uses the same shape)
        hole = np.zeros(shp, bool)
        cuts_geo = []
        cut_dir = np.zeros(shp, bool)
        if self.cutouts:
            cut_bc = self._cache[("cutbc", tuple(vals[s_] for s_ in self.params))]
            cut_boxes = self._cut_boxes(vals)
            for ci, (bx0, bx1, by0, by1) in enumerate(cut_boxes):
                step = 2 * N // (self.nodes + self.nodes % 2)                      # the edges sit on every second line of the finest grid, so the half-resolution check sees the same shape
                i0, i1 = (step * int(round((bx - lo_ax[2]) / h_ax[2] / step)) for bx in (bx0, bx1))
                j0, j1 = (step * int(round((by - lo_ax[1]) / h_ax[1] / step)) for by in (by0, by1))
                i0, i1, j0, j1 = max(i0, 0), min(i1, N), max(j0, 0), min(j1, N)
                if i1 - i0 < 2 or j1 - j0 < 2:
                    raise OdeError(f"cutout {ci + 1} is too small for this grid (it spans fewer than 2 intervals): increase the number of nodes or enlarge it")
                hc = np.zeros(shp, bool)
                hc[0, (j0 + 1 if j0 > 0 else 0):(j1 if j1 < N else N + 1), (i0 + 1 if i0 > 0 else 0):(i1 if i1 < N else N + 1)] = True
                hole |= hc
                cuts_geo.append({"hc": hc, "i0": i0, "i1": i1, "j0": j0, "j1": j1, "box": (lo_ax[2] + i0 * h_ax[2], lo_ax[2] + i1 * h_ax[2], lo_ax[1] + j0 * h_ax[1], lo_ax[1] + j1 * h_ax[1])})
            for a_ in range(len(cuts_geo)):
                for b_ in range(a_ + 1, len(cuts_geo)):
                    if (cuts_geo[a_]["hc"] & cuts_geo[b_]["hc"]).any():
                        raise OdeError(f"cutouts {a_ + 1} and {b_ + 1} overlap")
            for ci, g_ in enumerate(cuts_geo):
                i0, i1, j0, j1 = g_["i0"], g_["i1"], g_["j0"], g_["j1"]
                faces = {"left": (i0 > 0, (0, slice(j0, j1 + 1), i0)), "right": (i1 < N, (0, slice(j0, j1 + 1), i1)),
                         "bottom": (j0 > 0, (0, j0, slice(i0, i1 + 1))), "top": (j1 < N, (0, j1, slice(i0, i1 + 1)))}
                g_["faces"] = {}
                for side, (exposed, sl) in faces.items():
                    if not exposed:
                        continue
                    nodes = np.zeros(shp, bool)
                    nodes[sl] = True
                    nodes &= ~hole
                    g_["faces"][side] = nodes
                    for k in range(nf):
                        if (ci, k, side) not in cut_bc:
                            raise OdeError(f"the {side} side of cutout {ci + 1} is part of the boundary of the region but {self.fields[k].name} has no condition there")
                # nodes whose neighbour across the face lies inside this cutout (their stencil reads the ghost value from the face condition)
                adj = {"left": np.zeros(shp, bool), "right": np.zeros(shp, bool), "bottom": np.zeros(shp, bool), "top": np.zeros(shp, bool)}
                hc = g_["hc"]
                adj["left"][:, :, :-1] = hc[:, :, 1:]
                adj["right"][:, :, 1:] = hc[:, :, :-1]
                adj["bottom"][:, :-1, :] = hc[:, 1:, :]
                adj["top"][:, 1:, :] = hc[:, :-1, :]
                g_["adj"] = {sd: m_ & ~hole for sd, m_ in adj.items()}
        cut_dir_nodes = [np.zeros(shp, bool) for _ in range(nf)]
        for ci, g_ in enumerate(cuts_geo):
            for side, nodes in g_["faces"].items():
                for k in range(nf):
                    if cut_bc[(ci, k, side)][0] == "value":
                        cut_dir_nodes[k] |= nodes
        for k in range(nf):
            masks[k] = masks[k] & ~hole & ~cut_dir_nodes[k]
        counts = [int(m.sum()) for m in masks]
        if min(counts) < 1:
            raise OdeError("the boundary conditions leave no unknown nodes; increase the number of nodes")
        offs = np.cumsum([0, *counts])
        n_tot = int(offs[-1])
        idx_map = []
        for k in range(nf):
            im = -np.ones(shp, int)
            im[masks[k]] = offs[k] + np.arange(counts[k])
            idx_map.append(im)
        mixed = any(("UXY" in dd) and self._uses(dd["UXY"]) for dd in self.syms)
        if mixed and any(kinds[k][s] == "slope" for k in range(nf) for ax in order for s in side_of[ax]):
            raise OdeError("a mixed derivative needs value or periodic conditions on every side")

        def dirichlet(t):
            """Full-grid arrays with every value condition applied (unknown nodes left at 0)."""
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
                            coord = Yc if side in ("left", "right") else Xc
                            A[nodes] = cut_bc[(ci, k, side)][1](coord[nodes], t, 0.0)
                out.append(A)
            return out

        coupled_vals = [(k, ax, hi, side) for k in range(nf) for ax in order for hi, side in ((False, side_of[ax][0]), (True, side_of[ax][1]))
                        if kinds[k][side] == "value" and bc[(k, side)][2]]

        def full(y, base, t):
            """The fields on the whole grid from the unknowns ``y`` (value conditions applied, periodic duplicates copied; a value that reads other fields is set last)."""
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
            """Ghost layers: slope conditions (second order, from the condition), periodic wrap, or a copy where unused."""
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
            if d == 2:                                                # corners: only a mixed derivative reads them
                E[:, 0, 0], E[:, 0, -1], E[:, -1, 0], E[:, -1, -1] = E[:, 0, 1], E[:, 0, -2], E[:, -1, 1], E[:, -1, -2]
            return E

        def shifted(E, shifts):
            """The interior of ``E`` displaced by ``shifts`` (array-axis -> -1, 0 or 1)."""
            return E[tuple(slice(p_ + shifts.get(ax, 0), p_ + shifts.get(ax, 0) + s_) for ax, (p_, s_) in enumerate(zip(pad, shp)))]

        ih2 = {ax: 1.0 / (h_ax[ax] ** 2) for ax in order}
        i2h = {ax: 1.0 / (2 * h_ax[ax]) for ax in order}
        cell = float(np.prod([h_ax[ax] for ax in order]))
        names_of = {2: ("UX", "UXX"), 1: ("UY", "UYY"), 0: ("UZ", "UZZ")}
        # concentrated sources: the nearest node receives rate / cell size
        src_nodes = []
        for k, positions, rate in srcs:
            ix = [0, 0, 0]
            for a, ax in enumerate(order):
                ix[ax] = min(max(int(round((positions[a] - lo_ax[ax]) / h_ax[ax])), 0), n_ax[ax])
            src_nodes.append((k, tuple(ix), rate))

        # an axis or centre (cylindrical or spherical coordinates: terms such as u_x/x) at the start of an interval with a symmetry (slope) condition: the term is 0/0 there.
        # Its limit is u_xx, so that node is evaluated at a tiny coordinate with u_x = u_xx * (that coordinate), the Taylor expansion of a function with zero slope there.
        eps_ax = {ax: 1e-9 * (h_ax[ax] * n_ax[ax]) for ax in order}
        axis_cand = [ax for a, ax in enumerate(order) if lo_ax[ax] == 0.0 and not per[ax] and all(kinds[k][side_of[ax][0]] == "slope" for k in range(nf))]

        def singular_probe() -> bool:
            one = np.ones((1, 1, 1))
            pr = [one * (0.0 if name in ("UX", "UY", "UZ", "UXY") else 1.0) for dd in self.syms for name in dd]
            with np.errstate(all="ignore"):
                r0 = F(*([np.zeros((1, 1, 1))] * d), 0.0, *pr)
            return not all(np.all(np.isfinite(np.asarray(v, float))) for v in r0)
        centers: list[int] = []
        if axis_cand:
            try:
                centers = list(axis_cand) if singular_probe() else []
            except (ZeroDivisionError, ValueError, FloatingPointError):
                centers = list(axis_cand)

        def rhs(t, y):
            base = dirichlet(t)
            U = full(y, base, t)
            args = []
            for k in range(nf):
                E = extend(U[k], k, t, U)
                c = shifted(E, {})
                vals_k: dict = {"U": c}
                for ax in order:
                    nu, nuu = names_of[ax]
                    up, dn = shifted(E, {ax: 1}), shifted(E, {ax: -1})
                    if cuts_geo and ax in (1, 2):
                        up, dn = up.copy(), dn.copy()
                        for ci, g_ in enumerate(cuts_geo):
                            for side in (("left", "right") if ax == 2 else ("bottom", "top")):
                                M = g_["adj"][side]
                                if not M.any():
                                    continue
                                kind_c, lam_c, refs_c = cut_bc[(ci, k, side)]
                                if kind_c == "value":
                                    continue                                  # the node is fixed by the condition: its row is not used
                                coord = Yc if side in ("left", "right") else Xc
                                g_val = lam_c(coord[M], t, U[k][M], *[U[kk][M] for kk in refs_c])
                                if side in ("left", "bottom"):
                                    up[M] = dn[M] + 2 * h_ax[ax] * g_val       # the slope across the face gives the value one step inside the cutout
                                else:
                                    dn[M] = up[M] - 2 * h_ax[ax] * g_val
                    vals_k[nu] = (up - dn) * i2h[ax]
                    vals_k[nuu] = (up - 2 * c + dn) * ih2[ax]
                if "UXY" in self.syms[k]:
                    vals_k["UXY"] = ((shifted(E, {1: 1, 2: 1}) - shifted(E, {1: 1, 2: -1}) - shifted(E, {1: -1, 2: 1}) + shifted(E, {1: -1, 2: -1})) * (i2h[1] * i2h[2]) if mixed else np.zeros_like(c))
                for ax in centers:
                    nu, nuu = names_of[ax]
                    sel = [slice(None)] * 3
                    sel[ax] = 0
                    vals_k[nu][tuple(sel)] = vals_k[nuu][tuple(sel)] * eps_ax[ax]
                for name in self.syms[k]:
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
                raise OdeError("the right-hand side is not finite at some grid node (a term such as 1/x with x = 0 away from a symmetry axis?); an axis or centre at the start of an "
                               "interval is supported when every field has a slope (symmetry) condition there")
            return out

        y0 = np.empty(n_tot)
        for k in range(nf):
            A = np.broadcast_to(np.asarray(u0f[k](*[Xc, Yc, Zc][:d]), float), shp)
            y0[offs[k]:offs[k + 1]] = A[masks[k]]
        if not np.all(np.isfinite(y0)):
            raise OdeError("the initial condition is not finite at every node")
        # sparsity pattern of the Jacobian: every unknown depends on the neighbours along each axis (and the diagonals for a mixed derivative) and on the other fields there
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
        for k in range(nf):                                          # value conditions also set the size of the field
            for ax in order:
                for side in side_of[ax]:
                    if kinds[k][side] == "value":
                        scale[k] = max(scale[k], float(np.max(np.abs(dirichlet(0.0)[k]))), float(np.max(np.abs(dirichlet(t_end)[k]))))
        atol = np.concatenate([np.full(counts[k], 1e-6 * scale[k]) for k in range(nf)])
        want = sorted({tt for tt in times if 0.0 < tt < t_end} | {t_end}) if t_end > 0 else []
        if self.steady:
            ysol, its = _newton(lambda yy: rhs(0.0, yy), y0, pattern, scale)
            sol_t, sol_y, steps, nfev = [0.0], [ysol], its, its
        elif t_end == 0:
            sol_t, sol_y = [0.0], [y0]
            steps = nfev = 0
        else:
            try:
                sol = solve_ivp(rhs, (0.0, t_end), y0, method="BDF", t_eval=want, rtol=RTOL, atol=atol, jac_sparsity=pattern)
            except (ValueError, ArithmeticError) as exc:
                raise OdeError(f"the time integration failed: {exc}") from None
            if not sol.success:
                raise OdeError(f"the time integration failed: {sol.message}")
            sol_t, sol_y = [0.0, *sol.t.tolist()], [y0, *[sol.y[:, i] for i in range(sol.y.shape[1])]]
            steps, nfev = int(sol.nfev), int(sol.nfev)
        fields_t = []
        for tt, yv in zip(sol_t, sol_y):
            fl = full(yv, dirichlet(tt), tt)
            if cuts_geo:
                fl = [_fill_hole(A, hole) for A in fl]
            fields_t.append([self._natural(A) for A in fl])
        if cuts_geo:
            self._cache["_hole"] = (hole[0], [g_["box"] for g_ in cuts_geo])
        xs = lo_ax[2] + h_ax[2] * np.arange(n_ax[2] + 1)
        ys = (lo_ax[1] + h_ax[1] * np.arange(n_ax[1] + 1)) if d >= 2 else np.array([0.0])
        zs = (lo_ax[0] + h_ax[0] * np.arange(n_ax[0] + 1)) if d >= 3 else np.array([0.0])
        return sol_t, fields_t, steps, nfev, xs, (ys, zs)

    def _integrate_moving(self, vals: dict, times: list[float], N: int, t_end: float):
        """One space dimension on [start, s(t)] with the end moving as ds/dt = speed(fields at the front). The coordinate is stretched to a fixed interval,
        x = start + xi (s - start), so v(xi, t) = u(x, t) satisfies v_t = F(v, v_xi/L, v_xi,xi/L^2) + xi (L'/L) v_xi with L = s - start; the front position is one more unknown."""
        F, bc, u0f, _srcs = self._bound(vals)
        sub = {q: sp.Float(vals[q], 17) for q in self.params}
        allsyms = [q for dd in self.syms for q in dd.values()]
        rate_f = _lam([self.x, self.t, self.moving[0], *allsyms], self.moving[1].xreplace(sub))
        lo, s0 = self.span({q: vals[q] for q in self.inputs})
        nf = len(self.fields)
        xi = np.arange(N + 1) / N
        h = 1.0 / N
        i2h, ih2 = 1.0 / (2 * h), 1.0 / (h * h)
        if self.periodic:
            raise OdeError("a moving boundary cannot be combined with a periodic direction")
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
        if min(counts) < 1:
            raise OdeError("the boundary conditions leave no unknown nodes; increase the number of nodes")
        names1 = [list(dd.keys()) for dd in self.syms]

        def full(y, t, s):
            """The fields on the whole grid: unknowns from y, value conditions at the ends."""
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
                raise OdeError("the moving boundary has reached the fixed end of the interval (the region has vanished)")
            U = full(y, t, s)
            Xc = lo + xi * L
            args, fronts, convect = [], [], []
            for k in range(nf):
                A = U[k]
                E = np.empty(N + 3)
                E[1:-1] = A
                if kinds[k]["start"] == "slope":
                    E[0] = A[1] - 2 * h * L * float(bc[(k, "start")][1](t, s, A[0]))
                else:
                    E[0] = A[0]
                if kinds[k]["end"] == "slope":
                    E[-1] = A[N - 1] + 2 * h * L * float(bc[(k, "end")][1](t, s, A[N]))
                else:
                    E[-1] = A[N]
                c, up, dn = E[1:-1], E[2:], E[:-2]
                vx = (up - dn) * i2h
                vals_k = {"U": c, "UX": vx / L, "UXX": (up - 2 * c + dn) * ih2 / (L * L)}
                args += [vals_k[nm] for nm in names1[k]]
                convect.append(vx)
                # the field and its derivatives at the front (one-sided, second order) for the speed
                slope_f = (3 * A[N] - 4 * A[N - 1] + A[N - 2]) * i2h / L if kinds[k]["end"] == "value" else float(bc[(k, "end")][1](t, s, A[N]))
                curv_f = (2 * A[N] - 5 * A[N - 1] + 4 * A[N - 2] - A[N - 3]) * ih2 / (L * L) if N >= 3 else 0.0
                fv = {"U": A[N], "UX": slope_f, "UXX": curv_f}
                fronts += [fv[nm] for nm in names1[k]]
            with np.errstate(all="ignore"):
                res = F(Xc, t, s, *args)
                sdot = float(rate_f(s, t, s, *fronts))
            if not np.isfinite(sdot):
                raise OdeError("the speed of the moving boundary is not finite")
            out = np.empty(n_tot + 1)
            for k in range(nf):
                fk = np.broadcast_to(np.asarray(res[k], float), (N + 1,)) + xi * (sdot / L) * convect[k]
                out[offs[k]:offs[k + 1]] = fk[masks[k]]
            out[-1] = sdot
            if not np.all(np.isfinite(out)):
                raise OdeError("the right-hand side is not finite at some grid node")
            return out

        y0 = np.empty(n_tot + 1)
        X0 = lo + xi * (s0 - lo)
        for k in range(nf):
            A = np.broadcast_to(np.asarray(u0f[k](X0), float), (N + 1,))
            y0[offs[k]:offs[k + 1]] = A[masks[k]]
        y0[-1] = s0
        if not np.all(np.isfinite(y0)):
            raise OdeError("the initial condition is not finite at every node")
        # Jacobian pattern: neighbours along xi and the other fields; every row depends on the front position; the front speed depends on the last nodes
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
        atol = np.concatenate([np.full(counts[k], 1e-6 * scale[k]) for k in range(nf)] + [[1e-8 * max(abs(s0 - lo), 1e-30)]])
        want = sorted({tt for tt in times if 0.0 < tt < t_end} | {t_end}) if t_end > 0 else []
        if t_end == 0:
            sol_t, sol_y, steps = [0.0], [y0], 0
        else:
            try:
                sol = solve_ivp(rhs, (0.0, t_end), y0, method="BDF", t_eval=want, rtol=RTOL, atol=atol, jac_sparsity=pattern)
            except (ValueError, ArithmeticError) as exc:
                raise OdeError(f"the time integration failed: {exc}") from None
            if not sol.success:
                raise OdeError(f"the time integration failed: {sol.message}")
            sol_t, sol_y, steps = [0.0, *sol.t.tolist()], [y0, *[sol.y[:, i] for i in range(sol.y.shape[1])]], int(sol.nfev)
        fields_t, fronts_t, xs_t = [], [], []
        for tt, yv in zip(sol_t, sol_y):
            fronts_t.append(float(yv[-1]))
            xs_t.append(lo + xi * (float(yv[-1]) - lo))
            fields_t.append([self._natural(A) for A in full(yv, tt, float(yv[-1]))])
        self._cache["_moving"] = (sol_t, fronts_t, xs_t)
        return sol_t, fields_t, steps, steps, xs_t[-1], (np.array([0.0]), np.array([0.0]))

    def front_value(self, values: Mapping[sp.Symbol, float]) -> float:
        f = self.run(values)
        return f.front[1][-1]

    def _cut_boxes(self, vals: dict) -> list:
        if "cutlam" not in self._cache:
            self._cache["cutlam"] = [_lam(self.inputs, list(c["box"])) for c in self.cutouts]
        return [tuple(float(v) for v in f(*[vals[s_] for s_ in self.inputs])) for f in self._cache["cutlam"]]

    def _natural(self, A):
        """The stored shape of a field: ``(1, nx+1)`` for one space dimension, ``(ny+1, nx+1)`` for two, ``(nz+1, ny+1, nx+1)`` for three."""
        return A.reshape(1, -1) if self.dim == 1 else (A[0] if self.dim == 2 else A)

    def _uses(self, sym) -> bool:
        return any(r.has(sym) for r in self.rhs)

    def run(self, values: Mapping[sp.Symbol, float], outputs=(), final_only: bool = False) -> MultiFields:
        vals = self._values(values)
        t_end = 0.0 if self.steady else vals[self.t]
        if t_end < 0:
            raise OdeError(f"the time must not be negative (got {t_end:g} s)")
        times = sorted({t_end * i / 60 for i in range(1, 60)} | {o for o in outputs if 0 < o < t_end}) if t_end > 0 else []
        key = (tuple(vals[s] for s in self.inputs if s not in (self.x, self.y, self.z)), tuple(times))
        hit = self._cache.get(("run", key))
        if hit is not None:
            self._cache["last"] = hit.result
            return hit
        lo_n, hi_n = LIMITS[self.dim]
        N = self.nodes + (self.nodes % 2)
        ts, fields, steps, nfev, xs, (ys, zs) = self._integrate(vals, times, N, t_end)
        moving = self._cache.pop("_moving", None) if self.moving else None
        hole_info = self._cache.pop("_hole", None)
        notes: list[str] = []
        err = {f: 0.0 for f in self.fields}
        if N >= 2 * lo_n:
            _tc, fields_c, steps_c, nfev_c, _xc, _yc = self._integrate(vals, [], N // 2, t_end)
            steps, nfev = steps + steps_c, nfev + nfev_c
            self._cache.pop("_hole", None)
            if moving is not None:
                coarse_front = self._cache.pop("_moving")[1][-1]
                dfront = abs(moving[1][-1] - coarse_front)
                notes.append(f"front position {moving[1][-1]:.6g} (SI) with {N} intervals; difference from {N // 2} intervals {dfront:.1e}")
            worst = 0.0
            for k, f in enumerate(self.fields):
                if self.cell_centered:
                    a_ = fields[-1][k]
                    fine, coarse = 0.5 * (a_[:, 0::2] + a_[:, 1::2]), fields_c[-1][k]
                else:
                    sub_ = (slice(None), slice(None, None, 2)) if self.dim == 1 else (slice(None, None, 2),) * self.dim
                    fine, coarse = fields[-1][k][sub_], fields_c[-1][k]
                    if hole_info is not None:
                        fine, coarse = np.where(hole_info[0][sub_], 0.0, fine), np.where(hole_info[0][sub_], 0.0, coarse)           # nodes inside a cutout are not part of the solution
                scale = max(float(np.max(np.abs(fine))), 1e-300)
                err[f] = float(np.mean(np.abs(fine - coarse))) if self.cell_centered else float(np.max(np.abs(fine - coarse))) / 3     # a shock: the average (L1) difference, since cells at the jump differ by O(1)
                worst = max(worst, err[f] / scale)
            notes.append(f"{N} {'cells' if self.cell_centered else 'intervals'}" + (" in each direction" if self.dim > 1 else "") + f"; estimated discretisation error {worst:.1e} relative to the largest value" + (" (average over the domain)" if self.cell_centered else "") + f", from comparison with {N // 2}")
            if worst > 1e-2:
                notes.append("the estimated error is above 1 %: increase the number of nodes")
        res = PdeResult(("Newton's method (sparse Jacobian, LU)" if self.steady else "BDF (variable order, sparse Jacobian), method of lines" + (" with the coordinate stretched to the moving boundary" if self.moving else "")) + f" on {('a line', 'a rectangle', 'a box')[self.dim - 1]}", steps, nfev, RTOL, 0.0, notes)
        out = MultiFields([float(v) for v in xs], [float(v) for v in ys] if self.dim >= 2 else None, ts, {f: [fl[k] for fl in fields] for k, f in enumerate(self.fields)}, res, err,
                          [float(v) for v in zs] if self.dim >= 3 else None, hole_info[0] if hole_info is not None else None, [tuple(b_) for b_ in hole_info[1]] if hole_info is not None else None,
                          (list(moving[0]), list(moving[1])) if moving is not None else None, list(moving[2]) if moving is not None else None)
        if len(self._cache) > 20:
            self._cache.clear()
        self._cache[("run", key)] = out
        self._cache["last"] = res
        return out

    def value(self, dependent: sp.Symbol, values: Mapping[sp.Symbol, float]) -> float:
        vals = self._values(values)
        f = self.run(values)
        span = self.span(values)
        x = vals[self.x]
        if self.y is None:
            lo, hi = (f.xs[0], f.xs[-1]) if self.moving else span                 # a moving boundary: the region at the time asked for
            if not lo - 1e-9 * (hi - lo) <= x <= hi + 1e-9 * (hi - lo):
                raise OdeError(f"{self.x.name} = {x:g} (SI) lies outside the interval {lo:g} to {hi:g}")
            return interpolate(f.xs, f.u[dependent][-1][0].tolist(), min(max(x, lo), hi))
        coords = [self.x, self.y, self.z][:self.dim]
        for sym, (a, b) in zip(coords, span):
            v = vals[sym]
            if not a - 1e-9 * (b - a) <= v <= b + 1e-9 * (b - a):
                raise OdeError(f"{sym.name} = {v:g} (SI) lies outside the interval {a:g} to {b:g}")
        grid = f.u[dependent][-1]
        if f.cuts:
            for ci, (cx0, cx1, cy0, cy1) in enumerate(f.cuts):
                if cx0 < vals[self.x] < cx1 and cy0 < vals[self.y] < cy1:
                    raise OdeError(f"the point ({self.x.name}, {self.y.name}) lies inside cutout {ci + 1}, which is not part of the region")
        return _at_point(f, grid, [min(max(vals[sym], a), b) for sym, (a, b) in zip(coords, span)])


def _fill_hole(A, hole):
    """The nodes inside a cutout get a smooth continuation of the neighbouring values (they are not part of the solution; the fill only keeps interpolation near the faces sensible)."""
    B = A.copy()
    if not hole.any():
        return B
    known = ~hole
    B[hole] = float(B[known].mean()) if known.any() else 0.0
    for _ in range(80):
        P = np.pad(B, ((0, 0), (1, 1), (1, 1)), mode="edge")
        avg = 0.25 * (P[:, :-2, 1:-1] + P[:, 2:, 1:-1] + P[:, 1:-1, :-2] + P[:, 1:-1, 2:])
        B = np.where(hole, avg, A)
    return B


def _newton(fun, y0, pattern, scale):
    """Newton's method for ``fun(y) = 0`` with the Jacobian by finite differences over column groups (the sparsity pattern) and a sparse LU; damped by halving the step."""
    from scipy.optimize._numdiff import approx_derivative, group_columns
    from scipy.sparse.linalg import splu

    groups = group_columns(pattern)
    y = np.array(y0, float)
    f = fun(y)
    norm0 = max(float(np.linalg.norm(f)), 1e-300)
    sc = max(max(scale), 1e-30)
    for it in range(1, MAX_NEWTON + 1):
        J = approx_derivative(fun, y, method="2-point", f0=f, sparsity=(pattern, groups), rel_step=1e-7)
        try:
            lu = splu(J.tocsc())
            piv = np.abs(lu.U.diagonal())
            if piv.size and float(piv.min()) <= 1e-12 * float(piv.max()):
                raise RuntimeError("singular")
            dy = lu.solve(-f)
        except RuntimeError:
            raise OdeError("the linearised equations are singular (for instance every side has a slope condition, which fixes the solution only up to a constant); "
                           "give a value condition on at least one side") from None
        if not np.all(np.isfinite(dy)):
            raise OdeError("Newton's method produced non-finite values; give a closer starting guess ('guess')")
        lam, fn = 1.0, None
        while lam > 1e-4:
            fn = fun(y + lam * dy)
            if np.all(np.isfinite(fn)) and np.linalg.norm(fn) <= (1 - 1e-4 * lam) * np.linalg.norm(f) + 1e-300:
                break
            lam /= 2
        else:
            if not np.all(np.isfinite(fn)) or np.linalg.norm(fn) > 1.5 * np.linalg.norm(f):
                raise OdeError("Newton's method did not converge (the residual would not decrease); give a closer starting guess ('guess') or check that the problem is well posed")
        y = y + lam * dy
        f = fn
        if float(np.max(np.abs(lam * dy))) <= 1e-10 * (float(np.max(np.abs(y))) + sc) or float(np.linalg.norm(f)) <= 1e-13 * norm0:
            return y, it
    raise OdeError(f"Newton's method did not converge in {MAX_NEWTON} iterations; give a closer starting guess ('guess')")


def _at_point(f: MultiFields, grid, point: list[float]) -> float:
    """Cubic interpolation of one stored field at a point (x, [y, [z]])."""
    if len(point) == 2:
        return interpolate(f.ys, [interpolate(f.xs, grid[j].tolist(), point[0]) for j in range(len(f.ys))], point[1])
    if len(point) == 3:
        planes = [interpolate(f.ys, [interpolate(f.xs, grid[k][j].tolist(), point[0]) for j in range(len(f.ys))], point[1]) for k in range(len(f.zs))]
        return interpolate(f.zs, planes, point[2])
    return interpolate(f.xs, grid[0].tolist(), point[0])


def _slice_z(f: MultiFields, grid, z: float) -> list:
    """The (ny+1, nx+1) plane of a three-dimensional field at height z (cubic Lagrange over the four nearest planes)."""
    zs = f.zs
    n = len(zs) - 1
    h = (zs[-1] - zs[0]) / n
    pos = (z - zs[0]) / h
    i = min(max(int(math.floor(pos)), 0), n - 1)
    k0 = min(max(i - 1, 0), n - 3) if n >= 3 else 0
    pts = range(k0, min(k0 + 4, n + 1))
    out = np.zeros(grid.shape[1:])
    for a in pts:
        w = 1.0
        for b in pts:
            if a != b:
                w *= (pos - b) / (a - b)
        out += w * grid[a]
    return out.tolist()


# ---------------------------------------------------------------- per-field views, so the plotting code written for single fields can be reused

class FieldView:
    """One field of a :class:`PdeMulti` presented through the interface of the single-field systems (``dependent``, ``run``, ``span``, ...)."""

    pde = True

    def __init__(self, system: PdeMulti, k: int):
        self.s, self.k = system, k
        self.dependent = system.fields[k]
        for name in ("title", "x", "y", "t", "inputs", "why_numeric", "nodes"):
            setattr(self, name, getattr(system, name))
        self.dim = 2 if system.dim == 3 else system.dim      # a plane is shown for a three-dimensional field: the one at the chosen z

    def span(self, values):
        sp_ = self.s.span(values)
        return sp_[:2] if self.s.dim == 3 else sp_

    def run(self, values, outputs=()):
        from .pde import Fields
        from .pde2d import Fields2D

        f = self.s.run(values, outputs)
        err = f.error[self.dependent]
        if self.s.y is None:
            return Fields(f.xs, f.times, [a[0].tolist() for a in f.u[self.dependent]], f.result, err)
        if self.s.z is not None:
            lo, hi = self.s.span(values)[2]
            z = min(max(float(values[self.s.z]), lo), hi)
            return Fields2D(f.xs, f.ys, _slice_z(f, f.u[self.dependent][-1], z), f.result, err)
        return Fields2D(f.xs, f.ys, f.u[self.dependent][-1].tolist(), f.result, err, f.hole.tolist() if f.hole is not None else None)

    def history(self, values, x: float, y: float | None, times, z: float | None = None) -> list[float]:
        """The field at one point for each time in ``times`` (which the run was asked to land on)."""
        f = self.s.run(values, times)
        by_t = {round(tt, 12): k for k, tt in enumerate(f.times)}
        out = []
        for tt in times:
            k = by_t.get(round(tt, 12))
            if k is None:
                k = min(range(len(f.times)), key=lambda i: abs(f.times[i] - tt))
            grid = f.u[self.dependent][k]
            out.append(_at_point(f, grid, [x] if y is None else [x, y] if z is None else [x, y, z]))
        return out


# ---------------------------------------------------------------- building

def build(spec: Mapping[str, Any], calc, ns: dict, env: dict, custom: bool, index: int):
    from .model import Equation
    from .ode import OdeSpecError, _friendly, _make_fn, _parse, _split
    from .safeparse import bound_names

    title = str(spec.get("title") or "Partial differential equations").strip()[:100]
    xn, tn = spec.get("independent"), spec.get("time")
    yn = spec.get("second") or None
    zn = spec.get("third") or None
    if zn and not yn:
        raise OdeSpecError("'third' (a third space variable) needs 'second' as well")
    steady = tn in (None, "")
    if steady and not zn and not spec.get("cutouts"):
        raise OdeSpecError("a steady problem in this form needs a third space variable or cutouts; for a plain rectangle use the 'second' space variable without 'time' (a single field)")
    names = [("independent (space)", xn)] + ([] if steady else [("time", tn)]) + ([("second space", yn)] if yn else []) + ([("third space", zn)] if zn else [])
    for what, n in names:
        if not isinstance(n, str) or n not in calc.by_key or calc.by_key[n].is_constant:
            raise OdeSpecError(f"'{what}' must name one of the variables, got {n!r}")
    if len({xn, *([] if steady else [tn]), *( [yn] if yn else []), *( [zn] if zn else [])}) != len(names):
        raise OdeSpecError("the space and time variables must differ")
    x = calc.by_key[xn].symbol
    t = sp.Symbol("t__steady", real=True) if steady else calc.by_key[tn].symbol           # a steady problem has no time: a dummy symbol keeps the shared code uniform
    y = calc.by_key[yn].symbol if yn else None
    z = calc.by_key[zn].symbol if zn else None
    two = y is not None
    three = z is not None
    dimn = 3 if three else 2 if two else 1
    if spec.get("events"):
        raise OdeSpecError("events are not supported for partial differential equations")
    texts = spec.get("equations")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not texts or not all(isinstance(q, str) and q.strip() for q in texts) or len(texts) > MAX_FIELDS:
        raise OdeSpecError(f"give 1 to {MAX_FIELDS} equations, one for each field, e.g. " + ("'diff(T, x, 2) + diff(T, y, 2) + diff(T, z, 2) = 0'" if steady else "'diff(T, t) = a*diff(T, x, 2)'"))
    if steady and (spec.get("sources") or spec.get("periodic")):
        raise OdeSpecError("steady problems take no point sources or periodic directions in this form (put a source into the equation)")
    texts = [q.strip() for q in texts]
    lo_n, hi_n = STEADY_LIMITS[dimn] if steady else LIMITS[dimn]
    nodes = spec.get("nodes", {1: DEFAULT_NODES_1D, 2: DEFAULT_NODES_2D, 3: DEFAULT_NODES_3D}[dimn])
    if not isinstance(nodes, int) or isinstance(nodes, bool) or not lo_n <= nodes <= hi_n:
        raise OdeSpecError(f"'nodes' must be a whole number from {lo_n} to {hi_n}")
    space = [s for s in (x, y, z) if s is not None]
    moving_in = spec.get("moving")
    S = None
    if moving_in:
        if steady or two or spec.get("periodic") or spec.get("sources"):
            raise OdeSpecError("a moving boundary is for time-dependent problems in one space dimension, without periodic directions or point sources")
        if not isinstance(moving_in, Mapping) or not isinstance(moving_in.get("front"), str) or not str(moving_in.get("rate", "")).strip():
            raise OdeSpecError("'moving' is an object such as {\"front\": \"s\", \"rate\": \"-k*diff(T, x)/(rho*Lf)\"}: the variable that receives the front position and its speed")
        fv = moving_in["front"]
        if fv not in calc.by_key or calc.by_key[fv].is_constant or calc.by_key[fv].symbol in (x, t):
            raise OdeSpecError(f"moving.front must name a free variable of this calculation that receives the position of the moving end, got {fv!r}")
        S = calc.by_key[fv].symbol

    # the fields: quantities differentiated with respect to time
    field_names: list[str] = []
    for text in texts:
        for side in _split(text):
            try:
                tree = ast.parse(side.strip().replace("^", "**"), mode="eval")
            except SyntaxError:
                raise OdeSpecError(f"cannot read the equation {text!r}") from None
            for n in ast.walk(tree):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "diff" and len(n.args) >= 2 and isinstance(n.args[0], ast.Name)
                        and isinstance(n.args[1], ast.Name) and (n.args[1].id in (xn, yn, zn) if steady else n.args[1].id == tn) and n.args[0].id in calc.by_key and n.args[0].id not in field_names):
                    field_names.append(n.args[0].id)
    if steady:
        for text in texts:
            for side in _split(text):
                for n in ast.walk(ast.parse(side.strip().replace("^", "**"), mode="eval")):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "diff" and len(n.args) >= 2 and isinstance(n.args[1], ast.Name) and n.args[1].id not in (xn, yn, zn):
                        raise OdeSpecError(f"{text!r}: a steady problem has no time derivative; differentiate only with respect to {', '.join(q for q in (xn, yn, zn) if q)} (not {n.args[1].id})")
    if steady and len(field_names) != len(texts):
        raise OdeSpecError(f"{len(texts)} equation(s) but {len(field_names)} quantit{'y' if len(field_names) == 1 else 'ies'} differentiated in space ({', '.join(field_names) or 'none'}): give one equation per field")
    if len(field_names) != len(texts):
        raise OdeSpecError(f"{len(texts)} equation(s) but {len(field_names)} quantit{'y' if len(field_names) == 1 else 'ies'} differentiated with respect to {tn} "
                           f"({', '.join(field_names) or 'none'}): give one equation per field")
    fields = []
    for n in field_names:
        v = calc.by_key[n]
        if v.is_constant or v.symbol in (x, t, y, z):
            raise OdeSpecError(f"{n!r} is differentiated but is not a (non-constant) field variable")
        fields.append(v.symbol)
    nf = len(fields)
    fn = {n: sp.Function(n)(*space) if steady else sp.Function(n)(*space, t) for n in field_names}
    local = {**ns, **fn}

    # internal symbols for the field and its space derivatives
    def sym_set(n):
        d = {"U": sp.Symbol(f"{n}__0", real=True), "UX": sp.Symbol(f"{n}__x", real=True), "UXX": sp.Symbol(f"{n}__xx", real=True)}
        if two:
            d.update({"UY": sp.Symbol(f"{n}__y", real=True), "UYY": sp.Symbol(f"{n}__yy", real=True)})
            if not three:
                d["UXY"] = sp.Symbol(f"{n}__xy", real=True)
        if three:
            d.update({"UZ": sp.Symbol(f"{n}__z", real=True), "UZZ": sp.Symbol(f"{n}__zz", real=True)})
        return d
    syms = [sym_set(n) for n in field_names]
    UT = [sp.Symbol(f"{n}__t", real=True) for n in field_names]
    code = {(1, 0, 0, 0): "UX", (2, 0, 0, 0): "UXX", (0, 1, 0, 0): "UY", (0, 2, 0, 0): "UYY", (1, 1, 0, 0): "UXY", (0, 0, 1, 0): "UZ", (0, 0, 2, 0): "UZZ"}

    def to_internal(expr, what: str, allow_time: bool = False):
        rep = {}
        for d in expr.atoms(sp.Derivative):
            if not isinstance(d.expr, AppliedUndef) or d.expr.func.__name__ not in field_names:
                raise OdeSpecError(f"{d}: differentiate a field directly (e.g. diff({field_names[0]}, {xn}, 2))")
            k = field_names.index(d.expr.func.__name__)
            counts = dict(d.variable_count)
            if set(counts) - {x, t, *( [y] if two else []), *( [z] if three else [])}:
                raise OdeSpecError(f"{d}: the derivative must be with respect to {', '.join(s.name for s in (*space, t))}")
            key = (counts.get(x, 0), counts.get(y, 0) if two else 0, counts.get(z, 0) if three else 0, counts.get(t, 0))
            if key == (0, 0, 0, 1):
                if not allow_time:
                    raise OdeSpecError(f"{what}: " + ("a steady problem has no time derivative" if steady else "time derivatives appear only on the left of the equations"))
                rep[d] = UT[k]
            elif key in code and (code[key] in syms[k]):
                rep[d] = syms[k][code[key]]
            else:
                raise OdeSpecError(f"{d}: only first and second derivatives in space{' (and the mixed one in two dimensions)' if two and not three else ''} and the first in time are supported")
        e = expr.xreplace(rep)
        return e.xreplace({fn[n]: syms[k]["U"] for k, n in enumerate(field_names)})

    resids = []
    written = []
    for text in texts:
        lt, rt = _split(text)
        loc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(text) if n not in local}}
        lhs, rhs_ = _parse(lt, loc, custom, ns), _parse(rt, loc, custom, ns)
        written.append((lhs, rhs_))
        r = to_internal((lhs - rhs_).doit(), f"equation {text!r}", allow_time=not steady)
        if r.atoms(AppliedUndef) or r.atoms(sp.Derivative) or r.has(sp.Integral):
            raise OdeSpecError(f"the equation {text!r} uses a field in a way that cannot be handled (only the quantities and their space derivatives)")
        resids.append(r)
    if steady:
        F = list(resids)                                        # the residuals themselves: Newton's method needs no particular form
        if any(r.has(sp.Symbol(f"{n}__t", real=True)) for r in F for n in field_names):
            raise OdeSpecError("a steady problem has no time derivative")
    else:
        try:
            sols = sp.solve(resids, UT, dict=True)
        except Exception as exc:  # noqa: BLE001
            raise OdeSpecError(f"cannot solve the equations for the time derivatives: {exc}") from None
        if len(sols) != 1 or any(u not in sols[0] for u in UT) or any(sols[0][u].has(*UT) for u in UT):
            raise OdeSpecError("each equation must be solvable for the time derivative of its field (first order in time), and the system must determine them uniquely")
        F = [sols[0][u] for u in UT]
    if not any(r.has(s) for r in F for d in syms for k_, s in d.items() if k_ != "U"):
        raise OdeSpecError("the equations contain no space derivative: for a system of ordinary differential equations use a plain differential-equation entry")

    front_rate = None
    if S is not None:
        if any(S == f for f in fields):
            raise OdeSpecError("the front variable cannot also be a field")
        rtext = str(moving_in["rate"]).strip()
        rloc = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(rtext) if n not in local}}
        front_rate = to_internal(_parse(rtext, rloc, custom, ns).doit(), "the speed of the moving boundary").xreplace({x: S})
        if front_rate.atoms(AppliedUndef) or front_rate.atoms(sp.Derivative):
            raise OdeSpecError("the speed of the moving boundary may use the fields and their slopes at the front (diff(T, x) is the slope there), the position x or the front variable, time and parameters")

    # periodic directions
    periodic = spec.get("periodic") or []
    if isinstance(periodic, str):
        periodic = [q.strip() for q in periodic.replace(",", " ").split() if q.strip()]
    if not isinstance(periodic, list) or any(q not in [s.name for s in space] for q in periodic):
        raise OdeSpecError(f"'periodic' lists space variables ({', '.join(s.name for s in space)}) along which every field repeats")
    sides = SIDES_3D if three else SIDES_2D if two else SIDES_1D
    per_sides = set()
    for q in periodic:
        per_sides |= ({"start", "end", "left", "right"} if q == xn else {"bottom", "top"} if q == yn else {"front", "back"}) & set(sides)

    # boundary conditions: 'side: condition' for one field each
    boundary = spec.get("boundary") or []
    if isinstance(boundary, str):
        boundary = [q.strip() for q in boundary.split("\n") if q.strip()]
    if not isinstance(boundary, list) or not all(isinstance(b, str) for b in boundary):
        raise OdeSpecError("'boundary' is a list of conditions such as 'start: T = Ts' or 'left: diff(u, x) = 0'")
    need = (len(sides) - len(per_sides)) * nf
    if len(boundary) != need:
        raise OdeSpecError(f"{need} boundary condition{'s' if need != 1 else ''} needed (one for each field on each non-periodic side: {', '.join(s for s in sides if s not in per_sides) or 'none'}), but {len(boundary)} given")
    def parse_condition(side, cond, btxt):
        """One boundary condition 'side: condition' -> (field index, kind, expression for the value or slope, (left, right) as written)."""
        cl, cr = _split(cond)
        loc2 = {**local, **{n: sp.Symbol(n, real=True) for n in bound_names(cond) if n not in local}}
        a, b = _parse(cl, loc2, custom, ns), _parse(cr, loc2, custom, ns)
        res = (a - b).doit()
        used = {f.func.__name__ for f in res.atoms(AppliedUndef)} & set(field_names)
        if not used:
            raise OdeSpecError(f"the condition {btxt!r} must involve a field")
        deriv_fields = {d.expr.func.__name__ for d in res.atoms(sp.Derivative) if isinstance(d.expr, AppliedUndef)}
        if len(deriv_fields) > 1:
            raise OdeSpecError(f"the condition {btxt!r} contains the slope of more than one field ({', '.join(sorted(deriv_fields))}); only one slope can be determined by one condition")
        if len(used) == 1:
            owner = next(iter(used))
        elif deriv_fields:
            owner = next(iter(deriv_fields))                        # the field whose slope appears is the one constrained; the others enter through their values at the boundary
        else:
            left_fields = {f.func.__name__ for f in a.atoms(AppliedUndef)} & set(field_names)
            if len(left_fields) != 1:
                raise OdeSpecError(f"the condition {btxt!r} involves {', '.join(sorted(used))}: write the field it determines alone on the left side (e.g. 'left: b = 2*a'), or include the slope of that field")
            owner = next(iter(left_fields))
        k = field_names.index(owner)
        if two:
            normal = {"left": x, "right": x, "bottom": y, "top": y, "front": z, "back": z}[side]
            along = ", ".join(s.name for s in space if s is not normal)
            nsym = syms[k][{"left": "UX", "right": "UX", "bottom": "UY", "top": "UY", "front": "UZ", "back": "UZ"}[side]]
        else:
            normal, along, nsym = x, None, syms[k]["UX"]
        rep2 = {}
        for d in res.atoms(sp.Derivative):
            counts = dict(d.variable_count)
            if not isinstance(d.expr, AppliedUndef) or counts != {normal: 1}:
                raise OdeSpecError(f"the {side} condition may contain {field_names[k]} and its first derivative across the side, diff({field_names[k]}, {normal.name}); got {d}")
            rep2[d] = nsym
        res = res.xreplace(rep2).xreplace({fn[n]: syms[kk]["U"] for kk, n in enumerate(field_names)})
        if res.atoms(AppliedUndef) or res.atoms(sp.Derivative) or normal in res.free_symbols:
            raise OdeSpecError(f"the {side} condition cannot involve {normal.name} (it is fixed on that side)" + (f"; it may involve {along}" if along else ""))
        try:
            kind, sol = ("slope", sp.solve(res, nsym)) if res.has(nsym) else ("value", sp.solve(res, syms[k]["U"]))
        except Exception as exc:  # noqa: BLE001
            raise OdeSpecError(f"cannot use the {side} condition {btxt!r}: {exc}") from None
        if len(sol) != 1 or sol[0].has(nsym) or (kind == "value" and sol[0].has(syms[k]["U"])):
            raise OdeSpecError(f"the {side} condition {btxt!r} must determine the {'slope' if kind == 'slope' else 'value'} uniquely")
        return k, kind, sol[0], (a, b)

    bcs: dict = {}
    condition_texts: list = []
    pat = r"^\s*(" + "|".join(sides) + r")\s*:\s*(.+)$"
    for btxt in boundary:
        m = re.match(pat, btxt)
        if not m:
            raise OdeSpecError(f"boundary conditions are written '{'/'.join(sides)}: condition'; got {btxt!r}")
        side, cond = m.groups()
        if side in per_sides:
            raise OdeSpecError(f"the {side} side is periodic: it takes no boundary condition")
        k, kind, expr0, (a, b) = parse_condition(side, cond, btxt)
        if (k, side) in bcs:
            raise OdeSpecError(f"{field_names[k]} has two conditions on the {side} side")
        bcs[(k, side)] = (kind, expr0, (a, b))
        condition_texts.append((a, b, f"{field_names[k]} at {side}"))
    # cutouts: rectangles removed from the region, each with conditions on its exposed sides
    cutouts: list = []
    cut_in = spec.get("cutouts") or []
    if cut_in:
        if not two or three or moving_in or periodic:
            raise OdeSpecError("cutouts are for two-dimensional regions (a second space variable) without a third variable, periodic direction or moving boundary")
        if not isinstance(cut_in, list) or len(cut_in) > 3 or not all(isinstance(c_, Mapping) for c_ in cut_in):
            raise OdeSpecError("'cutouts' is a list of at most 3 objects such as {\"x0\": \"a/2\", \"x1\": \"a\", \"y0\": \"b/2\", \"y1\": \"b\", \"boundary\": [\"left: T = Ts\", \"bottom: diff(T, y) = 0\"]}")
    for ci, c_ in enumerate(cut_in):
        try:
            box = tuple(_parse(str(c_[key]), ns, custom, ns) for key in ("x0", "x1", "y0", "y1"))
        except KeyError:
            raise OdeSpecError(f"cutout {ci + 1} needs x0, x1, y0 and y1 (the rectangle that is removed, in the same variables as the region)") from None
        if any(e_.free_symbols & {x, y, t} for e_ in box):
            raise OdeSpecError(f"cutout {ci + 1}: its corners cannot depend on the space or time variables")
        lines_c = c_.get("boundary") or []
        if isinstance(lines_c, str):
            lines_c = [q.strip() for q in lines_c.split("\n") if q.strip()]
        if not isinstance(lines_c, list) or not all(isinstance(b_, str) for b_ in lines_c):
            raise OdeSpecError(f"cutout {ci + 1}: 'boundary' is a list of conditions such as 'left: T = Ts' (the sides of the removed rectangle)")
        cbcs: dict = {}
        for btxt in lines_c:
            m = re.match(r"^\s*(left|right|bottom|top)\s*:\s*(.+)$", btxt)
            if not m:
                raise OdeSpecError(f"cutout {ci + 1}: conditions are written 'left/right/bottom/top: condition'; got {btxt!r}")
            side, cond = m.groups()
            k, kind, expr0, (a, b) = parse_condition(side, cond, btxt)
            if (k, side) in cbcs:
                raise OdeSpecError(f"cutout {ci + 1}: {field_names[k]} has two conditions on the {side} side")
            if kind == "value" and any(expr0.has(syms[kk]["U"]) for kk in range(nf) if kk != k):
                raise OdeSpecError(f"cutout {ci + 1}: a value condition on a cutout cannot read another field (use a slope condition for that)")
            cbcs[(k, side)] = (kind, expr0, (a, b))
            condition_texts.append((a, b, f"{field_names[k]} at the {side} side of cutout {ci + 1}"))
        cutouts.append({"box": box, "bcs": cbcs})
    if cutouts and any(r.has(sd["UXY"]) for r in F for sd in syms if "UXY" in sd):
        raise OdeSpecError("a mixed derivative cannot be combined with cutouts")
    coupled_value = {(k, sd): {kk for kk in range(nf) if kk != k and e.has(syms[kk]["U"])} for (k, sd), (kd, e, _w) in bcs.items() if kd == "value"}
    for (k, sd), refs in coupled_value.items():
        for kk in refs:
            if coupled_value.get((kk, sd)):
                raise OdeSpecError(f"the {sd} conditions of {field_names[k]} and {field_names[kk]} both read the other's value there (circular): make one of them a slope condition or a value that does not read the other field")
    if two and not three and any(r.has(s["UXY"]) for r in F for s in syms) and any(kind == "slope" for kind, _e, _w in bcs.values()):
        raise OdeSpecError("a mixed derivative needs value or periodic conditions on every side (slope conditions need a corner treatment that is not available)")
    if not per_sides and all(kind == "slope" for kind, _e, _w in bcs.values()) and False:
        pass

    # initial state
    initial = spec.get("guess" if steady else "initial") or []
    if isinstance(initial, str):
        initial = [q.strip() for q in initial.split("\n") if q.strip()]
    if not isinstance(initial, list) or not all(isinstance(q, str) for q in initial):
        raise OdeSpecError("'guess' is a list such as 'T = Ti' (a starting guess for Newton's method; it may depend on the space variables)" if steady else
                           "'initial' is a list such as 'T = Ti', one for each field (it may depend on the space variables)")
    u0: list = [None] * nf
    for itxt in initial:
        il, ir = _split(itxt)
        il = il.strip()
        if il not in field_names:
            raise OdeSpecError(f"an initial condition's left side must be one of {', '.join(field_names)}; got {il!r}")
        k = field_names.index(il)
        if u0[k] is not None:
            raise OdeSpecError(f"initial value of {il} given twice")
        u0[k] = _parse(ir, {**ns}, custom, ns)
    if steady:
        u0 = [sp.Integer(0) if q is None else q for q in u0]            # the default starting guess is zero (fine for linear problems)
    miss = [field_names[k] for k in range(nf) if u0[k] is None]
    if miss:
        raise OdeSpecError(f"missing initial value for {', '.join(miss)}: add '{miss[0]} = …' (it may depend on {', '.join(s.name for s in space)})")

    def interval(k0, k1, what):
        a_ = _parse(str(spec.get(k0, "0")), ns, custom, ns) if str(spec.get(k0, "0")).strip() else sp.Integer(0)
        b_ = _parse(str(spec.get(k1) or ""), ns, custom, ns) if str(spec.get(k1) or "").strip() else None
        if b_ is None:
            raise OdeSpecError(f"a time-dependent partial differential equation needs '{k1}' (where the {what} interval ends)")
        return a_, b_
    start, end = interval("start", "end", "first")
    y0e, y1e = interval("second_start", "second_end", "second") if two else (None, None)
    z0e, z1e = interval("third_start", "third_end", "third") if three else (None, None)
    if any(s in e.free_symbols for e in (start, end, y0e, y1e, z0e, z1e) if e is not None for s in (x, t, *( [y] if two else []), *( [z] if three else []))):
        raise OdeSpecError("the ends of the intervals cannot depend on the space or time variables")

    # concentrated sources
    srcs_in = spec.get("sources") or []
    if not isinstance(srcs_in, list) or len(srcs_in) > 6 or not all(isinstance(q, Mapping) for q in srcs_in):
        raise OdeSpecError("'sources' is a list of at most 6 objects like {\"field\": \"T\", \"at\": \"x0\", \"rate\": \"q\"} (and \"at_second\", \"at_third\" in more dimensions)")
    sources: list = []
    for q in srcs_in:
        fname = q.get("field")
        if fname not in field_names:
            raise OdeSpecError(f"a source's 'field' must be one of {', '.join(field_names)}")
        pos = _parse(str(q.get("at", "")), ns, custom, ns) if str(q.get("at", "")).strip() else None
        ypos = _parse(str(q.get("at_second", "")), ns, custom, ns) if str(q.get("at_second", "")).strip() else None
        zpos = _parse(str(q.get("at_third", "")), ns, custom, ns) if str(q.get("at_third", "")).strip() else None
        rate = _parse(str(q.get("rate", "")), ns, custom, ns) if str(q.get("rate", "")).strip() else None
        if pos is None or rate is None or (two and ypos is None) or (not two and ypos is not None) or (three and zpos is None) or (not three and zpos is not None):
            raise OdeSpecError("each source needs 'at' (position)" + (", 'at_second'" if two else "") + (", 'at_third'" if three else "") + " and 'rate'")
        sources.append((field_names.index(fname), [pos, *([ypos] if two else []), *([zpos] if three else [])], rate))

    internal = {s for d in syms for s in d.values()}
    exprs = [*F, *u0, start, end, *( [y0e, y1e] if two else []), *[e for _k, e, _w in bcs.values()], z0e, z1e, *[e for _k, ps, r in sources for e in (*ps, r)]]
    exprs = [e for e in exprs if e is not None] + ([front_rate] if front_rate is not None else []) + [e for c_ in cutouts for e in (*c_["box"], *[v[1] for v in c_["bcs"].values()])]
    declared = {v.symbol for v in calc.variables}
    params = sorted({s for e in exprs for s in e.free_symbols if s not in internal and s not in (x, t, *( [y] if two else []), *( [z] if three else []), *([S] if S is not None else []))}, key=lambda s: s.name)
    for s in params:
        if s not in declared:
            raise OdeSpecError(f"{s} is not a variable of this calculation")
    if t in {s for e in u0 for s in e.free_symbols}:
        raise OdeSpecError("the initial state cannot depend on time")
    if steady and any(e.free_symbols & {sp.Symbol(f"{n}__t", real=True) for n in field_names} for e in F):
        raise OdeSpecError("a steady problem has no time derivative")

    # dimensions
    dim_t, unit_t = (DIMENSIONLESS, None) if steady else env[t]
    dim_x, unit_x = env[x]
    if S is not None and (S in end.free_symbols or env[S][0] != dim_x):
        raise OdeSpecError(f"the front variable {S.name} must have the dimension of {x.name} and must not appear in the initial end position 'end'")
    dim_y, unit_y = env[y] if two else (None, None)
    dim_z, unit_z = env[z] if three else (None, None)
    genv = dict(env)
    for k, f in enumerate(fields):
        du, uu = env[f]
        genv[syms[k]["U"]] = (du, uu)
        genv[syms[k]["UX"]] = (du / dim_x, uu / unit_x)
        genv[syms[k]["UXX"]] = (du / dim_x ** 2, uu / unit_x ** 2)
        if two:
            genv[syms[k]["UY"]] = (du / dim_y, uu / unit_y)
            genv[syms[k]["UYY"]] = (du / dim_y ** 2, uu / unit_y ** 2)
            if not three:
                genv[syms[k]["UXY"]] = (du / (dim_x * dim_y), uu / (unit_x * unit_y))
        if three:
            genv[syms[k]["UZ"]] = (du / dim_z, uu / unit_z)
            genv[syms[k]["UZZ"]] = (du / dim_z ** 2, uu / unit_z ** 2)
    try:
        for k, f in enumerate(fields):
            dr, _ = analyze(F[k], genv)                         # for a steady problem this checks that the terms of the equation agree with each other
            want = env[f][0] / dim_t
            if not steady and dr != want:
                raise DimensionError(f"the equation for {field_names[k]} gives its time derivative the dimension [{dr}], expected [{want}]")
            if u0[k] != 0:
                di, _ = analyze(u0[k], genv)
                if di != env[f][0]:
                    raise DimensionError(f"the initial value of {field_names[k]} has dimension [{di}], expected [{env[f][0]}]")
        if front_rate is not None:
            dr, _ = analyze(front_rate, genv)
            if front_rate != 0 and dr != dim_x / dim_t:
                raise DimensionError(f"the speed of the moving boundary has dimension [{dr}], expected [{dim_x / dim_t}]")
        for e, d_, what in ((start, dim_x, "first start"), (end, dim_x, "first end"), (y0e, dim_y, "second start"), (y1e, dim_y, "second end"), (z0e, dim_z, "third start"), (z1e, dim_z, "third end")):
            if e is not None and e != 0:
                de, _ = analyze(e, genv)
                if de != d_:
                    raise DimensionError(f"the {what} of the interval has dimension [{de}], expected [{d_}]")
        for (k, side), (kind, expr, _w) in bcs.items():
            if expr == 0:
                continue
            ndim = dim_z if side in ("front", "back") else dim_y if side in ("bottom", "top") else dim_x
            db, _ = analyze(expr, genv)
            want = env[fields[k]][0] if kind == "value" else env[fields[k]][0] / ndim
            if db != want:
                raise DimensionError(f"the {side} condition for {field_names[k]} gives the {'value' if kind == 'value' else 'slope'} the dimension [{db}], expected [{want}]")
        for ci, c_ in enumerate(cutouts):
            for e_, d_ in zip(c_["box"], (dim_x, dim_x, dim_y, dim_y)):
                if e_ != 0 and analyze(e_, genv)[0] != d_:
                    raise DimensionError(f"cutout {ci + 1}: a corner has dimension [{analyze(e_, genv)[0]}], expected [{d_}]")
            for (k, side), (kind, expr, _w) in c_["bcs"].items():
                if expr == 0:
                    continue
                ndim = dim_y if side in ("bottom", "top") else dim_x
                db, _ = analyze(expr, genv)
                want = env[fields[k]][0] if kind == "value" else env[fields[k]][0] / ndim
                if db != want:
                    raise DimensionError(f"cutout {ci + 1}: the {side} condition for {field_names[k]} gives the {'value' if kind == 'value' else 'slope'} the dimension [{db}], expected [{want}]")
        for k, ps, rate in sources:
            for p_, dm_ in zip(ps, (dim_x, dim_y, dim_z)):
                if p_ != 0:
                    dp, _ = analyze(p_, genv)
                    if dp != dm_:
                        raise DimensionError(f"a source position has dimension [{dp}], expected [{dm_}]")
            dr, _ = analyze(rate, genv)
            want = env[fields[k]][0] / dim_t * dim_x * (dim_y if two else DIMENSIONLESS) * (dim_z if three else DIMENSIONLESS)
            if dr != want:
                raise DimensionError(f"a source rate has dimension [{dr}], expected [{want}] (the field's rate of change times the {'volume' if three else 'area' if two else 'length'} it is spread over)")
    except DimensionError as exc:
        raise OdeSpecError(f"{title}: {_friendly(str(exc))}") from None

    inputs = sorted({x, *([] if steady else [t]), *( [y] if two else []), *( [z] if three else []), *params, *[s for e in (start, end, y0e, y1e, z0e, z1e) if e is not None for s in e.free_symbols],
                     *[s for c_ in cutouts for e in c_["box"] for s in e.free_symbols]}, key=lambda s: s.name)
    cond_shown = condition_texts if steady else condition_texts + [(sp.Function(n)(*space, 0), u0[k], "initial") for k, n in enumerate(field_names)]
    system = PdeMulti(title, texts, x, y, t, start, end, y0e, y1e, fields, syms, F, bcs, list(periodic), u0, sources, nodes, written, cond_shown, params, inputs, z=z, z0=z0e, z1=z1e, steady=steady, cutouts=cutouts, moving=(S, front_rate) if S is not None else None)
    for k, f in enumerate(fields):
        dim, unit = env[f]
        node = _make_fn(system, f, (dim, unit), calc.by_key[field_names[k]].latex or field_names[k], index * 10 + k)
        system.fns[f] = node
    eqs = []
    for k, f in enumerate(fields):
        node = system.fns[f]
        eq = Equation(f"{title}: {field_names[k]}" if nf > 1 else title, f"{field_names[k]} = numerical solution of {'; '.join(texts)}", f, node(*system.inputs),
                      frozenset({f, *system.inputs}), None)
        eq.ode = system
        eqs.append(eq)
    if S is not None:
        node = _make_fn(system, S, env[S], calc.by_key[S.name].latex or S.name, index * 10 + nf, evaluate=lambda vals: system.front_value(vals))
        system.fns[S] = node
        eq = Equation(f"{title}: {S.name} (moving boundary)", f"{S.name} = position of the moving boundary from {'; '.join(texts)}", S, node(*system.inputs), frozenset({S, *system.inputs}), None)
        eq.ode = system
        eqs.append(eq)
    return system, eqs
