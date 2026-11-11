"""Special functions for equations: Bessel (J, Y, I, K), Airy, Legendre, elliptic integrals, exponential integrals, sinc, the Lambert W function, and the zeros and
eigenvalues that appear in textbook series solutions.

SymPy defines the functions symbolically (derivatives, exact values, arbitrary-precision evaluation); this module adds

* ``NAMESPACE``: SciPy implementations for the fast ``lambdify`` paths (ODE right-hand sides, PDE grids, Newton iterations), and :func:`fast_lambdify` to use them;
* ``besselj_zero(n, k)``: the k-th positive zero of the Bessel function J_n (the natural frequencies of a drum, the roots of a cylinder's transient series);
* ``eig_slab(Bi, k)``, ``eig_cylinder(Bi, k)``, ``eig_sphere(Bi, k)``: the k-th positive root of the transient-conduction eigencondition for a plane wall
  (ζ tan ζ = Bi), a long cylinder (ζ J1(ζ) = Bi J0(ζ)) and a sphere (1 − ζ cot ζ = Bi), with Bi the Biot number.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import sympy as sp
from scipy import optimize, special as ss


@lru_cache(maxsize=4096)
def _jzero(n: int, k: int) -> float:
    if n < 0 or k < 1 or k > 200:
        raise ValueError("besselj_zero(n, k) needs a whole order n >= 0 and a zero number 1 <= k <= 200")
    return float(ss.jn_zeros(n, k)[-1])


def _brent(f, a: float, b: float) -> float:
    return float(optimize.brentq(f, a, b, xtol=1e-14, rtol=4e-15, maxiter=200))


@lru_cache(maxsize=8192)
def _eig(kind: str, bi: float, k: int) -> float:
    if k < 1 or k > 200 or not bi > 0 or not math.isfinite(bi):
        raise ValueError("the Biot number must be positive and the root number between 1 and 200")
    eps = 1e-12
    if kind == "slab":                                     # ζ tan ζ = Bi: one root in each ((k-1)π, (k-1)π + π/2)
        a, b = (k - 1) * math.pi + eps, (k - 1) * math.pi + math.pi / 2 - eps
        return _brent(lambda z: z * math.tan(z) - bi, a, b)
    if kind == "cylinder":                                 # ζ J1/J0 = Bi: one root between the (k-1)-th zero of J1 and the k-th zero of J0
        a = (float(ss.jn_zeros(1, k - 1)[-1]) if k > 1 else 0.0) + eps
        b = float(ss.jn_zeros(0, k)[-1]) - eps
        return _brent(lambda z: z * ss.j1(z) - bi * ss.j0(z), a, b)
    if kind == "sphere":                                   # 1 - ζ cot ζ = Bi: one root in ((k-1)π, kπ)
        a, b = (k - 1) * math.pi + eps, k * math.pi - eps
        return _brent(lambda z: 1 - z / math.tan(z) - bi, a, b)
    raise ValueError(kind)


def _integer(x: Any) -> int:
    v = float(x)
    if abs(v - round(v)) > 1e-9:
        raise ValueError("this argument must be a whole number")
    return int(round(v))


def _make(name: str, fn, latex_head: str):
    def _eval_evalf(self, prec):
        if not all(getattr(a, "is_number", False) for a in self.args):
            return None
        try:
            return sp.Float(fn(*[float(a) for a in self.args]), max(prec_to_dps(prec), 15))
        except (ValueError, OverflowError, ZeroDivisionError) as exc:
            raise ArithmeticError(str(exc)) from None

    def _latex(self, printer, *a, **kw):
        return rf"{latex_head}\left({', '.join(printer._print(x) for x in self.args)}\right)"
    return type(name, (sp.Function,), {"nargs": 2, "_eval_evalf": _eval_evalf, "_latex": _latex, "_eval_is_real": lambda self: True})


try:
    from mpmath.libmp import prec_to_dps
except ImportError:  # pragma: no cover
    def prec_to_dps(p):
        return max(int(p / 3.3219), 15)


besselj_zero = _make("besselj_zero", lambda n, k: _jzero(_integer(n), _integer(k)), r"j")
eig_slab = _make("eig_slab", lambda bi, k: _eig("slab", float(bi), _integer(k)), r"\zeta_{\mathrm{slab}}")
eig_cylinder = _make("eig_cylinder", lambda bi, k: _eig("cylinder", float(bi), _integer(k)), r"\zeta_{\mathrm{cyl}}")
eig_sphere = _make("eig_sphere", lambda bi, k: _eig("sphere", float(bi), _integer(k)), r"\zeta_{\mathrm{sph}}")

#: functions an equation may use (name -> SymPy object)
FUNCTIONS: dict[str, Any] = {
    "besselj": sp.besselj, "bessely": sp.bessely, "besseli": sp.besseli, "besselk": sp.besselk,
    "airyai": sp.airyai, "airybi": sp.airybi, "legendre": sp.legendre,
    "elliptic_k": sp.elliptic_k, "elliptic_e": sp.elliptic_e, "elliptic_f": sp.elliptic_f,
    "expint": sp.expint, "Ei": sp.Ei, "erfc": sp.erfc, "erfi": sp.erfi, "LambertW": sp.LambertW, "loggamma": sp.loggamma, "sinc": sp.sinc,
    "besselj_zero": besselj_zero, "eig_slab": eig_slab, "eig_cylinder": eig_cylinder, "eig_sphere": eig_sphere,
}

NAMESPACE: dict[str, Any] = {
    "besselj": ss.jv, "bessely": ss.yv, "besseli": ss.iv, "besselk": ss.kv,
    "airyai": lambda z: ss.airy(z)[0], "airybi": lambda z: ss.airy(z)[2],
    "legendre": lambda n, x: ss.eval_legendre(int(n), x),
    "elliptic_k": ss.ellipk, "elliptic_e": ss.ellipe, "elliptic_f": lambda z, m: ss.ellipkinc(z, m),
    "expint": ss.expn, "Ei": ss.expi, "erfc": math.erfc, "erfi": ss.erfi,
    "LambertW": lambda z: float(ss.lambertw(z).real), "loggamma": ss.gammaln, "sinc": lambda z: math.sin(z) / z if z else 1.0,
    "besselj_zero": lambda n, k: _jzero(_integer(n), _integer(k)),
    "eig_slab": lambda bi, k: _eig("slab", float(bi), _integer(k)),
    "eig_cylinder": lambda bi, k: _eig("cylinder", float(bi), _integer(k)),
    "eig_sphere": lambda bi, k: _eig("sphere", float(bi), _integer(k)),
}


def fast_lambdify(args, expr, runtime_functions: bool = False):
    """``lambdify`` into plain Python floats (``math``) plus the SciPy special functions above.

    With ``runtime_functions`` the SymPy Function classes made at run time (the numerically integrated solution of a differential equation) get a plain
    callable each, evaluated through their own ``_eval_evalf``; without it such a function would be a NameError in the generated code."""
    from .tables import REGISTRY

    extra: dict = {}
    if runtime_functions:
        for fn in (expr.atoms(sp.Function) if hasattr(expr, "atoms") else set()):
            cls = type(fn)
            if "_sliderule_ode" in cls.__dict__ and cls.__name__ not in extra:
                extra[cls.__name__] = lambda *a, _c=cls: float(_c(*[sp.Float(v, 17) for v in a])._eval_evalf(64))
    return sp.lambdify(args, expr, modules=[extra, NAMESPACE, REGISTRY, "math"])


def script_support() -> str:
    """Python source that defines ``besselj_zero`` and the ``eig_*`` helpers for a standalone exported script (the rest of SymPy's functions need no help)."""
    import inspect

    parts = ["import math", "from typing import Any", "from functools import lru_cache", "from mpmath.libmp import prec_to_dps", "from scipy import optimize, special as ss", ""]
    for fn in (_jzero, _brent, _eig, _integer, _make):
        parts.append(inspect.getsource(fn))
    parts += ['besselj_zero = _make("besselj_zero", lambda n, k: _jzero(_integer(n), _integer(k)), r"j")',
              'eig_slab = _make("eig_slab", lambda bi, k: _eig("slab", float(bi), _integer(k)), r"\\zeta_{\\mathrm{slab}}")',
              'eig_cylinder = _make("eig_cylinder", lambda bi, k: _eig("cylinder", float(bi), _integer(k)), r"\\zeta_{\\mathrm{cyl}}")',
              'eig_sphere = _make("eig_sphere", lambda bi, k: _eig("sphere", float(bi), _integer(k)), r"\\zeta_{\\mathrm{sph}}")',
              "NS.update(besselj_zero=besselj_zero, eig_slab=eig_slab, eig_cylinder=eig_cylinder, eig_sphere=eig_sphere)"]
    return "\n".join(parts)
