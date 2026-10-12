"""The shell starts on Now, every tab shows its root, and Back pops one step (P0-27).

The shell smoke flow of testing-and-quality.md §5.4 (SHELL-03, SHELL-05, NEW-03; D-13,
D-14, D-17, D-141, D-144). It asserts no offline state: the feed URL can be set only
in the Developer screen, from P1-28. More is reached through its root and its Speakers
row only, so the flow holds whatever else the More list shows (#77).
"""

from functools import cache

import flet.testing as ftt

from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.queries import fold
from pycon_us.core.timefmt import day_label
from tests.ui.helpers import (
    PLATFORM,
    press_system_back,
    remote,
    screenshot,
    tap_back_arrow,
    tap_id,
    tap_text,
    wait_for_id,
    wait_for_text,
    wait_for_tooltip,
)

START_TIMEOUT = 180.0
"""Seconds from launch to Now. Each run installs the test build afresh, so its first
launch unpacks Python before it starts, slowly on a busy host's emulator."""

TABS = [  # (the bar's destination, its root's title), in the bar's order (D-13)
    ("app.nav.now", "now.title"),
    ("app.nav.schedule", "schedule.title"),
    ("app.nav.my_schedule", "my_schedule.title"),
    ("app.nav.map", "map.title"),
    ("app.nav.more", "more.title"),
]


@cache
def first_speaker() -> str:
    """The name the Speakers page lists first: the directory sorted as search folds.

    Taken from the bundled snapshot, which the app shows until a refresh replaces it
    with the same year's feed.
    """
    year = load_year()
    data = process(year.read_snapshot().raw, year.feed_settings)
    return min((speaker.name for speaker in data.speakers.values()), key=fold)


async def test_shell_starts(flet_app: ftt.FletTestApp) -> None:
    t = remote(flet_app)

    # A cold start lands on Now with the bottom bar and its five tabs (D-13, D-14).
    await wait_for_id(t, "now.title", timeout=START_TIMEOUT)
    for nav, _ in TABS:
        assert (await t.find_by_semantics_identifier(nav)).count == 1, nav
    await screenshot("01-now")

    # Each tab shows its root, which replaces the one before (D-142).
    shown = "now.title"
    for nav, title in [*TABS[1:], TABS[0]]:
        await tap_id(t, nav)
        await wait_for_id(t, title)
        await wait_for_id(t, shown, gone=True)
        shown = title
        if title == "schedule.title":
            # The Schedule stub: where the feed came from, and the conference's days.
            await wait_for_id(t, "schedule.source")
            first_day = load_year().conference.first_day
            await wait_for_text(t, day_label(first_day))
            await screenshot("02-schedule")

    # More, its Speakers page, a speaker one drill level deeper (D-141).
    await tap_id(t, "app.nav.more")
    await wait_for_id(t, "more.title")
    await screenshot("03-more")
    await tap_text(t, "Speakers")
    await wait_for_id(t, "more.title", gone=True)
    await wait_for_tooltip(t, "Back")  # pushed Views: the back arrow, no bar (D-144)
    assert (await t.find_by_semantics_identifier("app.nav.more")).count == 0
    await screenshot("04-speakers")
    await tap_text(t, first_speaker())
    await wait_for_text(t, "Speakers", gone=True)
    await screenshot("05-speaker")

    # The back arrow pops one level at a time, to the More root and its bar (D-17).
    await tap_back_arrow(t)
    await wait_for_text(t, "Speakers")
    await tap_back_arrow(t)
    await wait_for_id(t, "more.title")
    await wait_for_id(t, "app.nav.more")
    await wait_for_tooltip(t, "Back", gone=True)  # a root has none; the pop is over
    await screenshot("06-more-again")

    if PLATFORM == "android":
        # The Back key pops a push too, and on a root other than Now goes to Now
        # (D-17, D-142). iOS has no Back key; its edge swipe is a manual check.
        await tap_text(t, "Speakers")
        await wait_for_id(t, "more.title", gone=True)
        await press_system_back(t)
        await wait_for_id(t, "more.title")
        await wait_for_tooltip(t, "Back", gone=True)  # the pop has finished
        await press_system_back(t)
        await wait_for_id(t, "now.title")
        await screenshot("07-back-key-to-now")
