"""Tests for the year-data loader (D-45, DATA-34, DATA-14, DATA-28)."""

import shutil
from datetime import UTC, date, datetime
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


def test_the_registration_dashboard_is_year_data_and_optional() -> None:
    # SESS-01's registration guidance links it; 2025 has none, and none is needed.
    assert (
        load_year(2026).conference.registration_url
        == "https://us.pycon.org/2026/accounts/dashboard/"
    )
    assert load_year(2025).conference.registration_url == ""


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


@pytest.mark.parametrize("year", YEARS)
def test_every_track_has_an_icon_of_its_own(year: int) -> None:
    """The hub shows the icons side by side as the key to the tracks (D-197): two
    rows told apart by their circle's colour alone would break D-33."""
    icons = [track.icon for track in load_year(year).conference.tracks]
    assert len(icons) == len(set(icons)), sorted(icons)


def test_track_pages_have_clean_explicit_slugs() -> None:
    """DATA-29: written in the year data, never Ionic's derived ``ais`` or ``…talkss``."""
    slugs = {t.key: t.slug for t in load_year(2026).conference.tracks}
    assert slugs == {
        "Talk": "talks",
        "Keynote": "keynotes",
        "Plenary": "plenaries",
        "Lightning-talks": "lightning-talks",
        "Ai": "ai",
        "Security": "security",
        "Charla": "charlas",
        "Poster": "posters",
        "Tutorial": "tutorials",
        "Sponsor Presentation": "sponsor-presentations",
        "Open Space": "open-spaces",
        "Summit": "summits",
        "Event": "events",
        "Informational": "notices",
        "Break": "breaks",
    }


@pytest.mark.parametrize("year", YEARS)
def test_every_track_has_a_slug_and_a_legend_line(year: int) -> None:
    tracks = load_year(year).conference.tracks
    assert len({t.slug for t in tracks}) == len(tracks)
    assert all(t.legend.strip() for t in tracks)


def test_a_slug_finds_its_track_and_an_unknown_one_none() -> None:
    conference = load_year(2026).conference
    track = conference.track_for_slug("charlas")
    assert track is not None and track.key == "Charla"
    for slug in ("ais", "lightning-talkss", "Charlas", "", "python"):
        assert conference.track_for_slug(slug) is None, slug


def test_a_track_the_registry_lacks_has_no_page() -> None:
    conference = load_year(2026).conference
    assert conference.track("Hallway-track").slug == ""
    assert conference.track_for_slug("") is None


def test_ai_and_security_are_the_new_tracks_of_2026() -> None:
    """SCHED-21: Ionic's "New track!" badge, now a fact of the year data."""
    assert {t.key for t in load_year(2026).conference.tracks if t.new} == {
        "Ai",
        "Security",
    }
    assert not any(t.new for t in load_year(2025).conference.tracks)


@pytest.mark.parametrize("year", YEARS)
def test_a_year_bundles_a_snapshot_exactly_when_it_records_its_capture_time(
    year: int,
) -> None:
    data = load_year(year)
    has_file = (data.folder / config.SNAPSHOT_FILE).is_file()
    assert has_file == (data.conference.snapshot_captured_at is not None)


def test_the_active_year_bundles_its_snapshot() -> None:
    """NEW-03: the app has data on its first launch, offline."""
    data = load_year()
    snapshot = data.read_snapshot()
    assert snapshot.raw == (config.DATA_DIR / "2026" / "conference.json").read_bytes()
    assert snapshot.captured_at == data.conference.snapshot_captured_at
    assert snapshot.captured_at.utcoffset() is not None
    assert snapshot.captured_at < datetime.now(UTC)


