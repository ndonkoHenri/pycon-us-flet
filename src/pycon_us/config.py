"""The active conference year and the loader for its bundled data (D-05, D-45).

``YEAR`` selects ``data/<year>/``. ``load_year()`` reads that folder's TOML files into the
frozen dataclasses below (the Open spaces and Lightning talks pages' tables, and their
checks, are in ``year_pages``), through ``year_schema``, then checks their rules. The dataclasses
are the schema: an unknown or missing key, a wrong type or a broken rule fails at load time
with a ``YearDataError`` that names the file, the key and the problem. Years, dates, names and URLs live in the data
files, never in code; rolling over is a new ``data/<year>/`` folder and a new ``YEAR``.

The year's feed snapshot, ``conference.json``, is read only when the app needs it, through
``YearData.read_snapshot()`` (D-38, NEW-03).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pycon_us.core.rules import DisplayTimeOverride, FeedSettings
from pycon_us.core.slugs import slugify_room
from pycon_us.year_pages import (
    LightningTalksInfo,
    OpenSpacesInfo,
    check_https,
    check_pages,
)
from pycon_us.year_schema import YearDataError, build, read_table

YEAR = 2026
"""The conference year the app shows (D-05)."""

DATA_DIR = Path(__file__).parent / "data"
"""Where the per-year folders live; ``flet build`` bundles it with the package.

A path relative to this module, because ``flet build`` copies ``src/`` into the app rather
than installing it (F15): the files sit next to the code on the phone too.
"""

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
"""A track slug: lower-case words joined by single hyphens (DATA-29)."""

SNAPSHOT_FILE = "conference.json"
"""The feed snapshot's name in a year folder (D-38, NEW-03)."""

TRACK_GROUPS = ("talks", "hands-on", "community", "logistics")
"""The filter-sheet groups a track can belong to, in display order (DATA-14)."""

type TrackFormat = Literal["short", "plural", "long"]


@dataclass(frozen=True)
class Track:
    """One entry of the track registry (DATA-14, DATA-28).

    Attributes:
        key: The track as feed processing names it: the feed's kind with its first letter
            upper-cased (``Ai``, ``Lightning-talks``, ``Open Space``).
        short: The name on badges and rows (``AI``).
        plural: The title of a list of its sessions (``Future of AI with Python``).
        long: The full name, for session detail (``The Future of AI with Python``).
        icon: The name of an outlined ``ft.Icons`` member (D-27).
        group: Its group in the filter sheet, one of ``TRACK_GROUPS``.
        slug: Its page's segment in ``/more/tracks/<slug>`` (DATA-29): written out,
            never derived, so a key's spelling (``Ai``, ``Lightning-talks``) never
            leaks into a route; lower case, words joined by ``-``.
        legend: One line on what its sessions are, for the Tracks hub and the track's
            page (EVT-04): "Talks given in Spanish".
        new: Whether the track is new this year: the hub and its page show a "New
            track" badge (SCHED-21).
    """

    key: str
    short: str
    plural: str
    long: str
    icon: str
    group: str
    slug: str
    legend: str
    new: bool = False


HUB_PAGES: dict[str, str | None] = {
    "sprints": None,
    "lightning-talks": "Lightning-talks",
    "open-spaces": "Open Space",
}
"""The Tracks hub's pages of their own, by segment under ``/more/tracks``, with the key of
the track each is the page of (the feed's kinds, DATA-14; the sprints are no track, D-126).

More's pages, also the hub's children, so Back returns to the hub (D-207). The routes
list them before ``:slug``, so the loader refuses a track slug that names another's page.
Here, with the registry, the loader stays free of Flet. #104 adds ``keynotes``.
"""


