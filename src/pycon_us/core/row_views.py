"""The row views lists hand their rows: each session's text, formatted once (D-153, D-184).

Pure functions of the processed feed, like ``queries`` (architecture §7.5): a list owner
builds one ``SessionView`` per session once per feed version (``ui.session_rows.use_session_views``)
and hands the same object to its row on every render. ``by_day`` groups them for a list
that spans days. ``places`` gives session detail its room tiles (SESS-02).
"""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, tzinfo
from itertools import groupby

from pycon_us.core.models import ConferenceData, Room, Session
from pycon_us.core.slugs import slugify_room
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
        place: Where it is (DATA-16); empty for a generic break, which is everywhere,
            and on a room's page for that room, which the page's title names (ROOM-02).
        speakers: Its authors as one line, "Ana Lima, Bo Chen"; empty when none.
    """

    session: Session
    when: str
    spoken_when: str
    place: str
    speakers: str


def session_view(
    session: Session, zone: tzinfo, *, use_24h: bool, in_room: str | None = None
) -> SessionView:
    """Return the row view of one session.

    Args:
        session: The session.
        zone: The conference's zone; every time shows in it (D-35, D-43).
        use_24h: Whether the device uses the 24-hour clock
            (``page.media.always_use_24_hour_format``).
        in_room: On a room's page, that room's slug (``Room.slug``): a place that is
            the room itself is left out, so the row shows its time alone and its
            phrase says no place, while another place stays (the lightning talks'
            Arena on a room they are streamed to). None on every other list.

    Returns:
        The view: the displayed start (the Job Fair's earlier one, DATA-11) to the end,
        the display location and the authors' names (pseudo-speakers included,
        DATA-15).
    """
    when = time_range_label(session.display_start, session.end, zone, use_24h=use_24h)
    place = session.display_location
    if in_room is not None and place and slugify_room(place) == in_room:
        place = ""  # the page's title already says it (ROOM-02)
    return SessionView(
        session=session,
        when=when,
        spoken_when=when.replace(_DASH, " to "),
        place=place,
        speakers=", ".join(session.speaker_names),
    )


def session_views(
    data: ConferenceData,
    session_ids: Iterable[str],
    zone: tzinfo,
    *,
    use_24h: bool,
    in_room: str | None = None,
) -> tuple[SessionView, ...]:
    """Return the row views of some sessions, in the given order (D-153).

    Args:
        data: The processed feed.
        session_ids: The sessions; ids that are not in the feed are left out.
        zone: The conference's zone.
        use_24h: Whether the device uses the 24-hour clock.
        in_room: On a room's page, the room's slug (``session_view()``).
    """
    sessions = data.sessions
    return tuple(
        session_view(sessions[i], zone, use_24h=use_24h, in_room=in_room)
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


@dataclass(frozen=True, eq=False)
class Places:
    """Where a session is, as session detail's room tiles show it (SESS-02).

    Attributes:
        label: The one place its row shows (``Session.display_location``, DATA-16);
            empty for a break held in many rooms, or a notice.
        room: The room ``label`` names, when the feed has one by that name (the
            lightning talks' Arena is one, D-124); its tile pushes room detail.
        others: Its other rooms that the feed has, each once, in the feed's order.
    """

    label: str
    room: Room | None
    others: tuple[Room, ...]

    @property
    def others_label(self) -> str:
        """The folded rooms' title: "+4 more rooms", or "In 7 rooms" with no label."""
        count = len(self.others)
        rooms = "room" if count == 1 else "rooms"
        return f"+{count} more {rooms}" if self.label else f"In {count} {rooms}"


def places(session: Session, rooms: Mapping[str, Room]) -> Places:
    """Return a session's places: the one it shows, then each other room once.

    Args:
        session: The session.
        rooms: ``ConferenceData.rooms``, by slug (``slugs.slugify_room``).
    """
    label = session.display_location
    room = rooms.get(slugify_room(label)) if label else None
    seen = {room.slug} if room else set()
    others: list[Room] = []
    for slug in map(slugify_room, session.rooms):
        if slug in rooms and slug not in seen:
            seen.add(slug)
            others.append(rooms[slug])
    return Places(label, room, tuple(others))
