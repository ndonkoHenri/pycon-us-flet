"""Tests for the year-data loader's errors: a malformed or missing file names what is wrong (D-45)."""

import shutil
from pathlib import Path

import pytest

from pycon_us import config
from pycon_us.config import YearDataError, load_year


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the bundled year data."""
    shutil.copytree(config.DATA_DIR, tmp_path, dirs_exist_ok=True)
    return tmp_path


def edit(path: Path, old: str, new: str) -> None:
    """Replace the first ``old`` in ``path`` with ``new``; ``old`` must be there."""
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
            'sprints_url = "https://',
            'sprints_url = "http://',
            "2026/conference.toml: sprints_url: expected an https:// URL with a host",
        ),
        (
            "conference.toml",
            'sprint_submit_url = "https://us.pycon.org',
            'sprint_submit_url = "https://',
            "2026/conference.toml: sprint_submit_url: expected an https:// URL",
        ),
        (
            "conference.toml",
            'speaker_discord_url = "https://',
            'speaker_discord_url = "http://',
            "2026/conference.toml: speaker_discord_url: expected an https:// URL with a host",
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
        (  # the hub's pages come before :slug: such a track has no page (D-207)
            "conference.toml",
            'slug = "charlas"',
            'slug = "sprints"',
            "2026/conference.toml: tracks[6].slug: 'sprints' is the segment of",
        ),
        (
            "conference.toml",
            'slug = "charlas"',
            'slug = "open-spaces"',
            "2026/conference.toml: tracks[6].slug: 'open-spaces' is the segment of",
        ),
        (  # its hub row pushes its slug, which must be its own page
            "conference.toml",
            'slug = "lightning-talks"',
            'slug = "lightning"',
            "2026/conference.toml: tracks[3].slug: expected 'lightning-talks', the",
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
        (
            "content.toml",
            'propose_url = "https://',
            'propose_url = "http://',
            "2026/content.toml: open_spaces.propose_url: expected an https:// URL",
        ),
        (
            "content.toml",
            'intro = "Hour-long sessions',
            'intro = " "\nx = "',
            "2026/content.toml: open_spaces.x: unknown key",
        ),
        (
            "content.toml",
            'intro = "Hour-long sessions',
            'intro = " "\n# "',
            "2026/content.toml: open_spaces.intro: is empty",
        ),
        (
            "content.toml",
            'signup_url = "https://',
            'signup_url = "mailto:',
            "2026/content.toml: lightning_talks.signup_url: expected an https:// URL",
        ),
        (
            "content.toml",
            'info_url = "https://us.pycon.org/2026/events/lightning-talks/"\n',
            "",
            "2026/content.toml: lightning_talks.info_url: missing key",
        ),
        (
            "content.toml",
            'answer = "They don',
            'answer = " "\n# "They don',
            "2026/content.toml: lightning_talks.doubts[0].answer: is empty",
        ),
        (
            "content.toml",
            'heading = "What',
            'heading = 5\n# "What',
            "2026/content.toml: lightning_talks.heading: expected a string, got 5",
        ),
    ],
)
def test_malformed_file_names_file_key_and_problem(
    data_dir: Path, file: str, old: str, new: str, message: str
) -> None:
    """A malformed year file's error names the file, the problem and any key.

    A schema error names the key it broke; invalid TOML has no key to name.
    """
    edit(data_dir / "2026" / file, old, new)
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value).startswith(message)


def test_lightning_talks_need_a_doubt_to_fold(data_dir: Path) -> None:
    """An empty "Think you can't do one?" would open on nothing (EVT-03)."""
    file = data_dir / "2026" / "content.toml"
    head = file.read_text(encoding="utf-8").split("[[lightning_talks.doubts]]")[0]
    file.write_text(head + "doubts = []\n", encoding="utf-8")
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value) == "2026/content.toml: lightning_talks.doubts: is empty"


def test_array_items_must_be_tables(data_dir: Path) -> None:
    """An array item that is a string, not a table, raises an error naming its index."""
    (data_dir / "2026" / "content.toml").write_text(
        'display_time_overrides = ["Job Fair"]\n', encoding="utf-8"
    )
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value) == (
        "2026/content.toml: display_time_overrides[0]: expected a table, got 'Job Fair'"
    )


def test_a_pages_copy_must_be_a_table(data_dir: Path) -> None:
    """A page's copy that is not a table raises an error naming it and its value."""
    (data_dir / "2026" / "content.toml").write_text(
        "open_spaces = 1\n", encoding="utf-8"
    )
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value) == "2026/content.toml: open_spaces: expected a table, got 1"


def test_content_without_overrides_has_none(data_dir: Path) -> None:
    """A ``content.toml`` with nothing set has no overrides and no other locations."""
    (data_dir / "2026" / "content.toml").write_text("# nothing yet\n", encoding="utf-8")
    content = load_year(2026, data_dir).content
    assert content.display_time_overrides == ()
    assert content.other_locations == ()


def test_missing_file_is_named(data_dir: Path) -> None:
    """A missing ``content.toml`` raises an error naming that file."""
    (data_dir / "2026" / "content.toml").unlink()
    with pytest.raises(YearDataError, match=r"^2026/content\.toml: file not found$"):
        load_year(2026, data_dir)


def test_missing_snapshot_file_is_named(data_dir: Path) -> None:
    """A missing ``conference.json`` is named when the snapshot is read."""
    (data_dir / "2026" / "conference.json").unlink()
    with pytest.raises(YearDataError, match=r"^2026/conference\.json: file not found$"):
        load_year(2026, data_dir).read_snapshot()


def test_missing_year_is_named(data_dir: Path) -> None:
    """A year without a folder raises an error naming its ``conference.toml``."""
    with pytest.raises(YearDataError, match=r"^2031/conference\.toml: file not found$"):
        load_year(2031, data_dir)
