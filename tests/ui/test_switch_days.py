"""F2: the third day tab shows that day's rows, and session › Back keeps the day.

DATA-17, SCHED-01, D-18, D-192. On the recorded feed, the day before the conference:
the Schedule opens on its first day; its third tab lists the third day's rows in their
place of the first day's. A session opened from there is a pushed View, and Back
returns to the third day, not to the first (the day is kept in `ViewMemory`, D-18).
"""

import flet.testing as ftt

from tests.ui.developer import before_conference, fresh_start
from tests.ui.helpers import (
    open_tab,
    remote,
    screenshot,
    tap_back_arrow,
    tap_id,
    wait_for_id,
    wait_for_tooltip,
)
from tests.ui.targets import day_rows, recorded, row_id, saveable

DAY = 2
"""The tab the flow switches to: the third day, past the tutorial days."""


async def test_switch_days_keeps_selection(
    flet_app: ftt.FletTestApp, feed_url: str
) -> None:
    """The third tab shows its day's rows in place of the first's; Back keeps it."""
    t = remote(flet_app)
    await fresh_start(t, now=before_conference(), feed_url=feed_url)
    first_day = row_id("schedule", day_rows(recorded(), 0)[0])
    third_day = [row_id("schedule", s) for s in day_rows(recorded(), DAY)[:2]]
    session = saveable(day_rows(recorded(), DAY))[0]

    # The first day shows; the third tab replaces its rows with the third day's.
    await open_tab(t, "schedule")
    await wait_for_id(t, first_day)
    await tap_id(t, f"schedule.day_tab.{DAY}")
    for row in third_day:
        await wait_for_id(t, row)
    await wait_for_id(t, first_day, gone=True)
    await screenshot("f2-third-day")

    # A session of that day, then Back: the Schedule is still on the third day.
    await tap_id(t, row_id("schedule", session))
    await wait_for_id(t, "schedule.title", gone=True)  # the push has finished
    await wait_for_id(t, "session.title")
    await tap_back_arrow(t)
    await wait_for_id(t, "schedule.title")
    await wait_for_tooltip(t, "Back", gone=True)  # the pop has finished
    for row in third_day:
        await wait_for_id(t, row)
    assert (await t.find_by_semantics_identifier(first_day)).count == 0
    await screenshot("f2-back-on-third-day")
