"""Tests for ``core/expo.py``: the expo's booths matched to the feed's sponsors.

EXPO-02, D-254 (#401): a booth lists every sponsor with its number, a labelled booth
has none, and 2026's gaps between ``map.toml`` and the feed are pinned, so a new one
fails by name. The loader's booth rules are in ``test_year_map.py``.
"""

from typing import Any

import pytest

from pycon_us.config import load_year
from pycon_us.core.expo import Expo, expo_booths
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData
from tests.feeds import changed, processed, settings

BOOTHS = load_year(2026).map.booths
"""2026's booths, from ``map.toml``."""


def snapshot_2026() -> ConferenceData:
    """2026's bundled snapshot, processed."""
    year = load_year(2026)
    return process(year.read_snapshot().raw, year.feed_settings)


def with_booth(name: str, booth: object) -> ConferenceData:
    """2026's recorded feed with the sponsor named ``name`` given ``booth_number``."""

    def change(doc: dict[str, Any]) -> None:
        for sponsors in doc["conference"]["sponsors"].values():
            for sponsor in sponsors:
                if sponsor["name"] == name:
                    sponsor["booth_number"] = booth

    return process(changed(2026, change), settings(2026))


def gaps(expo: Expo) -> tuple[set[str], set[str]]:
    """The booth numbers whose sponsors have no booth, and the booths with no sponsor."""
    return (
        {sponsor.booth or "" for sponsor in expo.unplaced},
        {item.booth.number for item in expo.booths if not item.sponsors},
    )


@pytest.mark.parametrize("source", ["snapshot", "recorded"])
def test_2026s_gaps_are_exactly_the_known_ones(source: str) -> None:
    """Booths 139 and 336 have sponsors but no rectangle; 407 and 606 have no sponsor.

    Ionic matched silently; a gap that is not one of these fails here by number.
    """
    data = snapshot_2026() if source == "snapshot" else processed(2026)
    assert gaps(expo_booths(data, BOOTHS)) == ({"139", "336"}, {"407", "606"})


def test_a_new_gap_is_named() -> None:
    """A sponsor moved to a booth the plan lacks shows up among the unplaced, by name."""
    expo = expo_booths(with_booth("Bloomberg", "999"), BOOTHS)
    assert [(s.booth, s.name) for s in expo.unplaced] == [
        ("139", "Phemeral"),
        ("336", "Astral"),
        ("999", "Bloomberg"),
    ]
    assert "613" in gaps(expo)[1]


def test_shared_booths_keep_every_exhibitor_by_folded_name() -> None:
    """726 lists its four community groups, 727 three, 728 and 734 two (D-254)."""
    expo = expo_booths(processed(2026), BOOTHS)
    shared = {
        item.booth.number: [s.name for s in item.sponsors]
        for item in expo.booths
        if len(item.sponsors) > 1
    }
    assert shared == {
        "726": [
            "Inland Empire Python Users Group",
            "PyBeach",
            "San Diego Python",
            "SoCal Python",
        ],
        "727": ["PyCon Africa", "PyCon Senegambia", "Python Mozambique Community"],
        "728": ["Data Con LA", "SCaLE"],
        "734": ["Django Software Foundation", "Djangonaut Space"],
    }


def test_every_booth_comes_once_by_number_in_natural_order() -> None:
    """The expo has map.toml's 61 booths, each once, sorted as numbers would sort."""
    numbers = [item.booth.number for item in expo_booths(processed(2026), BOOTHS).booths]
    assert len(numbers) == len(set(numbers)) == 61
    assert numbers == sorted(numbers, key=int)


def test_numbers_compare_as_text() -> None:
    """A feed's integer booth number is text by the time it meets the booth's."""
    expo = expo_booths(with_booth("Bloomberg", 613), BOOTHS)
    booth = next(item for item in expo.booths if item.booth.number == "613")
    assert [s.name for s in booth.sponsors] == ["Bloomberg"]


@pytest.mark.parametrize("source", ["snapshot", "recorded"])
def test_a_labelled_booth_has_no_exhibitor(source: str) -> None:
    """A label names only a booth the feed gives no one: the feed wins (D-254)."""
    data = snapshot_2026() if source == "snapshot" else processed(2026)
    labelled = {
        item.booth.number: len(item.sponsors)
        for item in expo_booths(data, BOOTHS).booths
        if item.booth.label
    }
    assert labelled == {"407": 0, "606": 0}


def test_a_year_without_booths_has_an_empty_expo() -> None:
    """2025 has no map.toml: no booths, and no unplaced sponsors either."""
    year = load_year(2025)
    assert year.map.booths == ()
    assert expo_booths(processed(2025), year.map.booths) == Expo()


def test_the_expo_is_built_once_per_feed() -> None:
    """The same feed and booths give the same object; another feed a new one (D-153)."""
    data = processed(2026)
    expo = expo_booths(data, BOOTHS)
    assert expo_booths(data, BOOTHS) is expo
    assert expo_booths(processed(2026), BOOTHS) is not expo
