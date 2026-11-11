"""System design: calculation blocks wired together into a dataflow graph.

A *block* is one calculation in which every variable has a **role**:

``input``     a value that arrives on a wire, or is typed in when nothing is wired to it
``output``    a quantity the block computes (the engine rearranges the equations to find it)
``constant``  a value fixed inside the block (physical constants are locked constants)

A *wire* runs from one block's output to another block's input. It is only legal when both ends have the same
physical *type* (dimension; absolute temperature and temperature difference are different types), the source is
an output, the target is an input with no other wire, the blocks differ, and the wire does not close a loop.

Everything here is plain data in / plain data out so it can run in the server or in the browser (Pyodide).
"""

from __future__ import annotations

import sympy as sp

from .core import Calculation, Variable
from .core import solve as solve_calculation
from .core.catalog import default_catalog
from .core.engine import parse_quantity, plan_structure, prune_plan
from .design_math import OPS as MATH_OPS
from .design_math import is_math, math_calculation, resolve_types, type_dict
from .units import default_registry

ROLES = ("input", "output", "constant")
MAX_COMMENT = 2000                     # characters in a block's free-text comment


# ------------------------------------------------------------------ types

def port_type(v: Variable) -> dict:
    """The 'data type' of a variable: its physical dimension (plus whether it is a temperature *difference*)."""
    reg = default_registry()
    key = str(v.dim) + ("~delta" if v.delta else "")
    kind = "temperature difference" if v.delta else reg.describe(v.dim)
    return {"key": key, "kind": kind, "si": v.si}


def default_roles(calc: Calculation) -> dict[str, str]:
    return {v.key: ("constant" if v.is_constant else "output" if v.key in calc.outputs else "input") for v in calc.variables}


def hidden_keys(calc: Calculation) -> set[str]:
    """Variables internal to a differential-equation system (the random unknowns of a stochastic equation, eliminated algebraic variables): they take no value and give none."""
    return {s.name for system in calc.parsed_odes for s in getattr(system, "hidden", ())}


def _roles(calc: Calculation, roles: dict | None) -> dict[str, str]:
    out = default_roles(calc)
    out.update({k: r for k, r in (roles or {}).items() if k in out})
    for k in hidden_keys(calc):
        if out.get(k) == "output":
            out[k] = "input"                      # nothing is computed for an internal variable
    return out


def wire_problem(src_calc: Calculation, src_key: str, dst_calc: Calculation, dst_key: str) -> str | None:
    """Why a wire between two ports is illegal on *type* grounds (``None`` if it is fine)."""
    a, b = src_calc.by_key.get(src_key), dst_calc.by_key.get(dst_key)
    if a is None or b is None:
        return "unknown variable"
    ta, tb = port_type(a), port_type(b)
    if ta["key"] != tb["key"]:
        return f"{a.label} is {ta['kind']} [{ta['si']}] but {b.label} expects {tb['kind']} [{tb['si']}]"
    return None


# ------------------------------------------------------------------ one block

def check_block(calc: Calculation, roles: dict | None = None) -> dict:
    """Can this role assignment be solved? Returns ``{ok, errors, warnings}`` without needing any numbers."""
    r = _roles(calc, roles)
    errors: list[str] = []
    warnings: list[str] = []
    for k, role in (roles or {}).items():
        if k not in calc.by_key:
            errors.append(f"unknown variable {k!r}")
        elif role not in ROLES:
            errors.append(f"{k}: role must be one of {', '.join(ROLES)}")
    for v in calc.variables:
        if v.is_constant and r[v.key] != "constant":
            errors.append(f"{v.label} ({v.key}) is a physical constant and must stay a constant")
    outputs = [k for k, role in r.items() if role == "output"]
    if not outputs:
        errors.append("choose at least one output")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    known = {calc.by_key[k].symbol for k, role in r.items() if role != "output"}
    solved, checks, _known, failures = plan_structure(calc, known, allow_numeric=True)
    solved_names = {it.sym.name for it in solved}
    for t in outputs:
        if t in solved_names:
            continue
        label = calc.by_key[t].label
        if calc.by_key[t].symbol in failures:
            errors.append(f"cannot rearrange the equations to compute {label} ({t})")
            continue
        blockers = sorted({u.name for eq in calc.parsed if calc.by_key[t].symbol in eq.symbols for u in eq.symbols
                           if u not in _known and u.name != t})
        if blockers:
            errors.append(f"{label} ({t}) cannot be computed: {', '.join(blockers)} would also have to be inputs or constants "
                          "(or be outputs that the other equations can determine)")
        else:
            errors.append(f"{label} ({t}) is coupled with other unknowns in a way that cannot be solved: the equations do not form a square system, or no solution exists in the allowed ranges")
    if not errors:
        needed = prune_plan(solved, outputs)
        used: set[sp.Symbol] = set()
        for it in needed:
            used |= it.eq.symbols
        for k, role in r.items():
            if role == "input" and calc.by_key[k].symbol not in used:
                warnings.append(f"{calc.by_key[k].label} ({k}) is not needed to compute the chosen outputs")
        if checks:
            warnings.append("some equations are over-specified by the chosen inputs; values that disagree will be reported")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


