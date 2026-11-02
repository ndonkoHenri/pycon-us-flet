"""Tests for what reaches staff who are not looking at the scan screen (#724, D-420).

``ui/scan_feedback.py``'s haptics, announcements and wake lock, and the scan screen's
sync chip, queue sheet and pauses (``ui/scan_screen.py``), in a real Flet session
(``tests/scan_rig.py``) with the memory fakes of ``tests/fakes.py``. The pulses felt,
the words spoken and the screen kept on are checked on devices (the PR).
"""

import asyncio
from typing import cast

import flet as ft
import pytest

from pycon_us.core.badges import NOT_A_BADGE, ScanOutcome, ScanResult
from pycon_us.prefs import Prefs
from pycon_us.staff import Staff
from pycon_us.ui import scan_feedback
from pycon_us.ui import semantics as ui_semantics
from pycon_us.ui.scan_screen import PAUSED_SHEET, ScanScreen
from tests import harness, scan_rig
from tests.fakes import MemoryHaptics, MemorySemantics, MemoryWakelock
from tests.scan_rig import ACCEPTED, Rig, Show, enter, entry, panel
from tests.trees import descendants

rig, show = scan_rig.rig, scan_rig.show

ANNOUNCING = Prefs(loaded=True, announcements=True)
"""iOS's flags: the platform takes announcements (F13)."""


def haptics(shown: harness.Shown) -> list[str]:
    """The haptic effects the screen asked for, by method name, in order."""
    return cast(MemoryHaptics, shown.services.haptics).effects


def semantics(shown: harness.Shown) -> MemorySemantics:
    """The semantics service that records each announcement and its level."""
    return cast(MemorySemantics, shown.services.semantics)


def wakelock(shown: harness.Shown) -> MemoryWakelock:
    """The wake lock that records each call and holds its state."""
    return cast(MemoryWakelock, shown.services.wakelock)


async def click_node(shown: harness.Shown, identifier: str) -> None:
    """Click the control that the ``Semantics`` with ``identifier`` wraps."""
    content = shown.node(identifier).content
    assert content is not None
    await shown.click(content)


def sheet(shown: harness.Shown) -> ft.BottomSheet | None:
    """The open queue sheet, or None."""
    dialogs = shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.BottomSheet) and d.open]
    return found[0] if found else None


async def close_sheet(shown: harness.Shown) -> None:
    """Tap the open sheet's Close button (``staff.queue.close``)."""
    current = sheet(shown)
    assert current is not None
    (close,) = [
        c
        for c in descendants(current)
        if isinstance(c, ft.IconButton) and c.tooltip == "Close"
    ]
    await shown.click(close)


@pytest.mark.parametrize(
    ("outcome", "effects"),
    [
        (ScanOutcome.ACCEPTED, ["light_impact"]),
        (ScanOutcome.DUPLICATE, ["medium_impact", "medium_impact"]),
        (ScanOutcome.DENIED, ["heavy_impact", "vibrate"]),
        (ScanOutcome.QUEUED, ["light_impact"]),
        (ScanOutcome.RECORDED, ["light_impact"]),
        (ScanOutcome.NOT_RECORDED, []),
    ],
)
async def test_each_outcome_gives_its_haptics(
    show: Show, rig: Rig, outcome: ScanOutcome, effects: list[str]
) -> None:
    """ux.md §7.2's column: light, medium twice, heavy then vibrate, light, light, none.

    The last two are CoC's incident recorded and not recorded (#760).
    """
    rig.result = ScanResult(outcome, "Word")
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    assert haptics(shown) == effects


