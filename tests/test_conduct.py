"""Tests for the CoC tool's pure rules: `core/conduct.py` (#758; MASK-01, MASK-02).

`parse_directory` reads `coc_attendees`' data as Ionic did, without letting one bad
entry hide the others; `search` folds and needs every word (D-46), caps its rows and
says when it cut them, and stays fast over 5,000 attendees; the count words and the one
threshold set serve the list and the result alike; `parse_capture` reads the
attendee an incident went to. The calls are in `tests/test_conduct_calls.py`.
"""

import time

import pytest

from pycon_us.core.conduct import (
    LIMIT,
    Attendee,
    Level,
    Matches,
    Recorded,
    count_level,
    count_words,
    display_name,
    parse_capture,
    parse_directory,
    search,
)
from tests.mock_calls import call, state_at
from tools.mock_api.crowd import crowd

ADA = Attendee("MOCK0001", "Ada Example", "ada", "Ada", 0)
JOSE = Attendee("MOCK0009", "José Müller", "pepe", "Pepito", 2)


def entry(code: object, full_name: object = "", **more: object) -> dict[str, object]:
    """Return one `coc_attendees` entry with this code and full name, and `more`."""
    return {"access_code": code, "full_name": full_name, **more}


def test_the_directory_sorts_by_folded_display_name_then_code() -> None:
    """Sorted as Ionic sorted it, by display name, with case and accents folded."""
    data = [
        entry("C", "zoë"),
        entry("B", "Émile"),
        entry("A", "", nickname="", badge_name=""),  # the code is the name
        entry("D", "", nickname="bob"),
        entry("E", "émile"),
    ]
    assert [a.code for a in parse_directory(data)] == ["A", "D", "B", "E", "C"]


@pytest.mark.parametrize(
    "bad",
    [
        "MOCK0005",
        None,
        entry(None, "No code"),
        entry("", "Empty code"),
        entry("   ", "Blank code"),
        entry(5, "Int code"),
    ],
)
def test_an_entry_without_an_access_code_is_left_out(bad: object) -> None:
    """An entry that isn't an object or has no code goes; the good one stays."""
    assert parse_directory([bad, entry("MOCK0001", "Ada Example")]) == (
        Attendee("MOCK0001", "Ada Example"),
    )


def test_a_repeated_code_keeps_the_first_entry() -> None:
    """Two entries with one code are one attendee, the first read."""
    data = [entry("MOCK0001", "Ada Example"), entry("MOCK0001", "Someone Else")]
    assert parse_directory(data) == (Attendee("MOCK0001", "Ada Example"),)


@pytest.mark.parametrize(
    ("violations", "incidents"),
    [(None, 0), ("3", 0), (2.0, 0), (True, 0), (-1, 0), (0, 0), (4, 4)],
)
def test_a_missing_or_non_integer_count_reads_as_zero(
    violations: object, incidents: int
) -> None:
    """`violations` counts only as a non-negative int; anything else is 0."""
    data = [entry("MOCK0001", "Ada", violations=violations)]
    assert parse_directory(data)[0].incidents == incidents


def test_names_that_are_not_strings_read_as_empty() -> None:
    """A null or numeric name is `""`; the display name falls back past it."""
    (attendee,) = parse_directory([entry("X1", None, nickname=7, badge_name=" Bo ")])
    assert (attendee.full_name, attendee.nickname, attendee.badge_name) == (
        "",
        "",
        "Bo",
    )
    assert display_name(attendee) == "Bo"


@pytest.mark.parametrize("data", [None, {}, {"data": []}, "[]"])
def test_data_that_is_not_a_list_is_refused(data: object) -> None:
    """Not a list: a `TypeError`, which the fetch makes an `ApiError`."""
    with pytest.raises(TypeError):
        parse_directory(data)


def test_display_name_falls_back_from_full_name_to_the_code() -> None:
    """Full name, else nickname, else badge name, else the access code."""
    assert display_name(Attendee("C", "Full", "nick", "Badge")) == "Full"
    assert display_name(Attendee("C", "", "nick", "Badge")) == "nick"
    assert display_name(Attendee("C", "", "", "Badge")) == "Badge"
    assert display_name(Attendee("C")) == "C"


