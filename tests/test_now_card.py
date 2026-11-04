"""Tests for the Now tab's next-session card, the minute tick, the resume and no data.

The screen runs in `tests/now_view.py`'s harness, with the clock held by the test.
"""

import asyncio
from collections.abc import Callable
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.screens import now as screen
from pycon_us.state import Conference
from pycon_us.ui import status_strip
from tests import now_view
from tests.now_view import (
    AT_11,
    FIRST_AT_11,
    JOB_FAIR,
    KEYNOTE,
    OPEN_SPACE,
    TALK,
    Ticks,
    _texts,
    _walk,
    header,
    may,
    next_cards,
)

render = now_view.render


# ------------------------------------------------------------------ your next session


async def test_your_next_session_is_the_saved_one_due_with_its_star_and_room(
    render: Callable[..., Any],
) -> None:
    """The card holds the saved session due next, with its star, status and room."""
    shown = await render(may(16, 9), saved=(TALK,))  # it starts in 1 h 30 min
    (card,) = next_cards(shown)
    assert shown.listed("now.next.session.") == [TALK]
    assert not shown.has("now.next_session")  # the tile's: nothing to explain
    assert any(
        isinstance(c, ft.Semantics) and c.identifier == f"now.next.favorite.{TALK}"
        for c in _walk(card)
    )
    assert "Starts in 1 h 30 min" in _texts(card)
    # Not on yet: no bar.
    assert not [c for c in _walk(card) if isinstance(c, ft.ProgressBar)]
    show_room = shown.node("now.show_room").content
    assert isinstance(show_room, ft.TextButton)
    await shown.click(show_room)
    assert shown.went == [f"/now/room/grand-ballroom-a?highlight={TALK}"]


async def test_the_card_s_status_is_a_stop_of_its_own(
    render: Callable[..., Any],
) -> None:
    """Row, status, star and "Show room": four stops (ux.md §5.1)."""
    shown = await render(may(16, 9), saved=(TALK,))
    (card,) = next_cards(shown)
    (status,) = [
        c
        for c in _walk(card)
        if isinstance(c, ft.Text) and c.value == "Starts in 1 h 30 min"
    ]
    assert status.semantics_label == "Starts in 1 hour 30 minutes"
    # Not in the row's merged node: the row's phrase does not say it.
    assert "Starts in" not in str(shown.node(f"now.next.session.{TALK}").label)
    # At large text "Show room" moves under the status whole.
    (actions,) = [
        c for c in _walk(card) if isinstance(c, ft.Row) and status in _walk(c)
    ][-1:]
    assert actions.wrap is True
    # Stretched across the card, so the button sits at its end on one line.
    assert actions.alignment == ft.MainAxisAlignment.SPACE_BETWEEN
    (column,) = [c for c in _walk(card) if isinstance(c, ft.Column)][:1]
    assert column.horizontal_alignment == ft.CrossAxisAlignment.STRETCH


async def test_your_session_on_is_in_the_card_with_its_bar_not_twice(
    render: Callable[..., Any],
) -> None:
    """A saved session on is in the card, with its bar, and not in Happening now."""
    shown = await render(may(15, 11, 10), saved=(OPEN_SPACE,))
    assert shown.listed("now.next.session.") == [OPEN_SPACE]
    card = shown.node(f"now.next.session.{OPEN_SPACE}")
    assert str(card.label).endswith(" 16 percent elapsed.")
    assert [c.value for c in _walk(card) if isinstance(c, ft.ProgressBar)] == [0.16]
    assert shown.listed()[:3] == list(FIRST_AT_11)
    assert OPEN_SPACE not in shown.listed()


async def test_your_next_session_is_not_repeated_in_up_next(
    render: Callable[..., Any],
) -> None:
    """The 11:30 talk is alone in its slot: the card says when, Up next is left out."""
    shown = await render(may(15, 11, 10), saved=("27",))
    assert shown.listed("now.next.session.") == ["27"]
    assert "27" not in shown.listed()
    assert shown.texts().count("Starts in 20 min") == 1  # the card's status
    assert shown.headings() == ["Your next session", "Happening now"]
    assert "See the rest of today in Schedule" in shown.texts()


async def test_up_next_lists_the_rest_of_its_slot_but_your_session(
    render: Callable[..., Any],
) -> None:
    """Up next lists the rest of its slot, without the saved session in the card."""
    shown = await render(may(15, 10, 50), saved=("4",))
    assert shown.listed("now.next.session.") == ["4"]
    assert "Up next · 11:00 AM" in shown.headings()
    await shown.show_all("up_next")
    # The talks, then the open spaces (D-327), each in the slot's order.
    talks = [i for i in AT_11 if not i.startswith("9") and i != "4"]
    open_spaces = [i for i in AT_11 if i.startswith("9")]
    assert shown.listed()[-(len(AT_11) - 1) :] == [*talks, *open_spaces]


