"""Tests for the conference moments (``year_moments.py``; #381, D-274, NOTIF-05).

The sign-up moments are ``content.toml`` entries, written by hand with their public
source; the keynotes' and panels' are derived from the feed, 15 minutes before each
starts, so a keynote the feed moves takes its moment along.
"""

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pycon_us import config
from pycon_us.config import YearDataError, load_year
from pycon_us.core.feed import process
from pycon_us.core.timeline import keynote_sessions
from pycon_us.locations import PAGES, drill_href, parent_of
from pycon_us.screens import keynotes
from pycon_us.year_moments import (
    DERIVED_IDS,
    HAND_IDS,
    KEYNOTE_LEAD,
    KEYNOTE_TRACK,
    EventReminder,
    keynote_moments,
)
from pycon_us.year_tracks import HUB_PAGES
from tests.feeds import changed, processed, retime, settings

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


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


def derived(year: int, *, use_24h: bool = False) -> tuple[EventReminder, ...]:
    """The keynote moments of ``year``'s recorded feed and year data."""
    data = load_year(year)
    return keynote_moments(
        processed(year), data.content.keynotes, data.conference.zone, use_24h=use_24h
    )


# ------------------------------------------------------------- the hand-authored moments


@pytest.mark.parametrize("year", YEARS)
def test_every_hand_moment_names_its_source_and_when_it_was_checked(year: int) -> None:
    """Each hand entry has a public https source and a checked date (D-274)."""
    moments = load_year(year).content.event_reminders
    assert moments
    for moment in moments:
        assert moment.source.startswith(f"https://us.pycon.org/{year}/")
        assert moment.checked is not None


@pytest.mark.parametrize("year", YEARS)
def test_every_hand_moment_opens_a_page_of_the_app(year: int) -> None:
    """A tap opens the moment's own page, never Now (D-274)."""
    for moment in load_year(year).content.event_reminders:
        assert moment.route in PAGES
        assert moment.route != "/now"


def test_2026_reminds_of_the_lightning_talk_and_open_space_sign_ups() -> None:
    """2026: two lightning-talk moments and an open-space one before each talk day."""
    moments = load_year(2026).content.event_reminders
    assert [(m.id, m.category, m.route) for m in moments] == [
        (8000, "open_space", "/more/open-spaces"),
        (8001, "lightning", "/more/lightning-talks"),
        (8002, "open_space", "/more/open-spaces"),
        (8003, "lightning", "/more/lightning-talks"),
        (8004, "open_space", "/more/open-spaces"),
    ]
    zone = ZoneInfo("America/Los_Angeles")
    assert [m.at.astimezone(zone).date().isoformat() for m in moments] == [
        "2026-05-14",
        "2026-05-15",
        "2026-05-15",
        "2026-05-16",
        "2026-05-16",
    ]


@pytest.mark.parametrize("year", YEARS)
def test_no_keynote_time_or_start_time_copy_is_in_the_year_data(year: int) -> None:
    """Keynote moments are only derived; no hand text names a clock time (#381)."""
    data = load_year(year)
    moments = data.content.event_reminders
    assert {m.category for m in moments} <= {"lightning", "open_space"}
    people = {p.name for k in data.content.keynotes for p in k.speakers}
    for moment in moments:
        words = f"{moment.title} {moment.body}"
        assert not re.search(r"\d{1,2}(:\d\d)?\s*(AM|PM|am|pm)|\d{1,2}:\d\d", words)
        assert not any(name in words for name in people)
        assert "keynote" not in words.lower()


