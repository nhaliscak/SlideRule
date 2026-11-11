"""Datapacks: versioned property data kept outside the calculation code, with the source of every number.

A datapack is a folder with ``manifest.json`` and ``data.json``::

    manifest.json   id, version, title, kind, licence, status, design_use, sources[], checksum (sha256 of data.json)
    data.json       {"records": [{"id", "name", "category", "designation", "condition", "note",
                                  "properties": {name: {"value", "unit", "basis", "source", "low", "high", "note"}}}]}

A property is either a single **value** or a **curve** against temperature (``{"curve": {"x": [...], "y": [...], "x_unit": "K", "method": "pchip"}, "unit": ...}``,
interpolated with the same machinery as calculation tables, never extrapolated: outside the stored range there is no answer). ``at`` records the state a
property was taken at (for example ``{"pressure": "101.325 kPa"}``) and ``rel_uncertainty`` the measured deviation from the reference it was checked against.

Every property names its **basis** (``min`` specified minimum, ``typical``, ``design`` value from a standard, ``computed``), its **source** (an id from
the manifest) and, where the sources disagree, a **low** and **high**. Property names come from a fixed vocabulary that fixes the dimension and a
plausibility range, so a value in the wrong unit or off by a power of ten is rejected when the pack loads instead of reaching a result.

Packs are read from the built-in ``sliderule/datapacks`` folder and from ``$SLIDERULE_HOME/datapacks`` (user packs, marked *custom*). A pack that fails
validation is not loaded; the reasons are reported by :func:`problems`. ``sliderule data validate`` runs the same checks.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from ..units import UnitError, default_registry
from . import tables

BASES = ("min", "typical", "design", "computed")
KINDS = ("materials", "fluids")

#: property name -> (label, canonical unit, smallest and largest plausible value in that unit), per pack kind
_MATERIALS: dict[str, tuple[str, str, float, float]] = {
    "density": ("Density", "kg/m^3", 50.0, 25000.0),
    "youngs_modulus": ("Young's modulus", "GPa", 0.001, 1200.0),
    "poisson_ratio": ("Poisson's ratio", "1", 0.0, 0.5),
    "yield_strength": ("Yield strength", "MPa", 1.0, 6000.0),
    "ultimate_strength": ("Ultimate tensile strength", "MPa", 1.0, 8000.0),
    "thermal_conductivity": ("Thermal conductivity", "W/(m*K)", 0.001, 3000.0),
    "specific_heat": ("Specific heat capacity", "J/(kg*K)", 0.001, 5000.0),
    "thermal_expansion": ("Linear thermal expansion coefficient", "1/K", 1e-7, 1e-3),
}
_FLUIDS: dict[str, tuple[str, str, float, float]] = {
    "density": ("Density", "kg/m^3", 0.01, 2000.0),
    "dynamic_viscosity": ("Dynamic viscosity", "Pa*s", 1e-7, 1e4),
    "thermal_conductivity": ("Thermal conductivity", "W/(m*K)", 0.001, 50.0),
    "specific_heat": ("Specific heat capacity at constant pressure", "J/(kg*K)", 100.0, 20000.0),
    "vapour_pressure": ("Vapour (saturation) pressure", "Pa", 1e-3, 1e9),
}
VOCABULARIES = {"materials": _MATERIALS, "fluids": _FLUIDS}
VOCABULARY = _MATERIALS                      # kept for callers written before fluids existed
MAX_CURVE_POINTS = 500
CURVE_METHODS = ("linear", "pchip")

#: words in a variable's label that point at a property (the picker lists matching properties first, and is the only way a dimensionless variable is offered one)
HINTS: dict[str, tuple[str, ...]] = {
    "density": ("density",), "youngs_modulus": ("young", "modulus", "elastic"), "poisson_ratio": ("poisson",), "yield_strength": ("yield",),
    "ultimate_strength": ("ultimate", "tensile"), "thermal_conductivity": ("conductivity",), "specific_heat": ("specific heat", "heat capacity"),
    "thermal_expansion": ("expansion",), "dynamic_viscosity": ("viscosity",), "vapour_pressure": ("vapour", "vapor", "saturation"),
}

BUILTIN = Path(__file__).resolve().parents[1] / "datapacks"


class DataPackError(ValueError):
    pass


def user_folder() -> Path:
    home = os.environ.get("SLIDERULE_HOME")
    return (Path(home) if home else Path.home() / ".sliderule") / "datapacks"


def checksum(data_bytes: bytes) -> str:
    return hashlib.sha256(data_bytes).hexdigest()


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _check_curve(w: str, p: dict, u, cu, lo_ok: float, hi_ok: float, canon: str, reg) -> list[str]:
    c = p["curve"]
    if not isinstance(c, dict):
        return [f"{w}: curve must be an object with x, y, x_unit and method"]
    errs: list[str] = []
    if "value" in p:
        errs.append(f"{w}: give either a value or a curve, not both")
    if c.get("x_quantity", "temperature") != "temperature":
        errs.append(f"{w}: curves are against temperature only for now")
    try:
        xu = reg.parse(str(c.get("x_unit", "")))
        if xu.dim != reg.parse("K").dim:
            errs.append(f"{w}: curve.x_unit {c.get('x_unit')!r} is not a temperature unit")
            return errs
    except UnitError as exc:
        return errs + [f"{w}: curve.x_unit: {exc}"]
    method = c.get("method", "pchip")
    if method not in CURVE_METHODS:
        errs.append(f"{w}: curve.method must be one of {', '.join(CURVE_METHODS)}")
        return errs
    try:
        xs, ys = tables.check_data(c.get("x"), c.get("y"), method, "error")
    except tables.TableError as exc:
        return errs + [f"{w}: curve: {exc}"]
    if len(xs) > MAX_CURVE_POINTS:
        errs.append(f"{w}: at most {MAX_CURVE_POINTS} curve points")
    xk = [xu.to_si(x) for x in xs]
    if min(xk) <= 0 or max(xk) > 6000:
        errs.append(f"{w}: curve temperatures must lie between 0 K and 6000 K")
    for x, y in zip(xs, ys):
        val = cu.from_si(u.to_si(y))
        if not lo_ok <= val <= hi_ok:
            errs.append(f"{w}: curve value {y:g} {p.get('unit')} at {x:g} {c.get('x_unit')} is outside the plausible range {lo_ok:g} to {hi_ok:g} {canon}")
            break
    return errs


def validate_pack(folder: Path) -> tuple[dict | None, list[str]]:
    """``(pack, errors)``: the loaded pack dict, or ``None`` with every reason it was refused."""
    errs: list[str] = []
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        raw = (folder / "data.json").read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        return None, [f"cannot read the pack: {exc}"]
    if not isinstance(manifest, dict) or not isinstance(data, dict):
        return None, ["manifest.json and data.json must be JSON objects"]

    pid = manifest.get("id")
    if not isinstance(pid, str) or not pid or not all(c.isalnum() or c in "-_" for c in pid):
        errs.append("manifest.id must be letters, digits, '-' or '_'")
    for key in ("version", "title", "licence", "status"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            errs.append(f"manifest.{key} is required")
    if manifest.get("kind") not in KINDS:
        errs.append(f"manifest.kind must be one of {', '.join(KINDS)}")
    if not isinstance(manifest.get("design_use"), bool):
        errs.append("manifest.design_use must be true or false (is the data fit for design calculations?)")
    if manifest.get("checksum") != checksum(raw):
        errs.append("data.json does not match manifest.checksum (edited after sealing: run `sliderule data seal`)")

    sources: dict[str, dict] = {}
    for i, s in enumerate(manifest.get("sources") or []):
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not str(s.get("ref", "")).strip():
            errs.append(f"sources[{i}] needs an id and a ref")
        elif s["id"] in sources:
            errs.append(f"duplicate source id {s['id']!r}")
        else:
            sources[s["id"]] = s
    if not sources:
        errs.append("a pack needs at least one source")

    reg = default_registry()
    seen: set[str] = set()
    records = data.get("records")
    if not isinstance(records, list) or not records:
        errs.append("data.records must be a non-empty list")
        records = []
    for rec in records:
        rid = rec.get("id") if isinstance(rec, dict) else None
        where = f"record {rid!r}"
        if not isinstance(rid, str) or not rid:
            errs.append("a record has no id")
            continue
        if rid in seen:
            errs.append(f"duplicate record id {rid!r}")
        seen.add(rid)
        if not str(rec.get("name", "")).strip() or not str(rec.get("category", "")).strip():
            errs.append(f"{where}: name and category are required")
        props = rec.get("properties")
        if not isinstance(props, dict) or not props:
            errs.append(f"{where}: needs at least one property")
            continue
        vocab = VOCABULARIES.get(manifest.get("kind"), _MATERIALS)
        for name, p in props.items():
            w = f"{where}.{name}"
            if name not in vocab:
                errs.append(f"{w}: unknown property for a {manifest.get('kind')} pack (allowed: {', '.join(vocab)})")
                continue
            if not isinstance(p, dict):
                errs.append(f"{w}: must be an object")
                continue
            _, canon, lo_ok, hi_ok = vocab[name]
            try:
                u, cu = reg.parse(str(p.get("unit", ""))), reg.parse(canon)
            except UnitError as exc:
                errs.append(f"{w}: unit {p.get('unit')!r}: {exc}")
                continue
            if u.dim != cu.dim:
                errs.append(f"{w}: unit {p.get('unit')!r} is not a unit of {vocab[name][0].lower()} (expected like {canon})")
                continue
            if p.get("basis") not in BASES:
                errs.append(f"{w}: basis must be one of {', '.join(BASES)}")
            if p.get("source") not in sources:
                errs.append(f"{w}: source {p.get('source')!r} is not listed in the manifest")
            if "rel_uncertainty" in p and not (_num(p["rel_uncertainty"]) and 0 < p["rel_uncertainty"] < 1):
                errs.append(f"{w}: rel_uncertainty must be a fraction between 0 and 1")
            at = p.get("at")
            if at is not None:
                if not isinstance(at, dict) or not all(isinstance(v, str) for v in at.values()):
                    errs.append(f"{w}: 'at' must map names to strings such as {{\"pressure\": \"101.325 kPa\"}}")
                elif "pressure" in at:
                    try:
                        if reg.parse(at["pressure"].split(None, 1)[1]).dim != reg.parse("Pa").dim:
                            raise UnitError("not a pressure")
                        float(at["pressure"].split(None, 1)[0])
                    except (UnitError, IndexError, ValueError):
                        errs.append(f"{w}: at.pressure must look like '101.325 kPa'")
            if "curve" in p:
                errs.extend(_check_curve(w, p, u, cu, lo_ok, hi_ok, canon, reg))
                continue
            if not _num(p.get("value")):
                errs.append(f"{w}: value must be a finite number (or give a curve)")
                continue
            val = cu.from_si(u.to_si(float(p["value"])))
            if not lo_ok <= val <= hi_ok:
                errs.append(f"{w}: {p['value']} {p.get('unit')} is outside the plausible range {lo_ok:g} to {hi_ok:g} {canon} (a unit or power-of-ten slip?)")
            for k in ("low", "high"):
                if k in p and not _num(p[k]):
                    errs.append(f"{w}: {k} must be a number")
            if _num(p.get("low")) and _num(p.get("high")) and not p["low"] <= p["value"] <= p["high"]:
                errs.append(f"{w}: value must lie between low and high")
    if errs:
        return None, errs
    return {"manifest": manifest, "records": records, "sources": sources, "folder": str(folder)}, []


_cache: dict[str, Any] = {"packs": None, "problems": {}}


def reload() -> None:
    packs: dict[str, dict] = {}
    bad: dict[str, list[str]] = {}
    for base, custom in ((BUILTIN, False), (user_folder(), True)):
        if not base.is_dir():
            continue
        for folder in sorted(p for p in base.iterdir() if (p / "manifest.json").is_file()):
            pack, errs = validate_pack(folder)
            if pack is None:
                bad[f"{'user' if custom else 'built-in'}:{folder.name}"] = errs
            elif pack["manifest"]["id"] in packs:
                bad[f"{'user' if custom else 'built-in'}:{folder.name}"] = [f"pack id {pack['manifest']['id']!r} is already loaded"]
            else:
                pack["custom"] = custom
                packs[pack["manifest"]["id"]] = pack
    _cache["packs"], _cache["problems"] = packs, bad
    _interp.clear()


def packs() -> dict[str, dict]:
    if _cache["packs"] is None:
        reload()
    return _cache["packs"]


def problems() -> dict[str, list[str]]:
    packs()
    return _cache["problems"]


def pack_summary(p: dict) -> dict:
    m = p["manifest"]
    return {"id": m["id"], "version": m["version"], "title": m["title"], "kind": m["kind"], "licence": m["licence"], "status": m["status"],
            "design_use": m["design_use"], "records": len(p["records"]), "custom": p["custom"], "sources": list(p["sources"].values())}


def _record_out(p: dict, rec: dict) -> dict:
    reg = default_registry()
    vocab = VOCABULARIES[p["manifest"]["kind"]]
    props = {}
    for name, v in rec["properties"].items():
        u = reg.parse(v["unit"])
        out = {**v, "label": vocab[name][0], "si_unit": reg.si_symbol(u.dim), "source_ref": p["sources"][v["source"]]["ref"]}
        if "curve" in v:
            c = v["curve"]
            xu = reg.parse(c["x_unit"])
            xk = [xu.to_si(x) for x in c["x"]]
            out["range_si"] = [min(xk), max(xk)]
            out["range"] = {"min": c["x"][0], "max": c["x"][-1], "unit": c["x_unit"]}
        else:
            out["si_value"] = u.to_si(float(v["value"]))
        props[name] = out
    return {"pack": p["manifest"]["id"], "pack_version": p["manifest"]["version"], "id": rec["id"], "name": rec["name"], "category": rec["category"],
            "kind": p["manifest"]["kind"], "designation": rec.get("designation", ""), "condition": rec.get("condition", ""), "note": rec.get("note", ""),
            "design_use": p["manifest"]["design_use"], "status": p["manifest"]["status"], "custom": p["custom"], "properties": props}


_interp: dict[tuple, Any] = {}


def value(pack: str, rid: str, prop: str, x: float | None = None, x_unit: str = "K", unit: str | None = None) -> dict:
    """One property of one record, in ``unit`` (default: the stored unit). A curve needs the temperature ``x`` in ``x_unit`` and refuses to
    answer outside the stored range."""
    rec = record(pack, rid)
    p = rec["properties"].get(prop)
    if p is None:
        raise DataPackError(f"{rid!r} has no property {prop!r} (it has: {', '.join(rec['properties'])})")
    reg = default_registry()
    try:
        u = reg.parse(p["unit"])
        out_u = reg.parse(unit) if unit else u
        if out_u.dim != u.dim:
            raise DataPackError(f"cannot give {prop} in {unit!r}: not a unit of {p['label'].lower()}")
    except UnitError as exc:
        raise DataPackError(str(exc)) from None
    meta = {"pack": pack, "pack_version": rec["pack_version"], "record": rid, "property": prop, "basis": p["basis"], "source": p["source_ref"],
            "design_use": rec["design_use"], "at": p.get("at", {}), "rel_uncertainty": p.get("rel_uncertainty"), "note": p.get("note", "")}
    if "curve" not in p:
        return {**meta, "value": out_u.from_si(p["si_value"]), "unit": out_u.symbol, "si_value": p["si_value"]}
    if x is None:
        r = p["range"]
        raise DataPackError(f"{prop} of {rid!r} depends on temperature: give x ({r['min']:g} to {r['max']:g} {r['unit']})")
    try:
        xu = reg.parse(x_unit)
        if xu.dim != reg.parse("K").dim:
            raise DataPackError(f"x_unit {x_unit!r} is not a temperature unit")
        xk = xu.to_si(float(x))
    except (UnitError, TypeError, ValueError) as exc:
        raise DataPackError(f"bad temperature: {exc}") from None
    key = (pack, pack_version_of(pack), rid, prop)
    if key not in _interp:
        c = p["curve"]
        cx = reg.parse(c["x_unit"])
        _interp[key] = tables.interpolator([cx.to_si(v) for v in c["x"]], [u.to_si(v) for v in c["y"]], c.get("method", "pchip"), "error")[0]
    lo, hi = p["range_si"]
    if not lo <= xk <= hi:
        shown = [xu.from_si(lo), xu.from_si(hi)]
        raise DataPackError(f"{x:g} {x_unit} is outside the stored range {shown[0]:.6g} to {shown[1]:.6g} {x_unit} of {prop} for {rid!r} (no extrapolation)")
    y_si = float(_interp[key](xk))
    return {**meta, "value": out_u.from_si(y_si), "unit": out_u.symbol, "si_value": y_si, "x": float(x), "x_unit": x_unit}


def pack_version_of(pack: str) -> str:
    return packs()[pack]["manifest"]["version"]


def search(q: str = "", pack: str = "", category: str = "") -> list[dict]:
    """Records whose name, category, designation or id contain every word of ``q`` (case-insensitive)."""
    words = q.lower().split()
    out = []
    for pid, p in packs().items():
        if pack and pid != pack:
            continue
        for rec in p["records"]:
            if category and rec["category"] != category:
                continue
            hay = " ".join(str(rec.get(k, "")) for k in ("id", "name", "category", "designation", "condition")).lower()
            if all(w in hay for w in words):
                out.append(_record_out(p, rec))
    return out


def options_for(variables: list[dict]) -> dict[str, list[dict]]:
    """For each ``{key, unit, label}``: the record properties that could fill that variable (same dimension), best label match first.

    A dimensionless variable is only offered properties whose hint words appear in its label (otherwise every ratio would match Poisson's ratio).
    """
    reg = default_registry()
    flat = []
    for pid, p in packs().items():
        vocab = VOCABULARIES[p["manifest"]["kind"]]
        for rec in p["records"]:
            for name, v in rec["properties"].items():
                flat.append((pid, p, rec, name, vocab[name][0], v, reg.parse(v["unit"]).dim))
    out: dict[str, list[dict]] = {}
    for var in variables:
        key, label = str(var.get("key", "")), str(var.get("label", "")).lower()
        try:
            dim = reg.parse(str(var.get("unit", ""))).dim
        except UnitError:
            out[key] = []
            continue
        rows = []
        for pid, p, rec, name, plabel, v, pdim in flat:
            if pdim != dim:
                continue
            match = any(w in label for w in HINTS.get(name, ()))
            if dim == reg.parse("1").dim and not match:
                continue
            item = {"pack": pid, "record": rec["id"], "record_name": rec["name"], "category": rec["category"], "property": name, "label": plabel,
                    "curve": "curve" in v, "match": match, "design_use": p["manifest"]["design_use"], "unit": v["unit"]}
            if "curve" in v:
                item["range"] = {"min": v["curve"]["x"][0], "max": v["curve"]["x"][-1], "unit": v["curve"]["x_unit"]}
            rows.append(item)
        rows.sort(key=lambda r: (not r["match"], r["label"], r["record_name"]))
        out[key] = rows
    return out


def record(pack: str, rid: str) -> dict:
    p = packs().get(pack)
    if p is None:
        raise DataPackError(f"no data pack {pack!r}")
    for rec in p["records"]:
        if rec["id"] == rid:
            return _record_out(p, rec)
    raise DataPackError(f"no record {rid!r} in pack {pack!r}")


def seal(folder: Path) -> str:
    """Write the sha256 of ``data.json`` into ``manifest.json`` (run after editing the data) and return it."""
    raw = (folder / "data.json").read_bytes()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["checksum"] = checksum(raw)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest["checksum"]