@dataclass(frozen=True)
class ConferenceInfo:
    """The facts about one conference year, from ``conference.toml``."""

    year: int
    name: str
    time_zone: str
    time_zone_name: str
    first_day: date
    last_talk_day: date
    last_day: date
    venue: str
    city: str
    site_url: str
    feed_url: str
    tracks: tuple[Track, ...]
    snapshot_captured_at: datetime | None = None
    """When ``tools/update_snapshot.py`` fetched the bundled snapshot; aware. None when the
    year bundles no snapshot (only the active year needs one)."""
    registration_url: str = ""
    """Where an attendee checks their registration and adds tutorials or summits to it,
    for session detail's registration guidance (SESS-01); empty when not known."""
    sprints_url: str = ""
    """The site's page about the development sprints, for the Sprints page (EVT-08);
    empty when not known."""
    sprint_submit_url: str = ""
    """Where a project signs up for the sprints, for the Sprints page (EVT-08); empty
    when not known."""

    @property
    def first_sprint_day(self) -> date | None:
        """The first sprint day, the day after the last talk day; None without sprints.

        The sprints run from it to ``last_day``: the feed has no sessions for them
        (D-126), so the year's dates are where they come from (EVT-05).
        """
        if self.last_day == self.last_talk_day:
            return None
        return self.last_talk_day + timedelta(days=1)

    @property
    def zone(self) -> ZoneInfo:
        """The conference's IANA time zone; every displayed time is in it (D-43)."""
        return ZoneInfo(self.time_zone)

    def track(self, key: str) -> Track:
        """Return the registry entry for ``key``, or a humanised stand-in for an unknown key.

        A new kind in next year's feed then still shows a readable name, instead of failing.
        """
        for track in self.tracks:
            if track.key == key:
                return track
        name = key.replace("-", " ")
        name = name[:1].upper() + name[1:]
        # No slug: a track the registry lacks has no page (DATA-29).
        return Track(
            key,
            name,
            name,
            name,
            icon="MIC_NONE_OUTLINED",
            group="talks",
            slug="",
            legend="",
        )

    def track_for_slug(self, slug: str) -> Track | None:
        """Return the registry entry whose page is ``/more/tracks/<slug>``, or None.

        Args:
            slug: A route segment, unquoted; an unknown one has no track (DATA-29).
        """
        for track in self.tracks:
            if track.slug == slug:
                return track
        return None

    def track_name(self, key: str, fmt: TrackFormat = "short") -> str:
        """Return the display name of track ``key`` in the given format (DATA-28)."""
        track = self.track(key)
        match fmt:
            case "short":
                return track.short
            case "plural":
                return track.plural
            case "long":
                return track.long


@dataclass(frozen=True)
class Content:
    """The year's content from ``content.toml`` (D-45).

    What feed processing and the Map need, and the copy and links of the Open spaces
    and Lightning talks pages (D-205).

    Attributes:
        display_time_overrides: Displayed starts to shift (DATA-11).
        hall_prefix: What the year's feed puts before a ``Hall …`` room elsewhere: a
            ``Lunch (Hall AB)`` is served in ``Expo Hall AB`` in 2026 (D-122). Empty
            when the feed names its halls the same way everywhere.
        lightning_talks_location: Where lightning talks are shown to happen, whatever
            rooms they are streamed to (D-124); empty to show their first room.
        other_locations: The places in the feed's room lists that are not rooms
            ("Elsewhere", "Lobby"), as the feed names them: the Map lists them apart,
            under "Other locations" (ROOM-01, D-188). Matched by room slug.
        open_spaces: The Open spaces page's words and link; None for a year that has
            none, whose page shows its sessions alone.
        lightning_talks: The Lightning talks page's copy and links; None for a year
            that has none, whose page shows its sessions alone.
    """

    display_time_overrides: tuple[DisplayTimeOverride, ...] = ()
    hall_prefix: str = ""
    lightning_talks_location: str = ""
    other_locations: tuple[str, ...] = ()
    open_spaces: OpenSpacesInfo | None = None
    lightning_talks: LightningTalksInfo | None = None


@dataclass(frozen=True, eq=False)
class Snapshot:
    """The feed snapshot bundled for an offline first launch (D-38, NEW-03).

    Attributes:
        raw: The public feed's bytes exactly as fetched, so the current parser reads them
            (D-47).
        captured_at: When they were fetched: aware. The status strip shows the data's age
            from it (P1).
    """

    raw: bytes
    captured_at: datetime


@dataclass(frozen=True)
class YearData:
    """Everything bundled for one conference year.

    Attributes:
        conference: The facts from ``conference.toml``.
        content: The texts and overrides from ``content.toml``.
        folder: The year's folder, where ``read_snapshot()`` finds the snapshot.
    """

    conference: ConferenceInfo
    content: Content
    folder: Path

    @property
    def feed_settings(self) -> FeedSettings:
        """What feed processing needs from this year's data."""
        return FeedSettings(
            time_zone=self.conference.zone,
            site_url=self.conference.site_url,
            hall_prefix=self.content.hall_prefix,
            lightning_talks_location=self.content.lightning_talks_location,
            display_time_overrides=self.content.display_time_overrides,
        )

    def read_snapshot(self) -> Snapshot:
        """Read the year's bundled feed snapshot (D-38, NEW-03).

        It is read on demand, not by ``load_year()``: once a feed cache exists the app
        never needs it. The bytes are not checked here; ``feed.process`` does that, and a
        test processes the committed snapshot.

        Returns:
            The snapshot's bytes and capture time.

        Raises:
            YearDataError: The year bundles no snapshot (``snapshot_captured_at`` is not
                set), or ``conference.json`` is missing: a broken build.
        """
        year = self.conference.year
        captured_at = self.conference.snapshot_captured_at
        if captured_at is None:
            raise YearDataError(
                f"{year}/conference.toml: snapshot_captured_at: missing key; "
                "the year bundles no snapshot"
            )
        try:
            raw = (self.folder / SNAPSHOT_FILE).read_bytes()
        except FileNotFoundError:
            raise YearDataError(f"{year}/{SNAPSHOT_FILE}: file not found") from None
        return Snapshot(raw, captured_at)


