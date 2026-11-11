"""Math blocks for System Design: add, subtract, multiply and divide wired between calculation blocks.

A math block is not a separate kind of evaluation: :func:`math_calculation` turns it into an ordinary
:class:`~sliderule.core.Calculation` (``y = x1 + x2`` ...) whose variables carry the right units, so the dimension
check, solving, worked steps, wire rules and every export format treat it like any other block.

What differs is how the *types* of its ports are decided (:func:`resolve_types`):

``add`` / ``subtract``
    every port has one type, **locked to the first wire connected to the block** (the earliest in the graph's wire
    list, on either side). With no wire connected the lock is released and the block accepts anything again.
``multiply`` / ``divide``
    the inputs take the type of whatever feeds them (or of the unit typed with a value) and the output type is the
    product (or quotient) of the input dimensions, so units combine and cancel: N x m is J, m / s is velocity,
    N / N is dimensionless.
"""

from __future__ import annotations

from .core import Calculation, V
from .core.engine import parse_quantity
from .units import default_registry
from .units.dimension import Dimension

MAX_INPUTS = 8
OPS: dict[str, dict] = {
    "add": {"name": "Add", "symbol": "+", "variadic": True, "lock": True, "terms": "Term", "result": "Sum",
            "description": "Adds its inputs. All ports take the type of the first wire connected to the block."},
    "sub": {"name": "Subtract", "symbol": "−", "variadic": False, "lock": True, "terms": ("Minuend", "Subtrahend"), "result": "Difference",
            "description": "Subtracts the second input from the first. All ports take the type of the first wire connected to the block."},
    "mul": {"name": "Multiply", "symbol": "×", "variadic": True, "lock": False, "terms": "Factor", "result": "Product",
            "description": "Multiplies its inputs; the units multiply too (N · m = J) and cancel where they can."},
    "div": {"name": "Divide", "symbol": "÷", "variadic": False, "lock": False, "terms": ("Numerator", "Denominator"), "result": "Quotient",
            "description": "Divides the first input by the second; the units divide too (m / s = velocity, N / N = dimensionless)."},
}

Type = tuple[Dimension, bool]        # (physical dimension, is a temperature difference)


def is_math(block: dict) -> bool:
    return block.get("kind") == "math"


def op_of(block: dict) -> str | None:
    return block.get("op") if block.get("op") in OPS else None


def input_keys(block: dict) -> list[str]:
    spec = OPS[block["op"]]
    if not spec["variadic"]:
        return ["x1", "x2"]
    try:
        n = int(block.get("n") or 2)
    except (TypeError, ValueError):
        n = 2
    return [f"x{i + 1}" for i in range(max(2, min(MAX_INPUTS, n)))]


def type_dict(t: Type | None) -> dict | None:
    """The wire-type description the editor and :func:`~sliderule.design.port_type` use (``None`` while unset)."""
    if t is None:
        return None
    reg = default_registry()
    dim, delta = t
    return {"key": str(dim) + ("~delta" if delta else ""), "kind": "temperature difference" if delta else reg.describe(dim), "si": reg.si_symbol(dim)}


def _value_type(text) -> Type | None:
    """The type implied by a typed value such as ``'5 kN'`` (``None`` when there is none or it cannot be read)."""
    if text is None or str(text).strip() == "":
        return None
    try:
        _val, unit = parse_quantity(str(text))
        return default_registry().parse(unit or "1").dim, False
    except Exception:  # noqa: BLE001 - reported later, when the block is solved
        return None


