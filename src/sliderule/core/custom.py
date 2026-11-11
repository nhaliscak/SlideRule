"""User-defined calculations: JSON documents <-> :class:`Calculation`, with strict validation.

A document is a plain dict (so it can be typed in the editor, saved, shared as a file, or read from one):

    {"id": "custom.spring_rate", "name": "Spring rate", "description": "...", "disciplines": ["mechanical"],
     "subdisciplines": [], "tags": [], "author": "",
     "variables": [{"key": "k", "label": "Spring rate", "unit": "N/m", "latex": "k", "example": "2 kN/m"}, ...],
     "equations": [{"title": "Hooke's law", "text": "F = k*x"}],
     "outputs": ["F"], "assumptions": [], "references": [], "validity": [{"condition": "x > 0", "message": "..."}]}

Everything read from outside is validated before it is built: types and sizes, identifier rules, unit syntax,
the restricted expression grammar (:mod:`.safeparse`) and the same dimensional-homogeneity check the library
passes at registration. :func:`calc_from_dict` raises :class:`CustomError` carrying every problem found.
"""

from __future__ import annotations

import itertools
import keyword
import math
import re
from typing import Any

from .model import Calculation, Variable
from .safeparse import MAX_TEXT
from .taxonomy import DISCIPLINES, SUBDISCIPLINES, TAXONOMY

FORMAT_ONE = "sliderule-calculation"
FORMAT_MANY = "sliderule-calculations"
VERSION = 1

ID_RE = re.compile(r"^custom\.[a-z0-9_]{1,60}$")
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,23}$")
MAX_VARIABLES, MAX_EQUATIONS, MAX_LIST, MAX_CALCS = 40, 12, 30, 200
_RESERVED = {"None", "True", "False"}   # variables may shadow function names, as in the library (gamma, pi ...)


class CustomError(ValueError):
    """One or more validation problems; ``errors`` is a list of ``{"field": ..., "message": ...}``."""

    def __init__(self, errors: list[dict]):
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


class _Collector:
    def __init__(self) -> None:
        self.errors: list[dict] = []

    def add(self, field: str, message: str) -> None:
        self.errors.append({"field": field, "message": message})

    def raise_if_any(self) -> None:
        if self.errors:
            raise CustomError(self.errors)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (s or "equation")[:60]


def _str(d: dict, key: str, errs: _Collector, field: str, *, required=False, maxlen=200, default="") -> str:
    v = d.get(key, default)
    if v is None:
        v = default
    if not isinstance(v, str):
        errs.add(field, "must be text")
        return default
    v = v.strip()
    if required and not v:
        errs.add(field, "is required")
    if len(v) > maxlen:
        errs.add(field, f"is longer than {maxlen} characters")
        return v[:maxlen]
    return v


def _num(d: dict, key: str, errs: _Collector, field: str) -> float | None:
    v = d.get(key)
    if v is None or v == "":
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        try:
            v = float(str(v).strip())
        except ValueError:
            errs.add(field, "must be a number")
            return None
    if not math.isfinite(v):
        errs.add(field, "must be a finite number")
        return None
    return float(v)


def _strings(d: dict, key: str, errs: _Collector, maxlen: int = 300) -> list[str]:
    v = d.get(key) or []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        errs.add(key, "must be a list of text items")
        return []
    if len(v) > MAX_LIST:
        errs.add(key, f"has more than {MAX_LIST} items")
    out = [x.strip()[:maxlen] for x in v if x.strip()]
    return out[:MAX_LIST]


