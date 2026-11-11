"""Worked steps for LiveCalc lines that call something that does its own work.

``calc("id", "out", ...)`` solves a library calculation; ``integrate``, ``derivative``, ``findroot`` and ``sumover`` run a numerical method over a
function you defined; and a call ``f(4)`` of your own function is an expression in itself. Showing any of them as ``calc(...)`` or ``f(4)`` followed by
a result is not a worked solution, so this module opens them up:

* a library call shows the calculation's own formulas, the inputs converted to SI, each formula with the numbers put in, the unit reduction and the
  result (the same working the Calculations tab gives), then the line's own arithmetic with that result substituted in;
* a calculus function shows the function, the method with the numbers it used (the stencil and its values, the bracket, the terms) and, when the
  function is a plain formula in one unitless variable, the exact antiderivative or derivative evaluated by hand, checked against the numeric result
  before it is shown;
* your own function shows its definition, the arguments and then its body with the values in.

``worked_steps`` returns ``None`` when it has nothing better than the plain steps (lists, matrices, nested cases it does not take apart), and
never raises: a result must not be lost because its explanation could not be built.
"""

from __future__ import annotations

import numpy as np
import sympy as sp

from . import livecalc as L
from . import livecalc_funcs as funcs

_SKIP_LIBRARY = ("Convert the result to the requested unit", "Result")
_GIVEN = "Given values and unit standardization (convert to SI)"
_CLOSED = "Closed-form solution in terms of the given quantities"
MAX_STEPS_PER_CALL = 14
MAX_LINES = 10


class _NoWork(Exception):
    pass


def worked_steps(node: tuple, sc: L.Scope, q: L.Q, sig: int, conversion: list[dict] | None) -> list[dict] | None:
    scalar = not (np.ndim(q.v) or L._is_complex(q))
    try:
        if L._is_complex(q) and not np.ndim(q.v):
            return _complex_steps(node, sc, q, sig, conversion)
        if scalar:
            if node[0] == "call" and node[1] in L.CALCULUS and node[1] not in sc.funcs:
                return _calculus_steps(node, sc, q, sig, conversion)
            if node[0] == "call" and node[1] in sc.funcs and node[1] not in sc.vars and node[1] != "calc":
                return _user_steps(node, sc, q, sig, conversion)
            if node[0] == "index":
                return _index_steps(node, sc, q, sig, conversion)
            if node[0] == "call" and node[1] in ("real", "imag", "conj", "abs", "arg") and node[1] not in sc.funcs:
                steps = _complex_steps(node, sc, q, sig, conversion)
                if steps is not None:
                    return steps
            steps = _library_steps(node, sc, q, sig, conversion)
            if steps is not None:
                return steps
            steps = _function_steps(node, sc, q, sig, conversion)
            if steps is not None:
                return steps
            return _elementary_steps(node, sc, q, sig, conversion)
        if L._is_complex(q) or np.ndim(q.v) != 1 and not (node[0] == "call" and node[1] in funcs.EXPLAINERS):
            return None
        if node[0] == "call" and node[1] in funcs.EXPLAINERS:
            return _function_steps(node, sc, q, sig, conversion)
        return _elementwise_steps(node, sc, q, sig, conversion)
    except (_NoWork, L.LiveError, ArithmeticError, ValueError, KeyError, IndexError, TypeError, AttributeError, sp.SympifyError, NotImplementedError):
        return None


# ------------------------------------------------------------------ the result tail

def _tail(sc: L.Scope, q: L.Q, sig: int, conversion: list[dict] | None) -> list[dict]:
    """The closing steps (SI conversion, the unit asked for, the result) for a value that is already known: the plain steps of a bare name,
    without their Expression and Substitute lines."""
    s2 = sc.copy()
    s2.vars = {**sc.vars, "result": q}
    plain = L._plain_steps(("name", "result"), s2, q, sig, conversion)
    return [s for s in plain if s["label"] not in ("Expression", "Substitute the values")]


def _text(s: str) -> str:
    return L.tex(("str", s))


# ------------------------------------------------------------------ library calls