def resolve_types(graph: dict) -> tuple[dict[tuple[str, str], Type | None], set[str]]:
    """Types of every port of every math block, and the ids of the add/subtract blocks that are locked.

    ``None`` means "not decided yet". A lock comes from the first wire (in the graph's wire order) whose far end already
    has a type; ties between chained math blocks are settled by iterating until nothing changes.
    """
    from .core.catalog import default_catalog

    blocks = {b.get("id"): b for b in graph.get("blocks", []) if b.get("id")}
    maths = {bid: b for bid, b in blocks.items() if is_math(b) and op_of(b)}
    calcs = {}
    cat = default_catalog()
    for bid, b in blocks.items():
        if bid not in maths and b.get("calc"):
            try:
                calcs[bid] = cat.get(b["calc"])
            except KeyError:
                pass
    wires = [w for w in graph.get("wires", []) if isinstance(w.get("from"), dict) and isinstance(w.get("to"), dict)]
    driver = {(w["to"].get("block"), w["to"].get("key")): (w["from"].get("block"), w["from"].get("key")) for w in wires}
    P: dict[tuple[str, str], Type | None] = {(bid, k): None for bid, b in maths.items() for k in [*input_keys(b), "y"]}
    locked: dict[str, Type] = {}

    def typ(end) -> Type | None:
        bid, key = end
        if bid in maths:
            return P.get((bid, key))
        calc = calcs.get(bid)
        v = calc.by_key.get(key) if calc else None
        return (v.dim, v.delta) if v is not None else None

    for _ in range(4 * len(maths) + 4):
        changed = False
        for bid, b in maths.items():
            keys = [*input_keys(b), "y"]
            if OPS[b["op"]]["lock"]:
                if bid in locked:
                    continue
                for w in wires:
                    a, z = (w["from"].get("block"), w["from"].get("key")), (w["to"].get("block"), w["to"].get("key"))
                    if a[0] == bid and a[1] in keys:
                        far = z
                    elif z[0] == bid and z[1] in keys:
                        far = a
                    else:
                        continue
                    if far[0] == bid:
                        continue
                    t = typ(far)
                    if t is not None:
                        locked[bid] = t
                        for k in keys:
                            P[(bid, k)] = t
                        changed = True
                        break
            else:
                ins: list[Type | None] = []
                for k in keys[:-1]:
                    src = driver.get((bid, k))
                    t = typ(src) if src else _value_type((b.get("values") or {}).get(k))
                    ins.append(t)
                    if P[(bid, k)] != t:
                        P[(bid, k)] = t
                        changed = True
                out = None
                if all(t is not None for t in ins):
                    dim = ins[0][0]
                    for t in ins[1:]:
                        dim = dim * t[0] if b["op"] == "mul" else dim / t[0]
                    out = (dim, False)
                if P[(bid, "y")] != out:
                    P[(bid, "y")] = out
                    changed = True
        if not changed:
            break
    return P, set(locked)


def math_calculation(block: dict, types: dict[tuple[str, str], Type | None] | None = None) -> Calculation:
    """The ordinary calculation a math block stands for, with port units taken from the resolved types."""
    op = block["op"]
    spec = OPS[op]
    bid = block.get("id", "")
    keys = input_keys(block)
    P = types or {}
    values = block.get("values") or {}
    unset: Type = (Dimension(), False)

    def port(k: str) -> Type:
        return P.get((bid, k)) or _value_type(values.get(k)) or unset

    if spec["lock"]:
        shared = next((P[(bid, k)] for k in keys if P.get((bid, k))), None) or next((t for k in keys if (t := _value_type(values.get(k)))), None) or unset
        in_types = {k: shared for k in keys}
        out_type = shared
    else:
        in_types = {k: port(k) for k in keys}
        dim = in_types[keys[0]][0]
        for k in keys[1:]:
            dim = dim * in_types[k][0] if op == "mul" else dim / in_types[k][0]
        out_type = (dim, False)
    reg = default_registry()
    terms = spec["terms"]
    label = (lambda i: terms[i]) if isinstance(terms, tuple) else (lambda i: f"{terms} {i + 1}")
    variables = [V(k, label(i), reg.si_symbol(in_types[k][0]), latex=f"x_{{{i + 1}}}", delta=in_types[k][1], signed=True) for i, k in enumerate(keys)]
    variables.append(V("y", spec["result"], reg.si_symbol(out_type[0]), latex="y", delta=out_type[1], signed=True))
    sign = {"add": " + ", "sub": " - ", "mul": "*", "div": "/"}[op]
    return Calculation(
        id=f"math.{op}", name=spec["name"], disciplines=["systems"], subdisciplines=["Integration Engineering"], description=spec["description"],
        variables=variables, equations=[(spec["name"], "y = " + sign.join(keys))], outputs=["y"], tags=["math", spec["name"].lower()],
        assumptions=["Values travel in coherent SI units and are converted at the ports."])
