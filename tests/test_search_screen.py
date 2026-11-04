"""Tests for the global search screen's scope, field and typing (#97; NEW-02, D-19).

The screen is `screens/search.py` (D-193). The matching is `core/search.py`'s,
tested in `tests/test_search.py`; here the screen around it, in
`tests/search_view.py`'s harness. The results are `test_search_screen_results.py`'s,
the first rows and Show all `test_search_screen_show_all.py`'s.

How the screen looks, wraps at 200 % text and reads to TalkBack and VoiceOver is checked
on devices (the PR).
"""

import asyncio
from typing import cast

import flet as ft
import pytest

from pycon_us.core.search import SearchResults, search
from pycon_us.screens import search as screen
from pycon_us.screens import search_results, search_scopes
from pycon_us.state import Conference
from pycon_us.ui import scrolling
from pycon_us.ui.scrolling import JUMP_MS
from pycon_us.ui.semantics import semantics_key
from tests import search_view
from tests.search_view import DATA, INDEX, YEAR, Render, Shown, session_ids

render, opened = (search_view.render, search_view.opened)


# ------------------------------------------------------------------ pure parts


@pytest.mark.parametrize(
    ("requested", "remembered", "scope"),
    [
        ("places", "all", "places"),  # the opener's preset (D-19)
        ("sponsors", "places", "sponsors"),  # #397's scope
        ("booths", "places", "all"),  # unknown: All, as D-180 says
        ("rooms", "places", "all"),  # P1's scope, which Places replaced (D-351)
        ("", "places", "all"),
        (None, "speakers", "speakers"),  # mounted without a query: the memory
        (None, "nonsense", "all"),
    ],
)
def test_the_scope_comes_from_the_opener_then_the_memory(
    requested: str | None, remembered: str, scope: str
) -> None:
    """A known requested scope wins; with none, the memory's; else All."""
    assert screen.scope_of(requested, remembered) == scope


def test_the_summary_names_only_the_types_found_in_words() -> None:
    """The summary counts each type found, in words, and skips the others."""
    sessions = search(INDEX, "a", "all")
    assert search_results.summary(sessions) == (
        f"{sessions.session_count} sessions, {len(sessions.speakers)} speakers, "
        f"{sessions.place_count} places, {len(sessions.sponsors)} sponsors"
    )
    one_room = SearchResults(rooms=(DATA.rooms["room-103abc"],))
    assert search_results.summary(one_room) == "1 place"
    desk = YEAR.map.pin("info-desk")
    assert desk is not None
    both = SearchResults(rooms=one_room.rooms, spots=(desk,))
    assert search_results.summary(both) == "2 places"  # rooms and spots together
    bloomberg = search(INDEX, "bloomberg", "sponsors")
    assert search_results.summary(bloomberg) == "1 sponsor"


# ------------------------------------------------------------------ the field


async def test_the_field_takes_the_focus_and_never_fixes_words(opened: Shown) -> None:
    """The field opens empty and focused, with no autocorrect or suggestions."""
    text_field = opened.field
    assert text_field.autofocus  # the keyboard is up as search opens (ux.md §4.3)
    # The plain keyboard: iOS's web search one shows Go, not Search (D-450).
    assert text_field.keyboard_type == ft.KeyboardType.TEXT
    assert text_field.autocorrect is False  # "asyncio", names
    assert text_field.enable_suggestions is False
    assert text_field.value == ""  # a fresh search


async def test_the_field_is_named_by_its_hint_then_by_its_label(opened: Shown) -> None:
    """The empty field is named by its hint, then by `LABEL` once typed in."""
    assert opened.field.hint_text == screen.HINTS["sessions"]
    assert opened.node("search.field").label is None  # the hint names it
    await opened.type("typing")
    assert opened.node("search.field").label == screen.LABEL
    assert opened.field.value == "typing"  # controlled: the text stays (D-157)


async def test_the_clear_button_empties_the_field_and_focuses_it(
    opened: Shown,
) -> None:
    """Clear empties the field and memory, shows idle at once and refocuses."""
    await opened.type("typing")
    await opened.pause()
    (clear,) = [b for b in opened.find(ft.IconButton) if b.tooltip == screen.CLEAR]
    await opened.event(clear, "click")
    assert opened.field.value == ""
    assert opened.memory.search_query == ""
    assert opened.has("search.idle")  # at once, without waiting for a pause
    assert [f._i for f in opened.focused] == [opened.field._i]


