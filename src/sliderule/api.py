"""Transport-independent API.

Every function takes and returns plain JSON-compatible data, so the same code is exposed by the
FastAPI server (local install) and called in-process through Pyodide (static web build).
"""

from __future__ import annotations

import functools
import json
import logging
from collections import Counter
from typing import Any, Callable

import sympy as sp

from . import __version__
from .core import Calculation, solve as _solve
from .core.catalog import default_catalog
from .core.taxonomy import SUBDISCIPLINES
from .library import reference_status
from .core.engine import plan_structure
from .core.timeout import TimeLimitExceeded, time_limit
from . import design, design_equation, design_export, livecalc, livecalc_help, settings, usercalcs, userlists
from .core.custom import CustomError, calc_from_dict, calc_to_dict
from .core import datapack
from .core.units_expr import fmt_number, unit_tex
from .units import UnitError, default_registry


class ApiError(Exception):
    def __init__(self, message: str, code: str = "BAD_REQUEST", status: int = 400):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


def limited(fn):
    """Run ``fn`` under the user's calculation time limit (``sliderule.settings``); exceeding it is a TIMEOUT error."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        default_catalog()          # building the library is not user work: keep it outside the limit
        try:
            with time_limit(settings.limit()):
                return fn(*args, **kwargs)
        except TimeLimitExceeded as exc:
            raise ApiError(f"The calculation took longer than {exc.seconds:g} s and was stopped. Raise or switch off the time limit in Settings "
                           "(the gear in the web app, `sliderule settings` on the command line) or simplify the problem.", "TIMEOUT", 408) from None
    return wrapper


# ------------------------------------------------------------------ property data (datapacks)

def data_packs() -> dict:
    """The loaded datapacks, the property vocabulary, and any packs that were refused (with the reasons)."""
    return {"packs": [datapack.pack_summary(p) for p in datapack.packs().values()],
            "properties": [{"kind": kind, "name": k, "label": v[0], "unit": v[1]} for kind, voc in datapack.VOCABULARIES.items() for k, v in voc.items()],
            "refused": datapack.problems()}


def data_search(q: str = "", pack: str = "", category: str = "") -> dict:
    res = datapack.search(q, pack, category)
    return {"count": len(res), "results": res}


def data_value(pack: str, record_id: str, prop: str, x: float | None = None, x_unit: str = "K", unit: str | None = None) -> dict:
    """One property, at temperature ``x`` (``x_unit``) for a curve, in ``unit`` (default: the stored unit)."""
    try:
        return datapack.value(pack, record_id, prop, x, x_unit, unit)
    except datapack.DataPackError as exc:
        missing = str(exc).startswith(("no data pack", "no record"))
        raise ApiError(str(exc), "NOT_FOUND" if missing else "OUT_OF_RANGE" if "outside the stored range" in str(exc) else "BAD_REQUEST",
                       404 if missing else 400) from None


def data_options(variables: list) -> dict:
    """Which datapack properties could fill each ``{key, unit, label}`` variable of the open calculation."""
    if not isinstance(variables, list) or len(variables) > 200 or not all(isinstance(v, dict) for v in variables):
        raise ApiError("variables must be a list of {key, unit, label}", "BAD_REQUEST", 400)
    return {"options": datapack.options_for(variables)}


def data_record(pack: str, record_id: str) -> dict:
    try:
        return datapack.record(pack, record_id)
    except datapack.DataPackError as exc:
        raise ApiError(str(exc), "NOT_FOUND", 404) from None


# ------------------------------------------------------------------ catalog

def meta() -> dict:
    cat = default_catalog()
    return {"name": "SlideRule", "version": __version__, "calculation_count": len(cat),
            "custom_count": sum(1 for c in cat if c.custom), "storage": usercalcs.storage(), "settings": settings.get(),
            "levels": {"basic": {"subdiscipline": BASIC_SUBDISCIPLINE, "subdisciplines": [BASIC_SUBDISCIPLINE, *BASIC_CHEMISTRY], "count": sum(1 for c in cat if is_basic(c))}, "advanced": {"count": len(cat)}}, **cat.facets()}


def _summary(c: Calculation) -> dict:
    return {
        "id": c.id, "name": c.name, "disciplines": c.disciplines, "subdisciplines": c.subdisciplines, "description": c.description, "tags": c.tags,
        "outputs": c.outputs, "custom": c.custom,
        "variables": [{"key": v.key, "label": v.label, "latex": v.latex, "kinds": v.kinds[:2], "constant": v.is_constant}
                      for v in c.variables],
    }


def _as_list(x: Any) -> list[str]:
    if x is None or x == "":
        return []
    if isinstance(x, str):
        return [p.strip() for p in x.split(",") if p.strip()]
    return [str(p).strip() for p in x if str(p).strip()]


#: the "basic" level of the calculation list: the equations of classical mechanics
BASIC_SUBDISCIPLINE = "Classical Mechanics"
#: ... and the college-level chemistry (an introductory sequence: general chemistry, equilibria, kinetics, thermodynamics, electrochemistry, atoms, organic)
BASIC_CHEMISTRY = ("General Chemistry", "Analytical Chemistry", "Chemical Kinetics", "Chemical Thermodynamics", "Electrochemistry", "Atomic Structure and Spectroscopy", "Organic Chemistry")


def is_basic(c: Calculation, subs: Any = None) -> bool:
    """``subs``: the user's own choice of what Basic includes (sub-discipline names); None for the default described above."""
    if subs is not None:
        return any(x in subs for x in c.subdisciplines)
    return BASIC_SUBDISCIPLINE in c.subdisciplines or ("chemistry" in c.disciplines and any(x in BASIC_CHEMISTRY for x in c.subdisciplines))
