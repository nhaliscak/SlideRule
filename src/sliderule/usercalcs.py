"""The user's own calculations: registered in the live catalog and, for installed copies, kept as files.

* Every calculation is validated by :func:`sliderule.core.custom.calc_from_dict` before it is registered.
* ``configure(folder)`` (called by ``sliderule serve`` and the CLI) loads ``*.json`` files from that folder and writes
  each saved calculation back to it, one file per calculation, so they are plain files that can be copied, shared or
  put under version control. Without a folder (the in-browser build) calculations live in memory and the page
  keeps its own copy in browser storage.
* Files and documents may hold one calculation or a bundle; ids are always ``custom.*`` so a user calculation can never
  replace a library one.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .core.catalog import default_catalog
from .core.custom import (FORMAT_ONE, VERSION, CustomError, calc_from_dict, calc_to_dict, make_document, parse_document,
                          slugify)

MAX_FILE_BYTES = 1_000_000
_lock = threading.RLock()
_docs: dict[str, dict] = {}
_folder: Path | None = None


def default_folder() -> Path:
    home = os.environ.get("SLIDERULE_HOME")
    return (Path(home) if home else Path.home() / ".sliderule") / "calculations"


def storage() -> dict:
    return {"kind": "folder", "path": str(_folder)} if _folder else {"kind": "memory"}


def _file(cid: str) -> Path:
    assert _folder is not None
    return _folder / f"{cid.removeprefix('custom.')}.json"


def _persist(doc: dict) -> None:
    if _folder is None:
        return
    _folder.mkdir(parents=True, exist_ok=True)
    path = _file(doc["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"format": FORMAT_ONE, "version": VERSION, "calculation": doc}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def reset() -> None:
    """Forget every user calculation (and stop using a folder). Used by tests."""
    global _folder
    with _lock:
        for cid in list(_docs):
            default_catalog().remove(cid)
        _docs.clear()
        _folder = None


def configure(folder: Path | str | None) -> list[dict]:
    """Use ``folder`` for persistence and load what is in it. Returns problems found, ``[{"file", "message"}]``."""
    global _folder
    problems: list[dict] = []
    with _lock:
        _folder = Path(folder) if folder else None
        if _folder is None or not _folder.is_dir():
            return problems
        for path in sorted(_folder.glob("*.json"))[:400]:
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    raise CustomError([{"field": "file", "message": "file is larger than 1 MB"}])
                items = parse_document(json.loads(path.read_text(encoding="utf-8")))
                for item in items:
                    _register(item, replace=True, persist=False)
            except (OSError, ValueError) as exc:   # bad JSON, bad calculation, unreadable file
                problems.append({"file": path.name, "message": str(exc)})
    return problems


def _unique_id(base: str) -> str:
    cid, n = base, 2
    while cid in _docs:
        cid, n = f"{base}_{n}", n + 1
    return cid


def _register(raw: dict, *, replace: bool, persist: bool = True) -> dict:
    if not isinstance(raw, dict):
        raise CustomError([{"field": "calculation", "message": "must be an object"}])
    default_catalog()          # build the library first: its one-off start-up cost must not count against the time limit
    raw = dict(raw)
    if not raw.get("id"):
        raw["id"] = _unique_id("custom." + slugify(str(raw.get("name") or "equation")))
    calc = calc_from_dict(raw)
    with _lock:
        if calc.id in _docs and not replace:
            raise CustomError([{"field": "id", "message": f"{calc.id} already exists"}])
        cat = default_catalog()
        if calc.id in _docs:
            cat.remove(calc.id)
        cat.add(calc)
        doc = calc_to_dict(calc)
        _docs[calc.id] = doc
        if persist:
            _persist(doc)
    return doc


def save(raw: dict, replace: bool = False) -> dict:
    """Validate and register one calculation (raises :class:`CustomError`); returns its canonical document."""
    return _register(raw, replace=replace)


def remove(cid: str) -> bool:
    with _lock:
        if cid not in _docs:
            return False
        default_catalog().remove(cid)
        del _docs[cid]
        if _folder is not None:
            try:
                _file(cid).unlink()
            except FileNotFoundError:
                pass
        return True


def listing() -> list[dict]:
    with _lock:
        return [dict(d) for d in _docs.values()]


def get(cid: str) -> dict | None:
    with _lock:
        d = _docs.get(cid)
        return dict(d) if d else None


def export(ids: list[str] | None = None) -> dict:
    with _lock:
        docs = [d for cid, d in _docs.items() if ids is None or cid in ids]
    return make_document(docs)


def import_document(obj, on_conflict: str = "rename", dry_run: bool = False) -> list[dict]:
    """Import a file's calculations. ``on_conflict``: ``rename`` (keep both), ``replace``, ``skip`` or ``ask`` (report only).

    Returns one row per calculation: ``{"id", "name", "status", "new_id"?, "errors"?}`` with status ``added``,
    ``replaced``, ``renamed``, ``unchanged``, ``skipped``, ``conflict`` or ``error``.
    """
    items = parse_document(obj)
    rows: list[dict] = []
    for item in items:
        name = item.get("name", "") if isinstance(item, dict) else ""
        cid = item.get("id", "") if isinstance(item, dict) else ""
        try:
            calc = calc_from_dict({**item, "id": cid or "custom." + slugify(str(name))})   # validate before touching anything
        except CustomError as exc:
            rows.append({"id": cid, "name": name, "status": "error", "errors": exc.errors})
            continue
        existing = _docs.get(calc.id)
        row = {"id": calc.id, "name": calc.name}
        if existing is None:
            rows.append({**row, "status": "added"})
            if not dry_run:
                _register(item, replace=False)
            continue
        if calc_to_dict(calc) == existing:
            rows.append({**row, "status": "unchanged"})
            continue
        if on_conflict == "replace":
            rows.append({**row, "status": "replaced"})
            if not dry_run:
                _register(item, replace=True)
        elif on_conflict == "skip":
            rows.append({**row, "status": "skipped"})
        elif on_conflict == "ask":
            rows.append({**row, "status": "conflict"})
        else:
            new_id = _unique_id(calc.id)
            rows.append({**row, "status": "renamed", "new_id": new_id})
            if not dry_run:
                _register({**item, "id": new_id}, replace=False)
    return rows
