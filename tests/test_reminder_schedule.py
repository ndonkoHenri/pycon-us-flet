"""Tests for keeping E3's reminders in step with the app (``reminder_schedule.py``; #447).

``current_plan()`` over the stores, and the hook in a real Flet session
(``tests/sessions.py``) under a stand-in for ``App``, with a ``Scheduler`` over
``tests/fakes.py``'s ``MemoryNotifications``: it applies once the start has loaded, at
each change of a watched field and on resume, and not for other changes (D-222, D-389).
Then ``use_reminder_taps()``: taps navigate only while the boot gate is open (D-396).
"""

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet_notifications import Notifications

from pycon_us import clock
from pycon_us.app import on_resume
from pycon_us.change_log import ChangeLog
from pycon_us.config import YearData, load_year
from pycon_us.core.change_batches import Batch
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.reminder_schedule import (
    current_plan,
    use_reminder_schedule,
    use_reminder_taps,
)
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services import Services
from pycon_us.services.reminders import Scheduler, reminder_id
from pycon_us.state import Conference
from tests.fakes import MemoryNotifications
from tests.feeds import processed
from tests.sessions import memory_services, rendering, settle

ZONE = ZoneInfo("America/Los_Angeles")
"""2026's conference zone."""

BEFORE = datetime(2026, 5, 1, 9, 0, tzinfo=ZONE)
"""A real now before PyCon US 2026: every session and moment is in the future."""

TALK = "142"
"""A 2026 talk: Saturday 16 May at 10:30 AM in Grand Ballroom A."""

KEYNOTE_MOMENT = 8050
"""The first keynote's moment (D-274)."""


@pytest.fixture(scope="module")
def year() -> YearData:
    """2026's bundled year data."""
    return load_year(2026)


@pytest.fixture
def held() -> Iterator[None]:
    """Hold ``clock.real_now()`` at ``BEFORE``; real time again afterwards."""
    clock.set_test_now(BEFORE)
    yield
    clock.set_test_now(None)


@dataclass
class Shown:
    """The stand-in ``App`` rendering the hook, its stores and the fake OS."""

    svc: Services
    conference: Conference
    favorites: Favorites
    change_log: ChangeLog
    prefs: Prefs
    os: MemoryNotifications

    @property
    def applies(self) -> int:
        """How many applies began: each one cancels the pending reminders first."""
        return self.os.calls.count("cancel_all_pending")


def showing(year: YearData, tmp_path: Path, *, loaded: bool) -> Shown:
    """Return the stores and services for the hook, the feed published."""
    os = MemoryNotifications()
    svc = replace(
        memory_services(year, tmp_path),
        reminders=Scheduler(cast(Notifications, os), android=True),
    )
    conference = Conference()
    conference.data = processed(2026)
    return Shown(
        svc,
        conference,
        Favorites(ids=frozenset({TALK}), loaded=True),
        ChangeLog(),
        Prefs(reminders=ReminderSettings(session_lead=10), loaded=loaded),
        os,
    )


@pytest.fixture
async def shown(year: YearData, tmp_path: Path, held: None) -> AsyncIterator[Shown]:
    """The hook under a stand-in ``App`` whose start has loaded, TALK saved."""
    state = showing(year, tmp_path, loaded=True)

    @ft.component
    def Host() -> ft.Control:
        """``App``'s part: the hook."""
        use_reminder_schedule(
            state.svc, state.conference, state.favorites, state.change_log, state.prefs
        )
        return ft.Column()

    async with rendering(Host):
        yield state
        state.svc.close()  # ends the loop before the session goes
        await settle()


def test_there_is_no_plan_before_a_feed(year: YearData) -> None:
    """Until the start publishes a feed, nothing is planned, so nothing is cancelled."""
    plan = current_plan(year, Conference(), Favorites(), Prefs(), BEFORE, use_24h=False)
    assert plan == []


def test_the_plan_holds_saved_sessions_and_the_keynotes_moments(year: YearData) -> None:
    """A saved talk's reminder, by the settings' lead, and the feed's keynote moments."""
    conference = Conference()
    conference.data = processed(2026)
    prefs = Prefs(reminders=ReminderSettings(session_lead=10))
    favorites = Favorites(ids=frozenset({TALK}))
    ids = {
        r.id
        for r in current_plan(year, conference, favorites, prefs, BEFORE, use_24h=False)
    }
    assert {reminder_id(TALK), KEYNOTE_MOMENT} <= ids


