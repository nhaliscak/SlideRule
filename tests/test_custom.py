import copy
import json

import pytest
from fastapi.testclient import TestClient

from sliderule import api, cli, design, design_export, usercalcs
from sliderule.core import solve
from sliderule.core.catalog import default_catalog
from sliderule.core.custom import CustomError, calc_from_dict, calc_to_dict, parse_document
from sliderule.core.safeparse import UnsafeExpression, check_expression
from sliderule.server import create_app

client = TestClient(create_app(serve_frontend=False))

SPRING = {
    "id": "custom.spring", "name": "Spring force", "description": "Hooke's law", "disciplines": ["mechanical"],
    "variables": [
        {"key": "F", "label": "Force", "unit": "N"},
        {"key": "k", "label": "Stiffness", "unit": "N/m", "example": "2 kN/m"},
        {"key": "x", "label": "Extension", "unit": "m", "example": "5 cm"}],
    "equations": [{"title": "Hooke's law", "text": "F = k*x"}], "outputs": ["F"],
}


@pytest.fixture(autouse=True)
def clean():
    usercalcs.reset()
    yield
    usercalcs.reset()


def spring(**changes):
    d = copy.deepcopy(SPRING)
    d.update(changes)
    return d


# ---------------------------------------------------------------- safety of equation text

@pytest.mark.parametrize("text", [
    "__import__('os').system('id')", "x.__class__", "().__class__.__bases__[0]", "[i for i in x]", "lambda: 1", "9**9**9",
    "2**(3**9)", "10**1000000", "'abc'", "factorial(10**9)", "open('f')", "x[0]", "x@x", "x//2", "1e300", "exec('1')", "x if x else 1",
])
def test_unsafe_expressions_are_refused(text):
    with pytest.raises(UnsafeExpression):
        check_expression(text, {"x": 1, "factorial": 1})


@pytest.mark.parametrize("text", ["x**2/2 + sqrt(x)", "Piecewise((x, x > 1), (2*x, True))", "x^2", "2**10", "2**(1/6)", "1e-3*x", "log10(x)"])
def test_ordinary_expressions_are_accepted(text):
    check_expression(text, {"x": 1, "sqrt": 1, "Piecewise": 1, "log10": 1})


def test_malicious_equation_never_runs(tmp_path):
    marker = tmp_path / "pwned"
    for evil in (f"F = k*x + __import__('os').system('touch {marker}')", f"F = k*x + exec(\"open('{marker}','w')\")"):
        with pytest.raises(CustomError):
            calc_from_dict(spring(equations=[{"text": evil}]))
    assert not marker.exists()


def test_dimensionally_wrong_equation_is_refused_with_a_reason():
    with pytest.raises(CustomError) as e:
        calc_from_dict(spring(equations=[{"text": "F = k*x**2"}]))
    assert "not dimensionally homogeneous" in e.value.errors[0]["message"]


@pytest.mark.parametrize("change,field", [
    ({"id": "mine"}, "id"), ({"id": "custom.Bad Id"}, "id"), ({"name": ""}, "name"), ({"disciplines": ["nonsense"]}, "disciplines"),
    ({"outputs": ["Z"]}, "outputs"), ({"outputs": ["k"], "equations": [{"text": "F = k*x"}], "variables": [
        {"key": "F", "label": "F", "unit": "N"}, {"key": "k", "label": "k", "unit": "N/m", "constant": 5}, {"key": "x", "label": "x", "unit": "m"}]}, "outputs"),
    ({"variables": []}, "variables"), ({"equations": []}, "equations"), ({"equations": [{"text": "F == k*x"}]}, "equations"),
])
def test_structural_errors_are_reported_by_field(change, field):
    with pytest.raises(CustomError) as e:
        calc_from_dict(spring(**change))
    assert field in {x["field"].split("[")[0].split(".")[0] for x in e.value.errors}


