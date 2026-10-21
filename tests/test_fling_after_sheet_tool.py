"""Tests for ``tools/fling_after_sheet.py``'s run, the adb driver for #346's row D.

``run()`` drives a scripted stand-in for the emulator, never a device: the rows it shows
follow the driver's taps and swipes, and its launcher log gives each trial a chosen
tap-to-fling time. They pin row D's two rules through the whole run (#484's review): a
trial counts only inside row D's window, and the run refuses a scene that does not start
on the now slot. What the run computes is tested in ``tests/test_fling_trials.py``.
"""

import pytest

from tools import fling_after_sheet
from tools.fling_after_sheet import Device, run
from tools.fling_trials import Node

NOW = ("Talk. N. 2:00 to 2:30 PM, Room 1.", "Talk. M. 2:00 to 2:30 PM, Room 2.")
"""The rows at the top on the now slot, as the setup leaves the Schedule."""

REST = ("Talk. R. 12:30 to 1:00 PM, Grand Ballroom B.", "Talk. S. 12:30 to 1:00 PM.")
"""Where "Show N sessions" leaves the list, with no fling."""

END = tuple(f"Open space. Row {n}. 3:00 to 4:00 PM, Room {n}." for n in range(4))
"""Where every fling ends, the controls' and the trials': a full fling."""

SHOW = Node("schedule.filter.show", "Show 345 sessions", (40, 2160, 1040, 2304))


class FakeDevice(Device):
    """An emulator in a script: the Schedule moves as the driver taps and flings."""

    def __init__(self, gap_ms: int | None, start: tuple[str, ...] = NOW) -> None:
        """Start on ``start``'s rows; each trial's fling comes ``gap_ms`` after its tap (``None``: unlogged)."""
        self.serial = "emulator-fake"
        self.width, self.height = 1080, 2400
        self.gap_ms = gap_ms
        self.now = start
        self.rows = start
        self.commands: list[str] = []

    def shell(self, command: str) -> str:
        """Record ``command``; a swipe ends the list on ``END``; the log holds the last tap and fling."""
        self.commands.append(command)
        if "input swipe" in command:
            self.rows = END
        if command.startswith("logcat -d") and self.gap_ms is not None:
            (x, y), (fx, fy) = SHOW.center, self.fling_points[0]
            line = "D TaplEvents: MotionEvent {{ action={}, x[0]={}, y[0]={}, eventTime={} }}"
            return "\n".join(
                [
                    line.format("ACTION_UP", x, y, 1000),
                    line.format("ACTION_DOWN", fx, fy, 1000 + self.gap_ms),
                ]
            )
        return ""

    def nodes(self) -> list[Node]:
        """Show the Now button, so every control and trial starts with a jump to the now slot."""
        return [Node("schedule.jump_now", "Now", (900, 2000, 1000, 2100))]

    def find(self, ident: str, timeout: float = 30) -> Node | None:
        """Find every element at once; "Show N sessions" at its place."""
        return SHOW if ident == SHOW.ident else Node(ident, "", (0, 0, 10, 10))

    def tap(self, ident: str) -> None:
        """Jump to now on the Now button; rest on ``REST`` when "Show N sessions" closes the sheet."""
        if ident == "schedule.jump_now":
            self.rows = self.now
        elif ident == SHOW.ident:
            self.rows = REST

    def gone(self, ident: str, timeout: float = 30) -> bool:
        """Every element leaves at once: the sheet closes, the tap reached the button."""
        return True

    def rows_when_still(self) -> list[str]:
        """The rows on screen now."""
        return list(self.rows)

    def swipes(self) -> int:
        """How many flings the driver sent."""
        return sum("input swipe" in c for c in self.commands)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the driver's waits: the fake device is still at once."""
    monkeypatch.setattr(fling_after_sheet.time, "sleep", lambda _: None)


def test_a_run_whose_flings_land_inside_the_window_passes() -> None:
    """Trials flung 520 ms after the tap, which end where the controls end, all moved."""
    tally = run(FakeDevice(gap_ms=520), trials=3, gap=0.5)
    assert tally.counts["moved"] == 3
    assert tally.passed


@pytest.mark.parametrize("gap_ms", [900, 648, 300])
def test_a_run_whose_flings_land_outside_the_window_fails_and_keeps_their_times(
    gap_ms: int,
) -> None:
    """Full flings at 900, 648 or 300 ms are off window, not moved: they fail the run, their times stay in the summary."""
    tally = run(FakeDevice(gap_ms=gap_ms), trials=3, gap=0.5)
    assert tally.counts["off window"] == 3
    assert tally.counts["moved"] == 0
    assert not tally.passed
    assert tally.gaps == [gap_ms] * 3
    assert f"tap to fling {gap_ms}-{gap_ms} ms" in tally.summary()


def test_a_run_with_no_timing_evidence_fails() -> None:
    """Trials whose tap and fling never reached the launcher's log are off window, and the run fails."""
    tally = run(FakeDevice(gap_ms=None), trials=2, gap=0.5)
    assert tally.counts["off window"] == 2
    assert tally.gaps == []
    assert not tally.passed


@pytest.mark.parametrize(
    "start", [("Talk. Early. 9:00 to 9:30 AM, Room 1.",), ()], ids=["9:00", "empty"]
)
def test_a_run_that_does_not_start_on_the_2_00_slot_is_refused(
    start: tuple[str, ...],
) -> None:
    """A scene at 9:00, or with no row at all, stops the run before any fling (--no-setup on the wrong clock)."""
    device = FakeDevice(gap_ms=520, start=start)
    with pytest.raises(RuntimeError, match="not 2:00"):
        run(device, trials=3, gap=0.5)
    assert device.swipes() == 0
