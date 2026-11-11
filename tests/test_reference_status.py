"""The list of references not checked against a source stays tied to the library."""

from sliderule import api
from sliderule.core.catalog import default_catalog
from sliderule.library.reference_status import UNVERIFIED, notes_for


def test_every_entry_points_at_a_reference_that_still_says_that():
    cat = default_catalog()
    for cid, items in UNVERIFIED.items():
        c = cat.get(cid)                                           # the calculation exists
        for fragment, note in items:
            assert any(fragment in r for r in c.references), f"{cid}: no reference contains {fragment!r} (corrected? then delete the entry)"
            assert len(note) > 30


def test_api_reports_them_with_the_full_reference_and_other_calculations_have_none():
    d = api.get_calculation("green.lca.gwp_co2_equivalent")
    assert len(d["unverified_references"]) == 1 and d["unverified_references"][0]["reference"] in d["references"] and "7.SM.6" in d["unverified_references"][0]["note"]
    assert api.get_calculation("physics.mechanics.atwood_machine")["unverified_references"] == []
    for cid in ("chemistry.physical.ranz_marshall_mass_transfer", "civil.earthquake.elastic_response_spectrum", "healthinfo.telemedicine.latency_budget"):
        assert api.get_calculation(cid)["unverified_references"] == []            # looked up on 2026-10-30
    assert notes_for("no.such.calc", ["x"]) == []


def test_the_page_and_scripts_are_revalidated_but_vendored_libraries_are_cached():
    from fastapi.testclient import TestClient
    from sliderule.server import create_app

    c = TestClient(create_app())
    for path in ("/", "/js/app.js", "/css/style.css"):
        r = c.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache" and r.headers.get("etag"), path
    again = c.get("/js/app.js", headers={"If-None-Match": c.get("/js/app.js").headers["etag"]})
    assert again.status_code == 304
    assert "max-age" in c.get("/vendor/katex/katex.min.css").headers["cache-control"]
