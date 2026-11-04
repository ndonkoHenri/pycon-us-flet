"""Tests for Settings' Reminders section: live with E3, D-60's interim without (#429, #449).

`interim_section()` and `card_for()` are plain functions, run without a page. The
live `RemindersSection` runs in a real Flet session (`tests/harness.py`) over the
fakes of `tests/fakes.py`, beside `use_reminder_schedule()` as `App` calls it, so
each change shows how many plans it applied. How the section looks and reads is
checked on devices (the PR).
"""

import asyncio
import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet_notifications import NotificationException, Notifications
from flet_permission_handler import PermissionHandler, PermissionStatus

from pycon_us.change_log import use_change_log
from pycon_us.config import YearData, load_year
from pycon_us.favorites import use_favorites
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.reminder_schedule import use_reminder_schedule
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.screens.settings import RADIO_WIDTH
from pycon_us.screens.settings_reminders import (
    ASK_TEXT,
    BLOCKED_TEXT,
    EXACT_TEXT,
    NOT_AVAILABLE,
    REFUSED_TEXT,
    WITH_ALARM,
    RemindersSection,
    card_for,
    interim_section,
)
from pycon_us.services import Services, use_services
from pycon_us.services.pref_keys import REMINDERS, Pref
from pycon_us.services.reminders import Access, Scheduler
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, use_conference
from pycon_us.ui import focus_back
from tests import harness
from tests.fakes import MemoryNotifications, MemoryPermissions
from tests.feeds import processed
from tests.sessions import memory_services

# ------------------------------------------------------------------ the interim


def parts_of(
    section: ft.Control,
) -> tuple[ft.Semantics, ft.Semantics, ft.ListTile]:
    """Return the section's heading, its row's identifier node and the row's tile."""
    assert isinstance(section, ft.Column)
    heading, row = section.controls
    assert isinstance(heading, ft.Semantics)
    assert isinstance(row, ft.MergeSemantics)  # one node, read as its words (D-214)
    node = row.content
    assert isinstance(node, ft.Semantics)
    assert isinstance(node.content, ft.ListTile)
    return heading, node, node.content


def test_the_interim_is_a_level_2_reminders_heading_over_one_named_row() -> None:
    """The section is a level-2 "Reminders" heading and one row, `settings.reminders.interim`."""
    heading, node, _ = parts_of(interim_section(ft.PagePlatform.IOS, slot=RADIO_WIDTH))
    assert heading.header and heading.heading_level == 2  # a section (D-211)
    assert isinstance(heading.content, ft.Container)
    assert isinstance(heading.content.content, ft.Text)
    assert heading.content.content.value == "Reminders"
    assert node.identifier == "settings.reminders.interim"


def test_the_interim_row_has_no_control_that_does_nothing() -> None:
    """No switch, no button, no tap: there is nothing to change in this build (D-60)."""
    _, _, tile = parts_of(interim_section(ft.PagePlatform.ANDROID, slot=RADIO_WIDTH))
    assert tile.trailing is None
    assert tile.on_click is None and not tile.toggle_inputs
    slot = tile.leading
    assert isinstance(slot, ft.Container)
    assert slot.width == RADIO_WIDTH  # its words start where Appearance's titles do
    assert isinstance(slot.content, ft.Icon)
    assert slot.content.icon == ft.Icons.NOTIFICATIONS_OFF_OUTLINED
    assert slot.content.semantics_label is None  # decorative: the words say it


@pytest.mark.parametrize(
    ("platform", "text"),
    [
        (ft.PagePlatform.IOS, WITH_ALARM),
        (ft.PagePlatform.ANDROID, NOT_AVAILABLE),
        (None, NOT_AVAILABLE),
    ],
)
def test_only_ios_promises_the_calendar_alarm(
    platform: ft.PagePlatform | None, text: str
) -> None:
    """On iOS the sentence mentions the export's alarm; Android's import drops it (D-272)."""
    _, _, tile = parts_of(interim_section(platform, slot=RADIO_WIDTH))
    assert tile.title == text


def test_the_sentences_say_what_ux_9_says() -> None:
    """The copy is ux.md §6.9's, word for word, on each platform."""
    assert NOT_AVAILABLE == (
        "Reminders aren't available in this build. Your next session appears on Now."
    )
    assert WITH_ALARM == (
        "Reminders aren't available in this build. Your next session appears on Now, "
        "and calendar exports include an alarm."
    )
    assert EXACT_TEXT == (  # D-221's honest wording
        "For more timely reminders, allow Alarms & reminders. Without this "
        "permission, reminders may arrive late, including after a session starts."
    )


