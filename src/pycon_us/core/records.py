"""Decode the feed's JSON records into frozen records (D-42; DATA-01, DATA-22, DATA-24, DATA-26).

Each decoder takes one JSON value and returns its record, or raises ``TypeError`` or
``ValueError`` naming the field and the problem; ``feed.process()`` then skips that record.
Ids become strings and times aware datetimes in the conference zone, and a lone surrogate
in a string becomes U+FFFD (#150). Unknown fields are ignored. ``Slot`` and ``OpenSpace``
are the feed as it is, before Ionic's rules (``core/rules.py``) make sessions of them.
Sponsors have no id for ``feed.process()`` to check, so ``sponsor_levels()`` decodes the
whole section and skips its own bad records.
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pycon_us.core.models import (
    JobListing,
    Poster,
    Speaker,
    Sponsor,
    SponsorLevel,
    Sprint,
)
from pycon_us.core.slugs import sponsor_slug

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


def sponsor_levels(
    document: Mapping[str, object], skip: Callable[[str, object], None]
) -> list[SponsorLevel]:
    """Decode ``conference.sponsors``, an object of sponsor lists keyed by level (DATA-22).

    A feed without the section has no levels. A section that is not an object, a level
    that is not a list and a sponsor that cannot be read are each passed to ``skip``, and
    the rest is kept; a level left without sponsors is not listed. The levels come in
    feed order: ``feed.process()`` sorts them.

    Args:
        document: The whole feed; ``feed.process()`` has checked that its
            ``conference``, when present, is an object.
        skip: Called with where and why for each record that cannot be read.

    Returns:
        The levels with at least one sponsor, in feed order.
    """
    conference = document.get("conference")
    sponsors = conference.get("sponsors") if isinstance(conference, dict) else None
    if sponsors is None:
        return []
    if not isinstance(sponsors, dict):
        skip("conference.sponsors", f"should be an object, got {sponsors!r}")
        return []
    levels: list[SponsorLevel] = []
    for key, items in sponsors.items():
        level = without_surrogates(key)
        where = f"conference.sponsors[{level!r}]"
        if not isinstance(items, list):
            skip(where, f"should be a list, got {items!r}")
            continue
        decoded: list[Sponsor] = []
        for index, item in enumerate(items):
            try:
                decoded.append(sponsor(item, level))
            except (TypeError, ValueError) as error:
                skip(f"{where}[{index}]", error)
        if decoded:  # Ionic sorted a level by its first sponsor's level_order
            levels.append(SponsorLevel(level, decoded[0].level_order, tuple(decoded)))
    return levels


def sponsor(item: object, level: str) -> Sponsor:
    """Decode one sponsor of the level ``level``.

    Its ``description`` is plain text: its line breaks are kept, each one line feed (the
    feed writes some as CR LF). An empty booth or table reads as None, as Ionic showed
    no pill for one.
    """
    record = _object(item)
    name = _text(record, "name")
    slug = sponsor_slug(name)
    if not slug.strip("-"):  # a blank name, or one of spaces and marks, slugs to dashes
        raise ValueError(f"'name' has no letter or digit to make a slug of: {name!r}")
    level_order = record.get("level_order")
    if type(level_order) is not int:
        raise TypeError(f"'level_order' should be an integer, got {level_order!r}")
    mobile_banner = record.get("mobile_banner")  # missing or null: no spotlight
    if not isinstance(mobile_banner, bool | None):
        raise TypeError(
            f"'mobile_banner' should be true or false, got {mobile_banner!r}"
        )
    description = _text(record, "description", optional=True)
    return Sponsor(
        name=name,
        slug=slug,
        level=level,
        level_order=level_order,
        logo_url=_text(record, "logo_url", optional=True),
        description=description.replace("\r\n", "\n").replace("\r", "\n"),
        booth=_place(record, "booth_number"),
        job_fair_table=_place(record, "job_fair_table_number"),
        mobile_banner=bool(mobile_banner),
        external_url=_text(record, "external_url", optional=True) or None,
    )


def without_surrogates(value: str) -> str:
    r"""Return ``value`` with each lone surrogate replaced by U+FFFD; the rest is kept.

    JSON can escape a lone surrogate (``"\ud800"``) and ``json.loads`` keeps it as a code
    point, but strict UTF-8 cannot encode one, and Flet sends every string to Flutter as
    strict UTF-8 (msgpack), so one would fail there (#150). An escaped pair is already one
    supplementary character (an emoji) after ``json.loads``, but a pair that arrives as
    CESU-8 bytes stays two code points, because ``json.loads`` decodes bytes with
    ``surrogatepass``. The UTF-16 round trip joins such a pair into its character and
    replaces each lone surrogate with one U+FFFD. UTF-8's ``errors="replace"`` is not
    used: it would turn them into ``?``.

    The record decoders apply it to every string they return, and ``feed.process()`` to
    the ``conference.content`` blocks.
    """
    if value.isascii():  # most feed strings: no surrogate, and ten times faster
        return value
    return value.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


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
    return without_surrogates(value)


def _place(record: Mapping[str, object], key: str) -> str | None:
    """Return a booth or table as text, or None when it is missing, null or blank.

    The feed writes them as strings; a number reads as its digits, as Ionic's
    ``String(booth_number)`` read it.
    """
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError(f"{key!r} should be a string, got {value!r}")
    return without_surrogates(str(value)).strip() or None


def _id(record: Mapping[str, object], key: str) -> str:
    """Return an id as a string (D-42, DATA-26); the feed's ids are integers."""
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int | str) or value == "":
        raise ValueError(f"{key!r} should be an id, got {value!r}")
    return str(value) if isinstance(value, int) else without_surrogates(value)


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
    return tuple(without_surrogates(str(value)) for value in values)


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
