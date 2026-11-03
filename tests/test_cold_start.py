"""Tests for ``tools/cold_start.py``'s reading of ``am start -W`` and ``logcat -v epoch``."""

import pytest

from tools import cold_start

LOG = """\
--------- beginning of main
1762128000.100  1000  1100 I ActivityTaskManager: START u0 {act=VIEW dat=confcompanion://app/schedule}
1762128000.871  1000  1100 I ActivityTaskManager: Displayed app: +771ms
1762128002.366 12345 12400 I flet.python: Content shown: cache feed, version 1
1762128003.000 12345 12400 I flet.python: Content shown: again
"""


def test_marker_is_timed_from_start_u0() -> None:
    """The first matching line after ``START u0`` gives the time, in ms."""
    assert cold_start.marker_ms(LOG, "Content shown") == 2266.0


def test_marker_before_the_start_doesnt_count() -> None:
    """A line older than ``START u0`` isn't this start's."""
    log = "1762127999.000 1 1 I flet.python: Content shown\n" + LOG
    assert cold_start.marker_ms(log, "Content shown") == 2266.0


def test_no_marker_reads_as_none() -> None:
    """A start whose line never came has no reading, not a zero."""
    assert cold_start.marker_ms(LOG, "S2 acked") is None
    assert cold_start.marker_ms("", "Content shown") is None


def test_total_time_is_read_from_am_start() -> None:
    """``TotalTime`` is the number on its own line, and not ``WaitTime``'s."""
    output = "Status: ok\nLaunchState: COLD\nTotalTime: 612\nWaitTime: 620\nComplete\n"
    assert cold_start.total_time(output) == 612
    assert cold_start.total_time("Status: timeout\n") is None


def test_summary_gives_median_and_range() -> None:
    """The line reads as §8's tables do: median, range, n."""
    assert cold_start.summary("TotalTime", [1, 2, 9]) == (
        "TotalTime: median 2.0 ms (1.0-9.0), n = 3"
    )
    assert cold_start.summary("TotalTime", []) == "TotalTime: no readings"


def test_owners_emulator_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run never force-stops anything on the owner's emulator."""

    def no_call(*args: object, **kwargs: object) -> None:
        """Fail the test if ``adb`` would run."""
        raise AssertionError(f"ran {args}")

    monkeypatch.setattr(cold_start.subprocess, "run", no_call)
    with pytest.raises(SystemExit, match="owner's"):
        cold_start.main(["--serial", "emulator-5554"])
