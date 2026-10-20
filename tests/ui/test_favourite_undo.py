"""F4: a starred session is in My schedule; unstarred there, Undo brings it back.

NEW-01, D-30, D-184, D-191. On the recorded feed, the day before the conference: the
first session with a star on the Schedule's first day is starred, and My schedule lists
it. Its star there removes it at once, with "Removed from My schedule" and Undo; Undo
saves it again, and its row returns.
"""

import flet.testing as ftt

from pycon_us.ui.badges import REMOVED
from tests.ui.developer import before_conference, fresh_start
from tests.ui.helpers import (
    open_tab,
    remote,
    screenshot,
    tap_id,
    tap_until,
    wait_for_id,
    wait_for_text,
)
from tests.ui.targets import day_rows, recorded, row_id, saveable, star_id


async def test_favourite_with_undo(flet_app: ftt.FletTestApp, feed_url: str) -> None:
    """A starred session is in My schedule; unstarred there, Undo brings it back."""
    t = remote(flet_app)
    await fresh_start(t, now=before_conference(), feed_url=feed_url)
    session = saveable(day_rows(recorded(), 0))[0]
    saved_row = row_id("my_schedule", session)

    # Star it on the Schedule; My schedule lists it.
    await open_tab(t, "schedule")
    await tap_id(t, star_id("schedule", session))
    await open_tab(t, "my_schedule")
    await wait_for_id(t, saved_row)
    await screenshot("f4-saved")

    # Unstar it there: the row goes, the SnackBar offers Undo (D-30).
    await tap_id(t, star_id("my_schedule", session))
    await wait_for_text(t, REMOVED)
    await wait_for_id(t, saved_row, gone=True)
    await screenshot("f4-removed-with-undo")

    # Undo saves it again, and the row is back.
    await tap_until(
        t,
        lambda: t.find_by_text("Undo"),
        lambda: t.find_by_semantics_identifier(saved_row),
        "Undo",
    )
    await screenshot("f4-undone")
