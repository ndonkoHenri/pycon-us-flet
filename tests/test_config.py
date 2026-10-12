"""Tests for the year-data loader (D-45, DATA-34, DATA-14, DATA-28)."""

import shutil
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import config
from pycon_us.config import YearDataError, load_year

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


@pytest.mark.parametrize("year", YEARS)
def test_every_year_loads(year: int) -> None:
    data = load_year(year)
    assert data.conference.year == year
    assert (
        data.conference.feed_url
        == f"https://us.pycon.org/{year}/schedule/conference.json"
    )
    assert data.conference.tracks


def test_the_active_year_is_2026_in_pacific_time() -> None:
    conference = load_year().conference
    assert config.YEAR == 2026
    assert conference.zone == ZoneInfo("America/Los_Angeles")
    assert conference.time_zone_name == "Pacific Time"
    assert (conference.first_day, conference.last_talk_day, conference.last_day) == (
        date(2026, 5, 13),
        date(2026, 5, 17),
        date(2026, 5, 19),
    )


def test_2025_is_in_eastern_time() -> None:
    conference = load_year(2025).conference
    assert conference.zone == ZoneInfo("America/New_York")
    assert conference.time_zone_name == "Eastern Time"


def test_job_fair_override_matches_only_the_whole_name() -> None:
    (override,) = load_year(2026).content.display_time_overrides
    assert override.minutes == -30
    assert override.pattern.fullmatch("Job Fair & Community Showcase")
    assert override.pattern.fullmatch("job fair &  community showcase ")
    assert not override.pattern.fullmatch(
        "Job Fair & Community Showcase & Poster Sessions"
    )


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("short", "AI"),
        ("plural", "Future of AI with Python"),
        ("long", "The Future of AI with Python"),
    ],
)
def test_track_name_formats(fmt: config.TrackFormat, expected: str) -> None:
    assert load_year(2026).conference.track_name("Ai", fmt) == expected


def test_security_keeps_its_track_title() -> None:
    conference = load_year(2026).conference
    assert conference.track_name("Security") == "Security"
    assert conference.track_name("Security", "plural") == "Trailblazing Python Security"


def test_2026_registry_names_every_processed_track() -> None:
    keys = {track.key for track in load_year(2026).conference.tracks}
    assert keys == {
        "Talk",
        "Keynote",
        "Plenary",
        "Lightning-talks",
        "Ai",
        "Security",
        "Charla",
        "Poster",
        "Tutorial",
        "Sponsor Presentation",
        "Open Space",
        "Summit",
        "Event",
        "Informational",
        "Break",
    }


def test_track_name_defaults_to_short() -> None:
    assert load_year(2026).conference.track_name("Lightning-talks") == "Lightning talks"


@pytest.mark.parametrize("fmt", ["short", "plural", "long"])
def test_unknown_track_falls_back_to_its_humanised_key(fmt: config.TrackFormat) -> None:
    conference = load_year(2026).conference
    assert conference.track_name("Hallway-track", fmt) == "Hallway track"
    assert conference.track("Hallway-track").group in config.TRACK_GROUPS


