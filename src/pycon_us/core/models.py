"""The conference model that feed processing builds and every screen reads (D-41, D-42).

All values are frozen and use identity equality (``eq=False``, D-70 rule 6), so assigning a
new model to a store always notifies, and comparing two large models never walks them.
Objects refer to each other by string id only, so there are no cycles: queries look ids up
in ``ConferenceData`` and return fresh view models instead of mutating these.

Feed processing fills the fields in stages. Decoding (P0-10) gives what the feed states;
Ionic's rules (``core/rules.py``) decide what becomes a session (P0-11) and add cleaned
names, flags and rooms (P0-12). Last, ``feed.process()`` converts the feed's markup once
(D-130, D-140): the ``*_md`` fields and ``Session.search_text`` stay at their empty
defaults until then, beside the raw HTML they come from.
"""

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, eq=False)
class Speaker:
    """A person in the speaker directory.

    Attributes:
        id: The feed's speaker id, as a string.
        name: The display name.
        photo_url: The photo's URL as the feed gives it; empty when there is none.
        bio: The feed's HTML biography; empty when there is none.
        bio_md: ``bio`` as Markdown (D-130).
    """

    id: str
    name: str
    photo_url: str
    bio: str
    bio_md: str = ""


@dataclass(frozen=True, eq=False)
class Session:
    """One item of the schedule: a talk, tutorial, break, notice and so on.

    Attributes:
        id: A stable string id in one of Ionic's four forms (D-42, DATA-26): a slot's
            ``conf_key``; an open space's ``conf_key + 9000``; ``poster-detail-<conf_key>``;
            or ``<kind>-<room>-<start>`` for a collapsed row.
        name: The name as the feed gives it (cleaned by P0-12); ``Posters``, ``Lunch`` and
            so on for a collapsed row.
        kind: The feed's kind, e.g. ``talk``, ``sponsor-workshop`` or ``open-space``.
        track: The track key (DATA-14): the kind with its first letter upper-cased, or
            ``Sponsor Presentation`` for ``sponsor-workshop`` and ``Open Space`` for open
            spaces. ``config.ConferenceInfo.track()`` gives its display names.
        location: The room text; several rooms are joined by ", ".
        display_location: The one place a row shows (DATA-16): an override such as the
            lightning talks' hall, else the first room; empty for a generic break.
        rooms: The rooms in ``location``, one name per room slug, in order (ROOM-06).
        description: The feed's description, empty when there is none: HTML, except
            Markdown for an open space (DATA-25).
        start: When it starts: aware, in the conference zone. Its time group's start.
        display_start: The start to show; earlier than ``start`` for the Job Fair
            (DATA-11), else equal.
        end: When it ends, never before ``start``; equal for a notice.
        day: The conference-local date of ``start``: the day it is listed under.
        speaker_ids: Its speakers in the directory, linked by name (DATA-15).
        speaker_names: Its authors as text, in the feed's order, including names that
            are not in the directory ("Hosted by …").
        pre_registered: Whether attending needs registration (DATA-09).
        spanish: Whether it is given in Spanish (DATA-10).
        url: Its page on the conference site; empty when there is none.
        image_url: An open space's image, absolute; empty when there is none.
        in_timeline: Whether the schedule's days list it; poster details are reached from
            the Posters row, tracks, rooms, speakers and search instead (DATA-07).
        description_md: ``description`` as Markdown (D-130); an open space's as the feed
            gives it, since it is Markdown already (DATA-25).
        search_text: What search matches (D-46): the name, the description's text and
            ``speaker_names``, folded (``queries.fold``).
    """

    id: str
    name: str
    kind: str
    track: str
    location: str
    display_location: str
    rooms: tuple[str, ...]
    description: str
    start: dt.datetime
    display_start: dt.datetime
    end: dt.datetime
    day: dt.date
    speaker_ids: tuple[str, ...]
    speaker_names: tuple[str, ...]
    pre_registered: bool
    spanish: bool
    url: str
    image_url: str
    in_timeline: bool
    description_md: str = ""
    search_text: str = ""


@dataclass(frozen=True, eq=False)
class Room:
    """A room and the sessions in it (DATA-16, ROOM-06).

    Attributes:
        slug: Its slug (``slugs.slugify_room``), the key of its route.
        name: Its name, as the feed first writes it.
        session_ids: Its sessions, by start, then name; a multi-room session is in each.
    """

    slug: str
    name: str
    session_ids: tuple[str, ...]