MAX_LIST_IDS = 3000


def list_calculations(q: str = "", disciplines: Any = None, variables: Any = None, solves_for: Any = None,
                      subdisciplines: Any = None, source: str = "", level: str = "", ids: Any = None, basic: Any = None) -> dict:
    """``source``: "" for everything, "custom" for the user's own calculations, "library" for the built-in ones.

    ``level``: "basic" keeps only the calculations of classical mechanics and college-level chemistry; "" or "advanced" keeps everything.
    ``basic``: names of the sub-disciplines the Basic level means, when the user has chosen their own (at most 300); the default otherwise.
    ``ids``: when given (even empty), only these calculations, in the order of the search ranking: the favourites and the user's groups are lists of ids kept by the page.
    """
    cat = default_catalog()
    if level not in ("", "advanced", "basic"):
        raise ApiError(f"Unknown level {level!r}: use basic or advanced", "BAD_REQUEST")
    disc, var, sol, sub = _as_list(disciplines), _as_list(variables), _as_list(solves_for), _as_list(subdisciplines)
    basic_subs = set(_as_list(basic)[:300]) if basic is not None else None
    keep = set(_as_list(ids)[:MAX_LIST_IDS]) if ids is not None else None
    want = (source == "custom") if source in ("custom", "library") else None

    def pool(d=disc, v=var, so=sol, sb=sub) -> list[Calculation]:
        out = cat.search(q or "", d, v, so, sb)
        if level == "basic":                              # a filter of its own: both this and any sub-discipline the user typed must hold
            out = [c for c in out if is_basic(c, basic_subs)]
        if keep is not None:
            out = [c for c in out if c.id in keep]
        if want is not None:
            out = [c for c in out if c.custom == want]
        return out

    found = pool()
    # Each facet is counted over what the *other* filters leave, so an option is offered only if choosing it would give something.
    facets = cat.facets(pool(d=[]))
    sub_counts = Counter(x for c in pool(sb=[]) for x in c.subdisciplines)
    facets["subdisciplines"] = [{"name": n, "count": sub_counts.get(n, 0)} for n in sorted(SUBDISCIPLINES)]
    facets["variables"] = _symbols_and_kinds(c.variables for c in pool(v=[]))
    facets["solves"] = _symbols_and_kinds(c.inputs for c in pool(so=[]))
    return {"count": len(found), "results": [_summary(c) for c in found], "facets": facets}


def _symbols_and_kinds(groups) -> list[str]:
    """The quantity kinds (commonest first) then the symbols found in these groups of variables, for filter auto-complete."""
    kinds: Counter = Counter()
    symbols: set[str] = set()
    for g in groups:
        for v in g:
            kinds.update(v.kinds[:2])
            symbols.add(v.key)
    return [*sorted(kinds, key=lambda k: (-kinds[k], k)), *sorted(symbols, key=str.lower)]


