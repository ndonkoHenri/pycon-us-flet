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
from pycon_us.prefs import Prefs
from pycon_us.screens import about_app
from pycon_us.screens.about_app import UNLOCK_TAPS, AboutApp
from pycon_us.services import Services, errors
from pycon_us.services.storage import Storage
from pycon_us.state import ViewMemory
from tests.fakes import FakePage, MemoryPrefs, MemorySemantics, bound


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
    )


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    monkeypatch.setattr(errors, "_details", False)
    return Prefs()


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, svc: Services, prefs: Prefs, page: FakePage
) -> Callable[[], dict[str, Any]]:
    """Render ``AboutApp`` and return what it passed to ``AppScaffold``.

    The tap count is one ref that lives as long as the page, as ``use_ref``'s does.
    """
    ref = MutableRef(0)
    monkeypatch.setattr(ft, "use_ref", lambda initial=None: ref)
    monkeypatch.setattr(about_app, "use_services", lambda: svc)
    monkeypatch.setattr(about_app, "use_prefs", lambda: prefs)
    monkeypatch.setattr(about_app, "AppScaffold", lambda **kwargs: kwargs)
    return lambda: cast(dict[str, Any], inspect.unwrap(AboutApp)())


def tiles(scaffold: dict[str, Any]) -> dict[str, ft.ListTile]:
    """The page's rows by title, the version row's ``ListTile`` included."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    found = {}
    for row in body.controls:
        if isinstance(row, ft.MergeSemantics):
            assert isinstance(row.content, ft.Semantics)
            row = row.content.content
        if isinstance(row, ft.ListTile):
            found[str(row.title)] = row
    return found


async def tap_version(render: Callable[[], dict[str, Any]], times: int) -> None:
    for _ in range(times):
        await cast(Any, tiles(render())["Version"].on_click)()


def snack(page: FakePage) -> ft.SnackBar:
    (dialog,) = page.dialogs
    assert isinstance(dialog, ft.SnackBar)
    assert dialog.behavior == ft.SnackBarBehavior.FLOATING
    assert dialog.persist is False  # it goes by itself, Open or not
    return dialog


def test_the_page_says_which_build_this_is(
    render: Callable[[], dict[str, Any]],
) -> None:
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
    body = render()["body"]
    assert isinstance(body, ft.ListView)
    header = body.controls[0]
    assert isinstance(header, ft.Container) and isinstance(header.content, ft.Column)
    name, about, not_official = header.content.controls
    assert isinstance(name, ft.Semantics) and name.header  # the page's heading
    assert isinstance(name.content, ft.Text)
    assert name.content.value == pycon_us.APP_NAME
    assert isinstance(about, ft.Text) and isinstance(not_official, ft.Text)
    assert about.value == "A companion for PyCon US 2026, built with Python and Flet."
    assert not_official.value == "Not an official PSF app."  # D-36


def test_the_version_row_carries_its_identifier_for_ui_flows(
    render: Callable[[], dict[str, Any]],
) -> None:
    body = render()["body"]
    assert isinstance(body, ft.ListView)
    [row] = [c for c in body.controls if isinstance(c, ft.MergeSemantics)]
    assert isinstance(row.content, ft.Semantics)
    assert row.content.identifier == "about_app.version"


async def test_six_taps_unlock_nothing(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage
) -> None:
    await tap_version(render, UNLOCK_TAPS - 1)
    assert not prefs.developer
    assert page.dialogs == []


async def test_the_seventh_tap_unlocks_developer_and_keeps_it_unlocked(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage, svc: Services
) -> None:
    assert UNLOCK_TAPS == 7
    await tap_version(render, 7)
    assert prefs.developer
    stored = cast(MemoryPrefs, svc.storage.prefs).values["pycon.dev"]
    assert json.loads(stored) == {"unlocked": True}  # survives a relaunch (D-184)
    assert errors._details is True  # handler errors now say what failed
    bar = snack(page)
    assert isinstance(bar.content, ft.Text)
    assert bar.content.value == "Developer options unlocked"
    assert bar.action == "Open"
    cast(Callable[[], None], bar.on_action)()  # Flet calls it without the event
    assert page.navigated == ["/more/developer"]


async def test_the_unlock_keeps_the_other_developer_options(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    prefs.dev = {"feed_url": "http://127.0.0.1:8000/conference-2026.json"}
    await tap_version(render, 7)
    assert prefs.dev == {
        "feed_url": "http://127.0.0.1:8000/conference-2026.json",
        "unlocked": True,
    }


async def test_seven_more_taps_say_it_is_already_on_and_count_again(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage
) -> None:
    await tap_version(render, 7)
    page.dialogs.clear()
    await tap_version(render, 6)
    assert page.dialogs == []  # the count starts again after an unlock
    await tap_version(render, 1)
    bar = snack(page)
    assert isinstance(bar.content, ft.Text)
    assert bar.content.value == "Developer options are already on"


async def test_when_not_embedded_the_taps_only_say_it_is_on(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    page: FakePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", True)  # the companion app
    await tap_version(render, 7)
    assert prefs.dev == {}  # nothing to unlock or store
    bar = snack(page)
    assert isinstance(bar.content, ft.Text)
    assert bar.content.value == "Developer options are already on"


async def test_an_unlock_that_cannot_be_saved_holds_for_the_session_and_says_so(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage, svc: Services
) -> None:
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await tap_version(render, 7)
    assert prefs.developer  # D-120: kept in memory
    bar = snack(page)
    assert isinstance(bar.content, ft.Text)
    assert bar.content.value == "Developer options unlocked until you close the app"
