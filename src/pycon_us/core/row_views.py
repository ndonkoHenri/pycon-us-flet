"""The row views lists hand their rows: each session's text, formatted once (D-153, D-184).

Pure functions of the processed feed, like `queries` (architecture §7.5): a list owner
builds one `SessionView` per session once per feed version (`ui.session_rows.use_session_views`)
and hands the same object to its row on every render. `by_day` groups them for a list
that spans days, and `by_slot` one day's into time slots. `places` gives session
detail its room tiles (SESS-02), `people` its Speakers section (SESS-07), and
`share_text` what its Share sends (NEW-06). `spoken_phrase()`,
`notice_phrase()` and `elapsed_phrase()` are what a row says to a screen reader,
as one phrase (D-33, D-200).
"""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from itertools import groupby

from pycon_us.core.models import ConferenceData, Room, Session, Speaker
from pycon_us.core.slugs import slugify_room
from pycon_us.core.timefmt import day_heading, instant, local_date, time_range_label

_DASH = "–"
"""The en dash of `timefmt` ranges, which a screen reader may skip or call a dash."""


@dataclass(frozen=True, eq=False)
class SessionView:
    """What a session row shows of one session, formatted once (SCHED-03; D-153).

    Rows never format times themselves (ux.md §3.9): a list builds one view per session
    once per feed version and hands the same object to its row on every render. Frozen
    with identity equality (D-70 rule 6), so `ft.memo` compares it by identity first
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
    session: Session,
    zone: tzinfo,
    *,
    use_24h: bool,
    in_room: str | None = None,
    of_speaker: str | None = None,
) -> SessionView:
    """Return the row view of one session.

    Args:
        session: The session.
        zone: The conference's zone; every time shows in it (D-35, D-43).
        use_24h: Whether the device uses the 24-hour clock
            (`page.media.always_use_24_hour_format`).
        in_room: On a room's page, that room's slug (`Room.slug`): a place that is
            the room itself is left out, so the row shows its time alone and its
            phrase says no place, while another place stays (the lightning talks'
            Arena on a room they are streamed to). None on every other list.
        of_speaker: On a speaker's page, that speaker's name (`Speaker.name`): the
            speakers line names only the others, "With Ana Lima", and is empty when
            the speaker is alone, so neither the row nor its phrase repeats the page's
            subject. None on every other list.

    Returns:
        The view: the displayed start (the Job Fair's earlier one, DATA-11) to the end,
        the display location and the authors' names (pseudo-speakers included,
        DATA-15).
    """
    when = time_range_label(session.display_start, session.end, zone, use_24h=use_24h)
    place = session.display_location
    if in_room is not None and place and slugify_room(place) == in_room:
        place = ""  # the page's title already says it (ROOM-02)
    speakers = ", ".join(session.speaker_names)
    if of_speaker is not None:
        # Matched by name: feed processing links each author by name (D-125), so a
        # linked speaker's name is among the authors'.
        others = [name for name in session.speaker_names if name != of_speaker]
        speakers = f"With {', '.join(others)}" if others else ""
    return SessionView(
        session=session,
        when=when,
        spoken_when=when.replace(_DASH, " to "),
        place=place,
        speakers=speakers,
    )


def session_views(
    data: ConferenceData,
    session_ids: Iterable[str],
    zone: tzinfo,
    *,
    use_24h: bool,
    in_room: str | None = None,
    of_speaker: str | None = None,
) -> tuple[SessionView, ...]:
    """Return the row views of some sessions, in the given order (D-153).

    Args:
        data: The processed feed.
        session_ids: The sessions; ids that are not in the feed are left out.
        zone: The conference's zone.
        use_24h: Whether the device uses the 24-hour clock.
        in_room: On a room's page, the room's slug (`session_view()`).
        of_speaker: On a speaker's page, the speaker's name (`session_view()`).
    """
    sessions = data.sessions
    return tuple(
        session_view(
            sessions[i], zone, use_24h=use_24h, in_room=in_room, of_speaker=of_speaker
        )
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


def by_slot(views: Iterable[SessionView]) -> list[tuple[datetime, list[SessionView]]]:
    """Return one day's row views grouped into time slots, as the Schedule's are (D-31).

    A slot is the sessions of one time group: they share `Session.start`, so the Job
    Fair sits in the 10:00 slot while its row says 9:30 (DATA-11, D-41). For a list
    of gutter slots that is not the Schedule's: a room's day (ROOM-02) and the open
    spaces' (EVT-01).

    Args:
        views: One day's views; within a start, in the order to show. They may come by
            the start a row shows (`timeline.schedule_order`, as the open spaces'
            do), which a display-time override can put before an earlier slot.

    Returns:
        Each slot's start and its views, by start whatever order the views came in;
        within a slot, in the order given.
    """
    # Keyed by instant: starts in one zone hash and compare by wall clock, which would
    # merge 1:30 PDT and 1:30 PST on the night summer time ends (#535).
    slots: dict[datetime, list[SessionView]] = {}
    for view in views:
        slots.setdefault(instant(view.session.start), []).append(view)
    return [(group[0].session.start, group) for _, group in sorted(slots.items())]


@dataclass(frozen=True, eq=False)
class Places:
    """Where a session is, as session detail's room tiles show it (SESS-02).

    Attributes:
        label: The one place its row shows (`Session.display_location`, DATA-16);
            empty for a break held in many rooms, or a notice.
        room: The room `label` names, when the feed has one by that name (the
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
        rooms: `ConferenceData.rooms`, by slug (`slugs.slugify_room`).
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


def people(
    session: Session, speakers: Mapping[str, Speaker]
) -> tuple[Speaker | str, ...]:
    """Return who a session's Speakers section lists, in the feed's author order (SESS-07).

    A directory speaker the session links is a `Speaker`, whose row opens their page;
    a name the directory has no one for is the name itself, shown as text: the lightning
    talks' "Hosted by …" (a pseudo-speaker, D-125, DATA-15) is the one in both recorded
    feeds. Each person and each name comes once; a linked speaker whose name the authors
    do not spell the same way (poster authors link by id, D-125) comes after them.

    Args:
        session: The session.
        speakers: `ConferenceData.speakers`, by id.
    """
    linked = [speakers[sid] for sid in session.speaker_ids if sid in speakers]
    by_name: dict[str, Speaker] = {}
    for speaker in linked:
        by_name.setdefault(speaker.name, speaker)
    found: list[Speaker | str] = []
    for name in session.speaker_names:
        entry = by_name.get(name, name)
        if entry not in found:
            found.append(entry)
    found.extend(speaker for speaker in linked if speaker not in found)
    return tuple(found)


def share_text(
    session: Session, conference: str, zone: tzinfo, *, use_24h: bool
) -> str:
    """Return what Share sends for a session (NEW-06): its title, when and where, its page.

    "Python for Humans" / "PyCon US 2026 · Saturday, May 16, 10:30–11:00 AM PDT ·
    Grand Ballroom A" / its public page on the conference site. The time is in
    conference time, as everywhere (D-35), and names its zone, since the person who
    reads it may be anywhere; it starts where the session detail's does (the Job
    Fair's 9:30, DATA-11). The conference's name says what the day belongs to, also
    when there is no page. The page is the feed's own link (`Session.url`, the one
    "Open on us.pycon.org" opens): a synthetic id (a collapsed break, the Posters row,
    a poster detail) and a session the site has no page for (a keynote, a notice)
    have none, so their text ends with when and where.

    Args:
        session: The session.
        conference: The conference's name from the year data, e.g. "PyCon US 2026".
        zone: The conference's zone.
        use_24h: Whether the device uses the 24-hour clock.
    """
    start = session.display_start
    when = time_range_label(start, session.end, zone, use_24h=use_24h)
    day = day_heading(local_date(start, zone))
    zone_name = start.astimezone(zone).tzname()
    details = [conference, f"{day}, {when} {zone_name}"]
    if session.display_location:  # a generic break is everywhere
        details.append(session.display_location)
    lines = [session.name, " · ".join(details)]
    if session.url:
        lines.append(session.url)
    return "\n".join(lines)


def spoken_phrase(
    labels: Sequence[str],
    view: SessionView,
    *,
    overlaps: Sequence[str] = (),
    show_time: bool = True,
) -> str:
    """Return what a screen reader says for a session row: one phrase (D-33).

    "Talk. What's new in typing. 9:25 to 10:10 AM, Room 104A. Ana Lima." (ux.md
    §3.9): the badges, the title, the time and place, then the speakers, each a
    sentence, so TalkBack and VoiceOver pause between them. On My schedule a last
    sentence names every clash in full, "Overlaps with “A”, “B” and “C”.", so the
    clash is heard, not only seen, even where the row counts the rest (ux.md §5.6).

    Args:
        labels: The badges' labels, in order (`badge_specs()`).
        view: The session's row view.
        overlaps: The names of the saved sessions the row overlaps, if any.
        show_time: False when the page above says the row's time (the Posters
            detail, D-206): the phrase leaves it out, as the row does.
    """
    when = ", ".join(
        part for part in (view.spoken_when if show_time else "", view.place) if part
    )
    clash = ""
    if overlaps:
        *rest, last = (f"“{name}”" for name in overlaps)
        names = f"{', '.join(rest)} and {last}" if rest else last
        clash = f"Overlaps with {names}"
    parts = (", ".join(labels), view.session.name, when, view.speakers, clash)
    return " ".join(_sentence(part) for part in parts if part)


def notice_phrase(label: str, view: SessionView) -> str:
    """Return what a screen reader says for a notice row, as one phrase (D-33).

    "Notice. Registration opens, 7:00 AM." (ux.md §3.9), with the place when there
    is one: "Break. Lunch, 12:00 to 1:00 PM, Expo Hall AB."

    Args:
        label: The notice's track name, e.g. "Notice" or "Break".
        view: The notice's row view.
    """
    place = f", {view.place}" if view.place else ""
    return _sentence(f"{label}. {view.session.name}, {view.spoken_when}{place}")


def _sentence(text: str) -> str:
    """End `text` with a full stop unless it already ends a sentence."""
    return text if text.endswith((".", "?", "!", "…")) else f"{text}."


def elapsed_phrase(elapsed: int) -> str:
    """Return the sentence that ends the phrase of a row that is on.

    "60 percent elapsed." In the phrase, not on the bar: merged into the row, the bar's
    value would be read as a bare "60". Flet sent `semantics_value` as a number, "60.0",
    until the pin `22a6dcb16` (#210); the phrase still says what the number means.

    Args:
        elapsed: The share of the session that has passed, in whole percent.
    """
    return f"{elapsed} percent elapsed."
