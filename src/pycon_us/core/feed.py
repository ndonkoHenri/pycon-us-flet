"""Turn the public feed into the conference model (D-41, D-42; DATA-01, DATA-13, DATA-24, DATA-26).

``process()`` is the pipeline's one entry point. Today it decodes: the JSON becomes frozen
records, every id a string, every time an aware datetime in the conference zone, and the
sessions are bucketed into conference-local days and time groups. Ionic's processing rules
(filters, open spaces, collapsed rows, names, flags, speakers by name, rooms) arrive with
P0-11 and P0-12, between decoding and grouping; until then every schedule slot is a session.

Failures are split in two. A feed whose structure is wrong raises ``FeedError``, so the
caller keeps the data it has. A single bad record is skipped, recorded in
``ConferenceData.skipped`` and logged; it never blanks the schedule. Unknown fields are
ignored, so the feed can grow without breaking the app.
"""

import json
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pycon_us.core.models import (
    ConferenceData,
    Day,
    JobListing,
    Poster,
    Session,
    Speaker,
    Sprint,
    TimeGroup,
)
from pycon_us.core.timefmt import local_date

logger = logging.getLogger(__name__)

_OPTIONAL_SECTIONS = ("posters", "sprints", "job-listings")  # the 2025 feed has none


class FeedError(ValueError):
    """The feed as a whole is unusable: not JSON, wrong structure, or no readable slot."""


@dataclass(frozen=True)
class FeedSettings:
    """What processing needs from the year data (``config.YearData.feed_settings``).

    Attributes:
        time_zone: The conference zone: times are converted to it and days bucketed in it.
    """

    time_zone: ZoneInfo


def process(raw: bytes, settings: FeedSettings) -> ConferenceData:
    """Decode the raw feed into the conference model.

    Args:
        raw: The feed's bytes, as fetched or cached.
        settings: The year's processing settings.

    Returns:
        The model. Records that could not be read are listed in ``skipped``.

    Raises:
        FeedError: The feed is not a JSON object with a ``schedule`` list, an optional
            section is not a list, or no schedule slot could be read.
    """
    sections = _sections(raw)
    zone = settings.time_zone
    skipped: list[str] = []

    def skip(where: str, problem: object) -> None:
        reason = f"{where}: {problem}"
        logger.warning("Skipped a feed record: %s", reason)
        skipped.append(reason)

    slots = _decode(
        sections["schedule"],
        "schedule",
        lambda item: _slot(item, zone),
        _first_id,
        skip,
    )
    if not slots:
        raise FeedError("no readable schedule slot")
    posters = _decode(sections["posters"], "posters", _poster, _first_id, skip)
    speakers: dict[str, Speaker] = {}
    for _, its_speakers in (*slots, *posters):
        for speaker in its_speakers:
            # The first record of an id wins, as in Ionic.
            speakers.setdefault(speaker.id, speaker)
    sessions = {session.id: session for session, _ in slots}

    return ConferenceData(
        sessions=sessions,
        speakers=speakers,
        days=_days(sessions.values()),
        posters=tuple(poster for poster, _ in posters),
        sprints=tuple(_decode(sections["sprints"], "sprints", _sprint, _id_of, skip)),
        job_listings=tuple(
            _decode(
                sections["job-listings"], "job-listings", _job_listing, _id_of, skip
            )
        ),
        skipped=tuple(skipped),
    )


def _sections(raw: bytes) -> dict[str, list[object]]:
    """Parse the JSON and return the lists we read: ``schedule`` and the optional sections."""
    try:
        document = json.loads(raw)
    except ValueError as error:  # JSONDecodeError and UnicodeDecodeError
        raise FeedError(f"not JSON: {error}") from None
    if not isinstance(document, dict):
        raise FeedError("not a JSON object")
    if not isinstance(document.get("schedule"), list):
        raise FeedError("no 'schedule' list")
    sections = {"schedule": document["schedule"]}
    for key in _OPTIONAL_SECTIONS:
        sections[key] = document.get(key, [])
        if not isinstance(sections[key], list):
            raise FeedError(f"{key!r} is not a list")
    return sections


def _decode[T](
    items: list[object],
    section: str,
    decode: Callable[[object], T],
    id_of: Callable[[T], str],
    skip: Callable[[str, object], None],
) -> list[T]:
    """Return the records ``decode`` can read, the first of each id; ``skip`` the others."""
    records: dict[str, T] = {}
    for index, item in enumerate(items):
        where = f"{section}[{index}]"
        try:
            record = decode(item)
        except (TypeError, ValueError) as error:
            skip(where, error)
            continue
        if (record_id := id_of(record)) in records:
            skip(where, f"duplicate id {record_id!r}")
            continue
        records[record_id] = record
    return list(records.values())


def _id_of(record: Sprint | JobListing) -> str:
    return record.id


def _first_id(pair: tuple[Session | Poster, list[Speaker]]) -> str:
    return pair[0].id


def _days(sessions: Iterable[Session]) -> tuple[Day, ...]:
    """Bucket sessions by local date, then by aware start (DATA-13).

    Groups are keyed by their start instant, not by a display label, so every group has a
    start and sorting by it is total; Ionic's string keys left some groups without one.
    """
    calendar: defaultdict[date, defaultdict[datetime, list[Session]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for session in sessions:
        calendar[session.day][session.start].append(session)
    return tuple(
        Day(
            day,
            tuple(
                TimeGroup(
                    start,
                    tuple(
                        s.id for s in sorted(group, key=lambda s: (s.location, s.name))
                    ),
                )
                for start, group in sorted(groups.items())
            ),
        )
        for day, groups in sorted(calendar.items())
    )


def _slot(item: object, zone: ZoneInfo) -> tuple[Session, list[Speaker]]:
    slot = _object(item)
    start, end = _moment(slot, "start", zone), _moment(slot, "end", zone)
    if end < start:
        raise ValueError(f"ends at {end.isoformat()}, before it starts")
    speakers = [_speaker(speaker) for speaker in _list(slot, "speakers")]
    session = Session(
        id=_id(slot, "conf_key"),
        name=_text(slot, "name"),
        kind=_text(slot, "kind"),
        location=_text(slot, "room"),
        description=_text(slot, "description", optional=True),
        start=start,
        end=end,
        day=local_date(start, zone),
        speaker_ids=tuple(speaker.id for speaker in speakers),
        url=_text(slot, "conf_url", optional=True),
    )
    return session, speakers


def _speaker(item: object) -> Speaker:
    record = _object(item)
    return Speaker(
        id=_id(record, "id"),
        name=_text(record, "name"),
        photo_url=_text(record, "photo", optional=True),
        bio=_text(record, "bio", optional=True),
    )


def _poster(item: object) -> tuple[Poster, list[Speaker]]:
    record = _object(item)
    speakers = [_speaker(speaker) for speaker in _list(record, "speakers")]
    poster = Poster(
        id=_id(record, "conf_key"),
        title=_text(record, "title"),
        description=_text(record, "description_html", optional=True),
        speaker_ids=tuple(speaker.id for speaker in speakers),
    )
    return poster, speakers


def _sprint(item: object) -> Sprint:
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


def _job_listing(item: object) -> JobListing:
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