async def test_a_submit_during_a_result_s_feedback_is_dropped(
    show: Show, rig: Rig
) -> None:
    """One scan at a time until its result is felt: no denial lands after the next."""
    rig.result = ScanResult(ScanOutcome.DENIED, "Denied")
    shown = await show()
    pulses = cast(MemoryHaptics, shown.services.haptics)
    pulses.gate = asyncio.Event()
    first = asyncio.create_task(enter(shown, "MOCK0001:v1"))
    while not pulses.effects:  # the denial's first pulse is under way
        await asyncio.sleep(0)
    await shown.settle()
    rig.result = ACCEPTED
    await asyncio.wait_for(enter(shown, "MOCK0002:v2"), timeout=5)
    assert [badge.code for badge in rig.badges] == ["MOCK0001"]
    assert entry(shown).value == "MOCK0002:v2"  # kept, to submit again
    pulses.gate.set()
    await first
    assert pulses.effects == ["heavy_impact", "vibrate"]


async def test_a_code_that_is_not_a_badge_gives_no_haptics(show: Show) -> None:
    """Junk is shown and said, never buzzed: nothing happened to a badge."""
    shown = await show()
    await enter(shown, "MOCK0001")
    assert haptics(shown) == []
    assert NOT_A_BADGE.word in panel(shown)


async def test_a_failed_pulse_is_logged_and_the_result_still_shows(
    show: Show, caplog: pytest.LogCaptureFixture
) -> None:
    """A haptics error stops the pulses only: the panel has the result."""
    shown = await show()
    cast(MemoryHaptics, shown.services.haptics).error = RuntimeError("no motor")
    await enter(shown, "MOCK0001:v1")
    assert panel(shown).startswith("Checked in")
    assert "Haptic feedback failed" in caplog.text
    assert not shown.snack_bars


async def test_without_announcements_the_live_region_alone_says_it(
    show: Show,
) -> None:
    """Android: nothing is announced; the panel stays a live region (``panel()``)."""
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    assert semantics(shown).announced == []
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 1"


@pytest.mark.parametrize(
    ("outcome", "level"),
    [
        (ScanOutcome.ACCEPTED, ft.Assertiveness.POLITE),
        (ScanOutcome.QUEUED, ft.Assertiveness.POLITE),
        (ScanOutcome.RECORDED, ft.Assertiveness.POLITE),
        (ScanOutcome.DUPLICATE, ft.Assertiveness.ASSERTIVE),
        (ScanOutcome.DENIED, ft.Assertiveness.ASSERTIVE),
    ],
)
async def test_with_announcements_a_result_is_announced_once_at_its_level(
    show: Show, rig: Rig, outcome: ScanOutcome, level: ft.Assertiveness
) -> None:
    """iOS: the result's words are announced, and the panel is no live region."""
    rig.result = ScanResult(outcome, "Word", "Name")
    shown = await show(prefs=ANNOUNCING)
    await enter(shown, "MOCK0001:v1")
    assert semantics(shown).announced == ["Word\nName"]
    assert semantics(shown).levels == [level]
    assert not shown.node("scan.result").live_region  # else it were said twice


