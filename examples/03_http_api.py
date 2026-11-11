"""Call a running SlideRule from another program, with nothing but the Python standard library.

Start a server first, in another terminal:
    sliderule serve --no-browser                      # the web app and the API, on http://127.0.0.1:8765
or  sliderule app --api --api-token mysecret          # the desktop window, with the API for other programs (token required)

Then:  python examples/03_http_api.py [--token mysecret] [--url http://127.0.0.1:8765]
"""

import argparse
import json
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8765")
ap.add_argument("--token", default=None, help="the bearer token, if the server was started with --api-token")
args = ap.parse_args()


def rpc(method, **params):
    """Every SlideRule function is reachable through one endpoint: POST /api/rpc {"method": ..., "params": ...}."""
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    req = urllib.request.Request(args.url + "/api/rpc", json.dumps({"method": method, "params": params}).encode(), headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        answer = json.load(r)
    if not answer["ok"]:
        raise SystemExit(f"{method}: {answer['error']['message']}")
    return answer["result"]


r = rpc("solve", calc_id="civil.column.euler_buckling", inputs={"E": "200 GPa", "I": "8.0e-6 m^4", "L": "3 m", "K": "1"},
        solve_for=["Pcr"], output_units={"Pcr": "kN"})
print("Pcr =", round(r["outputs"][0]["value"], 1), r["outputs"][0]["unit"])

c = rpc("convert", value=120, from_unit="km/h", to_unit="m/s")
print("120 km/h =", c["value_text"], c["unit"])

# The same calls as plain URLs (GET routes), and the interactive description of every route:
#   curl "http://127.0.0.1:8765/api/convert?value=120&from=km/h&to=m/s"
#   http://127.0.0.1:8765/api/docs
