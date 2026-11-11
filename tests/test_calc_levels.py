"""The calculation list's levels: Basic (classical mechanics and college chemistry), Advanced (everything), and the id lists behind Custom groups and Favorites."""

import pytest
from fastapi.testclient import TestClient

from sliderule import api, cli
from sliderule.core.catalog import default_catalog
from sliderule.server import create_app

client = TestClient(create_app())


def ids(res):
    return [r["id"] for r in res["results"]]


def test_basic_is_classical_mechanics_and_advanced_is_everything():
    everything = api.list_calculations()
    basic = api.list_calculations(level="basic")
    assert everything["count"] == len(default_catalog()) and api.list_calculations(level="advanced")["count"] == everything["count"]
    assert 150 <= basic["count"] < everything["count"] / 3
    cat = default_catalog()
    assert all(api.is_basic(cat.get(i)) for i in ids(basic))
    assert {c.id for c in cat if "Classical Mechanics" in c.subdisciplines} <= set(ids(basic))                  # nothing of classical mechanics is left out
    for must in ("physics.mechanics.atwood_machine", "physics.mechanics.projectile_on_incline", "physics.mechanics.bungee_energy", "mechanical.dynamics.damped_oscillator_response"):
        assert must in ids(basic)
    assert "physics.analytical.hamilton_pendulum_trajectory" not in ids(basic)                       # analytical mechanics is Advanced
    assert "chemistry.kinetics.arrhenius_two_point" in ids(basic)                                    # college chemistry is Basic
    assert {c.id for c in cat if "chemistry" in c.disciplines and set(c.subdisciplines) & set(api.BASIC_CHEMISTRY)} <= set(ids(basic))
    advanced_chem = [c for c in cat if "chemistry" in c.disciplines and not api.is_basic(c)]
    assert advanced_chem and all(c.id not in ids(basic) for c in advanced_chem)                      # physical, quantum, polymer, colloid, bio-, atmospheric chemistry stay Advanced


def test_basic_combines_with_the_other_filters_and_the_facets_follow_it():
    both = api.list_calculations(level="basic", q="pendulum")
    assert 0 < both["count"] < api.list_calculations(q="pendulum")["count"] and set(ids(both)) <= set(ids(api.list_calculations(level="basic")))
    facet = {d["id"]: d["count"] for d in api.list_calculations(level="basic")["facets"]["disciplines"]}
    assert facet.get("physics", 0) > 20 and sum(facet.values()) >= api.list_calculations(level="basic")["count"]
    assert api.list_calculations(level="basic", subdisciplines="Nanomaterials")["count"] == 0                      # two sub-discipline filters must both hold


def test_id_lists_give_favorites_and_groups():
    pick = ["physics.mechanics.atwood_machine", "physics.analytical.kapitza_pendulum", "does.not.exist"]
    r = api.list_calculations(ids=pick)
    assert sorted(ids(r)) == sorted(pick[:2]) and r["count"] == 2                                          # unknown ids are ignored
    assert api.list_calculations(ids=[])["count"] == 0                                                      # an empty list of favorites is an empty list, not everything
    assert ids(api.list_calculations(ids=pick, q="atwood")) == ["physics.mechanics.atwood_machine"]         # the search still applies inside a group
    assert api.list_calculations(ids=pick, level="basic")["count"] == 1                                     # and so does the level
    assert {d["id"]: d["count"] for d in r["facets"]["disciplines"]}.get("physics") == 2
    many = [c.id for c in default_catalog()][: api.MAX_LIST_IDS + 50]
    assert api.list_calculations(ids=many)["count"] <= api.MAX_LIST_IDS


def test_user_equations_can_be_in_a_group():
    from sliderule import usercalcs

    usercalcs.reset()
    try:
        usercalcs.save({"name": "Double it", "description": "y is twice x", "disciplines": ["civil"], "variables": [{"key": "x", "label": "Input", "unit": "m"}, {"key": "y", "label": "Output", "unit": "m"}],
                        "equations": [{"title": "double", "text": "y = 2*x"}], "outputs": ["y"], "assumptions": [], "references": [], "validity": []})
        mine = [c.id for c in default_catalog() if c.custom][0]
        assert ids(api.list_calculations(ids=[mine, "physics.mechanics.atwood_machine"], source="custom")) == [mine]
    finally:
        usercalcs.reset()