def _swap_calls(node, count: list[int], funcs) -> tuple:
    if not isinstance(node, tuple):
        return node
    if node[0] == "call" and node[1] == "calc" and "calc" not in funcs:
        count[0] += 1
        return ("name", f"calc{count[0]}")
    return tuple(_swap_calls(c, count, funcs) if isinstance(c, tuple) else [_swap_calls(x, count, funcs) for x in c] if isinstance(c, list) else c for c in node)


def _library_steps(node, sc, q, sig, conversion):
    count = [0]
    new = _swap_calls(node, count, sc.funcs)
    if not count[0]:
        return None
    entries = [w for w in sc.work if w["kind"] == "library"]
    if len(entries) != count[0] or len(entries) != len(sc.work) or any(e["sol"] is None for e in entries) or L._has_special(new):
        return None
    s2 = sc.copy()
    s2.vars = {**sc.vars, **{f"calc{k + 1}": e["q"] for k, e in enumerate(entries)}}
    steps = [{"label": "Expression", "latex": L.tex(node)}]
    for k, e in enumerate(entries):
        steps += _library_block(e, f"calc{k + 1}: " if len(entries) > 1 else "", sig)
    plain = L._plain_steps(new, s2, q, sig, conversion)
    if new[0] == "name":
        steps += [s for s in plain if s["label"] not in ("Expression", "Substitute the values")]
    else:
        plain[0] = {**plain[0], "label": "With the library results in place of the calls"}
        steps += plain
    return steps


def _library_block(e: dict, prefix: str, sig: int) -> list[dict]:
    calc, out, sol = e["calc"], e["out"], e["sol"]
    var = calc.by_key[out]
    given = [rf"{calc.by_key[k].latex or k} = {L.qty_texts(g, sig)[2]}" for k, g in e["given"]]
    steps = [{"label": f"{prefix}Library calculation", "latex": [_text(calc.name), rf"\text{{find }} {var.latex or out}\;\left({_text(var.label)}\right)", *given][:MAX_LINES + 2]}]
    sym = {s.title: s for s in sol.steps.get("symbolic", [])}
    if _CLOSED in sym:
        steps.append({"label": f"{prefix}In symbols, in the given quantities", "latex": [ln.latex for ln in sym[_CLOSED].lines][:MAX_LINES]})
    for st in sol.steps.get("numeric", []):
        if st.title in _SKIP_LIBRARY or not st.lines:
            continue
        label = f"{prefix}Convert the inputs to SI" if st.title == _GIVEN else f"{prefix}{st.title.split(' — ')[0]}"
        steps.append({"label": label, "latex": [ln.latex for ln in st.lines][:MAX_LINES]})
        if len(steps) >= MAX_STEPS_PER_CALL:
            steps.append({"label": f"{prefix}…", "latex": r"\text{the remaining steps are in the Calculations tab for this calculation}"})
            break
    return steps


# ------------------------------------------------------------------ elementary functions, complex numbers, element-wise list arithmetic

def _elementary_steps(node, sc, q, sig, conversion):
    if node[0] != "call" or node[1] in sc.funcs or len(node[2]) != 1 or node[1] not in funcs._ELEMENTARY:
        return None
    arg = L.evaluate(node[2][0], sc)
    mid = funcs.explain_elementary(node[1], arg, q, sc.angle == "deg", sig)
    return None if mid is None else [{"label": "Expression", "latex": L.tex(node)}, *mid, *_tail(sc, q, sig, conversion)]


def _complex_steps(node, sc, q, sig, conversion):
    mid = None
    if node[0] == "call" and node[1] not in sc.funcs and node[1] in ("real", "imag", "conj", "abs", "arg", "polar"):
        mid = funcs.explain_complex_function(node[1], [L.evaluate(a, sc) for a in node[2]], q, sig)
    if mid is None:
        if not L._is_complex(q):
            return None
        mid = funcs.explain_complex_value(q, sig)
    return [{"label": "Expression", "latex": L.tex(node)}, *mid, {"label": "Result", "latex": rf"= {L.qty_texts(q, sig)[2]}"}]


