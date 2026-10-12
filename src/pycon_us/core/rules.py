"""Ionic's processing rules: what becomes a session, and how (D-41, D-42; DATA-04..16).

``feed.process()`` decodes the feed into records (``core/records.py``), then applies these
rules in Ionic's order (``processData`` in the original app's ``conference-data.ts``)
before it groups the sessions into days:

1. ``drop_rule``: slots that are not sessions (DATA-04);
2. ``register_speakers``: the speaker directory, linked to sessions by name (DATA-15);
3. ``collapse``: poster and break slots fold into one row per day and name (DATA-06);
4. ``slot_session``: every other slot is a session, its title cleaned (DATA-08..11);
5. ``open_space_session``: scheduled open spaces are sessions too (DATA-05);
6. ``poster_details``: one session per poster, outside the timeline (DATA-07);
7. ``rooms``: every session under each of its rooms (DATA-16, ROOM-06).

Each function is pure. Ionic's display quirks are not reproduced here (D-41); where a rule
departs from Ionic on purpose, its docstring says so and names the decision.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from pycon_us.core.models import Poster, Room, Session, Speaker
from pycon_us.core.names import PLENARY_KINDS, clean_title, plain_text, trailing_room
from pycon_us.core.records import OpenSpace, Slot
from pycon_us.core.slugs import room_sort_key, slugify_room
from pycon_us.core.timefmt import local_date

COLLAPSED_KINDS = ("poster", "break")
"""The kinds whose slots fold into collapsed rows (DATA-06)."""

_HALL = re.compile(r"Hall\s", re.IGNORECASE)
_POSTERS = re.compile(r"posters?", re.IGNORECASE)
_LUNCH = re.compile(r"lunch\b", re.IGNORECASE)
_LUNCH_WEEKDAYS = (4, 5, 6)  # Friday to Sunday: the main conference days
_LUNCH_HOURS = range(12, 14)
_PSEUDO_SPEAKER = re.compile(r"hosted by\b", re.IGNORECASE)


@dataclass(frozen=True)
class DisplayTimeOverride:
    """Shift the displayed start of matching sessions; grouping keeps the real start (DATA-11).

    Attributes:
        match: A regular expression, matched case-insensitively against the whole cleaned
            session name, so it never matches a longer name by accident.
        minutes: How far to move the displayed start; negative is earlier.
    """

    match: str
    minutes: int

    @property
    def pattern(self) -> re.Pattern[str]:
        """The compiled, case-insensitive ``match``; apply it with ``fullmatch``."""
        return re.compile(self.match, re.IGNORECASE)


@dataclass(frozen=True)
class FeedSettings:
    """What processing needs from the year data (``config.YearData.feed_settings``).

    Attributes:
        time_zone: The conference zone: times are converted to it and days bucketed in it.
        site_url: The year's site, ending in ``/``; site-relative links resolve against it.
        hall_prefix: What the year's feed puts before a ``Hall …`` room elsewhere, e.g.
            ``Expo `` in 2026, where ``Lunch (Hall AB)`` is served in ``Expo Hall AB``
            (D-122).
        lightning_talks_location: Where lightning talks are shown to happen, whatever
            rooms they are streamed to; empty for none (D-124).
        display_time_overrides: Displayed starts to shift (DATA-11).
    """

    time_zone: ZoneInfo
    site_url: str
    hall_prefix: str
    lightning_talks_location: str = ""
    display_time_overrides: tuple[DisplayTimeOverride, ...] = ()


def track(kind: str) -> str:
    """Return the track key of a kind (DATA-14): its first letter upper-cased.

    ``sponsor-workshop`` is the one exception, as in Ionic: ``Sponsor Presentation``.
    """
    if kind == "sponsor-workshop":
        return "Sponsor Presentation"
    return kind[:1].upper() + kind[1:]


def drop_rule(slot: Slot) -> str | None:
    """Return the rule that drops a slot from the schedule, or None when it stays (DATA-04).

    The rules, in Ionic's order:

    * ``available-open-space``: a free open-space room or time (``available-open-space``
      and ``available-open-space-slot``);
    * ``open-space-duplicate``: a booked open space, which ``open-spaces`` also lists;
    * ``placeholder``: a cancelled talk's stub, named after its kind, with no description,
      contact or authors. Posters and breaks have that shape too and are never dropped,
      since they collapse into rows (Ionic's documented regression);
    * ``posters-plenary``: a plenary named "Posters (Room)", a copy of the Posters row;
    * ``blank``: a slot of kind ``blank`` or named ``Slot``.
    """
    if slot.kind.startswith("available-open-space"):
        return "available-open-space"
    if slot.kind == "open-space":
        return "open-space-duplicate"
    if _is_placeholder(slot):
        return "placeholder"
    if slot.kind == "plenary" and _POSTERS.fullmatch(
        trailing_room(plain_text(slot.name))[0]
    ):
        return "posters-plenary"
    if slot.kind == "blank" or slot.name == "Slot":
        return "blank"
    return None


def _is_placeholder(slot: Slot) -> bool:
    if slot.kind in COLLAPSED_KINDS:
        return False
    name = slot.name.strip().lower()
    return (
        bool(name)
        and name == slot.kind.lower()
        and not slot.description.strip()
        and not slot.has_contact
        and not slot.authors
    )


def register_speakers(records: Iterable[Speaker]) -> dict[str, Speaker]:
    """Return the speaker directory by id: the first record of each id wins (DATA-15).

    Pseudo-speakers such as "Hosted by Abigail, Chris, Cristián, and Lorena" are not
    people: they stay out of the directory and show as text (``Session.speaker_names``).
    Ionic listed them as speakers.
    """
    directory: dict[str, Speaker] = {}
    for speaker in records:
        if not _PSEUDO_SPEAKER.match(speaker.name):
            directory.setdefault(speaker.id, speaker)
    return directory


def collapse(slots: Iterable[Slot], settings: FeedSettings) -> list[Session]:
    """Fold poster and break slots into collapsed rows (DATA-06, SCHED-19).

    Slots share a row when they share Ionic's key: kind, conference-local day and name,
    plus the start for a break not named Lunch. So all of a day's posters make one row,
    a day's staggered lunches one row, and every other break one row per start. A row
    spans its slots' earliest start to latest end. Its name is ``Posters`` for posters;
    a Friday-to-Sunday ``Break`` that starts from 12:00 to 13:59 is renamed ``Lunch``. A
    trailing ``(Room)`` moves from the name to the location, which keeps the first slot's
    room otherwise, and a room named ``Hall …`` gets the year's ``hall_prefix`` (D-122).
    A row still named ``Break`` is everywhere at once, so it shows no location.

    Args:
        slots: Slots of the kinds in ``COLLAPSED_KINDS``, in feed order.
        settings: The year's processing settings.

    Returns:
        One session per row, in the order of each row's first slot. Its id keeps Ionic's
        form ``<kind>-<room>-<start>`` (D-42), with the start in ISO 8601 at the
        conference's offset: what Ionic's id holds when the feed writes that offset.
    """
    rows: dict[tuple[object, ...], list[Slot]] = {}
    for slot in slots:
        name = plain_text(slot.name)
        own_start = slot.kind == "break" and not _LUNCH.match(name)
        key = (slot.kind, local_date(slot.start, settings.time_zone), name)
        rows.setdefault((*key, slot.start if own_start else None), []).append(slot)
    return [_collapsed_row(group, settings) for group in rows.values()]


def _collapsed_row(slots: Sequence[Slot], settings: FeedSettings) -> Session:
    first, zone = slots[0], settings.time_zone
    name = "Posters" if first.kind == "poster" else plain_text(first.name)
    local_start = first.start.astimezone(zone)
    if (
        first.kind == "break"
        and name in ("Break", "break")
        and local_start.weekday() in _LUNCH_WEEKDAYS
        and local_start.hour in _LUNCH_HOURS
    ):
        name = "Lunch"
    name, room = trailing_room(name)
    room = _hall(room or first.room, settings.hall_prefix)
    if not room:  # Ionic: a later slot's "(Room)" fills an empty room
        later = (trailing_room(plain_text(slot.name))[1] for slot in slots[1:])
        room = _hall(next((r for r in later if r), ""), settings.hall_prefix)
    start = min(slot.start for slot in slots)
    return _session(
        id=f"{first.kind}-{room}-{start.astimezone(zone).isoformat()}",
        name=name,
        kind=first.kind,
        location=room,
        start=start,
        end=max(slot.end for slot in slots),
        zone=zone,
        no_location=first.kind == "break" and name == "Break",
    )


def _hall(room: str, hall_prefix: str) -> str:
    return hall_prefix + room if _HALL.match(room) else room


def slot_session(
    slot: Slot, settings: FeedSettings, speaker_ids_by_name: Mapping[str, str]
) -> Session:
    """Return the session of a slot that is neither dropped nor collapsed.

    Its title is cleaned (``names.clean_title``; DATA-08..10). A plenary-like slot's
    ``(Room)`` becomes its location, a ``Hall …`` room gets the year's prefix, and
    lightning talks show the year's ``lightning_talks_location`` (D-124). Its displayed
    start moves by the first display-time override that matches its whole title
    (DATA-11); its start, and so its time group, does not. Its speakers are the
    directory's people named in its authors (DATA-15), each once; the authors all stay
    as text in ``speaker_names``.
    """
    title = clean_title(slot.name, slot.kind)
    location = title.room or slot.room
    if slot.kind in PLENARY_KINDS:
        location = _hall(location, settings.hall_prefix)
    override = ""
    if slot.kind == "lightning-talks":
        override = settings.lightning_talks_location
    display_start = next(
        (
            slot.start + timedelta(minutes=shift.minutes)
            for shift in settings.display_time_overrides
            if shift.pattern.fullmatch(title.name)
        ),
        slot.start,
    )
    linked = (speaker_ids_by_name.get(name) for name in slot.authors)
    return _session(
        id=slot.id,
        name=title.name,
        kind=slot.kind,
        location=location,
        start=slot.start,
        end=slot.end,
        zone=settings.time_zone,
        display_location=override,
        display_start=display_start,
        description=slot.description,
        speaker_ids=tuple(dict.fromkeys(i for i in linked if i is not None)),
        speaker_names=slot.authors,
        pre_registered=title.pre_registered,
        spanish=title.spanish,
        url=slot.url,
    )


def open_space_session(space: OpenSpace, settings: FeedSettings) -> Session | None:
    """Return the session of a scheduled open space, or None for an unscheduled one (DATA-05).

    An open space without a start, an end or a room is a proposal, not a session. Its
    page is the site's open-spaces list, opened at its entry; its image is made absolute.
    """
    if space.start is None or space.end is None or not space.room:
        return None
    site_url = settings.site_url
    return _session(
        id=space.session_id,
        name=space.title,
        kind="open-space",
        location=space.room,
        start=space.start,
        end=space.end,
        zone=settings.time_zone,
        description=space.description,
        url=urljoin(site_url, f"schedule/open-spaces/#OpenSpace-{space.conf_key}"),
        image_url=urljoin(site_url, space.image_url) if space.image_url else "",
    )


def poster_details(
    posters: Iterable[tuple[Poster, Sequence[Speaker]]],
    rows: Iterable[Session],
    speakers: Mapping[str, Speaker],
    zone: ZoneInfo,
) -> list[Session]:
    """Return one ``poster-detail-<conf_key>`` session per poster (DATA-07).

    They take the time, day and place of the first Posters row and stay out of the
    timeline, where the Posters row stands for them. Their speakers are their authors in
    the directory, linked by id as Ionic did; every author stays as text (D-125). Without
    a Posters row there is no time to give them, so there are none (D-123; Ionic made
    them with no time at all).

    Args:
        posters: Each poster with its authors' speaker records.
        rows: The collapsed rows.
        speakers: The speaker directory.
        zone: The conference zone.
    """
    row = next((r for r in rows if r.kind == "poster" and r.name == "Posters"), None)
    if row is None:
        return []
    return [
        _session(
            id=f"poster-detail-{poster.id}",
            name=poster.title,
            kind="poster",
            location=row.location,
            start=row.start,
            end=row.end,
            zone=zone,
            description=poster.description,
            speaker_ids=tuple(a.id for a in authors if a.id in speakers),
            speaker_names=tuple(author.name for author in authors),
            in_timeline=False,
        )
        for poster, authors in posters
    ]


def rooms(sessions: Iterable[Session]) -> dict[str, Room]:
    """Return the rooms index by slug, in natural order of name (DATA-16, ROOM-06).

    A session is listed under each of its rooms, so a plenary streamed to seven rooms is
    in all seven. A room takes the first spelling met for its slug. Its sessions are
    sorted by start, then name (Ionic sorted by start only, keeping input order).
    """
    names: dict[str, str] = {}
    listed: dict[str, list[Session]] = {}
    for session in sessions:
        for name in session.rooms:
            slug = slugify_room(name)
            names.setdefault(slug, name)
            listed.setdefault(slug, []).append(session)
    return {
        slug: Room(
            slug=slug,
            name=names[slug],
            session_ids=tuple(
                s.id for s in sorted(listed[slug], key=lambda s: (s.start, s.name))
            ),
        )
        for slug in sorted(names, key=lambda slug: room_sort_key(names[slug]))
    }


def _room_names(location: str) -> tuple[str, ...]:
    """Split a location into its rooms, one name per slug, in order (DATA-16)."""
    by_slug: dict[str, str] = {}
    for name in (part.strip() for part in location.split(",")):
        if name:
            by_slug.setdefault(slugify_room(name), name)
    return tuple(by_slug.values())


def _session(
    *,
    id: str,
    name: str,
    kind: str,
    location: str,
    start: datetime,
    end: datetime,
    zone: ZoneInfo,
    display_location: str = "",
    no_location: bool = False,
    display_start: datetime | None = None,
    description: str = "",
    speaker_ids: tuple[str, ...] = (),
    speaker_names: tuple[str, ...] = (),
    pre_registered: bool = False,
    spanish: bool = False,
    url: str = "",
    image_url: str = "",
    in_timeline: bool = True,
) -> Session:
    """Build a session, deriving its track, rooms, displayed place and day.

    The displayed location is ``display_location`` when given, else the first room, else
    the location; ``no_location`` shows none (DATA-16).
    """
    room_names = _room_names(location)
    if no_location:
        display_location = ""
    elif not display_location:
        display_location = room_names[0] if room_names else location
    return Session(
        id=id,
        name=name,
        kind=kind,
        track="Open Space" if kind == "open-space" else track(kind),
        location=location,
        display_location=display_location,
        rooms=room_names,
        description=description,
        start=start,
        display_start=start if display_start is None else display_start,
        end=end,
        day=local_date(start, zone),
        speaker_ids=speaker_ids,
        speaker_names=speaker_names,
        pre_registered=pre_registered,
        spanish=spanish,
        url=url,
        image_url=image_url,
        in_timeline=in_timeline,
    )
