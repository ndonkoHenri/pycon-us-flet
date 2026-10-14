"""F3: a query typed without its accent finds a session and a speaker; Back keeps it.

NEW-02, D-19, D-46, D-193. On the recorded feed, search opens from the Schedule's app
bar, in the Sessions scope the Schedule gives it; a speaker's name typed without its
accent ("muller" for "Müller") finds their session, since search folds accents
(D-46). The Speakers chip keeps the query and finds the speaker. A result is a pushed
View on top of search, and Back returns to search with the query, the scope and the
result in place (D-18, D-141). One scope at a time, so each result is near the top:
the keyboard covers the screen's lower half, and a flow cannot scroll (U35).
"""

from functools import cache

import flet.testing as ftt

from pycon_us.core.models import Session, Speaker
from pycon_us.core.queries import fold
from pycon_us.core.search import search, search_index
from pycon_us.ui.semantics import semantics_key
from tests.ui.developer import before_conference, fresh_start
from tests.ui.helpers import (
    enter_text_id,
    open_tab,
    remote,
    screenshot,
    tap_back_arrow,
    tap_id,
    tap_tooltip,
    wait_for_id,
    wait_for_text,
)
from tests.ui.targets import recorded


@cache
def accent_query() -> tuple[str, Session, Speaker]:
    """Return a query, the one session and the one speaker it finds in the recorded feed.

    The query is a word of a speaker's name folded to plain letters ("muller"), so it
    differs from the name as shown; it is the first such word that finds exactly that
    speaker and one session, so both results are on screen without scrolling (F21).
    """
    data = recorded()
    index = search_index(data)
    for speaker in data.speakers.values():
        for word in speaker.name.split():
            query = fold(word)
            if query == word.lower():  # no accent to fold
                continue
            found = search(index, query)
            sessions = [s for day in found.sessions for s in day.sessions]
            if len(sessions) == 1 and found.speakers == (speaker,) and not found.rooms:
                return query, sessions[0], speaker
    raise AssertionError("No accented speaker name finds one session and its speaker")


async def test_search_finds_and_keeps_query(
    flet_app: ftt.FletTestApp, feed_url: str
) -> None:
    t = remote(flet_app)
    await fresh_start(t, now=before_conference(), feed_url=feed_url)
    query, session, speaker = accent_query()
    session_row = f"search.session.{semantics_key(session.id)}"
    speaker_row = f"search.speaker.{semantics_key(speaker.id)}"

    # Search from the Schedule, in its Sessions scope: the folded query finds the session.
    await open_tab(t, "schedule")
    await tap_tooltip(t, "Search")
    await enter_text_id(t, "search.field", query)
    await wait_for_id(t, session_row)
    await screenshot("f3-session-found")

    # The Speakers chip keeps the query and finds the speaker.
    await tap_id(t, "search.scope.speakers")
    await wait_for_id(t, speaker_row)
    await wait_for_id(t, session_row, gone=True)

    # The speaker, then Back: search again, with the query and the speaker.
    await tap_id(t, speaker_row)
    await wait_for_id(t, "search.field", gone=True)  # the push has finished
    await wait_for_id(t, "speaker.title")
    await wait_for_text(t, speaker.name)
    await tap_back_arrow(t)
    await wait_for_id(t, "search.field")
    await wait_for_text(t, query)  # the field still holds it
    await wait_for_id(t, speaker_row)
    await screenshot("f3-back-keeps-query")
