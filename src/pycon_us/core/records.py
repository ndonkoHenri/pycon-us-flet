"""Decode the feed's JSON records into frozen records (D-42; DATA-01, DATA-24, DATA-26).

Each decoder takes one JSON value and returns its record, or raises ``TypeError`` or
``ValueError`` naming the field and the problem; ``feed.process()`` then skips that record.
Ids become strings and times aware datetimes in the conference zone. Unknown fields are
ignored. ``Slot`` and ``OpenSpace`` are the feed as it is, before Ionic's rules
(``core/rules.py``) make sessions of them.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pycon_us.core.models import JobListing, Poster, Speaker, Sprint

logger = logging.getLogger(__name__)

OPEN_SPACE_ID_OFFSET = 9000
"""Added to an open space's ``conf_key``, which collides with the schedule's (DATA-05)."""


@dataclass(frozen=True)
class Slot:
    """One record of the feed's ``schedule``, decoded but not yet processed.

    Attributes:
        id: Its ``conf_key``, as a string (D-42).
        name: The name as the feed gives it: it may hold a Markdown link or a ``(Room)``.
        kind: The feed's kind.
        room: The room text; several rooms are joined by ", ".
        description: The HTML description; empty when there is none.
        start: Aware, in the conference zone.
        end: Aware, in the conference zone; never before ``start``.
        url: Its page on the conference site; empty when there is none.
        authors: The speakers' names, as text (DATA-15 links them by name).
        has_contact: Whether the feed lists a contact; a placeholder has none.
        speakers: The speaker records the slot carries.
    """

    id: str
    name: str
    kind: str
    room: str
    description: str
    start: datetime
    end: datetime
    url: str
    authors: tuple[str, ...]
    has_contact: bool
    speakers: tuple[Speaker, ...]


@dataclass(frozen=True)
class OpenSpace:
    """One record of the feed's ``open-spaces``, decoded (DATA-05).

    Attributes:
        conf_key: Its key in the open-space signups; it collides with schedule keys.
        title: The title.
        description: The description, in Markdown (not HTML).
        room: Where it meets: the feed's ``room_display``, or ``room`` when that is empty.
        start: Aware, in the conference zone; None until it is scheduled.
        end: Aware, in the conference zone; None until it is scheduled.
        image_url: Its image as the feed gives it, possibly site-relative; may be empty.
    """

    conf_key: int
    title: str
    description: str
    room: str
    start: datetime | None
    end: datetime | None
    image_url: str

    @property
    def session_id(self) -> str:
        """The id of the session it becomes: ``conf_key + 9000`` (D-42)."""
        return str(self.conf_key + OPEN_SPACE_ID_OFFSET)


def nested_posters(schedule: list[object]) -> list[object]:
    """Return the posters nested in poster slots, as 2025's feed lists them (D-121).

    Ionic never read a slot's ``sessions`` for a poster slot, and its branch for other
    kinds (DATA-27) is not ported: those are logged and ignored.
    """
    nested: list[object] = []
    for item in schedule:
        if not isinstance(item, dict) or not item.get("sessions"):
            continue
        if item.get("kind") == "poster" and isinstance(item["sessions"], list):
            nested += item["sessions"]
        else:
            logger.warning(
                "Ignored the nested sessions of slot %r (DATA-27)", item.get("conf_key")
            )
    return nested


def slot(item: object, zone: ZoneInfo) -> Slot:
    """Decode one record of ``schedule``."""
    record = _object(item)
    start, end = _moment(record, "start", zone), _moment(record, "end", zone)
    if end < start:
        raise ValueError(f"ends at {end.isoformat()}, before it starts")
    return Slot(
        id=_id(record, "conf_key"),
        name=_text(record, "name"),
        kind=_text(record, "kind"),
        room=_text(record, "room"),
        description=_text(record, "description", optional=True),
        start=start,
        end=end,
        url=_text(record, "conf_url", optional=True),
        authors=_strings(record, "authors"),
        has_contact=bool(_list(record, "contact")),
        speakers=tuple(_speaker(speaker) for speaker in _list(record, "speakers")),
    )


def open_space(item: object, zone: ZoneInfo) -> OpenSpace:
    """Decode one record of ``open-spaces``; it may not be scheduled yet."""
    record = _object(item)
    start, end = (
        _schedule_time(record, "start", zone),
        _schedule_time(record, "end", zone),
    )
    if start and end and end < start:
        raise ValueError(f"ends at {end.isoformat()}, before it starts")
    conf_key = record.get("conf_key")
    if type(conf_key) is not int:
        raise TypeError(f"'conf_key' should be an integer, got {conf_key!r}")
    return OpenSpace(
        conf_key=conf_key,
        title=_text(record, "title"),
        description=_text(record, "description", optional=True),
        room=_text(record, "room_display", optional=True).strip()
        or _text(record, "room", optional=True).strip(),
        start=start,
        end=end,
        image_url=_text(record, "image_url", optional=True),
    )


def _speaker(item: object) -> Speaker:
    record = _object(item)
    return Speaker(
        id=_id(record, "id"),
        name=_text(record, "name"),
        photo_url=_text(record, "photo", optional=True),
        bio=_text(record, "bio", optional=True),
    )


def poster(item: object) -> tuple[Poster, list[Speaker]]:
    """Decode one record of ``posters``, with its authors' speaker records."""
    record = _object(item)
    speakers = [_speaker(speaker) for speaker in _list(record, "speakers")]
    decoded = Poster(
        id=_id(record, "conf_key"),
        title=_text(record, "title"),
        description=_text(record, "description_html", optional=True),
        speaker_ids=tuple(speaker.id for speaker in speakers),
    )
    return decoded, speakers


