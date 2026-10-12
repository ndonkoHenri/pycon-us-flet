"""Tests for title cleaning (DATA-08..10), on names taken from the 2025 and 2026 feeds."""

import pytest

from pycon_us.core.names import Title, clean_title, plain_text, trailing_room


def test_names_become_plain_text() -> None:
    assert (
        plain_text("[Posters (Hall AB)](/2026/schedule/posters/list/)")
        == "Posters (Hall AB)"
    )
    assert plain_text("[Yes, You Can] Test SQL") == "[Yes, You Can] Test SQL"
    assert plain_text("Dask &amp; Xarray ") == "Dask & Xarray"
    assert plain_text("DuckDB <3 Python, a < b > c") == "DuckDB <3 Python, a < b > c"
    assert plain_text("&lt;s&gt;kept&lt;/s&gt;") == "<s>kept</s>"  # text, not markup


def test_tags_in_a_name_are_stripped_keeping_their_text() -> None:
    """D-114: 2025's cancelled workshop."""
    title = clean_title("CANCELLED: <s>Introduction to Sprints Workshop</s>", "event")
    assert title.name == "CANCELLED: Introduction to Sprints Workshop"


def test_trailing_room_is_split_off() -> None:
    assert trailing_room("Lunch (Hall AB) ") == ("Lunch", "Hall AB")
    assert trailing_room("Talk (with friends) and more") == (
        "Talk (with friends) and more",
        "",
    )


@pytest.mark.parametrize(
    ("name", "kind", "expected"),
    [
        (
            "[Keynote — Lin Qiao (Pacific Ballroom - Arena)](/2026/about/keynote-speakers/)",
            "keynote",
            Title("Lin Qiao", "Pacific Ballroom - Arena", False, False),
        ),
        (
            "[Keynote — Pablo Galindo Salgado, En Español (Pacific Ballroom - Arena)](/x/)",
            "keynote",
            Title("Pablo Galindo Salgado", "Pacific Ballroom - Arena", False, True),
        ),
        (
            "[Lightning Talks (Pacific Ballroom - Arena)](/2026/events/lightning-talks/)",
            "lightning-talks",
            Title("Lightning Talks", "Pacific Ballroom - Arena", False, False),
        ),
        (
            "Lightning-talks: Friday",  # the kind as a prefix, "-" or " "
            "lightning-talks",
            Title("Friday", "", False, False),
        ),
        (
            "Keynote - Lynn Root",  # 2025: a plenary, so "Keynote" is not its kind
            "plenary",
            Title("Keynote - Lynn Root", "", False, False),
        ),
        (
            "[PyLadies Auction, pre-registration required](/2026/events/pyladies-auction/)",
            "event",
            Title("PyLadies Auction", "", True, False),
        ),
        (
            "Python Language Summit, pre-registration required!",
            "summit",
            Title("Python Language Summit", "", True, False),
        ),
        ("Maintainers Summit", "summit", Title("Maintainers Summit", "", True, False)),
        ("Typing Summit", "summit", Title("Typing Summit", "", False, False)),
        (
            "Writing a Python Library (with tests)",  # only plenary-like names lose it
            "tutorial",
            Title("Writing a Python Library (with tests)", "", True, False),
        ),
        ("Mi charla", "charla", Title("Mi charla", "", False, True)),
        ("Datos en espanol", "talk", Title("Datos", "", False, True)),
        ("Espanol para todos", "talk", Title("Espanol para todos", "", False, False)),
    ],
)
def test_clean_title_takes_a_name_apart(name: str, kind: str, expected: Title) -> None:
    assert clean_title(name, kind) == expected
