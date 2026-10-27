"""Tests for About this app: its build, its sections and the 7-tap unlock.

#88 (D-73, D-187). The page runs in ``tests/about_page.py``'s stand-ins. The links and
the Conference data section are ``test_about_app_links.py``'s, Help us fix it
``test_about_app_help.py``'s. How the page looks and reads is checked on devices (the
PRs).
"""

import json
import platform
from collections.abc import Callable
from typing import Any, cast

import flet as ft
import pytest

import pycon_us
from pycon_us import prefs as prefs_module
from pycon_us.prefs import Prefs
from pycon_us.screens.about_app import UNLOCK_TAPS
from pycon_us.services import Services, errors
from tests import about_page
from tests.about_page import (
    CONFERENCE_DATA,
    HELP_US_FIX_IT,
    body_of,
    headings,
    tap_version,
    tiles,
)
from tests.fake_page import FakePage
from tests.fakes import MemoryPrefs

real_time, offline, page, svc, prefs, render = (
    about_page.real_time,
    about_page.offline,
    about_page.page,
    about_page.svc,
    about_page.prefs,
    about_page.render,
)


def test_the_page_says_which_build_this_is(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The page lists the app's version, Python's and Flet's, then its licences."""
    scaffold = render()
    assert scaffold["title"] == "About this app"
    rows = tiles(scaffold)
    assert [(title, tile.subtitle) for title, tile in rows.items()] == [
        ("Version", pycon_us.__version__),
        ("Python", platform.python_version()),
        ("Flet", "source build"),  # while the source pin lasts (development.md §2.2)
        ("Licences", None),
    ]


def test_the_page_s_sections_are_its_data_its_build_its_links_and_help(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The opening, Conference data, This build, Links, then Help us fix it.

    The page's own headings are level 2; Help us fix it's is its section's (below).
    """
    controls = body_of(render())
    assert controls[1] is CONFERENCE_DATA  # right under the opening (D-292)
    assert headings(controls) == [("This build", 2), ("Links", 2)]
    assert controls[-1] is HELP_US_FIX_IT  # after Links (D-297)


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
    rows = [c for c in body_of(render()) if isinstance(c, ft.MergeSemantics)]
    identifiers = [cast(ft.Semantics, row.content).identifier for row in rows]
    assert identifiers == ["about_app.version", "about_app.licences", "about_app.flet"]


def test_licences_opens_its_page_under_about_this_app(
    render: Callable[[], dict[str, Any]], page: FakePage
) -> None:
    """The Licences row opens ``/more/app/licences``, so Back returns here (D-296)."""
    tile = tiles(render())["Licences"]
    cast(Callable[[], None], tile.on_click)()
    assert page.navigated == ["/more/app/licences"]


async def test_licences_comes_after_the_developer_row(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Unlocked, Developer options stays right under the build's rows, where the taps were."""
    await tap_version(render, 7)
    controls = body_of(render())
    kinds = [
        "developer" if isinstance(c, ft.Semantics) and c.live_region else c
        for c in controls
    ]
    developer = kinds.index("developer")
    licences = controls[developer + 1]
    assert isinstance(licences, ft.MergeSemantics)
    assert cast(ft.Semantics, licences.content).identifier == "about_app.licences"


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