def test_the_mock_s_directory_parses_sorted() -> None:
    """The mock's four seeded attendees, sorted by name, with their counts."""
    status, reply = call(state_at(), "GET", "mask_violations/attendees/", "coc")
    assert status == 200
    assert isinstance(reply, dict)
    directory = parse_directory(reply["data"])
    assert [(display_name(a), a.incidents) for a in directory] == [
        ("Ada Example", 0),
        ("Grace Sample", 1),
        ("Linus Placeholder", 3),
        ("Margaret Test", 0),
    ]


@pytest.mark.parametrize(
    ("query", "found"),
    [
        ("ada", [ADA]),
        ("ADA EXAMPLE", [ADA]),
        ("example ada", [ADA]),  # any order
        ("jose", [JOSE]),  # accents folded
        ("MÜLLER", [JOSE]),
        ("muller", [JOSE]),
        ("pepe", [JOSE]),  # the nickname
        ("pepito", [JOSE]),  # the badge name
        ("ada pepe", []),  # every word, in one attendee
        ("xyz", []),
        ("", []),  # nothing typed finds nothing
        ("   ", []),
    ],
)
def test_search_folds_and_needs_every_word(query: str, found: list[Attendee]) -> None:
    """Every folded word must appear in the full name, nickname or badge name."""
    assert search((ADA, JOSE), query) == Matches(tuple(found), False)


def test_search_keeps_the_directory_s_order_and_caps_its_rows() -> None:
    """At most `LIMIT` rows, in order, with `more` set only when rows were cut."""
    attendees = tuple(Attendee(f"C{n:02}", f"Sam {n:02}") for n in range(LIMIT + 1))
    capped = search(attendees, "sam")
    assert capped.rows == attendees[:LIMIT]
    assert capped.more
    exact = search(attendees[:LIMIT], "sam")
    assert exact == Matches(attendees[:LIMIT], False)
    assert search(attendees, "sam", limit=3) == Matches(attendees[:3], True)


def test_search_over_5000_attendees_keeps_typing_smooth() -> None:
    """Each keystroke's search over 5,004 attendees takes well under a frame budget."""
    state = state_at()
    seeded = [
        {"access_code": a.access_code, "full_name": a.full_name}
        for a in state.attendees.values()
    ]
    directory = parse_directory(seeded + crowd(5000, first_id=5))
    assert len(directory) == 5004
    queries = ["t", "to", "tom", "toma", "tomas", "tomas m", "tomas mu", "zz", "e"]
    start = time.perf_counter()
    for query in queries:
        search(directory, query)
    per_search = (time.perf_counter() - start) / len(queries)
    assert per_search < 0.05  # 50 ms: typically about 1 ms
    assert search(directory, "tomas muller").rows  # the generated names are found


@pytest.mark.parametrize(
    ("incidents", "words", "level"),
    [
        (0, "No incidents on record", Level.NONE),
        (1, "1 incident on record", Level.NOTICE),
        (2, "2 incidents on record", Level.NOTICE),
        (3, "3 incidents on record", Level.HIGH),
        (12, "12 incidents on record", Level.HIGH),
    ],
)
def test_count_words_and_level(incidents: int, words: str, level: Level) -> None:
    """One wording and one threshold set (0, 1-2, 3+) for the list and the result."""
    assert count_words(incidents) == words
    assert count_level(incidents) is level


def test_a_capture_reply_reads_into_the_attendee_recorded() -> None:
    """Names, email and the new count, as `coc_capture` returns them."""
    data = {
        "nickname": "gsample",
        "full_name": "Grace Sample",
        "badge_name": "Grace S.",
        "email": "grace@example.com",
        "violations": 2,
    }
    assert parse_capture(data) == Recorded(
        "Grace Sample", "Grace S.", "grace@example.com", 2
    )


def test_a_capture_reply_without_names_email_or_count_still_reads() -> None:
    """The incident is recorded all the same: the name falls back, the rest is None."""
    assert parse_capture({"nickname": "gs"}) == Recorded("gs", "", None, None)
    assert parse_capture({"violations": "2", "email": ""}) == Recorded(
        "", "", None, None
    )


@pytest.mark.parametrize("data", [None, [], "recorded"])
def test_a_capture_reply_that_is_not_an_object_is_refused(data: object) -> None:
    """Not an object: a `TypeError`, which `record()` makes an `ApiError`."""
    with pytest.raises(TypeError):
        parse_capture(data)