@pytest.mark.parametrize("year", YEARS)
def test_the_hand_moments_are_in_the_apps_voice(year: int) -> None:
    """ux.md §4.9: US English, no exclamation marks."""
    for moment in load_year(year).content.event_reminders:
        words = f"{moment.title} {moment.body}"
        assert "!" not in words
        assert not re.search(r"organis|specialis|programme", words)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "id = 8001",
            "id = 8000",
            "2026/content.toml: event_reminders[1].id: duplicate id 8000",
        ),
        (
            "id = 8000",
            "id = 8050",
            "2026/content.toml: event_reminders[0].id: 8050 is not in 8000-8049",
        ),
        (
            "id = 8000",
            "id = 7999",
            "2026/content.toml: event_reminders[0].id: 7999 is not in 8000-8049",
        ),
        (
            "id = 8000",
            "id = 8999",
            "2026/content.toml: event_reminders[0].id: 8999 is not in 8000-8049",
        ),
        (
            "at = 2026-05-14T17:00:00-07:00",
            "at = 2026-05-14T17:00:00",
            (
                "2026/content.toml: event_reminders[0].at: expected a time with a UTC "
                "offset"
            ),
        ),
        (
            "at = 2026-05-14T17:00:00-07:00",
            "at = 2027-05-14T17:00:00-07:00",
            (
                "2026/content.toml: event_reminders[0].at: 2027-05-14 17:00:00-07:00 "
                "is not in 2026"
            ),
        ),
        (
            # New Year in UTC is still 2025 in Long Beach.
            "at = 2026-05-14T17:00:00-07:00",
            "at = 2026-01-01T05:00:00+00:00",
            (
                "2026/content.toml: event_reminders[0].at: 2026-01-01 05:00:00+00:00 "
                "is not in 2026"
            ),
        ),
        (
            "at = 2026-05-14T17:00:00-07:00",
            "at = 2026-05-14",
            (
                "2026/content.toml: event_reminders[0].at: expected a date and time, "
                "got datetime.date(2026, 5, 14)"
            ),
        ),
        (
            'category = "open_space"',
            'category = "party"',
            (
                "2026/content.toml: event_reminders[0].category: 'party' is not one of "
                "('lightning', 'open_space'); keynote moments come from the keynotes"
            ),
        ),
        (
            'category = "open_space"',
            'category = "keynote"',
            (
                "2026/content.toml: event_reminders[0].category: 'keynote' is not one "
                "of ('lightning', 'open_space'); keynote moments come from the keynotes"
            ),
        ),
        (
            'title = "Open space sign-ups for Friday"',
            'title = " "',
            "2026/content.toml: event_reminders[0].title: is empty",
        ),
        (
            'route = "/more/open-spaces"',
            'route = "more/open-spaces"',
            "2026/content.toml: event_reminders[0].route: expected a path from '/'",
        ),
        (
            'source = "https://us.pycon.org/2026/events/open-spaces/"',
            'source = "http://us.pycon.org/2026/events/open-spaces/"',
            (
                "2026/content.toml: event_reminders[0].source: expected an https:// "
                "URL with a host"
            ),
        ),
        (
            'source = "https://us.pycon.org/2026/events/open-spaces/"\n',
            "",
            (
                "2026/content.toml: event_reminders[0].source: expected an https:// "
                "URL with a host"
            ),
        ),
        (
            'open-spaces/"\nchecked = 2026-10-20\n',
            'open-spaces/"\n',
            "2026/content.toml: event_reminders[0].checked: missing key",
        ),
        (
            "id = 8000",
            "id = 8000\nchannel = 1",
            "2026/content.toml: event_reminders[0].channel: unknown key",
        ),
    ],
)
def test_a_broken_moment_names_its_entry_and_the_problem(
    data_dir: Path, old: str, new: str, message: str
) -> None:
    """The loader refuses a broken moment, naming the file, the entry and the problem."""
    edit(data_dir / "2026" / "content.toml", old, new)
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value) == message


def test_a_year_may_have_no_moments() -> None:
    """Moments are optional year data."""
    assert config.Content().event_reminders == ()


# ----------------------------------------------------------- the moments of the keynotes


@pytest.mark.parametrize("year", YEARS)
def test_every_keynote_and_panel_has_one_moment_15_minutes_before_it(
    year: int,
) -> None:
    """One moment per session of the Keynotes page, at the feed's start minus 15 min."""
    data = load_year(year)
    feed = processed(year)
    ids = [k.session_id for k in data.content.keynotes]
    sessions = keynote_sessions(feed, keynotes.TRACK, ids)
    assert {s.id for s in sessions} >= set(ids)
    moments = derived(year)
    assert len(moments) == len(sessions) == 6
    for moment, session in zip(moments, sessions, strict=True):
        assert moment.at == session.start - timedelta(minutes=15)
        assert moment.category == "keynote"
        assert moment.route == drill_href("/schedule", "session", session.id)


