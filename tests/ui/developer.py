"""Set the scene of a UI flow from the Developer screen, as a person would (D-73, D-78).

``open_developer()`` unlocks the screen with 7 taps on About this app's version row the
first time, and opens it from the More list once it is unlocked (D-187). ``fresh_start()``
sets the fake clock and the feed URL there, refreshes from that feed, and returns to Now,
so a flow runs on a known moment and a recorded feed rather than on the live one.
``apply_options()`` and ``refresh_now()`` are its steps, which a flow can take on its
own (F1 sets an unreachable feed URL). The inventory is testing-and-quality.md §5.2.
"""

from datetime import timedelta

from flet.testing.remote_tester import RemoteTester

from pycon_us.config import load_year
from pycon_us.screens.about_app import UNLOCK_TAPS
from pycon_us.screens.developer_data import refreshed
from tests.ui.helpers import (
    START_TIMEOUT,
    enter_text_id,
    tap_back_arrow,
    tap_id,
    wait_for,
    wait_for_id,
    wait_for_text,
    wait_for_tooltip,
)

REFRESH_TIMEOUT = 60.0
"""Seconds a Refresh now may take: the year's feed over the device's network, or the
app's 10 s feed timeout (``api.FEED_TIMEOUT``) when no answer comes."""

UPDATED = refreshed(None)[0]
"""What Refresh now says once it has published the feed: "Schedule updated from the
feed." """

NO_ANSWER = refreshed("offline")[0]
"""What Refresh now says when the feed did not answer, the app's own words."""


def before_conference() -> str:
    """Return 09:00 the day before the conference, as the fake clock field takes it.

    Conference time, ``YYYY-MM-DD HH:MM`` (the field's helper). Outside the conference
    the Schedule opens on its first day, at the top, with no jump to now (D-192, D-204):
    the rows a flow taps are on screen, since a flow cannot scroll (F21).
    """
    day = load_year().conference.first_day - timedelta(days=1)
    return f"{day.isoformat()} 09:00"


async def open_developer(t: RemoteTester) -> None:
    """Open Developer options from a tab root, unlocking them first if they are locked.

    More › About this app › the version row 7 times › Developer options, the row the
    unlock adds there (``about_app.developer``); once unlocked, the More list's own
    Developer options row (``more.developer``). Either way the View under Developer is
    the More root, since both rows navigate to ``/more/developer``.
    """
    await wait_for_tooltip(t, "Back", gone=True)  # on a root, any pop to it finished
    await tap_id(t, "app.nav.more")
    await wait_for_id(t, "more.title")
    if (await t.find_by_semantics_identifier("more.developer")).count:
        await tap_id(t, "more.developer")
    else:
        await tap_id(t, "more.app")
        await wait_for_id(t, "more.title", gone=True)  # About has replaced the root
        for _ in range(UNLOCK_TAPS):
            await tap_id(t, "about_app.version")
        await tap_id(t, "about_app.developer")
    await wait_for_id(t, "developer.apply")


async def refresh_now(t: RemoteTester, outcome: str | None = None) -> None:
    """Tap Developer's Refresh now and wait until it says how the refresh ended.

    The line under the Data rows (``developer.data_outcome``) is hidden from the tap
    until the refresh ends, but a Refresh now on a screen that already says something
    could be read before its own result: open Developer afresh first, which starts
    with no outcome.

    Args:
        t: The tester.
        outcome: The words to wait for; None for any outcome, e.g. when it depends on
            the device's network.
    """
    await tap_id(t, "developer.refresh_now")
    if outcome is None:
        await wait_for_id(t, "developer.data_outcome", timeout=REFRESH_TIMEOUT)
    else:
        await wait_for_text(t, outcome, timeout=REFRESH_TIMEOUT)


async def apply_options(
    t: RemoteTester, *, now: str | None = None, feed_url: str | None = None
) -> None:
    """Type the fake clock and the feed URL into Developer, tap Apply and wait for it.

    Args:
        t: The tester, on Developer options.
        now: The fake clock's start (``before_conference()``); None leaves the field.
        feed_url: The feed URL; None leaves the field.
    """
    if now is not None:
        await enter_text_id(t, "developer.fake_clock", now)
    if feed_url is not None:
        await enter_text_id(t, "developer.feed_url", feed_url)
    await tap_id(t, "developer.apply")
    await wait_for(
        t, lambda: t.find_by_text_containing("^Applied: "), "Apply's outcome"
    )


async def fresh_start(
    t: RemoteTester, *, now: str | None = None, feed_url: str | None = None
) -> None:
    """Wait for the app's start, set the clock and the feed in Developer, return to Now.

    A test build is a fresh install (testing-and-quality.md §5.1): it starts on Now with
    the bundled snapshot, and refreshes from the year's feed at once. A Refresh now that
    found that refresh still running would join it, and so publish the year's feed,
    since a running refresh keeps its URL (``Conference.set_feed_url``). So the first
    Refresh now only lets it end. Developer is then opened afresh, so the second one's
    words are its own, and that one refreshes from the feed URL just applied.

    Args:
        t: The tester.
        now: The fake clock's start (``before_conference()``); None keeps real time.
        feed_url: A feed for the app to refresh from now, e.g. the ``feed_url``
            fixture's recorded feed; None keeps the year's.
    """
    await wait_for_id(t, "now.title", timeout=START_TIMEOUT)
    await open_developer(t)
    await refresh_now(t)  # any outcome: the launch's refresh has ended
    await apply_options(t, now=now, feed_url=feed_url)
    if feed_url is not None:
        await tap_back_arrow(t)
        await open_developer(t)
        await refresh_now(t, UPDATED)
    await tap_back_arrow(t)
    await wait_for_id(t, "more.title")
    await wait_for_tooltip(t, "Back", gone=True)  # the pop has finished
    await tap_id(t, "app.nav.now")
    await wait_for_id(t, "now.title")
