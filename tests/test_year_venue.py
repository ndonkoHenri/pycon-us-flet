"""Tests for the venue's address and directions in the year data (MAP-11, D-313).

``conference.toml``'s optional ``address`` and ``[directions]``, which Venue & hours
shows, copies and opens a maps app at; their rules are ``year_info.check_directions()``.
"""

import pytest

from pycon_us.config import load_year
from pycon_us.year_info import Directions, check_directions
from pycon_us.year_schema import YearDataError, build

FILE = "2026/conference.toml"


def test_2026_has_the_feed_s_address_and_the_venue_s_point() -> None:
    """2026's address is the feed's; the point is the Pine Ave entrance."""
    info = load_year(2026).conference
    assert info.address == "300 E Ocean Blvd, Long Beach, CA 90802"
    assert info.directions == Directions(
        "Long Beach Convention Center (Pine Ave Entrance)", 33.764444, -118.191722
    )


def test_a_year_without_them_loads_with_none() -> None:
    """2025 has neither: its page has no address card, and no Directions."""
    info = load_year(2025).conference
    assert info.address == ""
    assert info.directions is None


@pytest.mark.parametrize(
    ("directions", "message"),
    [
        (Directions(" ", 1.0, 1.0), "directions.label: is empty"),
        (
            Directions("Venue", 90.5, 1.0),
            "directions.latitude: 90.5 is not between -90 and 90",
        ),
        (
            Directions("Venue", 1.0, -180.5),
            "directions.longitude: -180.5 is not between -180 and 180",
        ),
    ],
    ids=["blank-label", "latitude", "longitude"],
)
def test_a_broken_rule_names_the_file_and_the_key(
    directions: Directions, message: str
) -> None:
    """A blank label, or a point off the globe, fails with the key that is wrong."""
    with pytest.raises(YearDataError, match=f"^{FILE}: {message}$"):
        check_directions(directions, FILE)


def test_a_coordinate_without_a_decimal_point_is_refused() -> None:
    """TOML's ``33`` is an integer, not a coordinate: the schema says what it expects."""
    raw = {"label": "Venue", "latitude": 33, "longitude": -118.0}
    with pytest.raises(YearDataError, match="a number with a decimal point"):
        build(Directions, raw, FILE, "directions")
