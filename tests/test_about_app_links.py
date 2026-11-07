"""Tests for About this app's links and its Conference data section (#88; D-73, D-292).

The page runs in `tests/about_page.py`'s stand-ins.
"""

import inspect
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

import flet as ft
import pytest

import pycon_us
from pycon_us import clock
from pycon_us.screens import about_app
from pycon_us.screens.about_app import ConferenceData, shown_url
from pycon_us.services import Services, feed_api
from pycon_us.state import Conference
from tests import about_page
from tests.about_page import headings, link_rows
from tests.fakes import MemoryLauncher
from tests.feeds import recorded

real_time, offline, page, svc, prefs, render, conference = (
    about_page.real_time,
    about_page.offline,
    about_page.page,
    about_page.svc,
    about_page.prefs,
    about_page.render,
    about_page.conference,
)


# ------------------------------------------------------------------ Links


async def test_flet_opens_in_the_in_app_browser_and_reads_as_a_link(
    render: Callable[[], dict[str, Any]], svc: Services
) -> None:
    """The Flet row is a link to flet.dev that opens, and says so, in the browser."""
    node = link_rows(render())["about_app.flet"]
    assert node.link  # a link, not a button (INFO-14)
    tile = node.content
    assert isinstance(tile, ft.ListTile)
    assert (tile.title, tile.subtitle) == ("Flet website", "flet.dev")
    assert isinstance(tile.trailing, ft.Icon)
    assert tile.trailing.semantics_label == "Opens in browser"  # D-182
    await cast(Callable[[], Any], tile.on_click)()
    launcher = cast(MemoryLauncher, svc.launcher)
    assert launcher.launched == [
        ("https://flet.dev", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


def test_the_source_url_is_the_public_repository() -> None:
    """`SOURCE_URL` names the repository, so About this app and View source reach it (D-292, D-501)."""
    assert pycon_us.SOURCE_URL == "https://github.com/ndonkoHenri/pycon-us-flet"


def test_no_source_code_row_while_the_repository_is_private(
    render: Callable[[], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With `SOURCE_URL` None, Links lists Flet alone: no row links to a private repository."""
    monkeypatch.setattr(about_app, "SOURCE_URL", None)
    assert list(link_rows(render())) == ["about_app.flet"]


async def test_a_source_url_adds_a_source_code_row_after_flet(
    render: Callable[[], dict[str, Any]],
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once `SOURCE_URL` is set, a Source code row opens it in the in-app browser."""
    url = "https://example.org/conf-companion"
    monkeypatch.setattr(about_app, "SOURCE_URL", url)
    found = link_rows(render())
    assert list(found) == ["about_app.flet", "about_app.source"]
    tile = found["about_app.source"].content
    assert isinstance(tile, ft.ListTile)
    assert (tile.title, tile.subtitle) == ("Source code", "example.org/conf-companion")
    await cast(Callable[[], Any], tile.on_click)()
    launcher = cast(MemoryLauncher, svc.launcher)
    assert launcher.launched == [(url, ft.LaunchMode.IN_APP_BROWSER_VIEW)]


def test_a_url_is_shown_without_its_scheme_or_a_trailing_slash() -> None:
    """A row's address drops `https://` and a final slash, and keeps the path."""
    assert shown_url("https://flet.dev") == "flet.dev"
    assert shown_url("https://flet.dev/") == "flet.dev"
    assert shown_url("https://example.org/a/b/") == "example.org/a/b"


# ------------------------------------------------------------------ Conference data


@pytest.fixture
def section(
    monkeypatch: pytest.MonkeyPatch, svc: Services, conference: Conference
) -> Callable[[], list[ft.Control]]:
    """Render `ConferenceData` over `svc` and `conference`: its controls."""
    monkeypatch.setattr(about_app, "use_services", lambda: svc)
    monkeypatch.setattr(about_app, "use_conference", lambda: conference)
    monkeypatch.setattr(about_app, "use_minute", lambda: 0)

    def render() -> list[ft.Control]:
        column = inspect.unwrap(ConferenceData)()
        assert isinstance(column, ft.Column)
        return column.controls

    return render


def data_rows(controls: list[ft.Control]) -> dict[str, str]:
    """The section's rows: each title and its second line."""
    found = {}
    for item in controls:
        row = item
        if isinstance(row, ft.MergeSemantics):
            assert isinstance(row.content, ft.Semantics)
            assert row.content.identifier == "about_app.schedule"
            row = row.content.content
        if isinstance(row, ft.ListTile):
            found[str(row.title)] = str(row.subtitle)
    return found


def test_the_section_is_a_level_2_heading_over_the_conference_and_schedule(
    section: Callable[[], list[ft.Control]],
) -> None:
    """Conference data heads the year's conference and the schedule's line, in order."""
    controls = section()
    assert headings(controls) == [("Conference data", 2)]
    assert list(data_rows(controls)) == ["Conference", "Schedule"]
    assert data_rows(controls)["Conference"] == "PyCon US 2026"  # year data (D-35)


def test_a_first_start_offline_says_the_schedule_is_bundled(
    section: Callable[[], list[ft.Control]], svc: Services, conference: Conference
) -> None:
    """Offline on a first start, the line says the schedule is the one bundled."""
    captured = svc.year.conference.snapshot_captured_at
    assert captured is not None
    assert conference.source == "bundled"
    clock.start_fake_clock(captured + timedelta(days=3, minutes=1))
    assert data_rows(section())["Schedule"] == (
        "Bundled with the app, updated 3 days ago"
    )


async def test_after_a_refresh_the_line_says_from_the_feed_and_its_age_moves(
    section: Callable[[], list[ft.Control]],
    svc: Services,
    conference: Conference,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a refresh it says "From the feed"; the fake clock then moves its age."""

    async def serve(url: str, **_: Any) -> bytes:
        return recorded(2026)

    monkeypatch.setattr(feed_api, "fetch_feed", serve)
    await conference.refresh(svc.storage, svc.year)
    assert data_rows(section())["Schedule"] == "From the feed, updated just now"
    fetched = conference.fetched_at
    assert fetched is not None
    clock.start_fake_clock(fetched + timedelta(minutes=5, seconds=30))
    assert data_rows(section())["Schedule"] == "From the feed, updated 5 minutes ago"
    clock.start_fake_clock(fetched + timedelta(hours=2, seconds=30))
    assert data_rows(section())["Schedule"] == "From the feed, updated 2 hours ago"


def test_the_section_ticks_with_the_minute_and_reads_the_store(
    section: Callable[[], list[ft.Control]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A render calls `use_minute()` and `use_conference()`: the line keeps up."""
    calls: list[str] = []
    monkeypatch.setattr(about_app, "use_minute", lambda: calls.append("minute") or 0)
    use_conference = about_app.use_conference
    monkeypatch.setattr(
        about_app,
        "use_conference",
        lambda: calls.append("conference") or use_conference(),
    )
    section()
    assert sorted(calls) == ["conference", "minute"]
