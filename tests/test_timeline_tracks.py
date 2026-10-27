"""Tests for the track pages' query and a Posters row's posters.

``track_sessions()`` and ``posters()`` in ``core/timeline.py``; the timeline itself is
tested in ``test_timeline.py``. #85: DATA-20, SESS-09, SCHED-22; D-153.
"""

from typing import Any

import pytest

from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timeline import posters, schedule_order, track_sessions
from pycon_us.prefs import Prefs
from tests.feeds import YEARS, changed, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")


@pytest.mark.parametrize("year", YEARS)
def test_a_track_page_lists_its_sessions_by_day_in_schedule_order(year: int) -> None:
    """DATA-20, SCHED-22: every session of the track once, under its own day."""
    data = processed(year)
    for track in {s.track for s in data.sessions.values()} - {"Poster"}:
        result = track_sessions(data, track)
        assert [group.day for group in result] == sorted({g.day for g in result})
        listed = [s for group in result for s in group.sessions]
        assert len(listed) == len({s.id for s in listed})
        assert {s.id for s in listed} == {
            s.id for s in data.sessions.values() if s.track == track
        }
        for group in result:
            assert group.sessions
            assert all(s.day == group.day for s in group.sessions)
            assert list(group.sessions) == sorted(group.sessions, key=schedule_order)


@pytest.mark.parametrize("year", YEARS)
def test_the_posters_track_lists_the_posters_not_the_posters_row(year: int) -> None:
    """SCHED-22: Ionic listed both the posters and the row they collapse into."""
    data = processed(year)
    listed = [s for group in track_sessions(data, "Poster") for s in group.sessions]
    assert len(listed) == len(data.posters) > 0
    assert all(s.id.startswith("poster-detail-") for s in listed)


def _without_posters(doc: dict[str, Any]) -> None:
    """Drop the posters from a feed: 2026's ``posters`` list, 2025's poster slot."""
    doc["posters"] = []
    for slot in doc["schedule"]:
        if slot.get("kind") == "poster":
            slot.pop("sessions", None)


@pytest.mark.parametrize("year", YEARS)
def test_before_posters_are_published_the_posters_track_lists_the_posters_row(
    year: int,
) -> None:
    """The page is never empty while the Schedule shows a Posters row."""
    data = process(changed(year, _without_posters), settings(year))
    assert data.posters == ()
    listed = [s for group in track_sessions(data, "Poster") for s in group.sessions]
    assert len(listed) == 1
    assert listed[0].kind == "poster" and listed[0].in_timeline


def posters_row(data: ConferenceData) -> Session:
    """The feed's Posters row: the poster slots collapsed into one row (DATA-06)."""
    (row,) = (s for s in data.sessions.values() if s.kind == "poster" and s.in_timeline)
    return row


@pytest.mark.parametrize("year", YEARS)
def test_a_posters_row_lists_its_posters_as_the_posters_track_does(year: int) -> None:
    """SESS-09: the row's detail lists every poster, in the track page's order."""
    data = processed(year)
    listed = posters(data, posters_row(data))
    assert len(listed) == len(data.posters) > 0
    track = [s for group in track_sessions(data, "Poster") for s in group.sessions]
    assert list(listed) == track


def test_only_a_posters_row_has_posters() -> None:
    """A talk, a poster and an open space each list no posters."""
    data = processed(2026)
    for session_id in ("142", "poster-detail-60", "9119"):
        assert posters(data, data.sessions[session_id]) == ()


@pytest.mark.parametrize("year", YEARS)
def test_before_posters_are_published_the_posters_row_lists_none(year: int) -> None:
    """With no posters in the feed, the Posters row lists none."""
    data = process(changed(year, _without_posters), settings(year))
    assert posters(data, posters_row(data)) == ()


def test_a_posters_row_s_posters_are_memoised_per_feed() -> None:
    """A Posters row's posters are one object per feed, another for a new feed."""
    data = processed(2026)
    row = posters_row(data)
    assert posters(data, row) is posters(data, row)
    other = processed(2026)
    assert posters(other, posters_row(other)) is not posters(data, row)


def test_a_track_page_ignores_the_schedule_filter() -> None:
    """Open spaces are hidden on the Schedule by default, yet all listed on their page."""
    data = processed(2026)
    assert "Open Space" in Prefs().excluded_tracks
    expected = {s.id for s in data.sessions.values() if s.track == "Open Space"}
    assert expected
    listed = [s for group in track_sessions(data, "Open Space") for s in group.sessions]
    assert {s.id for s in listed} == expected


def test_a_track_without_sessions_has_an_empty_page() -> None:
    """A track with no sessions, here Sprint, has an empty page."""
    assert track_sessions(processed(2026), "Sprint") == ()


def test_a_track_page_is_memoised_per_feed() -> None:
    """A track page is one object per feed, another for a new feed."""
    data = processed(2026)
    assert track_sessions(data, "Talk") is track_sessions(data, "Talk")
    assert track_sessions(data, "Talk") is not track_sessions(processed(2026), "Talk")
