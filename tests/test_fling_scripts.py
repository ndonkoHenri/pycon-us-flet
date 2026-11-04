"""Tests for the regression flow's scripts, `maestro/scripts/record_control.js` and `record_fling.js`.

Maestro runs them with `runScript` against the flow's `output`; here Node runs them
the same way, in a fresh context whose `output` is a test's object, and hands back what
they left in it and what they printed. They are skipped where Node is missing.

The rows are phrases as the Schedule's rows carry them (D-190). `SLOT` stands for the
3:00 PM slot, where a full fling ends: many rows deep, so the cases that matter most are
trials that end in that slot but rows short of the controls (#484's review), and full
flings that end a row or two either side of them (seen on the emulator).
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "maestro" / "scripts"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node runs the flow's scripts")

HARNESS = """
const fs = require("fs");
const vm = require("vm");
const [file, given] = process.argv.slice(1);
const logged = [];
const context = { output: JSON.parse(given), console: { log: (line) => logged.push(String(line)) } };
vm.runInNewContext(fs.readFileSync(file, "utf8"), context);
process.stdout.write(JSON.stringify({ output: context.output, logged }));
"""

REST = "Talk. R. 12:30 to 1:00 PM, Grand Ballroom B."
SLOT = [f"Open space. Row {n}. 3:00 to 4:00 PM, Room {n}." for n in range(14)]
"""The 3:00 PM slot's rows, in the list's order."""

END = 6
"""Where the controls end: the index in `SLOT` of a control's top row."""


def rows_at(index: int) -> list[str]:
    """Return the first four rows on screen when `SLOT[index]` is the top row."""
    return SLOT[index : index + 4]


