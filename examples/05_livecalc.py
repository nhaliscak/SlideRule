"""Run a LiveCalc session from a file, the way the LiveCalc tab evaluates it.  python examples/05_livecalc.py [file]"""

import sys
from pathlib import Path

from sliderule import api

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("05_livecalc_session.txt")
lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#") and not ln.startswith("plot")]
result = api.handle("livecalc_eval", {"entries": lines, "sig_figs": 5})["result"]
for entry in result["entries"]:
    for line in entry["lines"]:
        shown = f"{line['value_text']} {line['unit']}".strip() if "value_text" in line else ("(function)" if line["kind"] == "function" else line["kind"])
        print(f"{line['text']:<22} {shown}")
