"""System export as MATLAB / Octave code and as an Excel workbook with formulas.

No MATLAB or Excel is needed: the generated formulas are translated back into Python (a small independent translator) and must reproduce SlideRule's own
results, and, where LibreOffice is installed, the workbook is recalculated by a real spreadsheet engine from deliberately wrong cached values.
"""

import base64
import copy
import io
import math
import random
import re
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree

import pytest
import sympy as sp
from scipy import special

from sliderule import api, design, design_code, design_export
from sliderule.core.catalog import default_catalog


def w(i, sb, sk, db, dk):
    return {"id": i, "from": {"block": sb, "key": sk}, "to": {"block": db, "key": dk}}


def wind():
    return copy.deepcopy(design.examples()[0]["graph"])          # a copy: tests change it


# ---------------------------------------------------------------- translators back into Python

def _split_args(text):
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        depth += ch == "("
        depth -= ch == ")"
        cur += ch
    return [*out, cur]


def _lazy_if(f):
    while "_if(" in f:
        i = f.index("_if(")
        j, depth = i + 4, 1
        while depth:
            depth += f[j] == "("
            depth -= f[j] == ")"
            j += 1
        c, a, b = (_lazy_if(x) for x in _split_args(f[i + 4:j - 1]))
        f = f[:i] + f"(({a}) if ({c}) else ({b}))" + f[j:]
    return f


_XL_NAMES = (("LOG10", "math.log10"), ("LOG", "_logb"), ("ERFC", "math.erfc"), ("BESSELJ", "_bj"), ("BESSELY", "_by"), ("BESSELI", "_bi"), ("BESSELK", "_bk"), ("SQRT", "math.sqrt"), ("EXP", "math.exp"), ("LN", "math.log"), ("SINH", "math.sinh"),
             ("COSH", "math.cosh"), ("TANH", "math.tanh"), ("ASINH", "math.asinh"), ("ACOSH", "math.acosh"), ("ATANH", "math.atanh"), ("ASIN", "math.asin"),
             ("ACOS", "math.acos"), ("ATAN2", "_atan2x"), ("ATAN", "math.atan"), ("SIN", "math.sin"), ("COS", "math.cos"), ("TAN", "math.tan"), ("ABS", "abs"),
             ("SIGN", "_sign"), ("ERF", "math.erf"), ("MAX", "max"), ("MIN", "min"), ("FACT", "math.factorial"), ("INT", "math.floor"), ("GAMMALN", "math.lgamma"),
             ("AND", "_and"), ("OR", "_or"), ("NOT", "_not"))


def excel_eval(formula, env):
    f = formula.replace("<>", "!=")
    f = re.sub(r"(?<![<>!=])=(?!=)", "==", f)
    f = f.replace("^", "**").replace("PI()", "math.pi").replace("NA()", "float('nan')").replace("TRUE", "True")
    f = re.sub(r"\bIF\(", "_if(", f)
    for a, b in _XL_NAMES:
        f = re.sub(rf"(?<![A-Za-z_]){a}\(", b + "(", f)
    ns = {"math": math, "_if": None, "_sign": lambda x: (x > 0) - (x < 0), "_and": lambda *a: all(a), "_or": lambda *a: any(a), "_not": lambda x: not x,
          "_logb": lambda x, b: math.log(x, b), "_bj": lambda x, n: special.jv(n, x), "_by": lambda x, n: special.yv(n, x), "_bi": lambda x, n: special.iv(n, x), "_bk": lambda x, n: special.kv(n, x), "_atan2x": lambda x, y: math.atan2(y, x), **env}      # Excel's ATAN2 takes (x, y)
    return eval(_lazy_if(f), ns)                                                                    # noqa: S307 - our own generated formula


