"""Tests for the Speakers list's query (`core/speakers.py`, #98).

The query is pure and runs on both recorded feeds and on small built cases
(`tests/speakers_view.py`): the letter headings (accents, letters without a Latin
base), the first session and its "+1 more", pseudo-speakers left out, and the filter's
matching (SPKR-01, SPKR-02, DATA-21; D-46). The screen is `test_speakers_screen.py`'s
and `test_speakers_rows.py`'s. How the list looks, wraps at 200 % and reads to
TalkBack and VoiceOver is checked on devices (the PR).
"""

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest

from pycon_us.core.models import ConferenceData, Speaker
from pycon_us.core.queries import fold, speaker_order
from pycon_us.core.search import search_index
from pycon_us.core.speakers import (
    NO_LETTER,
    SpeakerEntry,
    directory,
    filter_directory,
    has_bio,
    initials,
    letter_groups,
    letter_of,
    speaker_sessions,
)
from pycon_us.core.timeline import schedule_order
from pycon_us.ui.rows import more_label, speaker_phrase
from tests.feeds import YEARS, processed
from tests.speakers_view import names, with_speakers

# ------------------------------------------------------------------ letters (D-46)


@pytest.mark.parametrize(
    ("name", "letter"),
    [
        ("Ana Lima", "A"),
        ("nikkie", "N"),  # a lower-case handle
        ("Élodie Durand", "E"),  # an accent folds away
        ("Łukasz Langa", "L"),  # a letter NFKD leaves whole (D-180)
        ("Ömer Kaya", "O"),
        ("Жанна Петрова", "Ж"),  # no Latin base: its own letter
        ("张伟", "张"),
        ("3D Bob", "3"),
        ("", NO_LETTER),
    ],
)
def test_a_speaker_is_listed_under_the_folded_first_character(
    name: str, letter: str
) -> None:
    """A speaker's letter is the first character of the name, folded.

    Case and accents fold away, Ł folds to L, a letter without a Latin base is its own,
    and an empty name has `NO_LETTER`.
    """
    assert letter_of(name) == letter


def test_letters_follow_the_lists_order_with_non_latin_letters_after_z() -> None:
    """Letter groups follow the list's order, with non-Latin letters after Z."""
    data = with_speakers(
        ["Zoë Ng", "Élodie Durand", "Жанна Петрова", "Eve Park", "张伟", "Łukasz Langa"]
    )
    groups = letter_groups(directory(data))
    assert [(g.letter, names(g.entries)) for g in groups] == [
        ("E", ["Élodie Durand", "Eve Park"]),
        ("L", ["Łukasz Langa"]),
        ("Z", ["Zoë Ng"]),
        ("Ж", ["Жанна Петрова"]),
        ("张", ["张伟"]),
    ]


@pytest.mark.parametrize("year", YEARS)
def test_every_directory_speaker_is_listed_once_by_name_under_one_heading(
    year: int,
) -> None:
    """SPKR-01, DATA-21: no paging, D-46's order, and each letter's speakers together."""
    data = processed(year)
    entries = directory(data)
    assert [e.speaker for e in entries] == sorted(
        data.speakers.values(), key=speaker_order
    )
    groups = letter_groups(entries)
    letters = [group.letter for group in groups]
    assert len(letters) == len(set(letters))  # no letter twice: groups are contiguous
    assert sum(len(group.entries) for group in groups) == len(data.speakers)
    assert all(e.letter == g.letter for g in groups for e in g.entries)


@pytest.mark.parametrize("year", YEARS)
def test_pseudo_speakers_are_not_listed(year: int) -> None:
    """D-125: "Hosted by …" stays text on its sessions and is never a row."""
    data = processed(year)
    hosted = {
        name
        for session in data.sessions.values()
        for name in session.speaker_names
        if name.startswith("Hosted by")
    }
    assert hosted  # both feeds have one, so this test is not vacuous
    assert not hosted & set(names(directory(data)))


# ------------------------------------------------------------------ first session


