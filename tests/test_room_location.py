"""Tests for room detail's unknown room, sprint-only room and location card (ROOM-04).

The page runs in ``tests/room_view.py``'s harness.
"""

from typing import cast

import flet as ft

from pycon_us.ui import location_card
from tests import room_view
from tests.room_view import SATURDAY_MORNING, VIEW, Render, Room, ancestors
from tests.timers import HeldSleeps
from tests.trees import texts

render = room_view.render


# ------------------------------------------------------------------ not found


async def test_an_unknown_room_names_the_thing_and_offers_the_rooms(
    render: Render,
) -> None:
    """An unknown room shows Not found, and its All rooms button opens the Map."""
    room = await render("/map/room/bogus", slug="bogus")
    assert room.titles[-1] == "Not found"
    state = room.node("room.not_found")
    assert "This room isn't in the current schedule" in texts(state)
    (button,) = [
        c for c in room.session.index.values() if isinstance(c, ft.FilledTonalButton)
    ]
    assert button.content == "All rooms"
    await room.session.dispatch_event(button._i, "click", None)
    await room.settle()
    assert room.went == ["/map"]


# ------------------------------------------------------------------ sprint-only (MAP-08)


async def test_a_sprint_only_room_says_the_sprints_run_there_and_leads_to_them(
    render: Render,
) -> None:
    """A sprint-only room shows its state, not Not found, and opens the Sprints page.

    It has no sessions, so no day tabs; its title is the room's name (ux.md §4.6).
    """
    room = await render("/map/room/s-2", slug="s-2")
    assert room.titles[-1] == "S-2"
    state = room.node("room.sprints")
    assert "Sprints run here after the talks" in texts(state)
    assert room.nodes("room.not_found") == []
    assert room.find(ft.TabBar) == []
    (button,) = [
        c for c in room.session.index.values() if isinstance(c, ft.FilledTonalButton)
    ]
    assert button.content == "See the sprints"
    await room.session.dispatch_event(button._i, "click", None)
    await room.settle()
    assert room.went == ["/more/sprints"]


# ------------------------------------------------------------------ location (ROOM-04)


def above_the_lists(room: Room) -> list[ft.Control]:
    """The column the day tabs are in: what sits above the day lists, then them."""
    column = room.tabs.content
    assert isinstance(column, ft.Column)
    return column.controls


async def test_a_pinned_room_s_card_heads_each_day_s_list(render: Render) -> None:
    """The card names the room and its floor, heads every day's list, and opens it.

    In the lists, not above the tabs: at the largest text it filled half the screen
    there and left the slots a quarter (D-346, as D-194 did for Now).
    """
    room = await render(VIEW)
    nodes = room.nodes("room.location")
    lists = room.day_lists()
    assert len(nodes) == len(lists) == 3
    for day in lists:
        (node,) = [n for n in nodes if day.controls[0] in ancestors(n)]
        assert node.label == "Show Grand Ballroom A on the Upper level floor plan"
    (tabs, _pages) = above_the_lists(room)
    assert isinstance(cast(ft.Container, tabs).content, ft.TabBar)
    tap = nodes[0].parent
    assert isinstance(tap, ft.Container) and tap.on_click is not None
    await room.click(tap)
    assert room.went == [f"{VIEW}/plan/upper?pin=grandballrooma"]


async def test_the_card_heads_today_s_list_before_now_in_this_room(
    render: Render,
) -> None:
    """Today's head: the card, then "Now in this room" and its divider."""
    room = await render(VIEW, now=SATURDAY_MORNING)
    head = room.day_lists()[1].controls[0]
    assert isinstance(head, ft.Column)
    (card,) = [n for n in room.nodes("room.location") if head in ancestors(n)]
    (now,) = room.nodes("room.now")
    first, second = head.controls
    assert first in ancestors(card)
    assert second in ancestors(now)


async def test_the_card_pulses_once_per_room_view(render: Render) -> None:
    """Each day's list builds a card; only the first to mount pulses (D-34)."""
    room = await render(VIEW)
    await room.settle()
    assert len(room.nodes("room.location")) == 3
    assert card_sleeps(room).asked == [location_card.PULSE_MS / 1000]


async def test_the_shown_day_s_card_pulses_twice_and_hidden_ones_stay_still(
    render: Render,
) -> None:
    """Opened on Saturday (tab 1), Saturday's pin pulses, not Friday's hidden one.

    Both pulses run, the hidden days' rings never move, and a tab change replays
    nothing (#602).
    """
    room = await render(VIEW)
    sleeps = card_sleeps(room)
    assert room.tabs.selected_index == 1
    for _ in range(location_card.PULSES):
        for out in (True, False):
            await room.until(lambda: sleeps.held == 1)
            assert [ring_out(room, day) for day in range(3)] == [False, out, False]
            await sleeps.release()
    await room.until(lambda: sleeps.held == 0)
    assert len(sleeps.asked) == 2 * location_card.PULSES
    room.session.apply_patch(room.tabs._i, {"selected_index": 0})  # as Flutter does
    await room.session.dispatch_event(room.tabs._i, "change", 0)
    await room.settle()
    assert room.tabs.selected_index == 0
    assert sleeps.held == 0 and len(sleeps.asked) == 2 * location_card.PULSES
    assert [ring_out(room, day) for day in range(3)] == [False, False, False]


def ring_out(room: Room, day: int) -> bool:
    """Whether the card heading the day's list has its pin's ring out, mid-pulse."""
    head = room.day_lists()[day].controls[0]
    (halo,) = [
        c
        for c in room.find(ft.Container)
        if c.animate_scale is not None and head in ancestors(c)
    ]
    return halo.scale == location_card.RING_SCALE


def card_sleeps(room: Room) -> HeldSleeps:
    """The location card's held sleeps, which the fixture installed."""
    return cast(HeldSleeps, location_card.asyncio)


async def test_a_room_without_a_pin_shows_no_card_and_no_gap(render: Render) -> None:
    """A room without a pin ("Elsewhere"): the day tabs come first, as before."""
    room = await render("/map/room/elsewhere", slug="elsewhere")
    assert room.nodes("room.location") == []
    first = above_the_lists(room)[0]
    assert isinstance(cast(ft.Container, first).content, ft.TabBar)


async def test_a_sprint_only_room_shows_its_location_card_too(render: Render) -> None:
    """S-2 has no sessions but a pin: the card heads its sprints state."""
    room = await render("/map/room/s-2", slug="s-2")
    label = room.node("room.location").label
    assert label == "Show S-2 on the Seaside meeting rooms floor plan"
