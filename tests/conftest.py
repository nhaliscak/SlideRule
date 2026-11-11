import os

import pytest

from sliderule import settings


@pytest.fixture(autouse=True)
def _default_settings(request):
    """Every test starts and ends with default settings and nothing persisted."""
    settings.reset()
    if os.environ.get("CI") and request.module.__name__ != "test_timeout":
        settings.update(timeout_seconds=60)          # shared runners are several times slower than a desktop; tests about speed set their own limit
    yield
    settings.reset()


@pytest.fixture(autouse=True)
def _no_saved_lists():
    """Saved favorites and groups never leak between tests or into the user's real folder."""
    from sliderule import userlists

    userlists.configure(None)
    yield
    userlists.configure(None)


@pytest.fixture
def no_user_packs(tmp_path, monkeypatch):
    """Datapack tests see only the packs that ship with the program, never the packs in the user's own ~/.sliderule/datapacks (a local extract of reference data, say)."""
    from sliderule.core import datapack

    monkeypatch.setenv("SLIDERULE_HOME", str(tmp_path / "home"))
    datapack.reload()
    yield
    monkeypatch.undo()
    datapack.reload()