def test_the_first_session_is_the_earliest_and_the_rest_are_counted() -> None:
    """A speaker's first session is the earliest, and `more` counts the others."""
    data = processed(2026)
    template = next(iter(data.sessions.values()))
    day = timedelta(days=1)
    sessions = {
        "late": replace(
            template,
            id="late",
            name="Late",
            start=template.start + day,
            display_start=template.start + day,
            day=template.day + day,
            speaker_ids=("0",),
        ),
        "early": replace(template, id="early", name="Early", speaker_ids=("0", "1")),
        "later": replace(
            template,
            id="later",
            name="Later",
            start=template.start + 2 * day,
            display_start=template.start + 2 * day,
            day=template.day + 2 * day,
            speaker_ids=("0",),
        ),
    }
    built = replace(
        data,
        speakers={
            "0": Speaker("0", "Ana Lima", "", ""),
            "1": Speaker("1", "Bo", "", ""),
        },
        sessions=sessions,
    )
    ana, bo = directory(built)
    assert (ana.first_session, ana.more) == (sessions["early"], 2)
    assert (bo.first_session, bo.more) == (sessions["early"], 0)


def test_a_speaker_without_a_session_has_no_first_session() -> None:
    """A speaker without a session has no first session and nothing more."""
    (entry,) = directory(with_speakers(["Ana Lima"], sessions={"1": []}))
    assert (entry.first_session, entry.more) == (None, 0)


@pytest.mark.parametrize("year", YEARS)
def test_more_counts_every_other_session_of_the_speaker(year: int) -> None:
    """In each recorded feed, `more` counts a speaker's sessions after the first.

    The first is the earliest by day, then by schedule order.
    """
    data = processed(year)
    own: dict[str, list[Any]] = {}
    for session in data.sessions.values():
        for speaker_id in session.speaker_ids:
            own.setdefault(speaker_id, []).append(session)
    entries = directory(data)
    assert any(entry.more for entry in entries)  # some speakers have two sessions
    for entry in entries:
        sessions = sorted(
            own[entry.speaker.id], key=lambda s: (s.day, schedule_order(s))
        )
        assert entry.first_session is sessions[0]
        assert entry.more == len(sessions) - 1


def test_lukasz_langas_first_2025_session_is_the_thursday_talk() -> None:
    """Łukasz Langa's first 2025 session is the WebGL talk, with one more after it."""
    (entry,) = [e for e in directory(processed(2025)) if e.speaker.id == "27"]
    assert entry.first_session is not None
    assert entry.first_session.name.startswith("Discover 3D graphics with WebGL")
    assert entry.more == 1


# ------------------------------------------------------------------ a speaker's page


@pytest.mark.parametrize("year", YEARS)
def test_a_speaker_s_page_lists_every_session_by_day_as_the_list_orders_them(
    year: int,
) -> None:
    """SPKR-03: the page's first session is the Speakers list's first (D-189)."""
    data = processed(year)
    for entry in directory(data):
        days = speaker_sessions(data, entry.speaker.id)
        sessions = [s for day in days for s in day.sessions]
        assert sessions[0] is entry.first_session
        assert len(sessions) == entry.more + 1
        assert all(s.day == day.day for day in days for s in day.sessions)
        assert [day.day for day in days] == sorted({s.day for s in sessions})


def test_a_speaker_on_two_days_gets_a_group_per_day() -> None:
    """2026's Catherine Nelson: a Thursday tutorial, then Friday's panel."""
    days = speaker_sessions(processed(2026), "112")
    assert [[s.id for s in day.sessions] for day in days] == [["106"], ["110"]]
    assert days[0].day < days[1].day


def test_a_speaker_s_poster_is_one_of_their_sessions() -> None:
    """DATA-15: poster details link their authors too."""
    ids = [s.id for d in speaker_sessions(processed(2026), "55") for s in d.sessions]
    assert sorted(ids) == ["128", "poster-detail-52"]


def test_an_unknown_speaker_has_no_sessions() -> None:
    """An id no speaker has gets no sessions."""
    assert speaker_sessions(processed(2026), "nobody") == ()


@pytest.mark.parametrize(
    ("bio", "says"),
    [
        ("<p>Ana writes Python.</p>", True),
        ("Pythonista", True),
        ("TBD", True),  # a word: the app cannot tell it is a placeholder
        ("<p>2 books</p>", True),
        ("-", False),  # the feed's placeholder (2025: 12 speakers, 2026: 7)
        ("<p> &#45; </p>", False),
        ("", False),
    ],
)
def test_a_bio_says_something_when_its_text_has_a_letter_or_digit(
    bio: str, says: bool
) -> None:
    """A bio counts when its text has a letter or a digit, so a lone dash is none."""
    assert has_bio(Speaker("1", "Ana Lima", "", bio)) is says


