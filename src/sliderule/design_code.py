"""Export a System Design as MATLAB / Octave code or as an Excel workbook with live formulas.

Both exports share one *plan* (:func:`build_plan`): the free inputs and constants with their values converted to coherent SI, and, block by block in
dependency order, one step per computed quantity (the equation of the block rearranged for it, with each wire replaced by the quantity that feeds it).
Nothing is re-derived for the exporters: the plan comes from the same causal ordering the solver uses, and the SlideRule result of every quantity travels
with it so the generated file can check itself.

* ``render_matlab`` writes a script (MATLAB R2016b+ and GNU Octave): inputs in SI, one assignment per quantity, a results table and a self-check.
* ``render_excel`` writes an ``.xlsx`` (built with the standard library only, so it also works in the browser build): an *Inputs* sheet whose yellow cells
  you can edit, a *Calculations* sheet whose formulas refer to the inputs and to each other by name (``=PI()*Dr__b1^2/4``), a check against SlideRule's values and an
  *About* sheet. Cached values are stored, and Excel recalculates on opening.

Differential equations: one with a closed-form solution is written as that formula (both formats); a plain initial-value problem (no event, delay, boundary
condition or start-point singularity) is integrated with ``ode45`` in the MATLAB script only; finite ``Sum`` series become ``sum(arrayfun(...))`` / ``SUMPRODUCT``.

Not supported (reported with the block that causes it): boundary-value problems, events, delays, PDEs and SDEs, data tables, sums with open limits or
eigenvalue functions, and quantities that the solver finds numerically (root-finding, coupled equations) because they have no formula to write down.
"""

from __future__ import annotations

import io
import re
import zipfile
from types import SimpleNamespace
from xml.sax.saxutils import escape

import sympy as sp
from sympy.printing.octave import OctaveCodePrinter

from . import __version__
from .core.engine import parse_quantity, plan_structure, prune_plan
from .core.units_expr import fmt_number
from .design import solve_system
from .design_export import _display_name, _py_comment, system_model
from .units import default_registry


class Unsupported(Exception):
    pass


def closed_solution(system) -> dict | None:
    """The closed-form solution of a single ordinary differential equation (``{dependent: expression}``), or ``None`` when it is solved numerically."""
    closed = getattr(system, "closed", None)
    if type(system).__name__ != "OdeSystem" or not closed or getattr(system, "lag_syms", None) or getattr(system, "events", None):
        return None
    if set(closed) != set(system.dependents):
        return None
    return closed


def _in_dependency_order(items: list, local_to_q: dict, wire_map: dict) -> list:
    """The steps of one block so that each comes after the steps that produce what it uses (a differential equation's results can feed an algebraic equation of the same block, and the reverse)."""
    def needs(it) -> set:
        iv = getattr(it, "ivp", None)
        syms = set(it.expr.xreplace(local_to_q).xreplace(wire_map).free_symbols)
        if iv:
            syms |= {iv["tend"], *(x for e in (iv["t0"], *iv["rhs"], *iv["ics"]) for x in e.free_symbols)}
        return syms

    def gives(it):
        return local_to_q.get(it.sym, it.sym)

    pending, done, out = list(items), set(), []
    while pending:
        later = {gives(it) for it in pending}
        for it in pending:
            if not (needs(it) & later - {gives(it)}):
                out.append(it)
                pending.remove(it)
                break
        else:                                      # a cycle (coupled equations): keep the order the solver gave
            out.extend(pending)
            break
    return out


def plain_ivp(system) -> bool:
    """A numerically solved initial-value problem that MATLAB's ode45 reproduces directly (no events, delays, boundary conditions or hidden algebraic variables)."""
    if not (type(system).__name__ == "OdeSystem" and not system.closed and system.bvp is None and not system.events and not system.lag_syms
            and not system.pre and not system.hidden):
        return False
    # a centre or axis singularity at the start (u'/r at r = 0) needs the series start SlideRule uses: ode45 would begin at 0/0
    return not any(sp.denom(sp.together(r)).subs(system.t, system.start) == 0 for r in system.rhs)


def _diag(code: str, message: str, block: str | None = None) -> list[dict]:
    return [{"level": "error", "code": code, "message": message, "block": block}]