def variable_vocabulary() -> dict:
    """Distinct variable symbols and quantity kinds, for filter auto-complete."""
    cat = default_catalog()
    kinds: dict[str, int] = {}
    symbols: dict[str, set[str]] = {}
    for c in cat:
        for v in c.variables:
            for k in v.kinds[:2]:
                kinds[k] = kinds.get(k, 0) + 1
            symbols.setdefault(v.key, set()).add(v.label)
    return {"kinds": sorted(kinds, key=lambda k: (-kinds[k], k)),
            "symbols": [{"key": k, "labels": sorted(l)} for k, l in sorted(symbols.items(), key=lambda kv: kv[0].lower())]}


def _ode_info(c: Calculation) -> list[dict]:
    names = c.latex_names()
    return [{"title": s.title, "independent": (s.x.name if getattr(s, "pde", False) else s.t.name), "start": str(s.x0 if getattr(s, "dim", 1) == 2 else s.start), "method": s.method, "kind": "numeric" if s.numeric else "closed",
             "why_numeric": s.why_numeric, "equations": s.texts, "initial": s.initial_texts,
             **({"bvp": True, "end": str(s.bvp.end), "boundary": s.bvp.texts, "guess": s.bvp.guess_texts, "unknowns": [u.name for u in s.bvp.unknowns]} if s.bvp is not None else {}),
             **({"pde": True, "space": s.x.name, "nodes": s.nodes, **({"second": s.y.name, "end": str(s.x1), "second_end": str(s.y1)} if getattr(s, "dim", 1) == 2 else {"end": str(s.end), "order": s.order})}
                if getattr(s, "pde", False) else {}),
             "latex": s.written_latex(names), "conditions": s.condition_latex(names), "dependents": [d.name for d in s.dependents],
             "events": [{"title": e.title, "direction": e.direction, "terminal": e.terminal, "latex": f"{sp.latex(e.written[0], symbol_names=names)} = {sp.latex(e.written[1], symbol_names=names)}",
                         "time": e.time_var.name if e.time_var is not None else None, "values": {d.name: v.name for d, v in e.value_vars.items()}} for e in s.events]} for s in c.parsed_odes]


def _eq_latex(lhs, rhs, names) -> str:
    return f"{sp.latex(lhs, symbol_names=names)} = {sp.latex(rhs, symbol_names=names)}"


def get_calculation(calc_id: str) -> dict:
    try:
        c = default_catalog().get(calc_id)
    except KeyError as exc:
        raise ApiError(str(exc.args[0]), "NOT_FOUND", 404) from None
    return calculation_detail(c)


def calculation_detail(c: Calculation) -> dict:
    """The full description of a calculation as the editor and API show it (also used for generated math blocks)."""
    reg = default_registry()
    names = c.latex_names()
    out = _summary(c)
    out.update({
        "assumptions": c.assumptions, "references": c.references, "unverified_references": reference_status.notes_for(c.id, c.references), "example": c.example, "author": c.author,
        "validity": [m for _, m in c.validity], "default_roles": design.default_roles(c), "odes": _ode_info(c),
        "tables": [{"name": t["name"], "title": t.get("title", ""), "x_unit": t["x_unit"], "y_unit": t["y_unit"], "x": list(t["x"]), "y": list(t["y"]), "method": t.get("method", "linear")} for t in c.tables],
        "equations": [{"title": e.title, "text": e.text,
                       "latex": _eq_latex(*(e.written or (e.lhs, e.rhs)), names),
                       "evaluated": _eq_latex(e.lhs, e.rhs, names) if e.written else None} for e in c.parsed if e.ode is None],
        "variables": [{
            "key": v.key, "label": v.label, "latex": v.latex, "unit": v.unit, "si": v.si,
            "kind": v.kinds[0] if v.kinds else "dimensionless", "kinds": v.kinds,
            "default": v.default, "min": v.min, "max": v.max, "delta": v.delta, "signed": v.signed,
            "constant": v.constant, "note": v.note, "type": design.port_type(v),
            "units": v.units or [u["symbol"] for u in reg.units_for(v.dim, v.delta)],
        } for v in c.variables],
    })
    return out


