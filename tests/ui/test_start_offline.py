"""F1: with a feed that never answers, the Schedule keeps its rows and says it is offline.

NEW-03, DATA-02, SCHED-14, D-32, D-39. Developer's feed URL is set to a feed on the
laptop that takes each request and hangs up unanswered (the `silent_feed` fixture),
as a person would set it, and Refresh now says the feed did not answer. The Schedule
still lists the bundled snapshot's rows, with no error screen, and its status strip says
"Offline"; the strip's Refresh asks the feed again, which the feed holds until the flow
lets it hang up, so the flow sees that refresh run and end, and the rows stay. A device
with a network may have refreshed the snapshot from the year's feed before the flow got
to Developer: the rows are the same sessions, so the flow finds them either way. A cold
start in airplane mode, from the snapshot itself, needs a relaunch, which a flow cannot
do; it stays on the device checklist (D-79).
"""

import flet.testing as ftt
from flet.testing.remote_tester import RemoteTester

from tests.ui.developer import (
    NO_ANSWER,
    apply_options,
    before_conference,
    fresh_start,
    open_developer,
    refresh_now,
    reopen_developer,
)
from tests.ui.feeds import SilentFeed
from tests.ui.helpers import (
    open_tab,
    remote,
    screenshot,
    tap_back_arrow,
    tap_until,
    wait_for,
    wait_for_id,
    wait_for_text,
    wait_for_tooltip,
    wait_until,
)
from tests.ui.targets import bundled, day_rows, row_id

OFFLINE = "^Offline · "
"""The start of the strip's line after a refresh with no answer (`strip_line()`)."""

UPDATING = "Updating the schedule…"
"""The strip's line while a refresh the user asked for runs (`strip_line()`)."""


async def test_start_offline_shows_schedule(
    flet_app: ftt.FletTestApp, silent_feed: SilentFeed
) -> None:
    """With a feed that never answers, the Schedule keeps its rows and says Offline.

    Developer's "Refresh now" gets no answer; the strip's Refresh asks the feed again
    and says it is updating until the feed hangs up, then Offline again, and the rows
    stay.
    """
    t = remote(flet_app)
    await fresh_start(t, now=before_conference())

    # Developer: the feed URL a person types, then Refresh now, which gets no answer.
    await open_developer(t)
    await apply_options(t, feed_url=silent_feed.url)
    await screenshot("f1-developer-applied")  # on iOS, Apply in sight over the keyboard
    await reopen_developer(t)  # the keyboard down, the Data rows in sight
    await refresh_now(t, NO_ANSWER)
    assert silent_feed.requests, "Refresh now asked the silent feed"
    await screenshot("f1-developer-no-answer")
    await tap_back_arrow(t)
    await wait_for_tooltip(t, "Back", gone=True)

    # The Schedule: the first day's rows, and the strip says offline (D-32).
    first_rows = [row_id("schedule", session) for session in day_rows(bundled(), 0)[:3]]
    await open_tab(t, "schedule")
    for row in first_rows:
        await wait_for_id(t, row)
    await wait_for_offline_strip(t)
    assert (await t.find_by_semantics_identifier("schedule.no_data")).count == 0
    await screenshot("f1-schedule-offline")

    # The strip's Refresh asks the feed again (D-39). The feed holds the request, so
    # the strip says it is updating until the feed hangs up, and the flow knows the
    # tap took: the "Offline" line was already there before it.
    asked = silent_feed.requests
    silent_feed.hold()
    await tap_until(
        t,
        lambda: t.find_by_text("Refresh"),
        lambda: t.find_by_text(UPDATING),
        "the strip's Refresh",
    )
    await wait_until(
        t, lambda: silent_feed.requests > asked, "the strip's request to the feed"
    )
    silent_feed.hang_up()
    # No answer again: the strip says offline again, and the rows stay.
    await wait_for_text(t, UPDATING, gone=True)
    await wait_for_offline_strip(t)
    for row in first_rows:
        await wait_for_id(t, row)


async def wait_for_offline_strip(t: RemoteTester) -> None:
    """Wait until the status strip (`app.status`) says the app is offline."""
    await wait_for_id(t, "app.status")
    await wait_for(t, lambda: t.find_by_text_containing(OFFLINE), "the offline strip")