# ------------------------------------------------------------------ which card


ON = ReminderSettings(session_lead=10, primer="accepted")
"""Session reminders on at 10 min after the primer's Allow, the moments on."""

ALL_OFF = ReminderSettings(lightning=False, open_space=False, keynote=False)
"""Nothing on: no reminder needs notifications."""


@pytest.mark.parametrize(
    ("access", "settings", "android", "exact", "card"),
    [
        ("askable", ReminderSettings(), True, None, "ask"),  # the moments default on
        ("askable", ReminderSettings(), False, None, "ask"),
        ("askable", ALL_OFF, True, None, None),  # nothing to allow
        ("askable", ON, True, True, "ask"),  # Android may ask again after one no
        ("askable", ON, False, True, "blocked"),  # iOS asks once (F245)
        ("refused", ON, True, True, "refused"),  # Android may still ask (F259)
        ("blocked", ON, True, True, "blocked"),
        ("blocked", ReminderSettings(), False, True, "blocked"),
        ("allowed", ON, True, False, "exact"),
        ("allowed", ON, True, True, None),
        ("allowed", ON, True, None, None),  # not read yet
        ("allowed", ON, False, False, None),  # iOS has no such setting
        ("allowed", ReminderSettings(), True, False, None),  # sessions off
        ("unknown", ON, True, False, None),  # §4.8: as unavailable
        (None, ON, True, False, None),  # not read yet
    ],
)
def test_the_card_follows_the_oss_answers(
    access: Access | None,
    settings: ReminderSettings,
    android: bool,
    exact: bool | None,
    card: str | None,
) -> None:
    """Each permission state shows its card, and the exact one only on Android (D-221)."""
    assert card_for(access, settings, android=android, exact=exact) == card


# ------------------------------------------------------------------ live


@ft.component
def Planned() -> ft.Control:
    """The section, with the reminders kept applied as `App` keeps them (D-389)."""
    use_reminder_schedule(
        use_services(), use_conference(), use_favorites(), use_change_log(), use_prefs()
    )
    return RemindersSection(RADIO_WIDTH)


type Open = Callable[..., Awaitable[harness.Shown]]


@pytest.fixture
def os() -> MemoryNotifications:
    """The OS: notifications allowed, exact alarms allowed, every call succeeding."""
    return MemoryNotifications()


@pytest.fixture
async def open_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, os: MemoryNotifications
) -> AsyncIterator[Open]:
    """Provide `open_section(settings, android=, permissions=)`: the live section."""
    async with AsyncExitStack() as stack:

        async def open_(
            settings: ReminderSettings = ON,
            *,
            android: bool = False,
            permissions: MemoryPermissions | None = None,
        ) -> harness.Shown:
            def with_e3(
                year: YearData, directory: Path, memory: object = None
            ) -> Services:
                svc = memory_services(year, directory)
                scheduler = Scheduler(
                    cast(Notifications, os),
                    cast(PermissionHandler | None, permissions),
                    android=android,
                )
                return dataclasses.replace(
                    svc,
                    reminders=scheduler,
                    permissions=cast(PermissionHandler | None, permissions),
                )

            monkeypatch.setattr(harness, "memory_services", with_e3)
            prefs = Prefs(loaded=True)
            prefs.reminders = settings
            return await stack.enter_async_context(
                harness.showing(
                    Planned,
                    year=load_year(2026),
                    conference=Conference(
                        data=processed(2026), source="bundled", version=1
                    ),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="/more/settings",
                    prefs=prefs,
                )
            )

        yield open_


def tile_of(shown: harness.Shown, identifier: str) -> ft.ListTile:
    """The switch row's tile under `identifier`."""
    tile = shown.node(identifier).content
    assert isinstance(tile, ft.ListTile)
    return tile


def switch_of(shown: harness.Shown, identifier: str) -> ft.Switch:
    """The switch of the row `identifier`."""
    switch = tile_of(shown, identifier).trailing
    assert isinstance(switch, ft.Switch)
    return switch


async def toggle(shown: harness.Shown, identifier: str) -> None:
    """Toggle a row's switch as Flutter reports it: the new value, then the event."""
    switch = switch_of(shown, identifier)
    value: Any = not switch.value
    shown.session.apply_patch(switch._i, {"value": value})
    await shown.event(switch, "change", None)


