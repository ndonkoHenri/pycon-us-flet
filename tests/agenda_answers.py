"""Readers of `core.agenda`'s answers by id, for its three test modules (#312).

`test_agenda.py` (Now and your next session), `test_agenda_my_schedule.py` (My
schedule and its overlaps) and `test_agenda_fold.py` (what has ended, and the elapsed
share) compare the answers with the ids the feed names.
"""

from collections.abc import Iterable
from datetime import date, datetime

from pycon_us.config import load_year
from pycon_us.core.agenda import Agenda, NowNext, Phase, next_for_me
from pycon_us.core.models import ConferenceData, Session

POSTERS_ROW = "poster-Expo Hall AB-2026-05-17T09:30:00-07:00"


def may(year: int, day: int, hour: int, minute: int = 0) -> datetime:
    """An instant in May of `year`, in that year's conference zone."""
    zone = load_year(year).conference.zone
    return datetime(year, 5, day, hour, minute, tzinfo=zone)


# The answers hold the model's sessions (D-185); these read them by id, so the expected
# values stay as the feed names them.


def ids(sessions: Iterable[Session]) -> tuple[str, ...]:
    """Return the ids of `sessions`, in their order."""
    return tuple(session.id for session in sessions)


def happening(result: NowNext) -> tuple[str, ...]:
    """Return the ids of the sessions Now says are happening."""
    return ids(result.happening)


def next_start(result: NowNext) -> datetime | None:
    """Return the start of Now's next slot, or None when nothing is next."""
    return None if result.up_next is None else result.up_next.start


def up_next(result: NowNext) -> tuple[str, ...]:
    """Return the ids of the sessions in Now's next slot; empty when none is next."""
    return () if result.up_next is None else ids(result.up_next.sessions)


def shown(
    result: NowNext,
) -> tuple[Phase, tuple[str, ...], datetime | None, tuple[str, ...]]:
    """What Now shows: the phase, what is on, and the next slot's start and rows."""
    return result.phase, happening(result), next_start(result), up_next(result)


def next_id(data: ConferenceData, saved: frozenset[str], now: datetime) -> str | None:
    """Return the id of the next saved session at `now`, or None."""
    session = next_for_me(data, saved, now)
    return None if session is None else session.id


def agenda_ids(
    agenda: Agenda,
) -> list[tuple[date, list[tuple[datetime, tuple[str, ...]]]]]:
    """My schedule's days, each with its slots' starts and session ids."""
    return [
        (day.day, [(slot.start, ids(slot.sessions)) for slot in day.slots])
        for day in agenda.days
    ]


def overlap_ids(agenda: Agenda) -> dict[str, tuple[str, ...]]:
    """Return My schedule's overlaps by id: each session's clashing session ids."""
    return {session.id: ids(others) for session, others in agenda.overlaps.items()}
