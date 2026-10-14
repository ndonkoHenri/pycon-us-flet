"""F5: session › speaker › session, and each Back pops one View (#279's fix).

SESS-12, SHELL-16, D-17, D-141, D-144. On the recorded feed: a session near the top of
a Schedule day whose speaker has another session; its speaker row pushes the speaker's
page, whose row of that other session pushes it. The back arrow then returns to the
speaker, to the first session and to the Schedule, one View at a time, each known by
its title. On Android the Back key on the Schedule root goes to Now (D-142); iOS has no
Back key, and its edge swipe stays a manual check.
"""

from functools import cache

import flet.testing as ftt
from flet.testing.remote_tester import RemoteTester

from pycon_us.core.models import Session, Speaker
from pycon_us.core.speakers import speaker_sessions
from pycon_us.ui.semantics import semantics_key
from tests.ui.developer import before_conference, fresh_start
from tests.ui.helpers import (
    PLATFORM,
    open_tab,
    press_system_back,
    remote,
    screenshot,
    tap_back_arrow,
    tap_id,
    wait_for_id,
    wait_for_text,
    wait_for_tooltip,
)
from tests.ui.targets import conference_days, day_rows, recorded, row_id, saveable

TOP_ROWS = 3
"""How far down a day the first session may be: its row must be on screen (F21)."""


@cache
def drill() -> tuple[int, Session, Speaker, Session]:
    """Return the day tab, the first session, its speaker and the speaker's next session.

    The first day, in order, with a session among its first ``TOP_ROWS`` sessions whose
    speaker is in the directory and has another session, listed after it on their page
    (``speaker_sessions()``), so near its top too.
    """
    data = recorded()
    for index in range(len(conference_days(data))):
        for first in saveable(day_rows(data, index))[:TOP_ROWS]:
            for speaker_id in first.speaker_ids:
                if speaker_id not in data.speakers:
                    continue
                listed = [
                    s
                    for day in speaker_sessions(data, speaker_id)
                    for s in day.sessions
                ]
                later = listed[listed.index(first) + 1 :]
                if later:
                    return index, first, data.speakers[speaker_id], later[0]
    raise AssertionError("No session near a day's top has a speaker with another")


async def test_drill_back_one_step(flet_app: ftt.FletTestApp, feed_url: str) -> None:
    t = remote(flet_app)
    await fresh_start(t, now=before_conference(), feed_url=feed_url)
    day, first, speaker, second = drill()

    # Schedule › the day › the session.
    await open_tab(t, "schedule")
    await tap_id(t, f"schedule.day_tab.{day}")
    await tap_id(t, row_id("schedule", first))
    await wait_for_id(t, "schedule.title", gone=True)  # the push has finished
    await shows_session(t, first)

    # › its speaker › the speaker's other session: one pushed View each (D-17).
    await tap_id(t, f"session.speaker.{semantics_key(speaker.id)}")
    await shows_speaker(t, speaker)
    await tap_id(t, f"speaker.session.{semantics_key(second.id)}")
    await shows_session(t, second)
    await screenshot("f5-second-session")

    # Back, Back, Back: the speaker, the first session, the Schedule on that day.
    await tap_back_arrow(t)
    await shows_speaker(t, speaker)
    await tap_back_arrow(t)
    await shows_session(t, first)
    await tap_back_arrow(t)
    await wait_for_id(t, "schedule.title")
    await wait_for_tooltip(t, "Back", gone=True)  # a root has none; the pop is over
    await wait_for_id(t, row_id("schedule", first))
    await screenshot("f5-back-on-schedule")

    if PLATFORM == "android":
        # The Back key on a root other than Now goes to Now (D-142).
        await press_system_back(t)
        await wait_for_id(t, "now.title")


async def shows_session(t: RemoteTester, session: Session) -> None:
    """Wait until session detail shows ``session``: its title node and its name."""
    await wait_for_id(t, "session.title")
    await wait_for_text(t, session.name)
    await wait_for_id(t, "speaker.title", gone=True)  # a speaker's page has gone


async def shows_speaker(t: RemoteTester, speaker: Speaker) -> None:
    """Wait until the speaker's page shows: its title node and their name."""
    await wait_for_id(t, "speaker.title")
    await wait_for_text(t, speaker.name)
    await wait_for_id(t, "session.title", gone=True)  # no session's page is on top
