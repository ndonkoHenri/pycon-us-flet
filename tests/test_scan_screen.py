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
    ENTRY_TITLE_MAX,
    NOT_A_BADGE,
    Badge,
    ScanOutcome,
    ScanResult,
    entry_title,
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
from tests import harness, scan_rig
from tests.scan_rig import ACCEPTED, Rig, Show, enter, entry, panel, scan
from tests.test_high_contrast import AAA_TEXT
from tests.test_theme import AA_TEXT, contrast_ratio

rig, show, timer = scan_rig.rig, scan_rig.show, scan_rig.timer


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


def test_the_camera_note_says_how_to_go_on_and_blames_no_build() -> None:
    """The note names the two ways to scan and never a build's excuse (#1013)."""
    assert "camera" in CAMERA_UNAVAILABLE
    assert "Type the badge code" in CAMERA_UNAVAILABLE
    assert "Bluetooth or USB scanner" in CAMERA_UNAVAILABLE
    assert "build" not in CAMERA_UNAVAILABLE


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


@pytest.mark.parametrize(
    "text",
    ["https://example.org/a:b", "BEGIN:VCARD\nFN:Ada Lovelace\nEND:VCARD"],
)
async def test_a_scanned_url_or_contact_card_is_not_a_badge_code(
    show: Show, rig: Rig, text: str
) -> None:
    """A QR code that is a URL or a vCard has colons, yet says "Not a badge code" and reaches no handler (#978, D-477)."""
    shown = await show()
    await enter(shown, text)
    assert rig.badges == []
    assert entry(shown).value == ""  # cleared like every submit (D-473)
    assert panel(shown).startswith(NOT_A_BADGE.word)
    assert entry_title(text) in panel(shown)
    button = shown.node("scan.edit").content  # and the text is one tap away
    assert isinstance(button, ft.FilledTonalButton)
    await shown.click(button)
    await shown.settle()
    assert entry(shown).value == text
    assert not shown.nodes("scan.edit")


@pytest.mark.parametrize("line", ["BEGIN:VCARD", "WIFI:T:WPA;S:net;P:secret;;"])
async def test_the_first_line_of_a_contact_card_or_a_wifi_code_is_not_a_badge(
    show: Show, rig: Rig, line: str
) -> None:
    """A HID scanner types a QR text one line per Enter into the one-line field: a vCard's first line and a Wi-Fi code reach no handler (#978, D-477)."""
    shown = await show()
    await enter(shown, line)
    assert rig.badges == []
    assert panel(shown).startswith(NOT_A_BADGE.word)


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
    assert rig.focused == focused + 1  # the field has the focus again
    assert panel(shown) == spoken(None)  # the result is gone with its button
    assert not shown.nodes("scan.edit")
    assert rig.badges == []
    await enter(shown, "MOCK0005:v4l1d05")  # the typist's fix, submitted as typed
    assert rig.badges == [Badge("MOCK0005", "v4l1d05", "v4l1d05")]


async def test_a_long_refused_entry_is_clipped_on_the_panel_and_in_speech(
    show: Show, rig: Rig
) -> None:
    """A 300-character paste shows two lines at most and is said clipped (#965)."""
    shown = await show()
    text = "example.org/" + "word-" * 60 + "THE-END"  # no colon: a badge has one
    await enter(shown, text)
    clipped = entry_title(text)
    assert len(clipped) == ENTRY_TITLE_MAX + 1
    assert panel(shown) == f"{replace(NOT_A_BADGE, title=clipped).spoken}\nScan 1"
    assert "THE-END" not in panel(shown)
    (title,) = (t for t in shown.find(ft.Text) if t.value == clipped)
    assert title.max_lines == 2
    assert title.overflow == ft.TextOverflow.ELLIPSIS


async def test_edit_code_gives_back_the_whole_of_a_long_text(
    show: Show, rig: Rig
) -> None:
    """The clip is for the panel: "Edit code" puts all 300 characters back in the field (#965)."""
    shown = await show()
    text = "x" * 300
    await enter(shown, f" {text}\n")
    button = shown.node("scan.edit").content
    assert isinstance(button, ft.FilledTonalButton)
    await shown.click(button)
    await shown.settle()
    assert entry(shown).value == text


async def test_edit_code_keeps_the_newlines_the_title_collapses(
    show: Show, rig: Rig
) -> None:
    """A multi-line paste shows on one line, and Edit code gives it back as it was (#965)."""
    shown = await show()
    text = "BEGIN-VCARD\nFN-Ada Lovelace\nEND-VCARD"  # no colon: a badge has one
    await enter(shown, text)
    assert "BEGIN-VCARD FN-Ada Lovelace END-VCARD" in panel(shown)
    button = shown.node("scan.edit").content
    assert isinstance(button, ft.FilledTonalButton)
    await shown.click(button)
    await shown.settle()
    assert entry(shown).value == text


