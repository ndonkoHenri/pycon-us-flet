"""Tests for About this app: the build's facts and the 7-tap Developer unlock (#88; D-73).

``AboutApp`` runs outside a renderer: its hooks and ``AppScaffold`` are replaced, and a
fake page is bound as Flet binds a session's page. How the page looks and reads is
checked on devices (the PR).
"""

import inspect
import json
import platform
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.components.hooks.use_ref import MutableRef

import pycon_us
from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import about_app
from pycon_us.screens.about_app import UNLOCK_TAPS, AboutApp
from pycon_us.services import Services, errors
from pycon_us.services.storage import Storage
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)


@pytest.fixture
def page() -> Iterator[FakePage]:
    """Yield a ``FakePage`` bound as the page Flet's handlers see."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The 2026 ``Services`` over in-memory prefs and device services."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    """Fresh ``Prefs`` as in a packaged build: Developer locked, error details off."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    monkeypatch.setattr(errors, "_details", False)
    return Prefs()


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, svc: Services, prefs: Prefs, page: FakePage
) -> Callable[[], dict[str, Any]]:
    """Render ``AboutApp`` and return what it passed to ``AppScaffold``.

    The tap count is one ref, and the unsaved flag one state, that live as long as the
    page, as Flet's do.
    """
    ref = MutableRef(0)
    unsaved: list[bool] = [False]  # the one use_state: whether the unlock was saved

    def use_state(initial: bool) -> tuple[bool, Callable[[bool], None]]:
        return unsaved[0], lambda value: unsaved.__setitem__(0, value)

    monkeypatch.setattr(ft, "use_ref", lambda initial=None: ref)
    monkeypatch.setattr(ft, "use_state", use_state)
    monkeypatch.setattr(about_app, "use_services", lambda: svc)
    monkeypatch.setattr(about_app, "use_prefs", lambda: prefs)
    monkeypatch.setattr(about_app, "AppScaffold", lambda **kwargs: kwargs)
    return lambda: cast(dict[str, Any], inspect.unwrap(AboutApp)())


def tiles(scaffold: dict[str, Any]) -> dict[str, ft.ListTile]:
    """The build's rows by title, the version row's ``ListTile`` included."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    found = {}
    for row in body.controls:
        if isinstance(row, ft.Semantics) and row.live_region:
            continue  # the Developer row, below
        if isinstance(row, ft.MergeSemantics):
            assert isinstance(row.content, ft.Semantics)
            row = row.content.content
        if isinstance(row, ft.ListTile):
            found[str(row.title)] = row
    return found


async def tap_version(render: Callable[[], dict[str, Any]], times: int) -> None:
    """Tap the Version row ``times`` times, rendering the page before each."""
    for _ in range(times):
        await cast(Any, tiles(render())["Version"].on_click)()


def test_the_page_says_which_build_this_is(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The page lists the app's version, Python's and Flet's, in that order."""
    scaffold = render()
    assert scaffold["title"] == "About this app"
    rows = tiles(scaffold)
    assert [(title, tile.subtitle) for title, tile in rows.items()] == [
        ("Version", pycon_us.__version__),
        ("Python", platform.python_version()),
        ("Flet", "source build"),  # while the source pin lasts (development.md §2.2)
    ]


def test_the_page_names_the_app_and_says_it_is_not_the_psf_s(
    render: Callable[[], dict[str, Any]],
) -> None:
    """A level-2 heading names the app, over lines saying it is not the PSF's."""
    body = render()["body"]
    assert isinstance(body, ft.ListView)
    header = body.controls[0]
    assert isinstance(header, ft.Container) and isinstance(header.content, ft.Column)
    name, lines = header.content.controls
    assert isinstance(name, ft.Semantics) and name.header
    assert name.heading_level == 2  # under the bar's "About this app" (D-211)
    # Nodes of their own, so the name is read alone, and before the lines under it.
    assert isinstance(lines, ft.Semantics) and name.container and lines.container
    assert isinstance(lines.content, ft.Column)
    about, not_official = lines.content.controls
    assert isinstance(name.content, ft.Text)
    assert name.content.value == pycon_us.APP_NAME
    assert isinstance(about, ft.Text) and isinstance(not_official, ft.Text)
    assert about.value == "A companion for PyCon US 2026, built with Python and Flet."
    assert not_official.value == "Not an official PSF app."  # D-36