def calc_from_dict(d: Any) -> Calculation:
    """Validate and build a user-defined calculation (raises :class:`CustomError`)."""
    errs = _Collector()
    if not isinstance(d, dict):
        raise CustomError([{"field": "calculation", "message": "must be an object"}])
    cid = _str(d, "id", errs, "id", required=True, maxlen=80)
    if cid and not ID_RE.match(cid):
        errs.add("id", "must look like custom.my_equation (lower-case letters, digits and underscores)")
    name = _str(d, "name", errs, "name", required=True, maxlen=120)
    description = _str(d, "description", errs, "description", maxlen=2000)
    author = _str(d, "author", errs, "author", maxlen=80)

    disciplines = _strings(d, "disciplines", errs, 40)
    for x in disciplines:
        if x not in DISCIPLINES:
            errs.add("disciplines", f"unknown discipline {x!r}")
    subs = _strings(d, "subdisciplines", errs, 80)
    for x in subs:
        if x not in SUBDISCIPLINES:
            errs.add("subdisciplines", f"unknown sub-discipline {x!r}")
    disciplines = [x for x in disciplines if x in DISCIPLINES]
    subs = [x for x in subs if x in SUBDISCIPLINES]
    heading = {n: did for did, (n, _g, _s) in TAXONOMY.items()}
    for s in subs:
        owners = SUBDISCIPLINES[s]
        if not set(owners) & set(disciplines) and heading.get(s) not in disciplines:
            disciplines.append(owners[0])
    if not disciplines:
        errs.add("disciplines", "choose at least one discipline")
    tags = _strings(d, "tags", errs, 40)
    if "custom" not in tags:
        tags.append("custom")

    # ---- variables
    raw_vars = d.get("variables")
    variables: list[Variable] = []
    example: dict[str, str] = {}
    if not isinstance(raw_vars, list) or not raw_vars:
        errs.add("variables", "add at least one variable")
        raw_vars = []
    if len(raw_vars) > MAX_VARIABLES:
        errs.add("variables", f"more than {MAX_VARIABLES} variables")
        raw_vars = raw_vars[:MAX_VARIABLES]
    seen: set[str] = set()
    for i, rv in enumerate(raw_vars):
        f = f"variables[{i}]"
        if not isinstance(rv, dict):
            errs.add(f, "must be an object")
            continue
        key = _str(rv, "key", errs, f"{f}.key", required=True, maxlen=24)
        if key:
            if not KEY_RE.match(key) or keyword.iskeyword(key):
                errs.add(f"{f}.key", f"{key!r} is not a valid symbol (letters, digits, underscore; must start with a letter)")
            elif key in _RESERVED:
                errs.add(f"{f}.key", f"{key!r} is reserved")
            elif key in seen:
                errs.add(f"{f}.key", f"{key!r} is used twice")
            seen.add(key)
        label = _str(rv, "label", errs, f"{f}.label", required=True, maxlen=100)
        unit = _str(rv, "unit", errs, f"{f}.unit", maxlen=60, default="1") or "1"
        latex = _str(rv, "latex", errs, f"{f}.latex", maxlen=60) or None
        note = _str(rv, "note", errs, f"{f}.note", maxlen=300)
        kw: dict[str, Any] = {}
        for opt in ("default", "min", "max"):
            kw[opt] = _num(rv, opt, errs, f"{f}.{opt}")
        const = _num(rv, "constant", errs, f"{f}.constant")
        kw["delta"] = bool(rv.get("delta", False))
        kw["signed"] = bool(rv.get("signed", False))
        units = rv.get("units")
        if units is not None:
            if isinstance(units, list) and all(isinstance(u, str) for u in units) and len(units) <= 30:
                kw["units"] = [u.strip() for u in units if u.strip()] or None
            else:
                errs.add(f"{f}.units", "must be a list of unit names")
        if kw["min"] is not None and kw["max"] is not None and kw["min"] > kw["max"]:
            errs.add(f"{f}.min", "is larger than the maximum")
        if latex and not _latex_ok(latex):
            errs.add(f"{f}.latex", "contains characters that are not allowed in a symbol")
            latex = None
        shape = rv.get("shape")
        if shape is not None:
            if isinstance(shape, int) and not isinstance(shape, bool):
                shape = [shape]
            if (isinstance(shape, list) and 1 <= len(shape) <= 2 and all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 6 for n in shape)
                    and const is None):
                kw["shape"] = tuple(shape)
            else:
                errs.add(f"{f}.shape", "must be 1 to 6 (a vector) or [rows, columns], each 1 to 6; a vector or matrix cannot be a constant")
        ex = rv.get("example")
        if shape is not None and kw.get("shape") and isinstance(ex, list):
            for comp, val in zip((f"{key}_" + "_".join(map(str, i)) for i in itertools.product(*[range(1, n + 1) for n in kw["shape"]])), ex):
                if str(val).strip():
                    example[comp] = str(val).strip()[:60]
        elif ex not in (None, ""):
            example[key] = str(ex).strip()[:60]
        if not key or not label:
            continue
        v = Variable(key, label, unit, latex, constant=const, note=note, **kw)
        try:
            v.bind()
        except Exception as exc:  # unit text the registry cannot read, etc.
            errs.add(f"{f}.unit", str(exc))
            continue
        variables.append(v)

    odes = _odes(d, errs)
    tables = _tables(d, errs)
    functions = _functions(d, errs)

    # ---- equations
    raw_eqs = d.get("equations")
    equations: list[tuple[str, str]] = []
    if raw_eqs is None and odes:
        raw_eqs = []
    elif not isinstance(raw_eqs, list) or (not raw_eqs and not odes):
        errs.add("equations", "add at least one equation or differential equation")
        raw_eqs = []
    if len(raw_eqs) > MAX_EQUATIONS:
        errs.add("equations", f"more than {MAX_EQUATIONS} equations")
        raw_eqs = raw_eqs[:MAX_EQUATIONS]
    for i, re_ in enumerate(raw_eqs):
        f = f"equations[{i}]"
        if isinstance(re_, str):
            re_ = {"title": "", "text": re_}
        if not isinstance(re_, dict):
            errs.add(f, "must be an object with a title and text")
            continue
        text = _str(re_, "text", errs, f"{f}.text", required=True, maxlen=MAX_TEXT)
        title = _str(re_, "title", errs, f"{f}.title", maxlen=100) or (f"Equation {i + 1}" if len(raw_eqs) > 1 else "Governing equation")
        if text:
            equations.append((title, text))

    outputs = _strings(d, "outputs", errs, 40)
    keys = {v.key for v in variables}
    for v in variables:       # a vector or matrix also has component variables: v_1, v_2 ... / v_1_1 ...
        if v.shape:
            keys |= {f"{v.key}_" + "_".join(map(str, i)) for i in itertools.product(*[range(1, n + 1) for n in v.shape])}
    if len(keys) > MAX_VARIABLES * 4:
        errs.add("variables", f"more than {MAX_VARIABLES * 4} variables once vectors and matrices are expanded into components")
    for o in outputs:
        if o not in keys:
            errs.add("outputs", f"{o!r} is not one of the variables")
    consts = {v.key for v in variables if v.is_constant}
    outputs = [c for o in outputs for c in ([f"{o}_" + "_".join(map(str, i)) for i in itertools.product(*[range(1, n + 1) for n in next(v.shape for v in variables if v.key == o)])] if any(v.key == o and v.shape for v in variables) else [o])]
    if set(outputs) & consts:
        errs.add("outputs", "a constant cannot be an output")
    outputs = [o for o in outputs if o in keys and o not in consts]
    if not outputs and variables and not errs.errors:
        errs.add("outputs", "choose at least one quantity to solve for by default")

    validity: list[tuple[str, str]] = []
    rv = d.get("validity") or []
    if not isinstance(rv, list):
        errs.add("validity", "must be a list")
        rv = []
    for i, item in enumerate(rv[:MAX_LIST]):
        if isinstance(item, dict):
            cond = _str(item, "condition", errs, f"validity[{i}].condition", maxlen=MAX_TEXT)
            msg = _str(item, "message", errs, f"validity[{i}].message", maxlen=200)
        else:
            errs.add(f"validity[{i}]", "must be an object with a condition and message")
            continue
        if cond:
            validity.append((cond, msg or f"condition not satisfied: {cond}"))
    for k in example:
        if k not in keys:
            errs.add("example", f"refers to unknown variable {k!r}")
    assumptions, references = _strings(d, "assumptions", errs), _strings(d, "references", errs)
    errs.raise_if_any()

    try:
        return Calculation(
            id=cid, name=name, disciplines=disciplines, description=description, variables=variables, equations=equations,
            outputs=outputs, tags=tags, subdisciplines=subs, assumptions=assumptions,
            references=references, example=example, validity=validity, custom=True, author=author, odes=odes, tables=tables, functions=functions)
    except Exception as exc:  # parse errors, dimensional inconsistency, unused variables ...
        raise CustomError([{"field": _field_of(str(exc)), "message": _clean(str(exc), cid)}]) from None