async def test_a_name_is_not_capped_to_two_lines(show: Show, rig: Rig) -> None:
    """Only a refused entry's title is capped: an attendee's name wraps whole at any size (D-33)."""
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    (title,) = (t for t in shown.find(ft.Text) if t.value == ACCEPTED.title)
    assert title.max_lines is None
    assert title.overflow == ft.TextOverflow.CLIP


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


def under(control: object) -> list[object]:
    """``control`` and every control under it, in reading order."""
    found = [control]
    for child in (getattr(control, "content", None), *getattr(control, "controls", ())):
        if child is not None:
            found += under(child)
    return found


def body_order(shown: harness.Shown) -> list[str]:
    """What the scan screen's body holds, top to bottom: field, result, buttons, rest.

    The result panel and the camera note are components, found by their function's
    name; the field and the sync chip by their identifiers.
    """
    (body,) = shown.find(ft.ListView)
    names = {"ResultPanel": "result", "CameraUnavailable": "camera"}
    identifiers = {
        "scan.entry": "field",
        "scan.edit": "edit",
        "staff.sync_chip": "chip",
    }
    order: list[str] = []
    for child in body.controls:
        parts = under(child)
        order += [
            names[fn.__name__]
            for part in parts
            if (fn := getattr(part, "fn", None)) and fn.__name__ in names
        ] + [
            identifiers[part.identifier]
            for part in parts
            if isinstance(part, ft.Semantics) and part.identifier in identifiers
        ][:1]
    return order


async def test_at_normal_text_the_result_is_above_the_field(show: Show) -> None:
    """The order is the camera note, the result and then the field (ux.md §7.2)."""
    shown = await show(prefs=Prefs(loaded=True, time_above=False))
    assert body_order(shown) == ["camera", "result", "field"]


async def test_at_large_text_the_field_and_the_result_come_first(show: Show) -> None:
    """The field leads, so the keyboard scrolls nothing, then the result, then the rest (#955)."""
    shown = await show(prefs=Prefs(loaded=True, time_above=True))
    assert body_order(shown) == ["field", "result", "chip", "camera"]


async def test_at_large_text_the_result_s_buttons_follow_it_before_the_rest(
    show: Show, rig: Rig
) -> None:
    """The "Edit code" button sits under the result, ahead of the chip and camera note (#955)."""
    shown = await show(prefs=Prefs(loaded=True, time_above=True))
    await enter(shown, "NOCOLON")
    assert body_order(shown) == ["field", "result", "edit", "chip", "camera"]


async def test_the_field_is_the_same_control_when_the_text_size_flips_the_order(
    show: Show, rig: Rig
) -> None:
    """A size change while the screen is open moves the field without rebuilding it.

    A rebuilt field loses the focus, and a HID scanner's next scan goes nowhere.
    """
    prefs = Prefs(loaded=True, time_above=False)
    shown = await show(prefs=prefs)
    field_id = entry(shown)._i  # the client's id: kept while the control is kept
    prefs.time_above = True
    await shown.settle()
    assert body_order(shown)[0] == "field"
    assert entry(shown)._i == field_id


async def test_at_large_text_the_panel_puts_its_icon_above_its_words(
    show: Show, rig: Rig
) -> None:
    """The words get the card's whole width: a Column of the icon and the words (#955)."""
    shown = await show(prefs=Prefs(loaded=True, time_above=True))
    await enter(shown, "MOCK0001:v1")
    (card,) = [c for c in shown.find(ft.Container) if c.key == "1"]
    assert isinstance(card.content, ft.Column)
    icon, words = card.content.controls
    assert isinstance(icon, ft.Icon) and isinstance(words, ft.Column)
    assert not words.expand
    assert icon.apply_text_scaling is False  # it would fill the screen at 3x


async def test_at_normal_text_the_panel_keeps_its_icon_beside_its_words(
    show: Show, rig: Rig
) -> None:
    """Below the large sizes the icon stays in a row beside the words."""
    shown = await show(prefs=Prefs(loaded=True, time_above=False))
    await enter(shown, "MOCK0001:v1")
    (card,) = [c for c in shown.find(ft.Container) if c.key == "1"]
    assert isinstance(card.content, ft.Row)


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


async def test_a_refused_entry_is_not_cleared_with_the_tool_s_timer(
    show: Show, rig: Rig, timer: scan_rig.Timer
) -> None:
    """The Code of Conduct tool clears results after 15 s; "Edit code" outlasts it (D-473)."""
    rig.clear_after = 15
    shown = await show()
    await enter(shown, "MOCK0001v1")
    await enter(shown, "MOCK0002:v2")
    assert timer.waits == [15]  # a badge's result clears
    await enter(shown, "MOCK0003v3")
    timer.ring()
    await shown.settle()
    assert shown.nodes("scan.edit")
    assert panel(shown).startswith(NOT_A_BADGE.word)
