"""The user's favorites, groups, recent calculations and own choice of "Basic", kept on disk so every browser that opens the same installed app sees them.

Installed copies persist ``lists.json`` next to the equations folder (``$SLIDERULE_HOME`` or ``~/.sliderule``); the in-browser build has no disk and the page keeps
them in browser storage only. The page decides which copy wins from ``updated`` (milliseconds): the newer one, as a whole (no merging, so a deletion is not undone).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

MAX_GROUPS, MAX_IDS, MAX_RECENT, MAX_NAME = 50, 1000, 30, 40
_lock = threading.RLock()
_path: Path | None = None
_doc: dict = {}


class ListsError(ValueError):
    pass


def default_path() -> Path:
    home = os.environ.get("SLIDERULE_HOME")
    return (Path(home) if home else Path.home() / ".sliderule") / "lists.json"


def configure(path: Path | str | None) -> None:
    """Keep the lists in this file (``None``: in memory only)."""
    global _path, _doc
    with _lock:
        _path = Path(path) if path else None
        _doc = {}
        if _path and _path.exists():
            try:
                _doc = clean(json.loads(_path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                _doc = {}


def _ids(x: Any, limit: int) -> list[str]:
    return list(dict.fromkeys(i for i in x if isinstance(i, str) and 0 < len(i) <= 200))[:limit] if isinstance(x, list) else []


def clean(doc: Any) -> dict:
    """The document with anything unexpected dropped: ids are strings, at most 50 groups of 1000 ids, 30 recent."""
    if not isinstance(doc, dict):
        raise ListsError("the lists must be an object")
    groups: dict[str, list[str]] = {}
    raw = doc.get("groups")
    for name, ids in (raw.items() if isinstance(raw, dict) else []):
        if isinstance(name, str) and name.strip() and len(groups) < MAX_GROUPS:
            groups[name.strip()[:MAX_NAME]] = _ids(ids, MAX_IDS)
    out = {"favorites": _ids(doc.get("favorites"), MAX_IDS), "groups": groups, "recent": _ids(doc.get("recent"), MAX_RECENT),
           "updated": int(doc["updated"]) if isinstance(doc.get("updated"), (int, float)) and not isinstance(doc.get("updated"), bool) and doc["updated"] >= 0 else 0}
    basic = doc.get("basic")
    if isinstance(basic, list):
        out["basic"] = [b for b in basic if isinstance(b, str) and 0 < len(b) <= 120][:300]
    return out


def get() -> dict:
    with _lock:
        return {"stored": _path is not None, "lists": dict(_doc) if _doc else None}


def put(doc: Any) -> dict:
    global _doc
    new = clean(doc)
    with _lock:
        if _doc and new["updated"] < _doc.get("updated", 0):
            return {"stored": _path is not None, "lists": dict(_doc), "kept_newer": True}          # an older copy never replaces a newer one
        _doc = new
        if _path is not None:
            _path.parent.mkdir(parents=True, exist_ok=True)
            tmp = _path.with_suffix(".tmp")
            tmp.write_text(json.dumps(_doc, indent=2) + "\n", encoding="utf-8")
            tmp.replace(_path)
        return {"stored": _path is not None, "lists": dict(_doc), "kept_newer": False}
