"""Tests for the shared scan screen, ``ui/scan_screen.py`` (LEAD-01, LEAD-09; D-65, #723).

The screen runs in a real Flet session around a recording handler (``tests/scan_rig.py``).
Its haptics, announcements, wake lock, sync chip and pauses are
``tests/test_scan_feedback.py``'s. How it looks, a HID scanner's typing and the screen
readers are checked on devices (the PR).
"""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from itertools import product
from typing import cast

import flet as ft
import pytest

from pycon_us import capabilities
from pycon_us.account import Account
from pycon_us.core.badges import (
    NOT_A_BADGE,
    Badge,
    ScanOutcome,
    ScanResult,
)
from pycon_us.core.staff_tools import ToolKey
from pycon_us.core.timefmt import seconds_ago
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.prefs import Prefs
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import scan_screen
from pycon_us.ui.scan_camera import CAMERA_UNAVAILABLE
from pycon_us.ui.scan_result import (
    DIM_AFTER,
    FILLS,
    HC_FILLS,
    ICONS,
    READY,
    Shown,
    fill_of,
    spoken,
)
from pycon_us.ui.scan_screen import EDIT_CODE, SCAN_AGAIN, ResultPanel, ScanScreen
from pycon_us.ui.scrolling import FULL_LIST_EXTENT
from tests import scan_rig
from tests.scan_rig import ACCEPTED, Rig, Show, enter, entry, panel, scan
from tests.test_high_contrast import AAA_TEXT
from tests.test_theme import AA_TEXT, contrast_ratio

rig, show = scan_rig.rig, scan_rig.show