# ------------------------------------------------------------------ the shared plan

def _identifier(key: str, bid: str, used: set[str], case_sensitive: bool) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", f"{key}__{bid}")
    if not re.match(r"[A-Za-z]", base):
        base = "v" + base
    base = base[:56]
    name, n = base, 2
    norm = (lambda s: s) if case_sensitive else str.lower
    while norm(name) in used:
        name, n = f"{base}_{n}", n + 1
    used.add(norm(name))
    return name


def build_plan(graph: dict, sig_figs: int = 5, case_sensitive: bool = True) -> tuple[dict | None, list[dict]]:
    """``(plan, [])`` or ``(None, diagnostics)``."""
    result = solve_system(graph, sig_figs)
    if not result["ok"]:
        return None, result["diagnostics"]
    model = system_model(graph)
    blocks, order, qsym, drivers = model["blocks"], model["order"], model["qsym"], model["drivers"]
    reg = default_registry()
    for bid in order:
        calc = blocks[bid]["_calc"]
        if calc.tables:
            return None, _diag("UNSUPPORTED", f"block {bid} ({calc.name}) uses a data table, which has no plain formula; export LaTeX, Markdown, HTML or the Python script instead", bid)
        if calc.parsed_odes and not all(closed_solution(o) or plain_ivp(o) for o in calc.parsed_odes):
            return None, _diag("UNSUPPORTED", f"block {bid} ({calc.name}) uses a differential equation (boundary-value problem, event, delay or PDE) that is solved numerically, so it has no plain formula; export LaTeX, Markdown, HTML or the Python script instead", bid)
    used: set[str] = set()
    ident: dict[sp.Symbol, str] = {}
    for (bid, key), s in qsym.items():
        ident[s] = _identifier(key, bid, used, case_sensitive)

    wire_map = {qsym[dst]: qsym[src] for dst, src in drivers.items() if dst in qsym and src in qsym}
    inputs = []
    for (bid, key), v in model["free"].items():
        text = (blocks[bid].get("values") or {}).get(key)
        val, unit = parse_quantity(str(text)) if text and str(text).strip() else (v.default if v.default is not None else v.constant, v.unit)
        unit = (unit or v.unit).strip() or "1"
        u = reg.parse(unit, as_delta=v.delta)
        inputs.append({"bid": bid, "key": key, "label": v.label, "kind": "constant" if v.is_constant else "input", "value": float(val), "unit": unit,
                       "factor": u.factor, "shift": u.shift, "si": (float(val) + u.shift) * u.factor, "si_unit": v.si, "ident": ident[qsym[(bid, key)]], "sym": qsym[(bid, key)]})
    free_syms = {i["sym"] for i in inputs}

    steps = []
    for bid in order:
        b = blocks[bid]
        calc, roles = b["_calc"], b["_roles"]
        known = {calc.by_key[k].symbol for k, r in roles.items() if r != "output"}
        solved, _checks, _known, _fail = plan_structure(calc, known)
        outputs = [k for k, r in roles.items() if r == "output"]
        needed = prune_plan(solved, outputs)
        local_to_q = {v.symbol: qsym[(bid, v.key)] for v in calc.variables}
        have = {it.sym.name for it in needed}
        ode_forms = {dep.name: (expr, o.title) for o in calc.parsed_odes for dep, expr in (closed_solution(o) or {}).items() if dep.name in outputs}
        have |= set(ode_forms)
        ivp_steps = []
        for n_ode, o in enumerate(o for o in calc.parsed_odes if plain_ivp(o)):
            tt = sp.Symbol("tt_")
            to_matlab = {**{st: sp.Symbol(f"y({k + 1})") for k, st in enumerate(o.state)}, o.t: tt}

            def conv(e, to_matlab=to_matlab):
                return e.xreplace(to_matlab).xreplace(local_to_q).xreplace(wire_map)

            spec = {"sid": f"{bid}_{n_ode + 1}", "title": o.title, "tend": qsym[(bid, o.t.name)], "t0": conv(o.start), "rhs": [conv(r) for r in o.rhs], "ics": [conv(i) for i in o.ics]}
            for dep in o.dependents:
                if dep.name in outputs:
                    ivp_steps.append((dep.name, {**spec, "index": o.state_index[(dep, 0)] + 1}))
                    have.add(dep.name)
        missing = [k for k in outputs if k not in have and k in {o["key"] for o in result["blocks"][bid]["outputs"]}]
        if missing:
            return None, _diag("UNSUPPORTED", f"block {bid} ({calc.name}): {calc.by_key[missing[0]].label} is found numerically (root-finding or coupled equations), so it has no formula to export; "
                               "export LaTeX, Markdown, HTML or the Python script instead", bid)
        out_by_key = {o["key"]: o for o in result["blocks"][bid]["outputs"]}
        needed = [*(it for it in needed if it.sym.name not in {k for k, _ in ivp_steps}), *(SimpleNamespace(sym=calc.by_key[k].symbol, expr=e, eq=SimpleNamespace(title=t)) for k, (e, t) in ode_forms.items()),
                  *(SimpleNamespace(sym=calc.by_key[k].symbol, expr=sp.S.Zero, eq=SimpleNamespace(title=sp_["title"]), ivp=sp_) for k, sp_ in ivp_steps)]
        needed = _in_dependency_order(needed, local_to_q, wire_map)
        for it in needed:
            expr = it.expr.xreplace(local_to_q).xreplace(wire_map)
            stray = [s for s in expr.free_symbols if s not in ident]
            if stray or any(getattr(type(f), "_sliderule_ode", None) or hasattr(type(f), "_sliderule_table") for f in expr.atoms(sp.Function)):
                return None, _diag("UNSUPPORTED", f"block {bid} ({calc.name}): the formula for {calc.by_key[it.sym.name].label} uses a function that cannot be exported", bid)
            o = out_by_key.get(it.sym.name)
            v = calc.by_key[it.sym.name]
            du = reg.parse(o["unit"], as_delta=v.delta) if o else reg.parse(v.unit, as_delta=v.delta)
            steps.append({"bid": bid, "key": it.sym.name, "label": v.label, "expr": expr, "ivp": getattr(it, "ivp", None), "ident": ident[qsym[(bid, it.sym.name)]], "si_unit": v.si,
                          "ref": o["si_value"] if o else None, "unit": o["unit"] if o else v.unit, "factor": du.factor, "shift": du.shift, "eq": it.eq.title})
    produced = {qsym[(st["bid"], st["key"])] for st in steps}
    stray = [s for st in steps for s in st["expr"].free_symbols if s not in free_syms and s not in produced]
    for st in steps:
        iv = st["ivp"]
        if iv:
            stray += [s for e in (iv["t0"], *iv["rhs"], *iv["ics"]) for s in e.free_symbols if s not in ident and s.name != "tt_" and not s.name.startswith("y(")]
            stray += [s for s in iv["ics"] + [iv["t0"]] for s in s.free_symbols if s.name == "tt_" or s.name.startswith("y(")]        # the start and the initial values do not depend on the solution
    if stray:
        return None, _diag("UNSUPPORTED", f"internal: {stray[0]} has no value in the exported system")
    return {"order": order, "blocks": blocks, "inputs": inputs, "steps": steps, "ident": ident, "result": result, "sig": sig_figs}, []


