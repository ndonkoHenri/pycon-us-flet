"""Tests for My schedule's Export to calendar (.ics) (#426; SESS-05; ux.md §5.6, D-289).

When the overflow is offered, what the file holds and how a tap goes, in ``MySchedule``
as ``tests/harness.py``'s ``showing()`` renders it, on Android, whose save dialog is a
fake that records the file and can be held open. ``services.calendar``'s own routes,
iOS's loopback included, are ``tests/test_calendar.py``'s.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.screens import my_schedule as screen
from pycon_us.screens.my_schedule import MySchedule
from pycon_us.screens.my_schedule_extras import EXPORT, export_slug
from pycon_us.services.calendar import NOT_OPENED, saved_text
from pycon_us.state import Conference
from pycon_us.ui import states
from tests.fakes import MemoryFilePicker
from tests.feeds import processed
from tests.harness import Shown, showing
from tests.sessions import menu_text

YEAR = load_year(2026)
ZONE = YEAR.conference.zone

THURSDAY = datetime(2026, 5, 14, 10, 45, tzinfo=ZONE)
"""During the conference: Wednesday's sessions have ended, Saturday's are to come."""

MCP, KEYNOTE, TALK = "2", "153", "142"
"""Wednesday's 9:00 tutorial (ended by Thursday), Friday's keynote, Saturday's talk."""

FILE = "pycon-us-2026-my-schedule.ics"
"""The export's name: the year's, whatever is saved."""

Show = Callable[..., Awaitable[Shown]]
"""Shows My schedule with the given saved ids; ``loaded=False`` leaves them unread."""


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that shows My schedule on Android on Thursday morning.

    The status strip and the skeleton are placeholders, which have their own tests.
    """
    clock.set_test_now(THURSDAY)
    monkeypatch.setattr(screen, "StatusStrip", lambda **_: ft.Text("strip"))
    monkeypatch.setattr(states, "SkeletonList", lambda: ft.Text("skeleton"))
    async with AsyncExitStack() as stack:

        async def on_android(
            *saved: str, loaded: bool = True, data: bool = True
        ) -> Shown:
            """Show the screen with ``saved`` stored, and with or without the feed."""
            conference = (
                Conference(data=processed(2026), source="bundled", version=1)
                if data
                else Conference(problem="offline")
            )
            shown = await stack.enter_async_context(
                showing(
                    MySchedule,
                    screen,
                    year=YEAR,
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="",  # no Router
                    prefs=Prefs(loaded=True),
                    favorites=None if loaded else Favorites(),  # not read yet
                    saved=saved,
                )
            )
            shown.session.page.platform = ft.PagePlatform.ANDROID
            return shown

        yield on_android
    clock.set_test_now(None)


def export_item(shown: Shown) -> ft.PopupMenuItem:
    """The overflow's one item: Export to calendar."""
    menu = cast(ft.PopupMenuButton, shown.node("my_schedule.overflow").content)
    (item,) = menu.items
    assert cast(ft.Semantics, item.content).identifier == "my_schedule.export"
    return item


def picker(shown: Shown) -> MemoryFilePicker:
    """The screen's file picker, which records each save."""
    return cast(MemoryFilePicker, shown.services.file_picker)


def said(shown: Shown) -> list[str]:
    """The texts of the SnackBars the screen showed, in order."""
    return [str(cast(ft.Text, s.content).value) for s in shown.snack_bars]


def exported(shown: Shown) -> str:
    """The text of the one file the screen saved, after checking its name."""
    ((name, data),) = picker(shown).saved
    assert name == FILE
    return cast(bytes, data).decode()


def uids(text: str) -> list[str]:
    """The session ids of a calendar file's events, in the file's order."""
    return re.findall(r"^UID:2026-(.+)@", text, re.MULTILINE)


# ------------------------------------------------------------------ where it is offered


def test_the_file_is_named_after_the_year() -> None:
    """ux.md §5.6: ``pycon-us-<year>-my-schedule.ics``, a name a person recognises."""
    assert f"{export_slug(2026)}.ics" == FILE