def test_the_version_row_carries_its_identifier_for_ui_flows(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The Version row's merged node carries the ``about_app.version`` id."""
    body = render()["body"]
    assert isinstance(body, ft.ListView)
    [row] = [c for c in body.controls if isinstance(c, ft.MergeSemantics)]
    assert isinstance(row.content, ft.Semantics)
    assert row.content.identifier == "about_app.version"


def developer_row(scaffold: dict[str, Any]) -> ft.ListTile | None:
    """The row the unlock adds, or None."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    for row in body.controls:
        if isinstance(row, ft.Semantics) and row.live_region:
            link = row.content
            assert isinstance(link, ft.MergeSemantics)
            assert isinstance(link.content, ft.Semantics)
            assert link.content.identifier == "about_app.developer"
            tile = link.content.content
            assert isinstance(tile, ft.ListTile)
            return tile
    return None


async def test_six_taps_unlock_nothing(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage
) -> None:
    """Six taps on Version leave Developer locked and unlisted, with no dialog."""
    await tap_version(render, UNLOCK_TAPS - 1)
    assert not prefs.developer
    assert developer_row(render()) is None
    assert page.dialogs == []


async def test_the_seventh_tap_unlocks_developer_and_keeps_it_unlocked(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage, svc: Services
) -> None:
    """The seventh tap stores the unlock and adds a Developer row that opens it."""
    assert UNLOCK_TAPS == 7
    await tap_version(render, 7)
    assert prefs.developer
    stored = cast(MemoryPrefs, svc.storage.prefs).values["pycon.dev"]
    assert json.loads(stored) == {"unlocked": True}  # survives a relaunch (D-187)
    assert errors._details is True  # handler errors now say what failed
    # Said in place, where the taps were, not in a SnackBar (D-29, D-210).
    assert page.dialogs == []
    row = developer_row(render())
    assert row is not None
    assert (row.title, row.subtitle) == ("Developer options", "On")
    cast(Callable[[], None], row.on_click)()
    assert page.navigated == ["/more/developer"]


async def test_the_unlock_keeps_the_other_developer_options(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    """The unlock adds ``unlocked`` to the stored options and keeps the rest."""
    prefs.dev = {"feed_url": "http://127.0.0.1:8000/conference-2026.json"}
    await tap_version(render, 7)
    assert prefs.dev == {
        "feed_url": "http://127.0.0.1:8000/conference-2026.json",
        "unlocked": True,
    }


async def test_taps_once_it_is_on_change_nothing(
    render: Callable[[], dict[str, Any]], svc: Services
) -> None:
    """Taps after the unlock write nothing more to the prefs."""
    await tap_version(render, 7)
    writes = dict(cast(MemoryPrefs, svc.storage.prefs).values)
    await tap_version(render, 14)
    assert cast(MemoryPrefs, svc.storage.prefs).values == writes


async def test_when_not_embedded_developer_is_listed_without_taps(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In the companion app Developer is listed at once, and taps store nothing."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", True)  # the companion app
    assert developer_row(render()) is not None
    await tap_version(render, 7)
    assert prefs.dev == {}  # nothing to unlock or store
    assert errors._details is False  # the companion app shows details by itself


async def test_an_unlock_that_cannot_be_saved_holds_for_the_session_and_says_so(
    render: Callable[[], dict[str, Any]], prefs: Prefs, svc: Services
) -> None:
    """An unlock that can't be stored holds in memory, and its row says so."""
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await tap_version(render, 7)
    assert prefs.developer  # D-120: kept in memory
    row = developer_row(render())
    assert row is not None
    assert row.subtitle == "On until you close the app"