async def pick_lead(shown: harness.Shown, minutes: int) -> None:
    """Pick a lead on the segmented button, as Flutter reports it."""
    (picker,) = shown.find(ft.SegmentedButton)
    shown.session.apply_patch(picker._i, {"selected": [str(minutes)]})
    await shown.event(picker, "change", [str(minutes)])


def button(shown: harness.Shown, card: str) -> ft.OutlinedButton:
    """The button of the card `card`, under `<card>.action`."""
    found = shown.node(f"{card}.action").content
    assert isinstance(found, ft.OutlinedButton)
    return found


def applies(os: MemoryNotifications) -> int:
    """How many plans the scheduler applied: each one starts with a cancel."""
    return os.calls.count("cancel_all_pending")


async def stored(shown: harness.Shown) -> ReminderSettings:
    """The reminder settings as written to storage, as a relaunch reads them."""
    return ReminderSettings.from_stored(await shown.storage.get(REMINDERS))


def card_text(shown: harness.Shown) -> str | None:
    """The card's sentence, or None when no card shows."""
    for kind in ("allow", "refused", "blocked", "exact"):
        if shown.nodes(f"settings.reminders.{kind}"):
            text = shown.node(f"settings.reminders.{kind}").content
            assert isinstance(text, ft.Text)
            return str(text.value)
    return None


async def test_the_section_shows_the_switch_its_lead_and_the_moments(
    open_section: Open,
) -> None:
    """The session switch, its lead only while on, and three moment switches (§6.9)."""
    shown = await open_section(ReminderSettings())
    assert not switch_of(shown, "settings.reminders.sessions").value
    assert not shown.find(ft.SegmentedButton)  # only while on
    for field in ("keynote", "lightning", "open_space"):
        assert switch_of(shown, f"settings.reminders.{field}").value
        assert tile_of(shown, f"settings.reminders.{field}").toggle_inputs
    assert tile_of(shown, "settings.reminders.sessions").toggle_inputs
    assert card_text(shown) is None  # the OS allows them


async def test_each_change_saves_and_re_plans_once(
    open_section: Open, os: MemoryNotifications
) -> None:
    """On, the lead and a moment off each apply one plan, and survive a relaunch."""
    shown = await open_section(ReminderSettings(primer="accepted"))
    start = applies(os)
    assert start == 1  # the start's apply
    await toggle(shown, "settings.reminders.sessions")
    assert applies(os) == start + 1
    assert (await stored(shown)).session_lead == 10
    (picker,) = shown.find(ft.SegmentedButton)
    assert picker.selected == ["10"]
    await pick_lead(shown, 15)
    assert applies(os) == start + 2
    await toggle(shown, "settings.reminders.keynote")
    assert applies(os) == start + 3
    assert await stored(shown) == ReminderSettings(
        session_lead=15, keynote=False, primer="accepted"
    )
    assert not shown.snack_bars  # silently (§6.9)
    await toggle(shown, "settings.reminders.sessions")
    assert (await stored(shown)).session_lead == 0
    assert not shown.find(ft.SegmentedButton)


async def test_the_first_switch_shows_the_primer_while_unanswered(
    open_section: Open, os: MemoryNotifications
) -> None:
    """Never answered and the OS may ask: the switch saves 10 min, then the primer."""
    os.enabled = False
    shown = await open_section(ReminderSettings())
    await toggle(shown, "settings.reminders.sessions")
    sheets = [
        d
        for d in shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
        if isinstance(d, ft.BottomSheet)
    ]
    assert len(sheets) == 1 and sheets[0].open
    assert (await stored(shown)).session_lead == 10


async def test_an_askable_os_shows_allow_notifications(
    open_section: Open, os: MemoryNotifications
) -> None:
    """Notifications not allowed yet: "Allow notifications" asks, and its card goes."""
    os.enabled = False
    shown = await open_section(ReminderSettings())
    assert card_text(shown) == ASK_TEXT
    await shown.click(button(shown, "settings.reminders.allow"))
    assert os.calls.count("request_permissions") == 1
    assert card_text(shown) is None
    assert (await stored(shown)).primer == "accepted"  # no primer after this