def test_bad_units_symbols_and_unused_variables():
    bad_unit = spring(variables=[{**SPRING["variables"][0], "unit": "furlongs/fortnightish"}, *SPRING["variables"][1:]])
    with pytest.raises(CustomError) as e:
        calc_from_dict(bad_unit)
    assert e.value.errors[0]["field"] == "variables[0].unit"
    dup = spring(variables=[*SPRING["variables"], {"key": "x", "label": "again", "unit": "m"}])
    with pytest.raises(CustomError) as e:
        calc_from_dict(dup)
    assert "used twice" in e.value.errors[0]["message"]
    unused = spring(variables=[*SPRING["variables"], {"key": "w", "label": "Unused", "unit": "m"}])
    with pytest.raises(CustomError) as e:
        calc_from_dict(unused)
    assert "never used" in e.value.errors[0]["message"]
    with pytest.raises(CustomError):
        calc_from_dict(spring(variables=[{**SPRING["variables"][0], "latex": r"\input{/etc/passwd}"}, *SPRING["variables"][1:]]))


def test_subdiscipline_adds_its_owning_discipline():
    c = calc_from_dict(spring(disciplines=[], subdisciplines=["Hydraulic Engineering"]))
    assert c.disciplines and c.subdisciplines == ["Hydraulic Engineering"]


# ---------------------------------------------------------------- a user calculation behaves like a library one

def test_user_calculation_solves_in_any_direction_with_steps():
    c = calc_from_dict(SPRING)
    sol = solve(c, {"k": "2 kN/m", "x": "5 cm"}).to_dict()
    assert sol["outputs"][0]["si_value"] == pytest.approx(100.0)
    back = solve(c, {"F": "100 N", "x": "5 cm"}, ["k"]).to_dict()
    assert back["outputs"][0]["si_value"] == pytest.approx(2000.0)
    assert sol["steps"]["symbolic"] and sol["steps"]["numeric"]


def test_every_library_calculation_survives_a_round_trip_through_the_file_format():
    cat = default_catalog()
    failures = []
    for lib in list(cat):
        doc = calc_to_dict(lib)
        doc["id"] = "custom." + lib.id.replace(".", "_")
        try:
            c = calc_from_dict(json.loads(json.dumps(doc)))
        except CustomError as exc:
            failures.append((lib.id, exc.errors[:1]))
            continue
        inputs = {k: v for k, v in lib.example.items() if k not in lib.outputs and not lib.by_key[k].is_constant}
        a = solve(lib, inputs).to_dict()["outputs"]
        b = solve(c, inputs).to_dict()["outputs"]
        assert [(o["key"], o["si_value"]) for o in a] == [(o["key"], o["si_value"]) for o in b], lib.id
    assert not failures, failures[:5]


# ---------------------------------------------------------------- the user library: save, list, share, persist

def test_validate_reports_solvable_variables_and_example_result():
    r = api.custom_validate(SPRING)
    assert r["ok"] and set(r["solvable_for"]) == {"F", "k", "x"}
    assert r["example_result"]["outputs"][0]["text"].startswith("100")
    assert r["equations"][0]["latex"] == "F = k x"
    bad = api.custom_validate(spring(equations=[{"text": "F = k*x**2"}]))
    assert not bad["ok"] and bad["errors"][0]["field"] == "equations"


def test_save_list_search_delete_and_conflict():
    before = api.list_calculations("spring")["count"]      # the library has springs of its own
    r = api.handle("custom_save", {"calculation": SPRING})
    assert r["ok"] and r["result"]["id"] == "custom.spring"
    assert api.meta()["custom_count"] == 1
    found = api.list_calculations("spring", source="custom")
    assert found["count"] == 1 and found["results"][0]["custom"]
    assert api.list_calculations("spring")["count"] == before + 1
    assert api.list_calculations("spring", source="library")["count"] == before
    assert api.get_calculation("custom.spring")["custom"] is True
    dup = api.handle("custom_save", {"calculation": SPRING})
    assert not dup["ok"] and dup["error"]["status"] == 409
    assert api.handle("custom_save", {"calculation": SPRING, "replace": True})["ok"]
    assert api.handle("custom_delete", {"calc_id": "custom.spring"})["ok"]
    assert api.list_calculations("spring")["count"] == before
    assert api.handle("custom_delete", {"calc_id": "custom.spring"})["error"]["status"] == 404
    assert api.handle("custom_delete", {"calc_id": "mechanical.statics.something_in_the_library"})["error"]["status"] == 404


def test_a_user_calculation_can_never_replace_a_library_one():
    lib_id = next(iter(default_catalog())).id
    with pytest.raises(CustomError):
        calc_from_dict(spring(id=lib_id))
    assert api.handle("custom_delete", {"calc_id": lib_id})["error"]["status"] == 404


