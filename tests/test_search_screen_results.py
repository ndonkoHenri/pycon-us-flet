"""Tests for the search screen's results, their taps, Back and the empty states.

The harness is ``tests/search_view.py``'s.
"""

from typing import cast

import flet as ft

from pycon_us.core.search import first_results, search
from pycon_us.core.timefmt import day_heading
from pycon_us.locations import parent_of
from pycon_us.screens import search as screen
from pycon_us.screens.search_results import (
    FIRST_SESSIONS,
    FIRST_SPEAKERS,
    FIRST_SPONSORS,
)
from pycon_us.state import Conference
from pycon_us.ui import session_rows
from pycon_us.ui.semantics import semantics_key
from tests import search_view
from tests.search_view import (
    DATA,
    INDEX,
    YEAR,
    Render,
    Shown,
    _all_text,
    _first,
    _text,
    session_ids,
)

render, opened = (search_view.render, search_view.opened)


# ------------------------------------------------------------------ results


async def test_results_are_grouped_by_type_then_day_under_headings(
    opened: Shown,
) -> None:
    """All lists each type under a heading, and sessions under day headings."""
    await opened.event(opened.chip("all"), "click")
    await opened.type("a")
    await opened.pause()
    found = search(INDEX, "a", "all")
    first = first_results(
        found,
        sessions=FIRST_SESSIONS,
        speakers=FIRST_SPEAKERS,
        sponsors=FIRST_SPONSORS,
    )
    # No counts: the count line above the list says them (D-193). Each type shows its
    # first rows, then a row that shows the rest (D-218).
    expected: list[str] = ["h2:Sessions"]
    for day in first.sessions:
        expected.append(f"h3:{day_heading(day.day)}")
        for session in day.sessions:
            notice = session_rows.is_notice(session, YEAR.conference)
            kind = "notice" if notice else "session"
            expected.append(f"search.{kind}.{semantics_key(session.id)}")
    expected.append("search.show_all.sessions")
    expected.append("h2:Speakers")
    expected += [f"search.speaker.{semantics_key(s.id)}" for s in first.speakers]
    expected.append("search.show_all.speakers")
    expected.append("h2:Places")
    expected += [f"search.room.{room.slug}" for room in found.rooms]
    expected += [f"search.place.{pin.key}" for pin in found.spots]
    assert found.spots  # "a" finds venue spots too, after the rooms
    expected.append("h2:Sponsors")
    expected += [f"search.sponsor.{s.slug}" for s in first.sponsors]
    expected.append("search.show_all.sponsors")
    listed = [r for r in opened.results if not r.startswith("search.favorite.")]
    assert listed == expected


async def test_a_type_heading_looks_a_step_above_a_day_heading(opened: Shown) -> None:
    """On screen too, "Speakers" must not read as one more day (D-193)."""
    await opened.event(opened.chip("all"), "click")
    await opened.type("a")
    await opened.pause()
    (body,) = opened.find(ft.ListView)
    headings = {
        _text(h): h
        for h in opened.find(ft.Semantics)
        if h.header and h.heading_level in (2, 3)
    }
    first_day = day_heading(search(INDEX, "a", "all").sessions[0].day)
    type_text = cast(ft.Text, _first(headings["Speakers"], ft.Text))
    day_text = cast(ft.Text, _first(headings[first_day], ft.Text))
    assert type_text.theme_style == ft.TextThemeStyle.TITLE_MEDIUM
    assert type_text.color == ft.Colors.ON_SURFACE
    assert day_text.theme_style == ft.TextThemeStyle.TITLE_SMALL
    assert day_text.color == ft.Colors.PRIMARY
    # A divider before each type but the first, and the first day close under its type.
    kinds = [type(c).__name__ for c in body.controls]
    assert kinds.count("Divider") == 3
    assert not isinstance(body.controls[0], ft.Divider)
    day_box = cast(ft.Container, headings[first_day].content)
    assert day_box.padding == ft.Padding.only(left=16, top=0, right=16, bottom=8)


async def test_what_was_found_is_said_in_a_polite_live_region(opened: Shown) -> None:
    """The count is a live region, absent before a search and on a miss."""
    assert not opened.has("search.count")  # nothing searched yet
    await opened.type("grand")
    await opened.pause()
    count = opened.node("search.count")
    assert count.live_region
    assert _text(count) == f"{len(session_ids('grand', 'sessions'))} sessions"
    await opened.type("zzzz")
    await opened.pause()
    assert not opened.has("search.count")  # a miss announces itself