def matlab_eval(code, env):
    c = re.sub(r"sum\(arrayfun\(@\((\w+)\) (.*), (\d+):(\d+)\)\)", lambda m: f"sum(({m.group(2)}) for {m.group(1)} in range({m.group(3)}, {int(m.group(4)) + 1}))", code).replace("^", "**")
    for a, b in (("log10", "math.log10"), ("log2", "math.log2"), ("sqrt", "math.sqrt"), ("exp", "math.exp"), ("log", "math.log"), ("atan2", "math.atan2"), ("atan", "math.atan"),
                 ("asin", "math.asin"), ("acos", "math.acos"), ("sinh", "math.sinh"), ("cosh", "math.cosh"), ("tanh", "math.tanh"), ("sin", "math.sin"), ("cos", "math.cos"),
                 ("tan", "math.tan"), ("abs", "abs"), ("max", "max"), ("min", "min"), ("erf", "math.erf"), ("pi", "math.pi")):
        c = re.sub(rf"(?<![A-Za-z_.0-9]){a}(?=\()" if a != "pi" else r"(?<![A-Za-z_.0-9])pi(?![A-Za-z_0-9(])", b, c)
    c = c.replace("~", " not ").replace("&&", " and ").replace("||", " or ").replace("&", " and ").replace("|", " or ")
    return eval(c, {"math": math, **env})                                                            # noqa: S307


def run_matlab(content):
    """Execute the assignments of a generated script (if/elseif/else blocks included) and return the variables."""
    env: dict = {}
    lines = [ln.split("%")[0].rstrip() for ln in content.splitlines() if not ln.lstrip().startswith(("%", "fprintf", "names", "disp"))]
    stack = []                                         # (condition satisfied, any branch taken)
    for ln in lines:
        s = ln.strip()
        if not s or s in ("names = {};", "got = [];", "ref = [];"):
            continue
        if s.startswith("if all(") or s == "else" and not stack:
            break
        if s.startswith("if "):
            ok = bool(matlab_eval(s[3:], env))
            stack.append([ok, ok])
        elif s.startswith("elseif "):
            top = stack[-1]
            ok = (not top[1]) and bool(matlab_eval(s[7:], env))
            top[0], top[1] = ok, top[1] or ok
        elif s == "else":
            top = stack[-1]
            top[0], top[1] = not top[1], True
        elif s == "end":
            stack.pop()
        elif all(t[0] for t in stack):
            name, expr = s.rstrip(";").split(" = ", 1)
            env[name] = matlab_eval(expr, env)
    return env


def references(content):
    return {m.group(1): float(m.group(2)) for m in re.finditer(r"names\{end\+1\} = '(\w+)'; got\(end\+1\) = \w+; ref\(end\+1\) = ([^\s;]+);", content)}


def sheet_rows(z, n):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(z.read(f"xl/worksheets/sheet{n}.xml"))
    rows = []
    for r in root.iterfind(".//m:row", ns):
        cells = {}
        for c in r.iterfind("m:c", ns):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            f, v, t = c.find("m:f", ns), c.find("m:v", ns), c.find(".//m:t", ns)
            cells[col] = {"f": f.text if f is not None else None, "v": v.text if v is not None else None, "t": t.text if t is not None else None}
        rows.append(cells)
    return rows


def workbook(graph):
    res = design_export.export_system(graph, "excel")
    assert res["ok"], res.get("diagnostics")
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(res["content_base64"]))), res


# ---------------------------------------------------------------- MATLAB

def test_matlab_script_reproduces_the_system_and_is_readable():
    res = design_export.export_system(wind(), "matlab")
    assert res["ok"] and res["filename"].endswith(".m") and res["format"] == "matlab"
    code = res["content"]
    assert "Ar__b1 = pi*Dr__b1^2/4;" in code and "mH__b2 = Pe__b1*eta__b2*t__b2/HHV__b2;" in code     # wires are plain variable references
    assert "%% Block b2:" in code and "disp('matches the SlideRule reference values')" in code
    env = run_matlab(code)
    refs = references(code)
    assert len(refs) == 8
    for name, ref in refs.items():
        assert env[name] == pytest.approx(ref, rel=1e-6), name


def test_unit_conversion_follows_si_equals_value_plus_offset_times_factor():
    g = {"version": 1, "blocks": [{"id": "b1", "calc": "petroleum.pvt.gas_fvf", "values": {"z": "0.88", "T": "620 degR", "p": "3500 psi"}}], "wires": []}
    plan, _ = design_code.build_plan(g)
    tsc = next(i for i in plan["inputs"] if i["key"] == "Tsc")                            # a constant of 60 degF
    assert tsc["si"] == pytest.approx((60 + 459.67) * 5 / 9, rel=1e-6)
    env = run_matlab(design_export.export_system(g, "matlab")["content"])
    assert env["Tsc__b1"] == pytest.approx(tsc["si"]) and env["Bg__b1"] == pytest.approx(0.004408367727871258, rel=1e-6)


