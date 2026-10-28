"""The conference moments: year data for the sign-ups, and keynotes derived from the feed.

A conference moment is a fixed reminder that is not about a saved session (D-58,
NOTIF-05). Two kinds, with two id ranges (D-59, D-274):

- **Hand-authored** (8000–8049): the lightning-talk and open-space sign-ups, which no
  feed knows about. ``content.toml``'s ``[[event_reminders]]`` build into
  ``EventReminder`` through ``year_schema.build()``, as ``config.Content.event_reminders``,
  each with the public page it was said from and when that was checked.
  ``check_moments()`` checks them when the year loads.
- **Derived** (8050–8099): one per keynote and panel, 15 minutes before its start in the
  feed, from ``keynote_moments()``. Ionic hard-coded their times and copy, which drifted
  when the schedule moved; here a moved keynote moves its moment, and a keynote time
  never sits in the year data.

8999 is the Developer test reminder's (DEV-06), outside both ranges. A module of its own,
as ``year_keynotes`` is, so ``config.py`` grows by little (D-66). It imports no Flet: the
plan that turns these into reminders is ``services.reminder_plan.plan()`` (P2-67).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from urllib.parse import quote

from pycon_us.core.models import ConferenceData
from pycon_us.core.timefmt import instant, time_label
from pycon_us.core.timeline import keynote_sessions
from pycon_us.year_keynotes import Keynote, keynote_of
from pycon_us.year_pages import check_https, check_text
from pycon_us.year_schema import YearDataError

CATEGORIES = ("lightning", "open_space", "keynote")
"""What a moment is about; the reminder settings turn each one on or off (NOTIF-05)."""

HAND_CATEGORIES = ("lightning", "open_space")
"""The categories a hand-authored moment can have: keynote moments are only derived."""

HAND_IDS = range(8000, 8050)
"""The ids of hand-authored moments (D-274)."""

DERIVED_IDS = range(8050, 8100)
"""The ids of the moments derived from the keynotes, in the order they happen (D-274)."""

KEYNOTE_TRACK = "Keynote"
"""The keynotes' track, whose sessions all have a moment: the Keynotes page's
(``screens.keynotes.TRACK``, ``year_tracks.HUB_PAGES["keynotes"]``; a test keeps them
the same), named here because this module imports no screen."""

KEYNOTE_LEAD = timedelta(minutes=15)
"""How long before a keynote or panel starts its moment fires, as Ionic's did."""


@dataclass(frozen=True)
class EventReminder:
    """One conference moment: a fixed reminder that is not about a saved session.

    Attributes:
        id: Its notification id: 8000–8049 written by hand, 8050–8099 derived (D-274).
        category: One of ``CATEGORIES``.
        at: When it fires; aware.
        title: The notification's title.
        body: The notification's text.
        route: What a tap opens, a route path: ``/more/lightning-talks``, or the
            session of a keynote (D-274).
        source: The public page a hand-authored moment was said from; empty for a
            derived one, whose source is the feed.
        checked: When ``source`` was last checked; None for a derived moment.
        session_id: The session a keynote moment is about, so the plan gives a saved
            keynote one reminder, not two; empty for a hand-authored moment.
    """

    id: int
    category: str
    at: datetime
    title: str
    body: str
    route: str
    source: str = ""
    checked: date | None = None
    session_id: str = ""


def check_moments(
    moments: tuple[EventReminder, ...], year: int, zone: tzinfo, file: str
) -> None:
    """Check the hand-authored moments' rules (D-274).

    Args:
        moments: The ``[[event_reminders]]`` entries.
        year: The conference year: every moment fires in it, in the conference's zone.
        zone: The conference's time zone.
        file: The data file they come from, for the messages (``2026/content.toml``).

    Raises:
        YearDataError: A rule is broken; the message names the file and the entry.
    """
    seen: set[int] = set()
    for index, moment in enumerate(moments):
        key = f"event_reminders[{index}]"
        if moment.id not in HAND_IDS:
            raise YearDataError(
                f"{file}: {key}.id: {moment.id} is not in {HAND_IDS.start}-"
                f"{HAND_IDS.stop - 1}"
            )
        if moment.id in seen:
            raise YearDataError(f"{file}: {key}.id: duplicate id {moment.id}")
        seen.add(moment.id)
        if moment.category not in HAND_CATEGORIES:
            raise YearDataError(
                f"{file}: {key}.category: {moment.category!r} is not one of "
                f"{HAND_CATEGORIES}; keynote moments come from the keynotes"
            )
        if moment.at.utcoffset() is None:
            raise YearDataError(f"{file}: {key}.at: expected a time with a UTC offset")
        if moment.at.astimezone(zone).year != year:
            raise YearDataError(f"{file}: {key}.at: {moment.at} is not in {year}")
        check_text(moment.title, file, f"{key}.title")
        check_text(moment.body, file, f"{key}.body")
        if not moment.route.startswith("/"):
            raise YearDataError(f"{file}: {key}.route: expected a path from '/'")
        check_https(moment.source, file, f"{key}.source")
        if moment.checked is None:
            raise YearDataError(f"{file}: {key}.checked: missing key")


def keynote_moments(
    data: ConferenceData,
    keynotes: Iterable[Keynote],
    zone: tzinfo,
    *,
    use_24h: bool,
) -> tuple[EventReminder, ...]:
    """Return a moment for each keynote and panel, 15 minutes before its start (D-274).

    The sessions are the Keynotes page's (``timeline.keynote_sessions()``): every
    session of the keynotes' track and every session the year's keynote data names, in
    the order they happen. The feed gives the time, the name and the room, so a keynote
    the feed moves takes its moment along. A tap opens the session on the Schedule.

    Args:
        data: The processed feed.
        keynotes: The year's keynote entries (``Content.keynotes``); an entry's
            ``kind`` names a panel.
        zone: The conference's time zone, for the time in the title.
        use_24h: Whether the title's time is in 24-hour form.

    Returns:
        The moments, ids from 8050 in the order the sessions happen. Past moments are
        included: the plan drops them. Beyond 50 sessions, which no year comes close
        to, the rest have no moment.
    """
    keynotes = tuple(keynotes)
    sessions = keynote_sessions(data, KEYNOTE_TRACK, [k.session_id for k in keynotes])
    moments = []
    for moment_id, session in zip(DERIVED_IDS, sessions, strict=False):
        entry = keynote_of(keynotes, session.id)
        kind = "Panel" if entry is not None and entry.kind == "panel" else "Keynote"
        start = time_label(session.display_start, zone, use_24h=use_24h)
        place = f" · {session.display_location}" if session.display_location else ""
        moments.append(
            EventReminder(
                id=moment_id,
                category="keynote",
                # Subtracted in UTC, then shown in the conference's zone (#535).
                at=(instant(session.start) - KEYNOTE_LEAD).astimezone(zone),
                title=f"{kind} at {start}",
                body=f"{session.name}{place}",
                route=f"/schedule/session/{quote(session.id, safe='')}",
                session_id=session.id,
            )
        )
    return tuple(moments)