# ------------------------------------------------------------------ MATLAB / Octave

_MATLAB_HEAD = """\
% {title}
% Generated by SlideRule {version}. Runs in MATLAB (R2016b or later) and GNU Octave.
% Every quantity is in coherent SI units: change an input by editing its line below
% (the value, then its unit conversion factor and offset) and run the script again.
% Each result is compared with the value SlideRule computed when this file was made.
"""


class _MatlabPrinter(OctaveCodePrinter):
    """The Octave printer plus the logarithms SlideRule's equation language has as functions of their own."""

    def _print_log10(self, e):
        return f"log10({self._print(e.args[0])})"

    def _print_log2(self, e):
        return f"log2({self._print(e.args[0])})"

    def _print_erfc(self, e):
        return f"erfc({self._print(e.args[0])})"

    def _print_Sum(self, e):                            # a finite sum over a counter: one anonymous function mapped over the integers
        (n, lo, hi), = e.limits
        if not (lo.is_Integer and hi.is_Integer and 0 <= hi - lo <= 1000):
            raise ValueError("only a sum with a finite number of terms can be written")
        return f"sum(arrayfun(@({n.name}) {self._print(e.function)}, {int(lo)}:{int(hi)}))"

    def _print_elliptic_k(self, e):                     # complete elliptic integral of the first kind, parameter m = k^2 (MATLAB and Octave: ellipke)
        return f"ellipke({self._print(e.args[0])})"


