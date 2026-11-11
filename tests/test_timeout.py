import json
import math
import sys
import threading
import time

import pytest
import sympy
from fastapi.testclient import TestClient

from sliderule import api, cli, settings
from sliderule.core.timeout import TimeLimitExceeded, time_limit
from sliderule.server import create_app

client = TestClient(create_app(serve_frontend=False))


def busy(seconds):
    """Python-level work that makes plenty of function calls (what the guard can interrupt)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        math.sqrt(2.0)


# ---------------------------------------------------------------- the guard itself

def test_work_past_the_limit_is_stopped_and_work_within_it_is_not():
    t0 = time.monotonic()
    with pytest.raises(TimeLimitExceeded) as e:
        with time_limit(0.2):
            busy(5)
    assert e.value.seconds == 0.2 and time.monotonic() - t0 < 2
    with time_limit(2):
        busy(0.05)


@pytest.mark.parametrize("watchdog", [True, False])
def test_both_mechanisms_stop_runaway_work_and_leave_no_trace(monkeypatch, watchdog):
    """The watchdog timer (normal Python) and the profile hook (used where threads cannot start, e.g. Pyodide) behave the same."""
    from sliderule.core import timeout

    monkeypatch.setattr(timeout, "_watchdog_ok", watchdog)
    before = sys.getprofile()
    with pytest.raises(TimeLimitExceeded):
        with time_limit(0.2):
            busy(5)
    assert sys.getprofile() is before
    with time_limit(0.5):                                   # the next block is not disturbed by a stray exception from the previous one
        busy(0.05)
    time.sleep(0.4)
    with time_limit(2):
        with pytest.raises(TimeLimitExceeded):
            with time_limit(0.2):
                busy(5)


def test_none_means_no_limit_and_installs_nothing():
    before = sys.getprofile()
    with time_limit(None):
        assert sys.getprofile() is before
        busy(0.3)


def test_limits_nest_and_the_earliest_wins_and_profile_is_restored():
    before = sys.getprofile()
    with pytest.raises(TimeLimitExceeded) as e:
        with time_limit(0.2):
            with time_limit(30):
                busy(5)
    assert e.value.seconds == 0.2                       # the inner, longer limit did not claim the outer one's expiry
    with pytest.raises(TimeLimitExceeded) as e2:
        with time_limit(30):
            with time_limit(0.2):
                busy(5)
    assert e2.value.seconds == 0.2
    assert sys.getprofile() is before
    with time_limit(None):
        with time_limit(0.2):
            pass
    assert sys.getprofile() is before


def test_code_that_catches_exceptions_cannot_swallow_the_stop():
    def stubborn():
        end = time.monotonic() + 5
        while time.monotonic() < end:
            try:
                math.sqrt(2.0)
            except Exception:   # noqa: BLE001 - what SymPy does in places
                pass
    with pytest.raises(TimeLimitExceeded):
        with time_limit(0.2):
            stubborn()


def test_limits_are_per_thread():
    results = {}

    def work(name, limit, seconds):
        try:
            with time_limit(limit):
                busy(seconds)
            results[name] = "done"
        except TimeLimitExceeded:
            results[name] = "stopped"
    # the short one has far more work than its limit allows (so a slow, busy runner cannot let it finish first); the long one finishes well within its limit
    ts = [threading.Thread(target=work, args=("short", 0.2, 8)), threading.Thread(target=work, args=("long", 20, 0.6))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results == {"short": "stopped", "long": "done"}


# ---------------------------------------------------------------- the setting

def test_defaults_validation_and_the_risk_acknowledgement():
    s = settings.get()
    assert s["timeout_enabled"] and s["timeout_seconds"] == settings.DEFAULT_SECONDS == 10.0 and settings.limit() == 10.0
    assert s["disable_warning"] == settings.DISABLE_WARNING
    for bad in (0, 0.5, 5000, "ten", True, None.__class__):
        with pytest.raises(settings.SettingsError):
            settings.update(timeout_seconds=bad)
    with pytest.raises(settings.SettingsError) as e:
        settings.update(timeout_enabled=False)
    assert e.value.code == "WARNING_REQUIRED" and "never finishes" in str(e.value) and settings.limit() == 10.0
    settings.update(timeout_enabled=False, acknowledge_risk=True)
    assert settings.limit() is None and not settings.get()["timeout_enabled"]
    settings.update(timeout_seconds=45)                  # changing the number while off is fine and keeps it off
    assert settings.limit() is None and settings.get()["timeout_seconds"] == 45
    settings.update(timeout_enabled=True)                # turning it on never needs acknowledgement
    assert settings.limit() == 45


def test_settings_persist_to_a_file_and_bad_files_are_ignored(tmp_path):
    f = tmp_path / "s" / "settings.json"
    settings.configure(f)
    settings.update(timeout_seconds=25)
    settings.update(timeout_enabled=False, acknowledge_risk=True)
    assert json.loads(f.read_text()) == {"timeout_enabled": False, "timeout_seconds": 25.0}
    settings.reset()
    assert settings.limit() == 10.0
    settings.configure(f)
    assert settings.limit() is None and settings.get()["timeout_seconds"] == 25.0
    for junk in ("{not json", json.dumps({"timeout_seconds": 99999}), json.dumps({"timeout_enabled": "yes"}), "[]"):
        settings.reset()
        f.write_text(junk)
        settings.configure(f)
        assert settings.limit() == 10.0


# ---------------------------------------------------------------- the API and the calculation paths it guards

def slow_solve(*_a, **_k):
    busy(20)
    raise AssertionError("should have been stopped")


def test_api_settings_methods_and_meta():
    assert api.meta()["settings"]["timeout_seconds"] == 10.0
    assert api.handle("settings_set", {"timeout_seconds": 30})["result"]["timeout_seconds"] == 30
    r = api.handle("settings_set", {"timeout_enabled": False})
    assert not r["ok"] and r["error"]["code"] == "WARNING_REQUIRED" and r["error"]["status"] == 409 and "keeps running until it ends" in r["error"]["message"]
    assert api.handle("settings_get")["result"]["timeout_enabled"] is True
    assert api.handle("settings_set", {"timeout_enabled": False, "acknowledge_risk": True})["result"]["timeout_enabled"] is False
    assert api.handle("settings_set", {"timeout_seconds": 0})["error"]["status"] == 400


def test_a_calculation_over_the_limit_is_stopped_with_a_clear_error(monkeypatch):
    monkeypatch.setattr(api, "_solve", slow_solve)
    settings.update(timeout_seconds=1)
    t0 = time.monotonic()
    r = api.handle("solve", {"calc_id": next(iter(api.list_calculations()["results"]))["id"], "inputs": {}})
    assert not r["ok"] and r["error"]["code"] == "TIMEOUT" and r["error"]["status"] == 408
    assert "longer than 1 s" in r["error"]["message"] and "Settings" in r["error"]["message"] and time.monotonic() - t0 < 8
    assert api.handle("meta")["ok"]                      # the engine is fine afterwards


def test_with_the_limit_off_the_same_work_runs_to_completion(monkeypatch):
    done = []
    monkeypatch.setattr(api, "_solve", lambda *a, **k: (busy(1.3), done.append(1), type("S", (), {"to_dict": lambda self: {"ok": True}})())[2])
    settings.update(timeout_seconds=1)
    cid = api.list_calculations()["results"][0]["id"]
    assert api.handle("solve", {"calc_id": cid, "inputs": {}})["error"]["code"] == "TIMEOUT"
    settings.update(timeout_enabled=False, acknowledge_risk=True)
    assert api.handle("solve", {"calc_id": cid, "inputs": {}})["ok"] and done == [1]


def test_every_heavy_entry_point_is_guarded():
    import inspect
    for name in ("solve", "custom_save", "custom_import", "design_check_block", "design_solve", "design_validate", "design_export_document"):
        assert hasattr(getattr(api, name), "__wrapped__"), name
    assert "limited" in inspect.getsource(api)


def test_http_timeout_and_settings_endpoints(monkeypatch):
    monkeypatch.setattr(api, "_solve", slow_solve)
    settings.update(timeout_seconds=1)
    cid = api.list_calculations()["results"][0]["id"]
    r = client.post(f"/api/calculations/{cid}/solve", json={"inputs": {}})
    assert r.status_code == 408 and r.json()["detail"]["code"] == "TIMEOUT"
    assert client.get("/api/settings").json()["timeout_seconds"] == 1.0
    r = client.put("/api/settings", json={"timeout_enabled": False})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "WARNING_REQUIRED"
    assert client.put("/api/settings", json={"timeout_enabled": False, "acknowledge_risk": True}).json()["timeout_enabled"] is False
    assert client.put("/api/settings", json={"timeout_seconds": 99999}).status_code == 400
    assert client.post("/api/rpc", json={"method": "settings_get", "params": {}}).json()["result"]["timeout_enabled"] is False


def test_a_slow_custom_integral_is_stopped_by_the_setting_not_a_fixed_five_seconds(monkeypatch):
    monkeypatch.setattr(sympy.Integral, "doit", lambda self, **kw: busy(5))      # a stand-in for an integrand SymPy chews on for a long time
    doc = {"id": "custom.slow", "name": "slow", "disciplines": ["mechanical"],
           "variables": [{"key": "Q", "label": "Q", "unit": "1"}, {"key": "d", "label": "d", "unit": "1"}],
           "equations": [{"text": "Q = integrate(exp(-x**2)*sin(x)/(1 + x**4), (x, 0, d))"}], "outputs": ["Q"]}
    settings.update(timeout_seconds=1)
    t0 = time.monotonic()
    r = api.custom_validate(doc)
    assert not r["ok"] and "longer than 1 s" in r["errors"][0]["message"] and time.monotonic() - t0 < 4


# ---------------------------------------------------------------- command line

def test_cli_settings(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLIDERULE_HOME", str(tmp_path))
    run = lambda *a: cli.main(["--equations-dir", str(tmp_path / "eq"), *a])   # noqa: E731
    assert run("settings") == 0 and "time limit: 10 s" in capsys.readouterr().out
    assert run("settings", "--timeout", "30") == 0 and "30 s" in capsys.readouterr().out
    assert json.loads((tmp_path / "settings.json").read_text())["timeout_seconds"] == 30.0
    monkeypatch.setattr("builtins.input", lambda _="": "no")
    assert run("settings", "--no-timeout") == 1
    cap = capsys.readouterr()
    assert "WARNING" in cap.err and "never finishes" in cap.err and "unchanged" in cap.err and settings.limit() == 30.0
    monkeypatch.setattr("builtins.input", lambda _="": "yes")
    assert run("settings", "--no-timeout") == 0 and "OFF" in capsys.readouterr().out and settings.limit() is None
    settings.reset()
    assert run("settings") == 0 and "OFF" in capsys.readouterr().out      # persisted across runs
    assert run("settings", "--enable-timeout") == 0 and settings.limit() == 30.0
    assert run("settings", "--no-timeout", "--yes") == 0 and settings.limit() is None
    assert run("settings", "--timeout", "0") == 2
    assert run("settings", "--no-timeout", "--enable-timeout") == 2
