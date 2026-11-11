"""Catalog of calculations with name / discipline / variable filtering."""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from typing import Iterable

from .model import Calculation, Variable
from .taxonomy import DISCIPLINES, GROUPS, SUBDISCIPLINES

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _var_matches(v: Variable, term: str) -> bool:
    """A term matches a variable's symbol exactly, or (for terms of 3+ letters) the start of any word
    in its label or quantity kind: 'press' finds pressure, 'visc' finds viscosity, 'Re' only the symbol Re."""
    t = term.strip().lower()
    if not t:
        return True
    if t == v.key.lower() or t == (v.latex or "").lower().lstrip("\\"):
        return True
    if len(t) < 3:
        return False
    words = _tokens(v.label) + [w for k in v.kinds for w in _tokens(k)]
    return any(w.startswith(t) for w in words)


class Catalog:
    def __init__(self, calcs: Iterable[Calculation] = ()):
        self._calcs: dict[str, Calculation] = {}
        for c in calcs:
            self.add(c)

    def add(self, c: Calculation) -> None:
        if c.id in self._calcs:
            raise ValueError(f"duplicate calculation id {c.id!r}")
        self._calcs[c.id] = c

    def remove(self, calc_id: str) -> None:
        del self._calcs[calc_id]

    def __len__(self) -> int:
        return len(self._calcs)

    def __iter__(self):
        return iter(self._calcs.values())

    def get(self, calc_id: str) -> Calculation:
        try:
            return self._calcs[calc_id]
        except KeyError:
            raise KeyError(f"no calculation with id {calc_id!r}") from None

    def search(
        self,
        q: str = "",
        disciplines: Iterable[str] | None = None,
        variables: Iterable[str] | None = None,
        solves_for: Iterable[str] | None = None,
        subdisciplines: Iterable[str] | None = None,
    ) -> list[Calculation]:
        """Filter and rank.

        * ``q``: every word must appear in name/id/tags/description/equation titles; name hits rank first.
        * ``disciplines``: calculation must belong to at least one.
        * ``variables``: calculation must contain a variable matching *each* term (symbol, label word, quantity kind).
        * ``solves_for``: each term must match a non-constant variable (something you can compute).
        """
        disc = {d.lower() for d in (disciplines or [])}
        vterms = [t for t in (variables or []) if t.strip()]
        sterms = [t for t in (solves_for or []) if t.strip()]
        subs = [s.strip().lower() for s in (subdisciplines or []) if s.strip()]
        words = _tokens(q)
        scored: list[tuple[float, str, Calculation]] = []
        for c in self._calcs.values():
            if disc and not disc & set(c.disciplines):
                continue
            if subs and not any(s in x.lower() for s in subs for x in c.subdisciplines):
                continue
            if vterms and not all(any(_var_matches(v, t) for v in c.variables) for t in vterms):
                continue
            if sterms and not all(any(_var_matches(v, t) for v in c.inputs) for t in sterms):
                continue
            score = 0.0
            if words:
                name = set(_tokens(c.name))
                name_prefixes = " ".join(_tokens(c.name))
                other = set(_tokens(" ".join([c.id, c.description, *c.tags, *(e.title for e in c.parsed)])))
                vlabels = " ".join(v.label.lower() for v in c.variables)
                ok = True
                for w in words:
                    if w in name or any(n.startswith(w) for n in name):
                        score += 3
                    elif w in name_prefixes:
                        score += 2
                    elif w in other or any(o.startswith(w) for o in other):
                        score += 1
                    elif w in vlabels:
                        score += 0.5
                    else:
                        ok = False
                        break
                if not ok:
                    continue
            scored.append((-score, c.name.lower(), c))
        scored.sort(key=lambda r: (r[0], r[1]))
        return [c for _, _, c in scored]

    def facets(self, matches: Iterable[Calculation] | None = None) -> dict:
        pool = list(self if matches is None else matches)
        counts = Counter(d for c in pool for d in c.disciplines)
        subcounts = Counter(s for c in pool for s in c.subdisciplines)
        return {
            "disciplines": [{"id": k, "name": v, "group": GROUPS[k], "count": counts.get(k, 0)} for k, v in DISCIPLINES.items()],
            "subdisciplines": [{"name": s, "count": subcounts.get(s, 0)} for s in sorted(SUBDISCIPLINES)],
        }


@lru_cache(maxsize=1)
def default_catalog() -> Catalog:
    from .. import library

    return Catalog(library.all_calculations())
