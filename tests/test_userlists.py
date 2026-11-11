"""Favorites and groups saved on disk, so another browser sees them."""

import json

import pytest
from fastapi.testclient import TestClient

from sliderule import api, userlists
from sliderule.server import create_app


def doc(updated, favorites=("a",), groups=None):
    return {"favorites": list(favorites), "groups": groups or {"G": ["a", "b"]}, "recent": ["b"], "updated": updated}


def test_nothing_saved_until_something_is_and_memory_only_has_no_file(tmp_path):
    assert api.lists_get() == {"stored": False, "lists": None}
    r = api.lists_set(doc(5))
    assert r["stored"] is False and r["lists"]["favorites"] == ["a"] and api.lists_get()["lists"]["updated"] == 5              # memory only: kept for this server run


def test_saved_to_the_file_and_read_back_by_a_new_run(tmp_path):
    f = tmp_path / "lists.json"
    userlists.configure(f)
    api.lists_set(doc(10, groups={"Course": ["x", "y"]}))
    assert json.loads(f.read_text())["groups"] == {"Course": ["x", "y"]}
    userlists.configure(f)                                                                              # a restart
    got = api.lists_get()
    assert got["stored"] and got["lists"]["favorites"] == ["a"] and got["lists"]["groups"]["Course"] == ["x", "y"] and got["lists"]["updated"] == 10


def test_an_older_copy_never_replaces_a_newer_one(tmp_path):
    userlists.configure(tmp_path / "lists.json")
    api.lists_set(doc(100, favorites=["new"]))
    r = api.lists_set(doc(50, favorites=["old"]))
    assert r["kept_newer"] and r["lists"]["favorites"] == ["new"] and api.lists_get()["lists"]["favorites"] == ["new"]
    assert not api.lists_set(doc(100, favorites=["same-age wins by being last"]))["kept_newer"]


def test_everything_unexpected_is_dropped_and_bounded():
    bad = {"favorites": ["ok", 3, None, "", "x" * 300, "ok"], "groups": {"  ": ["a"], "n" * 80: ["z", 1], **{f"g{i}": ["q"] for i in range(80)}},
           "recent": [f"r{i}" for i in range(100)], "updated": True, "basic": ["Optics", 5, "y" * 500], "extra": "ignored"}
    c = userlists.clean(bad)
    assert c["favorites"] == ["ok"] and len(c["groups"]) == 50 and ("n" * 40) in c["groups"] and c["groups"]["n" * 40] == ["z"]
    assert len(c["recent"]) == 30 and c["updated"] == 0 and c["basic"] == ["Optics"] and "extra" not in c
    with pytest.raises(userlists.ListsError):
        userlists.clean([1, 2])
    assert not api.handle("lists_set", {"lists": "nope"})["ok"]


def test_a_damaged_file_is_ignored_and_http_agrees(tmp_path):
    f = tmp_path / "lists.json"
    f.write_text("{not json")
    userlists.configure(f)
    assert api.lists_get()["lists"] is None
    c = TestClient(create_app())
    assert c.put("/api/lists", json=doc(7)).json()["lists"]["updated"] == 7
    assert c.get("/api/lists").json()["lists"]["favorites"] == ["a"] and json.loads(f.read_text())["updated"] == 7
