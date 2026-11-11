"""Build the static, server-less web version into ./site.

The site is the same frontend plus a zip of the Python package; at runtime a Web Worker boots
Pyodide (CPython in WebAssembly), installs SymPy from the Pyodide CDN and imports the package.

    python scripts/build_web.py [--out site] [--pyodide 0.29.3]
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "sliderule"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "site"))
    ap.add_argument("--pyodide", default="0.29.3")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(PKG / "web", out)
    with zipfile.ZipFile(out / "sliderule_pkg.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PKG.rglob("*.py")):
            if "web" in f.relative_to(PKG).parts or f.name in ("server.py", "cli.py"):
                continue
            z.write(f, Path("sliderule") / f.relative_to(PKG))
        # property datapacks are JSON next to the code
        for f in sorted((PKG / "datapacks").rglob("*")):
            if f.is_file():
                z.write(f, Path("sliderule") / f.relative_to(PKG))
        # the HTML export embeds KaTeX (script, stylesheet, fonts) so exported pages work offline
        katex = PKG / "web" / "vendor" / "katex"
        for f in sorted([katex / "katex.min.css", katex / "katex.min.js", *(katex / "fonts").glob("*.woff2")]):
            z.write(f, Path("sliderule") / f.relative_to(PKG))
    cfg = {"engine": "pyodide", "pyodide": {"version": a.pyodide, "packages": ["sympy", "numpy", "scipy"], "bundle": "sliderule_pkg.zip"}}
    (out / "config.js").write_text(f"window.SLIDERULE_CONFIG = {json.dumps(cfg)};\n")
    (out / ".nojekyll").write_text("")
    print(f"built {out} ({sum(f.stat().st_size for f in out.rglob('*') if f.is_file()) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
