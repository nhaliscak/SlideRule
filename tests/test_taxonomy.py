"""The taxonomy mirrors docs/reference/disciplines.txt, and every sub-discipline in it has at least one calculation."""

from pathlib import Path

import pytest

from sliderule.core import solve
from sliderule.core.catalog import default_catalog
from sliderule.core.taxonomy import DISCIPLINES, SUBDISCIPLINES, TAXONOMY

REF = Path(__file__).resolve().parents[1] / "docs" / "reference" / "disciplines.txt"
CAT = default_catalog()


def parse_reference() -> dict[str, list[str]]:
    """Heading = a line followed by a blank line; the 'Emerging…' banner is a group marker, not a heading."""
    lines = [ln.rstrip("\n") for ln in REF.read_text(encoding="utf-8").splitlines()]
    out: dict[str, list[str]] = {}
    current = None
    for i, ln in enumerate(lines):
        if not ln.strip() or ln.strip() == "Emerging and Interdisciplinary Fields":
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if nxt == "" and i + 1 < len(lines):
            current = ln.strip()
            out[current] = []
        elif current is not None:
            out[current].append(ln.strip())
    return out


def test_taxonomy_matches_reference_file_exactly():
    ref = parse_reference()
    extra = {"architectural", "physics", "chemistry"}      # requested separately from the reference file
    mine = {name: subs for did, (name, _g, subs) in TAXONOMY.items() if did not in extra}
    assert set(ref) == set(mine), (set(ref) ^ set(mine))
    for name, subs in ref.items():
        assert mine[name] == subs, name


def test_every_subdiscipline_has_a_calculation():
    cov = {s: [] for s in SUBDISCIPLINES}
    for c in CAT:
        for s in c.subdisciplines:
            cov[s].append(c.id)
    assert [s for s, v in cov.items() if not v] == []


def test_every_subdiscipline_has_at_least_three_calculations():
    """The floor was one, then two; every sub-discipline now has at least three (a new sub-discipline must start with three)."""
    cov = {s: 0 for s in SUBDISCIPLINES}
    for c in CAT:
        for s in c.subdisciplines:
            cov[s] += 1
    assert sorted((n, s) for s, n in cov.items() if n < 3) == []


def test_subdisciplines_are_consistent_with_disciplines():
    """A calculation tagged with a sub-discipline should be listed under (at least one of) the discipline(s) that own it."""
    for c in CAT:
        for s in c.subdisciplines:
            owners = set(SUBDISCIPLINES[s])
            # sub-disciplines shared by name with a discipline heading are satisfied by the discipline itself
            heading_ids = {did for did, (name, _g, _s) in TAXONOMY.items() if name == s}
            assert owners & set(c.disciplines) or heading_ids & set(c.disciplines), (c.id, s, c.disciplines)


@pytest.mark.parametrize("did", list(DISCIPLINES))
def test_every_discipline_is_populated(did):
    assert [c for c in CAT if did in c.disciplines]


def test_filter_by_subdiscipline():
    ids = lambda r: {c.id for c in r}  # noqa: E731
    assert "civil.coastal.hudson_armor" in ids(CAT.search(subdisciplines=["coastal"]))
    r = CAT.search(subdisciplines=["Wind Energy Engineering"])
    assert r and all("Wind Energy Engineering" in c.subdisciplines for c in r)
    # combined filters narrow results
    assert ids(CAT.search("pressure", disciplines=["civil"], subdisciplines=["wind"])) <= ids(CAT.search(subdisciplines=["wind"]))
    assert CAT.search(subdisciplines=["no such thing"]) == []


def test_unit_restriction_blocks_non_decibel_units_for_levels():
    c = CAT.get("mechanical.acoustics.spl_from_pressure")
    ok = solve(c, {"p": "0.2 Pa"})
    assert ok.ok and ok.outputs[0]["value"] == pytest.approx(80, abs=1e-6)
    bad = solve(c, {"p": "0.2 Pa"}, output_units={"Lp": "%"})
    assert not bad.ok and bad.diagnostics[0].code in {"UNIT_NOT_ALLOWED", "DIM_MISMATCH"}
    c2 = CAT.get("mechanical.acoustics.level_combination_distance")
    s = solve(c2, {"L1": "85 %", "L2": "82 dB", "r1": "1 m", "r2": "50 m"})
    assert not s.ok and s.diagnostics[0].code == "UNIT_NOT_ALLOWED"
