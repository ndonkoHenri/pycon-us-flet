"""Ionic's processing rules: what becomes a session, and how (D-41, D-42; DATA-04..07).

``feed.process()`` decodes the feed into records (``core/records.py``), then applies these
rules in Ionic's order (``processData`` in the original app's ``conference-data.ts``)
before it groups the sessions into days:

1. ``drop_rule``: slots that are not sessions (DATA-04);
2. ``collapse``: poster and break slots fold into one row per day and name (DATA-06);
3. ``slot_session``: every other slot is a session;
4. ``open_space_session``: scheduled open spaces are sessions too (DATA-05);
5. ``poster_details``: one session per poster, outside the timeline (DATA-07).

Each function is pure. Ionic's display quirks are not reproduced here (D-41); where a rule
departs from Ionic on purpose, its docstring says so and names the decision.
"""

import html
import re
from collections.abc import Iterable, Sequence
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from pycon_us.core.models import Poster, Session
from pycon_us.core.records import OpenSpace, Slot
from pycon_us.core.timefmt import local_date

COLLAPSED_KINDS = ("poster", "break")
"""The kinds whose slots fold into collapsed rows (DATA-06)."""

_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TAG = re.compile(r"<[^>]*>")
_TRAILING_ROOM = re.compile(r"\s*\(([^)]+)\)\s*$")
_HALL = re.compile(r"Hall\s", re.IGNORECASE)
_POSTERS = re.compile(r"posters?", re.IGNORECASE)
_LUNCH = re.compile(r"lunch\b", re.IGNORECASE)
_LUNCH_WEEKDAYS = (4, 5, 6)  # Friday to Sunday: the main conference days
_LUNCH_HOURS = range(12, 14)


def plain_text(name: str) -> str:
    """Return a slot name as text: a Markdown link becomes its text, tags go, entities decode.

    Ionic ran ``markdownToTxt`` on names; the feeds only use links there, plus one
    ``<s>…</s>`` in 2025 (D-114: names strip tags and keep their text).
    """
    text = _TAG.sub("", _MARKDOWN_LINK.sub(r"\1", name))
    return html.unescape(text).strip()


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
        _TRAILING_ROOM.sub("", plain_text(slot.name)).strip()
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


def collapse(slots: Iterable[Slot], zone: ZoneInfo, hall_prefix: str) -> list[Session]:
    """Fold poster and break slots into collapsed rows (DATA-06, SCHED-19).

    Slots share a row when they share Ionic's key: kind, conference-local day and name,
    plus the start for a break not named Lunch. So all of a day's posters make one row,
    a day's staggered lunches one row, and every other break one row per start. A row
    spans its slots' earliest start to latest end. Its name is ``Posters`` for posters;
    a Friday-to-Sunday ``Break`` that starts from 12:00 to 13:59 is renamed ``Lunch``. A
    trailing ``(Room)`` moves from the name to the location, which keeps the first slot's
    room otherwise, and a room named ``Hall …`` gets the year's ``hall_prefix`` (D-122).

    Args:
        slots: Slots of the kinds in ``COLLAPSED_KINDS``, in feed order.
        zone: The conference zone.
        hall_prefix: What the year's feed puts before ``Hall`` elsewhere (``Expo ``).

    Returns:
        One session per row, in the order of each row's first slot. Its id keeps Ionic's
        form ``<kind>-<room>-<start>`` (D-42), with the start in ISO 8601 at the
        conference's offset: what Ionic's id holds when the feed writes that offset.
    """
    rows: dict[tuple[object, ...], list[Slot]] = {}
    for slot in slots:
        name = plain_text(slot.name)
        own_start = slot.kind == "break" and not _LUNCH.match(name)
        key = (slot.kind, local_date(slot.start, zone), name)
        rows.setdefault((*key, slot.start if own_start else None), []).append(slot)
    return [_collapsed_row(group, zone, hall_prefix) for group in rows.values()]


def _collapsed_row(slots: Sequence[Slot], zone: ZoneInfo, hall_prefix: str) -> Session:
    first = slots[0]
    name = "Posters" if first.kind == "poster" else plain_text(first.name)
    local_start = first.start.astimezone(zone)
    if (
        first.kind == "break"
        and name in ("Break", "break")
        and local_start.weekday() in _LUNCH_WEEKDAYS
        and local_start.hour in _LUNCH_HOURS
    ):
        name = "Lunch"
    room = first.room
    if match := _TRAILING_ROOM.search(name):
        room, name = match[1], name[: match.start()].strip()
    room = _hall(room, hall_prefix)
    if not room:  # Ionic: a later slot's "(Room)" fills an empty room
        later = (_TRAILING_ROOM.search(plain_text(slot.name)) for slot in slots[1:])
        room = next((_hall(m[1], hall_prefix) for m in later if m), "")
    start = min(slot.start for slot in slots)
    return Session(
        id=f"{first.kind}-{room}-{start.astimezone(zone).isoformat()}",
        name=name,
        kind=first.kind,
        track=track(first.kind),
        location=room,
        description="",
        start=start,
        end=max(slot.end for slot in slots),
        day=local_date(start, zone),
        speaker_ids=(),
        url="",
        image_url="",
        in_timeline=True,
    )


def _hall(room: str, hall_prefix: str) -> str:
    return hall_prefix + room if _HALL.match(room) else room


def slot_session(slot: Slot, zone: ZoneInfo) -> Session:
    """Return the session of a slot that is neither dropped nor collapsed."""
    return Session(
        id=slot.id,
        name=slot.name,
        kind=slot.kind,
        track=track(slot.kind),
        location=slot.room,
        description=slot.description,
        start=slot.start,
        end=slot.end,
        day=local_date(slot.start, zone),
        speaker_ids=tuple(speaker.id for speaker in slot.speakers),
        url=slot.url,
        image_url="",
        in_timeline=True,
    )


def open_space_session(
    space: OpenSpace, zone: ZoneInfo, site_url: str
) -> Session | None:
    """Return the session of a scheduled open space, or None for an unscheduled one (DATA-05).

    An open space without a start, an end or a room is a proposal, not a session. Its
    page is the site's open-spaces list, opened at its entry; its image is made absolute.
    """
    if space.start is None or space.end is None or not space.room:
        return None
    return Session(
        id=space.session_id,
        name=space.title,
        kind="open-space",
        track="Open Space",
        location=space.room,
        description=space.description,
        start=space.start,
        end=space.end,
        day=local_date(space.start, zone),
        speaker_ids=(),
        url=urljoin(site_url, f"schedule/open-spaces/#OpenSpace-{space.conf_key}"),
        image_url=urljoin(site_url, space.image_url) if space.image_url else "",
        in_timeline=True,
    )


def poster_details(posters: Iterable[Poster], rows: Iterable[Session]) -> list[Session]:
    """Return one ``poster-detail-<conf_key>`` session per poster (DATA-07).

    They take the time, day and place of the first Posters row and stay out of the
    timeline, where the Posters row stands for them. Without a Posters row there is no
    time to give them, so there are none (D-123; Ionic made them with no time at all).
    """
    row = next((r for r in rows if r.kind == "poster" and r.name == "Posters"), None)
    if row is None:
        return []
    return [
        Session(
            id=f"poster-detail-{poster.id}",
            name=poster.title,
            kind="poster",
            track="Poster",
            location=row.location,
            description=poster.description,
            start=row.start,
            end=row.end,
            day=row.day,
            speaker_ids=poster.speaker_ids,
            url="",
            image_url="",
            in_timeline=False,
        )
        for poster in posters
    ]
