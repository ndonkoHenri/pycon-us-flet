"""Tests for ``Shown`` and the content line it logs (D-112, D-165).

``AppScaffold`` puts the screen's body in ``Shown``, the leaf that reads the feed's
version, so a refresh re-renders it and not the screen, and logs "Content shown" once
per version. The builders run outside a renderer, with the fixtures of
``tests/chrome.py`` (``test_scaffold.py`` has the rest of ``AppScaffold``).
"""

import asyncio
import inspect
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.ui import scaffold
from pycon_us.ui.scaffold import AppScaffold, Shown
from tests import chrome
from tests.chrome import body_of, view_at
from tests.fakes import FakePage, Hooks, MemoryPrefs

# The harness's fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference, hooks = (
    chrome.year,
    chrome.svc,
    chrome.page,
    chrome.conference,
    chrome.hooks,
)


async def test_the_content_line_is_logged_once_per_feed_version(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=scaffold.__name__)
    conference.source, conference.version = "bundled", 1
    view_at(hooks, page, "/now")
    view_at(hooks, page, "/schedule")  # a tab switch mounts another screen
    conference.source, conference.version = "network", 2  # a refresh published
    view_at(hooks, page, "/schedule")

    assert [deps for _, deps in hooks.effects] == [[1], [1], [2]]
    for setup, _ in hooks.effects:
        await setup()
    lines = [r.getMessage() for r in caplog.records if r.name == scaffold.__name__]
    assert lines == [
        "Content shown: bundled feed, version 1",
        "Content shown: network feed, version 2",
    ]


class SlowPrefs(MemoryPrefs):
    """SharedPreferences whose replies wait until the test releases them."""

    def init(self) -> None:
        super().init()
        self.release = asyncio.Event()

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        await self.release.wait()
        return await super()._invoke_method(method_name, arguments, timeout)


@pytest.fixture
def slow_prefs() -> SlowPrefs:
    return SlowPrefs()  # before ``page``: a service registers with a bound page


async def test_a_newer_version_does_not_cancel_the_line_of_the_one_shown_before(
    slow_prefs: SlowPrefs,
    hooks: Hooks,
    page: FakePage,
    svc: Services,
    conference: Conference,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.INFO, logger=scaffold.__name__)
    storage = Storage(prefs=slow_prefs, directory=tmp_path, year=2026)
    slow_svc = replace(svc, storage=storage)
    monkeypatch.setattr(scaffold, "use_services", lambda: slow_svc)
    conference.source, conference.version = "cache", 1
    view_at(hooks, page, "/now")
    ((setup, _),) = hooks.effects

    # Flet cancels the run in progress when the network version re-runs the effect.
    run = asyncio.create_task(setup())
    await asyncio.sleep(0)  # the run reaches the round trip
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    slow_prefs.release.set()
    for _ in range(5):  # the shielded round trip returns, then logs
        await asyncio.sleep(0)

    lines = [r.getMessage() for r in caplog.records if r.name == scaffold.__name__]
    assert lines == ["Content shown: cache feed, version 1"]


def test_only_a_leaf_component_reads_the_feed_so_a_refresh_skips_the_screen(
    hooks: Hooks, page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scaffold, "Shown", Shown)  # the real component
    reads: list[str] = []
    monkeypatch.setattr(scaffold, "use_conference", lambda: reads.append("read"))
    body = ft.Text("body")
    hooks.view_path = page.route = "/more"

    with Renderer().with_context():  # what calling a component needs, as in a render
        view = AppScaffold(title="More", body=body)

    shown = body_of(view)
    assert isinstance(shown, ft.Component)
    assert shown.fn is inspect.unwrap(Shown)
    assert shown.args == (body,)
    assert reads == []  # the screen's own render never subscribed to Conference


def test_shown_hands_back_the_same_body(hooks: Hooks, conference: Conference) -> None:
    body = ft.Text("body")
    assert inspect.unwrap(Shown)(body) is body
    assert [deps for _, deps in hooks.effects] == [[conference.version]]
