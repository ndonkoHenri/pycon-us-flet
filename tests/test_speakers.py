"""Tests for the Speakers list: its query (``core/speakers.py``) and its screen (#98).

The query is pure and runs on both recorded feeds and on small built cases: the letter
headings (accents, letters without a Latin base), the first session and its "+1 more",
pseudo-speakers left out, and the filter's matching (SPKR-01, SPKR-02, DATA-21; D-46).

The screen runs in a real Flet session under the store providers (``tests/sessions.py``'s
``showing()``, which names the Flet internals it uses): a keystroke is the field's value
patched in and its change event dispatched, as Flutter sends them, and Flet's scheduler
re-renders what changed, so a test sees which row and section bodies ran (D-153). How
the list looks, wraps at 200 % and reads to TalkBack and VoiceOver is checked on devices
(the PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
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
from pycon_us.screens import speakers as screen
from pycon_us.state import Conference
from pycon_us.ui import rows
from pycon_us.ui.rows import more_label, speaker_phrase
from tests import sessions
from tests.feeds import YEARS, processed

YEAR = load_year(2026)
ROW = "speakers.speaker."
"""The prefix of a speaker row's semantics identifier."""


def with_speakers(names: list[str], *, sessions: dict[str, list[str]] | None = None):
    """The 2026 feed with only these speakers, whose ids are "0", "1", and so on.

    If ``sessions`` is given, only these sessions too: copies of one 2026 session,
    linked to the speakers named by id.
    """
    base = processed(2026)
    template = next(iter(base.sessions.values()))
    speakers = {str(n): Speaker(str(n), name, "", "") for n, name in enumerate(names)}
    built = {}
    for session_id, speaker_ids in (sessions or {}).items():
        built[session_id] = replace(template, id=session_id, speaker_ids=speaker_ids)
    return replace(base, speakers=speakers, sessions=built or base.sessions)


def names(entries: tuple[SpeakerEntry, ...]) -> list[str]:
    """The speakers' names, in the entries' order."""
    return [entry.speaker.name for entry in entries]


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
    and an empty name has ``NO_LETTER``.
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
    """A speaker's first session is the earliest, and ``more`` counts the others."""
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
    """In each recorded feed, ``more`` counts a speaker's sessions after the first.

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
    """The names the filter keeps from the feed's directory for ``query``."""
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
    """An entry for Ana Lima with ``more`` other sessions, and a first one or none."""
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


# ------------------------------------------------------------------ the screen


@dataclass
class Shown(sessions.Shown):
    """The harness's ``Shown`` (``tests/sessions.py``) on the Speakers screen.

    Its rows are speakers: ``rows`` holds the speaker ids whose row bodies ran.
    """

    sections: list[str] = field(default_factory=list)
    """The letters whose section bodies ran, in order."""

    @property
    def text_field(self) -> ft.TextField:
        """The screen's one filter field."""
        (text_field,) = self.find(ft.TextField)
        return text_field

    @property
    def listed(self) -> list[str]:
        """The speaker ids of the rows on screen, in the list's order."""
        (body,) = self.find(ft.ListView)  # the screen's one list
        found: list[str] = []

        def walk(control: object) -> None:
            identifier = getattr(control, "identifier", None)
            if isinstance(control, ft.Semantics) and str(identifier).startswith(ROW):
                found.append(str(identifier).removeprefix(ROW))
            # A component's rendered body is its _b (Flet internals, as above).
            for name in ("content", "_b"):
                child = getattr(control, name, None)
                for item in child if isinstance(child, list) else [child]:
                    if isinstance(item, ft.BaseControl):
                        walk(item)
            for child in getattr(control, "controls", None) or ():
                walk(child)

        walk(body)
        return found

    async def type(self, text: str) -> None:
        """Type into the filter as Flutter reports it: the value, then the event."""
        text_field = self.text_field
        self.session.apply_patch(text_field._i, {"value": text})
        await self.event(text_field, "change", None)


