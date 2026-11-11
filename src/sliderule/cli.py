"""Command-line entry point: ``sliderule serve | app | list | show | solve | convert``."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import webbrowser

from pathlib import Path

from . import __version__, api, settings, usercalcs, userlists


def _fmt_diag(d: dict) -> str:
    icon = {"error": "✗", "warning": "!", "info": "·"}.get(d["level"], "?")
    return f"  {icon} [{d['code']}] {d['message']}"


def cmd_list(a: argparse.Namespace) -> int:
    res = api.list_calculations(a.query or "", a.discipline, a.variable, a.solves_for, a.sub, level=a.level)
    for r in res["results"]:
        print(f"{r['id']:<52} {r['name']}")
    print(f"\n{res['count']} calculation(s)", file=sys.stderr)
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    c = api.handle("get_calculation", {"calc_id": a.id})
    if not c["ok"]:
        print(c["error"]["message"], file=sys.stderr)
        return 2
    c = c["result"]
    print(f"{c['name']}  ({', '.join(c['disciplines'])})\n{c['description']}\n")
    for e in c["equations"]:
        print(f"  {e['title']}: {e['text']}")
    print("\nVariables:")
    for v in c["variables"]:
        tag = f"= {v['constant']} {v['unit']} (constant)" if v["constant"] is not None else f"[{v['unit']}]"
        print(f"  {v['key']:<8} {v['label']:<44} {tag}")
    print("\nExample:", " ".join(f"{k}='{x}'" for k, x in c["example"].items()))
    return 0


def cmd_solve(a: argparse.Namespace) -> int:
    inputs = {}
    for item in a.assignments:
        if "=" not in item:
            print(f"expected KEY=VALUE UNIT, got {item!r}", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        inputs[k.strip()] = v.strip()
    if a.example:
        c = api.get_calculation(a.id)
        inputs = {**c["example"], **inputs}
    units = dict(u.split("=", 1) for u in (a.unit or []))
    search = {}
    for item in a.search or []:                      # KEY=LO:HI, each end a number or a quantity such as "0.01 1/s"
        key, _, rng = item.partition("=")
        lo, _, hi = rng.partition(":")
        if not key or not hi:
            print(f"expected KEY=LO:HI for --search, got {item!r}", file=sys.stderr)
            return 2
        search[key.strip()] = [lo.strip(), hi.strip()]
    res = api.handle("solve", {"calc_id": a.id, "inputs": inputs, "solve_for": a.solve_for, "output_units": units, "sig_figs": a.sig_figs, "search": search or None})
    if not res["ok"]:
        print(res["error"]["message"], file=sys.stderr)
        return 2
    sol = res["result"]
    if a.json:
        print(json.dumps(sol, indent=2, ensure_ascii=False))
        return 0 if sol["ok"] else 1
    for d in sol["diagnostics"]:
        print(_fmt_diag(d), file=sys.stderr if d["level"] != "info" else sys.stdout)
    if not sol["ok"]:
        return 1
    for o in sol["outputs"]:
        print(f"{o['key']} = {o['value_text']} {o['unit']}   ({o['label']})")
    if a.steps:
        for st in sol["steps"][a.steps]:
            print(f"\n## {st['title']}")
            for line in st["lines"]:
                print(f"  {line['latex']}" + (f"    % {line['note']}" if line["note"] else ""))
    return 0


def cmd_convert(a: argparse.Namespace) -> int:
    r = api.convert(a.value, a.src, a.dst)
    if not r["ok"]:
        print(r["error"], file=sys.stderr)
        return 2
    print(f"{a.value} {a.src} = {r['value_text']} {r['unit']}")
    for n in r["notes"]:
        print(f"  · {n}")
    return 0


def _reload_app():
    """App factory for ``serve --reload``: uvicorn imports it in a fresh process on every restart, so the
    settings and the equations folder that ``main`` configures have to be set up again here."""
    from .server import ApiGuard, bound_to_loopback, create_app

    settings.configure(settings.default_path())
    userlists.configure(userlists.default_path())
    for prob in usercalcs.configure(os.environ.get("SLIDERULE_EQUATIONS_DIR") or usercalcs.default_folder()):
        print(f"skipped {prob['file']}: {prob['message']}", file=sys.stderr)
    return create_app(guard=ApiGuard(any_host=not bound_to_loopback(os.environ.get("SLIDERULE_SERVE_HOST", "127.0.0.1"))))


def _serve(host: str, port: int, open_browser: bool, reload: bool = False, equations_dir: str | None = None) -> None:
    try:
        import uvicorn

        from .server import ApiGuard, bound_to_loopback, create_app
    except ImportError:
        print("The local server needs extra dependencies:  pip install 'sliderule[server]'", file=sys.stderr)
        raise SystemExit(3) from None
    url = f"http://{host}:{port}/"
    local = bound_to_loopback(host)
    if not local:
        print(f"WARNING: --host {host} makes SlideRule reachable from other computers. There is no login or encryption, and the API can write your equation and list files: "
              "use it only on a network you trust.", file=sys.stderr)
    os.environ["SLIDERULE_SERVE_HOST"] = host                 # a --reload restart builds the app again in a fresh process
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if reload:
        if equations_dir:
            os.environ["SLIDERULE_EQUATIONS_DIR"] = equations_dir
        print(f"SlideRule {__version__} serving on {url}  (restarts when a .py file changes; Ctrl+C to stop)")
        uvicorn.run("sliderule.cli:_reload_app", factory=True, reload=True, reload_dirs=[str(Path(__file__).parent)], host=host, port=port, log_level="warning")
        return
    print(f"SlideRule {__version__} serving on {url}  (Ctrl+C to stop)")
    uvicorn.run(create_app(guard=ApiGuard(any_host=not local)), host=host, port=port, log_level="warning")


def cmd_serve(a: argparse.Namespace) -> int:
    _serve(a.host, a.port, not a.no_browser, a.reload, a.equations_dir)
    return 0


_SERVER_WAIT_SECONDS = 20          # how long `sliderule app` waits for its private server before giving up


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(uvicorn, app, port: int):
    """Run ``app`` on 127.0.0.1:``port`` in a background thread; the running server once it answers, else ``None``."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.monotonic() + _SERVER_WAIT_SECONDS
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        return None
    return server


