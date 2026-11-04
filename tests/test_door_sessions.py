"""Tests for Door check's sessions and the choice, `core/door_sessions.py` (#764).

Pure: the seed's catalog (`tests/fixtures/mock/seed.json`) read through
`parse_catalog()`, plus generated sessions, so the order, the day groups, the search
and the stored shape are pinned without a page (DOOR-02, D-433).
"""

import json
import random
from datetime import date
from pathlib import Path

import pytest

from pycon_us.core.check_in import (
    Catalog,
    Category,
    Product,
    door_catalog,
    parse_catalog,
)
from pycon_us.core.door_sessions import (
    DoorChoice,
    by_day,
    choose_all,
    choose_session,
    door_sessions,
    filter_sessions,
    from_stored,
    to_stored,
)

SEED = Path(__file__).parent / "fixtures" / "mock" / "seed.json"
YEAR = 2026
WEDNESDAY = date(2026, 5, 13)


def seed_catalog() -> Catalog:
    """The seed's catalog, the door's part, as `redeemable` sends it."""
    seed = json.loads(SEED.read_text())
    return door_catalog(
        parse_catalog(
            {
                "redeemable_categories": seed["categories"],
                "redeemable_products": seed["products"],
            }
        )
    )


def test_the_door_keeps_tutorials_and_summits() -> None:
    """The swag categories, T-Shirt and Swag Bag, are Swag pickup's (DOOR-01)."""
    assert [c.name for c in seed_catalog().categories] == ["Tutorials", "Summits"]


def test_tutorials_are_wednesday_s_two_sessions_in_time_order() -> None:
    """Each session has its title, its day and time, and one day group holds both."""
    sessions = door_sessions(seed_catalog(), 1, YEAR)
    assert [(s.id, s.title, s.when, s.day, s.time) for s in sessions] == [
        (10, "All about decorators", "Wed 9:00 AM", WEDNESDAY, "9:00 AM"),
        (11, "Async in depth", "Wed 1:30 PM", WEDNESDAY, "1:30 PM"),
    ]
    assert by_day(sessions) == ((WEDNESDAY, sessions),)


def test_100_generated_sessions_group_by_day_chronologically_undated_last() -> None:
    """Shuffled, the seed's and 100 more come out by start, a group per day, then None."""
    rng = random.Random(764)
    products = list(seed_catalog().products)
    for n in range(100):
        day, hour, minute = rng.randint(12, 17), rng.randint(1, 12), rng.choice((0, 30))
        half = rng.choice(("AM", "PM"))
        name = f"May {day} {hour}:{minute:02d} {half} - Session {n}"
        products.append(Product(100 + n, name, 1))
    products += [Product(300, "Feb 30 9:00 AM - Not a day", 1), Product(301, "TBA", 1)]
    rng.shuffle(products)
    catalog = Catalog((Category(1, "Tutorials"),), tuple(products))
    sessions = door_sessions(catalog, 1, YEAR)
    assert len(sessions) == 104  # every Tutorials product once, Summits' left out
    starts = [(s.day, s.time) for s in sessions if s.day is not None]
    assert [s.day for s in sessions[-2:]] == [None, None]
    groups = by_day(sessions)
    days = [day for day, _ in groups]
    assert days[-1] is None and None not in days[:-1]
    assert days[:-1] == sorted({day for day, _ in starts})
    for _, group in groups[:-1]:
        minutes = [to_minutes(s.time) for s in group]
        assert minutes == sorted(minutes)
    assert [s.title for s in groups[-1][1]] == ["Feb 30 9:00 AM - Not a day", "TBA"]


def test_a_date_only_name_keeps_its_day_and_the_undated_stay_last() -> None:
    """A name that is only a date sorts and groups by its day; "TBA" stays last, once."""
    products = (
        Product(1, "Wed May 13 1:30 PM - Async", 1),
        Product(2, "TBA", 1),
        Product(3, "Wed May 13 9:00 AM", 1),
    )
    catalog = Catalog((Category(1, "Tutorials"),), products)
    sessions = door_sessions(catalog, 1, YEAR)
    assert [(s.id, s.title, s.when, s.time) for s in sessions] == [
        (3, "Wed May 13 9:00 AM", "", "9:00 AM"),
        (1, "Async", "Wed 1:30 PM", "1:30 PM"),
        (2, "TBA", "", ""),
    ]
    assert [day for day, _ in by_day(sessions)] == [WEDNESDAY, None]


def to_minutes(time: str) -> int:
    """Return a "1:30 PM" time as minutes after midnight, to compare."""
    clock, half = time.split()
    hour, minute = (int(part) for part in clock.split(":"))
    return (hour % 12 + (12 if half == "PM" else 0)) * 60 + minute


@pytest.mark.parametrize(
    ("query", "titles"),
    [
        ("", ["All about decorators", "Async in depth"]),
        ("async", ["Async in depth"]),
        ("ASYNC  depth", ["Async in depth"]),
        ("1:30", ["Async in depth"]),
        ("wed", ["All about decorators", "Async in depth"]),
        ("zzz", []),
    ],
)
def test_the_search_keeps_sessions_holding_every_word(
    query: str, titles: list[str]
) -> None:
    """Each word, folded, anywhere in the title or the day and time (D-46)."""
    sessions = door_sessions(seed_catalog(), 1, YEAR)
    assert [s.title for s in filter_sessions(sessions, query)] == titles


def test_a_session_and_all_sessions_are_labelled_for_the_chip() -> None:
    """One session is "Title · Wed 1:30 PM"; all of them name the category and every id."""
    catalog = seed_catalog()
    sessions = door_sessions(catalog, 1, YEAR)
    assert choose_session(1, sessions[1]) == DoorChoice(
        1, (11,), "Async in depth \N{MIDDLE DOT} Wed 1:30 PM"
    )
    every = choose_all(catalog.categories[0], sessions)
    assert every == DoorChoice(
        1, (10, 11), "Tutorials \N{MIDDLE DOT} All sessions", all_sessions=True
    )


def test_an_undated_session_is_labelled_by_its_name() -> None:
    """A product with no date in its name is chosen as its whole name."""
    catalog = Catalog((Category(5, "Talks"),), (Product(7, "Keynote", 5),))
    (session,) = door_sessions(catalog, 5, YEAR)
    assert choose_session(5, session).label == "Keynote"


def test_the_choice_round_trips_through_storage() -> None:
    """`to_stored()` and `from_stored()` keep every field, "All" included."""
    for choice in (
        DoorChoice(1, (11,), "Async in depth · Wed 1:30 PM"),
        DoorChoice(1, (10, 11), "Tutorials · All sessions", all_sessions=True),
    ):
        stored = json.loads(json.dumps(to_stored(choice)))
        assert from_stored(stored) == choice


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"category_id": 1, "product_ids": [], "label": "x"},
        {"category_id": True, "product_ids": [1], "label": "x"},
        {"category_id": 1, "product_ids": ["1"], "label": "x"},
        {"category_id": 1, "product_ids": [1], "label": ""},
        {"category_id": 1, "product_ids": 1, "label": "x"},
    ],
    ids=["empty", "no products", "bool id", "string id", "no label", "not a list"],
)
def test_an_unusable_stored_value_is_no_choice(value: dict[str, object]) -> None:
    """Anything but the stored shape reads as nothing chosen, so the picker opens."""
    assert from_stored(value) is None
