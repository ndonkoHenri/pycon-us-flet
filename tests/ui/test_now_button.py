"""On a second display still at now, the Schedule offers no "Now" button (#1079).

SCHED-15, D-204, D-499. With the clock on the opening day, the Schedule's first display jumps to
now and hides the button. Another tab and back puts the list back where it was, so the
button stays hidden: it's for when the list isn't showing where now is.
"""

import flet.testing as ftt

from tests.ui.developer import fresh_start
from tests.ui.helpers import open_tab, remote, screenshot, wait_for_id
from tests.ui.targets import conference_days, recorded

OPENING_DAY = 2
"""The conference's first main day, with a session under way at `AT`."""

AT = "09:30"
"""The fake clock's time on that day, in conference time."""

JUMP_NOW = "schedule.jump_now"
"""The "Now" button's semantics identifier."""


async def test_a_second_display_at_now_shows_no_now_button(
    flet_app: ftt.FletTestApp, feed_url: str
) -> None:
    """Neither the first display nor the one after another tab offers "Now" (D-204)."""
    t = remote(flet_app)
    day = conference_days(recorded())[OPENING_DAY]
    await fresh_start(t, now=f"{day.isoformat()} {AT}", feed_url=feed_url)
    await open_tab(t, "schedule")
    await wait_for_id(t, JUMP_NOW, gone=True)
    await screenshot("now-button-first-display")
    await open_tab(t, "more")
    await open_tab(t, "schedule")
    await wait_for_id(t, JUMP_NOW, gone=True)
    await screenshot("now-button-second-display")
