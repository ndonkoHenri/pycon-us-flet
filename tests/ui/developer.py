"""Set the scene of a UI flow from the Developer screen, as a person would (D-73, D-78).

`open_developer()` opens the screen through About this app's link, unlocking it with 7
taps on the version row the first time (D-187). `fresh_start()` sets the fake clock
and the feed URL there, refreshes from that feed, and returns to Now, so a flow runs on
a known moment and a recorded feed rather than on the live one (D-223).
`apply_options()`, `reopen_developer()` and `refresh_now()` are its steps, which a
flow can take on its own (F1 sets an unreachable feed URL). The inventory is
testing-and-quality.md §5.2.
"""

from datetime import timedelta
from pathlib import Path

from flet.testing import Finder
from flet.testing.remote_tester import RemoteTester

from pycon_us.config import load_year
from pycon_us.screens.about_app import UNLOCK_TAPS
from pycon_us.ui.actions import refreshed
from pycon_us.ui.status_strip import UPDATING
from tests.ui.helpers import (
    DEVICE,
    PLATFORM,
    adb,
    enter_text_id,
    open_tab,
    run,
    start_app,
    tap_back_arrow,
    tap_id,
    tap_until,
    wait_for_id,
    wait_for_text,
    wait_for_tooltip,
)

REFRESH_TIMEOUT = 60.0
"""Seconds a Refresh now may take: the year's feed over the device's network, or the
app's 10 s feed timeout (`feed_api.FEED_TIMEOUT`) when no answer comes."""

UPDATED = refreshed(None)[0]
"""What Refresh now says once it has published the feed: "Schedule updated from the
feed." """

NO_ANSWER = refreshed("offline")[0]
"""What Refresh now says when the feed did not answer, the app's own words."""


LINK_PREFIX = "confcompanion://app"
"""Every deep link's start; the scheme and host are `[tool.flet.deep_linking]`'s."""

ABOUT_APP_ROUTE = "/more/app"
"""About this app's route."""

ABOUT_APP_LINK = f"{LINK_PREFIX}{ABOUT_APP_ROUTE}"
"""About this app's deep link."""

OPEN_LINK_FLOW = Path(__file__).parents[2] / "maestro" / "subflows" / "open_link.yaml"
"""The Maestro flow that opens a link on iOS, and taps the simulator's Open prompt (F31)."""


def before_conference() -> str:
    """Return 09:00 the day before the conference, as the fake clock field takes it.

    Conference time, `YYYY-MM-DD HH:MM` (the field's helper). Outside the conference
    the Schedule opens on its first day, at the top, with no jump to now (D-192, D-204):
    the rows a flow taps are on screen, since a flow cannot scroll (F21).
    """
    day = load_year().conference.first_day - timedelta(days=1)
    return f"{day.isoformat()} 09:00"


async def open_route(route: str) -> None:
    """Open an app route by its deep link, from the host.

    About this app's row is below the fold of the More root on every phone, the iPhone
    17 Pro Max's too, and so is Settings', and a flow cannot scroll to either:
    `RemoteTester` has no drag (U35, #288), and the test binding drops the device's own
    touches, so a host-side swipe doesn't reach the app either. `adb` sends the link on
    Android, where Maestro reading the accessibility tree would change what the app
    does (F72). `simctl openurl` asks "Open in …?" (F31), so Maestro sends it on iOS.

    Args:
        route: The route path, e.g. `/more/app`.
    """
    if PLATFORM == "android":
        intent = ("shell", "am", "start", "-a", "android.intent.action.VIEW")
        await run(adb(), "-s", DEVICE, *intent, "-d", f"{LINK_PREFIX}{route}")
    else:
        env = ("-e", f"ROUTE={route}")
        await run("maestro", "--device", DEVICE, "test", *env, str(OPEN_LINK_FLOW))


async def open_about_app() -> None:
    """Open About this app by its deep link, from the host (`open_route()`)."""
    await open_route(ABOUT_APP_ROUTE)


async def open_developer(t: RemoteTester) -> None:
    """Open Developer options from a tab root, unlocking them first if they are locked.

    More › About this app (`open_about_app()`) › the version row 7 times › Developer
    options, the row the unlock adds there (`about_app.developer`); once unlocked, the
    taps are skipped. The View under Developer is the More root, since the row navigates
    to `/more/developer`.
    """
    await wait_for_tooltip(t, "Back", gone=True)  # on a root, any pop to it finished
    await open_tab(t, "more")
    await open_about_app()
    await wait_for_id(t, "more.title", gone=True)  # About has covered the root
    if not (await t.find_by_semantics_identifier("about_app.developer")).count:
        for _ in range(UNLOCK_TAPS):
            await tap_id(t, "about_app.version")
    await tap_id(t, "about_app.developer")
    await wait_for_id(t, "developer.apply")


