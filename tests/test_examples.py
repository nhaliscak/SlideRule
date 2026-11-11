"""The examples and the README promise things; these tests keep the Python ones and the README's numbers honest."""

import json
import re
import runpy
from pathlib import Path

import pytest

from sliderule import api
from sliderule.core.custom import calc_from_dict

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_python_api_example_prints_what_the_readme_shows(capsys):
    runpy.run_path(str(EXAMPLES / "02_python_api.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Pcr = 1754.6 kN" in out
    assert "I = 9.119e+06 mm^4" in out
    assert "Pcr (kN): [3948, 1755, 987, 632]" in out                      # the sweep quoted in the README
    assert "E = 68.9 GPa" in out and "6061-T6 aluminium: Pcr = 604 kN" in out
    assert "33.3333 m/s" in out


def test_livecalc_example_matches_the_readme_table(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["05_livecalc.py"])
    runpy.run_path(str(EXAMPLES / "05_livecalc.py"), run_name="__main__")
    out = capsys.readouterr().out
    for line in ("5 m + 30 cm            5.3 m", "120 km/h to m/s        33.333 m/s", "F = m*a                11772 N",
                 "F to kN                11.772 kN", "f(4)                   46", "20 degC to degF        68 °F"):
        assert line in out


def test_the_custom_equation_in_the_examples_and_the_readme_is_valid_and_gives_60_newtons():
    for text in (json.loads((EXAMPLES / "04_spring_force.json").read_text(encoding="utf-8")),
                 json.loads(re.search(r"```json\n(\{ \"format\".*?)\n```", (ROOT / "README.md").read_text(encoding="utf-8"), re.S).group(1))):
        assert text["format"] == "sliderule-calculation"
        calc = calc_from_dict(text["calculation"])
        assert calc.id == "custom.spring_force"
    from sliderule.core import solve

    got = solve(calc, {"k": "3 kN/m", "x": "2 cm"}, ["F"]).to_dict()
    assert got["outputs"][0]["value"] == pytest.approx(60.0)


def test_every_relative_link_in_the_readme_and_the_docs_it_moved_to_resolves():
    for md in (ROOT / "README.md", ROOT / "docs" / "FEATURES.md", ROOT / "docs" / "API.md", EXAMPLES / "README.md"):
        for _, target in re.findall(r"\[([^\]]*)\]\(([^)]+)\)", md.read_text(encoding="utf-8")):
            path = target.split("#")[0]
            if path and not path.startswith(("http", "mailto")):
                assert (md.parent / path).exists(), f"{md.name} links to {target}, which does not exist"


def test_the_readme_commands_it_prints_output_for_exist():
    cmds = ("sliderule solve", "sliderule data value", "sliderule custom import", "sliderule list")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert all(c in readme for c in cmds)
    assert api.handle("get_calculation", {"calc_id": "civil.column.euler_buckling"})["ok"]


def test_funding_file_points_at_the_donation_page():
    assert "buy_me_a_coffee: nhaliscak" in (ROOT / ".github" / "FUNDING.yml").read_text(encoding="utf-8")
