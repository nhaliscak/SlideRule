import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sliderule import api, design, design_export
from sliderule.core.catalog import default_catalog
from sliderule.core.engine import parse_quantity
from sliderule.server import create_app
from sliderule.units import convert

CAT = default_catalog()
client = TestClient(create_app(serve_frontend=False))
KATEX = Path(design_export.__file__).parent / "web" / "vendor" / "katex" / "katex.min.js"
EXAMPLES = design.examples()


def ex_graph(i):
    return EXAMPLES[i]["graph"]


def test_formats_and_modes():
    g = ex_graph(1)
    tex = design_export.export_system(g, "latex")
    assert tex["ok"] and tex["filename"] == "sliderule-system.tex" and tex["mime"].startswith("application/")
    assert r"\documentclass" in tex["content"] and r"\end{document}" in tex["content"]
    md = design_export.export_system(g, "markdown", "symbolic")
    assert md["ok"] and md["filename"] == "sliderule-system-symbolic.md" and "$$" in md["content"]
    num = design_export.export_system(g, "latex", "numeric", standalone=False)
    assert num["ok"] and r"\documentclass" not in num["content"] and num["filename"].endswith("-numeric.tex")
    sym = design_export.export_system(g, "markdown", "symbolic")["content"]
    both = design_export.export_system(g, "markdown", "both")["content"]
    assert len(both) > len(sym)


def test_html_export_is_printable_and_escaped():
    r = design_export.export_system(ex_graph(1), "html")
    assert r["ok"] and r["filename"] == "sliderule-system.html" and r["mime"] == "text/html"
    c = r["content"]
    assert c.startswith("<!doctype html>") and "@media print" in c and c.rstrip().endswith("</html>")
    # fully offline: KaTeX script, stylesheet and fonts are embedded, nothing is fetched
    assert "data:font/woff2;base64," in c and "<link" not in c and not re.search(r"<script[^>]+src=", c) and c.count("<script") == c.count("</script") == 2
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__(); self.tex = []; self._in = False
        def handle_starttag(self, tag, attrs):
            self._in = tag == "span" and "tex pending" in dict(attrs).get("class", "")
        def handle_data(self, d):
            if self._in:
                self.tex.append(d); self._in = False
    p = P(); p.feed(c)
    assert len(p.tex) > 50 and "<" not in "".join(p.tex).replace("\\lt", "")   # math survives as text, not markup
    assert _katex_check(sorted(set(p.tex))) == []


def _run_script(src: str) -> str:
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(src, "sliderule-system.py", "exec"), {"__name__": "__main__"})
    return buf.getvalue()


def test_python_script_reproduces_the_solver():
    for ex in EXAMPLES:
        r = design_export.export_system(ex["graph"], "python")
        assert r["ok"] and r["filename"] == "sliderule-system.py" and r["mime"] == "text/x-python"
        out = _run_script(r["content"])
        assert "matches the SlideRule reference values" in out, (ex["id"], out)


def test_python_script_converts_offset_units_and_accepts_overrides():
    c = CAT.get("mechanical.thermo.ideal_gas_law")
    roles = design.default_roles(c)
    g = {"version": 1, "wires": [], "blocks": [{"id": "gas", "calc": c.id, "x": 0, "y": 0, "roles": roles, "values": {"T": "25 degC", "P": "101.325 kPa", "n": "1 mol"}}]}
    src = design_export.export_system(g, "python")["content"]
    assert "to_si(25.0, 1.0, 273.15)" in src       # (x + shift) * factor
    ns: dict = {"__name__": "sliderule_system"}
    exec(compile(src, "s.py", "exec"), ns)
    base = ns["evaluate"]()
    hot = ns["evaluate"]({"T__gas": 2 * 298.15})
    assert all(hot[k] == pytest.approx(base[k] * 2) for k in base if k.startswith("V"))


def test_html_falls_back_to_cdn_when_katex_is_not_bundled(monkeypatch):
    monkeypatch.setattr(design_export, "_katex_inline", lambda: None)
    c = design_export.export_system(ex_graph(1), "html")["content"]
    assert "cdn.jsdelivr.net/npm/katex@" in c and "data:font" not in c


def test_invalid_requests_report_diagnostics():
    assert not design_export.export_system({"blocks": [], "wires": []})["ok"]
    bad = design_export.export_system(ex_graph(0), "docx")
    assert not bad["ok"]


def test_every_block_and_wire_appears():
    for ex in EXAMPLES:
        out = design_export.export_system(ex["graph"], "markdown")["content"]
        for b in ex["graph"]["blocks"]:
            assert CAT.get(b["calc"]).name in out, (ex["id"], b["calc"])