def _odes(d: dict, errs: _Collector) -> list[dict]:
    raw = d.get("odes") or []
    if not isinstance(raw, list):
        errs.add("odes", "must be a list")
        return []
    if len(raw) > 4:
        errs.add("odes", "at most 4 differential-equation systems")
        raw = raw[:4]
    out = []
    for i, o in enumerate(raw):
        f = f"odes[{i}]"
        if not isinstance(o, dict):
            errs.add(f, "must be an object")
            continue
        eqs = o.get("equations")
        if isinstance(eqs, str):
            eqs = [eqs]
        init = o.get("initial") or []
        if isinstance(init, str):
            init = [x for x in (s.strip() for s in init.split("\n")) if x]
        if not isinstance(eqs, list) or not eqs or not all(isinstance(x, str) and x.strip() for x in eqs):
            errs.add(f"{f}.equations", "add at least one equation such as diff(y, t) = -k*y")
            continue
        if not isinstance(init, list) or not all(isinstance(x, str) for x in init):
            errs.add(f"{f}.initial", "must be a list of conditions such as y = y0")
            continue
        method = o.get("method") or "auto"
        if method not in ("auto", "numeric", "symbolic"):
            errs.add(f"{f}.method", "must be auto, numeric or symbolic")
            method = "auto"
        events = o.get("events") or []
        if not isinstance(events, list) or len(events) > 3 or not all(isinstance(e, dict) for e in events):
            errs.add(f"{f}.events", "must be a list of at most 3 events, each an object with a 'when' condition")
            events = []
        clean_events = [{"title": str(e.get("title") or "")[:80], "when": str(e.get("when") or "").strip()[:MAX_TEXT], "direction": e.get("direction") or "either",
                         "terminal": bool(e.get("terminal", False)), "time": (str(e["time"]).strip()[:24] if e.get("time") else None),
                         "values": {str(k)[:24]: str(v)[:24] for k, v in (e.get("values") or {}).items()} if isinstance(e.get("values") or {}, dict) else {},
                         "reset": {str(k)[:40]: str(v)[:MAX_TEXT] for k, v in (e.get("reset") or {}).items()} if isinstance(e.get("reset") or {}, dict) else {}} for e in events]
        extra: dict = {}
        if o.get("boundary"):
            bnd = o["boundary"]
            if isinstance(bnd, str):
                bnd = [x for x in (q.strip() for q in bnd.split("\n")) if x]
            if not isinstance(bnd, list) or not all(isinstance(x, str) for x in bnd) or len(bnd) > 12:
                errs.add(f"{f}.boundary", "must be a list of at most 12 conditions such as 'start: y = 0'")
                continue
            guess = o.get("guess") or []
            if isinstance(guess, str):
                guess = [x for x in (q.strip() for q in guess.split("\n")) if x]
            if not isinstance(guess, list) or not all(isinstance(x, str) for x in guess):
                errs.add(f"{f}.guess", "must be a list such as 'y = 300 K'")
                guess = []
            unk = o.get("unknowns") or []
            if isinstance(unk, str):
                unk = [x.strip() for x in unk.replace(",", "\n").split("\n") if x.strip()]
            if not isinstance(unk, list) or not all(isinstance(x, str) for x in unk) or len(unk) > 4:
                errs.add(f"{f}.unknowns", "must be a list of at most 4 variable names")
                unk = []
            extra = {**({"unknowns": [x.strip()[:24] for x in unk if x.strip()]} if unk else {}),
                     "end": (str(o.get("end") or "").strip() or "")[:60], "boundary": [x.strip()[:MAX_TEXT] for x in bnd if x.strip()],
                     **({"guess": [x.strip()[:MAX_TEXT] for x in guess if x.strip()][:12]} if guess else {})}
            if not extra["end"]:
                errs.add(f"{f}.end", "a boundary-value problem needs the end of the interval, e.g. L")
        if o.get("second"):
            extra["second"] = str(o["second"]).strip()[:24]
            extra["second_start"] = (str(o.get("second_start", "0")).strip() or "0")[:60]
            extra["second_end"] = str(o.get("second_end") or "").strip()[:60]
            extra["end"] = str(o.get("end") or "").strip()[:60]
            extra["boundary"] = [x.strip()[:MAX_TEXT] for x in (o.get("boundary") or []) if isinstance(x, str) and x.strip()][:24]
            if o.get("guess"):
                extra["guess"] = [str(x).strip()[:MAX_TEXT] for x in o["guess"] if str(x).strip()][:4] if isinstance(o["guess"], list) else []
            if o.get("nodes") not in (None, ""):
                try:
                    extra["nodes"] = int(o["nodes"])
                except (TypeError, ValueError):
                    errs.add(f"{f}.nodes", "must be a whole number of grid intervals")
        if o.get("second") and o.get("third"):
            extra["third"] = str(o["third"]).strip()[:24]
            extra["third_start"] = (str(o.get("third_start", "0")).strip() or "0")[:60]
            extra["third_end"] = str(o.get("third_end") or "").strip()[:60]
        cuts = o.get("cutouts") or []
        if cuts and o.get("second"):
            if not isinstance(cuts, list) or len(cuts) > 3 or not all(isinstance(c, dict) for c in cuts):
                errs.add(f"{f}.cutouts", "must be a list of at most 3 rectangles, each an object with x0, x1, y0, y1 and boundary")
            else:
                extra["cutouts"] = [{**{k: str(c.get(k, "")).strip()[:60] for k in ("x0", "x1", "y0", "y1") if str(c.get(k, "")).strip()},
                                     "boundary": [str(b).strip()[:MAX_TEXT] for b in (c.get("boundary") or []) if isinstance(b, str) and b.strip()][:16]} for c in cuts]
        if o.get("time"):
            extra["time"] = str(o["time"]).strip()[:24]
            extra.setdefault("end", str(o.get("end") or "").strip()[:60])
            mv = o.get("moving")
            if isinstance(mv, dict) and mv.get("front") and mv.get("rate"):
                extra["moving"] = {"front": str(mv["front"]).strip()[:24], "rate": str(mv["rate"]).strip()[:MAX_TEXT]}
            elif mv:
                errs.add(f"{f}.moving", "must be an object such as {\"front\": \"s\", \"rate\": \"-k*diff(T, x)/(rho*Lf)\"}")
            if o.get("scheme") == "conservative":
                extra["scheme"] = "conservative"
                dry = o.get("dry")
                if isinstance(dry, dict) and dry.get("depth"):
                    zero = dry.get("zero") or []
                    if isinstance(zero, str):
                        zero = [q.strip() for q in zero.replace(",", " ").split() if q.strip()]
                    extra["dry"] = {"depth": str(dry["depth"]).strip()[:24], "zero": [str(q).strip()[:24] for q in zero if str(q).strip()][:3],
                                    **({"tol": str(dry["tol"]).strip()[:20]} if dry.get("tol") not in (None, "") else {})}
                elif dry:
                    errs.add(f"{f}.dry", "must be an object such as {\"depth\": \"h\", \"zero\": [\"q\"], \"tol\": \"1e-6\"}")
            per = o.get("periodic") or []
            if isinstance(per, str):
                per = [q.strip() for q in per.replace(",", " ").split() if q.strip()]
            if isinstance(per, list) and per:
                extra["periodic"] = [str(q)[:24] for q in per[:3]]
            srcs = o.get("sources") or []
            if isinstance(srcs, list) and srcs:
                if len(srcs) > 6 or not all(isinstance(q, dict) for q in srcs):
                    errs.add(f"{f}.sources", "at most 6 sources, each an object with field, at and rate")
                else:
                    extra["sources"] = [{k: str(q.get(k))[:MAX_TEXT] for k in ("field", "at", "at_second", "at_third", "rate") if q.get(k) not in (None, "")} for q in srcs]
            if o.get("nodes") not in (None, ""):
                try:
                    extra["nodes"] = int(o["nodes"])
                except (TypeError, ValueError):
                    errs.add(f"{f}.nodes", "must be a whole number of grid intervals")
        out.append({"title": _str(o, "title", errs, f"{f}.title", maxlen=100) or "Differential equation", **extra,
                    **({"events": [{k: v for k, v in e.items() if v not in (None, "", {})} for e in clean_events]} if clean_events else {}),
                    "independent": _str(o, "independent", errs, f"{f}.independent", required=True, maxlen=24),
                    "start": (str(o.get("start", "0")).strip() or "0")[:60], "method": method,
                    **_sde_fields(o, f, errs),
                    **({"algebraic": [x.strip()[:24] for x in (o["algebraic"].split(",") if isinstance(o["algebraic"], str) else o["algebraic"]) if isinstance(x, str) and x.strip()][:24]} if o.get("algebraic") else {}),
                    "equations": [x.strip()[:MAX_TEXT] for x in eqs][:12], "initial": [x.strip()[:MAX_TEXT] for x in init if x.strip()][:12]})
    return out