async def test_a_refusal_ios_wont_ask_again_sends_to_settings(
    open_section: Open, os: MemoryNotifications
) -> None:
    """Refused once on iOS: "Notifications are off in system settings.", Open settings."""
    os.enabled = False
    permissions = MemoryPermissions(PermissionStatus.DENIED)
    shown = await open_section(ON, permissions=permissions)
    assert card_text(shown) == BLOCKED_TEXT
    await shown.click(button(shown, "settings.reminders.blocked"))
    assert permissions.settings_opened == 1


async def test_android_blocked_sends_to_settings(open_section: Open) -> None:
    """Android's permanent denial: the blocked card with Open settings."""
    permissions = MemoryPermissions(PermissionStatus.PERMANENTLY_DENIED)
    shown = await open_section(ON, android=True, permissions=permissions)
    assert card_text(shown) == BLOCKED_TEXT


@pytest.mark.parametrize(
    ("settings", "card"),
    [
        (ON, REFUSED_TEXT),  # asked before: Android may have answered without a prompt
        (ReminderSettings(), ASK_TEXT),  # the first refusal: Android asks twice
    ],
)
async def test_android_refusing_a_request_again_offers_settings(
    open_section: Open,
    os: MemoryNotifications,
    settings: ReminderSettings,
    card: str,
) -> None:
    """Off in system settings, the status stays denied: a later refusal offers settings.

    Turned on there, the resume's read hides the card (#712, F259).
    """
    os.enabled = os.grant = False
    permissions = MemoryPermissions(PermissionStatus.DENIED)
    shown = await open_section(settings, android=True, permissions=permissions)
    assert card_text(shown) == ASK_TEXT
    await shown.click(button(shown, "settings.reminders.allow"))
    assert card_text(shown) == card
    os.enabled, permissions.status = True, PermissionStatus.GRANTED
    scheduler = shown.services.reminders
    assert scheduler is not None
    scheduler.request()  # what app.on_resume() asks
    await shown.settle()
    assert card_text(shown) is None


async def test_allowing_alarms_and_reminders_hides_its_card(
    open_section: Open, os: MemoryNotifications
) -> None:
    """Exact alarms not allowed: the card; its Open settings allowed them: it goes."""
    os.exact = False
    permissions = MemoryPermissions(PermissionStatus.GRANTED)
    shown = await open_section(ON, android=True, permissions=permissions)
    assert card_text(shown) == EXACT_TEXT
    before = applies(os)
    await shown.click(button(shown, "settings.reminders.exact"))
    assert os.calls.count("request_exact_alarm_permission") == 1
    assert card_text(shown) is None
    assert applies(os) == before + 1  # applied again, exact now


async def test_a_change_seen_on_resume_updates_the_card(
    open_section: Open, os: MemoryNotifications
) -> None:
    """Exact alarms allowed in system settings: the resume's apply hides the card."""
    os.exact = False
    permissions = MemoryPermissions(PermissionStatus.GRANTED)
    shown = await open_section(ON, android=True, permissions=permissions)
    assert card_text(shown) == EXACT_TEXT
    os.exact = True
    scheduler = shown.services.reminders
    assert scheduler is not None
    scheduler.request()  # what app.on_resume() asks
    await shown.settle()
    assert card_text(shown) is None


async def test_ios_never_shows_the_exact_alarm_card(
    open_section: Open, os: MemoryNotifications
) -> None:
    """No Alarms & reminders card on iOS, whatever the plugin says (D-221)."""
    os.exact = False
    shown = await open_section(ON)
    assert card_text(shown) is None