def cmd_app(a: argparse.Namespace) -> int:
    """Native window around the local server (needs pywebview and a GUI toolkit); with ``--api`` the same process also serves the API to other programs."""
    try:
        import uvicorn
        import webview

        from .server import ApiGuard, create_app
    except ImportError:
        print("Desktop mode needs extras:  pip install 'sliderule[desktop]'", file=sys.stderr)
        return 3
    servers = []
    if a.api:                                           # for other programs: a known port, API only, guarded (see server.ApiGuard)
        guard = ApiGuard(token=a.api_token or None, origins=tuple(a.api_origin or ()))
        api_server = _start_server(uvicorn, create_app(serve_frontend=False, guard=guard), a.api_port)
        if api_server is None:
            print(f"The API server did not start on port {a.api_port} (is it in use?). Pick another with --api-port.", file=sys.stderr)
            return 1
        servers.append(api_server)
        base = f"http://127.0.0.1:{a.api_port}"
        print(f"SlideRule API for other programs: POST {base}/api/rpc  (docs: {base}/api/docs)")
        print("  protected by a bearer token (Authorization: Bearer <token>)" if guard.token else
              "  NO TOKEN: any program on this computer can use it; add --api-token to require one")
        if guard.origins:
            print("  web pages allowed to call it: " + ", ".join(guard.origins))
        print("  it stops when the window is closed")
    port = a.port or _free_port()                       # a fixed port that is busy would show another program's page in the window
    window_server = _start_server(uvicorn, create_app(), port)
    if window_server is None:
        print(f"The local server did not start on port {port} (is it in use?). Try again without --port.", file=sys.stderr)
        for server in servers:
            server.should_exit = True
        return 1
    servers.append(window_server)
    webview.settings["ALLOW_DOWNLOADS"] = True          # Export, Save case and CSV buttons are download links; pywebview blocks them by default
    webview.create_window("SlideRule", f"http://127.0.0.1:{port}/", width=1280, height=860)
    try:
        webview.start()
    except webview.errors.WebViewException:
        print("pywebview found no GUI toolkit. Install one:  pip install 'pywebview[qt]'  (or GTK with WebKit2: your system's python-gobject and webkit2gtk packages).\n"
              "Or use  sliderule serve  to run in your browser.", file=sys.stderr)
        return 3
    finally:
        for server in servers:
            server.should_exit = True
    return 0