def test_ids_cannot_escape_the_equations_folder(tmp_path):
    usercalcs.configure(tmp_path / "eq")
    for evil in ("custom.../../evil", "custom.a/b", "custom.a\\b", "../custom.x", "custom."):
        with pytest.raises(CustomError):
            calc_from_dict(spring(id=evil))
    api.custom_save(spring(id="custom.fine"))
    assert [p.name for p in (tmp_path / "eq").iterdir()] == ["fine.json"] and not (tmp_path / "evil.json").exists()


def test_save_without_an_id_generates_one():
    r = api.custom_save({**SPRING, "id": ""})
    assert r["id"] == "custom.spring_force"
    assert api.custom_save({**SPRING, "id": ""})["id"] == "custom.spring_force_2"


def test_export_import_round_trip_and_conflicts():
    api.custom_save(SPRING)
    api.custom_save(spring(id="custom.other", name="Other"))
    out = api.custom_export()
    assert out["count"] == 2 and out["document"]["format"] == "sliderule-calculations"
    assert api.custom_export(["custom.spring"])["filename"] == "spring.sliderule.json"
    doc = json.loads(json.dumps(out["document"]))
    usercalcs.reset()
    res = api.custom_import(doc)
    assert [r["status"] for r in res["results"]] == ["added", "added"] and res["imported"] == 2
    again = api.custom_import(doc)
    assert [r["status"] for r in again["results"]] == ["unchanged", "unchanged"]
    changed = copy.deepcopy(doc)
    changed["calculations"][0]["name"] = "Spring force v2"
    ask = api.custom_import(changed, "ask")
    assert ask["results"][0]["status"] == "conflict" and api.get_calculation("custom.spring")["name"] == "Spring force"
    assert api.custom_import(changed, "skip")["results"][0]["status"] == "skipped"
    ren = api.custom_import(changed, "rename")["results"][0]
    assert ren["status"] == "renamed" and ren["new_id"] == "custom.spring_2" and api.get_calculation("custom.spring_2")
    assert api.custom_import(changed, "replace")["results"][0]["status"] == "replaced"
    assert api.get_calculation("custom.spring")["name"] == "Spring force v2"
    dry = api.custom_import({**changed, "calculations": [spring(id="custom.fresh", name="Fresh")]}, "rename", dry_run=True)
    assert dry["results"][0]["status"] == "added" and not api.list_calculations("fresh", source="custom")["count"]


def test_import_accepts_single_and_bare_files_and_rejects_bad_ones():
    assert parse_document({"format": "sliderule-calculation", "version": 1, "calculation": SPRING}) == [SPRING]
    assert parse_document(SPRING) == [SPRING]
    for bad in ([], {"format": "something-else"}, {"format": "sliderule-calculations", "version": 99, "calculations": [SPRING]},
                {"format": "sliderule-calculations", "calculations": []}):
        with pytest.raises(CustomError):
            parse_document(bad)
    mixed = api.custom_import({"format": "sliderule-calculations", "calculations": [SPRING, spring(id="custom.bad", equations=[{"text": "F = k*x**2"}])]})
    assert [r["status"] for r in mixed["results"]] == ["added", "error"] and mixed["imported"] == 1
    assert mixed["results"][1]["errors"][0]["field"] == "equations"


def test_calculations_persist_as_plain_files_and_reload(tmp_path):
    assert usercalcs.configure(tmp_path) == []
    api.custom_save(SPRING)
    f = tmp_path / "spring.json"
    assert json.loads(f.read_text())["calculation"]["id"] == "custom.spring"
    usercalcs.reset()
    assert not [r for r in api.list_calculations("spring")["results"] if r["custom"]]
    assert usercalcs.configure(tmp_path) == [] and api.get_calculation("custom.spring")["name"] == "Spring force"
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "evil.json").write_text(json.dumps(spring(id="custom.evil", equations=[{"text": "F = __import__('os')"}])))
    usercalcs.reset()
    problems = usercalcs.configure(tmp_path)
    assert {p["file"] for p in problems} == {"broken.json", "evil.json"} and api.get_calculation("custom.spring")
    api.custom_delete("custom.spring")
    assert not f.exists()


def test_template_from_a_library_calculation_is_editable_and_valid():
    t = api.custom_template("civil.hydraulics.manning")["calculation"] if "civil.hydraulics.manning" in {c.id for c in default_catalog()} else \
        api.custom_template(next(iter(default_catalog())).id)["calculation"]
    assert t["id"] == "" and t["name"].startswith("Copy of")
    assert api.custom_save(t)["id"].startswith("custom.copy_of")