def test_bad_level_is_refused_and_meta_reports_the_levels():
    with pytest.raises(api.ApiError):
        api.list_calculations(level="expert")
    assert api.handle("list_calculations", {"level": "expert"})["ok"] is False
    m = api.meta()["levels"]
    assert m["basic"]["subdiscipline"] == "Classical Mechanics" and m["basic"]["count"] == api.list_calculations(level="basic")["count"] and m["advanced"]["count"] == len(default_catalog())


def test_http_endpoint_and_rpc_agree_with_the_api():
    direct = api.list_calculations(level="basic")
    http = client.get("/api/calculations", params={"level": "basic"}).json()
    assert http["count"] == direct["count"] and ids(http) == ids(direct)
    rpc = client.post("/api/rpc", json={"method": "list_calculations", "params": {"level": "basic", "ids": ["physics.mechanics.atwood_machine"]}}).json()["result"]
    assert ids(rpc) == ["physics.mechanics.atwood_machine"]
    http_ids = client.get("/api/calculations", params={"ids": ["physics.mechanics.atwood_machine", "physics.mechanics.bungee_energy"]}).json()
    assert http_ids["count"] == 2
    assert client.get("/api/calculations", params={"level": "expert"}).status_code == 400


def test_command_line_level(capsys):
    import sys

    argv = sys.argv
    sys.argv = ["sliderule", "list", "--level", "basic", "atwood"]
    try:
        cli.main()
    except SystemExit:
        pass
    finally:
        sys.argv = argv
    out = capsys.readouterr().out
    assert "physics.mechanics.atwood_machine" in out and "chemistry" not in out


def test_every_facet_follows_the_other_filters():
    base = api.list_calculations()["facets"]
    r = api.list_calculations(level="basic", disciplines=["physics"])
    f = r["facets"]
    subs = {x["name"]: x["count"] for x in f["subdisciplines"]}
    assert subs["Classical Mechanics"] == 57 < r["count"] and subs["General Chemistry"] > 0 and sum(1 for n in subs.values() if n) < sum(1 for x in base["subdisciplines"] if x["count"])
    assert 0 < len(f["variables"]) < len(base["variables"]) and 0 < len(f["solves"]) < len(base["solves"])
    # a facet ignores its own filter, so a chosen option's siblings stay on offer
    two = api.list_calculations(subdisciplines=["Classical Mechanics"])["facets"]
    assert sum(1 for x in two["subdisciplines"] if x["count"]) == sum(1 for x in base["subdisciplines"] if x["count"])
    # a narrower set never offers more than the whole catalogue
    narrow = api.list_calculations(variables=["force"], level="basic")["facets"]["solves"]
    assert narrow and set(narrow) <= set(base["solves"]) and len(narrow) < len(base["solves"])


def test_users_own_basic_replaces_the_default_list():
    cat = default_catalog()
    default = api.list_calculations(level="basic")
    mine = api.list_calculations(level="basic", basic=["Optics"])
    assert 0 < mine["count"] and all("Optics" in cat.get(i).subdisciplines for i in ids(mine)) and ids(mine) != ids(default)
    assert api.list_calculations(level="basic", basic=[])["count"] == 0
    both = api.list_calculations(level="basic", basic=["Optics", "Classical Mechanics"])
    assert both["count"] > mine["count"]
    assert api.list_calculations(basic=["Optics"])["count"] == len(cat)                 # only the Basic level looks at it
    http = client.get("/api/calculations", params={"level": "basic", "basic": ["Optics"]}).json()
    assert ids(http) == ids(mine)
    assert all(f["count"] == 0 for f in api.list_calculations(level="basic", basic=["Optics"])["facets"]["subdisciplines"] if f["name"] == "General Chemistry")