def test_2026_keynote_moments_read_as_the_schedule_shows_them() -> None:
    """The title says what and when, the body who and where (D-274)."""
    moments = derived(2026)
    assert [(m.id, m.title, m.body) for m in moments] == [
        (8050, "Keynote at 9:45 AM", "Lin Qiao · Pacific Ballroom - Arena"),
        (
            8051,
            "Panel at 9:00 AM",
            "Diversity & Inclusion Panel · Pacific Ballroom - Arena",
        ),
        (
            8052,
            "Keynote at 9:25 AM",
            "Pablo Galindo Salgado · Pacific Ballroom - Arena",
        ),
        (8053, "Keynote at 9:00 AM", "amanda casari · Pacific Ballroom - Arena"),
        (
            8054,
            "Keynote at 3:15 PM",
            "Rachell Calhoun & Tim Schilling · Pacific Ballroom - Arena",
        ),
        (8055, "Panel at 4:00 PM", "Steering Council Panel · Pacific Ballroom - Arena"),
    ]
    assert moments[0].at == datetime.fromisoformat("2026-05-15T09:30:00-07:00")
    assert moments[0].route == "/schedule/session/153"
    assert parent_of(moments[0].route) == "/schedule"
    assert all(m.source == "" and m.checked is None for m in moments)


def test_2025_keynote_moments_are_in_eastern_time() -> None:
    """2025's keynotes are plenaries in the feed, found through the year data."""
    moments = derived(2025, use_24h=True)
    assert [(m.route, m.at.isoformat(), m.title) for m in moments] == [
        ("/schedule/session/49", "2025-05-16T09:30:00-04:00", "Keynote at 09:45"),
        ("/schedule/session/100", "2025-05-17T08:45:00-04:00", "Panel at 09:00"),
        ("/schedule/session/101", "2025-05-17T09:10:00-04:00", "Keynote at 09:25"),
        ("/schedule/session/151", "2025-05-18T08:45:00-04:00", "Keynote at 09:00"),
        ("/schedule/session/168", "2025-05-18T15:00:00-04:00", "Keynote at 15:15"),
        ("/schedule/session/169", "2025-05-18T15:45:00-04:00", "Panel at 16:00"),
    ]


def test_moving_a_keynote_in_the_feed_moves_its_moment() -> None:
    """A keynote the schedule moves takes its moment along, title and order included."""
    feed = process(
        changed(
            2026,
            retime(153, "2026-05-16T11:00:00-07:00", "2026-05-16T11:45:00-07:00"),
        ),
        settings(2026),
    )
    data = load_year(2026)
    moments = keynote_moments(
        feed, data.content.keynotes, data.conference.zone, use_24h=False
    )
    lin = next(m for m in moments if m.route == "/schedule/session/153")
    assert lin.at == datetime.fromisoformat("2026-05-16T10:45:00-07:00")
    assert lin.title == "Keynote at 11:00 AM"
    # The ids follow the order the sessions now happen in: Saturday's panel first.
    assert [(m.id, m.route.rsplit("/", 1)[1]) for m in moments][:3] == [
        (8050, "164"),
        (8051, "165"),
        (8052, "153"),
    ]


def test_a_keynote_without_an_entry_still_has_its_moment() -> None:
    """The keynotes' track is enough: a keynote announced after the build is reminded."""
    data = load_year(2026)
    moments = keynote_moments(processed(2026), (), data.conference.zone, use_24h=False)
    assert [m.route.rsplit("/", 1)[1] for m in moments] == ["153", "165", "176", "182"]
    assert {m.title.split(" at ")[0] for m in moments} == {"Keynote"}


def test_the_id_ranges_leave_room_for_each_other_and_the_test_reminder() -> None:
    """Hand ids 8000-8049, derived 8050-8099, and 8999 is DEV-06's (D-59, D-274)."""
    assert (HAND_IDS.start, HAND_IDS.stop) == (8000, 8050)
    assert (DERIVED_IDS.start, DERIVED_IDS.stop) == (8050, 8100)
    assert 8999 not in HAND_IDS
    assert 8999 not in DERIVED_IDS
    assert KEYNOTE_LEAD.total_seconds() == 15 * 60


def test_the_moments_follow_the_keynotes_pages_track() -> None:
    """The moments' track is the Keynotes page's and the hub's Keynotes row's."""
    assert KEYNOTE_TRACK == keynotes.TRACK == HUB_PAGES["keynotes"]