def test_a_year_without_a_snapshot_says_so() -> None:
    with pytest.raises(
        YearDataError,
        match=r"^2025/conference\.toml: snapshot_captured_at: missing key; "
        "the year bundles no snapshot$",
    ):
        load_year(2025).read_snapshot()


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
            'site_url = "https://us.pycon.org/2026/"',
            'site_url = "https://us.pycon.org/2026"',
            "2026/conference.toml: site_url: expected a final '/'",
        ),
        (
            "conference.toml",
            'feed_url = "https://us.pycon.org/2026/schedule/conference.json"',
            'feed_url = "https:///2026/schedule/conference.json"',
            "2026/conference.toml: feed_url: expected an https:// URL with a host",
        ),
        (
            "conference.toml",
            'registration_url = "https://',
            'registration_url = "http://',
            "2026/conference.toml: registration_url: expected an https:// URL with a host",
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
            "conference.toml",
            "snapshot_captured_at = ",
            'snapshot_captured_at = "yesterday"\n# ',
            "2026/conference.toml: snapshot_captured_at: expected a date and time, got 'yesterday'",
        ),
        (
            "conference.toml",
            "snapshot_captured_at = ",
            "snapshot_captured_at = 2026-10-12\n# ",
            "2026/conference.toml: snapshot_captured_at: expected a date and time, got datetime.date(2026, 10, 12)",
        ),
        (
            "conference.toml",
            "-07:00\n",
            "\n",
            "2026/conference.toml: snapshot_captured_at: expected a time with a UTC offset",
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
        (
            "content.toml",
            'other_locations = ["Elsewhere",',
            "other_locations = [1,",
            "2026/content.toml: other_locations: expected an array of strings, got [1,",
        ),
        (
            "conference.toml",
            'slug = "ai"',
            'slug = "AI"',
            "2026/conference.toml: tracks[4].slug: 'AI' is not lower-case words",
        ),
        (
            "conference.toml",
            'slug = "ai"',
            'slug = "lightning--talks"',
            "2026/conference.toml: tracks[4].slug: 'lightning--talks' is not",
        ),
        (
            "conference.toml",
            'slug = "ai"',
            'slug = "talks"',
            "2026/conference.toml: tracks[4].slug: duplicate slug 'talks'",
        ),
        (
            "conference.toml",
            'slug = "ai"\n',
            "",
            "2026/conference.toml: tracks[4].slug: missing key",
        ),
        (
            "conference.toml",
            'legend = "Talks given in Spanish"',
            'legend = " "',
            "2026/conference.toml: tracks[6].legend: is empty",
        ),
        (
            "conference.toml",
            'slug = "ai"\nlegend = "A dedicated track on AI: machine learning, LLMs and more"\nnew = true',
            'slug = "ai"\nlegend = "A dedicated track on AI: machine learning, LLMs and more"\nnew = "yes"',
            "2026/conference.toml: tracks[4].new: expected true or false",
        ),
        (
            "content.toml",
            'other_locations = ["Elsewhere",',
            'other_locations = ["Elsewhere", "ELSEWHERE",',
            "2026/content.toml: other_locations[1]: duplicate place 'ELSEWHERE'",
        ),
        (
            "content.toml",
            'other_locations = ["Elsewhere",',
            'other_locations = [" - ",',
            "2026/content.toml: other_locations[0]: names no place",
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
    content = load_year(2026, data_dir).content
    assert content.display_time_overrides == ()
    assert content.other_locations == ()


def test_2026_lists_the_places_that_are_not_rooms() -> None:
    """The Map's "Other locations" (ROOM-01, D-188): Ionic's map had no pin for them."""
    assert load_year(2026).content.other_locations == (
        "Elsewhere",
        "Lobby",
        "Out Front of Hyatt Regency",
    )


def test_missing_file_is_named(data_dir: Path) -> None:
    (data_dir / "2026" / "content.toml").unlink()
    with pytest.raises(YearDataError, match=r"^2026/content\.toml: file not found$"):
        load_year(2026, data_dir)


def test_missing_snapshot_file_is_named(data_dir: Path) -> None:
    (data_dir / "2026" / "conference.json").unlink()
    with pytest.raises(YearDataError, match=r"^2026/conference\.json: file not found$"):
        load_year(2026, data_dir).read_snapshot()


def test_missing_year_is_named(data_dir: Path) -> None:
    with pytest.raises(YearDataError, match=r"^2031/conference\.toml: file not found$"):
        load_year(2031, data_dir)
