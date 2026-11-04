"""Tests for Now's quick info buttons (#419; INFO-08, INFO-07, MAP-09; D-338).

What Now makes of them: three tonal buttons in the conference and sprint seasons only,
after the sessions and the Schedule link, so at peak times they push no session down,
each pushing its page over Now so Back returns there. The screen runs in a real Flet
session through `tests/now_view.py`'s harness. How the row wraps at 200 % and reads to
TalkBack and VoiceOver is checked on devices (the PR).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import flet as ft
import pytest

from pycon_us.locations import parent_of
from pycon_us.screens import now_quick
from pycon_us.screens.more import AT_THE_VENUE
from tests.now_view import may, render  # noqa: F401  (the harness's fixture)

BUTTONS = [f"now.quick.{segment}" for segment in now_quick.PAGES]
"""The buttons' identifiers, in the row's order."""


@pytest.fixture
def show(render: Callable[..., Any]) -> Callable[..., Any]:  # noqa: F811
    """`tests/now_view.py`'s `render`: Now at a time, in a real Flet session."""
    return render


def identifiers(shown: Any) -> list[str]:
    """The identifiers on Now's screen, in reading order."""
    return [
        str(c.identifier)
        for c in shown.all()
        if isinstance(c, ft.Semantics) and c.identifier
    ]


@pytest.mark.parametrize("now", [may(15, 11, 10), may(17, 20), may(18, 10)])
async def test_the_buttons_show_at_the_venue_after_the_sessions(
    show: Callable[..., Any], now: datetime
) -> None:
    """A peak, the last evening, a sprint day: the row follows every session row.

    It comes after the sections and before the spotlight, so it never pushes Now's
    sessions down (D-338, D-327).
    """
    shown = await show(now)
    order = identifiers(shown)
    places = [order.index(identifier) for identifier in BUTTONS]
    assert places == sorted(places)
    last_section = max(
        i
        for i, identifier in enumerate(order)
        if identifier.startswith("now.")
        and identifier not in BUTTONS
        and identifier != "now.spotlight"
    )
    assert places[0] > last_section
    if "now.spotlight" in order:
        assert places[-1] < order.index("now.spotlight")


@pytest.mark.parametrize("now", [may(1, 9), may(25, 9)])
async def test_the_buttons_hide_before_and_after_the_conference(
    show: Callable[..., Any], now: datetime
) -> None:
    """In the countdown and after the sprints, Now shows no quick info button."""
    shown = await show(now)
    assert not any(shown.has(identifier) for identifier in BUTTONS)


async def test_each_button_pushes_its_page_over_now(show: Callable[..., Any]) -> None:
    """A tap pushes `/now/<page>`, whose Back returns to Now (D-17)."""
    shown = await show(may(15, 11, 10))
    for identifier in BUTTONS:
        button = shown.node(identifier).content
        assert isinstance(button, ft.FilledTonalButton)
        await shown.click(button)
    assert shown.went == ["/now/wifi", "/now/help", "/now/venue"]
    assert {parent_of(location) for location in shown.went} == {"/now"}


def test_the_buttons_say_what_more_says() -> None:
    """Their titles and icons are More's At the venue entries, Wi-Fi first."""
    entries = now_quick.entries()
    assert {e.title for e in entries} == {e.title for e in AT_THE_VENUE}
    assert [e.title for e in entries] == ["Wi-Fi", "Help & safety", "Venue & hours"]
