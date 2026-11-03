"""Tests for badge payloads and the scan cooldown, ``core/badges.py`` (LEAD-03, LEAD-01; D-65).

``tests/test_badges.py`` is the UI's track badges; these are the attendee badges the
staff tools scan. The mock API's seed shows the parsed parts are what it checks.
"""

from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycon_us.core.badges import (
    COOLDOWN_SECONDS,
    ENTRY_TITLE_MAX,
    Badge,
    Cooldown,
    entry_title,
    parse_badge,
)
from tools.mock_api.badges import payload
from tools.mock_api.state import MockState


@pytest.mark.parametrize(
    ("raw", "badge"),
    [
        ("MOCK0001:v4l1d01", Badge("MOCK0001", "v4l1d01", "v4l1d01")),
        ("CODE:first:last", Badge("CODE", "first", "last")),
        ("CODE:a:b:c:d", Badge("CODE", "a", "d")),
        ("  CODE:val\n", Badge("CODE", "val", "val")),
        ("CODE:", Badge("CODE", "", "")),
        ("CODE::last", Badge("CODE", "", "last")),
        ("CODE:first:", Badge("CODE", "first", "")),
    ],
)
def test_parse_badge_splits_as_ionic(raw: str, badge: Badge) -> None:
    """Segment 0 is the code, segment 1 the door's validator, the last the lead's."""
    assert parse_badge(raw) == badge


@pytest.mark.parametrize("raw", ["", "   ", "CODE", ":validator", " :x", "https//x"])
def test_parse_badge_refuses_what_is_not_a_badge(raw: str) -> None:
    """No colon or an empty access code is not a badge ("Not a badge code")."""
    assert parse_badge(raw) is None


def test_the_parts_are_what_the_mock_api_checks() -> None:
    """Every seeded payload parses to the attendee's code and validator, both tools'."""
    state = MockState.from_seed()
    for attendee in state.attendees.values():
        badge = parse_badge(payload(attendee))
        assert badge is not None
        assert state.attendee(badge.code, badge.door_validator) is attendee
        assert state.attendee(badge.code, badge.lead_validator) is attendee


def test_a_held_code_is_accepted_once_per_cooldown() -> None:
    """At 0 s yes, 3.9 s no, 4.0 s yes again, and the clock restarts from that."""
    cooldown = Cooldown()
    assert COOLDOWN_SECONDS == cooldown.seconds == 4.0
    assert [cooldown.accept("A", t) for t in (0.0, 0.3, 3.9, 4.0, 7.9, 8.0)] == [
        True,
        False,
        False,
        True,
        False,
        True,
    ]


def test_a_different_code_is_never_held_back() -> None:
    """Interleaved codes each get their own cooldown."""
    cooldown = Cooldown()
    scans = [("A", 0.0), ("B", 0.1), ("A", 0.2), ("B", 2.0), ("C", 2.1), ("A", 4.0)]
    assert [cooldown.accept(code, t) for code, t in scans] == [
        True,
        True,
        False,
        False,
        True,
        True,
    ]


@given(
    st.lists(
        st.tuples(st.sampled_from("ABC"), st.floats(0, 3, allow_nan=False)),
        max_size=60,
    )
)
def test_accept_never_says_yes_twice_within_the_cooldown(
    scans: list[tuple[str, float]],
) -> None:
    """For any scans in time order, one code's accepted times are 4 s apart or more."""
    cooldown = Cooldown()
    now = 0.0
    accepted: dict[str, list[float]] = {}
    for code, step in scans:
        now += step
        if cooldown.accept(code, now):
            accepted.setdefault(code, []).append(now)
    for times in accepted.values():
        assert all(b - a >= COOLDOWN_SECONDS for a, b in pairwise(times))
    # And each code's first scan is always accepted.
    assert set(accepted) == {code for code, _ in scans}


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("MOCK0001", "MOCK0001"),
        ("a" * ENTRY_TITLE_MAX, "a" * ENTRY_TITLE_MAX),
        ("a" * (ENTRY_TITLE_MAX + 1), "a" * ENTRY_TITLE_MAX + "\u2026"),
        ("BEGIN:VCARD\r\nFN:Ada\n\n  Lovelace", "BEGIN:VCARD FN:Ada Lovelace"),
        ("word " * 40, ("word " * 12).rstrip() + "\u2026"),
    ],
)
def test_entry_title_is_one_clipped_line_of_the_words(text: str, title: str) -> None:
    """A refused entry's title keeps its words on one line and ends in an ellipsis past the cap (#965)."""
    assert entry_title(text) == title


@given(st.text())
def test_entry_title_is_never_longer_than_the_cap_and_its_ellipsis(text: str) -> None:
    """Whatever was pasted, the title is at most the cap plus its ellipsis (#965)."""
    title = entry_title(text)
    assert len(title) <= ENTRY_TITLE_MAX + 1
    assert bool(title) == bool(text.strip())  # an entry to edit always has a title