async def test_the_card_s_bar_follows_the_time_its_row_shows(
    render: Callable[..., Any],
) -> None:
    """The Job Fair shows 9:30 though its slot is 10:00 (DATA-11): on from 9:30 (D-186)."""
    shown = await render(may(17, 9, 45), saved=(JOB_FAIR,))
    card = shown.node(f"now.next.session.{JOB_FAIR}")
    assert str(card.label).endswith(" 7 percent elapsed.")
    assert [c.value for c in _walk(card) if isinstance(c, ft.ProgressBar)] == [0.07]


async def test_when_only_your_session_is_on_the_card_says_so(
    render: Callable[..., Any],
) -> None:
    """A keynote is alone in its slot: no Happening now section to say "nothing"."""
    shown = await render(may(15, 9, 50), saved=(KEYNOTE,))
    assert shown.listed("now.next.session.") == [KEYNOTE]
    assert "Happening now" not in shown.headings()
    assert "Nothing in session right now" not in shown.texts()
    (card,) = next_cards(shown)
    assert "Happening now" in _texts(card)  # the card's status says it


async def test_with_nothing_saved_it_says_how_to_save_a_session(
    render: Callable[..., Any],
) -> None:
    """With nothing saved, the card's tile says how to save a session."""
    shown = await render(may(16, 9))
    tile = shown.node("now.next_session")
    assert _texts(tile)[:2] == [
        "Nothing saved yet",
        "Star a session to see it here",
    ]


async def test_with_nothing_saved_soon_it_points_at_my_schedule(
    render: Callable[..., Any],
) -> None:
    """With nothing saved for 3 hours, the tile says so and opens My schedule."""
    shown = await render(may(15, 9), saved=(TALK,))  # tomorrow
    tile = shown.node("now.next_session")
    assert _texts(tile)[0] == "Nothing saved for the next 3 hours"
    (list_tile,) = [c for c in _walk(tile) if isinstance(c, ft.ListTile)]
    assert list_tile.on_click is not None
    cast(Callable[[], None], list_tile.on_click)()
    assert shown.went == ["/my-schedule"]


async def test_a_row_pushes_its_session_over_now(
    render: Callable[..., Any],
) -> None:
    """Back from the detail pops to Now (D-17): the detail is pushed on /now."""
    shown = await render(may(15, 11, 10))
    tappable = shown.node("now.session.4").parent
    assert isinstance(tappable, ft.Container)
    await shown.click(tappable)
    assert shown.went == ["/now/session/4"]


# ------------------------------------------------------------------ time passing


async def test_a_minute_moves_the_bars_and_re_renders_only_their_rows(
    render: Callable[..., Any],
) -> None:
    """A minute's tick moves the bars and re-renders only the rows on now (D-153)."""
    shown = await render(may(15, 11, 10))
    shown.rows.clear()
    await shown.at(may(15, 11, 11))
    assert str(shown.node("now.session.4").label).endswith(" 36 percent elapsed.")
    assert "27" not in shown.rows  # Up next did not change (D-153)
    assert "4" in shown.rows


async def test_the_minute_tick_turns_the_day_into_its_evening(
    render: Callable[..., Any],
) -> None:
    """The minute tick turns the header from the day to its evening's wrap."""
    shown = await render(may(15, 19, 59))
    await shown.at(may(15, 21))
    assert "That's a wrap for today" in header(shown)


async def test_a_resume_recomputes_at_once(
    render: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """In the background nothing ticks; the return catches up at once (D-40, D-175)."""
    monkeypatch.setattr(status_strip, "TICK_SECONDS", 0.01)
    shown = await render(may(15, 11, 10), ticks=Ticks())  # the real loop
    shown.services.foreground.clear()  # pause
    shown.clock[0] = may(15, 21)
    await asyncio.sleep(0.05)
    await shown.settle()
    assert "Up next at 11:30 AM" in header(shown)  # still the morning
    shown.services.foreground.set()  # resume
    await asyncio.sleep(0)
    await shown.settle()
    assert "That's a wrap for today" in header(shown)


async def test_the_strip_refreshes_the_feed_while_now_shows(
    render: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Now builds its status strip with `auto_refresh` on, so it refreshes the feed.

    That flag is what makes the strip refresh every 15 min while Now shows (D-175);
    the refresh itself is pinned in test_status_strip_ticks.py.
    """
    strips: list[bool] = []

    def strip(*, auto_refresh: bool = False) -> ft.Control:
        strips.append(auto_refresh)
        return ft.Text("strip")

    monkeypatch.setattr(screen, "StatusStrip", strip)
    shown = await render(may(15, 11, 10))
    assert strips and all(strips)  # the 15-min refresh runs here (D-175)
    assert shown.body.controls[1] is not None


# ------------------------------------------------------------------ without data


async def test_without_data_it_shows_the_skeleton_until_the_first_fetch_fails(
    render: Callable[..., Any],
) -> None:
    """With no data, Now shows a skeleton while loading, then the fetch's error."""
    loading = await render(may(15, 11, 10), conference=Conference())
    assert any(
        isinstance(c, ft.Semantics) and c.label == "Loading schedule"
        for c in loading.all()
    )
    failed = await render(may(15, 11, 10), conference=Conference(problem="offline"))
    state = failed.node("now.no_data")
    assert "Can't load the schedule" in _texts(state)
    assert "Connect to the internet and try again." in _texts(state)
