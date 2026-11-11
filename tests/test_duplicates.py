"""No new calculation may silently duplicate an existing one (see scripts/check_duplicates.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_duplicates as cd  # noqa: E402


def test_no_unreviewed_duplicate_suspects():
    seen = cd.reviewed()
    fresh = [(a, b, why) for a, b, why in cd.suspects() if frozenset((a, b)) not in seen]
    assert fresh == [], f"possible duplicates: review them, then keep, merge or remove (list kept ones in tests/duplicates_reviewed.txt): {fresh}"


def test_reviewed_list_only_names_calculations_that_exist():
    from sliderule.core.catalog import default_catalog

    ids = {c.id for c in default_catalog()}
    for pair in cd.reviewed():
        assert pair <= ids, pair