def test_the_panel_s_dashes_are_no_bio() -> None:
    """2026's "Beyond the Hype" panellists other than Catherine Nelson have "-"."""
    speakers = processed(2026).speakers
    assert [has_bio(speakers[i]) for i in ("112", "183", "184")] == [True, False, False]


# ------------------------------------------------------------------ the filter


def filtered(data: ConferenceData, query: str) -> list[str]:
    """The names the filter keeps from the feed's directory for `query`."""
    return names(filter_directory(directory(data), search_index(data), query))


FILTER_CASES = ["Cristián Maureira-Fredes", "Łukasz Langa", "Mike Müller", "Ana Typing"]


@pytest.mark.parametrize(
    ("query", "found"),
    [
        ("cristian", ["Cristián Maureira-Fredes"]),  # accents ignored
        ("LUKASZ", ["Łukasz Langa"]),  # case, and ł
        ("müller mike", ["Mike Müller"]),  # every word, in any order
        ("mike zzz", []),  # all words must match
        ("lang", ["Łukasz Langa"]),  # anywhere in the name
        ("a", ["Ana Typing", "Cristián Maureira-Fredes", "Łukasz Langa"]),  # in order
        # No word to match: the lone apostrophe iOS types before O’Brien, a zero-width
        # space. Both fold to nothing, and must not empty the list.
        ("\N{RIGHT SINGLE QUOTATION MARK}", sorted(FILTER_CASES, key=fold)),
        ("\N{ZERO WIDTH SPACE}", sorted(FILTER_CASES, key=fold)),
    ],
)
def test_the_filter_finds_names_by_every_word_folded(
    query: str, found: list[str]
) -> None:
    """The filter keeps, in list order, the names holding every folded query word.

    A word matches anywhere in a name, in any order; a query with no word to match, such
    as a lone apostrophe or a zero-width space, keeps the whole list.
    """
    assert filtered(with_speakers(FILTER_CASES), query) == found


@pytest.mark.parametrize("query", ["", "  ", " ' ", "\N{RIGHT SINGLE QUOTATION MARK}"])
def test_a_filter_without_a_word_keeps_the_whole_list_as_the_same_object(
    query: str,
) -> None:
    """A query without a word returns the very same entries, unfiltered."""
    data = with_speakers(FILTER_CASES)
    entries = directory(data)
    assert filter_directory(entries, search_index(data), query) is entries


def test_the_filter_never_matches_a_session_title() -> None:
    """The list filters names only (SPKR-02): "Typing" finds the speaker, not talks."""
    assert filtered(with_speakers(FILTER_CASES), "typing") == ["Ana Typing"]


# ------------------------------------------------------------------ initials


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ana Lima", "AL"),
        ("amanda casari", "AC"),
        ("Lía Da Silva - Rojas", "LR"),
        ("Łukasz Langa", "ŁL"),
        ("Amethyst Reese 🌸", "AR"),
        ("Glyph", "G"),
        ("张伟", "张"),
        ("🌸", ""),
    ],
)
def test_initials_are_the_first_and_last_words_first_letters(
    name: str, expected: str
) -> None:
    """Initials are the first letters of the first and last words with a letter."""
    assert initials(name) == expected


# ------------------------------------------------------------------ the row's phrase


def entry_of(more: int, *, session: bool = True) -> SpeakerEntry:
    """An entry for Ana Lima with `more` other sessions, and a first one or none."""
    talk = next(iter(processed(2026).sessions.values()))
    return SpeakerEntry(
        speaker=Speaker("1", "Ana Lima", "", ""),
        letter="A",
        first_session=replace(talk, name="Typing deep dive") if session else None,
        more=more,
    )


def test_a_speaker_row_reads_as_one_phrase() -> None:
    """ux.md §3.9: "Ana Lima, speaking: Title", and the rest counted in words."""
    assert speaker_phrase(entry_of(0)) == "Ana Lima, speaking: Typing deep dive"
    assert speaker_phrase(entry_of(1)) == (
        "Ana Lima, speaking: Typing deep dive, and 1 more session"
    )
    assert speaker_phrase(entry_of(2)).endswith(", and 2 more sessions")
    assert speaker_phrase(entry_of(0, session=False)) == "Ana Lima"


def test_more_keeps_its_number_and_word_together() -> None:
    """The "+1 more" label joins its number and word with a no-break space."""
    assert more_label(1) == "+1\N{NO-BREAK SPACE}more"
