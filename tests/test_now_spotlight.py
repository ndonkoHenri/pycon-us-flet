"""Tests for Now's sponsor spotlight (#398; SHELL-08, SPON-11; D-37, D-298).

The pick itself is `core.sponsors` (`test_sponsors.py`); here, what Now makes of it:
one still card, one button node, the same sponsor for the process, nothing without a
candidate, and a tap that pushes the sponsor over Now. The screen runs in a real Flet
session through `tests/now_view.py`'s harness. How the card looks, wraps at 200 % and
reads to TalkBack and VoiceOver is checked on devices (the PR).
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from random import Random
from typing import Any

import flet as ft
import pytest

from pycon_us.core.models import ConferenceData
from pycon_us.core.sponsors import pick_spotlight, spotlight_candidates
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import now_spotlight
from pycon_us.state import Conference
from tests.feeds import processed
from tests.now_view import may, render  # noqa: F401  (the harness's fixture)


@pytest.fixture
def show(render: Callable[..., Any]) -> Callable[..., Any]:  # noqa: F811
    """`tests/now_view.py`'s `render`: Now at a time, in a real Flet session."""
    return render


SEED = 7
"""The seed of the tests' `Random`: any seed works, one keeps the pick known."""


def seeded() -> ViewMemory:
    """A fresh process's view memory, its pick drawn from `Random(SEED)`."""
    return ViewMemory(rng=Random(SEED))


def expected() -> str:
    """The slug that `Random(SEED)` picks from the 2026 candidates."""
    picked = pick_spotlight(spotlight_candidates(processed(2026)), "", Random(SEED))
    assert picked is not None
    return picked.slug


def conference(data: ConferenceData | None, now: datetime) -> Conference:
    """A `Conference` store holding `data`, fresh at `now`."""
    return Conference(data=data, source="bundled", version=1, fetched_at=now)


async def test_the_card_thanks_one_candidate_as_one_button_node(
    show: Callable[..., Any],
) -> None:
    """One node, a button with the identifier and the words; its logo says nothing."""
    memory = seeded()
    shown = await show(may(15, 11, 10), memory=memory)
    node = shown.node(now_spotlight.IDENTIFIER)
    sponsor = next(
        s for s in spotlight_candidates(processed(2026)) if s.slug == expected()
    )
    assert node.button
    assert node.exclude_semantics  # the text and the tile are not nodes of their own
    article = "an" if sponsor.level[0] in "AEIOU" else "a"
    assert node.label == f"Thanks to {sponsor.name}, {article} {sponsor.level} sponsor"
    assert memory.spotlight == sponsor.slug


async def test_the_same_sponsor_shows_for_the_process(
    show: Callable[..., Any],
) -> None:
    """A new session in the process (F29) keeps the pick: nothing is drawn again."""
    memory = seeded()
    await show(may(15, 11, 10), memory=memory)
    memory.rng = Random(SEED + 1)  # a draw now would most likely pick another
    again = await show(may(16, 9), memory=memory)
    assert memory.spotlight == expected()
    assert str(again.node(now_spotlight.IDENTIFIER).label).startswith("Thanks to ")


@pytest.mark.parametrize("large_text", [False, True])
async def test_at_large_text_the_words_go_under_the_tile(
    show: Callable[..., Any], large_text: bool
) -> None:
    """Beside the tile; under it, the card's whole width, at large text (#649).

    Beside the 56 dp tile and the chevron, the words broke inside a word at the
    largest sizes ("Maintaini / ng"); under them, the chevron stays at the right.
    """
    shown = await show(
        may(15, 11, 10),
        memory=seeded(),
        prefs=Prefs(loaded=True, time_above=large_text),
    )
    body = shown.node(now_spotlight.IDENTIFIER).content
    if large_text:
        assert isinstance(body, ft.Column)
        top, words = body.controls
        assert isinstance(top, ft.Row) and isinstance(words, ft.Text)
        assert isinstance(top.controls[-1], ft.Icon)  # the chevron
    else:
        assert isinstance(body, ft.Row)
        (words,) = [c for c in body.controls if isinstance(c, ft.Text)]
        assert words.expand  # what the tile and the chevron leave


async def test_a_sponsor_that_left_the_feed_is_replaced(
    show: Callable[..., Any],
) -> None:
    """A slug that is no longer a candidate gives way to a new pick."""
    memory = ViewMemory(spotlight="gone-sponsor", rng=Random(SEED))
    await show(may(15, 11, 10), memory=memory)
    assert memory.spotlight == expected()


@pytest.mark.parametrize("now", [may(1, 9), may(15, 11, 10), may(18, 10), may(25, 9)])
async def test_the_card_shows_last_in_every_season(
    show: Callable[..., Any], now: datetime
) -> None:
    """Before, during, on the sprint days and after: the card ends Now's list."""
    shown = await show(now, memory=seeded())
    identifiers = [
        c.identifier
        for c in shown.all()
        if isinstance(c, ft.Semantics) and c.identifier
    ]
    assert identifiers[-1] == now_spotlight.IDENTIFIER


async def test_without_candidates_nothing_shows(show: Callable[..., Any]) -> None:
    """A feed without a banner sponsor shows no card, and picks nothing."""
    now = may(15, 11, 10)
    data = processed(2026)
    levels = tuple(
        replace(
            level,
            sponsors=tuple(replace(s, mobile_banner=False) for s in level.sponsors),
        )
        for level in data.sponsor_levels
    )
    memory = seeded()
    shown = await show(
        now,
        conference=conference(replace(data, sponsor_levels=levels), now),
        memory=memory,
    )
    assert not shown.has(now_spotlight.IDENTIFIER)
    assert memory.spotlight == ""


async def test_without_data_nothing_shows(show: Callable[..., Any]) -> None:
    """While the schedule loads, there is no card."""
    now = may(15, 11, 10)
    shown = await show(now, conference=conference(None, now), memory=seeded())
    assert not shown.has(now_spotlight.IDENTIFIER)


async def test_a_tap_pushes_the_sponsor_over_now(show: Callable[..., Any]) -> None:
    """Back from the detail pops to Now (D-17): the detail is pushed on /now."""
    shown = await show(may(15, 11, 10), memory=seeded())
    tappable = shown.node(now_spotlight.IDENTIFIER).parent
    assert isinstance(tappable, ft.Container)
    await shown.click(tappable)
    assert shown.went == [f"/now/sponsor/{expected()}"]


async def test_the_minute_tick_does_not_re_render_the_card(
    show: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card is memoised on its sponsor: a minute re-renders Now, not the card."""
    bodies: list[str] = []
    words = now_spotlight.thanks

    def counted(sponsor: Any) -> str:
        """Count the card's body runs, then say its words."""
        bodies.append(sponsor.slug)
        return words(sponsor)

    monkeypatch.setattr(now_spotlight, "thanks", counted)
    shown = await show(may(15, 11, 10), memory=seeded())
    assert bodies == [expected()]
    await shown.at(may(15, 11, 11))
    await shown.at(may(15, 21))
    assert bodies == [expected()]
