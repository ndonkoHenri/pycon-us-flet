"""Tests for the expo's booths in search's Places (EXPO-04, #406; D-19, D-46).

A booth is found by its number or its exhibitor's name, each exhibitor at its booth,
the sponsors' booths the plan does not draw among them; a sponsor is never found by
its booth (#397). The screen's rows and taps are in ``test_search_screen_results.py``.
"""

from functools import cache

import pytest

from pycon_us.config import load_year
from pycon_us.core.expo import BoothEntry, booth_entries, expo_booths, list_rows
from pycon_us.core.search import SearchIndex, search, search_index
from pycon_us.core.slugs import room_sort_key
from tests.feeds import processed


@cache
def index() -> SearchIndex:
    """The 2026 index over the bundled feed, its venue spots and its booths."""
    year = load_year(2026)
    return search_index(processed(2026), year.map.venue_spots(), year.map.booths)


def numbers(query: str, scope: str = "places") -> list[str]:
    """The keys of the booth entries ``query`` finds, in result order."""
    return [entry.key for entry in search(index(), query, scope).booths]


def test_a_number_lists_its_booth_under_places_and_no_sponsor() -> None:
    """The query "613" finds Bloomberg's booth; the sponsor is found by its name alone."""
    found = search(index(), "613")
    assert [entry.key for entry in found.booths] == ["613.bloomberg"]
    assert not found.sponsors
    by_name = search(index(), "bloomberg")
    assert [s.name for s in by_name.sponsors] == ["Bloomberg"]
    assert [entry.key for entry in by_name.booths] == ["613.bloomberg"]


def test_booth_and_its_number_find_the_booth() -> None:
    """A query "booth 613" finds the booth: "booth" is in each entry's text."""
    assert numbers("booth 613") == ["613.bloomberg"]


def test_an_exhibitor_s_name_finds_it_at_a_shared_booth() -> None:
    """A query "socal python" finds SoCal Python at 726, not 726's other exhibitors."""
    assert numbers("socal python") == ["726.socal-python"]
    assert len(numbers("726")) == 4  # every exhibitor of the shared booth


def test_a_booth_off_the_plan_is_found_and_marked_unplaced() -> None:
    """A query "phemeral" finds booth 139, which the plan does not draw (D-377)."""
    (entry,) = search(index(), "phemeral", "places").booths
    assert entry == BoothEntry("139", "Phemeral", "phemeral", placed=False)


def test_a_booth_without_an_exhibitor_is_found_by_its_label() -> None:
    """The Attendee lounge, booth 606, has no exhibitor: its label finds it."""
    assert numbers("attendee lounge") == ["606"]


@pytest.mark.parametrize("scope", ["sessions", "speakers", "sponsors"])
def test_only_all_and_places_find_booths(scope: str) -> None:
    """Booths are places: the other scopes leave them out."""
    assert numbers("613", scope) == []
    assert numbers("613", "all") == ["613.bloomberg"]


def test_booth_entries_are_the_list_s_rows_and_the_unplaced_by_number() -> None:
    """One entry per List row and per unplaced sponsor, in natural number order."""
    year = load_year(2026)
    expo = expo_booths(processed(2026), year.map.booths)
    entries = booth_entries(expo)
    assert len(entries) == len(list_rows(expo.booths)) + len(expo.unplaced)
    keys = [room_sort_key(entry.number) for entry in entries]
    assert keys == sorted(keys)
    assert [e.number for e in entries if not e.placed] == ["139", "336"]


def test_a_year_without_booths_indexes_none() -> None:
    """Without ``map.toml`` booths there is no expo, so search finds no booth."""
    assert search_index(processed(2026)).booths == ()
