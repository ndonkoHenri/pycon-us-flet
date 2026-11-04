"""Tests for session detail's Add to calendar (SESS-04, SESS-05; ux.md §5.5, D-272).

Which sessions offer it, where it sits in the overflow, and what a tap hands to
`services.calendar` (whose own routes `tests/test_calendar.py` covers), in
`SessionDetail` as `tests/session_detail.py` renders it. Android's route is
used here, the save dialog being a fake that can be held open.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.core.models import ConferenceData
from pycon_us.screens.session_extras import ADD_TO_CALENDAR
from pycon_us.services.calendar import NOT_OPENED, saved_text
from tests.fakes import MemoryFilePicker
from tests.session_detail import BREAK, TALK, Detail, Render, at, rendering
from tests.sessions import menu_text

KEYNOTE = "176"
"""A keynote: saved like a talk, but with no public page."""

OPEN_SPACE = "9119"
"""5K Fun Run: an open space, whose public page is linked in the page itself."""

TALK_FILE = "python-for-humans-designing-python-code.ics"
"""The talk's file: its title's first words (`ics.file_slug()`)."""


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Return a function that renders a session's detail on Android, given its id."""
    async with rendering(tmp_path, monkeypatch) as show:

        async def on_android(session_id: str) -> Detail:
            detail = await show(session_id)
            detail.session.page.platform = ft.PagePlatform.ANDROID
            return detail

        yield on_android


def items(detail: Detail) -> list[str | None]:
    """The overflow's items, by identifier, in order."""
    menu = cast(ft.PopupMenuButton, detail.node("session.overflow").content)
    return [cast(ft.Semantics, item.content).identifier for item in menu.items]


def calendar_item(detail: Detail) -> ft.PopupMenuItem:
    """The overflow's Add to calendar item."""
    menu = cast(ft.PopupMenuButton, detail.node("session.overflow").content)
    (item,) = [
        i
        for i in menu.items
        if cast(ft.Semantics, i.content).identifier == "session.add_to_calendar"
    ]
    return item


def picker(detail: Detail) -> MemoryFilePicker:
    """The detail's file picker, which records each save."""
    return cast(MemoryFilePicker, detail.services.file_picker)


def said(detail: Detail) -> list[str]:
    """The texts of the SnackBars the detail showed, in order."""
    return [str(cast(ft.Text, s.content).value) for s in detail.snack_bars]


# ------------------------------------------------------------------ where it is offered


async def test_add_to_calendar_follows_open_on_the_site(render: Render) -> None:
    """ux.md §5.5: the public page first, then Add to calendar, which stays in the app."""
    detail = await render(TALK)
    assert items(detail) == ["session.open_site", "session.add_to_calendar"]
    item = calendar_item(detail)
    assert menu_text(item).value == ADD_TO_CALENDAR == "Add to calendar"
    assert menu_text(item).semantics_label is None  # no "Opens in browser"
    assert not item.disabled


async def test_a_session_without_a_public_page_has_add_to_calendar_alone(
    render: Render,
) -> None:
    """Every session that can be saved now has an overflow, a keynote's one item."""
    detail = await render(KEYNOTE)
    assert items(detail) == ["session.add_to_calendar"]


async def test_an_open_space_offers_add_to_calendar_without_its_site(
    render: Render,
) -> None:
    """SESS-11, D-206: the site is linked in the page; the overflow adds to calendar."""
    detail = await render(OPEN_SPACE)
    assert items(detail) == ["session.add_to_calendar"]


async def test_a_break_has_no_overflow(render: Render) -> None:
    """D-31: a break is not saved, so it has no calendar item, and no page either."""
    detail = await render(BREAK)
    assert detail.nodes("session.overflow") == []


async def test_an_unknown_session_has_no_overflow(render: Render) -> None:
    """D-186: the not-found state has nothing to add."""
    detail = await render("no-such-session")
    assert detail.nodes("session.overflow") == []


async def test_a_removed_session_keeps_its_page_but_not_add_to_calendar(
    render: Render,
) -> None:
    """D-186: a session a newer feed dropped is not added to a calendar."""
    detail = await render(TALK)
    data = cast(ConferenceData, detail.conference.data)
    newer = replace(
        data, sessions={k: v for k, v in data.sessions.items() if k != TALK}
    )
    detail.conference.data, detail.conference.version = newer, 2
    await detail.settle()
    assert detail.nodes("session.removed")
    assert items(detail) == ["session.open_site"]


# ------------------------------------------------------------------ a tap


async def test_a_tap_hands_the_session_s_calendar_file_to_the_calendar(
    render: Render,
) -> None:
    """The tap saves the talk's one event, with its alarm, under its title's name."""
    clock.set_test_now(at("2026-05-16 09:00"))
    detail = await render(TALK)
    await detail.click(calendar_item(detail))
    ((name, data),) = picker(detail).saved
    assert name == TALK_FILE
    text = cast(bytes, data).decode()
    assert text.count("BEGIN:VEVENT") == 1
    assert "UID:2026-142@" in text
    assert "DTSTART:20260516T173000Z" in text  # 10:30 AM PDT
    assert "TRIGGER:-PT10M" in text
    assert said(detail) == [saved_text(TALK_FILE)]


async def test_add_to_calendar_is_disabled_while_the_dialog_is_up(
    render: Render,
) -> None:
    """A second tap cannot save the file twice; the item comes back afterwards."""
    detail = await render(TALK)
    gate = picker(detail).gate = asyncio.Event()
    task = asyncio.create_task(detail.click(calendar_item(detail)))
    await detail.settle()
    assert calendar_item(detail).disabled
    gate.set()
    await task
    await detail.settle()
    assert not calendar_item(detail).disabled


async def test_a_failed_save_says_so_on_the_detail(render: Render) -> None:
    """D-210: the failure is said on session detail, and the item can be tried again."""
    detail = await render(TALK)
    picker(detail).error = RuntimeError("save_file failed")
    await detail.click(calendar_item(detail))
    assert said(detail) == [NOT_OPENED]
    assert not calendar_item(detail).disabled