@dataclass(frozen=True, eq=False)
class TimeGroup:
    """The sessions of one day that start at the same instant: one slot of the timeline.

    Attributes:
        start: The shared start: aware, in the conference zone (DATA-13).
        session_ids: The sessions, ordered by location, then name.
    """

    start: dt.datetime
    session_ids: tuple[str, ...]


@dataclass(frozen=True, eq=False)
class Day:
    """One conference-local day of the schedule.

    Attributes:
        date: The date.
        groups: Its time groups, sorted by start.
    """

    date: dt.date
    groups: tuple[TimeGroup, ...]


@dataclass(frozen=True, eq=False)
class Poster:
    """A poster of the poster session (DATA-24).

    Attributes:
        id: The poster's ``conf_key``, as a string.
        title: The title.
        description: The feed's HTML description.
        speaker_ids: Its authors.
        description_md: ``description`` as Markdown (D-130).
    """

    id: str
    title: str
    description: str
    speaker_ids: tuple[str, ...]
    description_md: str = ""


@dataclass(frozen=True, eq=False)
class Sprint:
    """A project at the development sprints (DATA-24).

    Attributes:
        id: The feed's id, as a string.
        name: The project's name.
        url: The project's website.
        description: HTML or plain text, as the feed gives it.
        logo_url: The logo's URL, or None when the feed has none.
        submitter: Who signed the project up.
        description_md: ``description`` as Markdown (D-130).
        description_text: ``description``'s visible text, whitespace collapsed
            (``html_md.to_text``): the Sprints card's preview (EVT-05).
        search_text: The folded name, submitter and description text, for the
            Sprints filter (EVT-06, D-46): never markup.
    """

    id: str
    name: str
    url: str
    description: str
    logo_url: str | None
    submitter: str
    description_md: str = ""
    description_text: str = ""
    search_text: str = ""


@dataclass(frozen=True, eq=False)
class JobListing:
    """A sponsor's job listing (DATA-24).

    Attributes:
        id: The feed's id, as a string.
        sponsor_name: The sponsor.
        sponsor_logo_url: The sponsor's logo.
        sponsor_level: The sponsorship level, e.g. ``Visionary``.
        description: The feed's HTML list of roles; SPON-09 reads its links.
        description_md: ``description`` as Markdown (D-130).
    """

    id: str
    sponsor_name: str
    sponsor_logo_url: str
    sponsor_level: str
    description: str
    description_md: str = ""


@dataclass(frozen=True, eq=False)
class ConferenceData:
    """One processed feed: everything the screens show about the schedule.

    Attributes:
        sessions: Every session by id: the schedule's slots in feed order, then the
            collapsed rows, the open spaces and the poster details.
        speakers: The speaker directory by id, in order of first appearance: poster
            authors, then the schedule's speakers (DATA-15).
        days: The schedule's days, sorted by date; they hold the sessions in the timeline.
        rooms: Every room of a session, by slug, in natural order of name (DATA-16).
        posters: The posters, in feed order.
        sprints: The sprint projects, in feed order.
        job_listings: The job listings, in feed order.
        dropped: The ids of the records that did not become sessions of their own, by the
            rule that removed them (DATA-04..06): e.g. ``placeholder``, or ``collapsed`` for
            the slots folded into a collapsed row. An open space's id is its session id.
        skipped: One line per feed record that could not be read, naming it and why.
        content: The feed's ``conference.content`` HTML blocks by key, e.g. ``about`` or
            ``venues-hours`` (MAP-09 reads its sections).
        content_md: ``content`` as Markdown, by the same keys (D-130).
    """

    sessions: Mapping[str, Session]
    speakers: Mapping[str, Speaker]
    days: tuple[Day, ...]
    rooms: Mapping[str, Room]
    posters: tuple[Poster, ...]
    sprints: tuple[Sprint, ...]
    job_listings: tuple[JobListing, ...]
    dropped: Mapping[str, tuple[str, ...]]
    skipped: tuple[str, ...]
    content: Mapping[str, str]
    content_md: Mapping[str, str] = field(default_factory=dict)
