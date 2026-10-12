"""The conference model that feed processing builds and every screen reads (D-41, D-42).

All values are frozen and use identity equality (``eq=False``, D-70 rule 6), so assigning a
new model to a store always notifies, and comparing two large models never walks them.
Objects refer to each other by string id only, so there are no cycles: queries look ids up
in ``ConferenceData`` and return fresh view models instead of mutating these.

Feed processing fills the fields in stages. Decoding (P0-10) gives what the feed states;
Ionic's rules (``core/rules.py``) decide what becomes a session (P0-11) and add cleaned
names, flags and rooms (P0-12).
"""

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, eq=False)
class Speaker:
    """A person in the speaker directory.

    Attributes:
        id: The feed's speaker id, as a string.
        name: The display name.
        photo_url: The photo's URL as the feed gives it; empty when there is none.
        bio: The feed's HTML biography; empty when there is none.
    """

    id: str
    name: str
    photo_url: str
    bio: str


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
        description: The feed's description, empty when there is none: HTML, except
            Markdown for an open space (DATA-25).
        start: When it starts: aware, in the conference zone.
        end: When it ends, never before ``start``; equal for a notice.
        day: The conference-local date of ``start``: the day it is listed under.
        speaker_ids: Its speakers, in the feed's order.
        url: Its page on the conference site; empty when there is none.
        image_url: An open space's image, absolute; empty when there is none.
        in_timeline: Whether the schedule's days list it; poster details are reached from
            the Posters row, tracks, rooms, speakers and search instead (DATA-07).
    """

    id: str
    name: str
    kind: str
    track: str
    location: str
    description: str
    start: dt.datetime
    end: dt.datetime
    day: dt.date
    speaker_ids: tuple[str, ...]
    url: str
    image_url: str
    in_timeline: bool


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
    """

    id: str
    title: str
    description: str
    speaker_ids: tuple[str, ...]


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
    """

    id: str
    name: str
    url: str
    description: str
    logo_url: str | None
    submitter: str


@dataclass(frozen=True, eq=False)
class JobListing:
    """A sponsor's job listing (DATA-24).

    Attributes:
        id: The feed's id, as a string.
        sponsor_name: The sponsor.
        sponsor_logo_url: The sponsor's logo.
        sponsor_level: The sponsorship level, e.g. ``Visionary``.
        description: The feed's HTML list of roles.
    """

    id: str
    sponsor_name: str
    sponsor_logo_url: str
    sponsor_level: str
    description: str


@dataclass(frozen=True, eq=False)
class ConferenceData:
    """One processed feed: everything the screens show about the schedule.

    Attributes:
        sessions: Every session by id: the schedule's slots in feed order, then the
            collapsed rows, the open spaces and the poster details.
        speakers: Every speaker of a session or poster by id, in order of first appearance.
        days: The schedule's days, sorted by date; they hold the sessions in the timeline.
        posters: The posters, in feed order.
        sprints: The sprint projects, in feed order.
        job_listings: The job listings, in feed order.
        dropped: The ids of the records that did not become sessions of their own, by the
            rule that removed them (DATA-04..06): e.g. ``placeholder``, or ``collapsed`` for
            the slots folded into a collapsed row. An open space's id is its session id.
        skipped: One line per feed record that could not be read, naming it and why.
    """

    sessions: Mapping[str, Session]
    speakers: Mapping[str, Speaker]
    days: tuple[Day, ...]
    posters: tuple[Poster, ...]
    sprints: tuple[Sprint, ...]
    job_listings: tuple[JobListing, ...]
    dropped: Mapping[str, tuple[str, ...]]
    skipped: tuple[str, ...]