async def test_a_result_opens_its_detail_on_top_of_search(opened: Shown) -> None:
    """A result tap pushes its detail View above Search."""
    await opened.type("typing")
    await opened.pause()
    first = session_ids("typing", "sessions")[0]
    tap = opened.node(f"search.session.{semantics_key(first)}").parent
    await opened.event(cast(ft.Control, tap), "click")
    assert opened.views == ["/schedule", "/search", f"/search/session/{first}"]


async def test_back_from_a_result_returns_to_the_results_with_the_query(
    opened: Shown,
) -> None:
    """Back from a result shows the same query and results, searching nothing."""
    await opened.type("typing")
    await opened.pause()
    before = opened.results
    first = session_ids("typing", "sessions")[0]
    await opened.go(f"/search/session/{first}")
    opened.searches.clear()

    await opened.go(parent_of(f"/search/session/{first}", opened.memory.search_base))
    assert opened.views == ["/schedule", "/search"]
    assert opened.field.value == "typing"
    assert opened.results == before
    assert opened.searches == []  # the same View, still mounted: nothing to redo


async def test_a_venue_spot_opens_its_plan_with_the_pin_and_back_keeps_the_query(
    opened: Shown,
) -> None:
    """#393: a venue spot pushes its floor plan at its pin; Back finds the results."""
    await opened.event(opened.chip("places"), "click")
    await opened.type("info desk")
    await opened.pause()
    before = opened.results
    # One type: no heading (D-193). Lost & found is "the information desk" after hours.
    assert before == ["search.place.info-desk", "search.place.lost-and-found"]
    tap = opened.node("search.place.info-desk").content  # the ListTile
    await opened.event(cast(ft.Control, tap), "click")
    await opened.settle()  # the navigation's task
    assert opened.page.route == "/search/plan/concourse?pin=info-desk"
    assert opened.views == ["/schedule", "/search", "/search/plan/concourse"]
    opened.searches.clear()

    await opened.go(parent_of(opened.page.route, opened.memory.search_base))
    assert opened.views == ["/schedule", "/search"]
    assert opened.field.value == "info desk"
    assert opened.results == before
    assert opened.searches == []


async def test_a_sponsor_opens_its_detail_and_back_keeps_the_query_and_scope(
    opened: Shown,
) -> None:
    """#397: a sponsor row is one phrase; it pushes sponsor detail over the results."""
    await opened.event(opened.chip("sponsors"), "click")
    await opened.type("bloomberg")
    await opened.pause()
    before = opened.results
    assert before == ["search.sponsor.bloomberg"]  # one type: no heading (D-193)
    node = opened.node("search.sponsor.bloomberg")
    assert node.label == "Bloomberg, Visionary sponsor, booth 613"
    assert node.button and node.exclude_semantics  # one node, its texts unread
    assert _all_text(node) == "Bloomberg Visionary \N{MIDDLE DOT} Booth 613"
    await opened.event(cast(ft.Control, node.parent), "click")  # the inked row
    await opened.settle()  # the navigation's task
    assert opened.views == ["/schedule", "/search", "/search/sponsor/bloomberg"]
    opened.searches.clear()

    await opened.go(parent_of(opened.page.route, opened.memory.search_base))
    assert opened.views == ["/schedule", "/search"]
    assert opened.field.value == "bloomberg"
    assert opened.chip("sponsors").selected
    assert opened.results == before
    assert opened.searches == []


async def test_the_field_lets_the_focus_go_while_a_result_covers_it(
    opened: Shown,
) -> None:
    """The field can take the focus only while Search is the top View (#344, D-330).

    A field that kept the focus with its keyboard closed would get it back, and the
    keyboard with it, from Flutter's route focus restoration when Back pops the result.
    """
    await opened.type("typing")
    await opened.pause()
    assert opened.field.can_request_focus
    first = session_ids("typing", "sessions")[0]
    await opened.go(f"/search/session/{first}")
    assert opened.field.can_request_focus is False  # unfocused as the result opens

    await opened.go(parent_of(f"/search/session/{first}", opened.memory.search_base))
    assert opened.field.can_request_focus  # a tap focuses it again
    assert opened.focused == []  # and nothing asked for the focus on Back


async def test_a_view_rebuilt_below_a_result_cannot_take_the_focus(
    render: Render,
) -> None:
    """A Search View mounted below a result never autofocuses there (D-330)."""
    shown = await render(Conference(data=DATA, source="bundled", version=1))
    await shown.go("/search/room/grand-ballroom-a")
    assert shown.field.autofocus
    assert shown.field.can_request_focus is False  # so autofocus takes nothing
    await shown.go("/search")
    assert shown.field.can_request_focus


