"""Tests for ``tools/fling_trials.py``, what the adb driver for #346's row D computes.

Only what it computes is tested here, never a device: reading a ``uiautomator dump``,
timing the tap and the fling from the launcher's ``TaplEvents`` log, and judging a fling
by the rules of ``maestro/scripts/record_fling.js`` (``tests/test_fling_scripts.py``
holds the same cases for the script) and by row D's window. The driver's run itself is
tested in ``tests/test_fling_after_sheet_tool.py``.
"""

from tools.fling_trials import (
    Control,
    Node,
    Tally,
    classify,
    controls_agree,
    in_window,
    parse_nodes,
    session_rows,
    slot_of,
    tap_to_fling_ms,
)

REST = "Talk. R. 12:30 to 1:00 PM, Grand Ballroom B."
SLOT = tuple(f"Open space. Row {n}. 3:00 to 4:00 PM, Room {n}." for n in range(14))
"""The 3:00 PM slot's rows, in the list's order: where a full fling ends."""

END = 6
"""Where the controls end: the index in ``SLOT`` of a control's top row."""


def rows_at(index: int) -> tuple[str, ...]:
    """Return the first four rows on screen when ``SLOT[index]`` is the top row."""
    return SLOT[index : index + 4]


CONTROLS = (Control(REST, rows_at(END)),) * 3


def node(ident: str, label: str, bounds: str, visible: str = "true") -> str:
    """Return one ``<node>`` of a ``uiautomator dump`` with Flutter's attributes."""
    return (
        f'<node index="0" text="" resource-id="{ident}" content-desc="{label}" '
        f'visible-to-user="{visible}" bounds="{bounds}" />'
    )


def dump(*nodes: str) -> str:
    """Return a whole ``uiautomator dump`` holding ``nodes``."""
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
        + "".join(nodes)
        + "</hierarchy>"
    )


def judge(
    rows: tuple[str, ...], trial_start: str = "2:00", gap_ms: int | None = 520
) -> str:
    """Return how the driver judges a trial that began on ``trial_start``, flung ``gap_ms`` after the tap and ended with ``rows`` on top."""
    return classify(
        trial_start=trial_start,
        gap_ms=gap_ms,
        rows=rows,
        rest_row=REST,
        controls=CONTROLS,
    )


# ------------------------------------------------------------------ reading the screen


def test_session_rows_come_from_the_top_and_skip_what_does_not_show() -> None:
    """Rows are ordered by their place on screen, not the dump's order; hidden or empty ones are left out."""
    xml = dump(
        node(
            "schedule.session.2",
            "Second. 2:00 to 2:30 PM, Room 1.",
            "[0,900][1080,1200]",
        ),
        node("schedule.filter", "Filter", "[900,100][1000,200]"),
        node(
            "schedule.session.1", "First. 2:00 to 2:30 PM, Room 2.", "[0,600][1080,900]"
        ),
        node(
            "schedule.session.3",
            "Off screen. 2:00 to 2:30 PM, Room 3.",
            "[0,2400][1080,2400]",
        ),
        node(
            "schedule.session.4",
            "Hidden. 2:00 to 2:30 PM, Room 4.",
            "[0,1200][1080,1500]",
            visible="false",
        ),
    )
    assert session_rows(parse_nodes(xml)) == [
        "First. 2:00 to 2:30 PM, Room 2.",
        "Second. 2:00 to 2:30 PM, Room 1.",
    ]


def test_a_node_is_tapped_at_its_centre() -> None:
    """A tap on an element goes to the middle of its bounds."""
    assert Node(
        "schedule.filter.show", "Show 345 sessions", (40, 2160, 1040, 2304)
    ).center == (540, 2232)


def test_a_slot_is_the_phrases_first_start_time() -> None:
    """The slot is the first "H:MM to" of a row's phrase, and empty without one."""
    assert (
        slot_of("Talk. Something at 9:00 to 5:00. 2:00 to 2:30 PM, Room 1.") == "9:00"
    )
    assert slot_of(SLOT[0]) == "3:00"
    assert slot_of("") == ""


# ------------------------------------------------------------------ the touch log

TAPL = (
    "D TaplEvents: TIS / TouchInteractionService.onInputEvent: MotionEvent "
    "{{ action={action}, actionButton=0, id[0]=0, x[0]={x}, y[0]={y}, toolType[0]=TOOL_TYPE_FINGER, "
    "eventTime={t}, downTime={t}, deviceId=-1 }}"
)


def touch(action: str, x: float, y: float, t: int) -> str:
    """Return one ``TaplEvents`` line, as the launcher logs a touch."""
    return TAPL.format(action=action, x=x, y=y, t=t)


def test_the_tap_to_fling_time_runs_from_the_taps_up_to_the_flings_down() -> None:
    """The gap is the fling's ACTION_DOWN at its start point minus the tap's ACTION_UP on the button."""
    log = "\n".join(
        [
            touch("ACTION_DOWN", 540.0, 2232.0, 1000),
            touch("ACTION_UP", 540.0, 2232.0, 1060),
            touch("ACTION_DOWN", 540.0, 1800.0, 1472),
            touch("ACTION_UP", 540.0, 600.0, 1552),
        ]
    )
    assert tap_to_fling_ms(log, (540, 2232), (540, 1800)) == 412


