"""Tests for the shared scan screen, ``ui/scan_screen.py`` (LEAD-01, LEAD-09; D-65, #723).

The screen runs in a real Flet session (``tests/harness.py``) around a recording
handler; entry is what Flutter reports: the field's value, a change event, then the
submit event with the text. The clock is the module's ``clock()``, held by the test.
How it looks, a HID scanner's typing and the screen readers are checked on devices
(the PR).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path

import flet as ft
import pytest

from pycon_us import capabilities
from pycon_us.config import load_year
from pycon_us.core.badges import (
    NOT_A_BADGE,
    Badge,
    ScanOutcome,
    ScanResult,
)
from pycon_us.core.timefmt import seconds_ago
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import scan_screen
from pycon_us.ui.scan_result import (
    DIM_AFTER,
    FILLS,
    HC_FILLS,
    ICONS,
    READY,
    fill_of,
    spoken,
)
from pycon_us.ui.scan_screen import (
    CAMERA_UNAVAILABLE,
    ResultPanel,
    ScanScreen,
    Shown,
)
from tests import harness
from tests.test_high_contrast import AAA_TEXT
from tests.test_theme import AA_TEXT, contrast_ratio

VIEW = "/more/staff/lead"

ACCEPTED = ScanResult(ScanOutcome.ACCEPTED, "Checked in", "Ada Lovelace")

type Show = Callable[..., Awaitable[harness.Shown]]


class Rig:
    """What the screen under test was given and did: its handler's calls and focus."""

    def __init__(self) -> None:
        """Start with nothing handled, a clock at 100 s and the handler answering."""
        self.badges: list[Badge] = []
        self.focused = 0
        self.now = 100.0
        self.result = ACCEPTED
        self.gate: asyncio.Event | None = None
        self.paused = False

    async def on_badge(self, badge: Badge) -> ScanResult:
        """Record the badge; wait for ``gate`` when one is set; return ``result``."""
        self.badges.append(badge)
        if self.gate is not None:
            await self.gate.wait()
        return self.result


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> Rig:
    """A rig whose clock is the screen's and which counts the field's focus calls."""
    held = Rig()

    async def focus(_: ft.TextField) -> None:
        held.focused += 1

    monkeypatch.setattr(ft.TextField, "focus", focus)
    monkeypatch.setattr(scan_screen, "clock", lambda: held.now)
    return held


@pytest.fixture
async def show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> AsyncIterator[Show]:
    """Return a function that renders the scan screen around the rig's handler."""
    async with AsyncExitStack() as stack:

        async def render(
            screen: Callable[[], ft.Control] | None = None,
        ) -> harness.Shown:
            """Render ``screen``, by default a scan screen titled "Lead scanner"."""

            @ft.component
            def Scan() -> ft.Control:
                return ScanScreen(
                    title="Lead scanner", on_badge=rig.on_badge, paused=rig.paused
                )

            return await stack.enter_async_context(
                harness.showing(
                    screen or Scan,
                    scan_screen,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                )
            )

        yield render


def entry(shown: harness.Shown) -> ft.TextField:
    """The mounted badge code field."""
    (found,) = shown.find(ft.TextField)
    return found


async def enter(shown: harness.Shown, text: str) -> None:
    """Type ``text`` as Flutter reports it, then press Enter (a HID scanner's way)."""
    field = entry(shown)
    shown.session.apply_patch(field._i, {"value": text})
    await shown.event(field, "change", text)
    await shown.event(field, "submit", text)


def panel(shown: harness.Shown) -> str:
    """What the result panel's live region says."""
    node = shown.node("scan.result")
    assert node.live_region and node.container  # said as it changes (ux.md §9)
    return str(node.label)


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
    assert panel(shown) == "Checked in\nAda Lovelace"
    assert entry(shown).value == ""
    assert rig.focused == 1
    assert f"Read {seconds_ago(0)}" in shown.texts()


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
    assert panel(shown) == "Checked in\nAda Lovelace"
    assert entry(shown).value == ""
    rig.now += 0.2
    await enter(shown, "MOCK0001:v1")
    assert len(rig.badges) == 2
    assert panel(shown) == "Already checked in"


async def test_a_different_code_shows_at_once(show: Show, rig: Rig) -> None:
    """The cooldown is per code: another badge right after is handled."""
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    rig.result = ScanResult(ScanOutcome.ACCEPTED, "Checked in", "Grace Hopper")
    await enter(shown, "MOCK0002:v2")
    assert [b.code for b in rig.badges] == ["MOCK0001", "MOCK0002"]
    assert panel(shown) == "Checked in\nGrace Hopper"


async def test_junk_says_not_a_badge_code_and_keeps_the_text(
    show: Show, rig: Rig
) -> None:
    """Text without a code is no badge: said in the panel, kept for correction."""
    shown = await show()
    await enter(shown, "MOCK0001")
    assert rig.badges == []
    assert panel(shown) == NOT_A_BADGE.spoken
    assert entry(shown).value == "MOCK0001"
    assert rig.focused == 1  # Enter took the focus; it is back for the correction


async def test_a_submit_while_the_handler_runs_is_dropped(show: Show, rig: Rig) -> None:
    """One handler at a time: a second code in flight is dropped, its text kept."""
    shown = await show()
    rig.gate = asyncio.Event()
    first = asyncio.create_task(enter(shown, "MOCK0001:v1"))
    while not rig.badges:  # the first handler is running, held by the gate
        await asyncio.sleep(0)
    await shown.settle()
    await enter(shown, "MOCK0002:v2")
    assert [b.code for b in rig.badges] == ["MOCK0001"]
    assert entry(shown).value == "MOCK0002:v2"
    rig.gate.set()
    await first
    assert panel(shown) == "Checked in\nAda Lovelace"


async def test_a_paused_screen_drops_a_submit(show: Show, rig: Rig) -> None:
    """While paused (a dialog over it, #724), nothing is handled."""
    rig.paused = True
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    assert rig.badges == []
    assert panel(shown) == spoken(None)


async def test_the_keyboard_button_focuses_the_field(show: Show, rig: Rig) -> None:
    """The app bar's KEYBOARD button puts the focus in manual entry."""
    shown = await show()
    button = shown.node("scan.keyboard").content
    assert isinstance(button, ft.IconButton)
    assert button.tooltip == "Type a badge code"
    await shown.click(button)
    assert rig.focused == 1


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
    assert panel(shown) == "Checked in\nAda Lovelace"
    assert f"Read {age} seconds ago" in shown.texts()


@pytest.mark.parametrize(
    ("outcome", "icon"),
    [
        (ScanOutcome.ACCEPTED, ft.Icons.CHECK_CIRCLE),
        (ScanOutcome.DUPLICATE, ft.Icons.HISTORY),
        (ScanOutcome.DENIED, ft.Icons.BLOCK),
        (ScanOutcome.QUEUED, ft.Icons.CLOUD_UPLOAD_OUTLINED),
        (ScanOutcome.INVALID, ft.Icons.ERROR_OUTLINE),
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
