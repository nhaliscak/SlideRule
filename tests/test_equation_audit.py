"""The equation-audit checklist stays consistent with its verdicts and with the document generated from it."""

import importlib.util
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("equation_audit", ROOT / "scripts" / "equation_audit.py")
ea = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ea)


def topics():
    return [t for items in ea.CHECK.values() for t, _ in items]


def test_topics_are_unique_and_have_phrases():
    ts = topics()
    assert len(ts) == len(set(ts)) and len(ts) >= 500
    assert all(ph and all(p.strip() for p in ph) for items in ea.CHECK.values() for _, ph in items)


def test_every_verdict_prefix_refers_to_a_real_topic():
    ts = topics()
    for k in ea.PARTIAL:
        assert any(t.startswith(k) for t in ts), f"PARTIAL entry {k!r} matches no topic (renamed?)"
    for k in ea.COVERED:
        assert any(t.startswith(k) for t in ts), f"COVERED entry {k!r} matches no topic (renamed?)"


def test_a_covered_topic_has_a_search_hit_and_a_partial_one_says_what_exists():
    res = ea.run()
    for rows in res.values():
        for t, _, hit in rows:
            kind, note = ea.status(t, hit)
            if kind == "covered":
                assert hit is not None
            if kind == "partial":
                assert len(note) > 15, t


def test_the_document_matches_the_current_counts():
    res = ea.run()
    tot = Counter(ea.status(t, h)[0] for rows in res.values() for t, _, h in rows)
    text = (ROOT / "docs" / "EQUATION_AUDIT.md").read_text(encoding="utf-8")
    m = re.search(r"\| \*\*All\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \|", text)
    assert m and tuple(map(int, m.groups())) == (sum(tot.values()), tot["covered"], tot["partial"], tot["gap"]), "run: python scripts/equation_audit.py --write"
