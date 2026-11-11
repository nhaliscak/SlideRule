"""Build a local datapack of cryogenic thermal properties from the NIST Cryogenic Technologies Group material pages.

    python scripts/import_nist_cryo.py [--cache DIR] [--from-dir DIR] [--out DIR]

Each page (https://trc.nist.gov/cryogenics/materials/materialproperties.htm) gives thermal conductivity and specific heat as
log10 polynomial fits, log10 y = a + b log10 T + ... + i (log10 T)^8, with a data range, an equation range and the fit error. This
script fetches the pages politely (identifying User-Agent, one request every 2 s, robots.txt does not exist on trc.nist.gov and the
pages are not disallowed on www.nist.gov), keeps the HTML in a cache folder, evaluates each fit on a log-spaced grid inside the range
the data and the equation both cover, and writes a sealed datapack.

The pack is written to ``$SLIDERULE_HOME/datapacks/nist-cryo`` by default; pass ``--out src/sliderule/datapacks/nist-cryo`` to rebuild the one that ships.
NIST permits redistribution of its non-Standard-Reference-Data works if the source is acknowledged, a change notice is given and its statement is
included (https://www.nist.gov/open/license); the manifest and the NOTICE.md written next to it carry all three. The pages themselves show no SRD
copyright notice. If NIST says these fits are SRD, remove the shipped pack.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://trc.nist.gov/cryogenics/materials/"
USER_AGENT = "SlideRule-importer (+https://github.com/nhaliscak/SlideRule; one request every 2 s)"
POINTS = 60
COEFFS = "abcdefghi"
#: the property each recognised table header names -> (datapack property, unit)
COLUMNS = {"thermal conductivity": ("thermal_conductivity", "W/(m*K)"), "specific heat": ("specific_heat", "J/(kg*K)")}

#: page path under BASE (links on the index page; spaces as written there)
PAGES = [
    "1100 Aluminum/1100 Aluminum_rev.htm", "3003F Aluminum/3003FAluminum_rev.htm", "5083 Aluminum/5083Aluminum_rev.htm",
    "6061 Aluminum/6061_T6Aluminum_rev.htm", "6063_T5 Alulminum/6063-T5Aluminum_rev.htm", "Beryllium/Beryllium_rev.htm",
    "Beryllium Copper/BerylliumCopper_rev.htm", "Brass/Brass_rev.htm", "OFHC Copper/OFHC_Copper_rev1.htm",
    "G-10 CR Fiberglass Epoxy/G10CRFiberglassEpoxy_rev.htm", "Iconel 718/Inconel718_rev.htm", "Indium/Indium_rev.htm",
    "Invar(Fe-36Ni)/Invar_rev.htm", "Lead/Lead_rev.htm", "Molybdenum/Molybdenum_rev.htm", "Platinum/Platinum_rev.htm",
    "Polyamide (Nylon)/PolyamideNylon_rev.htm", "PET/PET_rev.htm", "Polyimide Kapton/PolyimideKapton_rev.htm", "Sapphire/Sapphire_rev.htm",
    "304Stainless/304Stainless_rev.htm", "304LStainless/304LStainless_rev.htm", "310 Stainless/310Stainless_rev.htm",
    "316Stainless/316Stainless_rev.htm", "Teflon/Teflon_rev.htm", "Ti6Al4V/Ti6Al4V_rev.htm",
]

CATEGORIES = [("alumin", "aluminium"), ("stainless", "stainless steel"), ("steel", "steel"), ("copper", "copper alloy"), ("brass", "copper alloy"),
              ("inconel", "nickel alloy"), ("iconel", "nickel alloy"), ("invar", "iron-nickel alloy"), ("ti", "titanium alloy"),
              ("g-10", "composite"), ("fiberglass", "composite"), ("nylon", "polymer"), ("polyimide", "polymer"), ("teflon", "polymer"),
              ("pet", "polymer"), ("polyamide", "polymer"), ("sapphire", "ceramic")]


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[list[str]] | None = None
        self._cell: list[str] | None = None
        self.title = ""
        self._in_title = False
        self._h: list[str] = []
        self._in_h = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
            self.tables[-1].append(self._row)
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._row.append(self._cell)
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._cell = None
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        if self._in_title:
            self.title += data

    def handle_entityref(self, name):
        if self._cell is not None:
            self._cell.append(" ")


def _clean(cells: list) -> list[str]:
    return [" ".join("".join(c).split()) for c in cells]


def parse_page(html: str) -> dict | None:
    """``{name, props: {prop: {unit, coef, data, eq, err}}}`` for the thermal conductivity and specific-heat columns, or ``None``."""
    p = _Tables()
    p.feed(html)
    name = re.sub(r"^Material Properties:\s*", "", " ".join(re.findall(r"Material Properties:[^<\n]*", html)[:1])).strip()
    name = re.sub(r"\s*\(UNS [^)]*\)", "", name) or " ".join(p.title.replace("cryogenic material properties", "").split())
    for rows in p.tables:
        rows = [_clean(r) for r in rows]
        header = next((r for r in rows if any(c.lower() in COLUMNS for c in r)), None)
        if header is None:
            continue
        by_label = {r[0].lower(): r for r in rows if r}
        if not all(k in by_label for k in COEFFS) or "data range" not in by_label:
            continue
        out = {}
        for col, label in enumerate(header):
            if label.lower() not in COLUMNS:
                continue
            prop, unit = COLUMNS[label.lower()]
            try:
                coef = [float(by_label[k][col]) for k in COEFFS]
                lo, hi = (float(v) for v in by_label["data range"][col].replace("–", "-").split("-"))
                elo, ehi = (float(v) for v in by_label["equation range"][col].replace("–", "-").split("-"))
                err = float(by_label["curve fit % error relative to data"][col]) / 100
            except (KeyError, IndexError, ValueError):
                continue
            out[prop] = {"unit": unit, "coef": coef, "range": (max(lo, elo), min(hi, ehi)), "err": err}
        if out:
            return {"name": name, "props": out}
    return None


def evaluate(coef: list[float], T: float) -> float:
    x = math.log10(T)
    return 10 ** sum(c * x**i for i, c in enumerate(coef))


def grid(lo: float, hi: float) -> list[float]:
    return [lo * (hi / lo) ** (i / (POINTS - 1)) for i in range(POINTS)]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def category(name: str) -> str:
    low = name.lower()
    return next((c for key, c in CATEGORIES if key in low), "other")


NIST_STATEMENT = (
    "This data/work was created by employees of the National Institute of Standards and Technology (NIST), an agency of the Federal Government. "
    "Pursuant to title 17 United States Code Section 105, works of NIST employees are not subject to copyright protection in the United States. "
    "This data/work may be subject to foreign copyright.\n\n"
    "The data/work is provided by NIST as a public service and is expressly provided \"AS IS.\" NIST MAKES NO WARRANTY OF ANY KIND, EXPRESS, IMPLIED OR "
    "STATUTORY, INCLUDING, WITHOUT LIMITATION, THE IMPLIED WARRANTY OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT AND DATA "
    "ACCURACY. NIST does not warrant or make any representations regarding the use of the data or the results thereof, including but not limited to the "
    "correctness, accuracy, reliability or usefulness of the data. NIST SHALL NOT BE LIABLE AND YOU HEREBY RELEASE NIST FROM LIABILITY FOR ANY INDIRECT, "
    "CONSEQUENTIAL, SPECIAL, OR INCIDENTAL DAMAGES (INCLUDING DAMAGES FOR LOSS OF BUSINESS PROFITS, BUSINESS INTERRUPTION, LOSS OF BUSINESS INFORMATION, "
    "AND THE LIKE), WHETHER ARISING IN TORT, CONTRACT, OR OTHERWISE, ARISING FROM OR RELATING TO THE DATA (OR THE USE OF OR INABILITY TO USE THIS DATA), "
    "EVEN IF NIST HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.\n\n"
    "To the extent that NIST may hold copyright in countries other than the United States, you are hereby granted the non-exclusive irrevocable and "
    "unconditional right to print, publish, prepare derivative works and distribute the NIST data, in any medium, or authorize others to do so on your "
    "behalf, on a royalty-free basis throughout the world.")
CHANGE_NOTICE = ("Changed by SlideRule: NIST publishes polynomial fit coefficients, not tables. SlideRule evaluated each fit at {points} log-spaced temperatures "
                 "inside the range covered by both NIST's data and its equation, rounded the results to 6 significant figures and stores them as a curve that is "
                 "interpolated between those points (PCHIP). Only thermal conductivity and specific heat are used. Built {built}.")

def build(pages: dict[str, str], today: str, accessed: dict[str, str] | None = None) -> tuple[dict, dict, list[str]]:
    """``pages``: page path -> HTML. Returns manifest, data and the paths that could not be read."""
    sources, records, skipped = [], [], []
    for path, html in pages.items():
        page = parse_page(html)
        if page is None:
            skipped.append(path)
            continue
        sid = slug(path.split("/")[0])
        sources.append({"id": sid, "ref": f"NIST Cryogenic Technologies Group, Cryogenic Material Properties: {page['name']}; log10 polynomial fit evaluated by SlideRule",
                        "url": BASE + urllib.parse.quote(path, safe="/()"), "accessed": (accessed or {}).get(path, today)})
        props = {}
        for prop, d in page["props"].items():
            lo, hi = d["range"]
            xs = [round(T, 4) for T in grid(lo, hi)]
            props[prop] = {"curve": {"x_unit": "K", "method": "pchip", "x": xs, "y": [float(f"{evaluate(d['coef'], T):.6g}") for T in xs]},
                           "unit": d["unit"], "basis": "computed", "source": sid, "rel_uncertainty": d["err"],
                           "note": "rel_uncertainty is NIST's stated curve-fit error relative to its own data, not the measurement uncertainty or the spread between batches"}
        records.append({"id": slug(page["name"]), "name": page["name"], "category": category(page["name"]), "designation": "",
                        "condition": f"cryogenic, {min(d['range'][0] for d in page['props'].values()):g} to {max(d['range'][1] for d in page['props'].values()):g} K",
                        "properties": props})
    manifest = {"id": "nist-cryo", "version": "0.1.0", "title": "Cryogenic thermal properties (NIST Cryogenic Technologies Group fits)", "kind": "materials",
                "licence": "Source: National Institute of Standards and Technology (NIST), Cryogenic Technologies Group, https://trc.nist.gov/cryogenics/materials/materialproperties.htm. "
                           + CHANGE_NOTICE.format(points=POINTS, built=today) + " NIST statement for distributions of non-SRD data: " + NIST_STATEMENT,
                "status": "Fits evaluated inside the range covered by both NIST's data and its equation; not for design", "design_use": False,
                "sources": sources, "checksum": ""}
    return manifest, {"records": records}, skipped


def fetch(path: str, cache: Path | None) -> str:
    local = cache / re.sub(r"[^A-Za-z0-9._-]+", "_", path) if cache else None
    if local and local.is_file():
        return local.read_text(encoding="latin-1")
    url = BASE + urllib.parse.quote(path, safe="/()")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("latin-1")
    if local:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(html, encoding="latin-1")
    time.sleep(2.0)
    return html


def main(argv: list[str] | None = None) -> int:
    from sliderule.core import datapack

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache", type=Path, help="folder where fetched pages are kept (and reused)")
    ap.add_argument("--from-dir", type=Path, help="read pages from this cache folder only, no network")
    ap.add_argument("--out", type=Path, help="output folder (default: the user datapack folder / nist-cryo)")
    a = ap.parse_args(argv)
    pages, failed, accessed = {}, [], {}
    for path in PAGES:
        try:
            folder = a.from_dir or a.cache
            f = folder / re.sub(r"[^A-Za-z0-9._-]+", "_", path) if folder else None
            pages[path] = f.read_text(encoding="latin-1") if a.from_dir else fetch(path, a.cache)
            if f is not None and f.is_file():
                accessed[path] = time.strftime("%Y-%m-%d", time.localtime(f.stat().st_mtime))      # the day the page was fetched
        except (OSError, urllib.error.URLError) as exc:
            failed.append(f"{path}: {exc}")
    manifest, data, skipped = build(pages, time.strftime("%Y-%m-%d"), accessed)
    out = a.out or datapack.user_folder() / "nist-cryo"
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "NOTICE.md").write_text(
        "# NIST cryogenic material properties (derived data)\n\nSource: National Institute of Standards and Technology (NIST), Cryogenic Technologies Group, "
        "Cryogenic Material Properties, https://trc.nist.gov/cryogenics/materials/materialproperties.htm. Terms of use: https://www.nist.gov/open/license.\n\n"
        "## Change notice\n\n" + CHANGE_NOTICE.format(points=POINTS, built=time.strftime("%Y-%m-%d")) + "\n\n## NIST statement\n\n" + NIST_STATEMENT.replace("\n\n", "\n\n") + "\n",
        encoding="utf-8")
    datapack.seal(out)
    pack, errs = datapack.validate_pack(out)
    print(f"{len(data['records'])} materials written to {out}:", "valid" if pack else errs)
    for line in failed:
        print("could not fetch", line, file=sys.stderr)
    for path in skipped:
        print("no thermal-conductivity/specific-heat table found in", path, file=sys.stderr)
    return 0 if pack else 1


if __name__ == "__main__":
    sys.exit(main())
