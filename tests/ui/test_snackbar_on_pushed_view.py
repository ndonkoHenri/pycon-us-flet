"""A SnackBar shown from a pushed View is seen on that View, and its Undo works (#197).

Session detail is a pushed View (D-141, D-144). Unstarring there shows "Removed from
My schedule" with Undo (D-30, D-184), through ``page.show_dialog`` like every SnackBar
in the app. Finders skip offstage widgets (testing-and-quality.md §5.1), and the tab
root under a finished push is offstage, so finding the SnackBar's text and its Undo
proves they are drawn on the View the user is looking at (D-210, F48).
"""

import asyncio
from functools import cache

import flet.testing as ftt
from flet.testing.remote_tester import RemoteTester

from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.queries import days
from pycon_us.core.timeline import timeline
from pycon_us.ui.semantics import semantics_key
from pycon_us.ui.session_rows import is_notice
from tests.ui.helpers import (
    STEP,
    answer_primer_not_now,
    remote,
    screenshot,
    start_app,
    tap_back_arrow,
    tap_id,
    tap_text,
    wait_for_id,
    wait_for_text,
    wait_for_tooltip,
)

SETTLE_SECONDS = 1.0
"""Time for a tap's handler to run on a slow debug build before the next tap, and for
the SnackBar's 250 ms entrance: a tap on Undo while the bar slides in misses it (on
the iOS simulator the first try tapped a bar 5 dp tall)."""

REMOVED = "Removed from My schedule"
"""The removal's SnackBar (``ui.favorite.REMOVED``), written out as a person reads it."""


@cache
def first_saveable() -> str:
    """The identifier of the first session on the first day that has a star.

    Outside the conference the Schedule opens on its first day (D-192), and a test
    build is a fresh install with no remembered day, so this row is near the top of the
    list: a flow cannot scroll (F21). Taken from the bundled snapshot, not written out,
    so a new year or snapshot moves the flow with it; a notice (the registration desk)
    has no star (D-31) and is skipped.
    """
    year = load_year()
    info = year.conference
    data = process(year.read_snapshot().raw, year.feed_settings)
    first_day = days(data, info.first_day, info.last_day)[0]
    session = next(
        session
        for slot in timeline(data, first_day, ())
        for session in slot.sessions
        if not is_notice(session, info)
    )
    return f"schedule.session.{semantics_key(session.id)}"


async def test_snackbar_from_session_detail_shows_on_session_detail(
    flet_app: ftt.FletTestApp,
) -> None:
    """Unstarring on session detail shows its SnackBar there, and its Undo works.

    Undo saves the session again, so the next tap shows the bar once more; Back then
    returns to the Schedule.
    """
    t = remote(flet_app)
    await start_app(t)

    # Schedule › a session: a pushed View, with the back arrow and no bar (D-144).
    await tap_id(t, "app.nav.schedule")
    await tap_id(t, first_saveable())
    await wait_for_id(t, "schedule.title", gone=True)  # the push has finished
    await wait_for_tooltip(t, "Back")

    # Star, then unstar: the removal's SnackBar is on this View, not the root's. The
    # star's tooltip is no finder target (a Tooltip object), so the add gets a moment.
    await tap_id(t, "session.favorite")
    await answer_primer_not_now(t)
    await settle(t)
    await tap_id(t, "session.favorite")
    await wait_for_text(t, REMOVED)

    # Its Undo is reachable there and saves the session again: once the bar has gone,
    # the next tap removes it, so the bar comes back (D-30).
    await settle(t)  # the bar has slid in; it stays 4 s from its start
    await tap_text(t, "Undo")
    await wait_for_text(t, REMOVED, gone=True)
    await tap_id(t, "session.favorite")
    await wait_for_text(t, REMOVED)
    await settle(t)  # a capture right after the find can predate the bar's first frame
    await screenshot("snackbar-on-session-detail")

    await tap_back_arrow(t)
    await wait_for_id(t, "schedule.title")


async def settle(t: RemoteTester) -> None:
    """Wait ``SETTLE_SECONDS`` of real time, then let the app draw a frame.

    ``RemoteTester.pump(duration)`` does not wait that long on a device: the tap that
    followed ``pump(1 s)`` landed while the SnackBar was still sliding in.
    """
    await asyncio.sleep(SETTLE_SECONDS)
    await t.pump(STEP)