def lists_get() -> dict:
    """The saved favorites, groups, recent calculations and Basic choice (``lists`` is None when nothing was saved yet; ``stored`` is false in the in-browser build, which has no disk)."""
    return userlists.get()


def lists_set(lists: dict) -> dict:
    """Save them. A copy older (by ``updated``) than the one already saved is not stored; the saved one is returned with ``kept_newer``."""
    try:
        return userlists.put(lists)
    except userlists.ListsError as exc:
        raise ApiError(str(exc), "BAD_REQUEST") from None


MAX_SWEEP = 200


@limited
def sweep(calc_id: str, inputs: dict, vary: str, values: Any, solve_for: Any = None, output_units: dict | None = None, sig_figs: int = 5) -> dict:
    """Solve the same calculation at several values of one input (given in the unit that input already has in ``inputs``).

    Returns the x values and, for every quantity solved for, its value at each point (``None`` where the calculation has no answer).
    """
    try:
        c = default_catalog().get(calc_id)
    except KeyError as exc:
        raise ApiError(str(exc.args[0]), "NOT_FOUND", 404) from None
    xs = []
    for v in (values if isinstance(values, (list, tuple)) else [values]):
        try:
            xs.append(float(v))
        except (TypeError, ValueError):
            raise ApiError(f"Sweep value {v!r} is not a number", "BAD_REQUEST") from None
    if not 2 <= len(xs) <= MAX_SWEEP:
        raise ApiError(f"A sweep needs between 2 and {MAX_SWEEP} points", "BAD_REQUEST")
    base = inputs or {}
    if vary not in base or not isinstance(base[vary], dict):
        raise ApiError(f"{vary!r} must be one of the inputs, with a value and a unit", "BAD_REQUEST")
    want = _as_list(solve_for) or None
    series: dict[str, dict] = {}
    failed = 0
    for n, x in enumerate(xs):
        sol = _solve(c, {**base, vary: {**base[vary], "value": x}}, want, output_units or {}, sig_figs, None, None).to_dict()
        if not sol["ok"]:
            failed += 1
        for o in sol["outputs"] if sol["ok"] else []:
            ser = series.setdefault(o["key"], {"key": o["key"], "label": o["label"], "latex": o["latex"], "unit": o.get("unit", ""), "y": [None] * len(xs)})
            ser["y"][n] = o["value"]
    return {"ok": bool(series), "calc_id": c.id, "vary": vary, "x": xs, "x_unit": base[vary].get("unit", ""), "series": list(series.values()), "failed": failed, "points": len(xs)}


@limited
def solve(calc_id: str, inputs: dict, solve_for: Any = None, output_units: dict | None = None, sig_figs: int = 5, ode_times: Any = None, search: dict | None = None) -> dict:
    try:
        c = default_catalog().get(calc_id)
    except KeyError as exc:
        raise ApiError(str(exc.args[0]), "NOT_FOUND", 404) from None
    return _solve(c, inputs or {}, _as_list(solve_for) or None, output_units or {}, sig_figs, _as_list(ode_times) or None, search or None).to_dict()


# ------------------------------------------------------------------ user-defined calculations

def _custom_error(exc: CustomError, status: int = 400) -> ApiError:
    err = ApiError("; ".join(f"{e['field']}: {e['message']}" for e in exc.errors), "INVALID_CALCULATION", status)
    err.details = exc.errors
    return err


def custom_validate(calculation: dict) -> dict:
    """Check a draft without saving it: errors per field, rendered equations, what can be solved for, example result.

    Running out of time is reported like any other problem with the draft (not as an API error), so the editor can show it."""
    default_catalog()
    try:
        with time_limit(settings.limit()):
            return _custom_validate(calculation)
    except TimeLimitExceeded as exc:
        return {"ok": False, "warnings": [], "errors": [{"field": "equations", "message":
                f"checking took longer than {exc.seconds:g} s and was stopped; simplify the equation or raise the time limit in Settings"}]}