async def test_the_interim_camera_text_shows_while_the_build_has_no_scanner(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without E1 the camera area says so, manual entry is ready, the panel waits."""
    monkeypatch.setattr(capabilities, "SCANNER", False)
    shown = await show()
    assert shown.nodes("scan.camera_unavailable")
    assert CAMERA_UNAVAILABLE in shown.texts()
    field = entry(shown)
    assert field.label == "Badge code" and field.autofocus
    assert panel(shown) == spoken(None) and READY in panel(shown)
    assert shown.nodes("scan.entry") and shown.nodes("scan.keyboard")


async def test_with_a_scanner_the_interim_text_is_gone(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With E1 bundled the interim gives way (#726 brings the preview there)."""
    monkeypatch.setattr(capabilities, "SCANNER", True)
    shown = await show()
    assert not shown.nodes("scan.camera_unavailable")


async def test_a_badge_shows_its_result_and_leaves_the_field_empty_and_focused(
    show: Show, rig: Rig
) -> None:
    """Enter parses, awaits the handler, shows its words, clears and refocuses."""
    shown = await show()
    await enter(shown, "MOCK0001:v4l1d01\n")
    assert rig.badges == [Badge("MOCK0001", "v4l1d01", "v4l1d01")]
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 1"
    assert entry(shown).value == ""
    assert rig.focused == 1
    assert f"Read {seconds_ago(0)}" in shown.texts()


async def test_the_field_asks_for_the_key_that_keeps_android_s_focus(
    show: Show,
) -> None:
    """``UNSPECIFIED`` keeps Android's keyboard up across submits (F274, #830)."""
    shown = await show()
    assert entry(shown).text_input_action == ft.TextInputAction.UNSPECIFIED


async def test_the_same_code_within_the_cooldown_changes_nothing(
    show: Show, rig: Rig
) -> None:
    """A held code is cleared without a word for 4 s; then it counts again."""
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    rig.result = ScanResult(ScanOutcome.DUPLICATE, "Already checked in")
    rig.now += 3.9
    await enter(shown, "MOCK0001:v1")
    assert len(rig.badges) == 1
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 1"
    assert entry(shown).value == ""
    rig.now += 0.2
    await enter(shown, "MOCK0001:v1")
    assert len(rig.badges) == 2
    assert panel(shown) == "Already checked in\nScan 2"


async def test_the_same_result_again_changes_what_the_live_region_says(
    show: Show, rig: Rig
) -> None:
    """An equal result is said again: its count changes the live region's label."""
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    first = panel(shown)
    rig.now += 4.1  # past the cooldown; the handler answers the same
    await enter(shown, "MOCK0001:v1")
    assert len(rig.badges) == 2
    assert first == "Checked in\nAda Lovelace\nScan 1"
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 2"
    assert "Read" not in panel(shown)  # the ticking age stays outside it


async def test_a_different_code_shows_at_once(show: Show, rig: Rig) -> None:
    """The cooldown is per code: another badge right after is handled."""
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    rig.result = ScanResult(ScanOutcome.ACCEPTED, "Checked in", "Grace Hopper")
    await enter(shown, "MOCK0002:v2")
    assert [b.code for b in rig.badges] == ["MOCK0001", "MOCK0002"]
    assert panel(shown) == "Checked in\nGrace Hopper\nScan 2"


async def test_junk_says_not_a_badge_code_with_the_text_and_clears_the_field(
    show: Show, rig: Rig
) -> None:
    """Text without a code is no badge: the panel shows what was read, the field is empty."""
    shown = await show()
    await enter(shown, "MOCK0001")
    assert rig.badges == []
    assert panel(shown) == f"{replace(NOT_A_BADGE, title='MOCK0001').spoken}\nScan 1"
    assert entry(shown).value == ""
    assert rig.focused == 1  # Enter took the focus; it is back for the next scan


async def test_a_scan_after_not_a_badge_code_is_read_alone(
    show: Show, rig: Rig
) -> None:
    """The next HID scan is its own badge, not typed after the text refused (#941, D-473)."""
    shown = await show()
    await scan(shown, "NOCOLON")
    await scan(shown, "MOCK0005:v4l1d05")
    assert rig.badges == [Badge("MOCK0005", "v4l1d05", "v4l1d05")]
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 2"


async def test_edit_code_gives_the_text_back_to_correct_by_hand(
    show: Show, rig: Rig
) -> None:
    """A typist taps "Edit code": the text is in the field to fix, and the panel is clear."""
    shown = await show()
    await enter(shown, "MOCK0005v4l1d05")  # the colon forgotten
    button = shown.node("scan.edit").content
    assert isinstance(button, ft.FilledTonalButton)
    assert button.content == EDIT_CODE
    focused = rig.focused
    await shown.click(button)
    await shown.settle()
    assert entry(shown).value == "MOCK0005v4l1d05"
    assert rig.focused == focused + 1  # the caret is after the text, ready to fix it
    assert panel(shown) == spoken(None)  # the result is gone with its button
    assert not shown.nodes("scan.edit")
    assert rig.badges == []
    await enter(shown, "MOCK0005:v4l1d05")  # the typist's fix, submitted as typed
    assert rig.badges == [Badge("MOCK0005", "v4l1d05", "v4l1d05")]


@pytest.mark.parametrize("text", ["", "   "])
async def test_an_empty_entry_has_nothing_to_edit(
    show: Show, rig: Rig, text: str
) -> None:
    """An empty entry's "Not a badge code" has no text to give back: no button."""
    shown = await show()
    await enter(shown, text)
    assert panel(shown).startswith(NOT_A_BADGE.word)
    assert not shown.nodes("scan.edit")


async def test_a_tool_s_result_has_no_edit_code(show: Show, rig: Rig) -> None:
    """Only a refused entry offers "Edit code"; a badge's result does not."""
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    assert not shown.nodes("scan.edit")


async def test_a_submit_while_the_handler_runs_is_dropped(show: Show, rig: Rig) -> None:
    """One handler at a time: a code in flight goes, the focus stays, the line says so."""
    shown = await show()
    rig.gate = asyncio.Event()
    first = asyncio.create_task(enter(shown, "MOCK0001:v1"))
    while not rig.badges:  # the first handler is running, held by the gate
        await asyncio.sleep(0)
    await shown.settle()
    focused = rig.focused
    await enter(shown, "MOCK0002:v2")
    await shown.settle()
    assert [b.code for b in rig.badges] == ["MOCK0001"]
    assert entry(shown).value == ""
    assert isinstance(entry(shown).helper, ft.Text)
    assert cast(ft.Text, entry(shown).helper).value == SCAN_AGAIN
    assert rig.focused == focused + 1  # iOS's Enter took it out (F274)
    rig.gate.set()
    await first
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 1"
    assert cast(ft.Text, entry(shown).helper).value == SCAN_AGAIN


async def test_scanning_goes_on_through_a_slow_send(show: Show, rig: Rig) -> None:
    """A scan after a dropped one is read alone, never joined to it (#875, D-471)."""
    shown = await show()
    rig.gate = asyncio.Event()
    first = asyncio.create_task(scan(shown, "MOCK0001:v1"))
    while not rig.badges:  # the first handler is running, held by the gate
        await asyncio.sleep(0)
    await scan(shown, "MOCK0002:v2")  # dropped
    await scan(shown, "MOCK0003:v3")  # dropped too, while the same handler runs
    rig.gate.set()
    await first
    rig.gate = None
    await scan(shown, "MOCK0004:v4")
    await scan(shown, "MOCK0005:v5")
    assert rig.badges == [
        Badge("MOCK0001", "v1", "v1"),
        Badge("MOCK0004", "v4", "v4"),
        Badge("MOCK0005", "v5", "v5"),
    ]
    assert entry(shown).helper is None  # a scan was read: the line has gone


async def test_a_result_that_comes_under_another_view_is_dropped(
    show: Show, rig: Rig
) -> None:
    """A slow handler's result after a push (the sponsor picker) stays quiet (D-426)."""
    shown = await show()
    rig.gate = asyncio.Event()
    first = asyncio.create_task(enter(shown, "MOCK0001:v1"))
    while not rig.badges:  # the handler is running, held by the gate
        await asyncio.sleep(0)
    shown.session.page.route = f"{scan_rig.VIEW}/sponsor"  # a View pushed on top
    rig.gate.set()
    await first
    assert panel(shown) == spoken(None)


async def test_back_from_a_pushed_page_puts_the_focus_back_in_the_field(
    show: Show, rig: Rig
) -> None:
    """Back from the leads list or a picker leaves the field focused (#775, D-438).

    The field never loses ``can_request_focus``: Flutter applies it a frame after the
    patch, so a focus asked for as it turns back on would be dropped (F288).
    """
    renders: list[Callable[[int], None]] = []

    @ft.component
    def Scan() -> ft.Control:
        _, set_count = ft.use_state(0)  # a render, as the Router's on a pop
        renders.append(set_count)
        return ScanScreen(title="Lead scanner", source=__name__, on_badge=rig.on_badge)

    shown = await show(Scan)
    assert rig.focused == 0  # autofocus serves the first View
    shown.session.page.route = f"{scan_rig.VIEW}/leads"  # a View pushed on top
    renders[-1](1)
    await shown.settle()
    assert entry(shown).can_request_focus is not False
    assert rig.focused == 0
    shown.session.page.route = scan_rig.VIEW  # Back
    renders[-1](2)
    await shown.settle()
    assert rig.focused == 1  # a HID scanner's next code lands in the field
    renders[-1](3)  # another render on top changes nothing
    await shown.settle()
    assert rig.focused == 1


async def test_a_paused_screen_drops_a_submit(show: Show, rig: Rig) -> None:
    """While the tool pauses it (its dialog is open, #724), nothing is handled."""
    rig.paused = "Paused while the note is open"
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    assert rig.badges == []
    assert panel(shown) == spoken(None)


async def test_a_scan_after_a_pause_is_read_alone(show: Show, rig: Rig) -> None:
    """What the pause dropped has gone, so the next scan never joins it (D-471)."""
    renders: list[Callable[[int], None]] = []

    @ft.component
    def Scan() -> ft.Control:
        count, set_count = ft.use_state(0)
        renders.append(set_count)
        return ScanScreen(
            title="Lead scanner",
            source=__name__,
            on_badge=rig.on_badge,
            paused=None if count else "Paused while the note is open",
        )

    shown = await show(Scan)
    await scan(shown, "MOCK0001:v1")
    await shown.settle()
    assert entry(shown).value == ""
    assert entry(shown).helper == "Paused while the note is open"  # the line says why
    focused = rig.focused
    renders[-1](1)  # the pause ends
    await shown.settle()
    assert rig.focused == focused + 1
    await scan(shown, "MOCK0002:v2")
    assert rig.badges == [Badge("MOCK0002", "v2", "v2")]


async def test_the_keyboard_button_focuses_the_field(show: Show, rig: Rig) -> None:
    """The app bar's KEYBOARD button puts the focus in manual entry."""
    shown = await show()
    button = shown.node("scan.keyboard").content
    assert isinstance(button, ft.IconButton)
    assert button.tooltip == "Type a badge code"
    await shown.click(button)
    assert rig.focused == 1


async def test_the_field_is_built_however_far_down_the_large_text_pushes_it(
    show: Show,
) -> None:
    """The list builds all of itself: a focus on an unbuilt field timed out (#828)."""
    shown = await show()
    (body,) = shown.find(ft.ListView)
    assert body.cache_extent == FULL_LIST_EXTENT


@pytest.mark.parametrize(("age", "dimmed"), [(DIM_AFTER - 1, False), (DIM_AFTER, True)])
async def test_a_result_dims_after_five_seconds_and_says_its_age(
    show: Show, rig: Rig, age: int, dimmed: bool
) -> None:
    """The fill gives way to the neutral one at 5 s; the words and age stay."""
    rig.now = 100.0 + age

    @ft.component
    def Panel() -> ft.Control:
        return ResultPanel(shown=Shown(ACCEPTED, 100.0, 1))

    shown = await show(Panel)
    (card,) = [c for c in shown.find(ft.Container) if c.key == "1"]
    expected = fill_of(ScanOutcome.ACCEPTED, high_contrast=False, dimmed=dimmed)
    assert card.bgcolor == expected[1]
    assert (card.bgcolor == ft.Colors.SURFACE_CONTAINER_HIGHEST) is dimmed
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 1"
    assert f"Read {age} seconds ago" in shown.texts()


@pytest.mark.parametrize(
    ("outcome", "icon"),
    [
        (ScanOutcome.ACCEPTED, ft.Icons.CHECK_CIRCLE),
        (ScanOutcome.DUPLICATE, ft.Icons.HISTORY),
        (ScanOutcome.DENIED, ft.Icons.BLOCK),
        (ScanOutcome.QUEUED, ft.Icons.CLOUD_UPLOAD_OUTLINED),
        (ScanOutcome.INVALID, ft.Icons.ERROR_OUTLINE),
        (ScanOutcome.RECORDED, ft.Icons.TASK_ALT),
        (ScanOutcome.NOT_RECORDED, ft.Icons.REMOVE_CIRCLE_OUTLINE),
    ],
)
def test_each_outcome_has_its_icon_and_says_its_words(
    outcome: ScanOutcome, icon: ft.IconData
) -> None:
    """Never colour alone (ux.md §9): an icon per outcome, and the words in order."""
    assert ICONS[outcome] == icon
    result = ScanResult(outcome, "Word", "Name", ("Reason", "More"))
    assert result.spoken == "Word\nName\nReason\nMore"
    assert ScanResult(outcome, "Word").spoken == "Word"


@pytest.mark.parametrize("outcome", [ScanOutcome.QUEUED, ScanOutcome.INVALID])
def test_queued_and_invalid_are_neutral(outcome: ScanOutcome) -> None:
    """Only accepted, duplicate and denied take a fill of their own (ux.md §7.2)."""
    for high_contrast in (False, True):
        assert fill_of(outcome, high_contrast=high_contrast, dimmed=False) == (
            ft.Colors.ON_SURFACE,
            ft.Colors.SURFACE_CONTAINER_HIGHEST,
        )


@pytest.mark.parametrize(
    ("fills", "least"), [(FILLS, AA_TEXT), (HC_FILLS, AAA_TEXT)], ids=["light", "hc"]
)
def test_each_outcome_s_label_reads_on_its_fill(
    fills: dict[ScanOutcome, tuple[str, str]], least: float
) -> None:
    """4.5:1 for the table's colours; 7:1 in high contrast, which darkens two."""
    assert set(fills) == {
        ScanOutcome.ACCEPTED,
        ScanOutcome.DUPLICATE,
        ScanOutcome.DENIED,
    }
    for label, fill in fills.values():
        assert contrast_ratio(label, fill) >= least, (label, fill)


def test_high_contrast_picks_its_own_fills() -> None:
    """The panel in high contrast takes ``HC_FILLS``, and LIGHT_TOKENS is not HC."""
    assert not LIGHT_TOKENS.high_contrast
    assert (
        fill_of(ScanOutcome.ACCEPTED, high_contrast=True, dimmed=False)
        == (HC_FILLS[ScanOutcome.ACCEPTED])
    )


@pytest.mark.parametrize("tool", ToolKey)
@pytest.mark.parametrize(
    ("url", "signed_in", "flag"), list(product((True, False), repeat=3))
)
def test_a_tool_opens_only_with_a_mock_url_an_account_and_its_flag(
    tool: ToolKey,
    url: bool,
    signed_in: bool,
    flag: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any one of the gate's three terms missing refuses every tool (D-51, #900)."""
    opened_by = {
        ToolKey.LEAD: Account(signed_in=signed_in, lead_retrieval=flag),
        ToolKey.DOOR: Account(signed_in=signed_in, door_check=flag),
        ToolKey.SWAG: Account(signed_in=signed_in, door_check=flag),
        ToolKey.COC: Account(signed_in=signed_in, mask_violation=flag),
    }
    prefs = Prefs(dev={DEV_MOCK_API_URL: "http://mock.test"} if url else {})
    monkeypatch.setattr(scan_screen, "use_prefs", lambda: prefs)
    monkeypatch.setattr(scan_screen, "use_account", lambda: opened_by[tool])
    assert scan_screen.use_tool_allowed(tool) is (url and signed_in and flag)