# ------------------------------------------------------------------ the graph

def _index(graph: dict, errors: list[dict]):
    cat = default_catalog()
    blocks: dict[str, dict] = {}
    types = None
    for b in graph.get("blocks", []):
        bid = b.get("id")
        if not bid or bid in blocks:
            errors.append({"level": "error", "code": "BAD_BLOCK", "message": f"duplicate or missing block id {bid!r}", "block": bid})
            continue
        if not isinstance(b.get("comment", ""), str) or len(b.get("comment", "")) > MAX_COMMENT:
            errors.append({"level": "error", "code": "BAD_BLOCK", "message": f"the comment on block {bid} must be text of at most {MAX_COMMENT} characters", "block": bid})
            continue
        if is_math(b):
            if b.get("op") not in MATH_OPS:
                errors.append({"level": "error", "code": "UNKNOWN_CALC", "message": f"unknown math operation {b.get('op')!r}", "block": bid})
                continue
            types = types if types is not None else resolve_types(graph)[0]
            calc = math_calculation(b, types)
            blocks[bid] = {**b, "_calc": calc, "_roles": _roles(calc, None)}
            continue
        try:
            calc = cat.get(b.get("calc", ""))
        except KeyError:
            errors.append({"level": "error", "code": "UNKNOWN_CALC", "message": f"unknown calculation {b.get('calc')!r}", "block": bid})
            continue
        blocks[bid] = {**b, "_calc": calc, "_roles": _roles(calc, b.get("roles"))}
    return blocks


def validate_graph(graph: dict) -> list[dict]:
    """Structural problems: ports, roles, types, single driver per input, no self-loops, no cycles."""
    errors: list[dict] = []
    blocks = _index(graph, errors)

    def err(code: str, msg: str, wire: dict | None = None, block: str | None = None) -> None:
        errors.append({"level": "error", "code": code, "message": msg, "block": block, "wire": (wire or {}).get("id")})

    driven: dict[tuple[str, str], dict] = {}
    edges: dict[str, set[str]] = {bid: set() for bid in blocks}
    for w in graph.get("wires", []):
        src, dst = w.get("from", {}), w.get("to", {})
        sb, db = blocks.get(src.get("block")), blocks.get(dst.get("block"))
        if sb is None or db is None:
            err("BAD_WIRE", "wire refers to a block that does not exist", w)
            continue
        if src["block"] == dst["block"]:
            err("SELF_LOOP", "a block cannot feed itself", w, src["block"])
            continue
        sk, dk = src.get("key"), dst.get("key")
        if sb["_roles"].get(sk) != "output":
            err("NOT_AN_OUTPUT", f"{sk} is not an output of its block", w, src["block"])
            continue
        if db["_roles"].get(dk) != "input":
            err("NOT_AN_INPUT", f"{dk} is not an input of its block", w, dst["block"])
            continue
        problem = wire_problem(sb["_calc"], sk, db["_calc"], dk)
        if problem:
            err("TYPE_MISMATCH", problem, w, dst["block"])
            continue
        if (dst["block"], dk) in driven:
            err("MULTIPLE_DRIVERS", f"input {dk} already has a wire", w, dst["block"])
            continue
        driven[(dst["block"], dk)] = w
        edges[src["block"]].add(dst["block"])
    if not errors and _topological_order(list(blocks), edges) is None:
        errors.append({"level": "error", "code": "CYCLE", "message": "the wires form a loop (algebraic loops are not supported)", "block": None, "wire": None})
    return errors


def _topological_order(ids: list[str], edges: dict[str, set[str]]) -> list[str] | None:
    indeg = {i: 0 for i in ids}
    for a in ids:
        for b in edges.get(a, ()):
            indeg[b] += 1
    ready = [i for i in ids if indeg[i] == 0]
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for b in sorted(edges.get(n, ()), key=ids.index):
            indeg[b] -= 1
            if indeg[b] == 0:
                ready.append(b)
    return order if len(order) == len(ids) else None