def _field_of(message: str) -> str:
    if "differential equation" in message:
        return "odes"
    if "variables never used" in message or "unused" in message:
        return "variables"
    if "bad output" in message:
        return "outputs"
    return "equations"


def _clean(message: str, cid: str) -> str:
    return message.removeprefix(f"{cid}: ")


_LATEX_BAD = re.compile(r"\\(?:input|include|write|def|newcommand|href|url|includegraphics|catcode|read|openin|openout)|[$%&#]")


def _latex_ok(s: str) -> bool:
    return not _LATEX_BAD.search(s) and s.count("{") == s.count("}")


def _functions(d: dict, errs: _Collector) -> list[dict]:
    raw = d.get("functions")
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        errs.add("functions", "must be a list")
        return []
    if len(raw) > 8:
        errs.add("functions", "at most 8 functions")
        raw = raw[:8]
    out = []
    for i, fdef in enumerate(raw):
        f = f"functions[{i}]"
        if not isinstance(fdef, dict):
            errs.add(f, "must be an object")
            continue
        name = _str(fdef, "name", errs, f"{f}.name", required=True, maxlen=24)
        body = _str(fdef, "body", errs, f"{f}.body", required=True, maxlen=MAX_TEXT)
        args = fdef.get("args")
        if isinstance(args, str):
            args = [a.strip() for a in args.split(",") if a.strip()]
        if not isinstance(args, list) or not 1 <= len(args) <= 4 or not all(isinstance(a, str) and KEY_RE.match(a) for a in args):
            errs.add(f"{f}.args", "give 1 to 4 argument names such as [\"Re\", \"rel\"]")
            continue
        if name and (not KEY_RE.match(name) or keyword.iskeyword(name) or name in _RESERVED):
            errs.add(f"{f}.name", f"{name!r} is not a valid function name")
            continue
        if name and body:
            out.append({"name": name, "args": list(args), "body": body})
    return out