async def test_a_key_a_clear_drops_is_never_remembered_for_a_rebuilt_view(
    opened: Shown, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-243, D-193: Flutter puts the Clear over it, so a rebuilt View must too.

    A key typed on the old text, whose report comes in before Flutter has the empty
    text, is dropped by the field; the memory that rebuilds Search below a result
    must drop it with it, or the rebuilt field brings the cleared text back.
    """
    answer = asyncio.Event()  # Flutter's answer to the focus request, held

    async def focus(self: ft.TextField) -> None:
        opened.focused.append(self)
        await answer.wait()

    monkeypatch.setattr(ft.TextField, "focus", focus)
    await opened.type("chen")
    (clear,) = [b for b in opened.find(ft.IconButton) if b.tooltip == screen.CLEAR]
    await opened.event(clear, "click")
    await opened.type("chensweigart")  # before the empty text reached Flutter
    answer.set()
    await opened.settle()
    assert opened.field.value == ""
    assert opened.memory.search_query == ""

    await opened.go("/schedule")
    await opened.go("/search/room/grand-ballroom-a")  # mounts Search below it
    await opened.go("/search")
    assert opened.field.value == ""
    assert opened.has("search.idle")


# ------------------------------------------------------------------ the debounce


async def test_typing_searches_once_the_typing_pauses_not_per_keystroke(
    opened: Shown,
) -> None:
    """Keystrokes each restart the debounce; one search runs at the pause."""
    asked = len(opened.sleeps.asked)
    for text in ("t", "ty", "typ", "typi", "typing"):
        await opened.type(text)
    assert opened.searches == []
    # Each keystroke restarted the wait: five waits asked for, the last one left.
    assert opened.sleeps.asked[asked:] == [screen.DEBOUNCE_SECONDS] * 5
    assert opened.sleeps.held == 1
    assert opened.has("search.idle")  # and the list still waits for a word
    assert opened.field.value == "typing"  # while the field kept up

    await opened.pause()
    assert opened.searches == [("typing", "sessions")]
    expected = [
        f"search.session.{semantics_key(i)}" for i in session_ids("typing", "sessions")
    ]
    assert [r for r in opened.results if r.startswith("search.session.")] == expected


async def test_the_keyboard_s_action_key_searches_at_once(opened: Shown) -> None:
    """The keyboard's action key is Search and searches at once, without the debounce."""
    assert opened.field.text_input_action is ft.TextInputAction.SEARCH  # U30
    await opened.type("typing")
    await opened.event(opened.field, "submit", "typing")
    assert opened.searches == [("typing", "sessions")]


async def test_a_keystroke_before_the_pause_re_renders_no_result_row(
    opened: Shown,
) -> None:
    """D-153: the results are the same object until the next search (F34)."""
    await opened.type("typing")
    await opened.pause()
    opened.rows.clear()
    await opened.type("typing ")
    assert opened.rows == []
    await opened.pause()  # the same sessions: still nothing re-renders
    assert opened.rows == []


# ------------------------------------------------------------------ scopes


async def test_the_opener_s_scope_is_selected_with_its_check(opened: Shown) -> None:
    """The five scope chips show a check, and the opener's alone is selected."""
    chips = {scope: opened.chip(scope) for scope in search_scopes.SCOPE_LABELS}
    assert [chip.label for chip in chips.values()] == [
        "All",
        "Sessions",
        "Speakers",
        "Places",
        "Sponsors",
    ]
    assert [scope for scope, chip in chips.items() if chip.selected] == ["sessions"]
    assert all(chip.show_checkmark for chip in chips.values())  # not colour alone


async def test_switching_scope_keeps_the_query_and_searches_at_once(
    opened: Shown,
) -> None:
    """A scope chip tap searches the query at once and remembers the scope."""
    await opened.type("grand")
    await opened.pause()
    opened.searches.clear()
    await opened.event(opened.chip("places"), "click")
    assert opened.searches == [("grand", "places")]
    assert opened.haptics.effects == ["selection_click"]  # a chip toggled (ux.md §4.5)
    assert opened.field.value == "grand"
    assert opened.chip("places").selected
    assert not opened.chip("sessions").selected
    assert opened.memory.search_scope == "places"
    assert [r for r in opened.results if r.startswith("search.room.")] == [
        "search.room.grand-ballroom-a",
        "search.room.grand-ballroom-b",
    ]


async def test_a_tap_on_the_selected_chip_keeps_its_scope_and_searches_nothing(
    opened: Shown,
) -> None:
    """The chips are only ours: Flutter never toggles one, so one scope stays on."""
    await opened.type("grand")
    await opened.pause()
    opened.searches.clear()
    before = {
        scope: opened.chip(scope).selected for scope in search_scopes.SCOPE_LABELS
    }
    assert all(opened.chip(scope).on_select is None for scope in before)
    await opened.event(opened.chip("sessions"), "click")
    after = {scope: opened.chip(scope).selected for scope in search_scopes.SCOPE_LABELS}
    assert after == before
    assert [scope for scope, on in after.items() if on] == ["sessions"]
    assert opened.searches == []
    assert opened.haptics.effects == []  # nothing toggled


async def test_the_hint_says_what_the_scope_searches(opened: Shown) -> None:
    """The field's hint names what the selected scope searches."""
    assert opened.field.hint_text == "Search sessions"  # the Schedule's scope
    await opened.event(opened.chip("all"), "click")
    assert opened.field.hint_text == "Search sessions, speakers, places"
    await opened.event(opened.chip("places"), "click")
    assert opened.field.hint_text == "Search rooms and places"
    await opened.event(opened.chip("sponsors"), "click")
    assert opened.field.hint_text == "Search sponsors"


async def test_the_preset_scope_s_chip_is_scrolled_into_sight_at_once(
    render: Render,
) -> None:
    """Opened from the Map, the row jumps to Places with no animation (#794)."""
    shown = await render(Conference(data=DATA, source="bundled", version=1))
    await shown.go("/search?scope=places")
    assert shown.jumps == [("search.scope_anchor.places", 0)]


async def test_a_pick_slides_the_row_to_the_picked_chip(opened: Shown) -> None:
    """A chip picked off the row's edge slides into sight; the opening jumped (#794)."""
    assert opened.jumps == [("search.scope_anchor.sessions", 0)]
    await opened.event(opened.chip("sponsors"), "click")
    await opened.settle()
    assert opened.jumps[1:] == [("search.scope_anchor.sponsors", JUMP_MS)]
    await opened.event(opened.chip("sponsors"), "click")  # the selected one
    await opened.settle()
    assert len(opened.jumps) == 2  # no change of scope, no scroll


async def test_a_drag_of_the_row_stops_a_waiting_jump(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A drag stops the opening jump's retries, which would snap the row back (#794).

    On All the anchor is already in place, so the real `jump_to_key()` gets no
    scroll end and would ask again after `LANDING_S`.
    """
    shown = await render(Conference(data=DATA, source="bundled", version=1))
    asks: list[object] = []

    async def scroll_to(self: ft.Row, **kwargs: object) -> None:
        asks.append(kwargs["scroll_key"])  # the row stays still: no scroll end

    monkeypatch.setattr(search_scopes, "jump_to_key", scrolling.jump_to_key)
    monkeypatch.setattr(scrolling, "LANDING_S", 0.05)
    monkeypatch.setattr(ft.Row, "scroll_to", scroll_to)
    await shown.go("/search?scope=all")
    assert len(asks) == 1
    (row,) = [r for r in shown.find(ft.Row) if r.scroll is not None]
    drag = {
        "event_type": "user",
        "direction": "forward",
        "pixels": 0.0,
        "min_scroll_extent": 0.0,
        "max_scroll_extent": 300.0,
        "viewport_dimension": 400.0,
    }
    await shown.event(row, "scroll", drag)
    await asyncio.sleep(0.2)  # past every retry the jump had left
    assert len(asks) == 1


async def test_each_chip_has_an_anchor_before_it_and_reads_in_order(
    opened: Shown,
) -> None:
    """The keys sit on empty gaps, so the chips read in order, one node each (D-242)."""
    (row,) = [r for r in opened.find(ft.Row) if r.scroll is not None]
    items = cast(list[ft.Row], row.controls[:-1])
    anchors = [cast(ft.Container, item.controls[0]) for item in items]
    assert [str(a.key) for a in anchors] == [
        search_scopes.anchor_key(scope) for scope in search_scopes.SCOPE_LABELS
    ]
    assert all(a.content is None for a in anchors)  # nothing to read
    assert [a.width for a in anchors] == [16, 8, 8, 8, 8]  # the gutter, then gaps
    nodes = [cast(ft.MergeSemantics, item.controls[1]).content for item in items]
    assert [cast(ft.Semantics, n).identifier for n in nodes] == [
        f"search.scope.{scope}" for scope in search_scopes.SCOPE_LABELS
    ]


async def test_an_unknown_scope_opens_on_all(render: Render) -> None:
    """`/search?scope=booths` opens with All selected."""
    conference = Conference(data=DATA, source="bundled", version=1)
    shown = await render(conference)
    await shown.go("/search?scope=booths")  # a typo, or a scope of a later version
    assert shown.chip("all").selected


async def test_the_hint_wraps_only_while_it_shows(opened: Shown) -> None:
    """At the largest text a two-line hint kept a blank line under typed text."""
    assert opened.field.hint_max_lines == 2
    await opened.type("typing")
    assert opened.field.hint_max_lines == 1
