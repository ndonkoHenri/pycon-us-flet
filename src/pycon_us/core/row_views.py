"""The row views lists hand their rows: each session's text, formatted once (D-153, D-184).

Pure functions of the processed feed, like ``queries`` (architecture §7.5): a list owner
builds one ``SessionView`` per session once per feed version (``ui.rows.use_session_views``)
and hands the same object to its row on every render. ``by_day`` groups them for a list
that spans days.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, tzinfo
from itertools import groupby

from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timefmt import local_date, time_range_label

_DASH = "–"
"""The en dash of ``timefmt`` ranges, which a screen reader may skip or call a dash."""


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


def by_day(
    views: Iterable[SessionView], zone: tzinfo
) -> Iterator[tuple[date, list[SessionView]]]:
    """Yield row views grouped by their conference-local day, keeping their order.

    A row says a time but not a day, so a list that is not one day's (a speaker's or a
    room's sessions) puts each day's rows under the day's heading (ux.md §3.9).

    Args:
        views: The views, in schedule order.
        zone: The conference's zone; days are conference-local (D-43).

    Yields:
        Each day and its views, in the order given.
    """
    for day, group in groupby(views, lambda view: local_date(view.session.start, zone)):
        yield day, list(group)