async def test_each_opening_starts_a_new_search_and_back_leaves_for_the_opener(
    opened: Shown,
) -> None:
    """Back from Search returns to the opener, and Search reopens empty."""
    await opened.type("typing")
    assert opened.memory.search_query == "typing"
    await opened.go(parent_of("/search", opened.memory.search_base))
    assert opened.views == ["/schedule"]

    (button,) = opened.find(ft.IconButton)
    await opened.event(button, "click")
    assert opened.views == ["/schedule", "/search"]
    assert opened.field.value == ""
    assert opened.has("search.idle")


async def test_a_view_rebuilt_below_a_result_gets_the_query_and_scope_back(
    render: Render,
) -> None:
    """A deep entry under ``/search`` mounts Search below the top (D-18, D-164)."""
    conference = Conference(data=DATA, source="bundled", version=1)
    shown = await render(conference)
    shown.memory.search_query, shown.memory.search_scope = "grand", "places"
    await shown.go("/search/room/grand-ballroom-a")
    await shown.go("/search")
    assert shown.field.value == "grand"
    assert shown.chip("places").selected
    assert "search.room.grand-ballroom-a" in shown.results


async def test_a_star_in_the_results_saves_the_session_and_re_renders_one_row(
    opened: Shown,
) -> None:
    """A star tap in the results saves the session and re-renders only its row."""
    await opened.type("typing")
    await opened.pause()
    first = session_ids("typing", "sessions")[0]
    star = opened.node(f"search.favorite.{semantics_key(first)}")
    opened.rows.clear()
    await opened.event(cast(ft.Control, star.content), "click")
    assert opened.favorites.ids == {first}
    assert opened.rows == [first]


# ------------------------------------------------------------------ states


async def test_before_a_word_the_screen_says_what_search_covers(opened: Shown) -> None:
    """Before a word (spaces are none), a live idle state says what search covers."""
    idle = opened.node("search.idle")
    assert idle.live_region
    assert screen.COVERS in _all_text(idle)
    assert screen.IDLE_TITLES["sessions"] in _all_text(idle)
    await opened.type("   ")  # spaces are no word
    await opened.pause()
    assert opened.has("search.idle")


async def test_a_miss_says_search_covers_all_days_and_ignores_filters(
    opened: Shown,
) -> None:
    """A miss in All quotes the query, says what search covers, and has no button."""
    await opened.event(opened.chip("all"), "click")
    await opened.type("pydanitc")
    await opened.pause()
    miss = opened.node("search.no_match")
    assert "No results for \N{LEFT DOUBLE QUOTATION MARK}pydanitc" in _all_text(miss)
    assert screen.COVERS in _all_text(miss)
    # In All there is nowhere else to look: the field and the sentence are the way out.
    assert opened.find(ft.FilledTonalButton) == []


async def test_a_miss_in_one_scope_offers_the_results_of_the_others(
    opened: Shown,
) -> None:
    """A miss in one scope offers "Show all results", which switches to All."""
    await opened.event(opened.chip("places"), "click")
    await opened.type("typing")  # sessions, no place
    await opened.pause()
    assert opened.has("search.no_match")
    (button,) = opened.find(ft.FilledTonalButton)
    assert button.content == "Show all results"
    await opened.event(button, "click")
    assert opened.chip("all").selected
    assert opened.field.value == "typing"
    # The button went away with the miss: the focus goes to the field, not nowhere.
    assert [f._i for f in opened.focused] == [opened.field._i]
    assert any(r.startswith("search.session.") for r in opened.results)


async def test_without_data_the_skeleton_then_try_again(render: Render) -> None:
    """Without data Search shows its status strip, then no-data once a fetch fails."""
    conference = Conference()
    shown = await render(conference)
    await shown.go("/search?scope=all")
    assert shown.has("app.status")
    assert not shown.has("search.no_data")  # the first fetch has not failed yet
    conference.problem = "offline"
    await shown.settle()
    assert shown.has("search.no_data")


async def test_one_type_of_results_gets_no_type_heading(opened: Shown) -> None:
    """The count line says "7 sessions": a "Sessions (7)" heading would repeat it."""
    await opened.type("typing")
    await opened.pause()
    headings = [r for r in opened.results if r.startswith("h")]
    days = search(INDEX, "typing", "sessions").sessions
    assert headings == [f"h2:{day_heading(day.day)}" for day in days]