_ELEMENTWISE_CALLS = {"sqrt", "cbrt", "exp", "ln", "log", "log10", "log2", "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "abs", "floor", "ceil"}
MAX_ENTRIES = 3


def _entry_node(node, i: int, n: int, sc: L.Scope, vecs: dict):
    """The scalar expression for entry ``i``: list literals give their i-th element, list variables become a name that the substitution fills with the element."""
    if not isinstance(node, tuple):
        return node
    if node[0] == "list":
        if len(node[1]) != n or any(e[0] == "list" for e in node[1]):
            raise _NoWork
        return node[1][i]
    if node[0] == "name" and node[1] in sc.vars and np.ndim(sc.vars[node[1]].v) == 1:
        if sc.vars[node[1]].v.shape[0] != n:
            raise _NoWork
        vecs[node[1]] = sc.vars[node[1]]
        return node
    if node[0] in ("index", "str", "kw", "slice") or (node[0] == "call" and (node[1] not in _ELEMENTWISE_CALLS or node[1] in sc.funcs)):
        raise _NoWork
    return tuple(_entry_node(c, i, n, sc, vecs) if isinstance(c, tuple) else [_entry_node(x, i, n, sc, vecs) for x in c] if isinstance(c, list) else c for c in node)


def _elementwise_steps(node, sc, q, sig, conversion):
    """A list result of scalar arithmetic: the expression written out for the first entries (and the last), then the whole list."""
    n = int(np.asarray(q.v).shape[0])
    if n < 2 or node[0] in ("list", "name", "num", "qty") and node[0] != "qty":
        return None
    picks = list(range(min(n, MAX_ENTRIES))) + ([n - 1] if n > MAX_ENTRIES else [])
    lines = []
    for i in picks:
        vecs: dict = {}
        ni = _entry_node(node, i, n, sc, vecs)
        subst = {name: L.qty_texts(L.Q(float(np.real(v.v[i])), v.dim, v.unit), sig)[2] for name, v in vecs.items()}
        for name in L.names_in(ni):
            if name in sc.vars and name not in subst and not np.ndim(sc.vars[name].v):
                subst[name] = L.qty_texts(sc.vars[name], sig)[2]
        shown = L.qty_texts(L.Q(float(np.real(q.v[i])), q.dim, q.unit), sig)[2]
        if i == picks[-1] and n > MAX_ENTRIES:
            lines.append(r"\cdots")
        lines.append(rf"\text{{entry {i + 1}: }}\ {L.tex(ni, subst)} = {shown}")
    return [{"label": "Expression", "latex": L.tex(node)},
            {"label": "The same arithmetic on every entry", "latex": lines},
            *_tail(sc, q, sig, conversion)]


# ------------------------------------------------------------------ statistics, vector and matrix functions

def _swap_functions(node, sc: L.Scope, sig: int, found: list) -> tuple:
    if not isinstance(node, tuple):
        return node
    if node[0] == "call" and node[1] in funcs.EXPLAINERS and node[1] not in sc.funcs and node[1] not in sc.vars:
        args = [L.evaluate(a, sc) for a in node[2]]
        res = L.evaluate(node, sc)
        mid = funcs.explain(node[1], args, res, sig)
        if mid is not None:
            found.append((node[1], res, mid))
            return ("name", f"{node[1]}{len(found)}")
    return tuple(_swap_functions(c, sc, sig, found) if isinstance(c, tuple) else [_swap_functions(x, sc, sig, found) for x in c] if isinstance(c, list) else c for c in node)


def _function_steps(node, sc, q, sig, conversion):
    found: list = []
    new = _swap_functions(node, sc, sig, found)
    if not found:
        return None
    steps = [{"label": "Expression", "latex": L.tex(node)}]
    for k, (name, _res, mid) in enumerate(found):
        steps += [{**m, "label": f"{name}{k + 1}: {m['label']}" if len(found) > 1 else m["label"]} for m in mid]
    s2 = sc.copy()
    s2.vars = {**sc.vars, **{f"{name}{k + 1}": res for k, (name, res, _m) in enumerate(found)}}
    if new[0] == "name":
        return steps + _tail(s2, q, sig, conversion)
    if np.ndim(q.v) or L._is_complex(q) or L._has_special(new):
        return None
    plain = L._plain_steps(new, s2, q, sig, conversion)
    plain[0] = {**plain[0], "label": "With the results of the functions"}
    return steps + plain


def _index_steps(node, sc, q, sig, conversion):
    base, subs = node[1], node[2]
    if base[0] != "name" or any(x[0] == "slice" for x in subs) or base[1] not in sc.vars:
        return None
    idx = [int(L.evaluate(x, sc).v) for x in subs]
    whole = sc.vars[base[1]]
    return [{"label": "Expression", "latex": L.tex(node)},
            {"label": f"The list ({base[1]})", "latex": rf"{L.name_tex(base[1])} = {L.qty_texts(whole, sig)[2]}"},
            {"label": "Pick the entry (counting from 1)", "latex": rf"{L.name_tex(base[1])}_{{{', '.join(str(i) for i in idx)}}}"}] + _tail(sc, q, sig, conversion)


# ------------------------------------------------------------------ your own functions

def _user_steps(node, sc, q, sig, conversion):
    name, args = node[1], node[2]
    fn = sc.funcs[name]
    vals = [L.evaluate(a, sc) for a in args]
    if any(np.ndim(v.v) or L._is_complex(v) for v in vals) or len(vals) != len(fn.params):
        return None
    inner = sc.copy()
    inner.vars = {**sc.vars, **dict(zip(fn.params, vals))}
    body = L.make_steps(fn.body, inner, q, sig, conversion)
    head = rf"{L.name_tex(name)}\left({', '.join(L.name_tex(p) for p in fn.params)}\right)"
    return [{"label": "Expression", "latex": L.tex(node)},
            {"label": f"Definition of {name}", "latex": rf"{head} = {L.tex(fn.body)}"},
            {"label": "Arguments", "latex": [rf"{L.name_tex(p)} = {L.qty_texts(v, sig)[2]}" for p, v in zip(fn.params, vals)]},
            *body[1:]]


# ------------------------------------------------------------------ calculus functions

def _calculus_steps(node, sc, q, sig, conversion):
    if len(sc.work) != 1 or sc.work[0]["kind"] != "calculus":
        return None
    e = sc.work[0]
    name, fname, fn, pts, info = e["name"], e["fname"], e["fn"], e["pts"], e["info"]
    x = L.name_tex(fn.params[0])
    f = L.name_tex(fname)
    qt = lambda v: L.qty_texts(v, sig)[2]  # noqa: E731
    steps = [{"label": "Expression", "latex": L.tex(node)},
             {"label": "The function", "latex": rf"{f}\left({x}\right) = {L.tex(fn.body)}"}]
    sym = _symbolic(name, fn, pts, e["q"], sc, sig)
    if name == "integrate":
        a, b = pts
        steps.append({"label": "What is asked", "latex": rf"\int_{{{qt(a)}}}^{{{qt(b)}}} {f}\left({x}\right)\,d{x}"})
        why = r"\text{the function carries units, so it is integrated numerically:}" if _has_units(fn.body) else r"\text{no exact antiderivative was found, so it is integrated numerically:}"
        steps += sym or [{"label": "Method", "latex": [why,
                                                      rf"\text{{adaptive Gauss–Kronrod quadrature (QUADPACK), {info['evals']} evaluations of }}{f}",
                                                      rf"\text{{estimated numerical error: }} {L._num_tex(info['err'], 2)}\ \text{{ (in SI base units)}}"]}]
    elif name == "derivative":
        a = pts[0]
        h = info["h"]
        v = info["vals"]
        steps.append({"label": "What is asked", "latex": rf"{f}'\left({qt(a)}\right)"})
        steps += sym or [
            {"label": "Method: five-point central difference",
             "latex": rf"{f}'\left({x}_0\right) \approx \frac{{{f}({x}_0 - 2h) - 8\,{f}({x}_0 - h) + 8\,{f}({x}_0 + h) - {f}({x}_0 + 2h)}}{{12\,h}}"},
            {"label": "Step", "latex": [rf"{x}_0 = {L._num_tex(info['x0'], sig)},\quad h = {L._num_tex(h, sig)}\ \text{{ (SI base units)}}"]},
            {"label": f"Values of {fname} (SI base units)", "latex": [rf"{f}\left({x}_0 {t}\right) = {L._num_tex(val, sig)}" for t, val in zip(("- 2h", "- h", "+ h", "+ 2h"), v)]},
            {"label": "Substitute", "latex": rf"\frac{{({L._num_tex(v[0], sig)}) - 8\,({L._num_tex(v[1], sig)}) + 8\,({L._num_tex(v[2], sig)}) - ({L._num_tex(v[3], sig)})}}{{12\cdot {L._num_tex(h, sig)}}}"}]
    elif name == "findroot":
        lo, hi, root = info["lo"], info["hi"], info["root"]
        a = pts[0]
        steps.append({"label": "What is asked", "latex": rf"{f}\left({x}\right) = 0\ \text{{ between }}\ {qt(pts[0])}\ \text{{ and }}\ {qt(pts[1])}"})
        steps.append({"label": "The root is bracketed", "latex": [rf"{f}\left({L._num_tex(lo, sig)}\right) = {L._num_tex(info['flo'], sig)}", rf"{f}\left({L._num_tex(hi, sig)}\right) = {L._num_tex(info['fhi'], sig)}",
                                                                   r"\text{opposite signs, so a root lies between them}"]})
        if sym:
            steps += sym
        elif not info.get("trivial"):
            check = float(L.call_user(fn, fname, [L.Q(float(root), a.dim, a.unit)], sc, 0).v)
            steps.append({"label": "Method: Brent's method", "latex": [r"\text{bisection, secant and inverse quadratic steps, always keeping the root bracketed}",
                                                                        rf"\text{{converged in }} {info['iters']} \text{{ iterations}}",
                                                                        rf"{f}\left({x}\right) \approx {L._num_tex(check, 2)}\ \text{{ at the root (SI base units)}}"]})
    else:                                                                                       # sumover
        terms = info["terms"]
        k0, k1 = info["first"], info["last"]
        steps.append({"label": "What is asked", "latex": rf"\sum_{{{x}={k0}}}^{{{k1}}} {f}\left({x}\right)"})
        shown = [(k0 + i, t) for i, t in enumerate(terms)]
        if len(shown) > 6:
            shown = shown[:3] + [None] + shown[-1:]
        steps.append({"label": f"The {len(terms)} terms", "latex": [r"\cdots" if s is None else rf"{f}\left({s[0]}\right) = {qt(s[1])}" for s in shown]})
        steps += sym or []
        steps.append({"label": "Add them up", "latex": rf"\sum = {qt(e['q'])}"})
    return steps + _tail(sc, q, sig, conversion)


def _has_units(node) -> bool:
    if not isinstance(node, tuple):
        return False
    return node[0] in ("qty", "unit") or any(_has_units(c) for c in node[1:] if isinstance(c, tuple)) or any(_has_units(x) for c in node[1:] if isinstance(c, list) for x in c)


class _NoSym(Exception):
    pass


_SYM_FUNCS = {"exp": sp.exp, "ln": sp.log, "log": sp.log, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sqrt": sp.sqrt, "asin": sp.asin, "acos": sp.acos,
              "atan": sp.atan, "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh}


def _to_sympy(node, x: sp.Symbol, param: str, sc: L.Scope):
    k = node[0]
    if k == "num":
        return sp.nsimplify(node[1], rational=True)
    if k == "name":
        if node[1] == param:
            return x
        if node[1] == "pi":
            return sp.pi
        if node[1] == "e":
            return sp.E
        v = sc.vars.get(node[1])
        if v is None or np.ndim(v.v) or not v.dim.is_dimensionless:
            raise _NoSym
        return sp.nsimplify(float(v.v), rational=True)
    if k == "neg":
        return -_to_sympy(node[1], x, param, sc)
    if k == "bin":
        a, b = _to_sympy(node[2], x, param, sc), _to_sympy(node[3], x, param, sc)
        return {"+": a + b, "-": a - b, "*": a * b, "/": a / b}[node[1]]
    if k == "pow":
        return sp.Pow(_to_sympy(node[1], x, param, sc), _to_sympy(node[2], x, param, sc))
    if k == "call" and node[1] in _SYM_FUNCS and node[1] not in sc.funcs and len(node[2]) == 1:
        if sc.angle == "deg" and node[1] in ("sin", "cos", "tan", "asin", "acos", "atan"):
            raise _NoSym
        return _SYM_FUNCS[node[1]](_to_sympy(node[2][0], x, param, sc))
    raise _NoSym


def _symbolic(name: str, fn, pts: list[L.Q], res: L.Q, sc: L.Scope, sig: int) -> list[dict] | None:
    """Exact antiderivative or derivative of a unitless formula, evaluated by hand and checked against the numeric result; ``None`` if it does not apply."""
    if name not in ("integrate", "derivative", "findroot", "sumover") or not res.dim.is_dimensionless or not all(p.dim.is_dimensionless for p in pts):
        return None
    try:
        x = sp.Symbol(fn.params[0], real=True)
        expr = _to_sympy(fn.body, x, fn.params[0], sc)
        f = L.name_tex(fn.text.split("(")[0].strip())
        xt = L.name_tex(fn.params[0])
        num = lambda v: L._num_tex(float(v), sig)  # noqa: E731
        want = float(res.v)
        if name == "findroot":
            roots = [r for r in sp.solve(sp.Eq(expr, 0), x) if r.is_real is not False and abs(float(sp.N(r)) - want) <= 1e-8 * max(1.0, abs(want))]
            if not roots:
                return None
            allr = [r for r in sp.solve(sp.Eq(expr, 0), x) if r.is_real is not False]
            r = roots[0]
            return [{"label": "Solve exactly", "latex": rf"{sp.latex(expr)} = 0 \;\Rightarrow\; {xt} = {', '.join(sp.latex(v) for v in allr[:4])}"},
                    {"label": "The root inside the bracket", "latex": rf"{xt} = {sp.latex(r)} = {num(sp.N(r, 15))}"}]
        if name == "sumover":
            k0, k1 = (int(float(p.v)) for p in pts)
            if k1 - k0 > 400:
                return None
            n_sym, big_n = sp.Symbol(fn.params[0], integer=True), sp.Symbol("N", integer=True, positive=True)
            term = _to_sympy(fn.body, n_sym, fn.params[0], sc)
            steps = []
            closed = sp.summation(term, (n_sym, k0, big_n))
            if not closed.has(sp.Sum):
                steps.append({"label": "Closed form of the sum", "latex": rf"\sum_{{{xt}={k0}}}^{{N}} {sp.latex(term)} = {sp.latex(sp.simplify(closed))}"})
                exact = sp.simplify(closed.subs(big_n, k1))
            else:
                exact = sp.summation(term, (n_sym, k0, k1))
            if exact.has(sp.Sum) or abs(float(sp.N(exact)) - want) > 1e-8 * max(1.0, abs(want)):
                return None
            steps.append({"label": f"Evaluate with the last term {k1}", "latex": [rf"\sum_{{{xt}={k0}}}^{{{k1}}} {sp.latex(term)} = {sp.latex(exact)}", rf"= {num(sp.N(exact, 15))}"]})
            return steps
        if name == "derivative":
            d = sp.diff(expr, x)
            a = sp.nsimplify(float(pts[0].v), rational=True)
            val = sp.N(d.subs(x, a), 15)
            if not np.isfinite(float(val)) or abs(float(val) - want) > 1e-6 * max(1.0, abs(want)):
                return None
            return [{"label": "Differentiate", "latex": rf"{f}'\left({xt}\right) = {sp.latex(d)}"},
                    {"label": "Evaluate", "latex": [rf"{f}'\left({sp.latex(a)}\right) = {sp.latex(d.subs(x, a))}", rf"= {num(val)}"]}]
        big = sp.integrate(expr, x)
        if big.has(sp.Integral):
            return None
        lo, hi = (sp.nsimplify(float(p.v), rational=True) for p in pts)
        val = sp.N(big.subs(x, hi) - big.subs(x, lo), 15)
        if not np.isfinite(float(val)) or abs(float(val) - want) > 1e-6 * max(1.0, abs(want)):
            return None
        return [{"label": "Antiderivative", "latex": rf"F\left({xt}\right) = \int {sp.latex(expr)}\,d{xt} = {sp.latex(big)}"},
                {"label": "Evaluate between the limits", "latex": [rf"F\left({sp.latex(hi)}\right) - F\left({sp.latex(lo)}\right) = {sp.latex(big.subs(x, hi))} - \left({sp.latex(big.subs(x, lo))}\right)", rf"= {num(val)}"]}]
    except (_NoSym, sp.SympifyError, NotImplementedError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
