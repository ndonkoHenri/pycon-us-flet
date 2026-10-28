"""Tests for the Developer screen's Data section: rows, refresh, clear the cache, words (#107).

The fixtures and lookups are ``tests/data_section.py``'s. How the section looks is
checked on devices (the PR).
"""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.account import Account
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.screens.developer_data import (
    CLEARED,
    reset_app,
)
from pycon_us.screens.developer_ui import (
    NBSP,
    confirmation,
    snapshot_day,
)
from pycon_us.services import Services, api
from pycon_us.state import Conference
from pycon_us.ui.actions import KEPT, refreshed
from tests import data_section
from tests.data_section import (
    Rendered,
    identified,
    outcome,
    press,
    row,
    subtitle,
    tap,
)
from tests.fake_page import FakePage
from tests.feeds import recorded

(
    real_time,
    offline,
    page,
    svc,
    stored,
    prefs,
    conference,
    favorites,
    account,
    packaged,
    rendered,
    minutes,
    render,
) = (
    data_section.real_time,
    data_section.offline,
    data_section.page,
    data_section.svc,
    data_section.stored,
    data_section.prefs,
    data_section.conference,
    data_section.favorites,
    data_section.account,
    data_section.packaged,
    data_section.rendered,
    data_section.minutes,
    data_section.render,
)


# ------------------------------------------------------------------ the rows


def test_each_action_carries_the_identifier_ui_flows_use(
    render: Callable[[], ft.Column],
) -> None:
    """The section's identifiers are exactly its five rows' and the outcome line's."""
    assert set(identified(render())) == {
        "developer.refresh_now",
        "developer.clear_cache",
        "developer.share_log",
        "developer.show_welcome",
        "developer.reset_app",
        "developer.data_outcome",
    }


def test_each_action_is_one_node_with_its_identifier(
    render: Callable[[], ft.Column],
) -> None:
    """Each of the five rows is a MergeSemantics over its identified tile: one node.

    A bare Semantics(identifier) around a control is an empty extra node for TalkBack;
    merged, the row is one button node that carries it (D-190).
    """
    rows = [c for c in render().controls if isinstance(c, ft.MergeSemantics)]
    assert len(rows) == 5
    for merged in rows:
        inner = merged.content
        assert isinstance(inner, ft.Semantics) and inner.identifier
        assert isinstance(inner.content, ft.ListTile)


async def test_a_disabled_row_s_node_says_it_is_disabled(
    render: Callable[[], ft.Column],
) -> None:
    """A disabled row's identifier node is disabled too, and an enabled row's is not.

    Flet's Semantics says "enabled" from its own ``disabled``, and the merged node kept
    it: Android dumped Clear cached feed, disabled, as enabled="true" (F42, #239). The
    row's identifier node takes the tile's state (D-214).
    """
    nodes = [
        cast(ft.Semantics, merged.content)
        for merged in render().controls
        if isinstance(merged, ft.MergeSemantics)
    ]
    rows = {node.identifier: node for node in nodes}
    assert row(render(), "developer.clear_cache").disabled is True  # no cache yet
    assert rows["developer.clear_cache"].disabled is True
    assert rows["developer.reset_app"].disabled is False


def test_reset_app_reads_as_destructive(render: Callable[[], ft.Column]) -> None:
    """Reset app's icon and title are in the error colour, and the row is enabled."""
    tile = row(render(), "developer.reset_app")
    assert isinstance(tile.leading, ft.Icon) and tile.leading.color == ft.Colors.ERROR
    assert isinstance(tile.title, ft.Text) and tile.title.color == ft.Colors.ERROR
    assert tile.disabled is False


def test_refresh_now_says_what_the_schedule_on_screen_is(
    render: Callable[[], ft.Column],
) -> None:
    """Refresh now's subtitle names the bundled snapshot the fixture published."""
    assert subtitle(render(), "developer.refresh_now").startswith(
        "Bundled with the app, updated "
    )