async def test_it_applies_once_the_start_has_loaded(shown: Shown) -> None:
    """The start's apply schedules the saved talk and the moments, exact when allowed."""
    assert shown.applies == 1
    assert reminder_id(TALK) in shown.os.pending
    assert KEYNOTE_MOMENT in shown.os.pending


async def test_a_watched_change_applies_again(shown: Shown) -> None:
    """Unsaving the talk applies a plan without its reminder."""
    shown.favorites.ids = frozenset()
    await settle()
    assert shown.applies == 2
    assert reminder_id(TALK) not in shown.os.pending
    assert KEYNOTE_MOMENT in shown.os.pending


@pytest.mark.parametrize("store", ["favorites", "conference", "prefs", "change_log"])
async def test_each_store_s_change_asks(shown: Shown, store: str) -> None:
    """Favourites, the feed, the reminder settings and the change log each ask."""
    if store == "favorites":
        shown.favorites.ids = frozenset({TALK, "143"})
    elif store == "conference":
        shown.conference.version += 1
    elif store == "prefs":
        shown.prefs.reminders = ReminderSettings(session_lead=5)
    else:
        shown.change_log.batches = (Batch(detected_at=BEFORE, changes=()),)
    await settle()
    assert shown.applies == 2


async def test_other_changes_leave_the_reminders_alone(shown: Shown) -> None:
    """A refresh starting or the theme changing plans nothing again."""
    shown.conference.refreshing = True
    shown.prefs.theme = "dark"
    await settle()
    assert shown.applies == 1


async def test_a_resume_applies_again(shown: Shown) -> None:
    """``on_resume()`` asks for an apply, which brings back what the OS dropped."""
    shown.os.pending.clear()  # as a force-stop or the OS clears them
    shown.conference._started_at = clock.now()  # no refresh is due
    await on_resume(shown.svc, shown.conference, shown.prefs)
    await settle()
    assert shown.applies == 2
    assert reminder_id(TALK) in shown.os.pending


async def test_nothing_is_applied_before_the_start_has_loaded(
    year: YearData, tmp_path: Path, held: None
) -> None:
    """While the boot gate waits on the settings and the feed, nothing is cancelled."""
    state = showing(year, tmp_path, loaded=False)

    @ft.component
    def Host() -> ft.Control:
        """``App``'s part: the hook, before the start ends."""
        use_reminder_schedule(
            state.svc, state.conference, state.favorites, state.change_log, state.prefs
        )
        return ft.Column()

    async with rendering(Host):
        state.favorites.ids = frozenset()
        await settle()
        assert state.os.calls == []


async def test_without_e3_the_hook_does_nothing(
    year: YearData, tmp_path: Path, held: None
) -> None:
    """With no Scheduler, as in the companion app, the interim stands (D-60)."""
    svc = memory_services(year, tmp_path)
    assert svc.reminders is None
    prefs = Prefs(loaded=True)

    @ft.component
    def Host() -> ft.Control:
        """``App``'s part: the hook, without E3."""
        use_reminder_schedule(svc, Conference(), Favorites(), ChangeLog(), prefs)
        return ft.Column()

    async with rendering(Host):
        prefs.reminders = ReminderSettings(session_lead=5)
        await settle()


async def test_taps_navigate_only_while_the_gate_is_open(
    year: YearData, tmp_path: Path, held: None
) -> None:
    """Before the gate opens a tap is held for ``Start``; after, it navigates at once."""
    state = showing(year, tmp_path, loaded=False)
    scheduler = state.svc.reminders
    assert scheduler is not None
    gate: dict[str, Callable[[], None]] = {}

    @ft.component
    def Host() -> ft.Control:
        """``App``'s part: the hook, with the gate as the test sets it."""
        ready, set_ready = ft.use_state(False)
        gate["open"] = lambda: set_ready(True)
        use_reminder_taps(state.svc, ready=ready)
        return ft.Column()

    async with rendering(Host) as session:
        went: list[str] = []
        session.page.navigate = went.append  # pyright: ignore[reportAttributeAccessIssue]
        scheduler.open_tapped("/my-schedule/session/142")
        assert (scheduler.tapped, went) == ("/my-schedule/session/142", [])
        gate["open"]()
        await settle()
        scheduler.open_tapped("/schedule/session/153")
        assert went == ["/schedule/session/153"]
        assert scheduler.tapped == "/my-schedule/session/142"  # Start's to take