def _matlab_expr(expr: sp.Expr, ident: dict) -> str:
    code = _MatlabPrinter({"strict": True}).doprint(expr.xreplace({s: sp.Symbol(n) for s, n in ident.items()}))
    return re.sub(r"(?<=[\w)])\.([*/^])", r"\1", code)         # element-wise operators are the same for scalars; write the plain ones


def _matlab_statements(name: str, expr: sp.Expr, ident: dict, comment: str) -> list[str]:
    """``name = expr;`` with every Piecewise written as an if/elseif/else block (an expression cannot branch in MATLAB)."""
    lines: list[str] = []
    n = 0
    while True:
        inner = [p for p in expr.atoms(sp.Piecewise) if len(p.atoms(sp.Piecewise)) == 1]
        if not inner:
            break
        p = inner[0]
        n += 1
        tmp = sp.Symbol(f"{name}_branch{n}")
        ident = {**ident, tmp: tmp.name}
        for k, (e, c) in enumerate(p.args):
            if c == sp.true:
                lines += ["else" if k else "", f"    {tmp.name} = {_matlab_expr(e, ident)};"]
            else:
                lines += [f"{'if' if k == 0 else 'elseif'} {_matlab_expr(c, ident)}", f"    {tmp.name} = {_matlab_expr(e, ident)};"]
        if p.args[-1][1] != sp.true:
            lines += ["else", f"    {tmp.name} = NaN;"]
        lines.append("end")
        lines = [ln for ln in lines if ln != ""]
        expr = expr.xreplace({p: tmp})
    lines.append(f"{name} = {_matlab_expr(expr, ident)};   % {comment}")
    return lines


def _matlab_ivp(st: dict, ident: dict, solved: set) -> list[str]:
    """An initial-value problem integrated with ode45; one integration serves every output of the same system."""
    iv = st["ivp"]
    sid = iv["sid"]
    lines: list[str] = []
    if sid not in solved:
        solved.add(sid)
        names = {**ident, sp.Symbol("tt_"): "tt"}
        rhs = "; ".join(_matlab_expr(r, names) for r in iv["rhs"])
        ics = "; ".join(_matlab_expr(i, ident) for i in iv["ics"])
        lines += [f"% {iv['title']}: solved numerically with ode45 (tight tolerances; a stiff problem may need ode15s)",
                  f"f_{sid} = @(tt, y) [{rhs}];",
                  f"[~, Y_{sid}] = ode45(f_{sid}, [{_matlab_expr(iv['t0'], ident)}, {ident[iv['tend']]}], [{ics}], odeset('RelTol', 1e-10, 'AbsTol', 1e-13));"]
    lines.append(f"{st['ident']} = Y_{sid}(end, {iv['index']});   % {st['label']} [{st['si_unit']}]")
    return lines