def test_refresh_now_s_age_follows_the_clock_while_the_screen_is_open(
    render: Callable[[], ft.Column],
    conference: Conference,
    minutes: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-198: the minute tick re-renders the section, so "updated ..." stays current."""
    fetched_at = conference.fetched_at
    assert fetched_at is not None
    monkeypatch.setattr(clock, "now", lambda: fetched_at)
    assert subtitle(render(), "developer.refresh_now") == (
        "Bundled with the app, updated just now"
    )
    monkeypatch.setattr(clock, "now", lambda: fetched_at + timedelta(hours=3))
    assert subtitle(render(), "developer.refresh_now") == (
        "Bundled with the app, updated 3 hours ago"
    )
    assert len(minutes) == 2  # on the tick at every render (D-70: never conditional)


async def test_refresh_now_asks_for_a_refresh_and_says_how_it_ended(
    render: Callable[[], ft.Column],
    conference: Conference,
    monkeypatch: pytest.MonkeyPatch,
    page: FakePage,
) -> None:
    """Refresh now says in place, not in a SnackBar, how each refresh ended.

    Offline, the bundled schedule stays; with the feed answering, the schedule and the
    row's subtitle come from the feed.
    """
    await tap(render, "developer.refresh_now")
    assert outcome(render()) == (
        "Couldn't refresh: no answer from the feed. The app keeps the schedule it has."
    )
    assert conference.source == "bundled"  # kept

    async def serve(url: str, **_: Any) -> bytes:
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", serve)
    await tap(render, "developer.refresh_now")
    assert conference.source == "network"
    assert outcome(render()) == "Schedule updated from the feed."
    assert subtitle(render(), "developer.refresh_now") == (
        "From the feed, updated just now"
    )
    assert page.dialogs == []  # in place, not a SnackBar (D-29, D-210)


async def test_refresh_now_is_disabled_while_an_asked_for_refresh_runs(
    render: Callable[[], ft.Column],
    conference: Conference,
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh now is disabled, with a ring, only while a refresh it asked for runs.

    A quiet refresh leaves the row enabled; its own refresh says "Updating the
    schedule…" until it ends.
    """
    release = asyncio.Event()

    async def hold(url: str, **_: Any) -> bytes:
        await release.wait()
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", hold)
    conference.start_refresh(svc.storage, svc.year)  # quiet: the row stays enabled
    await asyncio.sleep(0)
    assert row(render(), "developer.refresh_now").disabled is False
    asked = asyncio.create_task(tap(render, "developer.refresh_now"))
    await asyncio.sleep(0)
    tile = row(render(), "developer.refresh_now")
    assert tile.disabled is True  # D-181: as every Refresh button
    assert subtitle(render(), "developer.refresh_now") == "Updating the schedule…"
    assert isinstance(tile.trailing, ft.ProgressRing)  # something moves (ux.md §4)
    release.set()
    await asked
    tile = row(render(), "developer.refresh_now")
    assert tile.disabled is False
    assert tile.trailing is None


async def test_a_reset_during_an_asked_for_refresh_ends_the_tap_without_an_outcome(
    render: Callable[[], ft.Column],
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reset during an asked-for refresh cancels the tap, which shows no outcome."""
    release = asyncio.Event()

    async def hold(url: str, **_: Any) -> bytes:
        await release.wait()
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", hold)
    asked = asyncio.create_task(tap(render, "developer.refresh_now"))
    await asyncio.sleep(0)
    async with asyncio.timeout(5):
        await reset_app(svc, conference, prefs, favorites, Account())
    # The tap awaited the refresh that the reset cancelled: it ends cancelled too
    # (Conference.reset()), not with a claim that the schedule was updated.
    await asyncio.wait({asked})
    assert asked.cancelled()
    assert outcome(render()) is None
    release.set()


# ------------------------------------------------------------------ Clear cached feed


async def test_clear_cached_feed_is_disabled_without_a_cache(
    render: Callable[[], ft.Column],
) -> None:
    """Without a cache, Clear cached feed is disabled and says why, readably."""
    tile = row(render(), "developer.clear_cache")
    assert tile.disabled is True
    assert subtitle(render(), "developer.clear_cache") == (
        "No cached schedule on this device"
    )
    # Why it is off stays readable: not at the disabled 38 % (ux.md principle 8).
    assert cast(ft.Text, tile.subtitle).color == ft.Colors.ON_SURFACE_VARIANT


async def test_clear_cached_feed_asks_first_and_cancel_keeps_the_cache(
    render: Callable[[], ft.Column], rendered: Rendered, svc: Services
) -> None:
    """Clear cached feed asks in a modal dialog first, and Cancel keeps the cache."""
    await svc.storage.write_feed(recorded(2026))
    assert subtitle(render(), "developer.clear_cache") == (
        "The next start shows the bundled schedule"
    )
    await tap(render, "developer.clear_cache")
    render()
    dialog = rendered.dialog
    assert dialog is not None and dialog.modal is True
    assert dialog.title == ft.Text("Clear the cached schedule?")
    assert svc.storage.feed_path.exists()  # nothing deleted before the answer
    await press(dialog, "developer.clear_cache.cancel")
    render()
    assert rendered.dialog is None
    assert svc.storage.feed_path.exists()
    assert dialog.on_dismiss is not None  # Back cancels too


async def test_clear_cached_feed_deletes_the_cache_and_keeps_the_session_s_data(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    svc: Services,
    conference: Conference,
) -> None:
    """Confirming the clear deletes the cache file but not the session's data.

    The outcome line says it was cleared, and the row is disabled again.
    """
    await svc.storage.write_feed(recorded(2026))
    version = conference.version
    await tap(render, "developer.clear_cache")
    render()
    await press(rendered.dialog, "developer.clear_cache.confirm")
    column = render()
    assert rendered.dialog is None
    assert not svc.storage.feed_path.exists()  # the next start: the snapshot (D-39)
    assert conference.version == version  # this session keeps what it shows
    assert outcome(column) == CLEARED[0]
    assert row(column, "developer.clear_cache").disabled is True


def test_the_clear_confirmation_names_the_bundled_schedule_s_day() -> None:
    """The clear confirmation names the day of the schedule bundled with the app.

    It also says the schedule on screen stays until the app is closed.
    """
    dialog = confirmation(
        "clear",
        saved=0,
        packaged=True,
        snapshot_day="Mon, Oct 12",
        on_confirm=lambda: None,
        on_cancel=lambda: None,
    )
    assert dialog is not None
    text = cast(ft.Text, cast(ft.Column, dialog.content).controls[0]).value
    assert "the schedule bundled with the app (Mon, Oct 12)" in str(text)
    assert "You keep seeing it until you close the app" in str(text)


def test_the_bundled_schedule_s_day_never_wraps_in_its_middle(svc: Services) -> None:
    """The bundled schedule's day joins its three words with no-break spaces."""
    day = snapshot_day(svc.year.conference)
    assert day and " " not in day  # "(Sun, Oct" / "11)" on a phone before
    assert day.replace(NBSP, " ").count(" ") == 2  # e.g. "Sun, Oct 11"


# ------------------------------------------------------------------ the words


def test_refresh_now_says_how_the_refresh_ended() -> None:
    """A refresh's outcome says the schedule was updated, or why it was kept."""
    assert refreshed(None) == ("Schedule updated from the feed.", True)
    assert refreshed("offline")[1] is False
    assert refreshed("server") == (
        f"Couldn't refresh: the feed's answer couldn't be used. {KEPT}",
        False,
    )