async def test_an_announcement_never_answered_doesn_t_stop_the_next_scan(
    show: Show, rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An announcement iOS never answers (VoiceOver on, F276) stops no scan."""
    monkeypatch.setattr(ui_semantics, "ANNOUNCE_WAIT_S", 0.01)
    shown = await show(prefs=ANNOUNCING)
    semantics(shown).answers = False
    await enter(shown, "MOCK0001:v1")
    await enter(shown, "MOCK0002:v2")
    assert [badge.code for badge in rig.badges] == ["MOCK0001", "MOCK0002"]
    assert len(semantics(shown).announced) == 2


async def test_the_wake_lock_is_held_while_mounted_and_in_the_foreground(
    show: Show,
) -> None:
    """Taken on mount, let go in the background, taken again on the resume."""
    shown = await show()
    lock = wakelock(shown)
    assert lock.calls == ["enable"] and lock.enabled
    shown.services.foreground.clear()  # what the lifecycle handler does on pause
    shown.services.background.set()
    await shown.settle()
    assert lock.calls[-1] == "disable" and not lock.enabled
    shown.services.background.clear()  # and on the resume
    shown.services.foreground.set()
    await shown.settle()
    assert lock.calls == ["enable", "disable", "enable"] and lock.enabled


async def test_leaving_the_scan_screen_lets_the_screen_sleep(
    show: Show, rig: Rig
) -> None:
    """Unmounted, the screen gives the wake lock back (its effect's cleanup)."""

    @ft.component
    def Host() -> ft.Control:
        scanning, set_scanning = ft.use_state(True)
        leave = ft.TextButton("Leave", on_click=lambda: set_scanning(False))
        if not scanning:
            return ft.Text("Left")
        return ft.Column(
            [
                ScanScreen(
                    title="Lead scanner", source=__name__, on_badge=rig.on_badge
                ),
                leave,
            ]
        )

    shown = await show(Host)
    lock = wakelock(shown)
    assert lock.enabled
    (leave,) = shown.find(ft.TextButton)
    await shown.click(leave)
    assert "Left" in shown.texts()
    assert lock.calls == ["enable", "disable"] and not lock.enabled


async def test_a_failed_wake_lock_is_logged_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The screen may dim, but a refused wake lock is no error for the screen."""
    lock = MemoryWakelock()
    lock.error = RuntimeError("refused")
    await scan_feedback.set_awake(lock, on=True)
    await scan_feedback.set_awake(lock, on=False)
    assert "Could not take the wake lock" in caplog.text
    assert "Could not release the wake lock" in caplog.text


async def test_the_app_bar_s_chip_says_the_queue(show: Show) -> None:
    """The sync chip is in the bar, in Developer's words (D-412)."""
    shown = await show(staff=Staff(pending=3))
    chip = shown.node("staff.sync_chip").content
    assert isinstance(chip, ft.Chip)
    assert isinstance(chip.label, ft.Text) and chip.label.value == "3 pending"


async def test_at_large_text_the_chip_heads_the_body_and_wraps(show: Show) -> None:
    """At large text the chip heads the body, its words free to wrap (#752).

    A ``Chip`` kept one line and clipped "All synced"; the chip still opens the sheet.
    """
    shown = await show(
        prefs=Prefs(loaded=True, time_above=True), staff=Staff(pending=3)
    )
    node = shown.node("staff.sync_chip")
    (body,) = shown.find(ft.ListView)
    assert node in descendants(body)
    assert (node.label, node.button) == ("3 pending", True)
    assert not [c for c in descendants(node) if isinstance(c, ft.Chip)]
    (words,) = [c for c in descendants(node) if isinstance(c, ft.Text)]
    assert (words.value, words.expand_loose) == ("3 pending", True)
    (tap,) = [
        c
        for c in shown.find(ft.Container)
        if c.on_click is not None and node in descendants(c)
    ]
    await shown.click(tap)
    assert sheet(shown) is not None


async def test_the_queue_sheet_pauses_scanning_and_gives_the_focus_back(
    show: Show, rig: Rig
) -> None:
    """While the sheet is open a code is dropped, kept and the field says why."""
    shown = await show(staff=Staff(pending=3))
    await click_node(shown, "staff.sync_chip")
    assert sheet(shown) is not None
    assert entry(shown).helper == PAUSED_SHEET
    await enter(shown, "MOCK0001:v1")
    assert rig.badges == []
    assert entry(shown).value == "MOCK0001:v1"
    focused = rig.focused
    await close_sheet(shown)
    assert sheet(shown) is None
    assert entry(shown).helper is None
    assert rig.focused == focused + 1  # back in the field, ready for the next code
    await enter(shown, "MOCK0001:v1")
    assert [badge.code for badge in rig.badges] == ["MOCK0001"]


async def test_the_tool_s_pause_shows_its_reason(show: Show, rig: Rig) -> None:
    """A tool's dialog pauses scanning with its own words under the field."""
    rig.paused = "Paused while the note is open"
    shown = await show()
    assert entry(shown).helper == "Paused while the note is open"
