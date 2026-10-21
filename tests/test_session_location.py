"""Tests for the room's ``LocationCard`` on session detail (DATA-33, D-349).

Under the When and where card, a session in one room with a pin shows that room's
card, which pushes the floor viewer at the pin; multi-room sessions keep their tiles.
"""

from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.core.models import ConferenceData
from pycon_us.ui import location_card
from tests.session_detail import BREAK, TALK, VIEW, Detail, Render, rendering
from tests.timers import HeldSleeps

ROOM_104C = "199"
"""A session in Room 104C, pinned on the Concourse level."""

LIGHTNING = "175"
"""Lightning talks: the Arena and four streamed rooms (D-124)."""

ELSEWHERE = "9173"
"""An open space "Elsewhere": a room the feed has, with no pin."""


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Provide an async function that renders a session's detail at ``VIEW`` by id."""
    async with rendering(tmp_path, monkeypatch) as show:
        yield show


def card_tap(detail: Detail) -> ft.Container:
    """The location card's tap target: the container around its one node."""
    tap = detail.node("session.location").parent
    assert isinstance(tap, ft.Container) and tap.on_click is not None
    return tap


async def test_a_pinned_room_s_card_opens_its_floor_plan_at_the_pin(
    render: Render,
) -> None:
    """Room 104C's card names the room and floor, and pushes the Concourse plan."""
    detail = await render(ROOM_104C)
    card = detail.node("session.location")
    assert card.label == "Show Room 104C on the Concourse level floor plan"
    assert card.button
    await detail.click(card_tap(detail))
    assert detail.pushed == [f"{VIEW}/plan/concourse?pin=104c"]


async def test_the_card_sits_under_when_and_where_and_keeps_the_room_tile(
    render: Render,
) -> None:
    """The card follows the When and where card; the room tile still pushes the room.

    Two destinations, two stops: what else is on there, and where it is (D-349).
    """
    detail = await render(TALK)
    room = detail.node("session.room")
    card = detail.node("session.location")
    column = next(
        c for c in ancestors(card) if isinstance(c, ft.Column) and c.spacing == 12
    )
    first, second = column.controls
    assert first in ancestors(room)
    assert second in ancestors(card)


def ancestors(control: ft.BaseControl) -> list[ft.BaseControl]:
    """The controls ``control`` is in, from its parent up to the page."""
    found: list[ft.BaseControl] = []
    parent = control.parent
    while parent is not None:
        found.append(parent)
        parent = parent.parent
    return found


@pytest.mark.parametrize("session_id", [LIGHTNING, BREAK])
async def test_a_multi_room_session_keeps_its_tiles_and_has_no_card(
    render: Render, session_id: str
) -> None:
    """Lightning talks and a break in five rooms: which room's card? None."""
    detail = await render(session_id)
    assert detail.nodes("session.other_rooms")
    assert detail.nodes("session.location") == []


async def test_a_room_without_a_pin_shows_no_card(render: Render) -> None:
    """"Elsewhere" has a room tile and no pin: no card, and no gap."""
    detail = await render(ELSEWHERE)
    assert detail.nodes("session.room")
    assert detail.nodes("session.location") == []


async def test_the_pin_pulses_once_when_the_page_opens(render: Render) -> None:
    """The card mounts once per session View: one pulse starts, then it waits."""
    detail = await render(TALK)
    await detail.settle()
    sleeps = cast(HeldSleeps, location_card.asyncio)
    assert sleeps.asked == [location_card.PULSE_MS / 1000]


async def test_a_dropped_session_keeps_its_card(render: Render) -> None:
    """A session a refresh drops keeps its content, the card too (D-186)."""
    detail = await render(TALK)
    data = cast(ConferenceData, detail.conference.data)
    newer = replace(
        data, sessions={k: v for k, v in data.sessions.items() if k != TALK}
    )
    detail.conference.data, detail.conference.version = newer, 2
    await detail.settle()
    assert detail.nodes("session.removed")
    assert detail.nodes("session.location")
