"""The active conference year and the loader for its bundled data (D-05, D-45).

``YEAR`` selects ``data/<year>/``. ``load_year()`` reads that folder's TOML files into the
frozen dataclasses below, through ``year_schema``, then checks their rules. Six
concerns have modules of their own, each with its tables and their checks: the track
registry and the Tracks hub's pages in ``year_tracks`` (D-228), the Open spaces and
Lightning talks pages in ``year_pages`` (D-205), the keynotes in ``year_keynotes``
(D-217), the info pages in ``year_info`` (D-263; About the PSF's and Social's in
``year_links``), the conference moments in ``year_moments`` (D-274), and ``map.toml``'s
floor plans and pins in ``year_map`` (DATA-32). The dataclasses
are the schema: an unknown or missing key, a wrong type or a broken rule fails at load
time with a ``YearDataError`` that names the file, the key and the problem. Years,
dates, names and URLs live in the data files, never in code; rolling over is a new
``data/<year>/`` folder and a new ``YEAR``.

The year's feed snapshot, ``conference.json``, is read only when the app needs it, through
``YearData.read_snapshot()`` (D-38, NEW-03).
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pycon_us.core.feed import process
from pycon_us.core.hours import ServiceHours
from pycon_us.core.rules import DisplayTimeOverride, FeedSettings
from pycon_us.core.slugs import slugify_room
from pycon_us.year_info import (
    Directions,
    HelpInfo,
    SafetyContact,
    SponsorCredits,
    WifiInfo,
    check_credit_sponsors,
    check_directions,
    check_info,
)
from pycon_us.year_keynotes import Keynote, check_keynote_sessions, check_keynotes
from pycon_us.year_links import PsfInfo, SocialInfo
from pycon_us.year_map import MapData, check_hours_pins, check_map
from pycon_us.year_moments import EventReminder, check_moments
from pycon_us.year_pages import (
    LightningTalksInfo,
    OpenSpacesInfo,
    check_https,
    check_pages,
    check_text,
)
from pycon_us.year_schema import YearDataError, build, read_table
from pycon_us.year_tracks import KEYNOTE_TRACKS, Track, TrackFormat, check_tracks

YEAR = 2026
"""The conference year the app shows (D-05)."""

DATA_DIR = Path(__file__).parent / "data"
"""Where the per-year folders live; ``flet build`` bundles it with the package.

A path relative to this module, because ``flet build`` copies ``src/`` into the app rather
than installing it (F15): the files sit next to the code on the phone too.
"""

SNAPSHOT_FILE = "conference.json"
"""The feed snapshot's name in a year folder (D-38, NEW-03)."""


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
    address: str = ""
    """The venue's street address, which Venue & hours shows and copies (MAP-11,
    D-313); empty when not known."""
    directions: Directions | None = None
    """Where Venue & hours' Directions opens a maps app (MAP-11, D-313); None for a
    year without it, whose page has no Directions."""

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

    What feed processing and the Map need, the copy and links of the Open spaces and
    Lightning talks pages (D-205), the keynotes' people and abstracts (D-217), the info
    pages' tables (D-263; the Wi-Fi page's network and password, D-280, and the venue
    hours, D-282), and the hand-authored conference moments (D-274).

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
        keynotes: The keynotes and panels, one entry per session (SESS-08, SPKR-04).
        wifi: The Wi-Fi page's network and password (INFO-08, D-280); None for a year
            without them, whose page shows the feed's block.
        event_reminders: The sign-up moments, written by hand (NOTIF-05); the
            keynotes' moments are derived from the feed (``year_moments``).
        safety_contacts: Help & safety's ways to report a concern, each from a public
            source (INFO-07, D-45, D-281); empty for a year without them.
        help: Help & safety's other lines and links; None for a year without them,
            whose page shows the feed's block (D-281).
        psf: About the PSF's mission, Donate and links (INFO-06, D-283); None for a
            year without them, whose page shows the feed's block.
        social: The Social page's hashtags and links (INFO-10, D-284); None for a
            year without them, whose page shows the feed's block.
        venue_hours: When each venue service is open, for Venue & hours (MAP-09,
            D-282); empty for a year without them, whose page shows the feed's block.
        sponsor_credits: Who provides the Wi-Fi and the quiet room, by sponsor slug
            (D-37, D-337); a year without them credits no one.
    """

    display_time_overrides: tuple[DisplayTimeOverride, ...] = ()
    hall_prefix: str = ""
    lightning_talks_location: str = ""
    other_locations: tuple[str, ...] = ()
    open_spaces: OpenSpacesInfo | None = None
    lightning_talks: LightningTalksInfo | None = None
    keynotes: tuple[Keynote, ...] = ()
    wifi: WifiInfo | None = None
    event_reminders: tuple[EventReminder, ...] = ()
    safety_contacts: tuple[SafetyContact, ...] = ()
    help: HelpInfo | None = None
    psf: PsfInfo | None = None
    social: SocialInfo | None = None
    venue_hours: tuple[ServiceHours, ...] = ()
    sponsor_credits: SponsorCredits = field(default_factory=SponsorCredits)


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
        map: The floor plans and their pins from ``map.toml`` (DATA-32); empty for a
            year without the file.
    """

    conference: ConferenceInfo
    content: Content
    folder: Path
    map: MapData

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


def load_year(
    year: int = YEAR, data_dir: Path = DATA_DIR, *, check_sessions: bool = False
) -> YearData:
    """Load and check the data files of ``year``.

    Args:
        year: The conference year; its files are in ``data_dir/<year>/``.
        data_dir: The folder that holds the year folders.
        check_sessions: Also refuse a keynote whose session the year's bundled
            snapshot lacks, or has on a track not in ``KEYNOTE_TRACKS`` (D-217), and a
            sponsor credit whose slug it lacks (D-337). The tests and tools ask; the app
            does not, since
            parsing the snapshot at every start would cost what D-38 saves, and a
            keynote a newer feed drops just shows no card, a credit no credit.

    Returns:
        The year's data.

    Raises:
        YearDataError: A file is missing, is not valid TOML, or breaks the schema.
            ``map.toml`` alone may be missing: the year then has no plans.
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
    _check_content(content, conference, content_file)
    map_file = f"{year}/map.toml"
    map_data = MapData()
    if (folder / "map.toml").exists():  # a year may bundle no plans (2025)
        map_data = build(MapData, read_table(folder / "map.toml", map_file), map_file)
        check_map(map_data, map_file)
    check_hours_pins(content.venue_hours, map_data, content_file)
    data = YearData(conference, content, folder, map_data)
    if check_sessions and (content.keynotes or content.sponsor_credits.items()):
        # Raises for a year with keynotes or credits but no snapshot to check them by.
        feed = process(data.read_snapshot().raw, data.feed_settings)
        check_keynote_sessions(
            content.keynotes, feed.sessions, KEYNOTE_TRACKS, content_file
        )
        check_credit_sponsors(content.sponsor_credits, feed, content_file)
    return data


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
    if conference.address:
        check_text(conference.address, file, "address")
    if conference.directions is not None:
        check_directions(conference.directions, file)
    check_tracks(conference.tracks, file)


def _check_content(content: Content, conference: ConferenceInfo, file: str) -> None:
    check_pages(content.open_spaces, content.lightning_talks, file)
    check_keynotes(content.keynotes, file)
    check_moments(content.event_reminders, conference.year, conference.zone, file)
    check_info(content, conference, file)
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
