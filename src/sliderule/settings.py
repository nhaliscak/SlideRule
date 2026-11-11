"""User settings. Currently: the time limit for long calculations.

Installed copies persist them in ``settings.json`` next to the equations folder (``$SLIDERULE_HOME`` or ``~/.sliderule``);
the in-browser build has no disk, so the page keeps its own copy in browser storage and re-applies it on start.
Turning the limit off is deliberate: it needs an explicit acknowledgement of the risks at every layer (UI, API, CLI).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

DEFAULT_SECONDS = 10.0
MIN_SECONDS, MAX_SECONDS = 1.0, 3600.0

DISABLE_WARNING = (
    "With no time limit, a calculation that never finishes — a hard symbolic integral, rearranging a very complicated equation, "
    "an unusually large System Design — keeps running until it ends, and it may never end. "
    "In the web app the engine stays busy and every later calculation waits behind it, so the page can look frozen until you reload it "
    "(unsaved System Design work is lost; saved equations and files are not). "
    "With the installed app the server process keeps using a processor core and memory, which can slow the computer or make the system stop the process, "
    "and it can only be stopped by quitting the program. Results are never affected by the limit; it only decides when to give up."
)

_lock = threading.RLock()
_values: dict = {"timeout_enabled": True, "timeout_seconds": DEFAULT_SECONDS}
_path: Path | None = None


class SettingsError(ValueError):
    def __init__(self, message: str, code: str = "BAD_SETTING"):
        super().__init__(message)
        self.code = code


def default_path() -> Path:
    home = os.environ.get("SLIDERULE_HOME")
    return (Path(home) if home else Path.home() / ".sliderule") / "settings.json"


def get() -> dict:
    with _lock:
        return {**_values, "default_seconds": DEFAULT_SECONDS, "min_seconds": MIN_SECONDS, "max_seconds": MAX_SECONDS,
                "disable_warning": DISABLE_WARNING, "storage": {"kind": "file", "path": str(_path)} if _path else {"kind": "memory"}}


def limit() -> float | None:
    """Seconds a calculation may run, or ``None`` when the limit is switched off."""
    with _lock:
        return float(_values["timeout_seconds"]) if _values["timeout_enabled"] else None


def update(timeout_enabled: bool | None = None, timeout_seconds: float | None = None, acknowledge_risk: bool = False) -> dict:
    with _lock:
        new = dict(_values)
        if timeout_seconds is not None:
            if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not (MIN_SECONDS <= timeout_seconds <= MAX_SECONDS):
                raise SettingsError(f"the time limit must be a number of seconds from {MIN_SECONDS:g} to {MAX_SECONDS:g}")
            new["timeout_seconds"] = float(timeout_seconds)
        if timeout_enabled is not None:
            if not isinstance(timeout_enabled, bool):
                raise SettingsError("timeout_enabled must be true or false")
            if not timeout_enabled and _values["timeout_enabled"] and not acknowledge_risk:
                raise SettingsError(DISABLE_WARNING, "WARNING_REQUIRED")
            new["timeout_enabled"] = timeout_enabled
        _values.update(new)
        _save()
        return get()


def _save() -> None:
    if _path is None:
        return
    _path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps(_values, indent=2) + "\n", encoding="utf-8")
    tmp.replace(_path)


def configure(path: Path | str | None) -> None:
    """Persist to ``path`` and load it if it exists (an unreadable or invalid file is ignored, defaults stay)."""
    global _path
    with _lock:
        _path = Path(path) if path else None
        if _path is None or not _path.is_file():
            return
        try:
            data = json.loads(_path.read_text(encoding="utf-8"))
            enabled, secs = data.get("timeout_enabled", True), float(data.get("timeout_seconds", DEFAULT_SECONDS))
            if isinstance(enabled, bool) and MIN_SECONDS <= secs <= MAX_SECONDS:
                _values.update(timeout_enabled=enabled, timeout_seconds=secs)
        except (OSError, ValueError, TypeError, AttributeError):
            pass


def reset() -> None:
    """Back to defaults and no file (used by tests)."""
    global _path
    with _lock:
        _path = None
        _values.update(timeout_enabled=True, timeout_seconds=DEFAULT_SECONDS)