def render_matlab(graph: dict, sig_figs: int = 5, title: str = "System model") -> tuple[str, list[dict]]:
    plan, diags = build_plan(graph, sig_figs)
    if plan is None:
        return "", diags
    blocks, ident = plan["blocks"], plan["ident"]
    out = [_MATLAB_HEAD.format(title=title, version=__version__).rstrip("\n"), "", "%% Inputs and constants (SI = (value + offset) * factor)"]
    for i in plan["inputs"]:
        u = "" if i["unit"] in ("", "1") else f" {i['unit']}"
        out.append(f"{i['ident']} = ({i['value']!r} + {i['shift']!r})*{i['factor']!r};   % block {i['bid']}: {i['label']} ({i['kind']}), {fmt_number(i['value'], sig_figs)[0]}{u} -> SI {i['si_unit']}")
    seen = None
    solved_ivp: set[str] = set()
    for st in plan["steps"]:
        if st["bid"] != seen:
            seen = st["bid"]
            out += ["", f"%% Block {seen}: {_display_name(blocks[seen]['_calc'])}"]
            out += [ln.replace("#", "%", 1) for ln in _py_comment(blocks[seen].get("comment"))]
        try:
            if st["ivp"]:
                out += _matlab_ivp(st, ident, solved_ivp)
                continue
            out += _matlab_statements(st["ident"], st["expr"], ident, f"{st['label']} [{st['si_unit']}]")
        except Exception as exc:  # noqa: BLE001 - a function the MATLAB printer does not know
            return "", _diag("UNSUPPORTED", f"block {st['bid']}: cannot write the formula for {st['label']} in MATLAB ({str(exc).splitlines()[0]})", st["bid"])
    out += ["", "%% Results (value in the unit SlideRule used, then in SI)", "names = {};", "got = [];", "ref = [];"]
    for st in plan["steps"]:
        if st["ref"] is None:
            continue
        shown = f"{st['ident']}/{st['factor']!r} - {st['shift']!r}" if (st["factor"] != 1 or st["shift"]) else st["ident"]
        out.append(f"fprintf('%-48s %14.6g %s   (SI %.6g)\\n', '{st['bid']}: {st['label'].replace(chr(39), chr(39) * 2)}', {shown}, '{st['unit']}', {st['ident']});")
        out.append(f"names{{end+1}} = '{st['ident']}'; got(end+1) = {st['ident']}; ref(end+1) = {st['ref']!r};")
    out += ["", "if all(abs(got - ref) <= 1e-6*max(abs(ref), 1e-300))", "    disp('matches the SlideRule reference values');", "else", "    disp('DIFFERS from the SlideRule reference values');", "end", ""]
    return "\n".join(out), []


# ------------------------------------------------------------------ Excel formulas

_XL_FUNCS = {sp.exp: "EXP", sp.log: "LN", sp.sin: "SIN", sp.cos: "COS", sp.tan: "TAN", sp.asin: "ASIN", sp.acos: "ACOS", sp.atan: "ATAN", sp.sinh: "SINH",
             sp.cosh: "COSH", sp.tanh: "TANH", sp.asinh: "ASINH", sp.acosh: "ACOSH", sp.atanh: "ATANH", sp.Abs: "ABS", sp.sign: "SIGN", sp.erf: "ERF",
             sp.Max: "MAX", sp.Min: "MIN", sp.factorial: "FACT"}
_XL_REL = {sp.Gt: ">", sp.Lt: "<", sp.Ge: ">=", sp.Le: "<=", sp.Eq: "=", sp.Ne: "<>"}


def _num(x: float) -> str:
    s = f"{float(x):.15g}".upper()
    return s