def _custom_validate(calculation: dict) -> dict:
    try:
        c = calc_from_dict(calculation)
    except CustomError as exc:
        return {"ok": False, "errors": exc.errors, "warnings": []}
    names = c.latex_names()
    warnings: list[str] = []
    all_syms = {v.symbol for v in c.variables}
    solvable = []
    for v in c.variables:
        if v.is_constant:
            continue
        known = all_syms - {v.symbol}
        _s, _chk, known_after, _f = plan_structure(c, known, allow_numeric=True)
        if v.symbol in known_after:
            solvable.append(v.key)
    for o in c.outputs:
        if o not in solvable:
            warnings.append(f"{o} cannot be solved for from the other variables with these equations")
    example_result = None
    if c.example:
        ex_inputs = {k: val for k, val in c.example.items() if k not in c.outputs and not c.by_key[k].is_constant}
        if not ex_inputs:
            warnings.append("the example gives no input values")
        else:
            try:
                sol = _solve(c, ex_inputs, None, {}, 5).to_dict()
                bad = [d for d in sol.get("diagnostics", []) if d["level"] == "error"]
                example_result = {"outputs": [{"key": o["key"], "text": f"{o['value_text']} {o['unit']}".strip()} for o in sol.get("outputs", [])],
                                  "errors": [d["message"] for d in bad]}
                if bad:
                    warnings.append("the example does not solve: " + bad[0]["message"])
            except Exception as exc:  # noqa: BLE001 - surface anything the engine rejects
                warnings.append(f"the example does not solve: {exc}")
    else:
        warnings.append("no example values: add some to see a worked result immediately")
    return {"ok": True, "errors": [], "warnings": warnings, "id": c.id, "solvable_for": solvable,
            "equations": [{"title": e.title, "latex": _eq_latex(*(e.written or (e.lhs, e.rhs)), names),
                           "evaluated": _eq_latex(e.lhs, e.rhs, names) if e.written else None} for e in c.parsed if e.ode is None],
            "example_result": example_result, "odes": _ode_info(c), "calculation": calc_to_dict(c)}


@limited
def custom_save(calculation: dict, replace: bool = False) -> dict:
    try:
        doc = usercalcs.save(calculation, replace)
    except CustomError as exc:
        conflict = any(e["field"] == "id" and "already exists" in e["message"] for e in exc.errors)
        raise _custom_error(exc, 409 if conflict else 400) from None
    return {"ok": True, "id": doc["id"], "calculation": doc, "storage": usercalcs.storage()}


def custom_delete(calc_id: str) -> dict:
    if not usercalcs.remove(calc_id):
        raise ApiError(f"no user-defined calculation {calc_id!r}", "NOT_FOUND", 404)
    return {"ok": True}


def custom_list() -> dict:
    return {"calculations": usercalcs.listing(), "storage": usercalcs.storage()}


def custom_export(ids: Any = None) -> dict:
    """A shareable bundle (save the ``document`` as JSON)."""
    wanted = _as_list(ids) or None
    doc = usercalcs.export(wanted)
    stem = doc["calculations"][0]["id"].removeprefix("custom.") if len(doc["calculations"]) == 1 else "sliderule-equations"
    return {"document": doc, "filename": f"{stem}.sliderule.json", "count": len(doc["calculations"])}


@limited
def custom_import(document: Any, on_conflict: str = "rename", dry_run: bool = False) -> dict:
    """Import calculations from a parsed JSON document. ``on_conflict``: rename | replace | skip | ask."""
    if on_conflict not in ("rename", "replace", "skip", "ask"):
        raise ApiError("on_conflict must be rename, replace, skip or ask")
    try:
        rows = usercalcs.import_document(document, on_conflict, dry_run)
    except CustomError as exc:
        raise _custom_error(exc) from None
    return {"results": rows, "storage": usercalcs.storage(),
            "imported": sum(r["status"] in ("added", "replaced", "renamed") for r in rows)}


def custom_template(calc_id: str) -> dict:
    """A copy of any calculation (library or user-defined) as an editable draft."""
    try:
        c = default_catalog().get(calc_id)
    except KeyError as exc:
        raise ApiError(str(exc.args[0]), "NOT_FOUND", 404) from None
    doc = calc_to_dict(c)
    doc["name"] = f"Copy of {c.name}" if not c.custom else c.name
    doc["id"] = ""
    doc["author"] = ""
    return {"calculation": doc}


