"""Tests for `core/lead_notes.py`: a lead note's parts and Ionic's text format (LEAD-10).

The text is what the server and Ionic's records keep (`composeNote`, `parseNote`;
docs/research/ionic/staff-tools-auth.md §7a), so a note composed here reads back the
same, and an older or hand-written note still opens.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycon_us.core.lead_notes import FOLLOW_UPS, Interest, LeadNote, compose, parse


def test_a_full_note_is_three_lines_in_ionic_s_format() -> None:
    """Interest, then the follow-ups in the sheet's order, then the trimmed text."""
    note = LeadNote(Interest.WARM, ("Hiring", "Demo"), "  Wants a call.\nNext week. ")
    assert compose(note) == (
        "Interest: warm\nFollow-up: Demo, Hiring\nNotes: Wants a call.\nNext week."
    )


@pytest.mark.parametrize(
    ("note", "text"),
    [
        (LeadNote(), ""),
        (LeadNote(text="   "), ""),
        (LeadNote(Interest.HOT), "Interest: hot"),
        (LeadNote(follow_ups=("Partner",)), "Follow-up: Partner"),
        (LeadNote(text="café"), "Notes: café"),
    ],
)
def test_only_the_parts_that_are_set_are_written(note: LeadNote, text: str) -> None:
    """An unset part writes no line; nothing set writes nothing (the outbox ignores it)."""
    assert compose(note) == text


@given(
    interest=st.none() | st.sampled_from(Interest),
    follow_ups=st.sets(st.sampled_from(FOLLOW_UPS)),
    text=st.text(),
)
def test_a_composed_note_parses_back_to_itself(
    interest: Interest | None, follow_ups: set[str], text: str
) -> None:
    """Round trip: the parts come back, the follow-ups in order and the text trimmed."""
    note = LeadNote(interest, tuple(f for f in FOLLOW_UPS if f in follow_ups), text)
    composed = compose(note)
    if composed:
        assert parse(composed) == LeadNote(note.interest, note.follow_ups, text.strip())


def test_parsing_matches_any_case_and_drops_unknown_follow_ups() -> None:
    """Ionic's patterns, case-insensitively; a label it doesn't know is dropped."""
    note = parse("interest: HOT\nfollow-up: demo, Swag, send INFO\nnotes: Call back")
    assert note == LeadNote(Interest.HOT, ("Send info", "Demo"), "Call back")


def test_a_note_in_no_known_line_is_free_text() -> None:
    """A legacy note (Ionic's older free text) opens as the text, all of it."""
    assert parse("  Met at the booth.\nLikes Flet. ") == LeadNote(
        text="Met at the booth.\nLikes Flet."
    )


def test_the_notes_line_runs_to_the_end() -> None:
    """`Notes:` takes every line after it, as Ionic's pattern does."""
    assert parse("Interest: cold\nNotes: one\ntwo").text == "one\ntwo"


def test_free_text_that_mentions_a_part_stays_text() -> None:
    """Only the lines before `Notes:` are parts: the text can say "Interest: hot"."""
    note = LeadNote(text="Asked about Interest: hot\nFollow-up: Demo")
    assert parse(compose(note)) == note