async def reopen_developer(t: RemoteTester) -> None:
    """Leave Developer options for the More root and open them again.

    The keyboard that typing left up goes with the View, so the Data rows are on
    screen again, and Refresh now's outcome line starts empty.
    """
    await tap_back_arrow(t)
    await wait_for_id(t, "more.title")
    await open_developer(t)


async def refresh_now(t: RemoteTester, outcome: str | None = None) -> None:
    """Tap Developer's Refresh now until it starts, and wait until it says how it ended.

    A tap can be lost: while the View slides in, the row's centre can lie off the screen
    (#1111), so one tap would leave a flow waiting for words that never come. So the tap
    is repeated until the row says it is refreshing, or the outcome line shows, for a
    refresh too quick to see. A second tap changes nothing: the row is disabled while
    it runs, and the outcome ends the tapping.

    The line under the Data rows (`developer.data_outcome`) is hidden from the tap
    until the refresh ends, but a Refresh now on a screen that already says something
    could be read before its own result: open Developer afresh first
    (`reopen_developer()`), which starts with no outcome.

    Args:
        t: The tester.
        outcome: The words to wait for; None for any outcome, e.g. when it depends on
            the device's network.
    """

    async def started() -> Finder:
        said = await t.find_by_semantics_identifier("developer.data_outcome")
        return said if said.count else await t.find_by_text(UPDATING)

    await tap_until(
        t,
        lambda: t.find_by_semantics_identifier("developer.refresh_now"),
        started,
        "Refresh now",
    )
    if outcome is None:
        await wait_for_id(t, "developer.data_outcome", timeout=REFRESH_TIMEOUT)
    else:
        await wait_for_text(t, outcome, timeout=REFRESH_TIMEOUT)


async def apply_options(
    t: RemoteTester, *, now: str | None = None, feed_url: str | None = None
) -> None:
    """Type the fake clock and the feed URL into Developer, tap Apply and wait for it.

    The feed URL is typed last, also when it stays empty: the keyboard is up then, and
    the URL field keeps the Apply row under it in sight (`APPLY_IN_SIGHT`), where
    the clock field, higher up, leaves it under the keyboard. A flow cannot close the
    keyboard: `RemoteTester` has no keyboard action (U35).

    Args:
        t: The tester, on Developer options.
        now: The fake clock's start (`before_conference()`); None leaves the field.
        feed_url: The feed URL; None empties the field, for the year's feed.
    """
    if now is not None:
        await enter_text_id(t, "developer.fake_clock", now)
    await enter_text_id(t, "developer.feed_url", feed_url or "")
    # The list may still be scrolling the field into sight above the keyboard, and a
    # tap on a moving list only stops it: tap again until Apply says what it did. A
    # second Apply of the same values changes nothing.
    await tap_until(
        t,
        lambda: t.find_by_semantics_identifier("developer.apply"),
        lambda: t.find_by_text_containing("^Applied: "),
        "Apply",
    )


async def fresh_start(
    t: RemoteTester, *, now: str | None = None, feed_url: str | None = None
) -> None:
    """Wait for the app's start, set the clock and the feed in Developer, return to Now.

    A test build is a fresh install (testing-and-quality.md §5.1): it starts on Now with
    the bundled snapshot, and refreshes from the year's feed at once. A Refresh now that
    found that refresh still running after Apply would join it, and publish nothing,
    since a refresh from a URL no longer in effect writes nothing (D-244). So the first
    Refresh now only lets it end. Developer is then opened afresh, so the second one's
    words are its own, and that one refreshes from the feed URL just applied.

    Args:
        t: The tester.
        now: The fake clock's start (`before_conference()`); None keeps real time.
        feed_url: A feed for the app to refresh from now, e.g. the `feed_url`
            fixture's recorded feed; None keeps the year's.
    """
    await start_app(t)
    await open_developer(t)
    await refresh_now(t)  # any outcome: the launch's refresh has ended
    await apply_options(t, now=now, feed_url=feed_url)
    if feed_url is not None:
        await reopen_developer(t)
        await refresh_now(t, UPDATED)
    await tap_back_arrow(t)
    await wait_for_id(t, "more.title")
    await wait_for_tooltip(t, "Back", gone=True)  # the pop has finished
    await open_tab(t, "now")
