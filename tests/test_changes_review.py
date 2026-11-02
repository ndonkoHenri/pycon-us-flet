"""Tests for the Review SnackBar and the Schedule's overflow (``screens/changes_review.py``).

NEW-04, D-255, D-335, #437. Each case runs in a real Flet session (``tests/sessions.py``)
under a host that mounts the hook as ``App`` does and shows Schedule changes when the
test opens it. Batches are recorded by ``ChangeLog.record()`` from feed pairs built in
``tests/feeds.py``; the clock is held at 10:42 AM on Saturday, May 16 in Long Beach.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.change_log import Published, use_change_log
from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData
from pycon_us.favorites import use_favorites
from pycon_us.locations import parent_of
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.screens import schedule_changes
from pycon_us.screens.changes_review import (
    MENU_LABEL,
    REVIEW,
    ScheduleOverflow,
    close_review,
    use_review_snack_bar,
)
from pycon_us.services import use_services
from pycon_us.state import Conference
from pycon_us.ui import snack_bars
from pycon_us.ui.snack_bars import SNACK_BAR_MS
from tests.feeds import Edit, add, changed, move, processed, recorded, rename, settings
from tests.harness import Shown, showing
from tests.sessions import menu_text, text_of

YEAR = load_year(2026)
URL = "https://example.test/conference.json"
"""The feed URL both sides of each pair came from."""

NOW = datetime(2026, 5, 16, 17, 42, tzinfo=UTC)
TALK = 142
"""A 2026 talk in the recorded feed."""

OTHER = 51
"""Another 2026 talk."""

OPEN: list[Callable[[bool], None]] = []
"""The host's setter of whether the list shows, from its latest render."""


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    """Freeze ``clock.now()`` at ``NOW`` for the test, then return to real time."""
    clock.set_test_now(NOW)
    yield
    clock.set_test_now(None)


@ft.component
def Host() -> ft.Control:
    """Mount the hook as ``App`` does; show Schedule changes once the test opens it."""
    use_review_snack_bar(use_services(), use_change_log(), use_favorites(), use_prefs())
    opened, set_opened = ft.use_state(False)
    OPEN[:] = [set_opened]
    return schedule_changes.ScheduleChanges("2026") if opened else ft.Text("elsewhere")


@pytest.fixture
async def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Shown]:
    """The host in a real Flet session at ``/now/session/142``, nothing saved."""
    async with showing(
        Host,
        schedule_changes,
        year=YEAR,
        conference=Conference(data=processed(2026), source="network", version=1),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path="/now",
        prefs=Prefs(loaded=True),
        route="/now/session/142",
    ) as shown:
        yield shown


def feed(*edits: Edit) -> ConferenceData:
    """The recorded 2026 feed with ``edits`` applied, processed."""

    def apply(doc: dict[str, object]) -> None:
        for edit in edits:
            edit(doc)

    raw = changed(2026, apply) if edits else recorded(2026)
    return process(raw, settings(2026))


async def record(shown: Shown, before: ConferenceData, after: ConferenceData) -> None:
    """Record the change from ``before`` to ``after`` as a network refresh publishes it."""
    await shown.change_log.record(
        shown.storage,
        Published(before, "network", URL),
        Published(after, "network", URL),
        lambda: True,
    )
    await shown.settle()


def said(shown: Shown) -> list[str]:
    """The texts of the SnackBars the page showed, in order."""
    return [text_of(bar.content) for bar in shown.snack_bars]


def updates(monkeypatch: pytest.MonkeyPatch) -> list[ft.SnackBar]:
    """Record each SnackBar sent to the client again: a closed one must be sent."""
    sent: list[ft.SnackBar] = []

    def update(snack: ft.SnackBar) -> None:
        sent.append(snack)

    monkeypatch.setattr(ft.SnackBar, "update", update)
    return sent


async def review(shown: Shown) -> None:
    """Tap the last SnackBar's Review, as the client would."""
    action = cast(ft.SnackBarAction, shown.snack_bars[-1].action)
    assert action.label == REVIEW
    await shown.click(action)


# ------------------------------------------------------------------ the SnackBar


async def test_a_batch_shows_one_floating_review_snack_bar(host: Shown) -> None:
    """A move and a rename of unsaved sessions: "Schedule updated · 2 changes", Review, 4 s."""
    await record(host, feed(), feed(move(OTHER, "Room 101B"), rename(TALK, "New")))
    (bar,) = host.snack_bars
    assert said(host) == ["Schedule updated · 2 changes"]
    assert bar.open and bar.behavior == ft.SnackBarBehavior.FLOATING
    assert bar.duration == SNACK_BAR_MS and not bar.persist


async def test_saved_sessions_are_counted_first(host: Shown) -> None:
    """A batch that touches a saved session says how many saved sessions changed."""
    await host.favorites.toggle(host.storage, str(TALK))
    await record(host, feed(), feed(move(TALK, "Room 101B"), rename(OTHER, "New")))
    assert said(host) == ["1 saved session changed"]


async def test_same_data_and_additions_only_show_nothing(host: Shown) -> None:
    """No change records nothing, and a batch of additions only is recorded silently."""
    await record(host, feed(), feed())
    await record(host, feed(), feed(add(9001, TALK, "A new open space")))
    assert len(host.change_log.batches) == 1  # the additions are listed
    assert host.snack_bars == []