def test_matlab_writes_branches_as_if_blocks_and_comments_as_comments():
    g = {"version": 1, "blocks": [{"id": "b1", "calc": "chemical.fluids.pipe_flow_darcy_weisbach", "values": dict(default_catalog().get("chemical.fluids.pipe_flow_darcy_weisbach").example),
                                   "comment": "Line one\n\nimport os; os.system('x') %%"}], "wires": []}
    code = design_export.export_system(g, "matlab")["content"]
    assert re.search(r"^if Re__b1 < 2300$", code, re.M) and "else" in code and "end" in code
    assert "%   Line one" in code and not [ln for ln in code.splitlines() if "import os" in ln and not ln.lstrip().startswith("%")]
    env = run_matlab(code)
    for name, ref in references(code).items():
        assert env[name] == pytest.approx(ref, rel=1e-6), name


def test_matlab_has_functions_the_printer_lacks_and_refuses_what_has_no_formula():
    cid = "mechanical.dynamics.pendulum_large_amplitude_period"
    g = {"version": 1, "blocks": [{"id": "b1", "calc": cid, "values": dict(default_catalog().get(cid).example)}], "wires": []}
    assert "ellipke(" in design_export.export_system(g, "matlab")["content"]


# ---------------------------------------------------------------- Excel

def test_workbook_structure_names_and_formulas():
    z, res = workbook(wind())
    assert res["filename"].endswith(".xlsx") and res["binary"] and "content" not in res
    assert {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/styles.xml", "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml", "xl/worksheets/sheet3.xml"} <= set(z.namelist())
    for n in z.namelist():
        ElementTree.fromstring(z.read(n))                                                    # every part is well-formed XML
    wb = z.read("xl/workbook.xml").decode()
    names = re.findall(r'<definedName name="([^"]+)">([^<]+)<', wb)
    assert len({n.lower() for n, _ in names}) == len(names) == 11 + 8 and 'fullCalcOnLoad="1"' in wb
    calc = sheet_rows(z, 2)
    ar = next(r for r in calc if r.get("B", {}).get("t") == "Ar")
    assert ar["E"]["f"] == "PI()*Dr__b1^2/4" and ar["D"]["t"] == "pi*Dr__b1^2/4"
    mh = next(r for r in calc if r.get("B", {}).get("t") == "mH")
    assert mh["E"]["f"] == "Pe__b1*eta__b2*t__b2/HHV__b2"                                    # a wire is a reference to the upstream result
    inp = sheet_rows(z, 1)
    eg = next(r for r in inp if r.get("B", {}).get("t") == "eg")
    assert eg["E"]["v"] == "94" and eg["G"]["v"] == "0.01" and eg["I"]["f"].startswith("(E")


def test_workbook_formulas_reproduce_slide_rule_when_translated():
    z, _ = workbook(wind())
    env = {}
    for r in sheet_rows(z, 1)[1:]:
        if r.get("I", {}).get("f"):
            env[next(n for n, ref in re.findall(r'<definedName name="([^"]+)">([^<]+)<', z.read("xl/workbook.xml").decode()) if ref == f"Inputs!$I${sheet_rows(z, 1).index(r) + 1}")] = float(r["I"]["v"])
    for r in sheet_rows(z, 2)[1:]:
        if r.get("E", {}).get("f"):
            ident = next(n for n, ref in re.findall(r'<definedName name="([^"]+)">([^<]+)<', z.read("xl/workbook.xml").decode()) if ref == f"Calculations!$E${sheet_rows(z, 2).index(r) + 1}")
            env[ident] = excel_eval(r["E"]["f"], env)
            assert env[ident] == pytest.approx(float(r["I"]["v"]), rel=1e-6), ident


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
def test_a_real_spreadsheet_engine_recalculates_the_workbook(tmp_path):
    z, res = workbook(wind())
    bogus = tmp_path / "bogus.xlsx"
    with zipfile.ZipFile(bogus, "w") as out:                                                  # wipe every cached value: only the formulas can produce the numbers
        for n in z.namelist():
            data = z.read(n)
            if n.startswith("xl/worksheets/"):
                data = re.sub(r"(</f>)<v>[^<]*</v>", r"\1<v>0</v>", data.decode()).encode()
            out.writestr(n, data)
    subprocess.run(["soffice", "--headless", "--convert-to", "csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,-1", "--outdir", str(tmp_path), str(bogus)],
                   check=True, capture_output=True, timeout=180)
    rows = [ln.split(",") for ln in (tmp_path / "bogus-Calculations.csv").read_text().splitlines()[1:9]]
    assert [r[9] for r in rows] == ["OK"] * 8
    mh = next(r for r in rows if r[1] == "mH")
    assert float(mh[4]) == pytest.approx(867.9044, rel=1e-5)


def test_excel_formula_converter_matches_sympy_on_awkward_expressions():
    x, y, z = sp.symbols("x y z", positive=True)
    s = sp.Symbol("s", real=True)
    names = {x: "x", y: "y", z: "z", s: "s"}
    exprs = [-3*x**2 + y/7 - sp.sqrt(z), (x + y)**(-sp.Rational(3, 2)) * z, -x**(y + 1), x**y**z, sp.Rational(5, 3)*x/(y*z) - 2.5e-5*z, sp.exp(-x/y)**3 + sp.log(z),
             sp.Max(x, y) - sp.Min(y, z), sp.atan2(s, x) + sp.sinh(y), sp.Piecewise((x**2, s < 0), (sp.sqrt(y), sp.And(s >= 0, s < 1)), (1/z, True)), sp.Abs(s - x)*sp.sign(s),
             sp.floor(x*3) + sp.ceiling(-y*3), sp.erf(x/3) + sp.acos(sp.Rational(1, 3)) + sp.pi*sp.E, -(x - y)**2, 1/(x + y), (x*y)**sp.Rational(1, 2), -2*s**2]
    rng = random.Random(7)
    for e in exprs:
        f = design_code.excel_formula(e, names)
        fn = sp.lambdify([x, y, z, s], e, modules=["math"])
        for _ in range(6):
            vals = {"x": rng.uniform(0.2, 3), "y": rng.uniform(0.2, 3), "z": rng.uniform(0.2, 3), "s": rng.uniform(-2, 2)}
            assert excel_eval(f, vals) == pytest.approx(fn(vals["x"], vals["y"], vals["z"], vals["s"]), rel=1e-9, abs=1e-12), (e, f)


def test_a_broad_sample_of_the_library_exports_correctly():
    cat = [c for c in default_catalog() if not c.custom][::9]
    checked = skipped = 0
    for c in cat:
        g = {"version": 1, "blocks": [{"id": "b1", "calc": c.id, "values": dict(c.example)}], "wires": []}
        if not design.solve_system(g)["ok"]:
            continue
        plan, diags = design_code.build_plan(g, 5, case_sensitive=False)
        if plan is None:
            assert diags[0]["code"] == "UNSUPPORTED", c.id
            skipped += 1
            continue
        if any(st["ivp"] for st in plan["steps"]):                  # numerically integrated: MATLAB only, a spreadsheet formula cannot do it
            skipped += 1
            continue
        env = {i["ident"]: i["si"] for i in plan["inputs"]}
        try:
            for st in plan["steps"]:
                env[st["ident"]] = excel_eval(design_code.excel_formula(st["expr"], plan["ident"]), env)
                if st["ref"] is not None:
                    assert env[st["ident"]] == pytest.approx(st["ref"], rel=1e-6, abs=1e-12), (c.id, st["key"])
        except design_code.Unsupported:
            skipped += 1
            continue
        checked += 1
        code, mdiags = design_code.render_matlab(g, 5)
        assert code or mdiags[0]["code"] == "UNSUPPORTED", c.id
    assert checked > 50 and skipped < checked


def test_names_ignore_case_in_excel_and_stay_valid():
    used: set[str] = set()
    a = design_code._identifier("P", "b1", used, False)
    b = design_code._identifier("p", "b1", used, False)
    assert a != b and a.lower() != b.lower() and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", b)
    assert design_code._identifier("η", "b1", used, False).startswith("v")


# ---------------------------------------------------------------- limits, API, comments

def test_blocks_without_a_plain_formula_are_refused_with_the_block_named():
    ode = default_catalog().get("mechanical.dynamics.bouncing_ball_impacts")                 # an event: no plain formula and no ode45 export
    g = {"version": 1, "blocks": [{"id": "b7", "calc": ode.id, "values": dict(ode.example)}], "wires": []}
    for fmt in ("matlab", "excel"):
        res = design_export.export_system(g, fmt)
        assert not res["ok"] and res["diagnostics"][0]["code"] == "UNSUPPORTED" and res["diagnostics"][0]["block"] == "b7"


def test_math_blocks_comments_and_the_rpc():
    g = wind()
    g["blocks"][0]["comment"] = "Site survey values"
    g["blocks"].append({"id": "m1", "kind": "math", "op": "add", "values": {"x2": "500 kW"}})
    g["wires"] = [w("w1", "b1", "Pe", "m1", "x1"), w("w2", "m1", "y", "b2", "P")]
    res = api.handle("design_export", {"graph": g, "format": "matlab", "mode": "both", "sig_figs": 5, "standalone": True})
    assert res["ok"] and "%   Site survey values" in res["result"]["content"]
    env = run_matlab(res["result"]["content"])
    assert env["y__m1"] == pytest.approx(env["Pe__b1"] + 500e3)
    z, _ = workbook(g)
    about = [c["A"]["t"] for c in sheet_rows(z, 3)]
    assert any("Site survey values" in t for t in about) and any("Add" in t for t in about)
    assert design_export.export_system(g, "nonsense")["ok"] is False


# ---------------------------------------------------------------- differential equations with a closed-form solution



def test_closed_form_differential_equation_blocks_export_and_match_the_numerical_solver():
    cat = default_catalog()
    found = [c for c in cat if c.parsed_odes and not c.tables and all(design_code.closed_solution(o) for o in c.parsed_odes)]
    assert len(found) >= 10
    for c in found:
        g = {"version": 1, "blocks": [{"id": "b1", "calc": c.id, "values": dict(c.example)}], "wires": []}
        plan, diags = design_code.build_plan(g, 5, case_sensitive=False)
        assert plan is not None, (c.id, diags)
        env = {i["ident"]: i["si"] for i in plan["inputs"]}
        for st in plan["steps"]:
            env[st["ident"]] = excel_eval(design_code.excel_formula(st["expr"], plan["ident"]), env)
            assert env[st["ident"]] == pytest.approx(st["ref"], rel=1e-6, abs=1e-12), (c.id, st["key"])      # the closed form equals the solver's number
        code, d = design_code.render_matlab(g)
        assert code and not d, c.id


def test_numerically_solved_differential_equations_are_still_refused():
    g = {"version": 1, "blocks": [{"id": "b3", "calc": "mechanical.dynamics.bouncing_ball_impacts", "values": dict(default_catalog().get("mechanical.dynamics.bouncing_ball_impacts").example)}], "wires": []}
    diags = design_code.build_plan(g)[1]
    assert diags[0]["code"] == "UNSUPPORTED" and "numerically" in diags[0]["message"] and diags[0]["block"] == "b3"


# ---------------------------------------------------------------- initial-value problems (MATLAB only)

def _integrate_generated_ode(code):
    """Read the generated ode45 call back (right-hand side, span, initial values), integrate it with SciPy, and run the rest of the script with the results written in."""
    from scipy.integrate import solve_ivp

    inputs = code.split("%% Block")[0]                          # the inputs section: every ode45 call depends on these only
    env = run_matlab(inputs)
    out = {}
    for m in re.finditer(r"f_(\w+) = @\(tt, y\) \[(.*)\];\n\[~, Y_\w+\] = ode45\(f_\w+, \[(.*?), (\w+)\], \[(.*?)\], odeset", code):
        sid, rhs, t0, tend, ics = m.groups()
        parts = [re.sub(r"y\((\d+)\)", lambda k: f"y[{int(k.group(1)) - 1}]", p) for p in rhs.split("; ")]
        f = lambda t, y, parts=parts: [matlab_eval(p, {**env, "tt": t, "y": y}) for p in parts]          # noqa: E731
        y0 = [matlab_eval(p, env) for p in ics.split("; ")]
        sol = solve_ivp(f, [matlab_eval(t0, env), env[tend]], y0, method="DOP853", rtol=1e-11, atol=1e-14)
        out[sid] = sol.y[:, -1]
    body = re.sub(r"(\w+) = Y_(\w+)\(end, (\d+)\);", lambda m: f"{m.group(1)} = {float(out[m.group(2)][int(m.group(3)) - 1])!r};", code)
    body = "\n".join(ln for ln in body.splitlines() if "ode45" not in ln and "@(" not in ln)
    return run_matlab(body)


def test_initial_value_problems_export_to_matlab_with_ode45_and_match_the_solver():
    found = []
    for c in default_catalog():
        if c.custom or c.tables or not c.parsed_odes or not all(design_code.closed_solution(o) or design_code.plain_ivp(o) for o in c.parsed_odes):
            continue
        if not any(design_code.plain_ivp(o) for o in c.parsed_odes):
            continue
        g = {"version": 1, "blocks": [{"id": "b1", "calc": c.id, "values": dict(c.example)}], "wires": []}
        code, diags = design_code.render_matlab(g)
        assert code and not diags, (c.id, diags)
        assert "ode45(" in code and "RelTol" in code
        env = _integrate_generated_ode(code)
        for name, ref in references(code).items():
            assert env[name] == pytest.approx(ref, rel=1e-5, abs=1e-7), (c.id, name)         # abs: a conserved quantity's drift (-5.6e-8 J here) is the solver's integration error, not the script's
        found.append(c.id)
    assert len(found) >= 4 and any("pi_control" in f for f in found)


def test_excel_refuses_a_numerically_integrated_system_and_says_why():
    cid = "mechanical.dynamics.damped_oscillator_response"
    g = {"version": 1, "blocks": [{"id": "b5", "calc": cid, "values": dict(default_catalog().get(cid).example)}], "wires": []}
    res = design_export.export_system(g, "excel")
    assert not res["ok"] and res["diagnostics"][0]["block"] == "b5" and "spreadsheet" in res["diagnostics"][0]["message"]
    assert design_export.export_system(g, "matlab")["ok"]


SERIES = ["heat.slab_transient_conduction_series", "acoustics.plucked_string_displacement_series", "signal.square_wave_fourier_partial_sum", "heat.rectangular_plate_steady_series"]


def _series_graph(suffix):
    c = next(x for x in default_catalog() if x.id.endswith(suffix))
    return {"version": 1, "blocks": [{"id": "b1", "calc": c.id, "values": dict(c.example)}], "wires": []}


@pytest.mark.parametrize("suffix", SERIES)
def test_finite_series_export_as_sums_in_matlab(suffix):
    code, diags = design_code.render_matlab(_series_graph(suffix))
    assert code and not diags and "sum(arrayfun(@(" in code
    env = run_matlab(code)
    for name, ref in references(code).items():
        assert env[name] == pytest.approx(ref, rel=1e-6, abs=1e-12), name


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_finite_series_recalculate_correctly_in_a_real_spreadsheet_engine(tmp_path):
    for k, suffix in enumerate(SERIES):
        z, _res = workbook(_series_graph(suffix))
        assert b"SUMPRODUCT(" in z.read("xl/worksheets/sheet2.xml")
        bogus = tmp_path / f"s{k}.xlsx"
        with zipfile.ZipFile(bogus, "w") as out:
            for n in z.namelist():
                data = z.read(n)
                if n.startswith("xl/worksheets/"):
                    data = re.sub(r"(</f>)<v>[^<]*</v>", r"\1<v>0</v>", data.decode()).encode()
                out.writestr(n, data)
        subprocess.run(["soffice", "--headless", "--convert-to", "csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,-1", "--outdir", str(tmp_path), str(bogus)],
                       check=True, capture_output=True, timeout=180)
        import csv

        rows = list(csv.reader((tmp_path / f"s{k}-Calculations.csv").read_text().splitlines()))[1:]
        status = [r[9] for r in rows if len(r) > 9 and r[9]]
        assert status and set(status) == {"OK"}, (suffix, status)
