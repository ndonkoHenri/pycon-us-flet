"""What the UI flows look for, taken from the feeds by the app's own code.

A flow names rows by their semantics identifiers (`<screen>.session.<key>`, D-184),
never by ids written out, so a new snapshot or a new year moves the flows with it.
`recorded()` is the recorded feed that `fresh_start()` serves (the `feed_url`
fixture), `bundled()` the snapshot the build carries; `day_rows()` lists a
Schedule day's rows in the order the screen shows them, and `row_id()` names one.
"""

from datetime import date
from functools import cache

from pycon_us.config import YEAR, load_year
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.queries import days
from pycon_us.core.timeline import timeline
from pycon_us.prefs import Prefs
from pycon_us.ui.semantics import semantics_key
from pycon_us.ui.session_rows import is_notice
from tests import feeds


@cache
def recorded() -> ConferenceData:
    """Return the recorded feed of the active year, processed as the app processes it."""
    return process(feeds.recorded(YEAR), load_year().feed_settings)


@cache
def bundled() -> ConferenceData:
    """Return the snapshot the build bundles, processed as the app processes it."""
    year = load_year()
    return process(year.read_snapshot().raw, year.feed_settings)


def conference_days(data: ConferenceData) -> tuple[date, ...]:
    """Return the days the Schedule's tabs show, in order (`schedule.day_tab.<i>`)."""
    info = load_year().conference
    return days(data, info.first_day, info.last_day)


def day_rows(data: ConferenceData, index: int) -> list[Session]:
    """Return the rows of the Schedule's day `index`, in the screen's order.

    Filtered as a fresh install filters them: its stored filter is the default one,
    which hides open spaces (`Prefs.excluded_tracks`, D-20).
    """
    day = conference_days(data)[index]
    hidden = Prefs().excluded_tracks
    return [s for slot in timeline(data, day, hidden) for s in slot.sessions]


def saveable(sessions: list[Session]) -> list[Session]:
    """Return the sessions that have a star: every one but the notices (D-31)."""
    info = load_year().conference
    return [session for session in sessions if not is_notice(session, info)]


def row_id(screen: str, session: Session) -> str:
    """Return the identifier of a session's row on `screen`: a notice's or a session's."""
    kind = "notice" if is_notice(session, load_year().conference) else "session"
    return f"{screen}.{kind}.{semantics_key(session.id)}"


def star_id(screen: str, session: Session) -> str:
    """Return the identifier of a session row's star on `screen` (D-184)."""
    return f"{screen}.favorite.{semantics_key(session.id)}"