# ------------------------------------------------------------------ settings

def settings_get() -> dict:
    return settings.get()


def settings_set(timeout_enabled: Any = None, timeout_seconds: Any = None, acknowledge_risk: bool = False) -> dict:
    """Change the time limit. Switching it off requires ``acknowledge_risk`` (the reply to the warning is part of the API)."""
    try:
        return settings.update(timeout_enabled, timeout_seconds, bool(acknowledge_risk))
    except settings.SettingsError as exc:
        raise ApiError(str(exc), exc.code, 409 if exc.code == "WARNING_REQUIRED" else 400) from None


# ------------------------------------------------------------------ units

def kinds_catalog() -> dict:
    """Quantity kinds with pickable units, for the standalone converter."""
    reg = default_registry()
    seen: dict = {}
    for kind, si in reg._named_si:  # noqa: SLF001 - registry owns this table
        u = reg.parse(si)
        if u.dim in seen:
            continue
        seen[u.dim] = kind
    rows = []
    for dim, kind in seen.items():
        units = [r["symbol"] for r in reg.units_for(dim)]
        if len(units) > 1:
            rows.append({"kind": kind, "si": reg.si_symbol(dim), "units": units})
    rows.sort(key=lambda r: r["kind"])
    return {"kinds": rows}


def parse_unit_expr(expr: str, as_delta: bool = False) -> dict:
    reg = default_registry()
    try:
        u = reg.parse(expr, bool(as_delta))
    except UnitError as exc:
        return {"ok": False, "code": exc.code, "error": str(exc)}
    return {"ok": True, "symbol": u.symbol, "latex": unit_tex(u), "kind": reg.describe(u.dim), "dimension": str(u.dim),
            "factor_to_si": u.factor, "shift": u.shift, "systems": sorted(u.systems), "notes": list(u.notes),
            "si_unit": reg.si_symbol(u.dim)}


def convert(value: Any, from_unit: str, to_unit: str, sig_figs: int = 6) -> dict:
    """Convert and show the working."""
    reg = default_registry()
    try:
        x = float(value)
        a, b = reg.parse(from_unit), reg.parse(to_unit)
        if a.dim != b.dim:
            raise UnitError(f"cannot convert {a.symbol} ({reg.describe(a.dim)}) to {b.symbol} ({reg.describe(b.dim)})", "DIM_MISMATCH")
    except (UnitError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc), "code": getattr(exc, "code", "BAD_NUMBER")}
    si = a.to_si(x)
    y = b.from_si(si)
    sig = int(sig_figs)
    n = lambda v: fmt_number(v, sig)[1]  # noqa: E731
    si_u = reg.si_symbol(a.dim)
    si_tex = unit_tex(reg.parse(si_u, as_delta=True))
    lines = []
    if a.shift:
        lines.append(rf"{n(x)}\,{unit_tex(a)} \to \left({n(x)} + {fmt_number(a.shift, sig)[1]}\right)\times {n(a.factor)} = {n(si)}\,{si_tex}")
    elif not a.is_identity:
        lines.append(rf"{n(x)}\,{unit_tex(a)} \times \frac{{{n(a.factor)}\,{si_tex}}}{{1\,{unit_tex(a)}}} = {n(si)}\,{si_tex}")
    if b.shift:
        lines.append(rf"\frac{{{n(si)}\,{si_tex}}}{{{n(b.factor)}}} - {fmt_number(b.shift, sig)[1]} = {n(y)}\,{unit_tex(b)}")
    elif not b.is_identity:
        lines.append(rf"{n(si)}\,{si_tex} \times \frac{{1\,{unit_tex(b)}}}{{{n(b.factor)}\,{si_tex}}} = {n(y)}\,{unit_tex(b)}")
    if not lines:
        lines.append(rf"{n(x)}\,{unit_tex(a)} = {n(y)}\,{unit_tex(b)}")
    notes = [*a.notes, *b.notes]
    return {"ok": True, "value": y, "value_text": fmt_number(y, sig)[0], "unit": b.symbol, "si_value": si, "si_unit": si_u,
            "steps": lines, "notes": notes,
            "result_latex": rf"{n(x)}\,{unit_tex(a)} = {n(y)}\,{unit_tex(b)}"}