# ---------------------------------------------------------------- HTTP

def test_http_endpoints():
    assert client.post("/api/custom/validate", json={"calculation": SPRING}).json()["ok"]
    assert client.post("/api/custom", json={"calculation": SPRING}).json()["id"] == "custom.spring"
    r = client.post("/api/custom", json={"calculation": SPRING})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "INVALID_CALCULATION"
    bad = client.post("/api/custom", json={"calculation": spring(id="custom.x", equations=[{"text": "F = k*x**2"}])})
    assert bad.status_code == 400 and bad.json()["detail"]["details"][0]["field"] == "equations"
    assert [c["id"] for c in client.get("/api/custom").json()["calculations"]] == ["custom.spring"]
    exp = client.get("/api/custom/export").json()
    assert exp["count"] == 1
    assert client.post("/api/custom/import", json={"document": exp["document"], "on_conflict": "ask"}).json()["results"][0]["status"] == "unchanged"
    assert client.post("/api/calculations/custom.spring/solve", json={"inputs": {"k": "2 kN/m", "x": "5 cm"}}).json()["outputs"][0]["si_value"] == pytest.approx(100)
    assert client.delete("/api/custom/custom.spring").json()["ok"]
    assert client.delete("/api/custom/custom.spring").status_code == 404
    rpc = client.post("/api/rpc", json={"method": "custom_save", "params": {"calculation": SPRING}}).json()
    assert rpc["ok"]


# ---------------------------------------------------------------- CLI

def test_cli_import_list_solve_export_remove(tmp_path, capsys):
    src = tmp_path / "spring.json"
    src.write_text(json.dumps({"format": "sliderule-calculation", "version": 1, "calculation": SPRING}))
    folder = str(tmp_path / "eq")
    run = lambda *a: cli.main(["--equations-dir", folder, *a])   # noqa: E731
    assert run("custom", "import", str(src)) == 0
    usercalcs.reset()
    assert run("custom", "list") == 0 and "custom.spring" in capsys.readouterr().out
    usercalcs.reset()
    assert run("solve", "custom.spring", "--example") == 0 and "F = 100 N" in capsys.readouterr().out
    usercalcs.reset()
    out = tmp_path / "bundle.json"
    assert run("custom", "export", "-o", str(out)) == 0 and json.loads(out.read_text())["format"] == "sliderule-calculations"
    usercalcs.reset()
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(spring(equations=[{"text": "F = k*x**2"}])))
    assert run("custom", "validate", str(bad)) == 1
    usercalcs.reset()
    assert run("custom", "remove", "custom.spring") == 0
    assert not (tmp_path / "eq" / "spring.json").exists()


# ---------------------------------------------------------------- inside System Design and its exports

def test_custom_blocks_work_in_system_design_and_every_export():
    api.custom_save(SPRING)
    api.custom_save(spring(id="custom.energy", name="Spring energy", variables=[
        {"key": "E", "label": "Energy", "unit": "J"}, {"key": "F", "label": "Force", "unit": "N"}, {"key": "x", "label": "Extension", "unit": "m", "example": "5 cm"}],
        equations=[{"text": "E = F*x/2"}], outputs=["E"]))
    g = {"version": 1, "blocks": [
        {"id": "s", "calc": "custom.spring", "x": 0, "y": 0, "values": {"k": "2 kN/m", "x": "5 cm"}},
        {"id": "e", "calc": "custom.energy", "x": 300, "y": 0, "values": {"x": "5 cm"}}],
        "wires": [{"id": "w1", "from": {"block": "s", "key": "F"}, "to": {"block": "e", "key": "F"}}]}
    r = design.solve_system(g)
    assert r["ok"]
    assert next(o for o in r["blocks"]["e"]["outputs"] if o["key"] == "E")["si_value"] == pytest.approx(2.5)
    for fmt in ("latex", "markdown", "html", "python"):
        out = design_export.export_system(g, fmt)
        assert out["ok"], (fmt, out)
        assert "user-defined" in out["content"], fmt
    py = design_export.export_system(g, "python")["content"]
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(py, "s.py", "exec"), {"__name__": "__main__"})
    assert "matches the SlideRule reference values" in buf.getvalue()
