"""Build a LOCAL materials datapack from an extracted copy of the CRC Handbook of Chemistry and Physics.

    python scripts/import_crc_materials.py /path/to/out/handbook [--out DIR] [--report]

The input is the output folder of local_pdf_extractor (``handbook.elements.jsonl``: typed elements, tables with their cell grid). The output is a datapack
folder (``manifest.json`` + ``data.json``, sealed) that SlideRule loads like any other pack; by default it goes to ``$SLIDERULE_HOME/datapacks/crc-materials``
(``~/.sliderule/datapacks/crc-materials``), **outside the repository on purpose**: the Handbook is a copyrighted compilation (CRC Press / Taylor & Francis), so
the extracted data is for the user's own copy and must not be committed, published or sold with the program. See docs/DATA_AND_STANDARDS_STRATEGY.md.

What is read, and why only these tables. A table is used only if its cell grid keeps every value in its own row and column, so a value can never be attached
to the wrong material. Tables whose columns were flattened by the PDF (the printed "Thermal and Physical Properties of Pure Metals" has one cell per column
holding all 70 metals with some entries missing, and "Density of Various Solids" interleaves three side-by-side blocks) are used only for the columns that are
complete (density), and every other column of that table is left out (specific heat, thermal conductivity and expansion each lack some entries, so which value belongs to which
metal cannot be told). The glasses table is not used either: its names wrap over two lines that sit beside different data rows, so an entry's rows cannot be told
apart reliably.

    p.2084-2085   thermal conductivity of 15 pure metals against temperature (W/cm K, converted)
    p.2086        thermal conductivity of about 50 alloys at 4 to 973 K
    p.2081        molar heat capacity of selected solids, 200 to 600 K (converted with the atomic mass)
    p.2082-2083   density at 25 degC of the metallic elements (a complete column in every block)
    p.2089-2090   thermal conductivity of ceramics and insulating materials (two side-by-side blocks)
    p.748         room-temperature elastic moduli and mechanical properties of the rare earth metals
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sliderule.core import datapack  # noqa: E402

EDITION = "CRC Handbook of Chemistry and Physics, 89th Edition (Internet Version 2009), D. R. Lide, ed., CRC Press / Taylor & Francis"

#: IUPAC standard atomic weights (g/mol) of the elements in the molar heat-capacity table: used to turn J/(mol K) into J/(g K), and only after each value has been
#: cross-checked against the Handbook's own J/(g K) column
ATOMIC_WEIGHT = {"Aluminum": 26.982, "Beryllium": 9.0122, "Boron": 10.81, "Calcium": 40.078, "Chromium": 51.996, "Cobalt": 58.933, "Copper": 63.546,
                 "Germanium": 72.630, "Gold": 196.97, "Graphite": 12.011, "Iron": 55.845, "Lead": 207.2, "Lithium": 6.94, "Magnesium": 24.305, "Manganese": 54.938,
                 "Potassium": 39.098, "Silicon": 28.086, "Silver": 107.87, "Sodium": 22.990, "Tantalum": 180.95, "Titanium": 47.867, "Tungsten": 183.84,
                 "Vanadium": 50.942, "Zinc": 65.38}
SYMBOLS = set(["Ag", "Al", "Au", "B", "Ba", "Be", "Bi", "C", "Ca", "Cd", "Ce", "Co", "Cr", "Cs", "Cu", "Fe", "Ga", "Ge", "Hf", "Hg", "In", "Ir", "K", "La", "Li", "Mg", "Mn", "Mo", "Na", "Nb", "Ni", "Os", "Pb", "Pd", "Pt", "Rb", "Re", "Rh", "Ru", "Sb", "Sc", "Si", "Sn", "Sr", "Ta", "Th", "Ti", "Tl", "U", "V", "W", "Y", "Zn", "Zr"])


# ------------------------------------------------------------------ reading

def load(folder: Path) -> list[dict]:
    with open(folder / "handbook.elements.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def tables(els: list[dict], page: int) -> list[list[list[str]]]:
    return [e["table_rows"] for e in els if e["type"] == "Table" and e["page"] == page and e.get("table_rows")]


_NUM = re.compile(r"^[–−-]?\d+(?:\.\d+)?(?:[eE][–−+-]?\d+)?")


def num(cell: str) -> float | None:
    """The number at the start of a cell ('0.402*', '103a', '–150', '2.5'), None if the cell has none (a blank, a dash, text)."""
    s = cell.strip().replace("−", "-").replace("–", "-")
    m = _NUM.match(s)
    if not m or s in ("-", "—"):
        return None
    tail = s[m.end():].strip()
    if tail and not re.fullmatch(r"[a-z*†‡]{0,3}", tail):         # '3.2 to 5' or '12 ± 3' is not a single value
        return None
    return float(m.group(0))


def slug(*parts: str) -> str:
    s = "-".join(p for p in parts if p).replace("⊥", " perp ").replace("||", " par ")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:80]


def prop(value, unit, source, note=None, **extra):
    d = {"value": float(f"{value:.6g}"), "unit": unit, "basis": "typical", "source": source}
    if note:
        d["note"] = note
    d.update(extra)
    return d


def curve(xs, ys, x_unit, unit, source, note=None):
    d = {"curve": {"x_unit": x_unit, "method": "pchip" if len(xs) > 2 else "linear", "x": [float(x) for x in xs], "y": [float(f"{y:.6g}") for y in ys]},
         "unit": unit, "basis": "typical", "source": source}
    if note:
        d["note"] = note
    return d


class Builder:
    def __init__(self):
        self.records: dict[str, dict] = {}
        self.report: list[str] = []

    def add(self, rid: str, name: str, category: str, designation: str, condition: str, note: str, name_props: dict) -> None:
        rec = self.records.setdefault(rid, {"id": rid, "name": name, "category": category, "designation": designation, "condition": condition, "note": note, "properties": {}})
        for k, v in name_props.items():
            if k in rec["properties"]:                              # two tables give the same property: keep the first, say so
                self.report.append(f"{rid}: {k} given twice, kept the first")
            else:
                rec["properties"][k] = v


# ------------------------------------------------------------------ thermal conductivity of the pure metals (p.2084-2085)
#: element symbol -> English name; the Handbook's tables often print only the symbol (some with a Greek letter naming the crystal phase)
ELEMENT_NAMES = {
    "Ag": "Silver", "Al": "Aluminum", "Au": "Gold", "B": "Boron", "Ba": "Barium", "Be": "Beryllium", "Bi": "Bismuth", "C": "Carbon", "Ca": "Calcium",
    "Cd": "Cadmium", "Ce": "Cerium", "Co": "Cobalt", "Cr": "Chromium", "Cs": "Cesium", "Cu": "Copper", "Dy": "Dysprosium", "Er": "Erbium",
    "Eu": "Europium", "Fe": "Iron", "Ga": "Gallium", "Gd": "Gadolinium", "Ge": "Germanium", "Hf": "Hafnium", "Hg": "Mercury", "Ho": "Holmium",
    "In": "Indium", "Ir": "Iridium", "K": "Potassium", "La": "Lanthanum", "Li": "Lithium", "Lu": "Lutetium", "Mg": "Magnesium", "Mn": "Manganese",
    "Mo": "Molybdenum", "Na": "Sodium", "Nb": "Niobium", "Nd": "Neodymium", "Ni": "Nickel", "Os": "Osmium", "Pb": "Lead", "Pd": "Palladium",
    "Pm": "Promethium", "Pr": "Praseodymium", "Pt": "Platinum", "Rb": "Rubidium", "Re": "Rhenium", "Rh": "Rhodium", "Ru": "Ruthenium",
    "Sb": "Antimony", "Sc": "Scandium", "Si": "Silicon", "Sm": "Samarium", "Sn": "Tin", "Sr": "Strontium", "Ta": "Tantalum", "Tb": "Terbium",
    "Th": "Thorium", "Ti": "Titanium", "Tl": "Thallium", "Tm": "Thulium", "U": "Uranium", "V": "Vanadium", "W": "Tungsten", "Y": "Yttrium",
    "Yb": "Ytterbium", "Zn": "Zinc", "Zr": "Zirconium",
}
PHASES = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta"}


def pure_metal_names(els: list[dict]) -> dict[str, str]:
    """symbol -> name from the metals table (p.2082-2083): 'Aluminum (Al)'."""
    out = {}
    for p in (2082, 2083):
        for t in tables(els, p):
            for row in t:
                for m in re.finditer(r"([A-Z][a-z]+) \(([A-Z][a-z]?)\s?\)", row[0]):
                    out[m.group(2)] = m.group(1)
    return out


def parse_metal_k(els, b: Builder, names: dict[str, str]) -> None:
    for page in (2084, 2085):
        for t in tables(els, page):
            hi = next(i for i, r in enumerate(t) if r[0].strip() == "T/K")
            head = []
            for h in t[hi]:
                h = h.strip()
                head.append(h[:-1] if h not in SYMBOLS and h[:-1] in SYMBOLS else h)
            cols = {h: j for j, h in enumerate(head) if h in SYMBOLS}
            for sym, j in cols.items():
                xs, ys = [], []
                for r in t[hi + 1:]:
                    T, k = num(r[0]), num(r[j]) if j < len(r) else None
                    if T is not None and k is not None and T >= 100:
                        xs.append(T)
                        ys.append(k * 100.0)                        # W/(cm K) -> W/(m K)
                if len(xs) >= 3:
                    b.add(slug("element", names.get(sym, sym)), names.get(sym) or ELEMENT_NAMES.get(sym, sym), "metal element", sym, "pure, highly purified specimen", "", {
                        "thermal_conductivity": curve(xs, ys, "K", "W/(m*K)", "tk-metals",
                                                      "typical values for a highly purified specimen; the conductivity of real material varies, most of all below 100 K")})


# ------------------------------------------------------------------ alloys (p.2086)

def parse_alloys(els, b: Builder) -> None:
    for t in tables(els, 2086):
        hi = next(i for i, r in enumerate(t) if r[1].strip() == "Alloy")
        temps = [num(c.replace("K", "")) for c in t[hi][2:]]
        group = ""
        for r in t[hi + 1:]:
            if r[0].strip():
                group = r[0].strip().rstrip(":")
            name = r[1].strip()
            xs, ys = [], []
            for T, c in zip(temps, r[2:]):
                k = num(c)
                if T is not None and T >= 77 and k is not None:
                    xs.append(T)
                    ys.append(k)
            if name and len(xs) >= 2:
                b.add(slug("alloy", group, name), f"{group}: {name}".strip(), "alloy", name, "", "composition in weight percent as printed",
                      {"thermal_conductivity": curve(xs, ys, "K", "W/(m*K)", "tk-alloys")})


# ------------------------------------------------------------------ molar heat capacity (p.2081), and the pure-metal table (p.2082-2083)

def parse_heat_capacity(els, b: Builder) -> dict[str, float]:
    """Specific heat curves 200-600 K for the elements whose atomic weight is known; returns name -> specific heat at 300 K in J/(g K)."""
    at300 = {}
    for t in tables(els, 2081):
        hi = next(i for i, r in enumerate(t) if r[0].strip() == "Name")
        for r in t[hi + 1:]:
            name = r[0].strip()
            if name not in ATOMIC_WEIGHT:
                continue
            # the printed grid merges the 300 K and 350 K cells; the temperatures are in the header, one cell holds two tokens
            temps = [200, 250, 300, 350, 400, 500, 600]
            cells = [r[1], r[2], r[3], r[4], r[5], r[6]]
            tokens = []
            for ci, c in enumerate(cells):
                toks = c.split()
                if ci == 2 and len(toks) == 2:
                    tokens += [(300, toks[0]), (350, toks[1])]
                elif ci == 2 and len(toks) == 1:
                    later_empty = all(not c.split() for c in cells[3:])            # one value and nothing after it: it is the 300 K one (the range ends there)
                    tokens += [(300 if later_empty else None, toks[0])]
                else:
                    T = {0: 200, 1: 250, 3: 400, 4: 500, 5: 600}.get(ci)
                    tokens += [(T, toks[0])] if toks else []
            if any(T is None for T, _ in tokens):
                b.report.append(f"heat capacity of {name}: the merged 300/350 K cell holds one value, skipped")
                continue
            xs = [T for T, _ in tokens]
            ys = [float(v) / ATOMIC_WEIGHT[name] * 1000.0 for _, v in tokens]      # J/(mol K) / (g/mol) -> J/(g K) -> J/(kg K)
            if len(xs) >= 3:
                if 300 in xs:
                    at300[name] = ys[xs.index(300)] / 1000.0
                b.add(slug("element", name), name, "metal element" if name != "Graphite" else "element", "", "", "",
                      {"specific_heat": curve(xs, ys, "K", "J/(kg*K)", "cp-solids", "molar heat capacity of the Handbook divided by the standard atomic weight")})
    return at300


def parse_pure_metals(els, b: Builder, at300: dict[str, float]) -> None:
    """The pure-metals table (p.2082-2083). When the extract keeps one metal per row, density, expansion and specific heat at 25 degC and conductivity at 27 degC are
    read from their own columns; a cell footnoted 'b' (taken at 100 degC) is dropped and one footnoted 'a' is marked estimated. When a block of metals shares one cell
    (the older extract), only the density column, which is complete there, is used."""
    fix = lambda s: re.sub(r"(\d)\.\s+(\d)", r"\1.\2", s)           # noqa: E731  '2. 70' -> '2.70' (the grid cells keep the PDF's spacing)
    cols = {"ρ25": "density", "α× 10^6": "alpha", "cp": "cp", "λ": "lam"}
    for page in (2082, 2083):
        for t in tables(els, page):
            head = [re.sub(r"\s+", " ", h.strip()) for h in t[0]]
            if "ρ25" not in head:
                continue
            idx = {key: head.index(h) for h, key in cols.items() if h in head}
            for r in t[2:]:
                names = re.findall(r"([A-Z][a-z]+) \(([A-Z][a-z]?)\s?\)", r[0])
                if not names:
                    continue
                if len(names) > 1:                                              # the older extract: a block of metals in one cell
                    dens = fix(r[idx["density"]]).split()
                    if len(dens) != len(names):
                        b.report.append(f"p.{page}: density column has {len(dens)} values for {len(names)} metals, block skipped")
                        continue
                    for (nm, sym), d in zip(names, dens):
                        if num(d) is not None:
                            b.add(slug("element", nm), nm, "metal element", sym, "pure metal at 25 degC", "", {"density": prop(num(d) * 1000.0, "kg/m^3", "metals-table", at={"temperature": "25 degC"})})
                    continue
                nm, sym = names[0]

                def cell(key):
                    raw = fix(r[idx[key]]).strip() if key in idx and idx[key] < len(r) else ""
                    if re.search(r"\d\s*b$", raw):                            # footnote b: measured at 100 degC, not at the column's temperature
                        return None, False
                    v = num(raw)
                    return v, bool(re.search(r"\d\s*a$", raw))

                props, rec = {}, b.records.get(slug("element", nm), {"properties": {}})
                for key, unit, scale, at, name in (("density", "kg/m^3", 1000.0, "25 degC", "density"), ("alpha", "1/K", 1e-6, "25 degC", "thermal_expansion"),
                                                   ("cp", "J/(kg*K)", 1000.0, "25 degC", "specific_heat"), ("lam", "W/(m*K)", 100.0, "27 degC", "thermal_conductivity")):
                    v, est = cell(key)
                    if v is None or name in rec["properties"]:                  # a conductivity curve from p.2084 is better than the single 27 degC value
                        continue
                    props[name] = prop(v * scale, unit, "metals-table", "Estimated by the Handbook's compilers" if est else None, at={"temperature": at})
                if props:
                    b.add(slug("element", nm), nm, "metal element", sym, "pure metal", "", props)


# ------------------------------------------------------------------ ceramics and insulating materials (p.2089-2090) and glasses (p.2091-2092)

def _insulator_rows(els) -> list[tuple[str, str, str, str]]:
    """(name, density, t, k) in reading order: the left block of the first page, its right block, then the same for the second page."""
    out = []
    for page in (2089, 2090):
        for t in tables(els, page):
            for block in (0, 4):
                for r in t[2:]:
                    if len(r) >= block + 4:
                        out.append(tuple(c.strip() for c in r[block:block + 4]))
    return out


def parse_insulators(els, b: Builder) -> None:
    """Names and densities are only printed on the first row of an entry, the rows below belong to it; a heading row has a name and no data ('Wood:', 'Graphite'),
    and the lower-case entries that follow it (balsa, fir, 100 mesh) are its children, while a capitalised entry ends the group."""
    group, name, dens = "", "", ""
    pts: dict[tuple[str, str], list[tuple[float, float]]] = {}
    order: list[tuple[str, str]] = []
    for nm, d, tt, k in _insulator_rows(els):
        if nm and not tt and not k and not d:                       # a heading
            group, name, dens = nm.rstrip(":"), "", ""
            continue
        if nm:
            child = bool(group) and (not nm[0].isupper() or (group == "Mica" and nm == "Canadian"))
            if not child:
                group = ""
            name, dens = (f"{group}: {nm}" if child else nm), ""
        if d:
            dens = d
        T, kk = num(tt), num(k)
        if not name or T is None or kk is None:
            continue
        key = (name, dens)
        if key not in pts:
            pts[key] = []
            order.append(key)
        pts[key].append((T, kk))
    for nm, d in order:
        p = sorted(set(pts[(nm, d)]))
        dv = num(d) if d else None
        props = {}
        if len(p) >= 2 and len({T for T, _ in p}) == len(p):
            props["thermal_conductivity"] = curve([T for T, _ in p], [k for _, k in p], "degC", "W/(m*K)", "tk-ceramics")
        elif len(p) == 1:
            props["thermal_conductivity"] = prop(p[0][1], "W/(m*K)", "tk-ceramics", f"at {p[0][0]:g} degC", at={"temperature": f"{p[0][0]:g} degC"})
        if dv is not None:
            props["density"] = prop(dv * 1000.0, "kg/m^3", "tk-ceramics")
        if props:
            b.add(slug("material", nm, d), nm if not d else f"{nm} (density {d} g/cm3)", "insulating or ceramic material", nm, "", "", props)


# ------------------------------------------------------------------ rare earth moduli (p.748)

def parse_rare_earth(els, b: Builder) -> None:
    """Table 11 (p.748): moduli and strengths of the rare earth metals. Rows are named by symbol with an optional Greek phase letter ('γCe'); the record is named
    for the element and the phase ('Cerium (gamma)'). Both the grid layout (one column per quantity) and the older one (three moduli in one cell) are read."""
    for t in tables(els, 748):
        if not any("Young" in c for r in t[:4] for c in r):
            continue
        for r in t:
            if len(r) < 5 or not r[0].strip():
                continue
            name = r[0].strip()
            toks = r[1].split()
            if len(toks) == 3 and all(num(x) is not None for x in toks):         # older extract: 'E G K' in one cell
                e, nu, ys, uts = num(toks[0]), num(r[2]), num(r[3]), num(r[4])
            elif len(r) >= 7 and any(num(c) is not None for c in r[1:7]):          # grid: E, G, K, nu, yield, UTS
                e, nu, ys, uts = num(r[1]), num(r[4]), num(r[5]), num(r[6])
            else:
                continue
            phase = PHASES.get(name[0])
            sym = name[1:] if phase else name
            element = ELEMENT_NAMES.get(sym, sym)
            props = {}
            if e is not None:
                props["youngs_modulus"] = prop(e, "GPa", "rare-earth")
            if nu is not None:
                props["poisson_ratio"] = prop(nu, "1", "rare-earth")
            if ys is not None:
                props["yield_strength"] = prop(ys, "MPa", "rare-earth", "0.2 % offset; the Handbook marks some values as measured on non-standard material")
            if uts is not None:
                props["ultimate_strength"] = prop(uts, "MPa", "rare-earth")
            if props:
                b.add(slug("element", element) + (f"-{phase}" if phase else ""), f"{element} ({phase})" if phase else element, "rare earth metal",
                      f"{name[0]}-{sym}" if phase else sym, "polycrystalline, room temperature" + (f", {phase} phase" if phase else ""), "", props)


# ------------------------------------------------------------------ assembling

SOURCES = [
    ("tk-metals", "Thermal Conductivity of Metals and Semiconductors as a Function of Temperature (Ho, Powell and Liley, 1972; White and Minges, 1985)", 2084),
    ("tk-alloys", "Thermal Conductivity of Alloys as a Function of Temperature", 2086),
    ("cp-solids", "Heat Capacity of Selected Solids (JANAF, CODATA)", 2081),
    ("metals-table", "Thermal and Physical Properties of Pure Metals (density at 25 degC)", 2082),
    ("tk-ceramics", "Thermal Conductivity of Ceramics and Other Insulating Materials", 2089),
    ("rare-earth", "Table 11. Room Temperature Elastic Moduli and Mechanical Properties of the rare earth metals", 748),
]


def build(folder: Path) -> tuple[dict, dict, list[str]]:
    els = load(folder)
    b = Builder()
    names = pure_metal_names(els)
    parse_metal_k(els, b, names)
    parse_alloys(els, b)
    at300 = parse_heat_capacity(els, b)
    parse_pure_metals(els, b, at300)
    parse_insulators(els, b)
    parse_rare_earth(els, b)
    for what, key, page in (("rare earth moduli", "youngs_modulus", 748), ("pure-metal densities", "density", 2082), ("pure-metal specific heats", "specific_heat", 2082)):
        if not any(key in r["properties"] and r["category"] in ("rare earth metal", "metal element") for r in b.records.values()):
            b.report.append(f"WARNING p.{page}: no {what} were read; the extractor's table layout may have changed")
    manifest = {
        "id": "crc-materials", "version": "0.1.0", "title": "Materials from the CRC Handbook (local extract)", "kind": "materials",
        "licence": "Copyright CRC Press / Taylor & Francis. Extracted from the user's own copy of the Handbook for personal use. Do not redistribute, commit or publish this folder.",
        "status": "Local extract: values as printed (typical values), parsed by script from the PDF text layer; check any value you rely on against the book",
        "design_use": False,
        "sources": [{"id": sid, "ref": f"{EDITION}: {title}", "location": f"PDF page {pg}", "accessed": "2026-10-31"} for sid, title, pg in SOURCES],
        "checksum": "",
    }
    return manifest, {"records": sorted(b.records.values(), key=lambda r: r["id"])}, b.report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder", type=Path, help="the extractor's output folder (contains handbook.elements.jsonl)")
    ap.add_argument("--out", type=Path, default=datapack.user_folder() / "crc-materials")
    ap.add_argument("--report", action="store_true", help="print what was skipped and why")
    a = ap.parse_args()
    manifest, data, report = build(a.folder)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (a.out / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    datapack.seal(a.out)
    pack, errs = datapack.validate_pack(a.out)
    kinds = {}
    for r in data["records"]:
        kinds[r["category"]] = kinds.get(r["category"], 0) + 1
    print(f"{len(data['records'])} records {kinds}")
    print("valid" if pack else "REFUSED:\n  " + "\n  ".join(errs[:40]))
    for line in report:
        if line.startswith("WARNING"):
            print(line, file=sys.stderr)
    if a.report:
        print("\n".join(report))
    print(f"written to {a.out}")
    sys.exit(0 if pack else 1)


if __name__ == "__main__":
    main()
