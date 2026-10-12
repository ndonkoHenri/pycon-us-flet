"""The active conference year and the loader for its bundled data (D-05, D-45).

``YEAR`` selects ``data/<year>/``. ``load_year()`` reads that folder's TOML files with
``tomllib`` into the frozen dataclasses below. The dataclasses are the schema: an unknown or
missing key, a wrong type or a broken rule fails at load time with a ``YearDataError`` that
names the file, the key and the problem. Years, dates, names and URLs live in the data
files, never in code; rolling over is a new ``data/<year>/`` folder and a new ``YEAR``.
"""

import dataclasses
import re
import tomllib
import typing
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

YEAR = 2026
"""The conference year the app shows (D-05)."""

DATA_DIR = Path(__file__).parent / "data"
"""Where the per-year folders live; ``flet build`` bundles it with the package."""

TRACK_GROUPS = ("talks", "hands-on", "community", "logistics")
"""The filter-sheet groups a track can belong to, in display order (DATA-14)."""

type TrackFormat = Literal["short", "plural", "long"]

_TYPE_NAMES = {
    str: "a string",
    int: "an integer",
    bool: "true or false",
    date: "a date",
}


class YearDataError(ValueError):
    """A year data file is missing or invalid; the message names the file, key and problem."""


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
    """

    key: str
    short: str
    plural: str
    long: str
    icon: str
    group: str


@dataclass(frozen=True)
class ConferenceInfo:
    """The facts about one conference year, from ``conference.toml``."""

    year: int
    name: str
    time_zone: str
    first_day: date
    last_talk_day: date
    last_day: date
    venue: str
    city: str
    site_url: str
    feed_url: str
    tracks: tuple[Track, ...]

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
        return Track(key, name, name, name, icon="MIC_NONE_OUTLINED", group="talks")

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
class DisplayTimeOverride:
    """Shift the displayed start of matching sessions; grouping keeps the real start (DATA-11).

    Attributes:
        match: A regular expression, matched case-insensitively against the whole cleaned
            session name, so it never matches a longer name by accident.
        minutes: How far to move the displayed start; negative is earlier.
    """

    match: str
    minutes: int

    @property
    def pattern(self) -> re.Pattern[str]:
        """The compiled, case-insensitive ``match``; apply it with ``fullmatch``."""
        return re.compile(self.match, re.IGNORECASE)


@dataclass(frozen=True)
class Content:
    """The year's content from ``content.toml``; for now only the display-time overrides."""

    display_time_overrides: tuple[DisplayTimeOverride, ...] = ()


@dataclass(frozen=True)
class YearData:
    """Everything bundled for one conference year."""

    conference: ConferenceInfo
    content: Content


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
    conference = _build(
        ConferenceInfo,
        _read(folder / "conference.toml", conference_file),
        conference_file,
    )
    _check_conference(conference, year, conference_file)
    content_file = f"{year}/content.toml"
    content = _build(
        Content, _read(folder / "content.toml", content_file), content_file
    )
    _check_content(content, content_file)
    return YearData(conference, content)


def _read(path: Path, file: str) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except FileNotFoundError:
        raise YearDataError(f"{file}: file not found") from None
    except tomllib.TOMLDecodeError as error:
        raise YearDataError(f"{file}: invalid TOML: {error}") from None


def _build[T: DataclassInstance](
    cls: type[T], raw: object, file: str, key: str = ""
) -> T:
    """Build dataclass ``cls`` from a TOML table, checking key names and value types."""
    if not isinstance(raw, dict):
        raise YearDataError(f"{file}: {key}: expected a table, got {raw!r}")
    fields = {field.name: field for field in dataclasses.fields(cls)}
    prefix = f"{key}." if key else ""
    if unknown := sorted(raw.keys() - fields.keys()):
        raise YearDataError(f"{file}: {prefix}{unknown[0]}: unknown key")
    required = [
        name
        for name, field in fields.items()
        if field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
    ]
    if missing := [name for name in required if name not in raw]:
        raise YearDataError(f"{file}: {prefix}{missing[0]}: missing key")
    hints = typing.get_type_hints(cls)
    values = {
        name: _value(hints[name], value, file, prefix + name)
        for name, value in raw.items()
    }
    return cls(**values)


def _value(expected: object, value: object, file: str, key: str) -> object:
    if typing.get_origin(expected) is tuple:  # an array of tables
        item_cls = typing.get_args(expected)[0]
        if not isinstance(value, list):
            raise YearDataError(
                f"{file}: {key}: expected an array of tables, got {value!r}"
            )
        return tuple(
            _build(item_cls, item, file, f"{key}[{index}]")
            for index, item in enumerate(value)
        )
    # type() rather than isinstance(): a bool is not an integer, and a datetime is not a date.
    if type(value) is not expected:
        raise YearDataError(
            f"{file}: {key}: expected {_TYPE_NAMES[expected]}, got {value!r}"
        )
    return value


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
    for key in ("site_url", "feed_url"):
        url = urlsplit(getattr(conference, key))
        if url.scheme != "https" or not url.hostname:
            raise YearDataError(f"{file}: {key}: expected an https:// URL with a host")
    seen: set[str] = set()
    for index, track in enumerate(conference.tracks):
        if track.key in seen:
            raise YearDataError(
                f"{file}: tracks[{index}].key: duplicate track {track.key!r}"
            )
        seen.add(track.key)
        if track.group not in TRACK_GROUPS:
            raise YearDataError(
                f"{file}: tracks[{index}].group: {track.group!r} is not one of {TRACK_GROUPS}"
            )


def _check_content(content: Content, file: str) -> None:
    for index, override in enumerate(content.display_time_overrides):
        try:
            re.compile(override.match)
        except re.error as error:
            raise YearDataError(
                f"{file}: display_time_overrides[{index}].match: {error}"
            ) from None
