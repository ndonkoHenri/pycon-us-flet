"""Tests for the in-app reminder Banner (`ui/reminder_banner.py`; #428, D-60, NEW-05).

The hook renders in a real Flet session (`tests/sessions.py`) under a stand-in for
`App`, with `ft.use_dialog` recorded, the clock held and `page.navigate`
recorded, and E3's `Scheduler` over `tests/fakes.py`'s `MemoryNotifications`,
its notifications not shown until a test says so. When the Banner shows is
`due_session()`'s, tested in `test_reminders.py`; here, what the hook does with
it: when it asks, what it shows, what Open and Dismiss do, and `os_reminds()`'s
rule, which hides it while the OS reminds (D-396).
"""

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet_notifications import Notifications

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.reminder_settings import ReminderSettings, SessionLead
from pycon_us.services import Services
from pycon_us.services.reminders import Scheduler
from pycon_us.state import Conference
from pycon_us.ui.reminder_banner import os_reminds, use_reminder_banner
from tests.fakes import MemoryNotifications
from tests.feeds import processed
from tests.sessions import memory_services, rendering, settle

ZONE = ZoneInfo("America/Los_Angeles")
"""2026's conference zone."""

TALK = "142"
"""A 2026 talk: Saturday 16 May at 10:30 AM in Grand Ballroom A."""

TALK_START = datetime(2026, 5, 16, 10, 30, tzinfo=ZONE)
"""When `TALK` starts, as the app shows it."""


@dataclass
class Shown:
    """The stand-in `App` rendering the hook, and what it did."""

    svc: Services
    conference: Conference
    favorites: Favorites
    prefs: Prefs
    dialogs: list[ft.DialogControl | None]
    went: list[str] = field(default_factory=list)

    @property
    def scheduler(self) -> Scheduler:
        """E3's `Scheduler`, whose `read_enabled()` reads the fake OS's answer."""
        assert self.svc.reminders is not None
        return self.svc.reminders

    @property
    def banner(self) -> ft.Banner | None:
        """The Banner the last render asked `ft.use_dialog` for, or None."""
        last = self.dialogs[-1] if self.dialogs else None
        assert last is None or isinstance(last, ft.Banner)
        return last


@pytest.fixture
def held() -> Iterator[Callable[[datetime], None]]:
    """Hold `clock.now()` where a test puts it; real time again afterwards."""
    yield clock.set_test_now
    clock.set_test_now(None)


@pytest.fixture
async def shown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    held: Callable[[datetime], None],
) -> AsyncIterator[Shown]:
    """The hook under a stand-in `App`, 9 min before `TALK`, which is saved."""
    held(TALK_START - timedelta(minutes=9))
    conference = Conference()
    conference.data = processed(2026)
    favorites = Favorites(ids=frozenset({TALK}), loaded=True)
    svc = replace(
        memory_services(load_year(2026), tmp_path),
        reminders=Scheduler(cast(Notifications, MemoryNotifications())),
    )
    prefs = Prefs(reminders=ReminderSettings(session_lead=10), loaded=True)
    state = Shown(svc, conference, favorites, prefs, [])
    monkeypatch.setattr(ft, "use_dialog", state.dialogs.append)

    @ft.component
    def Host() -> ft.Control:
        """`App`'s part: the hook, with the boot gate open."""
        use_reminder_banner(state.svc, conference, favorites, prefs, ready=True)
        return ft.Column()

    async with rendering(Host) as session:
        monkeypatch.setattr(session.page, "navigate", state.went.append)
        yield state


def words(banner: ft.Banner) -> str:
    """The Banner's text, under its identifier."""
    content = banner.content
    assert isinstance(content, ft.Semantics)
    assert content.identifier == "reminder.banner"
    assert isinstance(content.content, ft.Text)
    return str(content.content.value)


def button(banner: ft.Banner, identifier: str) -> ft.TextButton:
    """The action `identifier` names, from its `named()` wrapping."""
    for action in banner.actions:
        assert isinstance(action, ft.MergeSemantics)
        node = action.content
        assert isinstance(node, ft.Semantics)
        if node.identifier == identifier:
            assert isinstance(node.content, ft.TextButton)
            return node.content
    raise AssertionError(identifier)


async def tap(banner: ft.Banner, identifier: str) -> None:
    """Call the action's click handler, as a tap does, and let it settle."""
    handler = button(banner, identifier).on_click
    assert callable(handler)
    handler()  # pyright: ignore[reportCallIssue]
    await settle()


async def test_it_shows_the_saved_session_and_its_minutes(shown: Shown) -> None:
    """9 min before a saved talk, the Banner names it, its minutes and its room."""
    banner = shown.banner
    assert banner is not None
    name = shown.conference.data.sessions[TALK].name  # pyright: ignore[reportOptionalMemberAccess]
    assert words(banner) == f"{name} starts in 9 min · Grand Ballroom A"
    assert [button(banner, f"reminder.{key}").content for key in ("dismiss", "open")]