def load_year(year: int = YEAR, data_dir: Path = DATA_DIR) -> YearData:
    """Load and check the data files of ``year``.

    Args:
        year: The conference year; its files are in ``data_dir/<year>/``.
        data_dir: The folder that holds the year folders.

    Returns:
        The year's data.

    Raises:
        YearDataError: A file is missing, is not valid TOML, or breaks the schema.
    """
    folder = data_dir / str(year)
    conference_file = f"{year}/conference.toml"
    conference = build(
        ConferenceInfo,
        read_table(folder / "conference.toml", conference_file),
        conference_file,
    )
    _check_conference(conference, year, conference_file)
    content_file = f"{year}/content.toml"
    content = build(
        Content, read_table(folder / "content.toml", content_file), content_file
    )
    _check_content(content, content_file)
    return YearData(conference, content, folder)


def _check_conference(conference: ConferenceInfo, year: int, file: str) -> None:
    if conference.year != year:
        raise YearDataError(
            f"{file}: year: {conference.year} does not match the folder {year}"
        )
    try:
        ZoneInfo(conference.time_zone)
    except ZoneInfoNotFoundError, ValueError:
        raise YearDataError(
            f"{file}: time_zone: unknown time zone {conference.time_zone!r}"
        ) from None
    if conference.first_day.year != year:
        raise YearDataError(
            f"{file}: first_day: {conference.first_day} is not in {year}"
        )
    if conference.last_talk_day < conference.first_day:
        raise YearDataError(f"{file}: last_talk_day: is before first_day")
    if conference.last_day < conference.last_talk_day:
        raise YearDataError(f"{file}: last_day: is before last_talk_day")
    captured_at = conference.snapshot_captured_at
    if captured_at is not None and captured_at.utcoffset() is None:
        raise YearDataError(
            f"{file}: snapshot_captured_at: expected a time with a UTC offset"
        )
    optional = tuple(
        key
        for key in ("registration_url", "sprints_url", "sprint_submit_url")
        if getattr(conference, key)
    )
    for key in ("site_url", "feed_url", *optional):
        check_https(getattr(conference, key), file, key)
    if not conference.site_url.endswith("/"):  # site-relative links resolve against it
        raise YearDataError(f"{file}: site_url: expected a final '/'")
    seen: set[str] = set()
    slugs: set[str] = set()
    for index, track in enumerate(conference.tracks):
        if track.key in seen:
            raise YearDataError(
                f"{file}: tracks[{index}].key: duplicate track {track.key!r}"
            )
        seen.add(track.key)
        if not _SLUG.fullmatch(track.slug):
            raise YearDataError(
                f"{file}: tracks[{index}].slug: {track.slug!r} is not lower-case "
                "words joined by '-'"
            )
        if track.slug in slugs:
            raise YearDataError(
                f"{file}: tracks[{index}].slug: duplicate slug {track.slug!r}"
            )
        slugs.add(track.slug)
        _check_hub_page(track, file, index)
        if not track.legend.strip():
            raise YearDataError(f"{file}: tracks[{index}].legend: is empty")
        if track.group not in TRACK_GROUPS:
            raise YearDataError(
                f"{file}: tracks[{index}].group: {track.group!r} is not one of {TRACK_GROUPS}"
            )


def _check_content(content: Content, file: str) -> None:
    check_pages(content.open_spaces, content.lightning_talks, file)
    seen: set[str] = set()
    for index, name in enumerate(content.other_locations):
        slug = slugify_room(name)
        if not slug:
            raise YearDataError(f"{file}: other_locations[{index}]: names no place")
        if slug in seen:
            raise YearDataError(
                f"{file}: other_locations[{index}]: duplicate place {name!r}"
            )
        seen.add(slug)
    for index, override in enumerate(content.display_time_overrides):
        try:
            re.compile(override.match)
        except re.error as error:
            raise YearDataError(
                f"{file}: display_time_overrides[{index}].match: {error}"
            ) from None


def _check_hub_page(track: Track, file: str, index: int) -> None:
    """Refuse a track slug that names a page of the hub's other than the track's own.

    The hub's pages (``HUB_PAGES``) come before ``:slug`` under ``/more/tracks``
    (D-207), so a track at ``sprints`` would have no page. A track with a page of its
    own keeps the page's segment as its slug: its hub row pushes
    ``/more/tracks/<slug>``, which must be that page.
    """
    own = next((seg for seg, key in HUB_PAGES.items() if key == track.key), None)
    if own is not None and track.slug != own:
        raise YearDataError(
            f"{file}: tracks[{index}].slug: expected {own!r}, the segment of "
            f"the track's own page, /more/tracks/{own}"
        )
    if own is None and track.slug in HUB_PAGES:
        raise YearDataError(
            f"{file}: tracks[{index}].slug: {track.slug!r} is the segment of "
            f"another page, /more/tracks/{track.slug}"
        )