type Render = Callable[[Conference], Awaitable[Shown]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Return a function that shows the Speakers screen over a given ``Conference``.

    Each screen it shows closes when the test ends.
    """
    header = screen.SectionHeader

    def counted_phrase(entry: SpeakerEntry) -> str:
        sessions.current(Shown).rows.append(entry.speaker.id)
        return speaker_phrase(entry)

    def counted_header(text: str) -> ft.Control:
        sessions.current(Shown).sections.append(text)
        return header(text)

    # Each body calls these once: counting the calls counts the bodies (S2).
    monkeypatch.setattr(rows, "speaker_phrase", counted_phrase)
    monkeypatch.setattr(screen, "SectionHeader", counted_header)

    async with AsyncExitStack() as stack:

        async def show(conference: Conference) -> Shown:
            return await stack.enter_async_context(
                sessions.showing(
                    screen.Speakers,
                    screen,
                    year=YEAR,
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="",  # no Router: what ft.use_view_path() says outside one
                    kind=Shown,
                )
            )

        yield show


@pytest.fixture
async def shown(render: Render) -> Shown:
    """The Speakers screen over the recorded 2026 feed."""
    return await render(Conference(data=processed(2026), source="bundled", version=1))


ALL = directory(processed(2026))


async def test_the_list_shows_every_speaker_once_without_paging(shown: Shown) -> None:
    """The list shows every speaker once, each row and letter section rendered once."""
    assert shown.listed == [entry.speaker.id for entry in ALL]
    assert sorted(shown.rows) == sorted(entry.speaker.id for entry in ALL)
    assert shown.sections == [group.letter for group in letter_groups(ALL)]


async def test_a_keystroke_re_renders_no_row_that_stays(shown: Shown) -> None:
    """D-153: the rows found are unchanged, so their bodies are skipped (F34)."""
    shown.rows.clear()
    shown.sections.clear()
    await shown.type("cristian")
    (cristian,) = [e for e in ALL if e.speaker.name.startswith("Cristián")]
    assert shown.listed == [cristian.speaker.id]
    assert shown.rows == []
    assert shown.sections == ["C"]  # its section changed; the others went
    assert shown.text_field.value == "cristian"  # controlled: the text stays (D-157)

    shown.sections.clear()
    await shown.type("cristian ")  # the same speakers: nothing re-renders
    assert (shown.rows, shown.sections) == ([], [])


async def test_a_filter_that_finds_nothing_offers_to_clear_it(
    shown: Shown, focused: list[ft.TextField]
) -> None:
    """A filter that finds nothing says so in a live region and offers to clear it.

    Clearing lists every speaker again and gives the field the focus.
    """
    await shown.type("zzz")
    assert shown.listed == []
    state = shown.node("speakers.no_match")
    assert state.live_region
    (button,) = [b for b in shown.find(ft.FilledTonalButton) if b.parent is not None]
    assert button.content == screen.CLEAR_FILTER

    await shown.click(button)
    assert shown.text_field.value == ""
    assert len(shown.listed) == len(ALL)
    # The button went: the field takes the focus.
    assert [f._i for f in focused] == [shown.text_field._i]


async def test_the_fields_clear_button_shows_only_with_text(
    shown: Shown, focused: list[ft.TextField]
) -> None:
    """The field's clear button shows only with text, over the field and not in it.

    A tap clears the text, hides the button and gives the field the focus.
    """

    def clear_buttons() -> list[ft.IconButton]:
        return [b for b in shown.find(ft.IconButton) if b.parent is not None]

    assert clear_buttons() == []
    await shown.type("ana")
    (clear,) = clear_buttons()
    assert clear.tooltip == screen.CLEAR_FILTER  # its accessible name (D-27)
    # Over the field, not in it: the field's merged node would swallow it.
    assert not _under(clear, shown.node("speakers.filter"))

    await shown.click(clear)
    assert shown.text_field.value == ""
    assert clear_buttons() == []
    # The button went: the field takes the focus.
    assert [f._i for f in focused] == [shown.text_field._i]


async def test_the_filter_field_is_named_and_identified(shown: Shown) -> None:
    """The filter field is identified, named by its hint or, with text, by its label."""
    node = shown.node("speakers.filter")
    assert node.content is shown.text_field
    assert shown.text_field.hint_text == screen.FILTER_HINT
    # The hint names the empty field; it leaves the semantics tree once there is
    # text, and the node's label takes over, never both at once (read twice).
    assert node.label is None
    assert isinstance(node.parent, ft.MergeSemantics)  # one node with the field's
    await shown.type("mu")
    assert shown.node("speakers.filter").label == screen.FILTER_HINT
    await shown.type("")
    assert shown.node("speakers.filter").label is None


async def test_the_filter_field_never_fixes_names(shown: Shown) -> None:
    """The filter field has autocorrect and suggestions off, so names stay as typed."""
    assert shown.text_field.autocorrect is False
    assert shown.text_field.enable_suggestions is False  # Android's own switch


async def test_the_filter_field_has_no_line_even_when_focused(shown: Shown) -> None:
    """ux.md §5.7: a pill like Material's search bar, not the theme's focus ring."""
    border = cast(dict[ft.ControlState, ft.OutlineInputBorder], shown.text_field.border)
    assert border.keys() == {ft.ControlState.DEFAULT, ft.ControlState.FOCUSED}
    for state in border.values():
        assert state.side == ft.BorderSide(0, ft.Colors.TRANSPARENT)
        assert state.border_radius == 28


async def test_a_filter_says_how_many_it_found_in_a_live_region(shown: Shown) -> None:
    """A filter counts the speakers it found, in words, in a live region.

    Without a filter there is no count, and a miss leaves the announcing to the no-match
    state.
    """

    def counted() -> list[ft.Semantics]:
        return [
            s
            for s in shown.find(ft.Semantics)
            if s.identifier == "speakers.count" and s.parent is not None
        ]

    assert counted() == []  # no filter: nothing to count
    await shown.type("mu")
    (count,) = counted()
    assert count.live_region
    found = len(shown.listed)
    assert found > 1
    assert cast(ft.Text, cast(ft.Container, count.content).content).value == (
        f"{found} speakers"
    )
    await shown.type("mike müller")
    (count,) = counted()
    assert cast(ft.Text, cast(ft.Container, count.content).content).value == (
        "1 speaker"
    )
    await shown.type("zzz")  # a miss: the no-match state announces itself
    assert counted() == []


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[ft.TextField]:
    """The fields asked to take the focus; the harness has no Flutter to answer."""
    asked: list[ft.TextField] = []

    async def focus(self: ft.TextField) -> None:
        # As the real one, which invokes the method through the field's page.
        assert self.page is not None, "the field is not on the page"
        asked.append(self)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return asked


async def test_each_letter_is_a_heading_node_of_its_own(shown: Shown) -> None:
    """Each letter is a heading inside a container node of its own, one per group.

    D-33: headings let screen readers jump letter by letter; a node of its own keeps
    the heading's focus on the letter, not on its whole section.
    """
    headings = [s for s in shown.find(ft.Semantics) if s.header]
    assert len(headings) == len(letter_groups(ALL))
    for heading in headings:
        wrapper = heading.parent
        assert isinstance(wrapper, ft.Semantics) and wrapper.container


async def test_a_row_is_one_button_read_as_its_phrase(shown: Shown) -> None:
    """A speaker row is one merged button node that reads its phrase alone."""
    (mike,) = [e for e in ALL if e.speaker.name == "Mike Müller"]
    node = shown.node(f"speakers.speaker.{mike.speaker.id}")
    assert node.label == speaker_phrase(mike)
    assert node.button
    assert node.exclude_semantics  # the texts and initials are not read again
    tap = node.parent
    assert isinstance(tap, ft.Container) and tap.on_click is not None
    assert isinstance(tap.parent, ft.MergeSemantics)


async def test_a_row_shows_the_photo_over_the_initials(shown: Shown) -> None:
    """Each row's avatar shows the speaker's initials under their photo, if any."""
    by_id = {e.speaker.id: e for e in ALL}
    avatars = [a for a in shown.find(ft.CircleAvatar) if a.parent is not None]
    assert len(avatars) == len(ALL)
    with_photo = [a for a in avatars if a.foreground_image_src]
    assert with_photo  # the public feed has photos for most speakers
    for avatar in avatars:
        row = avatar
        while not (
            isinstance(row, ft.Semantics)
            and str(row.identifier).startswith("speakers.")
        ):
            row = cast(ft.Control, row.parent)
        speaker = by_id[str(row.identifier).removeprefix("speakers.speaker.")].speaker
        assert cast(ft.Text, avatar.content).value == initials(speaker.name)
        assert avatar.foreground_image_src == (speaker.photo_url or None)
        assert avatar.bgcolor == ft.Colors.PRIMARY_CONTAINER  # a tested pair (theme)
        assert avatar.color == ft.Colors.ON_PRIMARY_CONTAINER


async def test_a_row_with_more_sessions_says_so_after_the_first(shown: Shown) -> None:
    """A row with more sessions puts "+1 more" on a line of its own, below its title.

    The title stops at two lines, so it never cuts the count.
    """
    (entry,) = [e for e in ALL if e.speaker.name == "Catherine Nelson"]
    assert entry.first_session is not None and entry.more == 1
    node = shown.node(f"speakers.speaker.{entry.speaker.id}")
    texts = [
        str(t.value)
        for t in shown.find(ft.Text)
        if _under(t, node) and t.parent is not None
    ]
    title, more = texts[-2:]
    assert title == entry.first_session.name
    assert more == "+1\N{NO-BREAK SPACE}more"  # its own line, never cut by the title
    (title_text,) = [
        t for t in shown.find(ft.Text) if t.value == title and _under(t, node)
    ]
    assert title_text.max_lines == 2


async def test_a_tap_pushes_the_speakers_detail(shown: Shown) -> None:
    """A tap on a row pushes that speaker's detail, one drill level down."""
    went = shown.went  # what page.navigate was asked for
    entry = ALL[0]
    node = shown.node(f"{ROW}{entry.speaker.id}")
    await shown.click(cast(ft.Control, node.parent))
    assert len(went) == 1
    assert went[0].endswith(f"/speaker/{entry.speaker.id}")  # one drill level


def _under(control: ft.BaseControl, ancestor: ft.BaseControl) -> bool:
    """Whether ``ancestor`` is ``control`` or one of its parents."""
    node: ft.BaseControl | None = control
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent
    return False


async def test_without_data_the_skeleton_shows_until_the_first_fetch_fails(
    render: Render,
) -> None:
    """ux.md §4.1, NEW-03: no data at all is the only time anything loads."""
    loading = await render(Conference())
    labels = [node.label for node in loading.find(ft.Semantics)]
    assert "Loading speakers" in labels
    assert loading.listed == []


async def test_after_a_failed_first_fetch_it_offers_to_try_again(
    render: Render,
) -> None:
    """After a failed first fetch, a live no-data state offers Try again."""
    failed = await render(Conference(problem="offline"))
    state = failed.node("speakers.no_data")
    assert state.live_region
    buttons = [b.content for b in failed.find(ft.FilledTonalButton)]
    assert buttons == ["Try again"]


async def test_a_feed_without_speakers_says_none_are_announced(
    render: Render,
) -> None:
    """Not a filter miss: nothing was filtered, so there is nothing to clear."""
    data = replace(processed(2026), speakers={})
    empty = await render(Conference(data=data, version=1))
    state = empty.node("speakers.not_announced")
    assert state.live_region
    titles = [str(t.value) for t in empty.find(ft.Text)]
    assert screen.NOT_ANNOUNCED in titles
    assert not any(t.startswith("No speakers match") for t in titles)
    assert empty.find(ft.FilledTonalButton) == []  # no Clear filter, no button


async def test_a_new_feed_version_rebuilds_the_list_and_its_filter(
    render: Render,
) -> None:
    """The memo keys on ``Conference.version``: a refresh must reach the list."""
    full = processed(2026)
    (mike,) = [e for e in ALL if e.speaker.name == "Mike Müller"]
    speakers = {k: v for k, v in full.speakers.items() if k != mike.speaker.id}
    conference = Conference(data=replace(full, speakers=speakers), version=1)
    refreshed = await render(conference)
    assert mike.speaker.id not in refreshed.listed
    await refreshed.type("mike müller")
    assert refreshed.listed == []

    conference.data = full  # as a refresh publishes it (Conference._publish)
    conference.version += 1
    await refreshed.settle()
    assert refreshed.listed == [mike.speaker.id]  # the new index finds him
    await refreshed.type("")
    assert mike.speaker.id in refreshed.listed
    assert len(refreshed.listed) == len(ALL)