def solve_system(graph: dict, sig_figs: int = 5) -> dict:
    """Evaluate every block in dependency order, passing wired values (in SI) downstream."""
    errors = validate_graph(graph)
    if errors:
        return {"ok": False, "order": [], "blocks": {}, "diagnostics": errors}
    errs: list[dict] = []
    blocks = _index(graph, errs)
    edges: dict[str, set[str]] = {bid: set() for bid in blocks}
    drivers: dict[tuple[str, str], tuple[str, str]] = {}
    for w in graph.get("wires", []):
        s, d = w["from"], w["to"]
        edges[s["block"]].add(d["block"])
        drivers[(d["block"], d["key"])] = (s["block"], s["key"])
    order = _topological_order(list(blocks), edges) or []
    results: dict[str, dict] = {}
    produced: dict[tuple[str, str], tuple[float, str]] = {}
    diagnostics: list[dict] = []
    failed: set[str] = set()

    def diag(level: str, code: str, msg: str, bid: str) -> None:
        diagnostics.append({"level": level, "code": code, "message": msg, "block": bid, "wire": None})

    for bid in order:
        b = blocks[bid]
        calc, roles = b["_calc"], b["_roles"]
        check = check_block(calc, roles)
        if not check["ok"]:
            for m in check["errors"]:
                diag("error", "ROLES", m, bid)
            failed.add(bid)
            continue
        inputs: dict[str, dict] = {}
        problem = False
        for v in calc.variables:
            role = roles[v.key]
            if v.is_constant or role == "output":
                continue
            src = drivers.get((bid, v.key))
            if src is not None:
                if src[0] in failed or src not in produced:
                    diag("error", "UPSTREAM_FAILED", f"{v.label} ({v.key}) depends on a block that could not be solved", bid)
                    problem = True
                    continue
                si_value, _unit = produced[src]
                inputs[v.key] = {"value": si_value, "unit": v.si}
                continue
            text = (b.get("values") or {}).get(v.key)
            if text is None or str(text).strip() == "":
                if v.key in hidden_keys(calc):
                    continue
                if v.default is None:
                    diag("error", "MISSING_VALUE", f"{v.label} ({v.key}) has no wire and no value", bid)
                    problem = True
                    continue
                text = f"{v.default} {v.unit}"
            try:
                val, unit = parse_quantity(str(text))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user as a diagnostic
                diag("error", "BAD_VALUE", f"{v.label} ({v.key}): {exc}", bid)
                problem = True
                continue
            inputs[v.key] = {"value": val, "unit": unit or v.unit}
        if problem:
            failed.add(bid)
            continue
        outputs = [k for k, role in roles.items() if role == "output"]
        sol = solve_calculation(calc, inputs, solve_for=outputs, output_units=b.get("out_units") or {}, sig_figs=sig_figs)
        results[bid] = sol.to_dict()
        for d in sol.diagnostics:
            if d.level != "info":
                diag(d.level, d.code, d.message, bid)
        if not sol.ok:
            failed.add(bid)
            continue
        for o in sol.outputs:
            produced[(bid, o["key"])] = (o["si_value"], o["si_unit"])
    return {"ok": not failed, "order": order, "blocks": results, "diagnostics": diagnostics}


# ------------------------------------------------------------------ examples

EXAMPLES: list[dict] = [
    {
        "id": "wind_to_hydrogen", "name": "Wind turbine → hydrogen electrolyzer",
        "description": "Electrical power from a turbine feeds an electrolyzer; the wire converts kW to MW automatically.",
        "graph": {
            "version": 1,
            "blocks": [
                {"id": "b1", "calc": "energy.wind.turbine_power", "x": 40, "y": 40,
                 "values": {"rho": "1.225 kg/m^3", "Dr": "100 m", "v": "10 m/s", "Cp": "0.45", "eg": "94 %", "CF": "35 %", "Pr": "3000 kW"}},
                {"id": "b2", "calc": "energy.hydrogen.electrolyzer", "x": 520, "y": 60, "values": {"eta": "70 %", "t": "24 h"}},
            ],
            "wires": [{"id": "w1", "from": {"block": "b1", "key": "Pe"}, "to": {"block": "b2", "key": "P"}}],
        },
    },
    {
        "id": "altitude_to_lift", "name": "Altitude → air density → lift and drag",
        "description": "The standard atmosphere supplies air density to a wing; try changing the altitude.",
        "graph": {
            "version": 1,
            "blocks": [
                {"id": "b1", "calc": "aerospace.atmosphere.isa_troposphere", "x": 40, "y": 40, "values": {"h": "3000 m"}},
                {"id": "b2", "calc": "aerospace.aerodynamics.lift_drag", "x": 520, "y": 40,
                 "values": {"v": "60 m/s", "S": "16.2 m^2", "CL": "0.5", "CD": "0.03"}},
            ],
            "wires": [{"id": "w1", "from": {"block": "b1", "key": "rho"}, "to": {"block": "b2", "key": "rho"}}],
        },
    },
]


def examples() -> list[dict]:
    return EXAMPLES


# ------------------------------------------------------------------ math blocks for the editor

def math_info(graph: dict) -> dict:
    """For every math block: whether its type is locked, the type of each port (``None`` = still open) and the block's definition
    in the same shape as ``get_calculation`` (so the editor can draw it like any other block)."""
    from .api import calculation_detail

    types, locked = resolve_types(graph)
    out: dict[str, dict] = {}
    for b in graph.get("blocks", []):
        if not is_math(b) or b.get("op") not in MATH_OPS:
            continue
        calc = math_calculation(b, types)
        keys = [v.key for v in calc.variables]
        out[b["id"]] = {"locked": b["id"] in locked, "types": {k: type_dict(types.get((b["id"], k))) for k in keys},
                        "detail": calculation_detail(calc), "symbol": MATH_OPS[b["op"]]["symbol"]}
    return {"blocks": out}