def _tables(d: dict, errs: _Collector) -> list[dict]:
    from . import tables as T

    raw = d.get("tables")
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        errs.add("tables", "must be a list")
        return []
    if len(raw) > 6:
        errs.add("tables", "at most 6 tables")
        raw = raw[:6]
    out, names = [], set()
    for i, t in enumerate(raw):
        f = f"tables[{i}]"
        if not isinstance(t, dict):
            errs.add(f, "must be an object")
            continue
        name = _str(t, "name", errs, f"{f}.name", required=True, maxlen=24)
        if name and (not KEY_RE.match(name) or keyword.iskeyword(name) or name in _RESERVED or name in names):
            errs.add(f"{f}.name", f"{name!r} is not a valid, unused function name")
        names.add(name)
        item = {"name": name, "x_unit": _str(t, "x_unit", errs, f"{f}.x_unit", maxlen=60) or "1", "y_unit": _str(t, "y_unit", errs, f"{f}.y_unit", maxlen=60) or "1",
                "x": t.get("x"), "y": t.get("y"), "method": t.get("method") or "linear", "outside": t.get("outside") or "error"}
        title = _str(t, "title", errs, f"{f}.title", maxlen=100)
        if title:
            item["title"] = title
        try:
            item["x"], item["y"] = T.check_data(item["x"], item["y"], item["method"], item["outside"])
        except T.TableError as exc:
            errs.add(f, str(exc))
            continue
        out.append(item)
    return out


