"""Turn the public feed into the conference model (D-41, D-42; DATA-01, DATA-13, DATA-24, DATA-26).

``process()`` is the pipeline's one entry point. It decodes the JSON into frozen records
(``core/records.py``), every id a string and every time an aware datetime in the conference
zone; applies Ionic's processing rules (``core/rules.py``) to decide what becomes a
session; buckets the timeline's sessions into conference-local days and time groups; sorts
the sponsorship levels once (DATA-22); and last converts the feed's HTML to Markdown and
search text, once (D-130, D-140), reading the job listings' roles as it goes (D-278).

Failures are split in two. A feed whose structure is wrong raises ``FeedError``, so the
caller keeps the data it has. A single bad record is skipped, recorded in
``ConferenceData.skipped`` and logged; it never blanks the schedule. Unknown fields are
ignored, so the feed can grow without breaking the app.
"""

import json
import logging
import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date, datetime
from functools import cache

from pycon_us.core import html_md, jobs, records, rules
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
from pycon_us.core.queries import fold
from pycon_us.core.records import OpenSpace, Slot
from pycon_us.core.rules import FeedSettings

logger = logging.getLogger(__name__)

# The 2025 feed has no posters, sprints or job listings.
_OPTIONAL_SECTIONS = ("open-spaces", "posters", "sprints", "job-listings")

# An inline Markdown link in an open space's description: its text shows, its
# destination does not, so search leaves the destination out (D-46, D-140).
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


class FeedError(ValueError):
    """The feed as a whole is unusable: not JSON, wrong structure, or no readable slot."""


def process(raw: bytes, settings: FeedSettings) -> ConferenceData:
    """Decode the raw feed, apply Ionic's rules to it, then convert its markup.

    Args:
        raw: The feed's bytes, as fetched or cached.
        settings: The year's processing settings.

    Returns:
        The model. Records that could not be read are listed in ``skipped``; records that
        did not become sessions of their own, in ``dropped``.

    Raises:
        FeedError: The feed is not a JSON object with a ``schedule`` list, an optional
            section is not a list, ``conference`` or its ``content`` is not an object, or
            no schedule slot could be read.
    """
    started = time.perf_counter()
    document = _document(raw)
    sections = _sections(document)
    zone = settings.time_zone
    skipped: list[str] = []

    def skip(where: str, problem: object) -> None:
        reason = f"{where}: {problem}"
        logger.warning("Skipped a feed record: %s", reason)
        skipped.append(reason)

    content = _content(document, skip)

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
    # Ionic registered poster authors first, then the schedule's speakers.
    speakers = rules.register_speakers(
        [
            *(speaker for _, authors in posters for speaker in authors),
            *(speaker for slot in kept for speaker in slot.speakers),
        ]
    )
    by_name: dict[str, str] = {}
    for speaker in speakers.values():
        by_name.setdefault(speaker.name, speaker.id)

    rows = rules.collapse(folded, settings)
    candidates = [rules.slot_session(slot, settings, by_name) for slot in kept] + rows
    for space in spaces:
        session = rules.open_space_session(space, settings)
        if session is None:
            dropped["unscheduled-open-space"].append(space.session_id)
        else:
            candidates.append(session)
    details = rules.poster_details(posters, rows, speakers, zone)
    if posters and not details:
        logger.warning("No Posters row: the %d posters get no session", len(posters))
    sessions = _index(candidates + details, skip)
    if dropped:
        logger.info(
            "Dropped %s",
            ", ".join(f"{len(ids)} {rule}" for rule, ids in dropped.items()),
        )

    data = ConferenceData(
        sessions=sessions,
        speakers=speakers,
        days=_days(s for s in sessions.values() if s.in_timeline),
        rooms=rules.rooms(sessions.values()),
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
        sponsor_levels=tuple(
            sorted(
                records.sponsor_levels(document, skip), key=lambda level: level.order
            )
        ),
        dropped={rule: tuple(ids) for rule, ids in dropped.items()},
        # After the decoders above, which add to it as they run.
        skipped=tuple(skipped),
        content=content,
    )
    # After the rules: the placeholder rule reads the raw description, as Ionic did.
    data = _converted(data, settings.site_url)
    # D-109 compares this with 150 ms on the iPhone's release build.
    logger.info(
        "Feed processed in %d ms: %d sessions, %d skipped",
        round((time.perf_counter() - started) * 1000),
        len(data.sessions),
        len(data.skipped),
    )
    return data


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