def test_closed_form_matches_solver():
    """Each exported closed form, evaluated at the block inputs, reproduces solve_system's SI outputs."""
    for ex in EXAMPLES:
        g = ex["graph"]
        res = design.solve_system(g)
        model = design_export.system_model(g)
        assert model["closed"]
        for (bid, key), expr in model["closed"].items():
            subs = {}
            for (b2, k2), v in model["free"].items():
                b = model["blocks"][b2]
                text = (b.get("values") or {}).get(k2)
                val, unit = parse_quantity(text) if text else (v.default if v.default is not None else v.constant, v.unit)
                subs[model["qsym"][(b2, k2)]] = convert(val, (unit or v.unit), v.si)
            got = float(expr.xreplace(subs))
            want = next(o for o in res["blocks"][bid]["outputs"] if o["key"] == key)["si_value"]
            assert got == pytest.approx(want, rel=1e-7), (ex["id"], bid, key)


def _math_strings(text: str, fmt: str) -> list[str]:
    if fmt == "markdown":
        return [m.strip() for m in re.findall(r"\$\$(.+?)\$\$", text, re.S)] + re.findall(r"(?<![$\\])\$([^$\n]+)\$", text)
    out = [m.strip() for m in re.findall(r"\\\[(.+?)\\\]", text, re.S)]
    return out + re.findall(r"(?<!\\)\$([^$\n]+)\$", text)


def _katex_check(strings: list[str]):
    node = shutil.which("node")
    if not node or not KATEX.exists():
        pytest.skip("node or vendored KaTeX not available")
    script = (
        "const k=require(process.argv[1]);const items=JSON.parse(require('fs').readFileSync(0,'utf8'));"
        "const bad=[];for(const s of items){try{k.renderToString(s,{throwOnError:true,strict:'ignore'})}catch(e){bad.push([s.slice(0,120),String(e.message)])}}"
        "console.log(JSON.stringify(bad));"
    )
    r = subprocess.run([node, "-e", script, str(KATEX)], input=json.dumps(strings), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _display_tex(tex: str) -> list[str]:
    # KaTeX has no \tag*{\small\textit{..}} support issues, but strip the note tag to keep it about the math
    return [re.sub(r"\\tag\*\{.*\}\s*$", "", s, flags=re.S) for s in _math_strings(tex, "latex")]


def test_katex_renders_every_example_math():
    strings = []
    for ex in EXAMPLES:
        for mode in ("both", "symbolic", "numeric"):
            strings += _math_strings(design_export.export_system(ex["graph"], "markdown", mode)["content"], "markdown")
            strings += _display_tex(design_export.export_system(ex["graph"], "latex", mode)["content"])
    assert len(strings) > 100
    assert _katex_check(sorted(set(strings))) == []


def _single_block(c):
    """One block using the calculation's own worked example: example values are inputs, everything else is computed."""
    roles = {v.key: "constant" if v.is_constant else ("input" if v.key in c.example and v.key not in c.outputs else "output") for v in c.variables}
    values = {k: val for k, val in c.example.items() if roles.get(k) == "input"}
    return {"version": 1, "wires": [], "blocks": [{"id": "b1", "calc": c.id, "x": 0, "y": 0, "roles": roles, "values": values}]}


def test_every_library_calc_exports_as_a_single_block_system():
    strings, failures, script_failures = set(), [], []
    for c in CAT:
        g = _single_block(c)
        r = design_export.export_system(g, "markdown")
        if not r["ok"]:
            failures.append((c.id, r["diagnostics"][:1]))
            continue
        strings.update(_math_strings(r["content"], "markdown"))
        try:
            py = design_export.export_system(g, "python")
            if design_export._has_numeric_ode(c.id):          # events, delays, boundary-value problems and PDEs cannot be written as a script (plain initial-value problems can)
                if py["ok"] or py["diagnostics"][0]["code"] != "NUMERIC_ODE":
                    script_failures.append(c.id)
            elif "matches the SlideRule reference values" not in _run_script(py["content"]):
                script_failures.append(c.id)
        except Exception as exc:   # noqa: BLE001 - report which calc broke
            script_failures.append(f"{c.id}: {type(exc).__name__}: {exc}")
    assert not failures, failures[:5]
    assert not script_failures, script_failures[:5]
    assert len(strings) > 3000
    assert _katex_check(sorted(strings)) == []


def test_api_and_http_endpoints_agree():
    body = {"graph": ex_graph(0), "format": "markdown", "mode": "symbolic", "sig_figs": 4, "standalone": True}
    direct = api.handle("design_export", body)["result"]
    http = client.post("/api/design/export", json=body).json()
    assert direct["ok"] and http["content"] == direct["content"]
    assert client.post("/api/rpc", json={"method": "design_export", "params": body}).json()["result"]["content"] == direct["content"]


def test_pandoc_parses_exports_without_warnings(tmp_path):
    pandoc = shutil.which("pandoc")
    if not pandoc:
        pytest.skip("pandoc not installed")
    for fmt, ext, reader in (("latex", "tex", "latex"), ("markdown", "md", "markdown+tex_math_dollars")):
        f = tmp_path / f"s.{ext}"
        f.write_text(design_export.export_system(ex_graph(1), fmt)["content"], encoding="utf-8")
        r = subprocess.run([pandoc, "-f", reader, "-t", "native", str(f)], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0 and not r.stderr.strip(), (fmt, r.stderr[:300])
