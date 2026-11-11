"""`sliderule app`: the native window around the local server, tested with a stand-in for pywebview (no display needed)."""

import argparse
import sys
import types
import urllib.error
import urllib.request


from sliderule import cli


API_OFF = {"api": False, "api_port": 8765, "api_token": None, "api_origin": None}


def fake_webview(start):
    mod = types.ModuleType("webview")
    mod.settings = {"ALLOW_DOWNLOADS": False}
    mod.errors = types.SimpleNamespace(WebViewException=type("WebViewException", (Exception,), {}))
    mod.windows = []
    mod.create_window = lambda title, url, **kw: mod.windows.append((title, url, kw))
    mod.start = lambda: start(mod)
    return mod


def run(monkeypatch, start, port=0, api=None):
    mod = fake_webview(start)
    monkeypatch.setitem(sys.modules, "webview", mod)
    return cli.cmd_app(argparse.Namespace(port=port, **{**API_OFF, **(api or {})})), mod


def test_the_window_opens_only_once_the_server_answers_and_allows_downloads(monkeypatch):
    seen = {}

    def start(mod):
        title, url, kw = mod.windows[0]
        seen["url"] = url
        with urllib.request.urlopen(url, timeout=30) as r:                        # the server is already up when the window would load
            seen["status"], seen["page"] = r.status, r.read().decode()
        seen["downloads"] = mod.settings["ALLOW_DOWNLOADS"]

    code, mod = run(monkeypatch, start)
    assert code == 0 and seen["status"] == 200 and "SlideRule" in seen["page"] and seen["downloads"] is True       # Export / Save case are download links
    assert mod.windows[0][0] == "SlideRule" and seen["url"].startswith("http://127.0.0.1:")


def test_default_port_is_a_free_one_not_a_fixed_one(monkeypatch):
    urls = []
    for _ in range(2):
        run(monkeypatch, lambda mod: urls.append(mod.windows[0][1]))
    assert all(u.startswith("http://127.0.0.1:") and not u.startswith("http://127.0.0.1:8765/") for u in urls)


def test_no_gui_toolkit_gives_advice_not_a_traceback(monkeypatch, capsys):
    def start(mod):
        raise mod.errors.WebViewException("no toolkit")

    code, _ = run(monkeypatch, start)
    err = capsys.readouterr().err
    assert code == 3 and "pywebview[qt]" in err and "sliderule serve" in err


def test_missing_pywebview_points_at_the_extra(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "webview", None)                             # makes `import webview` raise ImportError
    assert cli.cmd_app(argparse.Namespace(port=0, **API_OFF)) == 3
    assert "sliderule[desktop]" in capsys.readouterr().err


def test_an_unstartable_server_is_reported(monkeypatch, capsys):
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        monkeypatch.setattr(cli, "_SERVER_WAIT_SECONDS", 1.0)                         # do not wait the full 20 s
        code, _ = run(monkeypatch, lambda mod: None, port=busy.getsockname()[1])
    assert code == 1 and "did not start" in capsys.readouterr().err


def test_api_option_serves_the_api_to_other_programs_on_a_known_port(monkeypatch, capsys):
    port = cli._free_port()
    got = {}

    def start(mod):                                                              # the window is "open"; now act as another program
        def call(headers):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/rpc", data=b'{"method": "settings_get", "params": {}}', headers={"Content-Type": "application/json", **headers})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status, r.read().decode()
            except urllib.error.HTTPError as exc:
                return exc.code, ""

        got["no token"] = call({})[0]
        got["token"] = call({"Authorization": "Bearer s3cret"})
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"Authorization": "Bearer s3cret"}), timeout=10)      # the API port serves no web page
            got["page"] = 200
        except urllib.error.HTTPError as exc:
            got["page"] = exc.code

    code, _ = run(monkeypatch, start, api=dict(api=True, api_port=port, api_token="s3cret", api_origin=["http://localhost:3000"]))
    out = capsys.readouterr().out
    assert code == 0 and got["no token"] == 401 and got["token"][0] == 200 and "timeout_seconds" in got["token"][1] and got["page"] == 404
    assert f"POST http://127.0.0.1:{port}/api/rpc" in out and "bearer token" in out and "http://localhost:3000" in out and "stops when the window is closed" in out


def test_api_without_a_token_says_so(monkeypatch, capsys):
    run(monkeypatch, lambda mod: None, api=dict(api=True, api_port=cli._free_port()))
    assert "NO TOKEN" in capsys.readouterr().out


def test_a_busy_api_port_is_reported_before_the_window_opens(monkeypatch, capsys):
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        monkeypatch.setattr(cli, "_SERVER_WAIT_SECONDS", 1.0)
        code, mod = run(monkeypatch, lambda m: None, api=dict(api=True, api_port=busy.getsockname()[1]))
    assert code == 1 and "API server did not start" in capsys.readouterr().err and mod.windows == []
