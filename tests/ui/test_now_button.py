"""On a second display still at now, the Schedule offers no "Now" button (#1079).

SCHED-15, D-204, D-499. With the clock on the opening day, the Schedule's first display jumps to
now and hides the button. Another tab and back puts the list back where it was, so the
button stays hidden: it's for when the list isn't showing where now is.
"""

import asyncio

import flet.testing as ftt
from flet.testing.remote_tester import RemoteTester

from tests.ui.developer import fresh_start
from tests.ui.helpers import STEP, open_tab, remote, screenshot, wait_for_id
from tests.ui.targets import conference_days, recorded

OPENING_DAY = 2
"""The conference's first main day, with a session under way at `AT`."""

AT = "09:30"
"""The fake clock's time on that day, in conference time."""

JUMP_NOW = "schedule.jump_now"
"""The "Now" button's semantics identifier."""

LANDED_SECONDS = 5.0
"""Real time the first jump gets to land, pumping: the button also hides while the jump is
on its way, so its absence doesn't say it has landed, and a `Finder` can't read a list's
offset (§5.4). The test binding draws only when pumped, so a plain sleep starves a jump's
400 ms scroll where animations are on, as on the iOS simulator: the jump gives up as
"still", and the scroll's late end moves the button."""


async def land(t: RemoteTester) -> None:
    """Pump for `LANDED_SECONDS` of real time, so the first jump's scroll runs and ends."""
    for _ in range(int(LANDED_SECONDS / 0.3)):
        await asyncio.sleep(0.3)
        await t.pump(STEP)


async def test_a_second_display_at_now_shows_no_now_button(
    flet_app: ftt.FletTestApp, feed_url: str
) -> None:
    """Neither the first display nor the one after another tab offers "Now" (D-204)."""
    t = remote(flet_app)
    day = conference_days(recorded())[OPENING_DAY]
    await fresh_start(t, now=f"{day.isoformat()} {AT}", feed_url=feed_url)
    await open_tab(t, "schedule")
    await wait_for_id(t, JUMP_NOW, gone=True)
    await land(t)
    await wait_for_id(t, JUMP_NOW, gone=True)
    await screenshot("now-button-first-display")
    await open_tab(t, "more")
    await open_tab(t, "schedule")
    await wait_for_id(t, JUMP_NOW, gone=True)
    await screenshot("now-button-second-display")
