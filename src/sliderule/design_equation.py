"""Turn a System Design into a calculation of its own (a "My equations" entry).

The saved calculation is the *complete system of equations* of the graph, not a closed form: every equation each block needs, with
each wire collapsed into one shared variable (an input fed by a wire *is* the output that feeds it). The free inputs keep the values
typed on the canvas as their example; the chosen outputs are what the calculation solves for by default. Because all the equations
are kept, any variable of the saved calculation can still be solved for, it can be used as a block in another system, and every
export works as for any other equation.

A differential equation with a closed-form solution is saved as that solution. Not supported (reported, not silently dropped): numerically solved differential equations, events and data tables.
The validity limits of the blocks are carried over (written with the saved equation's variable names) when they only involve variables of the saved equation and the editor accepts them;
the others are listed in the assumptions.
"""

from __future__ import annotations

import keyword
import re
from types import SimpleNamespace

import sympy as sp

from .core import solve
from .core.custom import _RESERVED, KEY_RE, CustomError, _latex_ok, calc_from_dict
from .design import solve_system, validate_graph
from .design_code import closed_solution
from .design_export import system_model

DRAFT_ID = "custom.system_draft"


def _display(block: dict) -> str:
    return block["_calc"].name


def _validity_limits(blocks: dict, order: list, qsym: dict, to_final: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    """The validity limits of every block, renamed to the saved equation's variables; ``(limits, [(block, message) for those that cannot be carried])``."""
    out: list[dict] = []
    dropped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for bid in order:
        calc = blocks[bid]["_calc"]
        # straight to the saved equation's plain symbols: going through the block's positive symbols would let sympy decide the relation (a + b > 0 is True for positive a, b)
        local_to_final = {v.symbol: to_final[qsym[(bid, v.key)]] for v in calc.variables if qsym[(bid, v.key)] in to_final}
        for cond, message in calc.parsed_validity:
            if any(sym not in local_to_final for sym in cond.free_symbols):
                dropped.append((bid, message))                  # it involves a quantity the saved equation does not contain
                continue
            q = cond.xreplace(local_to_final)
            text = f"{sp.sstr(q.lhs)} != {sp.sstr(q.rhs)}" if isinstance(q, sp.Ne) else sp.sstr(q)
            if text in seen:
                continue
            seen.add(text)
            if len(text) > 200 or any(t in text for t in ("&", "|", "~")):
                dropped.append((bid, message))
                continue
            out.append({"condition": text, "message": f"{message} (block {bid}, {calc.name})"[:200]})
    return out[:30], dropped


def system_to_equation(graph: dict, name: str = "", description: str = "", outputs: list[str] | None = None) -> dict:
    """Return ``{"ok", "calculation", "candidates", "selected", "summary", "errors", "warnings"}`` without saving anything."""
    errors = [e["message"] for e in validate_graph(graph)]
    if errors:
        return {"ok": False, "errors": errors}
    result = solve_system(graph)
    if not result["ok"]:
        return {"ok": False, "errors": [f"{d['message']} (block {d['block']})" if d.get("block") else d["message"] for d in result["diagnostics"] if d["level"] == "error"]
                or ["the system cannot be evaluated, so it cannot be saved as an equation"]}
    model = system_model(graph)
    blocks, order, qsym = model["blocks"], model["order"], model["qsym"]
    if not order:
        return {"ok": False, "errors": ["the system has no blocks"]}

    # ---- the equations that take part, refusing anything that is not plain algebra
    problems: list[str] = []
    included: list[tuple[str, object]] = []          # (block id, (eq, lhs, rhs))
    for bid in order:
        b = blocks[bid]
        calc = b["_calc"]
        if calc.tables:
            problems.append(f"block {bid} ({calc.name}) uses a data table, which cannot be saved inside a system equation yet")
            continue
        if calc.parsed_odes and not all(closed_solution(o) for o in calc.parsed_odes):
            problems.append(f"block {bid} ({calc.name}) uses a differential equation that is solved numerically, which cannot be saved inside a system equation")
            continue
        local_to_q = {v.symbol: qsym[(bid, v.key)] for v in calc.variables}
        for o in calc.parsed_odes:                                # a differential equation with a closed-form solution is saved as that solution
            for dep, expr in closed_solution(o).items():
                if b["_roles"].get(dep.name) == "output":
                    included.append((bid, (SimpleNamespace(title=f"{o.title} (closed-form solution)", ode=None), dep.xreplace(local_to_q), expr.xreplace(local_to_q))))
        for (eq, lhs, rhs, needed) in model["equations"][bid]:
            if not needed or eq.ode is not None:
                continue
            if any(getattr(type(a), "_sliderule_ode", None) or hasattr(type(a), "_sliderule_table") for e in (lhs, rhs) for a in e.atoms(sp.Function)):
                problems.append(f"block {bid} ({calc.name}) uses a numerically solved or tabulated function")
                break
            included.append((bid, (eq, lhs, rhs)))
    if problems:
        return {"ok": False, "errors": problems}

    # ---- variables: wires merge two ports into one variable (the input becomes the output that feeds it)
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(n):
        while parent.get(n, n) != n:
            parent[n] = parent.get(parent[n], parent[n])
            n = parent[n]
        return n

    for w in graph.get("wires", []):
        src, dst = (w["from"]["block"], w["from"]["key"]), (w["to"]["block"], w["to"]["key"])
        parent[find(dst)] = find(src)
    by_symbol = {s: node for node, s in qsym.items()}
    used: list[tuple[str, str]] = []
    for _bid, (_eq, lhs, rhs) in included:
        for s in sorted((lhs.free_symbols | rhs.free_symbols), key=lambda x: x.name):
            node = by_symbol.get(s)
            if node is not None and node not in used:
                used.append(node)
    shared_const: dict[tuple[str, float], tuple[str, str]] = {}
    for node in used:                                         # the same physical constant in two blocks is one variable
        v = blocks[node[0]]["_calc"].by_key[node[1]]
        if v.constant is not None:
            first = shared_const.setdefault((v.key, v.constant), node)
            if first != node:
                parent[find(node)] = find(first)
    classes: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for node in used:
        classes.setdefault(find(node), []).append(node)

    names: dict[tuple[str, str], str] = {}
    taken: set[str] = set()
    for rep in classes:
        base = blocks[rep[0]]["_calc"].by_key[rep[1]].key
        cand = base if base not in taken else f"{base}_{rep[0]}"
        n = 2
        while cand in taken or not KEY_RE.match(cand) or keyword.iskeyword(cand) or cand in _RESERVED:
            cand = f"{base}_{rep[0]}_{n}" if n > 2 or cand != base else f"{base}_{rep[0]}"
            n += 1
        cand = cand[:24]
        taken.add(cand)
        names[rep] = cand
    to_final = {qsym[node]: sp.Symbol(names[find(node)]) for node in used}

    labels: dict[str, int] = {}
    variables: list[dict] = []
    for rep, members in classes.items():
        b = blocks[rep[0]]
        v = b["_calc"].by_key[rep[1]]
        role = b["_roles"][rep[1]]
        label = v.label
        labels[label] = labels.get(label, 0) + 1
        if labels[label] > 1:
            label = f"{v.label} ({_display(b)}, block {rep[0]})"
        spec: dict = {"key": names[rep], "label": label[:100], "unit": (b.get("out_units") or {}).get(rep[1]) if role == "output" and (b.get("out_units") or {}).get(rep[1]) else v.unit}
        if v.constant is not None:
            spec["constant"] = v.constant
        elif role != "output":
            text = (b.get("values") or {}).get(rep[1])
            if text in (None, ""):
                text = b["_calc"].example.get(rep[1]) or (f"{v.default} {v.unit}" if v.default is not None else "")
            if text:
                spec["example"] = str(text)[:60]
        for opt in ("min", "max"):
            if getattr(v, opt) is not None:
                spec[opt] = getattr(v, opt)
        if v.signed:
            spec["signed"] = True
        if v.delta:
            spec["delta"] = True
        if v.latex and _latex_ok(v.latex) and names[rep] == v.key:
            spec["latex"] = v.latex
        variables.append(spec)

    equations = []
    for bid, (eq, lhs, rhs) in included:
        text = f"{sp.sstr(lhs.xreplace(to_final), full_prec=False)} = {sp.sstr(rhs.xreplace(to_final), full_prec=False)}"
        equations.append({"title": f"{blocks[bid]['_calc'].name} ({bid}): {eq.title}"[:100], "text": text})

    # ---- outputs: what the saved equation solves for by default
    consumed = {(w["from"]["block"], w["from"]["key"]) for w in graph.get("wires", [])}
    candidates = []
    for node in used:
        b = blocks[node[0]]
        if b["_roles"][node[1]] == "output":
            v = b["_calc"].by_key[node[1]]
            candidates.append({"ref": f"{node[0]}.{node[1]}", "label": f"{v.label} ({_display(b)}, block {node[0]})", "key": names[find(node)], "final": node not in consumed})
    everything = [c["ref"] for c in candidates]
    chosen = [r for r in (outputs or everything) if r in set(everything)] or everything
    out_keys = list(dict.fromkeys(c["key"] for c in candidates if c["ref"] in chosen))
    if not out_keys:
        return {"ok": False, "errors": ["the system has no computed quantity to use as an output"]}
    for c in candidates:                       # a computed quantity left out of the outputs becomes an input: give it the value the system computes
        if c["ref"] not in chosen:
            bid, key = c["ref"].split(".", 1)
            o = next((o for o in result["blocks"][bid]["outputs"] if o["key"] == key), None)
            spec = next(v for v in variables if v["key"] == c["key"])
            if o is not None and "example" not in spec:
                spec["example"] = f"{o['value']!r} {o['unit']}"[:60]

    disciplines = list(dict.fromkeys(d for bid in order for d in blocks[bid]["_calc"].disciplines))
    block_names = list(dict.fromkeys(blocks[bid]["_calc"].name for bid in order))
    notes = [f"Assembled from a System Design of {len(order)} block(s): " + "; ".join(block_names[:6]) + ("; ..." if len(block_names) > 6 else "") + ".",
             ]
    notes += [f"Block {bid} ({blocks[bid]['_calc'].name}): {blocks[bid]['comment'].strip()}" for bid in order if (blocks[bid].get("comment") or "").strip()]
    validity, dropped = _validity_limits(blocks, order, qsym, to_final)
    notes += [f"Validity limit of block {bid} not carried over: {msg}" for bid, msg in dropped][:6]
    title = (name or "").strip() or ("System: " + " + ".join(block_names[:3]) + (" + ..." if len(block_names) > 3 else ""))
    draft = {"id": DRAFT_ID, "name": title[:120], "description": (description or "").strip()[:2000] or f"System of equations assembled in System Design from: {', '.join(block_names)[:300]}.",
             "disciplines": disciplines, "subdisciplines": [], "variables": variables, "equations": equations, "outputs": out_keys, "assumptions": notes[:12],
             "references": ["SlideRule System Design"], "validity": validity}
    # ---- check it now, so the dialog can show what is wrong before anything is saved
    warnings: list[str] = []
    for _attempt in range(2):
        try:
            calc = calc_from_dict(draft)
            break
        except CustomError as exc:
            bad = {int(m.group(1)) for e in exc.errors if (m := re.match(r"validity\[(\d+)\]", e["field"]))}
            if not bad and draft["validity"] and not _attempt and all(e["field"] == "equations" for e in exc.errors):
                bad = set(range(len(draft["validity"])))          # the editor reports a condition it cannot parse under "equations": drop the limits and try again
            if _attempt or not bad:
                return {"ok": False, "errors": [f"{e['field']}: {e['message']}" for e in exc.errors], "candidates": candidates}
            # a validity limit the editor does not accept is left out (and said so) rather than blocking the save
            draft["assumptions"] = [*draft["assumptions"], *(f"Validity limit not carried over: {draft['validity'][i]['message']}" for i in sorted(bad))][:12]
            draft["validity"] = [v for i, v in enumerate(draft["validity"]) if i not in bad]
    try:
        sol = solve(calc, dict(calc.example), solve_for=out_keys)
        if not sol.ok:
            warnings.append("with the typed values the saved equation does not solve: " + "; ".join(d.message for d in sol.diagnostics if d.level == "error")[:300])
        else:
            got = {o["key"]: o["si_value"] for o in sol.outputs}
            for c in candidates:
                if c["ref"] in chosen:
                    bid, key = c["ref"].split(".", 1)
                    ref = next((o["si_value"] for o in result["blocks"][bid]["outputs"] if o["key"] == key), None)
                    if ref is not None and c["key"] in got and abs(got[c["key"]] - ref) > 1e-6 * max(abs(ref), 1e-300):
                        warnings.append(f"{c['label']}: the saved equation gives {got[c['key']]:.6g} but the system gives {ref:.6g} (SI)")
    except Exception as exc:  # noqa: BLE001 - reported to the user as a warning, the draft is still returned
        warnings.append(f"could not test-solve the saved equation: {exc}")
    draft.pop("id")
    return {"ok": True, "calculation": draft, "candidates": candidates, "selected": chosen,
            "summary": {"variables": len(variables), "equations": len(equations), "blocks": len(order)}, "warnings": warnings}

