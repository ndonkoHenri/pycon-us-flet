"""Read-only questions screens ask of the processed feed (architecture §7.5).

Queries never change the model (SCHED-17): they return new values computed from it.
"""

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta, tzinfo

from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timefmt import time_range_label

_DASH = "–"
"""The en dash of ``timefmt`` ranges, which a screen reader may skip or call a dash."""


def days(data: ConferenceData, first_day: date, last_day: date) -> tuple[date, ...]:
    """Return the Schedule's days: every date of the conference, in order (DATA-17).

    The range runs from the conference's first day to its last (the sprints, which the
    feed has no sessions for), and widens to any schedule day outside it, so no session
    is ever without its day. A day's index is its position here, and it never moves while
    the feed and the year stay the same. Filters play no part (Ionic ignored them too).

    Args:
        data: The processed feed.
        first_day: The conference's first day, from ``conference.toml``.
        last_day: The conference's last day, from ``conference.toml``.

    Returns:
        The dates, one per day, oldest first.
    """
    dates = [day.date for day in data.days]
    start, end = min([first_day, *dates]), max([last_day, *dates])
    return tuple(start + timedelta(days=n) for n in range((end - start).days + 1))


def fold(text: str) -> str:
    """Return text as search compares it: accents stripped and case folded (D-46).

    So ``Cristián`` and ``CRISTIAN`` both fold to ``cristian``. Feed processing folds
    ``Session.search_text`` once; a query is folded the same way.

    Args:
        text: Any text.

    Returns:
        The NFKD decomposition without its combining marks, case folded.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


@dataclass(frozen=True, eq=False)
class SessionView:
    """What a session row shows of one session, formatted once (SCHED-03; D-153).

    Rows never format times themselves (ux.md §3.9): a list builds one view per session
    once per feed version and hands the same object to its row on every render. Frozen
    with identity equality (D-70 rule 6), so ``ft.memo`` compares it by identity first
    and a row whose view and star are unchanged skips its body (F34).

    Attributes:
        session: The session.
        when: Its conference-local time range, e.g. "9:25–10:10 AM" (DATA-12), or one
            time for a notice.
        spoken_when: The same range as a screen reader should say it: "9:25 to 10:10 AM".
        place: Where it is (DATA-16); empty for a generic break, which is everywhere.
        speakers: Its authors as one line, "Ana Lima, Bo Chen"; empty when none.
    """

    session: Session
    when: str
    spoken_when: str
    place: str
    speakers: str

    @property
    def meta(self) -> str:
        """The time and place line: "9:25–10:10 AM · Room 104A", or the time alone."""
        return f"{self.when} · {self.place}" if self.place else self.when


def session_view(session: Session, zone: tzinfo, *, use_24h: bool) -> SessionView:
    """Return the row view of one session.

    Args:
        session: The session.
        zone: The conference's zone; every time shows in it (D-35, D-43).
        use_24h: Whether the device uses the 24-hour clock
            (``page.media.always_use_24_hour_format``).

    Returns:
        The view: the displayed start (the Job Fair's earlier one, DATA-11) to the end,
        the display location and the authors' names (pseudo-speakers included,
        DATA-15).
    """
    when = time_range_label(session.display_start, session.end, zone, use_24h=use_24h)
    return SessionView(
        session=session,
        when=when,
        spoken_when=when.replace(_DASH, " to "),
        place=session.display_location,
        speakers=", ".join(session.speaker_names),
    )


def session_views(
    data: ConferenceData, session_ids: Iterable[str], zone: tzinfo, *, use_24h: bool
) -> tuple[SessionView, ...]:
    """Return the row views of some sessions, in the given order (D-153).

    Args:
        data: The processed feed.
        session_ids: The sessions; ids that are not in the feed are left out.
        zone: The conference's zone.
        use_24h: Whether the device uses the 24-hour clock.
    """
    sessions = data.sessions
    return tuple(
        session_view(sessions[i], zone, use_24h=use_24h)
        for i in session_ids
        if i in sessions
    )
