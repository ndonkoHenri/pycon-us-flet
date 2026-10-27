"""Tests for the search screen's first rows of each type and its Show all (D-193).

The harness is ``tests/search_view.py``'s.
"""

from typing import cast

import flet as ft

from pycon_us.core.search import search
from pycon_us.screens import search_results
from pycon_us.screens.search_results import (
    FIRST_SESSIONS,
    FIRST_SPEAKERS,
    FIRST_SPONSORS,
)
from pycon_us.ui.semantics import semantics_key
from tests import search_view
from tests.search_view import INDEX, Shown, _text, session_ids

render, opened = (search_view.render, search_view.opened)


# ------------------------------------------------------------------ first rows (D-218)


def _listed_sessions(shown: Shown) -> list[str]:
    """The keys of the session and notice rows the list shows, in order."""
    prefixes = ("search.session.", "search.notice.")
    return [r.split(".", 2)[2] for r in shown.results if r.startswith(prefixes)]


def _listed_speakers(shown: Shown) -> list[str]:
    """The keys of the speaker rows the list shows, in order."""
    return [
        r.split(".", 2)[2] for r in shown.results if r.startswith("search.speaker.")
    ]


def _listed_sponsors(shown: Shown) -> list[str]:
    """The slugs of the sponsor rows the list shows, in order."""
    return [
        r.split(".", 2)[2] for r in shown.results if r.startswith("search.sponsor.")
    ]


def _tile_text(node: ft.Semantics) -> str:
    """A "Show all" row's words: its tile's title."""
    tile = cast(ft.ListTile, node.content)
    return str(cast(ft.Text, tile.title).value)


async def _show_whole(shown: Shown, kind: str) -> None:
    """Tap a "Show all" row, as Flutter reports a tap on its tile."""
    tile = cast(ft.ListTile, shown.node(f"search.show_all.{kind}").content)
    await shown.event(tile, "click")


def _keys(ids: list[str]) -> list[str]:
    """The semantics keys of ``ids``."""
    return [semantics_key(i) for i in ids]


async def test_a_broad_query_renders_each_type_s_first_rows_and_the_full_count(
    opened: Shown,
) -> None:
    """#216: rendering every row of a one-letter query made its first render slow."""
    await opened.event(opened.chip("all"), "click")
    await opened.type("a")
    opened.rows.clear()
    await opened.pause()
    found = search(INDEX, "a", "all")
    assert found.session_count > FIRST_SESSIONS
    assert len(found.speakers) > FIRST_SPEAKERS
    assert len(found.sponsors) > FIRST_SPONSORS
    first = _keys(session_ids("a")[:FIRST_SESSIONS])
    assert _listed_sessions(opened) == first
    assert (
        _listed_speakers(opened)
        == _keys([s.id for s in found.speakers])[:FIRST_SPEAKERS]
    )
    assert len(opened.rows) <= FIRST_SESSIONS  # no row past the cut was built
    # The count line says what the search found, not what the list shows yet.
    assert _text(opened.node("search.count")) == search_results.summary(found)
    # Each "Show all" row says the full count and is a button for screen readers.
    show = opened.node("search.show_all.sessions")
    assert show.button
    assert _tile_text(show) == f"Show all {found.session_count} sessions"
    assert _tile_text(opened.node("search.show_all.speakers")) == (
        f"Show all {len(found.speakers)} speakers"
    )
    assert _listed_sponsors(opened) == [s.slug for s in found.sponsors][:FIRST_SPONSORS]
    assert _tile_text(opened.node("search.show_all.sponsors")) == (
        f"Show all {len(found.sponsors)} sponsors"
    )
    # It ends the shown sessions, before the next type.
    listed = [r for r in opened.results if not r.startswith("search.favorite.")]
    at = listed.index("search.show_all.sessions")
    assert listed[at - 1].endswith(f".{first[-1]}")
    assert listed[at + 1] == "h2:Speakers"


async def test_show_all_renders_the_rest_of_its_type_and_each_new_row_once(
    opened: Shown,
) -> None:
    """Show all lists the rest of its type only, building each new row once."""
    await opened.event(opened.chip("all"), "click")
    await opened.type("a")
    await opened.pause()
    opened.rows.clear()
    opened.searches.clear()

    await _show_whole(opened, "sessions")
    every = session_ids("a")
    assert _listed_sessions(opened) == _keys(every)  # every one, in search's order
    assert not opened.has("search.show_all.sessions")
    # The rows already shown are not built again; the new ones once each (D-153),
    # notices too (the harness counts every row body).
    assert sorted(opened.rows) == sorted(every[FIRST_SESSIONS:])
    assert opened.searches == []  # the same results, rendered further
    # The speakers stay cut until their own row is tapped.
    assert len(_listed_speakers(opened)) == FIRST_SPEAKERS
    assert opened.has("search.show_all.speakers")

    await _show_whole(opened, "speakers")
    found = search(INDEX, "a", "all")
    assert _listed_speakers(opened) == _keys([s.id for s in found.speakers])
    assert not opened.has("search.show_all.speakers")
    assert _listed_sessions(opened) == _keys(every)  # still whole

    await _show_whole(opened, "sponsors")
    assert _listed_sponsors(opened) == [s.slug for s in found.sponsors]
    assert not opened.has("search.show_all.sponsors")


async def test_a_keystroke_keeps_what_was_shown_and_a_new_search_cuts_again(
    opened: Shown,
) -> None:
    """The same words keep a whole list whole; any new search cuts it again."""
    await opened.event(opened.chip("all"), "click")
    await opened.type("a")
    await opened.pause()
    await _show_whole(opened, "sessions")
    opened.rows.clear()

    await opened.type("a ")  # the same words: before and after the pause, no row
    assert opened.rows == []
    await opened.pause()
    assert opened.rows == []
    assert not opened.has("search.show_all.sessions")  # the same results, still whole

    await opened.type("e")  # other results: cut again
    await opened.pause()
    assert _listed_sessions(opened) == _keys(session_ids("e")[:FIRST_SESSIONS])
    assert opened.has("search.show_all.sessions")

    await opened.type("a")  # the first query again: a new search, cut too
    await opened.pause()
    assert _listed_sessions(opened) == _keys(session_ids("a")[:FIRST_SESSIONS])
    assert opened.has("search.show_all.sessions")


async def test_a_keystroke_before_the_pause_re_renders_no_row_of_a_cut_list(
    opened: Shown,
) -> None:
    """D-153 with the cut: the results and what is shown of them stay the same."""
    await opened.type("p")
    await opened.pause()
    assert opened.has("search.show_all.sessions")
    opened.rows.clear()
    await opened.type("py")
    assert opened.rows == []
    assert opened.has("search.show_all.sessions")