async def test_a_refresh_that_no_longer_counts_shows_nothing(host: Shown) -> None:
    """A refresh whose URL was left, or whose session closed, records and shows nothing."""
    await host.change_log.record(
        host.storage,
        Published(feed(), "network", URL),
        Published(feed(move(OTHER, "Room 101B")), "network", URL),
        lambda: False,
    )
    await host.settle()
    assert host.snack_bars == []


async def test_each_batch_gets_its_own_snack_bar_once(host: Shown) -> None:
    """Two batches show two SnackBars; a later notification of the log shows no more."""
    first = feed(move(OTHER, "Room 101B"))
    await record(host, feed(), first)
    await record(host, first, feed(move(OTHER, "Room 101B"), rename(TALK, "New")))
    cast(ft.Observable, host.change_log).notify()  # a notification, no batch
    await host.settle()
    assert said(host) == ["Schedule updated · 1 change"] * 2


async def test_a_screen_reader_keeps_it_until_used(host: Shown) -> None:
    """With a screen reader on, the SnackBar persists, as the Undo one does (D-184)."""
    host.prefs.screen_reader = True
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    assert host.snack_bars[-1].persist


async def test_it_closes_once_no_screen_reader_is_on(
    host: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#343: TalkBack off in front closes it after its 4 s, as the Undo one (D-356)."""
    monkeypatch.setattr(snack_bars, "SNACK_BAR_MS", 10)
    host.prefs.screen_reader = True  # and the OS says none is on now
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    bar = host.snack_bars[-1]
    assert bar.persist
    await asyncio.sleep(0.05)
    assert not bar.open and not host.prefs.screen_reader


async def test_review_pushes_the_list_on_the_view_on_top(host: Shown) -> None:
    """Review pushes ``changes/2026`` on the current View, so Back returns there."""
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    await review(host)
    assert host.went == ["/now/session/142/changes/2026"]
    assert parent_of(host.went[0]) == "/now/session/142"


async def test_review_over_search_drops_the_query(host: Shown) -> None:
    """Over search, the list is pushed on ``/search``; the query is a view option."""
    host.session.page.route = "/search?q=pathlib"
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    await review(host)
    assert host.went == ["/search/changes/2026"]


async def test_review_on_the_list_only_closes_it(
    host: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On ``…/changes/2026`` Review pushes nothing and closes its SnackBar (D-255)."""
    host.prefs.screen_reader = True
    host.session.page.route = "/schedule/changes/2026"
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    sent = updates(monkeypatch)
    await review(host)
    assert host.went == []
    (bar,) = host.snack_bars
    assert not bar.open and sent == [bar]


# ------------------------------------------------------------------ closing it


async def test_showing_the_list_closes_it(
    host: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a screen reader on, the list closes the Review SnackBar when it shows."""
    host.prefs.screen_reader = True
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    sent = updates(monkeypatch)
    OPEN[0](True)
    await host.settle()
    (bar,) = host.snack_bars
    assert not bar.open and sent == [bar]


@pytest.mark.parametrize("route", ["/now/changes/2026", "/more/settings/changes/2026"])
async def test_opening_from_now_s_card_or_settings_closes_it(
    host: Shown, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """The list pushed by Now's card or Settings › Data closes it too (#438)."""
    host.prefs.screen_reader = True
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    sent = updates(monkeypatch)
    host.session.page.route = route
    OPEN[0](True)
    await host.settle()
    (bar,) = host.snack_bars
    assert not bar.open and sent == [bar]


async def test_a_newer_batch_outlives_an_earlier_opening(
    host: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A batch's SnackBar shown while the list is open stays until used or replaced."""
    host.prefs.screen_reader = True
    first = feed(move(OTHER, "Room 101B"))
    await record(host, feed(), first)
    OPEN[0](True)
    await host.settle()
    sent = updates(monkeypatch)
    await record(host, first, feed(move(OTHER, "Room 101B"), rename(TALK, "New")))
    older, newer = host.snack_bars[-2:]
    assert newer.open and newer is not older and sent == []


async def test_mark_all_as_seen_closes_it(
    host: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``close_review()``, which Mark all as seen calls, closes it, and only once."""
    host.prefs.screen_reader = True
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    sent = updates(monkeypatch)
    close_review(host.session.page)
    close_review(host.session.page)
    (bar,) = host.snack_bars
    assert not bar.open and sent == [bar]


async def test_a_snack_bar_that_has_gone_is_not_closed_again(
    host: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One Flet already reports dismissed (used, or replaced) is not sent again."""
    await record(host, feed(), feed(move(OTHER, "Room 101B")))
    host.snack_bars[-1].open = False  # as Flet's dismiss sets it
    sent = updates(monkeypatch)
    close_review(host.session.page)
    assert sent == []


# ------------------------------------------------------------------ the overflow


@pytest.fixture
async def overflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Shown]:
    """The Schedule's overflow alone, on the Schedule's View."""
    async with showing(
        lambda: ScheduleOverflow(source=__name__),
        year=YEAR,
        conference=Conference(data=processed(2026), source="bundled", version=1),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path="/schedule",
    ) as shown:
        yield shown


async def test_the_overflow_pushes_schedule_changes_on_the_schedule(
    overflow: Shown,
) -> None:
    """Schedule › More options › Schedule changes pushes the list; Back returns."""
    menu = cast(ft.PopupMenuButton, overflow.node("schedule.overflow").content)
    (item,) = menu.items
    assert cast(ft.Semantics, item.content).identifier == "schedule.changes"
    assert menu_text(item).value == MENU_LABEL
    await overflow.click(item)
    assert overflow.went == ["/schedule/changes/2026"]
    assert parent_of(overflow.went[0]) == "/schedule"