def _converted(data: ConferenceData, site_url: str) -> ConferenceData:
    """Return the model with every markup field converted (D-130, D-140; DATA-23..25).

    Each distinct value converts once: a poster's description is also its poster
    detail's, and many fields are empty. Open spaces are Markdown already, so their
    descriptions pass through (D-115) and their search text comes from the Markdown.
    Sprint projects get their description's text and a search text too, for the
    Sprints card's preview and its filter (EVT-05, EVT-06); job listings get their
    roles and a search text (SPON-07, SPON-09, D-278).
    """

    @cache
    def markdown(value: str) -> str:
        return html_md.to_markdown(value, site_url)

    def marked_up(session: Session) -> Session:
        if session.kind == "open-space":
            description_md = session.description
            text = _markdown_text(session.description)
        else:
            description_md = markdown(session.description)
            text = html_md.to_text(session.description)
        return replace(
            session,
            description_md=description_md,
            search_text=fold(" ".join([session.name, text, *session.speaker_names])),
        )

    def project(sprint: Sprint) -> Sprint:
        text = html_md.to_text(sprint.description)
        return replace(
            sprint,
            description_md=markdown(sprint.description),
            description_text=text,
            search_text=fold(f"{sprint.name} {sprint.submitter} {text}"),
        )

    return replace(
        data,
        sessions={key: marked_up(value) for key, value in data.sessions.items()},
        speakers={
            key: replace(value, bio_md=markdown(value.bio))
            for key, value in data.speakers.items()
        },
        posters=tuple(
            replace(p, description_md=markdown(p.description)) for p in data.posters
        ),
        sprints=tuple(project(sprint) for sprint in data.sprints),
        job_listings=tuple(
            jobs.read_listing(j, site_url, markdown) for j in data.job_listings
        ),
        content_md={key: markdown(value) for key, value in data.content.items()},
    )


def _markdown_text(value: str) -> str:
    """Return the visible text of an open space's Markdown, for search (D-46, D-140).

    A link keeps its text and loses its destination, and the ``*`` and backtick markers
    go. ``_`` stays: in these descriptions it joins identifiers (``ic_ocr_cataloger``),
    never emphasis. Then ``to_text`` collapses whitespace as for HTML.
    """
    shown = _MARKDOWN_LINK.sub(r"\1", value)
    return html_md.to_text(shown.replace("*", "").replace("`", ""))


def _document(raw: bytes) -> dict[str, object]:
    """Parse the JSON, which must be an object."""
    try:
        document = json.loads(raw)
    except ValueError as error:  # JSONDecodeError and UnicodeDecodeError
        raise FeedError(f"not JSON: {error}") from None
    if not isinstance(document, dict):
        raise FeedError("not a JSON object")
    return document


def _sections(document: dict[str, object]) -> dict[str, list[object]]:
    """Return the lists we read: ``schedule`` and the optional sections."""
    schedule = document.get("schedule")
    if not isinstance(schedule, list):
        raise FeedError("no 'schedule' list")
    sections: dict[str, list[object]] = {"schedule": schedule}
    for key in _OPTIONAL_SECTIONS:
        section = document.get(key, [])
        if not isinstance(section, list):
            raise FeedError(f"{key!r} is not a list")
        sections[key] = section
    return sections


def _content(
    document: dict[str, object], skip: Callable[[str, object], None]
) -> dict[str, str]:
    """Return the ``conference.content`` HTML blocks by key; both levels are optional.

    A block that is not a string is skipped, like any other unreadable record. Keys and
    blocks bypass the record decoders, so their lone surrogates are replaced here (#152).
    """
    conference = document.get("conference", {})
    if not isinstance(conference, dict):
        raise FeedError("'conference' is not an object")
    content = conference.get("content", {})
    if not isinstance(content, dict):
        raise FeedError("'conference.content' is not an object")
    blocks: dict[str, str] = {}
    for key, value in content.items():
        if isinstance(value, str):
            blocks[records.without_surrogates(key)] = records.without_surrogates(value)
        else:
            skip(f"conference.content[{key!r}]", f"should be a string, got {value!r}")
    return blocks


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