def _xl(e: sp.Basic, names: dict) -> tuple[str, int]:
    """An Excel expression for ``e`` and its precedence (1 sum or negation, 2 product, 3 power, 5 atom or call)."""
    if isinstance(e, sp.Symbol):
        return names[e], 5
    if e == sp.pi:
        return "PI()", 5
    if e == sp.E:
        return "EXP(1)", 5
    if e == sp.true:
        return "TRUE", 5
    if e.is_Integer:
        return (str(int(e)), 5) if e >= 0 else (f"({int(e)})", 5)
    if e.is_Rational:
        return f"({int(e.p)}/{int(e.q)})", 5
    if e.is_Float:
        s = _num(e)
        return (s, 5) if float(e) >= 0 else (f"({s})", 5)
    wrap = lambda pair, need: f"({pair[0]})" if pair[1] < need else pair[0]
    if e.is_Add:
        out = ""
        for k, a in enumerate(e.args):
            s, _p = _xl(a, names)
            if s.startswith("-"):
                out += f" - {s[1:]}" if k else s
            else:
                out += f" + {s}" if k else s
        return out, 1
    if e.is_Mul:
        c, rest = e.as_coeff_Mul()
        sign = "-" if c < 0 else ""
        c = abs(c)
        num: list = []
        den: list = []
        if c != 1:
            if c.is_Rational and not c.is_Integer:
                if c.p != 1:
                    num.append(sp.Integer(c.p))
                den.append(sp.Integer(c.q))
            else:
                num.append(c)
        for f in sp.Mul.make_args(rest):
            if f.is_Pow and (f.exp.is_negative is True):
                den.append(sp.Pow(f.base, -f.exp, evaluate=False) if f.exp != -1 else f.base)
            else:
                num.append(f)
        top = "*".join(wrap(_xl(f, names), 2) for f in num) or "1"
        if den:
            bottom = "*".join(wrap(_xl(f, names), 3) for f in den)
            top = f"{top}/({bottom})" if len(den) > 1 else f"{top}/{wrap(_xl(den[0], names), 3)}"
        return sign + top, 1 if sign else 2
    if e.is_Pow:
        b, x = e.args
        if x == sp.Rational(1, 2):
            return f"SQRT({_xl(b, names)[0]})", 5
        if x == -1:
            return f"1/{wrap(_xl(b, names), 3)}", 2
        if x == sp.Rational(-1, 2):
            return f"1/SQRT({_xl(b, names)[0]})", 2
        if x.is_negative is True:
            return f"1/{wrap(_xl(sp.Pow(b, -x, evaluate=False), names), 3)}", 2
        bs = wrap(_xl(b, names), 4)
        es, ep = _xl(x, names)
        return f"{bs}^{es if ep >= 5 else '(' + es + ')'}", 3
    if isinstance(e, sp.Piecewise):
        text = "NA()"
        for expr_, cond in reversed(e.args):
            text = _xl(expr_, names)[0] if cond == sp.true else f"IF({_xl(cond, names)[0]},{_xl(expr_, names)[0]},{text})"
        return text, 5
    if type(e) in _XL_REL:
        return f"{_xl(e.lhs, names)[0]}{_XL_REL[type(e)]}{_xl(e.rhs, names)[0]}", 0
    if isinstance(e, (sp.And, sp.Or)):
        return f"{'AND' if isinstance(e, sp.And) else 'OR'}({','.join(_xl(a, names)[0] for a in e.args)})", 5
    if isinstance(e, sp.Not):
        return f"NOT({_xl(e.args[0], names)[0]})", 5
    f = type(e)
    if isinstance(e, sp.Sum):                                     # SUMPRODUCT turns the body into an array formula over ROW(INDIRECT("lo:hi"))
        (n, lo, hi), = e.limits
        if not (lo.is_Integer and hi.is_Integer and 0 <= hi - lo <= 1000) or lo < 1:
            raise Unsupported("Sum with open limits")
        inner = _xl(e.function, {**names, n: f'ROW(INDIRECT("{int(lo)}:{int(hi)}"))'})[0]
        return f"SUMPRODUCT({inner})", 5
    if f in _XL_FUNCS:
        return f"{_XL_FUNCS[f]}({','.join(_xl(a, names)[0] for a in e.args)})", 5
    if f is sp.atan2:
        return f"ATAN2({_xl(e.args[1], names)[0]},{_xl(e.args[0], names)[0]})", 5            # Excel takes (x, y)
    if f is sp.floor:
        return f"INT({_xl(e.args[0], names)[0]})", 5
    if f is sp.ceiling:
        return f"-INT(-{wrap(_xl(e.args[0], names), 3)})", 1
    if f is sp.gamma:
        return f"EXP(GAMMALN({_xl(e.args[0], names)[0]}))", 5
    if f.__name__ in ("besselj", "bessely", "besseli", "besselk") and e.args[0].is_Integer and e.args[0] >= 0:
        return f"{f.__name__.upper()}({_xl(e.args[1], names)[0]},{int(e.args[0])})", 5                  # Excel takes (x, n)
    if f.__name__ == "log10":
        return f"LOG10({_xl(e.args[0], names)[0]})", 5
    if f.__name__ == "log2":
        return f"LOG({_xl(e.args[0], names)[0]},2)", 5
    if f.__name__ == "erfc":
        return f"ERFC({_xl(e.args[0], names)[0]})", 5
    raise Unsupported(f"{f.__name__}")


