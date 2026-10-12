"""Turn the public feed into the conference model (D-41, D-42; DATA-01, DATA-13, DATA-24, DATA-26).

``process()`` is the pipeline's one entry point. It decodes the JSON into frozen records
(``core/records.py``), every id a string and every time an aware datetime in the conference
zone; applies Ionic's processing rules (``core/rules.py``) to decide what becomes a
session; and buckets the timeline's sessions into conference-local days and time groups.

Failures are split in two. A feed whose structure is wrong raises ``FeedError``, so the
caller keeps the data it has. A single bad record is skipped, recorded in
``ConferenceData.skipped`` and logged; it never blanks the schedule. Unknown fields are
ignored, so the feed can grow without breaking the app.
"""

import json
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pycon_us.core import records, rules
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
from pycon_us.core.records import OpenSpace, Slot

logger = logging.getLogger(__name__)

# The 2025 feed has no posters, sprints or job listings.
_OPTIONAL_SECTIONS = ("open-spaces", "posters", "sprints", "job-listings")


class FeedError(ValueError):
    """The feed as a whole is unusable: not JSON, wrong structure, or no readable slot."""


@dataclass(frozen=True)
class FeedSettings:
    """What processing needs from the year data (``config.YearData.feed_settings``).

    Attributes:
        time_zone: The conference zone: times are converted to it and days bucketed in it.
        site_url: The year's site, ending in ``/``; site-relative links resolve against it.
        hall_prefix: What the year's feed puts before a ``Hall …`` room elsewhere, e.g.
            ``Expo `` in 2026, where ``Lunch (Hall AB)`` is served in ``Expo Hall AB``
            (D-122).
    """

    time_zone: ZoneInfo
    site_url: str
    hall_prefix: str


def process(raw: bytes, settings: FeedSettings) -> ConferenceData:
    """Decode the raw feed and apply Ionic's rules to it.

    Args:
        raw: The feed's bytes, as fetched or cached.
        settings: The year's processing settings.

    Returns:
        The model. Records that could not be read are listed in ``skipped``; records that
        did not become sessions of their own, in ``dropped``.

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
        lambda item: records.slot(item, zone),
        _id_of,
        skip,
    )
    if not slots:
        raise FeedError("no readable schedule slot")
    poster_ids: set[str] = set()  # posters and 2025's nested posters share ids (D-121)
    posters = _decode(
        sections["posters"], "posters", records.poster, _first_id, skip, poster_ids
    )
    posters += _decode(
        records.nested_posters(sections["schedule"]),
        "schedule posters",
        records.nested_poster,
        _first_id,
        skip,
        poster_ids,
    )
    spaces = _decode(
        sections["open-spaces"],
        "open-spaces",
        lambda item: records.open_space(item, zone),
        _session_id_of,
        skip,
    )

    dropped: defaultdict[str, list[str]] = defaultdict(list)
    kept: list[Slot] = []
    folded: list[Slot] = []
    for slot in slots:
        if rule := rules.drop_rule(slot):
            dropped[rule].append(slot.id)
        elif slot.kind in rules.COLLAPSED_KINDS:
            dropped["collapsed"].append(slot.id)
            folded.append(slot)
        else:
            kept.append(slot)
    rows = rules.collapse(folded, zone, settings.hall_prefix)
    candidates = [rules.slot_session(slot, zone) for slot in kept] + rows
    for space in spaces:
        session = rules.open_space_session(space, zone, settings.site_url)
        if session is None:
            dropped["unscheduled-open-space"].append(space.session_id)
        else:
            candidates.append(session)
    details = rules.poster_details((poster for poster, _ in posters), rows)
    if posters and not details:
        logger.warning("No Posters row: the %d posters get no session", len(posters))
    sessions = _index(candidates + details, skip)
    if dropped:
        logger.info(
            "Dropped %s",
            ", ".join(f"{len(ids)} {rule}" for rule, ids in dropped.items()),
        )

    speakers: dict[str, Speaker] = {}
    for its_speakers in (
        *(speakers for _, speakers in posters),
        *(slot.speakers for slot in kept),
    ):
        for speaker in its_speakers:
            # The first record of an id wins; Ionic registered poster authors first.
            speakers.setdefault(speaker.id, speaker)

    return ConferenceData(
        sessions=sessions,
        speakers=speakers,
        days=_days(s for s in sessions.values() if s.in_timeline),
        posters=tuple(poster for poster, _ in posters),
        sprints=tuple(
            _decode(sections["sprints"], "sprints", records.sprint, _id_of, skip)
        ),
        job_listings=tuple(
            _decode(
                sections["job-listings"],
                "job-listings",
                records.job_listing,
                _id_of,
                skip,
            )
        ),
        dropped={rule: tuple(ids) for rule, ids in dropped.items()},
        skipped=tuple(skipped),
    )


def _index(
    sessions: Iterable[Session], skip: Callable[[str, object], None]
) -> dict[str, Session]:
    """Return the sessions by id; a later session with an id already taken is skipped."""
    index: dict[str, Session] = {}
    for session in sessions:
        if session.id in index:
            skip(f"session {session.name!r}", f"duplicate id {session.id!r}")
            continue
        index[session.id] = session
    return index


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
    taken: set[str] | None = None,
) -> list[T]:
    """Return the records ``decode`` can read, the first of each id; ``skip`` the others.

    ``taken`` holds the ids already read, when two lists share one id space; the ids read
    here are added to it.
    """
    taken = set() if taken is None else taken
    records: list[T] = []
    for index, item in enumerate(items):
        where = f"{section}[{index}]"
        try:
            record = decode(item)
        except (TypeError, ValueError) as error:
            skip(where, error)
            continue
        if (record_id := id_of(record)) in taken:
            skip(where, f"duplicate id {record_id!r}")
            continue
        taken.add(record_id)
        records.append(record)
    return records


def _id_of(record: Slot | Sprint | JobListing) -> str:
    return record.id


def _session_id_of(space: OpenSpace) -> str:
    return space.session_id


def _first_id(pair: tuple[Poster, list[Speaker]]) -> str:
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