@pytest.mark.parametrize("year", YEARS)
def test_track_icons_are_material_icon_names(year: int) -> None:
    for track in load_year(year).conference.tracks:
        assert hasattr(ft.Icons, track.icon), track.key


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the bundled year data."""
    shutil.copytree(config.DATA_DIR, tmp_path, dirs_exist_ok=True)
    return tmp_path


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


@pytest.mark.parametrize(
    ("file", "old", "new", "message"),
    [
        (
            "conference.toml",
            'city = "Long Beach, CA"',
            'city = "Long Beach, CA"\ncolour = "red"',
            "2026/conference.toml: colour: unknown key",
        ),
        (
            "conference.toml",
            'feed_url = "https://us.pycon.org/2026/schedule/conference.json"',
            "",
            "2026/conference.toml: feed_url: missing key",
        ),
        (
            "conference.toml",
            "first_day = 2026-05-13",
            'first_day = "2026-05-13"',
            "2026/conference.toml: first_day: expected a date, got '2026-05-13'",
        ),
        (
            "conference.toml",
            "first_day = 2026-05-13",
            "first_day = 2026-05-13T09:00:00",
            "2026/conference.toml: first_day: expected a date",
        ),
        (
            "conference.toml",
            "year = 2026",
            "year = true",
            "2026/conference.toml: year: expected an integer, got True",
        ),
        (
            "conference.toml",
            "year = 2026",
            "year = 2027",
            "2026/conference.toml: year: 2027 does not match the folder 2026",
        ),
        (
            "conference.toml",
            '"America/Los_Angeles"',
            '"America/Long_Beach"',
            "2026/conference.toml: time_zone: unknown time zone 'America/Long_Beach'",
        ),
        (
            "conference.toml",
            "last_talk_day = 2026-05-17",
            "last_talk_day = 2026-05-12",
            "2026/conference.toml: last_talk_day: is before first_day",
        ),
        (
            "conference.toml",
            "last_day = 2026-05-19",
            "last_day = 2026-05-16",
            "2026/conference.toml: last_day: is before last_talk_day",
        ),
        (
            "conference.toml",
            'site_url = "https://',
            'site_url = "http://',
            "2026/conference.toml: site_url: expected an https:// URL with a host",
        ),
        (
            "conference.toml",
            'feed_url = "https://us.pycon.org/2026/schedule/conference.json"',
            'feed_url = "https:///2026/schedule/conference.json"',
            "2026/conference.toml: feed_url: expected an https:// URL with a host",
        ),
        (
            "conference.toml",
            'key = "Keynote"',
            'key = "Talk"',
            "2026/conference.toml: tracks[1].key: duplicate track 'Talk'",
        ),
        (
            "conference.toml",
            'group = "hands-on"',
            'group = "workshops"',
            "2026/conference.toml: tracks[8].group: 'workshops' is not one of",
        ),
        (
            "conference.toml",
            'short = "Talk"',
            "short = 1",
            "2026/conference.toml: tracks[0].short: expected a string, got 1",
        ),
        (
            "conference.toml",
            'long = "Talk"',
            "",
            "2026/conference.toml: tracks[0].long: missing key",
        ),
        (
            "conference.toml",
            "year = 2026",
            "year = ",
            "2026/conference.toml: invalid TOML",
        ),
        (
            "content.toml",
            "minutes = -30",
            'minutes = "-30"',
            "2026/content.toml: display_time_overrides[0].minutes: expected an integer",
        ),
        (
            "content.toml",
            "minutes = -30",
            'minutes = -30\ncolour = "red"',
            "2026/content.toml: display_time_overrides[0].colour: unknown key",
        ),
        (
            "content.toml",
            "[[display_time_overrides]]",
            "[display_time_overrides]",
            "2026/content.toml: display_time_overrides: expected an array of tables",
        ),
        (
            "content.toml",
            r"match = '\s*job",
            r"match = '(\s*job",
            "2026/content.toml: display_time_overrides[0].match: missing ),",
        ),
    ],
)
def test_malformed_file_names_file_key_and_problem(
    data_dir: Path, file: str, old: str, new: str, message: str
) -> None:
    edit(data_dir / "2026" / file, old, new)
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value).startswith(message)


def test_array_items_must_be_tables(data_dir: Path) -> None:
    (data_dir / "2026" / "content.toml").write_text(
        'display_time_overrides = ["Job Fair"]\n', encoding="utf-8"
    )
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value) == (
        "2026/content.toml: display_time_overrides[0]: expected a table, got 'Job Fair'"
    )


def test_content_without_overrides_has_none(data_dir: Path) -> None:
    (data_dir / "2026" / "content.toml").write_text("# nothing yet\n", encoding="utf-8")
    assert load_year(2026, data_dir).content.display_time_overrides == ()


def test_missing_file_is_named(data_dir: Path) -> None:
    (data_dir / "2026" / "content.toml").unlink()
    with pytest.raises(YearDataError, match=r"^2026/content\.toml: file not found$"):
        load_year(2026, data_dir)


def test_missing_year_is_named(data_dir: Path) -> None:
    with pytest.raises(YearDataError, match=r"^2031/conference\.toml: file not found$"):
        load_year(2031, data_dir)