def excel_formula(expr: sp.Expr, names: dict) -> str:
    text = _xl(expr, names)[0]
    if len(text) > 8000:
        raise Unsupported("the formula is longer than Excel allows")
    return text


# ------------------------------------------------------------------ the .xlsx container

def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


_S_DEFAULT, _S_HEAD, _S_INPUT, _S_CONST, _S_WRAP, _S_TITLE, _S_NOTE = range(7)

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="4"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="14"/><name val="Calibri"/></font><font><i/><sz val="10"/><color rgb="FF666666"/><name val="Calibri"/></font></fonts>
<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE4DCC8"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2B3"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEDEDED"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFBBBBBB"/></left><right style="thin"><color rgb="FFBBBBBB"/></right><top style="thin"><color rgb="FFBBBBBB"/></top><bottom style="thin"><color rgb="FFBBBBBB"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="7"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


class _Sheet:
    def __init__(self, name: str, widths: list[float]):
        self.name, self.widths = name, widths
        self.rows: list[dict[int, str]] = []

    def row(self, cells: list | None = None) -> int:
        """Append a row; each cell is None, ``("s", text, style)``, ``("n", number, style)`` or ``("f", formula, cached, style)``. Returns the 1-based row number."""
        xml: dict[int, str] = {}
        r = len(self.rows) + 1
        for c, cell in enumerate(cells or []):
            if cell is None:
                continue
            ref = f"{_col(c)}{r}"
            kind = cell[0]
            if kind == "s":
                xml[c] = f'<c r="{ref}" t="inlineStr" s="{cell[2]}"><is><t xml:space="preserve">{escape(str(cell[1]))}</t></is></c>'
            elif kind == "n":
                xml[c] = f'<c r="{ref}" s="{cell[2]}"><v>{_num(cell[1])}</v></c>'
            else:
                cached = cell[2]
                if isinstance(cached, str):
                    xml[c] = f'<c r="{ref}" s="{cell[3]}" t="str"><f>{escape(cell[1])}</f><v>{escape(cached)}</v></c>'
                else:
                    xml[c] = f'<c r="{ref}" s="{cell[3]}"><f>{escape(cell[1])}</f><v>{_num(cached)}</v></c>'
        self.rows.append(xml)
        return r

    def xml(self, freeze: bool = True) -> str:
        cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(self.widths))
        rows = "".join(f'<row r="{r + 1}">{"".join(cells[c] for c in sorted(cells))}</row>' for r, cells in enumerate(self.rows))
        pane = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>' if freeze else ""
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"{pane}<cols>{cols}</cols><sheetData>{rows}</sheetData></worksheet>")


