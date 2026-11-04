"""Tests for `core/list_place.py`: the item at a list's top, as a key (D-331, #337)."""

from pycon_us.core.list_place import Place, place_at, rescaled

KEYS = ("a", "b", "c", "d")
HEIGHTS = {"a": 100.0, "b": 200.0, "c": 300.0, "d": 400.0}


def test_from_the_top_the_place_is_the_first_item_whose_bottom_is_below_it() -> None:
    """At 350 dp the list's top is 50 dp into "c" (a 100, b 200 above it)."""
    assert place_at(KEYS, HEIGHTS, 350.0) == Place("c", 50.0, 300.0, 350.0)
    assert place_at(KEYS, HEIGHTS, 0.0) == Place("a", 0.0, 100.0, 0.0)
    assert place_at(KEYS, HEIGHTS, 300.0) == Place("c", 0.0, 300.0, 300.0)


def test_an_item_above_without_a_height_leaves_the_place_unknown() -> None:
    """A lazy list never built the items above, so counting from the top fails."""
    assert place_at(KEYS, {"c": 300.0, "d": 400.0}, 350.0) is None


def test_past_the_last_item_there_is_no_place() -> None:
    """The bottom padding is no item."""
    assert place_at(KEYS, HEIGHTS, 1000.0) is None


def test_from_a_known_place_only_the_items_between_need_heights() -> None:
    """A lazy list reports the items the user scrolls through: enough to walk there."""
    near = Place("b", 150.0, 200.0, 250.0, layout="v1")  # its top at 100
    heights = {"b": 200.0, "c": 300.0}
    assert place_at(KEYS, heights, 420.0, near=near) == Place(
        "c", 120.0, 300.0, 420.0, "v1"
    )
    # Back up, into "a" (it reported too) and to the top.
    assert place_at(KEYS, {**heights, "a": 100.0}, 30.0, near=near) == Place(
        "a", 30.0, 100.0, 30.0, "v1"
    )
    # Past "c" into "d", whose height is unknown.
    assert place_at(KEYS, heights, 700.0, near=near) is None


def test_a_known_place_whose_item_is_gone_says_nothing() -> None:
    """A filter that hid the item leaves nothing to count from."""
    assert place_at(KEYS, HEIGHTS, 10.0, near=Place("x", 0.0, 9.0, 0.0)) is None


def test_the_distance_into_the_item_grows_with_it_and_stays_inside() -> None:
    """The same rows of a slot stay at the top when its text grows or shrinks."""
    place = Place("c", 60.0, 300.0, 360.0)
    assert rescaled(place, 390.0) == 78.0
    assert rescaled(place, 150.0) == 30.0
    assert rescaled(Place("c", 299.0, 300.0, 0.0), 100.0) == 99.0
    assert rescaled(Place("c", 10.0, 0.0, 0.0), 100.0) == 0.0