async def test_open_lands_on_the_session_over_my_schedule_and_closes_it(
    shown: Shown,
) -> None:
    """Open navigates to the session's route and the Banner goes, not to come back."""
    banner = shown.banner
    assert banner is not None
    await tap(banner, "reminder.open")
    assert shown.went == [f"/my-schedule/session/{TALK}"]
    assert shown.banner is None
    shown.favorites.ids = frozenset({TALK})  # a change asks again: still dismissed
    await settle()
    assert shown.banner is None


async def test_dismiss_closes_it_until_restart(
    shown: Shown, held: Callable[[datetime], None]
) -> None:
    """Dismiss closes the Banner, and a later minute does not bring it back."""
    banner = shown.banner
    assert banner is not None
    await tap(banner, "reminder.dismiss")
    assert shown.banner is None
    assert shown.went == []
    held(TALK_START - timedelta(minutes=5))
    shown.favorites.ids = frozenset({TALK, "51"})
    await settle()
    assert shown.banner is not None  # "51" is due too, and was never dismissed
    other = shown.conference.data.sessions["51"].name  # pyright: ignore[reportOptionalMemberAccess]
    assert words(shown.banner).startswith(f"{other} starts in 5 min")


async def test_unsaving_the_session_closes_it_at_once(shown: Shown) -> None:
    """Removing the session from My schedule closes the Banner without a tick."""
    shown.favorites.ids = frozenset()
    await settle()
    assert shown.banner is None


async def test_the_minutes_follow_the_clock(
    shown: Shown, held: Callable[[datetime], None]
) -> None:
    """A minute later the same Banner says one minute less; at the start it goes."""
    held(TALK_START - timedelta(minutes=8))
    shown.conference.notify()  # pyright: ignore[reportAttributeAccessIssue]
    await settle()
    assert shown.banner is not None
    assert "starts in 8 min" in words(shown.banner)
    held(TALK_START)
    shown.conference.notify()  # pyright: ignore[reportAttributeAccessIssue]
    await settle()
    assert shown.banner is None


async def test_nothing_changes_in_the_background(
    shown: Shown, held: Callable[[datetime], None]
) -> None:
    """In the background a store change asks nothing; back in front, one does."""
    shown.svc.foreground.clear()  # the lifecycle handler's pause (D-40)
    held(TALK_START)
    shown.favorites.ids = frozenset({TALK, "51"})
    await settle()
    assert shown.banner is not None  # as it was when the app went away
    shown.svc.foreground.set()  # the resume (D-175)
    shown.favorites.ids = frozenset({TALK})
    await settle()
    assert shown.banner is None


# ------------------------------------------------------------------ the OS reminds (D-396)


@pytest.mark.parametrize(
    ("e3", "enabled", "lead", "reminds"),
    [
        (True, True, 10, True),  # the OS shows the reminder: no Banner
        (True, True, 5, True),
        (True, False, 10, False),  # notifications denied: the Banner stays
        (True, True, 0, False),  # session reminders off: the Banner stays
        (False, False, 10, False),  # no E3, as in the companion app (D-60)
    ],
)
def test_the_banner_gives_way_only_to_a_reminder_the_os_shows(
    e3: bool, enabled: bool, lead: SessionLead, reminds: bool
) -> None:
    """`os_reminds()`: E3 schedules, notifications show and session reminders are on."""
    scheduler = (
        Scheduler(cast(Notifications, MemoryNotifications()), enabled=enabled)
        if e3
        else None
    )
    assert os_reminds(scheduler, ReminderSettings(session_lead=lead)) is reminds


async def test_no_banner_while_the_os_reminds_and_back_once_it_does_not(
    shown: Shown,
) -> None:
    """Notifications allowed hide it at the next check; reminders turned off bring it back.

    A change of the settings asks again at once, as the favourites' and the feed's do.
    """
    assert shown.banner is not None  # notifications not (yet) shown: the interim
    await shown.scheduler.read_enabled()  # the fake OS shows them, as on a resume
    await settle()
    assert shown.banner is None
    shown.prefs.reminders = ReminderSettings(session_lead=0)
    await settle()
    assert shown.banner is not None


async def test_a_permission_read_alone_moves_the_banner_both_ways(shown: Shown) -> None:
    """A read that changes `Scheduler.enabled` asks again at once, no store changing.

    Back from system settings, the read on resume hides the Banner when notifications
    are allowed and brings it back when they are denied, without the minute tick.
    """
    os = cast(MemoryNotifications, shown.scheduler.notifications)
    await shown.scheduler.read_enabled()
    await settle()
    assert shown.banner is None
    os.enabled = False  # denied in system settings
    await shown.scheduler.read_enabled()
    await settle()
    assert shown.banner is not None