async def test_overlapping_switches_each_keep_the_others_change(
    open_section: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two moments switched off before the first write ends both stay off (#706's review).

    The first write is held until the second tap's handler has started, so the two
    overlap by construction: built from the same record, the later save restored the
    first.
    """
    shown = await open_section(ReminderSettings(primer="accepted"))
    write = Storage.set
    change = Prefs.change_reminders
    first_write_begun, both_taps_begun, written = (asyncio.Event() for _ in range(3))
    started = ended = 0

    async def counted(
        self: Prefs,
        storage: Storage,
        change_to: Callable[[ReminderSettings], ReminderSettings],
    ) -> bool:
        nonlocal started
        started += 1
        if started == 2:
            both_taps_begun.set()
        return await change(self, storage, change_to)

    async def held_set(self: Storage, pref: Pref[Any], value: Any) -> bool:
        nonlocal ended
        if pref is REMINDERS:
            first_write_begun.set()
            await both_taps_begun.wait()  # neither write ends before both taps began
        saved = await write(self, pref, value)
        if pref is REMINDERS:
            ended += 1
            if ended == 2:
                written.set()
        return saved

    monkeypatch.setattr(Prefs, "change_reminders", counted)
    monkeypatch.setattr(Storage, "set", held_set)
    first = asyncio.create_task(toggle(shown, "settings.reminders.keynote"))
    await asyncio.wait_for(first_write_begun.wait(), 5)
    assert not both_taps_begun.is_set()  # the first write is in flight, alone
    second = asyncio.create_task(toggle(shown, "settings.reminders.lightning"))
    await asyncio.wait_for(asyncio.gather(first, second, written.wait()), 5)
    await shown.settle()
    assert (
        started == 2
    )  # the second tap's change began while the first's write was held
    expected = ReminderSettings(keynote=False, lightning=False, primer="accepted")
    assert await stored(shown) == expected
    assert shown.prefs.reminders == expected
    assert not switch_of(shown, "settings.reminders.keynote").value
    assert not switch_of(shown, "settings.reminders.lightning").value


@pytest.mark.parametrize("card", ["blocked", "exact"])
async def test_back_from_system_settings_the_button_gets_the_focus(
    open_section: Open,
    os: MemoryNotifications,
    monkeypatch: pytest.MonkeyPatch,
    card: str,
) -> None:
    """Back from system settings with nothing changed, its button is focused (D-372)."""
    monkeypatch.setattr(focus_back, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(focus_back, "LEAVE_WITHIN", 1)  # the trip below leaves
    focused: list[ft.OutlinedButton] = []

    async def focus(self: ft.OutlinedButton) -> None:
        focused.append(self)

    monkeypatch.setattr(ft.OutlinedButton, "focus", focus)
    if card == "blocked":
        os.enabled = False
        status = PermissionStatus.PERMANENTLY_DENIED
    else:
        os.exact = os.grant_exact = False  # left without allowing them
        status = PermissionStatus.GRANTED
    permissions = MemoryPermissions(status)
    gate = asyncio.Event()
    # Both cards open another app's window: the OS's settings page, or Alarms & reminders.
    if card == "blocked":
        permissions.settings_gate = gate
    else:
        os.settings_gate = gate
    shown = await open_section(ON, android=True, permissions=permissions)
    click = asyncio.create_task(
        shown.click(button(shown, f"settings.reminders.{card}"))
    )
    await shown.settle()
    opened = (
        permissions.settings_opened
        if card == "blocked"
        else os.calls.count("request_exact_alarm_permission")
    )
    assert opened == 1  # the settings page is up
    shown.services.presence.leave()  # Android: the app goes under the settings page
    gate.set()  # the user leaves the page
    await shown.settle()
    assert focused == []  # nothing is focused while the app is under the page
    shown.services.presence.come_back()
    await click
    await shown.settle()
    assert focused == [button(shown, f"settings.reminders.{card}")]


def test_the_calendar_alarm_follows_the_lead() -> None:
    """The .ics alarm is the lead while session reminders are on, else 10 min (D-401)."""
    assert ReminderSettings().calendar_alarm.total_seconds() == 600
    assert ReminderSettings(session_lead=5).calendar_alarm.total_seconds() == 300
    assert ReminderSettings(session_lead=15).calendar_alarm.total_seconds() == 900


async def test_a_first_real_refusal_after_a_failed_request_still_offers_allow(
    open_section: Open, os: MemoryNotifications
) -> None:
    """After a failed request then a first refusal, Allow stays beside Open settings.

    The failed request recorded the ask but showed no prompt, so the OS may still ask
    (#716's review).
    """
    os.errors["request_permissions"] = NotificationException("operation_failed")
    os.enabled = os.grant = False
    permissions = MemoryPermissions(PermissionStatus.DENIED)
    shown = await open_section(
        ReminderSettings(), android=True, permissions=permissions
    )
    await shown.click(button(shown, "settings.reminders.allow"))  # fails, no prompt
    assert (await stored(shown)).primer == "accepted"
    del os.errors["request_permissions"]
    await shown.click(button(shown, "settings.reminders.allow"))  # the first "no"
    assert card_text(shown) == REFUSED_TEXT
    assert shown.nodes("settings.reminders.refused.settings")
    os.grant, permissions.status = True, PermissionStatus.GRANTED  # Android asks again
    await shown.click(button(shown, "settings.reminders.refused"))
    assert card_text(shown) is None