async def test_with_something_saved_the_overflow_offers_the_export(show: Show) -> None:
    """The app bar's overflow holds Export to calendar (.ics), which stays in the app."""
    shown = await show(MCP, TALK)
    item = export_item(shown)
    assert menu_text(item).value == EXPORT == "Export to calendar (.ics)"
    assert menu_text(item).semantics_label is None  # not a link: no "Opens in browser"
    assert not item.disabled


async def test_with_nothing_saved_there_is_no_overflow(show: Show) -> None:
    """Nothing to export: the empty state has no overflow (ux.md §5.6)."""
    shown = await show()
    shown.node("my_schedule.empty")
    assert shown.nodes("my_schedule.overflow") == []


async def test_saved_ids_the_feed_dropped_give_no_overflow(show: Show) -> None:
    """D-172: ids the feed no longer lists are not in the schedule, so not exported."""
    shown = await show("no-such-session")
    shown.node("my_schedule.dropped")
    assert shown.nodes("my_schedule.overflow") == []


async def test_an_unread_saved_list_gives_no_overflow(show: Show) -> None:
    """D-172: when the saved list could not be read, there is nothing to export."""
    shown = await show(MCP, loaded=False)
    shown.node("my_schedule.unavailable")
    assert shown.nodes("my_schedule.overflow") == []


async def test_without_the_feed_there_is_no_overflow(show: Show) -> None:
    """With no schedule to look the saved ids up in, there is nothing to export."""
    shown = await show(MCP, data=False)
    shown.node("my_schedule.no_data")
    assert shown.nodes("my_schedule.overflow") == []


# ------------------------------------------------------------------ a tap


async def test_the_export_holds_exactly_the_saved_sessions_still_in_the_schedule(
    show: Show,
) -> None:
    """Every saved session the feed lists, ended ones too, in start order, each alarmed.

    A dropped id is left out; Wednesday's tutorial, over by Thursday, is not (#426).
    """
    shown = await show(TALK, "no-such-session", KEYNOTE, MCP)
    await shown.click(export_item(shown))
    text = exported(shown)
    assert uids(text) == [MCP, KEYNOTE, TALK]
    assert text.count("BEGIN:VALARM") == 3
    assert "DTSTART:20260513T160000Z" in text  # Wednesday, 9:00 AM PDT
    assert said(shown) == [saved_text(FILE)]


async def test_a_session_removed_from_my_schedule_leaves_the_export(
    show: Show,
) -> None:
    """The export follows the stars: after a removal it holds the sessions still saved."""
    shown = await show(MCP, KEYNOTE, TALK)
    star = shown.node(f"my_schedule.favorite.{KEYNOTE}").content
    assert isinstance(star, ft.IconButton)
    await shown.click(star)
    await shown.click(export_item(shown))
    assert uids(exported(shown)) == [MCP, TALK]


async def test_when_everything_has_ended_the_overflow_still_exports_it(
    show: Show,
) -> None:
    """D-289: with every saved session over, the overflow still exports them."""
    shown = await show(MCP)
    shown.node("my_schedule.all_over")
    await shown.click(export_item(shown))
    assert uids(exported(shown)) == [MCP]


async def test_the_export_is_disabled_while_the_dialog_is_up(show: Show) -> None:
    """A second tap cannot save the file twice; the item comes back afterwards."""
    shown = await show(MCP, TALK)
    gate = picker(shown).gate = asyncio.Event()
    task = asyncio.create_task(shown.click(export_item(shown)))
    await shown.settle()
    assert export_item(shown).disabled
    gate.set()
    await task
    await shown.settle()
    assert not export_item(shown).disabled


async def test_a_cancelled_save_says_nothing(show: Show) -> None:
    """D-272: a cancel in the save dialog is the user's choice, and needs no answer."""
    shown = await show(MCP, TALK)
    picker(shown).answer = None
    await shown.click(export_item(shown))
    assert said(shown) == []
    assert not export_item(shown).disabled


async def test_a_failed_save_says_so_on_my_schedule(show: Show) -> None:
    """D-210: the failure is said on the screen, and the item can be tried again."""
    shown = await show(MCP, TALK)
    picker(shown).error = RuntimeError("save_file failed")
    await shown.click(export_item(shown))
    assert said(shown) == [NOT_OPENED]
    assert not export_item(shown).disabled