# ------------------------------------------------------------------ system design

@limited
def design_check_block(calc_id: str, roles: dict | None = None) -> dict:
    try:
        c = default_catalog().get(calc_id)
    except KeyError as exc:
        raise ApiError(str(exc.args[0]), "NOT_FOUND", 404) from None
    return design.check_block(c, roles)


@limited
def design_solve(graph: dict, sig_figs: int = 5) -> dict:
    return design.solve_system(graph or {}, sig_figs)


@limited
def design_validate(graph: dict) -> dict:
    errors = design.validate_graph(graph or {})
    return {"ok": not errors, "diagnostics": errors}


@limited
def design_export_document(graph: dict, format: str = "latex", mode: str = "both", sig_figs: int = 5, standalone: bool = True) -> dict:
    return design_export.export_system(graph or {}, format, mode, int(sig_figs), bool(standalone))


@limited
def design_to_equation(graph: dict, name: str = "", description: str = "", outputs: Any = None) -> dict:
    """Draft a "My equations" entry from a system (nothing is saved; save the returned ``calculation`` with ``custom_save``)."""
    return design_equation.system_to_equation(graph or {}, name, description, _as_list(outputs) or None)


@limited
def design_math(graph: dict) -> dict:
    return design.math_info(graph or {})


def design_examples() -> dict:
    return {"examples": design.examples()}


# ------------------------------------------------------------------ generic dispatcher

_METHODS: dict[str, Callable[..., dict]] = {
    "meta": meta, "data_packs": data_packs, "data_search": data_search, "data_record": data_record, "data_value": data_value, "data_options": data_options, "lists_get": lists_get, "lists_set": lists_set, "list_calculations": list_calculations, "get_calculation": get_calculation, "solve": solve, "sweep": sweep,
    "convert": convert, "parse_unit": parse_unit_expr, "kinds": kinds_catalog, "vocabulary": variable_vocabulary,
    "design_check_block": design_check_block, "design_solve": design_solve, "design_validate": design_validate,
    "design_examples": design_examples, "design_math": design_math, "design_to_equation": design_to_equation, "settings_get": settings_get, "settings_set": settings_set,
    "custom_validate": custom_validate, "custom_save": custom_save, "custom_delete": custom_delete, "custom_list": custom_list,
    "custom_export": custom_export, "custom_import": custom_import, "custom_template": custom_template, "design_export": design_export_document,
    "livecalc_eval": limited(livecalc.livecalc_eval), "livecalc_plot": limited(livecalc.livecalc_plot),
    "livecalc_functions": livecalc_help.functions_catalog, "livecalc_export": limited(livecalc.livecalc_export), "livecalc_library": limited(livecalc.livecalc_library), "livecalc_to_equation": limited(livecalc.livecalc_to_equation),
}


def handle(method: str, params: dict | None = None) -> dict:
    """Run an API method and wrap the outcome as ``{"ok": ..., "result" | "error": ...}``."""
    fn = _METHODS.get(method)
    if fn is None:
        return {"ok": False, "error": {"code": "NO_SUCH_METHOD", "message": f"unknown method {method!r}", "status": 404}}
    try:
        return {"ok": True, "result": fn(**(params or {}))}
    except ApiError as exc:
        err = {"code": exc.code, "message": exc.message, "status": exc.status}
        if getattr(exc, "details", None):
            err["details"] = exc.details
        return {"ok": False, "error": err}
    except TypeError as exc:
        return {"ok": False, "error": {"code": "BAD_PARAMS", "message": str(exc), "status": 400}}
    except Exception as exc:  # noqa: BLE001 - an engine fault must reach the page as a message, not as an unexplained HTTP 500
        logging.getLogger("sliderule").exception("unexpected error in %s", method)
        return {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": f"Something went wrong inside the engine while running {method} ({type(exc).__name__}: {exc}). "
                                                                           "Please report it with the inputs you used.", "status": 500}}


def handle_json(method: str, params_json: str = "{}") -> str:
    """String-in/string-out wrapper, convenient across the Pyodide boundary."""
    return json.dumps(handle(method, json.loads(params_json or "{}")))