def run_script(name: str, output: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Run `maestro/scripts/<name>` on `output` and return the output it left and its lines."""
    assert NODE is not None
    result = subprocess.run(
        [NODE, "-e", HARNESS, str(SCRIPTS / name), json.dumps(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    done = json.loads(result.stdout)
    return done["output"], done["logged"]


def control(
    rows: list[str], output: dict[str, Any] | None = None, rest: str = REST
) -> dict[str, Any]:
    """Run `record_control.js` for one control that ended with `rows` on top, after `output`."""
    done, _ = run_script(
        "record_control.js", {**(output or {}), "restRow": rest, "topRows": rows}
    )
    return done


def controls(*ends: int) -> dict[str, Any]:
    """Return the flow's `output` once controls that ended at these `SLOT` indexes ran."""
    output: dict[str, Any] = {}
    for end in ends:
        output = control(rows_at(end), output)
    return output


def trial(rows: list[str], **changes: Any) -> dict[str, Any]:
    """Return the flow's `output` for one trial that ended with `rows` on top, after three controls."""
    output = {
        **controls(END, END, END),
        "startSlot": "2:00",
        "trialStart": "2:00",
        "restRow": REST,
        "topRows": rows,
    }
    output.update(changes)
    return output


def kind_of(rows: list[str], **changes: Any) -> str:
    """Return how `record_fling.js` judges one trial: the word its line prints."""
    _, logged = run_script("record_fling.js", trial(rows, **changes))
    return logged[0].split(": ", 1)[1].split(" ", 1)[0]


# ------------------------------------------------------------------ record_fling.js


def test_a_trial_that_ends_where_the_controls_did_moved() -> None:
    """A fling that ends on the row the controls ended on ran in full."""
    assert kind_of(rows_at(END)) == "moved"


def test_a_trial_that_ends_up_to_three_rows_either_side_moved() -> None:
    """A full fling varies by a row or two: up to three rows before or past the controls is near."""
    for index in (END - 3, END - 1, END + 1, END + 3):
        assert kind_of(rows_at(index)) == "moved", index


def test_a_trial_that_ends_in_the_controls_slot_but_rows_short_is_short() -> None:
    """A fling that stops four or more rows short of the controls, in their slot, is cut short (#484's review)."""
    assert kind_of(rows_at(END - 4)) == "short"
    assert kind_of(rows_at(0)) == "short"


def test_a_trial_that_ends_rows_past_the_controls_is_not_moved() -> None:
    """A fling that ends four or more rows past the controls is no full fling either."""
    assert kind_of(rows_at(END + 4)) == "short"


def test_a_trial_that_ends_on_the_rests_row_did_not_scroll() -> None:
    """The rest's row on top after the fling means the list did not scroll."""
    assert kind_of([REST, *SLOT[:3]]) == "none"


def test_a_trial_with_no_row_read_is_invalid() -> None:
    """No row read after the fling (empty copies) says nothing about it."""
    assert kind_of(["", "", "", ""]) == "invalid"


def test_a_trial_that_began_off_the_now_slot_is_invalid() -> None:
    """A trial that began elsewhere (the fake clock moved the now slot) is invalid, wherever it ended."""
    assert kind_of(rows_at(END), trialStart="2:45") == "invalid"


def test_the_trials_add_up_and_count_what_was_lost() -> None:
    """Each trial adds to the counts, `lost` counts every trial that did not move, and the summary says so."""
    output, _ = run_script("record_fling.js", trial(rows_at(END)))
    output, _ = run_script("record_fling.js", {**output, "topRows": rows_at(0)})
    output, logged = run_script("record_fling.js", {**output, "topRows": [REST]})
    assert output["counts"] == {
        "moved": 1,
        "dragged": 0,
        "short": 1,
        "none": 1,
        "invalid": 0,
    }
    assert output["lost"] == 2
    assert output["dragged"] == 0
    assert output["summary"] == "1 moved, 0 dragged, 1 short, 1 none, 0 invalid, of 3"
    assert logged[0].startswith("fling 3: none")


def test_a_trial_that_ends_where_the_drag_did_lost_its_velocity() -> None:
    """A trial near the slow swipe's rows is "dragged": not a loss, but counted apart (#1012)."""
    drag = rows_at(0)
    assert kind_of(drag, dragRows=drag) == "dragged"
    output, _ = run_script("record_fling.js", trial(drag, dragRows=drag))
    assert output["dragged"] == 1
    assert output["lost"] == 0


def test_a_full_fling_near_the_drag_is_still_moved() -> None:
    """Being near a control comes first: it ran in full, wherever a drag would end."""
    assert kind_of(rows_at(END), dragRows=rows_at(END)) == "moved"


# ------------------------------------------------------------------ record_control.js


def test_controls_that_end_near_each_other_agree() -> None:
    """Three controls up to three rows apart agree, and each is kept with its rows."""
    output = controls(END, END + 2, END - 1)
    assert output["controlsOk"] is True
    assert [c["top"] for c in output["controls"]] == [
        SLOT[END],
        SLOT[END + 2],
        SLOT[END - 1],
    ]
    assert output["controls"][1]["rows"] == rows_at(END + 2)


def test_controls_further_apart_than_their_rows_disagree() -> None:
    """A control that ends four rows from another makes the controls measure nothing."""
    assert controls(END, END + 4)["controlsOk"] is False
    assert controls(END, END, END - 4)["controlsOk"] is False


def test_a_control_that_did_not_leave_the_rest_fails() -> None:
    """A control with the rest's row among its rows did not scroll a full fling."""
    assert control([REST, *SLOT[:3]])["controlsOk"] is False


def test_a_control_from_another_rest_fails() -> None:
    """Every control must start from the first one's rest, or they are not the same fling."""
    output = control(rows_at(END))
    output = control(rows_at(END), output, rest="Talk. S. 12:30 to 1:00 PM, Room 2.")
    assert output["controlsOk"] is False


def test_a_control_that_lost_its_velocity_is_dropped() -> None:
    """One that ends where the slow swipe did measures nothing, and is not kept (#1012)."""
    drag = rows_at(0)
    kept = control(rows_at(END), {"dragRows": drag})
    dropped, logged = run_script(
        "record_control.js", {**kept, "restRow": REST, "topRows": drag}
    )
    assert len(dropped["controls"]) == 1
    assert dropped["controlsOk"] is True
    assert logged[0].startswith("control dropped")


def test_a_control_with_no_row_read_fails() -> None:
    """A control whose rows could not be read (empty copies) measures nothing."""
    assert control(["", "", "", ""])["controlsOk"] is False
