"""Find calculations that may duplicate each other (run before adding new ones; a test keeps the reviewed list honest).

Two calculations are flagged when they have the same name, or share most of their equation text, or share the same
output variables together with most of their inputs. Pairs a person has looked at and kept are listed in
``tests/duplicates_reviewed.txt`` (one ``id_a id_b`` per line).

    python scripts/check_duplicates.py                 # list unreviewed suspects
    python scripts/check_duplicates.py --all           # include the reviewed ones
    python scripts/check_duplicates.py ID [ID ...]     # only pairs involving these calculations (use before adding one)
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sliderule.core.catalog import default_catalog  # noqa: E402

REVIEWED = ROOT / "tests" / "duplicates_reviewed.txt"


def _tokens(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[A-Za-z_][A-Za-z_0-9]*|\d+\.?\d*", text))


def _profile(c):
    eq = [e.text for e in c.parsed] if hasattr(c.parsed[0], "text") else []
    return {"name": re.sub(r"\W+", " ", c.name.lower()).strip(), "eq": _tokens(" ".join(eq)), "out": frozenset(c.outputs), "keys": frozenset(v.key for v in c.variables)}


def suspects(calcs=None, only: set[str] | None = None):
    calcs = [c for c in (calcs or default_catalog()) if not c.custom]
    prof = {c.id: _profile(c) for c in calcs}
    for a, b in itertools.combinations(calcs, 2):
        if only and a.id not in only and b.id not in only:
            continue
        pa, pb = prof[a.id], prof[b.id]
        why = None
        if pa["name"] == pb["name"]:
            why = "same name"
        elif pa["eq"] and pb["eq"] and len(pa["eq"] & pb["eq"]) / len(pa["eq"] | pb["eq"]) >= 0.8 and len(pa["eq"]) >= 6:
            why = "equations share ≥ 80 % of their tokens"
        elif pa["out"] and pa["out"] == pb["out"] and len(pa["keys"] & pb["keys"]) / len(pa["keys"] | pb["keys"]) >= 0.8 and len(pa["keys"]) >= 4:
            why = "same outputs and ≥ 80 % of the same variable names"
        if why:
            yield a.id, b.id, why


def reviewed() -> set[frozenset[str]]:
    if not REVIEWED.exists():
        return set()
    out = set()
    for line in REVIEWED.read_text().splitlines():
        parts = line.split("#")[0].split()
        if len(parts) == 2:
            out.add(frozenset(parts))
    return out


def main(argv: list[str]) -> int:
    show_all = "--all" in argv
    ids = {a for a in argv if not a.startswith("--")}
    seen = reviewed()
    n = 0
    for a, b, why in suspects(only=ids or None):
        done = frozenset((a, b)) in seen
        if done and not show_all:
            continue
        n += 1
        print(f"{'(reviewed) ' if done else ''}{a}  <->  {b}   [{why}]")
    print(f"{n} suspect pair(s)")
    return 1 if n and not show_all else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