def _package(sheets: list[_Sheet], names: dict[str, str], freeze: list[bool]) -> bytes:
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(sheets)))
          + "</Types>")
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets)))
               + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    defined = "".join(f'<definedName name="{escape(n)}">{escape(ref)}</definedName>' for n, ref in sorted(names.items()))
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + "".join(f'<sheet name="{escape(s.name)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, s in enumerate(sheets))
          + f"</sheets><definedNames>{defined}</definedNames>" + '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", _STYLES)
        for i, s in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", s.xml(freeze[i]))
    return buf.getvalue()


def render_excel(graph: dict, sig_figs: int = 5, title: str = "System model") -> tuple[bytes, list[dict]]:
    plan, diags = build_plan(graph, sig_figs, case_sensitive=False)       # Excel names ignore case
    if plan is None:
        return b"", diags
    ivp = next((st for st in plan["steps"] if st["ivp"]), None)
    if ivp is not None:
        return b"", _diag("UNSUPPORTED", f"block {ivp['bid']}: {ivp['label']} comes from a differential equation that is integrated numerically, which a spreadsheet formula cannot do; export MATLAB or the Python script instead", ivp["bid"])
    blocks, ident = plan["blocks"], plan["ident"]
    inputs_sheet = _Sheet("Inputs", [9, 12, 38, 10, 16, 12, 14, 12, 18])
    calc_sheet = _Sheet("Calculations", [9, 14, 38, 44, 18, 12, 18, 12, 18, 10, 14, 12])
    about = _Sheet("About", [110])
    names: dict[str, str] = {}

    inputs_sheet.row([("s", h, _S_HEAD) for h in ("Block", "Symbol", "Quantity", "Kind", "Value (edit)", "Unit", "Factor to SI", "Offset (added first)", "Value in SI")])
    for i in plan["inputs"]:
        r = len(inputs_sheet.rows) + 1
        style = _S_CONST if i["kind"] == "constant" else _S_INPUT
        inputs_sheet.row([("s", i["bid"], _S_DEFAULT), ("s", i["key"], _S_DEFAULT), ("s", i["label"], _S_DEFAULT), ("s", i["kind"], _S_DEFAULT), ("n", i["value"], style),
                          ("s", i["unit"], _S_DEFAULT), ("n", i["factor"], _S_DEFAULT), ("n", i["shift"], _S_DEFAULT), ("f", f"(E{r}+H{r})*G{r}", i["si"], _S_DEFAULT)])
        names[i["ident"]] = f"Inputs!$I${r}"
    inputs_sheet.row()
    inputs_sheet.row([("s", "Yellow cells are inputs you can change (in the unit shown); grey cells are physical constants. Column I (in coherent SI) feeds the Calculations sheet.", _S_NOTE)])

    calc_sheet.row([("s", h, _S_HEAD) for h in ("Block", "Symbol", "Quantity", "Formula as derived", "Value (SI)", "SI unit", "Value (shown)", "Unit", "SlideRule (SI)", "Check", "Unit factor", "Unit offset")])
    values = {i["ident"]: i["si"] for i in plan["inputs"]}
    for st in plan["steps"]:
        r = len(calc_sheet.rows) + 1
        try:
            formula = excel_formula(st["expr"], ident)
        except Unsupported as exc:
            return b"", _diag("UNSUPPORTED", f"block {st['bid']}: cannot write the formula for {st['label']} in Excel ({exc})", st["bid"])
        ref = st["ref"]
        si = ref if ref is not None else 0.0
        values[st["ident"]] = si
        shown = si / st["factor"] - st["shift"]
        written = sp.sstr(st["expr"].xreplace({s: sp.Symbol(n) for s, n in ident.items()})).replace("**", "^")
        calc_sheet.row([("s", st["bid"], _S_DEFAULT), ("s", st["key"], _S_DEFAULT), ("s", st["label"], _S_DEFAULT), ("s", written, _S_DEFAULT),
                        ("f", formula, si, _S_DEFAULT), ("s", st["si_unit"], _S_DEFAULT), ("f", f"E{r}/K{r}-L{r}", shown, _S_DEFAULT), ("s", st["unit"], _S_DEFAULT),
                        ("n", ref, _S_DEFAULT) if ref is not None else None,
                        ("f", f'IF(ABS(E{r}-I{r})<=0.000001*MAX(ABS(I{r}),1E-300),"OK","DIFFERS")', "OK", _S_DEFAULT) if ref is not None else None,
                        ("n", st["factor"], _S_DEFAULT), ("n", st["shift"], _S_DEFAULT)])
        names[st["ident"]] = f"Calculations!$E${r}"
    calc_sheet.row()
    calc_sheet.row([("s", "Every formula refers to the inputs and to other results by name (Formulas > Name Manager). Change a yellow cell on the Inputs sheet and everything below follows. "
                          "The Check column compares with the values SlideRule computed when this file was made, so it reads DIFFERS once you change an input; that is expected.", _S_NOTE)])

    about.row([("s", title, _S_TITLE)])
    about.row([("s", f"Generated by SlideRule {__version__}. Quantities are computed in coherent SI units; unit conversions are explicit (Inputs columns G and H, Calculations columns K and L).", _S_WRAP)])
    about.row([("s", "Blocks:", _S_HEAD)])
    for bid in plan["order"]:
        about.row([("s", f"{bid}: {_display_name(blocks[bid]['_calc'])}", _S_WRAP)])
        for line in _py_comment(blocks[bid].get("comment")):
            about.row([("s", "    " + line.lstrip("# ").rstrip(), _S_NOTE)])
    return _package([inputs_sheet, calc_sheet, about], names, [True, True, False]), []
