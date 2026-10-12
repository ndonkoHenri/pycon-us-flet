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
from tools.feed_invariants import outline

pytestmark = [
    pytest.mark.usefixtures("machine_tz"),
    pytest.mark.parametrize("year", YEARS),
]


def test_no_session_is_lost(year: int) -> None:
    assert feed_invariants.no_session_is_lost(recorded_feed(year)) == []


def test_ids_are_unique_stable_strings_in_ionics_forms(year: int) -> None:
    feed = recorded_feed(year)
    assert feed_invariants.ids_are_unique_stable_strings_in_ionics_forms(feed) == []


def test_every_session_is_on_one_conference_day(year: int) -> None:
    feed = recorded_feed(year)
    assert feed_invariants.every_session_is_on_one_conference_day(feed) == []


def test_times_are_aware_in_the_years_zone_and_ordered(year: int) -> None:
    feed = recorded_feed(year)
    assert feed_invariants.times_are_aware_in_the_years_zone_and_ordered(feed) == []


def test_every_group_has_a_start_and_ordered_rows(year: int) -> None:
    feed = recorded_feed(year)
    assert feed_invariants.every_group_has_a_start_and_ordered_rows(feed) == []


def test_no_dropped_category_survives(year: int) -> None:
    assert feed_invariants.no_dropped_category_survives(recorded_feed(year)) == []


def test_one_lunch_row_per_day_with_lunch(year: int) -> None:
    assert feed_invariants.one_lunch_row_per_day_with_lunch(recorded_feed(year)) == []


def test_only_overridden_sessions_show_another_start(year: int) -> None:
    feed = recorded_feed(year)
    assert feed_invariants.only_overridden_sessions_show_another_start(feed) == []


def test_speakers_and_sessions_link_both_ways(year: int) -> None:
    feed = recorded_feed(year)
    assert feed_invariants.speakers_and_sessions_link_both_ways(feed) == []


def test_rooms_and_sessions_agree(year: int) -> None:
    assert feed_invariants.rooms_and_sessions_agree(recorded_feed(year)) == []


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
    """D-77: a deliberate change updates the snapshot and explains its diff."""
    zone = load_year(year).conference.zone
    snapshot(f"outline-{year}", outline(processed(year), zone))
