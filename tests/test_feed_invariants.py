"""Invariants of the processed feed, and the reviewed snapshot of it (D-77; DATA-17, SCHED-19).

Each invariant runs on every recorded feed (2025 and 2026) under both machine zones. The
invariants themselves live in ``tools/feed_invariants.py``, which ``tools/check_feed.py``
runs on the live feed every week; each returns its problems, so a test here asserts the
list is empty. The snapshot is a readable outline of *our* processed model, one line per
session, compared with ``tests/fixtures/snapshots/outline-<year>.json``. After a deliberate
change, run ``uv run pytest tests/test_feed_invariants.py --snapshot-update`` and explain
the diff in the PR. Ionic's own processing output is compared in
``test_ionic_reference.py`` (#66).
"""

from collections.abc import Callable

import pytest

from pycon_us.config import load_year
from tests.feeds import YEARS, processed, recorded_feed
from tools import feed_invariants
from tools.feed_outline import outline

pytestmark = [
    pytest.mark.usefixtures("machine_tz"),
    pytest.mark.parametrize("year", YEARS),
]


def test_no_session_is_lost(year: int) -> None:
    """Every raw slot is a session or dropped by a named rule: nothing vanishes."""
    assert feed_invariants.no_session_is_lost(recorded_feed(year)) == []


def test_ids_are_unique_stable_strings_in_ionics_forms(year: int) -> None:
    """Session ids equal their keys, in Ionic's four forms, and are stable (D-42).

    Each id is a string equal to its key, so no two sessions share one, and processing
    the same bytes again gives the same outline.
    """
    feed = recorded_feed(year)
    assert feed_invariants.ids_are_unique_stable_strings_in_ionics_forms(feed) == []


def test_every_session_is_on_one_conference_day(year: int) -> None:
    """Each timeline session is listed once, under its conference-local date."""
    feed = recorded_feed(year)
    assert feed_invariants.every_session_is_on_one_conference_day(feed) == []


def test_times_are_aware_in_the_years_zone_and_ordered(year: int) -> None:
    """Every session time is in the year's zone, and none ends before it starts."""
    feed = recorded_feed(year)
    assert feed_invariants.times_are_aware_in_the_years_zone_and_ordered(feed) == []


def test_every_group_has_a_start_and_ordered_rows(year: int) -> None:
    """Each day's groups run by distinct starts, and every row starts with its group.

    Within a group, the rows are ordered by location, then name (D-31).
    """
    feed = recorded_feed(year)
    assert feed_invariants.every_group_has_a_start_and_ordered_rows(feed) == []


def test_no_dropped_category_survives(year: int) -> None:
    """No record of a dropped category is a session of its own.

    Free or duplicate open spaces, placeholders, the Posters plenary, blanks, and the
    poster and break slots all stay out; posters fold into one Posters row a poster
    day, and a feed with breaks keeps its break rows.
    """
    assert feed_invariants.no_dropped_category_survives(recorded_feed(year)) == []


def test_one_lunch_row_per_day_with_lunch(year: int) -> None:
    """The staggered lunch slots fold into one Lunch row on each day with lunch."""
    assert feed_invariants.one_lunch_row_per_day_with_lunch(recorded_feed(year)) == []


def test_only_overridden_sessions_show_another_start(year: int) -> None:
    """Only a session with a display-time override shows a start of its own."""
    feed = recorded_feed(year)
    assert feed_invariants.only_overridden_sessions_show_another_start(feed) == []


def test_speakers_and_sessions_link_both_ways(year: int) -> None:
    """Every linked speaker exists, has a session and is named in it."""
    feed = recorded_feed(year)
    assert feed_invariants.speakers_and_sessions_link_both_ways(feed) == []


def test_rooms_and_sessions_agree(year: int) -> None:
    """Rooms are one per slug, naturally sorted, each listing who names it."""
    assert feed_invariants.rooms_and_sessions_agree(recorded_feed(year)) == []


def test_sponsor_slugs_are_unique(year: int) -> None:
    """Each sponsor's slug is its name's, and no two sponsors share one (SPON-02)."""
    assert feed_invariants.sponsor_slugs_are_unique(recorded_feed(year)) == []


def test_sponsor_levels_are_sorted_and_not_empty(year: int) -> None:
    """The sponsor levels run by their order, each once, none empty (DATA-22)."""
    feed = recorded_feed(year)
    assert feed_invariants.sponsor_levels_are_sorted_and_not_empty(feed) == []


def test_every_invariant_has_a_test_here(year: int) -> None:
    """The weekly check runs ``INVARIANTS``; each of them must also guard the fixtures."""
    tests = {
        name.removeprefix("test_")
        for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    }
    assert {check.__name__ for check in feed_invariants.INVARIANTS} <= tests


def test_processed_model_matches_the_reviewed_snapshot(
    year: int, snapshot: Callable[[str, object], None]
) -> None:
    """The processed model's outline matches the year's reviewed snapshot.

    D-77: a deliberate change updates the snapshot and explains its diff.
    """
    zone = load_year(year).conference.zone
    snapshot(f"outline-{year}", outline(processed(year), zone))