def _read_json(path: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return None


def cmd_data(a: argparse.Namespace) -> int:
    from .core import datapack as dp

    act = a.action
    if act == "path":
        print(dp.user_folder())
        return 0
    if act == "list":
        for p in api.data_packs()["packs"]:
            print(f"{p['id']:<24} v{p['version']:<8} {p['records']:>4} records  {'custom' if p['custom'] else 'built-in':<9} {p['title']}"
                  f"{'' if p['design_use'] else '  [not for design]'}")
        for name, errs in dp.problems().items():
            print(f"REFUSED {name}: {len(errs)} problem(s), run `sliderule data validate`", file=sys.stderr)
        return 0
    if act == "show":
        if len(a.items) != 2:
            print("usage: sliderule data show PACK RECORD", file=sys.stderr)
            return 2
        r = api.handle("data_record", {"pack": a.items[0], "record_id": a.items[1]})
        if not r["ok"]:
            print(r["error"]["message"], file=sys.stderr)
            return 2
        r = r["result"]
        print(f"{r['name']}  [{r['pack']} v{r['pack_version']}]  {r['status']}\n")
        for n, v in r["properties"].items():
            if "curve" in v:
                rg = v["range"]
                unc = f", within {v['rel_uncertainty'] * 100:g} % of the reference" if v.get("rel_uncertainty") else ""
                print(f"  {v['label']:<42} curve {rg['min']:g} to {rg['max']:g} {rg['unit']}, in {v['unit']}  [{v['basis']}{unc}; {v['source_ref'][:50]}]")
                continue
            rng = f"  ({v['low']:g} to {v['high']:g})" if "low" in v and "high" in v else ""
            print(f"  {v['label']:<42} {v['value']:g} {v['unit']}{rng}  [{v['basis']}; {v['source_ref'][:60]}]")
        return 0
    if act == "value":
        if len(a.items) != 3:
            print("usage: sliderule data value PACK RECORD PROPERTY [--at T] [--at-unit degC] [--unit Pa*s]", file=sys.stderr)
            return 2
        r = api.handle("data_value", {"pack": a.items[0], "record_id": a.items[1], "prop": a.items[2], "x": a.at, "x_unit": a.at_unit, "unit": a.unit})
        if not r["ok"]:
            print(r["error"]["message"], file=sys.stderr)
            return 2
        r = r["result"]
        at = f" at {r['x']:g} {r['x_unit']}" if "x" in r else ""
        unc = f", within {r['rel_uncertainty'] * 100:g} % of the reference" if r.get("rel_uncertainty") else ""
        print(f"{r['value']:.6g} {r['unit']}{at}  [{r['basis']}{unc}; {r['pack']} v{r['pack_version']}]")
        return 0
    folders = [Path(i) for i in a.items] or sorted(p for base in (dp.BUILTIN, dp.user_folder()) if base.is_dir() for p in base.iterdir() if p.is_dir())
    rc = 0
    for f in folders:
        if act == "seal":
            print(f"{f}: sealed {dp.seal(f)}")
            continue
        pack, errs = dp.validate_pack(f)
        print(f"{f.name}: {'ok' if pack else 'REFUSED'}")
        for e in errs:
            print(f"  ✗ {e}")
        rc = rc or (0 if pack else 1)
    return rc


def cmd_custom(a: argparse.Namespace) -> int:
    act = a.action
    if act == "path":
        print(usercalcs.storage().get("path", "(no folder)"))
        return 0
    if act == "list":
        for d in usercalcs.listing():
            print(f"{d['id']:<44} {d['name']}")
        print(f"\n{len(usercalcs.listing())} user-defined calculation(s) in {usercalcs.storage().get('path')}", file=sys.stderr)
        return 0
    if act == "remove":
        r = api.handle("custom_delete", {"calc_id": a.items[0]})
        print("removed" if r["ok"] else r["error"]["message"], file=sys.stderr if not r["ok"] else sys.stdout)
        return 0 if r["ok"] else 1
    if act == "export":
        r = api.custom_export(a.items or None)
        out = Path(a.output or r["filename"])
        out.write_text(json.dumps(r["document"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {r['count']} calculation(s) to {out}")
        return 0
    status = 0
    for path in a.items:     # validate | import
        doc = _read_json(path)
        if doc is None:
            status = 1
            continue
        r = api.handle("custom_import", {"document": doc, "on_conflict": a.on_conflict, "dry_run": act == "validate"})
        if not r["ok"]:
            print(f"{path}: {r['error']['message']}", file=sys.stderr)
            status = 1
            continue
        for row in r["result"]["results"]:
            extra = f" -> {row['new_id']}" if row.get("new_id") else ""
            print(f"{path}: {row['id'] or row['name']}: {row['status']}{extra}")
            for e in row.get("errors", []):
                print(f"    {e['field']}: {e['message']}")
            status |= row["status"] == "error"
    return status


def cmd_settings(a: argparse.Namespace) -> int:
    if a.no_timeout and a.enable_timeout:
        print("choose either --no-timeout or --enable-timeout", file=sys.stderr)
        return 2
    changes: dict = {}
    if a.timeout is not None:
        changes["timeout_seconds"] = a.timeout
    if a.enable_timeout:
        changes["timeout_enabled"] = True
    if a.no_timeout:
        print("WARNING: " + settings.DISABLE_WARNING, file=sys.stderr)
        if not a.yes:
            try:
                answer = input("Type 'yes' to turn the time limit off: ")
            except EOFError:
                answer = ""
            if answer.strip().lower() != "yes":
                print("unchanged", file=sys.stderr)
                return 1
        changes["timeout_enabled"] = False
    if changes:
        r = api.handle("settings_set", {**changes, "acknowledge_risk": True})
        if not r["ok"]:
            print(r["error"]["message"], file=sys.stderr)
            return 2
    s = settings.get()
    print("time limit: " + (f"{s['timeout_seconds']:g} s" if s["timeout_enabled"] else "OFF (calculations are never stopped)"))
    print(f"stored in:  {s['storage'].get('path', '(not persisted)')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sliderule", description="Unit-aware engineering calculations with worked solutions.")
    p.add_argument("--version", action="version", version=f"sliderule {__version__}")
    p.add_argument("--equations-dir", help="folder holding your own equations (default: $SLIDERULE_HOME/calculations or ~/.sliderule/calculations)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the local web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--reload", action="store_true", help="restart the server when a Python file changes (development; HTML/JS/CSS edits show on a page refresh anyway)")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("app", help="run as a native desktop window (needs sliderule[desktop])")
    s.add_argument("--port", type=int, default=0, help="port for the window's private local server (default: any free port)")
    s.add_argument("--api", action="store_true", help="also serve the API on a known port so other programs on this computer can run SlideRule functions (POST /api/rpc)")
    s.add_argument("--api-port", type=int, default=8765, help="port for --api (default 8765)")
    s.add_argument("--api-token", default=os.environ.get("SLIDERULE_API_TOKEN"), help="require this bearer token on every API request (default: $SLIDERULE_API_TOKEN, else none)")
    s.add_argument("--api-origin", action="append", metavar="ORIGIN", help="let a web page at this origin (for example http://localhost:3000) call the API; repeatable")
    s.set_defaults(fn=cmd_app)

    s = sub.add_parser("list", help="search calculations")
    s.add_argument("query", nargs="?")
    s.add_argument("-d", "--discipline", action="append", default=[])
    s.add_argument("-v", "--variable", action="append", default=[], help="require a variable (symbol, word or quantity kind)")
    s.add_argument("--solves-for", action="append", default=[])
    s.add_argument("-s", "--sub", action="append", default=[], help="sub-discipline (substring), e.g. 'hydraulic'")
    s.add_argument("--level", choices=["basic", "advanced"], default="", help="basic: classical mechanics and college-level chemistry; advanced (default): everything")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("show", help="describe one calculation")
    s.add_argument("id")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("solve", help="solve a calculation")
    s.add_argument("id")
    s.add_argument("assignments", nargs="*", help="KEY='VALUE UNIT' ...")
    s.add_argument("--for", dest="solve_for", action="append", help="variable to solve for (repeatable)")
    s.add_argument("--unit", action="append", help="output unit, KEY=UNIT (repeatable)")
    s.add_argument("--example", action="store_true", help="start from the calculation's built-in example inputs")
    s.add_argument("--steps", choices=["symbolic", "numeric"], help="print worked steps (LaTeX)")
    s.add_argument("--search", action="append", metavar="KEY=LO:HI", help="range to search when a value must be found numerically (repeatable)")
    s.add_argument("--sig-figs", type=int, default=5)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_solve)

    s = sub.add_parser("custom", help="manage your own equations (files in the equations folder)")
    s.add_argument("action", choices=["list", "path", "import", "validate", "export", "remove"])
    s.add_argument("items", nargs="*", help="files to import/validate, ids to export/remove")
    s.add_argument("-o", "--output", help="export: file to write")
    s.add_argument("--on-conflict", choices=["rename", "replace", "skip"], default="rename", help="import: when an id already exists")
    s.set_defaults(fn=cmd_custom)

    s = sub.add_parser("data", help="property datapacks: list, show a record, get a value, validate or seal a pack folder")
    s.add_argument("action", choices=["list", "show", "value", "validate", "seal", "path"])
    s.add_argument("items", nargs="*", help="show: PACK RECORD; value: PACK RECORD PROPERTY; validate/seal: pack folders (default: every installed pack)")
    s.add_argument("--at", type=float, help="value: the temperature for a curve")
    s.add_argument("--at-unit", default="K", help="value: unit of --at (default K)")
    s.add_argument("--unit", help="value: unit to give the answer in")
    s.set_defaults(fn=cmd_data)

    s = sub.add_parser("settings", help="show or change settings (the time limit for long calculations)")
    s.add_argument("--timeout", type=float, metavar="SECONDS", help="stop calculations that run longer than this")
    s.add_argument("--enable-timeout", action="store_true", help="switch the time limit back on")
    s.add_argument("--no-timeout", action="store_true", help="switch the time limit off (asks for confirmation)")
    s.add_argument("--yes", action="store_true", help="with --no-timeout: confirm without asking")
    s.set_defaults(fn=cmd_settings)

    s = sub.add_parser("convert", help="convert a value between units")
    s.add_argument("value", type=float)
    s.add_argument("src")
    s.add_argument("dst")
    s.set_defaults(fn=cmd_convert)

    a = p.parse_args(argv)
    userlists.configure(userlists.default_path())
    settings.configure(settings.default_path())     # before the equations folder: loading user equations can evaluate integrals
    for prob in usercalcs.configure(a.equations_dir or usercalcs.default_folder()):
        print(f"skipped {prob['file']}: {prob['message']}", file=sys.stderr)
    try:
        return a.fn(a)
    except api.ApiError as exc:
        print(exc.message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