def nested_poster(item: object) -> tuple[Poster, list[Speaker]]:
    """Decode a poster nested in a poster slot (2025): ``name`` and ``description`` (D-121)."""
    record = _object(item)
    speakers = [_speaker(speaker) for speaker in _list(record, "speakers")]
    decoded = Poster(
        id=_id(record, "conf_key"),
        title=_text(record, "name"),
        description=_text(record, "description", optional=True),
        speaker_ids=tuple(speaker.id for speaker in speakers),
    )
    return decoded, speakers


def sprint(item: object) -> Sprint:
    """Decode one record of ``sprints``."""
    record = _object(item)
    logo_url = record.get("logo_url")
    return Sprint(
        id=_id(record, "id"),
        name=_text(record, "name"),
        url=_text(record, "url"),
        description=_text(record, "description_html", optional=True),
        logo_url=None if logo_url is None else _text(record, "logo_url"),
        submitter=_text(record, "submitter", optional=True),
    )


def job_listing(item: object) -> JobListing:
    """Decode one record of ``job-listings``."""
    record = _object(item)
    return JobListing(
        id=_id(record, "id"),
        sponsor_name=_text(record, "sponsor_name"),
        sponsor_logo_url=_text(record, "sponsor_logo_url", optional=True),
        sponsor_level=_text(record, "sponsor_level", optional=True),
        description=_text(record, "description_html", optional=True),
    )


def _object(item: object) -> Mapping[str, object]:
    if not isinstance(item, dict):
        raise TypeError(f"expected an object, got {item!r}")
    return item


def _text(record: Mapping[str, object], key: str, *, optional: bool = False) -> str:
    """Return a string field; an optional one may be missing or null, which reads as ""."""
    value = record.get(key)
    if value is None and optional:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{key!r} should be a string, got {value!r}")
    return value


def _id(record: Mapping[str, object], key: str) -> str:
    """Return an id as a string (D-42, DATA-26); the feed's ids are integers."""
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int | str) or value == "":
        raise ValueError(f"{key!r} should be an id, got {value!r}")
    return str(value)


def _list(record: Mapping[str, object], key: str) -> list[object]:
    """Return an optional list field; missing or null reads as empty."""
    value = record.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"{key!r} should be a list, got {value!r}")
    return value


def _strings(record: Mapping[str, object], key: str) -> tuple[str, ...]:
    """Return an optional list of strings; missing or null reads as empty."""
    values = _list(record, key)
    if not all(isinstance(value, str) for value in values):
        raise TypeError(f"{key!r} should be a list of strings, got {values!r}")
    return tuple(str(value) for value in values)


def _schedule_time(
    record: Mapping[str, object], key: str, zone: ZoneInfo
) -> datetime | None:
    """Return an open space's time; missing, null or "" means "not scheduled yet" (None)."""
    if record.get(key) in (None, ""):
        return None
    return _moment(record, key, zone)


def _moment(record: Mapping[str, object], key: str, zone: ZoneInfo) -> datetime:
    """Return an ISO 8601 time with a UTC offset as an aware datetime in ``zone``."""
    text = _text(record, key)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{key!r} is not an ISO 8601 time: {text!r}") from None
    if moment.utcoffset() is None:
        raise ValueError(f"{key!r} has no UTC offset: {text!r}")
    try:
        return moment.astimezone(zone)
    except OverflowError:  # e.g. 0001-01-01T00:00:00+00:00 has no Pacific equivalent
        raise ValueError(f"{key!r} is out of range: {text!r}") from None