def _sde_fields(o: dict, f: str, errs: _Collector) -> dict:
    """The extra entries of a stochastic differential equation: statistics to report, number of paths and steps, seed."""
    out: dict = {}
    st = o.get("statistics")
    if st:
        if not isinstance(st, list) or len(st) > 12 or not all(isinstance(q, dict) for q in st):
            errs.add(f"{f}.statistics", "must be a list of at most 12 objects such as {\"of\": \"x\", \"kind\": \"mean\", \"var\": \"xm\"}")
        else:
            out["statistics"] = [{k: str(q[k]).strip()[:MAX_TEXT] for k in ("of", "event", "kind", "var", "level", "p") if q.get(k) not in (None, "")} for q in st]
    for k in ("paths", "steps", "seed"):
        if o.get(k) not in (None, ""):
            try:
                out[k] = int(o[k])
            except (TypeError, ValueError):
                errs.add(f"{f}.{k}", "must be a whole number")
    return out


def _written_equations(c: Calculation) -> list[dict]:
    """The equations as the author wrote them: one entry per source equation, however many scalar equations it became."""
    out, seen = [], set()
    for e in c.parsed:
        if e.ode is not None:
            continue
        key = (e.source or e.title, e.text)
        if e.source and key in seen:
            continue
        seen.add(key)
        out.append({"title": e.source or e.title, "text": e.text})
    return out


