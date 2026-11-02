"""Tests for the year-data loader (D-45, DATA-34, DATA-14, DATA-28).

The tracks' registry is ``test_config_tracks.py``'s; a malformed or missing file,
``test_config_errors.py``'s.
"""

import subprocess
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from pycon_us import config
from pycon_us.config import YearDataError, load_year

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


@pytest.mark.parametrize("year", YEARS)
def test_every_year_loads(year: int) -> None:
    """Each bundled year loads with its year, its feed URL and some tracks."""
    data = load_year(year)
    assert data.conference.year == year
    assert (
        data.conference.feed_url
        == f"https://us.pycon.org/{year}/schedule/conference.json"
    )
    assert data.conference.tracks


def test_the_year_loader_loads_no_flet_module() -> None:
    """The tools read the year data without Flet: dependencies point down (§1)."""
    probe = "import sys, pycon_us.config; print('flet' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_the_active_year_has_a_folder_of_its_own() -> None:
    """``load_year()`` reads ``YEAR``'s folder, whose dates fall in that year (D-05)."""
    conference = load_year().conference
    assert conference.year == config.YEAR
    assert conference.first_day.year == config.YEAR
    assert conference.last_day.year == config.YEAR


def test_2026_is_in_pacific_time() -> None:
    """2026 is in Pacific Time, May 13 to 19 with talks to May 17."""
    conference = load_year(2026).conference
    assert conference.zone == ZoneInfo("America/Los_Angeles")
    assert conference.time_zone_name == "Pacific Time"
    assert (conference.first_day, conference.last_talk_day, conference.last_day) == (
        date(2026, 5, 13),
        date(2026, 5, 17),
        date(2026, 5, 19),
    )


def test_the_registration_dashboard_is_year_data_and_optional() -> None:
    """2026 names its registration dashboard, and 2025 loads with none.

    SESS-01's registration guidance links it; 2025 has none, and none is needed.
    """
    assert (
        load_year(2026).conference.registration_url
        == "https://us.pycon.org/2026/accounts/dashboard/"
    )
    assert load_year(2025).conference.registration_url == ""


def test_the_sprint_pages_are_year_data_and_optional() -> None:
    """2026 names its sprint info and project form pages, and 2025 loads with neither.

    EVT-08: they are the Sprints page's menu; 2025's feed has no sprint projects.
    """
    conference = load_year(2026).conference
    assert conference.sprints_url == "https://us.pycon.org/2026/events/dev-sprints/"
    assert (
        conference.sprint_submit_url
        == "https://us.pycon.org/2026/sprints/project/submit/"
    )
    assert load_year(2025).conference.sprints_url == ""
    assert load_year(2025).conference.sprint_submit_url == ""


def test_the_speaker_discord_page_is_year_data_and_optional() -> None:
    """2026 names the public page Ionic opened for speakers; 2025 loads without it.

    AUTH-10, D-411: a web page in the in-app browser, never an /api/v1 call (D-51).
    """
    conference = load_year(2026).conference
    assert (
        conference.speaker_discord_url
        == "https://us.pycon.org/2026/speaker/join_discord/"
    )
    assert "/api/" not in conference.speaker_discord_url
    assert load_year(2025).conference.speaker_discord_url == ""


def test_the_sprints_follow_the_last_talk_day() -> None:
    """EVT-05: the feed has no sessions for them; the year's dates say when they are."""
    conference = load_year(2026).conference
    assert conference.first_sprint_day == date(2026, 5, 18)
    without = replace(conference, last_day=conference.last_talk_day)
    assert without.first_sprint_day is None


def test_2025_is_in_eastern_time() -> None:
    """2025's conference is in the New York zone, named Eastern Time."""
    conference = load_year(2025).conference
    assert conference.zone == ZoneInfo("America/New_York")
    assert conference.time_zone_name == "Eastern Time"


def test_job_fair_override_matches_only_the_whole_name() -> None:
    """The Job Fair's -30 minute override matches its whole name only.

    Case and spacing don't count, but a longer name that starts with it is no match.
    """
    (override,) = load_year(2026).content.display_time_overrides
    assert override.minutes == -30
    assert override.pattern.fullmatch("Job Fair & Community Showcase")
    assert override.pattern.fullmatch("job fair &  community showcase ")
    assert not override.pattern.fullmatch(
        "Job Fair & Community Showcase & Poster Sessions"
    )


@pytest.mark.parametrize("year", YEARS)
def test_a_year_bundles_a_snapshot_exactly_when_it_records_its_capture_time(
    year: int,
) -> None:
    """A year has a snapshot file exactly when it records ``snapshot_captured_at``."""
    data = load_year(year)
    has_file = (data.folder / config.SNAPSHOT_FILE).is_file()
    assert has_file == (data.conference.snapshot_captured_at is not None)


def test_the_active_year_bundles_its_snapshot() -> None:
    """NEW-03: the app has data on its first launch, offline."""
    data = load_year()
    snapshot = data.read_snapshot()
    folder = config.DATA_DIR / str(config.YEAR)
    assert snapshot.raw == (folder / config.SNAPSHOT_FILE).read_bytes()
    assert snapshot.captured_at == data.conference.snapshot_captured_at
    assert snapshot.captured_at.utcoffset() is not None
    assert snapshot.captured_at < datetime.now(UTC)


def test_a_year_without_a_snapshot_says_so() -> None:
    """Reading 2025's snapshot raises a ``YearDataError`` that names the missing key."""
    with pytest.raises(
        YearDataError,
        match=r"^2025/conference\.toml: snapshot_captured_at: missing key; "
        "the year bundles no snapshot$",
    ):
        load_year(2025).read_snapshot()


def test_2026_lists_the_places_that_are_not_rooms() -> None:
    """The Map's "Other locations" (ROOM-01, D-188): Ionic's map had no pin for them."""
    assert load_year(2026).content.other_locations == (
        "Elsewhere",
        "Lobby",
        "Out Front of Hyatt Regency",
    )


def test_2026_has_the_open_spaces_and_lightning_talks_pages_copy() -> None:
    """EVT-02, EVT-03: their links and words are year data (D-45), never code."""
    content = load_year(2026).content
    assert content.open_spaces is not None
    assert content.open_spaces.propose_url == (
        "https://us.pycon.org/2026/signup/open-space/"
    )
    talks = content.lightning_talks
    assert talks is not None
    assert talks.signup_url == "https://us.pycon.org/2026/signup/lightning-talk/"
    assert talks.info_url == "https://us.pycon.org/2026/events/lightning-talks/"
    assert talks.heading and talks.intro and len(talks.doubts) == 4
    # Copy in the app's voice (ux.md §4.9): no exclamation marks.
    words = [talks.heading, *talks.intro, content.open_spaces.intro]
    words += [text for d in talks.doubts for text in (d.doubt, d.answer)]
    assert not any("!" in text for text in words)


def test_a_year_may_leave_out_the_pages_copy() -> None:
    """2025 keeps only what its recorded feed needs: its pages show the sessions."""
    content = load_year(2025).content
    assert (content.open_spaces, content.lightning_talks) == (None, None)
