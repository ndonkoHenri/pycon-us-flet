"""The shell starts on Welcome, then Now; every tab shows its root; Back pops one step.

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
from pycon_us.core.timefmt import day_tab_label
from tests.ui.helpers import (
    PLATFORM,
    START_TIMEOUT,
    press_system_back,
    remote,
    screenshot,
    start_app,
    tap_back_arrow,
    tap_first_text,
    tap_id,
    tap_text,
    wait_for_id,
    wait_for_text,
    wait_for_tooltip,
)

TABS = [  # (the bar's destination, its root's title), in the bar's order (D-13)
    ("app.nav.now", "now.title"),
    ("app.nav.schedule", "schedule.title"),
    ("app.nav.my_schedule", "my_schedule.title"),
    ("app.nav.map", "map.title"),
    ("app.nav.more", "more.title"),
]


@cache
def first_speakers() -> list[str]:
    """The names the Speakers page lists first: the directory sorted as search folds.

    Taken from the bundled snapshot. On a device with a network, a refresh replaces it
    with the live feed, whose speakers change between snapshot refreshes, so the flow
    taps whichever of the first few is on screen. P1-30's ``fresh_start()`` will serve
    a recorded feed instead.
    """
    year = load_year()
    data = process(year.read_snapshot().raw, year.feed_settings)
    return sorted((speaker.name for speaker in data.speakers.values()), key=fold)[:5]


async def test_shell_starts(flet_app: ftt.FletTestApp) -> None:
    """The app starts on Now, each tab shows its root, and Back pops one step."""
    t = remote(flet_app)

    # A fresh install opens Welcome, without the bar (D-287); Get started goes on.
    await wait_for_id(t, "welcome.start", timeout=START_TIMEOUT)
    assert (await t.find_by_semantics_identifier("app.nav.now")).count == 0
    await screenshot("00-welcome")
    await start_app(t)

    # Get started lands on Now with the bottom bar and its five tabs (D-13, D-14).
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
            # The Schedule: a tab per conference day, the first one "Wed 13" (#86).
            await wait_for_id(t, "schedule.day_tab.0")
            first_day = load_year().conference.first_day
            await wait_for_text(t, day_tab_label(first_day))
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
    await tap_first_text(t, first_speakers())
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