def calc_to_dict(c: Calculation) -> dict:
    """The canonical, shareable document for a calculation (library or user-defined)."""
    variables = []
    for v in getattr(c, "declared", None) or c.variables:
        item: dict[str, Any] = {"key": v.key, "label": v.label, "unit": v.unit}
        if v.shape:
            item["shape"] = list(v.shape)
        if v.latex and v.latex != v.key:
            item["latex"] = v.latex
        for k in ("default", "min", "max", "constant"):
            if getattr(v, k) is not None:
                item[k] = getattr(v, k)
        if v.delta:
            item["delta"] = True
        if v.signed:
            item["signed"] = True
        if v.note:
            item["note"] = v.note
        if v.units:
            item["units"] = list(v.units)
        if v.shape:
            comps = [f"{v.key}_" + "_".join(map(str, i)) for i in itertools.product(*[range(1, n + 1) for n in v.shape])]
            if all(k in c.example for k in comps):
                item["example"] = [c.example[k] for k in comps]
        elif v.key in c.example:
            item["example"] = c.example[v.key]
        variables.append(item)
    return {
        "id": c.id, "name": c.name, "description": c.description, "author": c.author,
        "disciplines": list(c.disciplines), "subdisciplines": list(c.subdisciplines),
        "tags": [t for t in c.tags if t != "custom"],
        "variables": variables,
        "equations": _written_equations(c),
        "outputs": list(c.outputs), "assumptions": list(c.assumptions), "references": list(c.references),
        "validity": [{"condition": cond, "message": m} for (cond, m) in c.validity],
        **({"odes": [dict(o) for o in c.odes]} if c.odes else {}),
        **({"tables": [dict(t) for t in c.tables]} if c.tables else {}),
        **({"functions": [dict(f) for f in c.functions]} if c.functions else {}),
    }


def make_document(calcs: list[dict]) -> dict:
    """Wrap calculation dicts for saving or sharing (always the bundle form)."""
    return {"format": FORMAT_MANY, "version": VERSION, "calculations": calcs}


def parse_document(obj: Any) -> list[dict]:
    """Accept a single-calculation file, a bundle, or a bare calculation dict; return the calculation dicts."""
    if not isinstance(obj, dict):
        raise CustomError([{"field": "file", "message": "not a SlideRule calculation file"}])
    fmt = obj.get("format")
    if fmt is not None and fmt not in (FORMAT_ONE, FORMAT_MANY):
        raise CustomError([{"field": "format", "message": f"unknown format {fmt!r}"}])
    ver = obj.get("version", VERSION)
    if not isinstance(ver, int) or ver > VERSION:
        raise CustomError([{"field": "version", "message": f"file version {ver!r} is newer than this SlideRule understands"}])
    if fmt == FORMAT_MANY or "calculations" in obj:
        items = obj.get("calculations")
    elif fmt == FORMAT_ONE or "calculation" in obj:
        items = [obj.get("calculation")]
    else:
        items = [obj]
    if not isinstance(items, list) or not items:
        raise CustomError([{"field": "file", "message": "contains no calculations"}])
    if len(items) > MAX_CALCS:
        raise CustomError([{"field": "file", "message": f"contains more than {MAX_CALCS} calculations"}])
    return items