def test_the_tap_to_fling_time_is_unknown_without_both_touches() -> None:
    """A log that lacks the tap or the fling gives no time rather than a wrong one."""
    assert (
        tap_to_fling_ms(
            touch("ACTION_DOWN", 540.0, 1800.0, 1472), (540, 2232), (540, 1800)
        )
        is None
    )
    assert (
        tap_to_fling_ms(
            touch("ACTION_UP", 540.0, 2232.0, 1060), (540, 2232), (540, 1800)
        )
        is None
    )


# ------------------------------------------------------------------ judging a fling


def test_a_trial_that_ends_up_to_three_rows_from_the_controls_moved() -> None:
    """A full fling varies by a row or two: on the controls' row, or up to three rows either side, is near."""
    for index in (END - 3, END - 1, END, END + 1, END + 3):
        assert judge(rows_at(index)) == "moved", index


def test_a_trial_that_ends_in_the_controls_slot_but_rows_short_is_short() -> None:
    """A fling that stops four or more rows short of the controls, in their slot, is cut short (#484's review)."""
    assert judge(rows_at(END - 4)) == "short"
    assert judge(rows_at(0)) == "short"


def test_a_trial_that_ends_rows_past_the_controls_is_not_moved() -> None:
    """A fling that ends four or more rows past the controls is no full fling either."""
    assert judge(rows_at(END + 4)) == "short"


def test_a_trial_that_ends_on_the_rests_row_did_not_scroll() -> None:
    """The rest's row on top after the fling means the list did not scroll."""
    assert judge((REST, *SLOT[:3])) == "none"


def test_a_trial_off_the_now_slot_or_with_no_row_is_invalid() -> None:
    """A trial that began off the now slot, or whose rows could not be read, says nothing."""
    assert judge(rows_at(END), trial_start="2:45") == "invalid"
    assert judge(()) == "invalid"


def test_row_ds_window_runs_from_330_to_600_ms_both_ends_included() -> None:
    """A measured time from 330 to 600 ms is inside row D's window; a ms either side, or none, is not."""
    assert in_window(330) and in_window(520) and in_window(600)
    assert not in_window(329) and not in_window(601) and not in_window(None)


def test_a_trial_flung_outside_the_window_or_untimed_is_off_window_whatever_it_did() -> (
    None
):
    """A fling at 648 or 900 ms, or with no measured time, says nothing about row D, moved or not (#484's review)."""
    for gap_ms in (329, 601, 648, 900, None):
        assert judge(rows_at(END), gap_ms=gap_ms) == "off window", gap_ms
        assert judge((REST, *SLOT[:3]), gap_ms=gap_ms) == "off window", gap_ms


def test_a_trial_off_the_now_slot_is_invalid_before_its_timing_counts() -> None:
    """A trial that began off the now slot is invalid even when its time is outside the window too."""
    assert judge(rows_at(END), trial_start="9:00", gap_ms=900) == "invalid"


def test_controls_that_end_near_each_other_agree() -> None:
    """Controls up to three rows apart measure one full fling."""
    assert controls_agree(
        [
            Control(REST, rows_at(END)),
            Control(REST, rows_at(END + 2)),
            Control(REST, rows_at(END - 1)),
        ]
    )


def test_controls_that_disagree_or_did_not_move_measure_nothing() -> None:
    """Controls four rows apart, one that kept the rest's row, one from another rest, or none at all fail."""
    assert not controls_agree(
        [Control(REST, rows_at(END)), Control(REST, rows_at(END + 4))]
    )
    assert not controls_agree([Control(REST, (REST, *SLOT[:3]))])
    other_rest = "Talk. S. 12:30 to 1:00 PM, Room 2."
    assert not controls_agree(
        [Control(REST, rows_at(END)), Control(other_rest, rows_at(END))]
    )
    assert not controls_agree([Control(REST, ())])
    assert not controls_agree([])


def test_the_tally_passes_only_when_every_trial_moved_and_no_tap_missed() -> None:
    """One lost fling, one off-window trial or one missed tap fails the run; the summary gives the counts and every time."""
    tally = Tally()
    tally.counts["moved"] = 2
    tally.gaps = [412, 380, 455]
    assert tally.passed
    assert tally.summary() == (
        "2 moved, 0 short, 0 none, 0 invalid, 0 off window, of 2; taps that missed the button, 0; "
        "tap to fling 380-455 ms (median 412)"
    )
    tally.missed = 1
    assert not tally.passed
    tally.missed = 0
    tally.counts["short"] = 1
    assert not tally.passed
    tally.counts["short"] = 0
    tally.counts["off window"] = 1
    tally.gaps.append(900)
    assert not tally.passed
    assert "1 off window, of 3" in tally.summary()
    assert "tap to fling 380-900 ms" in tally.summary()
