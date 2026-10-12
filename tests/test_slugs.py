"""Tests for room slugs and the room sort order (DATA-16, ROOM-06)."""

import pytest

from pycon_us.core.slugs import room_sort_key, slugify_room


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Room 103ABC", "room-103abc"),
        ("Pacific Ballroom - Arena", "pacific-ballroom-arena"),
        ("S-3A", "s-3a"),
        ("Room 310/311", "room-310-311"),
        ("  Meet *outside* room 315 ", "meet-outside-room-315"),
        ("Café", "caf"),  # Ionic's [^a-z0-9]+, kept exactly
    ],
)
def test_slugify_room_matches_ionic(name: str, slug: str) -> None:
    assert slugify_room(name) == slug


def test_rooms_sort_naturally_ignoring_case_and_accents() -> None:
    names = [
        "Room 1000",
        "room 102A",
        "Seaside Ballroom A",
        "Room 101AB",
        "S-1",
        "garden outside 315",
        "Élysée",
        "Room 101A",
        "Seaside Ballroom",
    ]
    assert sorted(names, key=room_sort_key) == [
        "Élysée",
        "garden outside 315",
        "Room 101A",
        "Room 101AB",
        "room 102A",
        "Room 1000",
        "S-1",
        "Seaside Ballroom",
        "Seaside Ballroom A",
    ]


def test_letters_without_a_decomposition_keep_their_own_place() -> None:
    """D-125: "ø" is not "o" with an accent, so it sorts after "z"."""
    assert sorted(["Ørsted Hall", "Zebra Room", "Orchid Room"], key=room_sort_key) == [
        "Orchid Room",
        "Zebra Room",
        "Ørsted Hall",
    ]
