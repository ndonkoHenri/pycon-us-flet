"""Tests for the global search screen (``screens/search.py``, #97; NEW-02, D-19, D-191).

The matching is ``core/search.py``'s, tested in ``tests/test_search.py``; here the
screen around it. It runs in a real Flet session under the real Router with
``manage_views``, as the app renders it: a small route table with a Schedule stand-in,
the global modal ``/search`` and a drill whose detail is a plain View, so a result tap,
Back and a fresh open go through the Router's own view stack (S4, D-141). Navigation is
``page.navigate`` replaced by what Flutter does next: the page's route changes and the
Router hears of it. A keystroke is the field's value patched in and its change event
dispatched, as Flutter sends them (``tests/test_speakers.py``).

How the screen looks, wraps at 200 % text and reads to TalkBack and VoiceOver is
checked on devices (the PR).
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest
from flet.controls.context import _context_page
from flet.messaging.session import Session

from pycon_us.config import load_year
from pycon_us.core.search import SearchResults, search, search_index
from pycon_us.core.timefmt import day_heading
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.locations import parent_of
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens import search as screen
from pycon_us.screens import search_results
from pycon_us.services import Services, ServicesCtx, use_services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ConferenceCtx, ViewMemory
from pycon_us.ui import scaffold, session_rows
from pycon_us.ui.session_rows import semantics_key
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed
from tests.test_session_rows import _connection

YEAR = load_year(2026)
DATA = processed(2026)
INDEX = search_index(DATA)


# ------------------------------------------------------------------ pure parts


@pytest.mark.parametrize(
    ("requested", "remembered", "scope"),
    [
        ("rooms", "all", "rooms"),  # the opener's preset (D-19)
        ("sponsors", "rooms", "all"),  # unknown (P2's scopes): All, as D-180 says
        ("", "rooms", "all"),
        (None, "speakers", "speakers"),  # mounted without a query: the memory
        (None, "nonsense", "all"),
    ],
)
def test_the_scope_comes_from_the_opener_then_the_memory(
    requested: str | None, remembered: str, scope: str
) -> None:
    assert screen.scope_of(requested, remembered) == scope


def test_the_summary_names_only_the_types_found_in_words() -> None:
    sessions = search(INDEX, "a", "all")
    assert search_results.summary(sessions) == (
        f"{sessions.session_count} sessions, {len(sessions.speakers)} speakers, "
        f"{len(sessions.rooms)} rooms"
    )
    one_room = SearchResults(rooms=(DATA.rooms["room-103abc"],))
    assert search_results.summary(one_room) == "1 room"


# ------------------------------------------------------------------ the harness


@ft.component
def Opener() -> ft.View:
    """A tab root with a Search button, as the Schedule's (D-19)."""
    memory = use_services().memory
    return ft.View(
        route="/schedule",
        controls=[scaffold.search_button(memory, "sessions")],
    )


@ft.component
def Detail() -> ft.View:
    """A pushed detail: its path, so a test can tell which one shows."""
    return ft.View(route=ft.use_view_path(), controls=[ft.Text(ft.use_view_path())])


DRILL = ft.Route(path=":kind/:ident", recursive=True, component=Detail)
ROUTES = [
    ft.Route(path="schedule", component=Opener, children=[DRILL]),
    ft.Route(path="search", component=screen.Search, modal=True, children=[DRILL]),
]


@dataclass
class Shown:
    """A Flet session showing the app's views, and what the screen asked for."""

    session: Session
    memory: ViewMemory
    favorites: Favorites
    haptics: MemoryHaptics
    searches: list[tuple[str, str]] = field(default_factory=list)
    """Each ``search(index, query, scope)`` the screen ran, as (query, scope)."""
    rows: list[str] = field(default_factory=list)
    """The session ids whose row bodies ran, in order."""
    focused: list[ft.TextField] = field(default_factory=list)
    token: Any = None

    @property
    def page(self) -> ft.Page:
        return cast(ft.Page, self.session.page)

    def live(self) -> list[ft.BaseControl]:
        """The controls on the page now (the index keeps some that left it)."""
        return [c for c in self.session.index.values() if c.page is not None]

    def find[T: ft.BaseControl](self, kind: type[T]) -> list[T]:
        return [c for c in self.live() if isinstance(c, kind)]

    def node(self, identifier: str) -> ft.Semantics:
        found = [c for c in self.find(ft.Semantics) if c.identifier == identifier]
        assert len(found) == 1, identifier
        return found[0]

    def has(self, identifier: str) -> bool:
        return any(c.identifier == identifier for c in self.find(ft.Semantics))

    @property
    def views(self) -> list[str]:
        """The routes of the Views the Router stacks, bottom first."""
        node: Any = self.page.views
        # page.views is the root component; the providers' bodies lead to the
        # Router's, a list of Views (or components rendering one each).
        while not isinstance(node, list):
            node = node._b
        routes = []
        for view in node:
            while not isinstance(view, ft.View):
                view = view._b
            routes.append(str(view.route))
        return routes

    @property
    def field(self) -> ft.TextField:
        (text_field,) = self.find(ft.TextField)
        return text_field

    @property
    def results(self) -> list[str]:
        """The identifiers of the result rows and headings, in the list's order."""
        (body,) = self.find(ft.ListView)
        found: list[str] = []

        def walk(control: object) -> None:
            if isinstance(control, ft.Semantics) and control.header:
                found.append(f"h{control.heading_level}:{_text(control)}")
            identifier = getattr(control, "identifier", None)
            if isinstance(identifier, str) and identifier.startswith("search."):
                found.append(identifier)
            for name in ("content", "_b"):
                child = getattr(control, name, None)
                for item in child if isinstance(child, list) else [child]:
                    if isinstance(item, ft.BaseControl):
                        walk(item)
            for child in getattr(control, "controls", None) or ():
                walk(child)

        walk(body)
        return found

    async def settle(self) -> None:
        for _ in range(20):
            await asyncio.sleep(0)

    async def pause(self) -> None:
        """Wait out the debounce, then let the re-render through."""
        await asyncio.sleep(screen.DEBOUNCE_SECONDS * 2)
        await self.settle()

    async def go(self, location: str) -> None:
        """Navigate as ``page.navigate`` does through Flutter: a new route, heard."""
        self.page.route = location
        # The Router's own handler, which reads only the event's route.
        handler: Any = self.page.on_route_change
        handler(SimpleNamespace(route=location))
        await self.settle()

    async def type(self, text: str) -> None:
        """Type into the field as Flutter reports it: the value, then the event."""
        text_field = self.field
        self.session.apply_patch(text_field._i, {"value": text})
        await self.session.dispatch_event(text_field._i, "change", None)
        await self.settle()

    async def event(self, control: ft.BaseControl, name: str, data: Any = None) -> None:
        await self.session.dispatch_event(control._i, name, data)
        await self.settle()

    def chip(self, scope: str) -> ft.Chip:
        return cast(ft.Chip, self.node(f"search.scope.{scope}").content)


def _first[T: ft.BaseControl](control: object, kind: type[T]) -> T | None:
    """The first ``kind`` under ``control``, following ``content``."""
    while control is not None and not isinstance(control, kind):
        control = getattr(control, "content", None)
    return control


def _text(control: object) -> str:
    """The first ``Text`` value under ``control``."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""


async def show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conference: Conference
) -> Shown:
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    memory = ViewMemory()
    haptics = MemoryHaptics()
    svc = Services(
        year=YEAR,
        storage=storage,
        memory=memory,
        semantics=MemorySemantics(),
        haptics=haptics,
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )
    favorites = Favorites()
    await favorites.load(storage)
    result = Shown(Session(_connection()), memory, favorites, haptics)

    def counted_search(index: Any, query: str, scope: str = "all") -> SearchResults:
        result.searches.append((query, scope))
        return search(index, query, scope)

    phrase = session_rows.spoken_phrase

    def counted_phrase(labels: Any, view: Any) -> str:
        result.rows.append(view.session.id)
        return phrase(labels, view)

    async def focus(self: ft.TextField) -> None:
        result.focused.append(self)

    monkeypatch.setattr(screen, "search", counted_search)
    # Each row body says its phrase once: counting the calls counts the bodies (S2).
    monkeypatch.setattr(session_rows, "spoken_phrase", counted_phrase)
    monkeypatch.setattr(ft.TextField, "focus", focus)
    monkeypatch.setattr(screen, "DEBOUNCE_SECONDS", 0.05)

    @ft.component
    def Root() -> ft.Control:
        return ServicesCtx(
            svc,
            lambda: ConferenceCtx(
                conference,
                lambda: PrefsCtx(
                    Prefs(loaded=True),
                    lambda: FavoritesCtx(
                        favorites, lambda: ft.Router(ROUTES, manage_views=True)
                    ),
                ),
            ),
        )

    page = result.page
    page.route = "/schedule"
    result.token = _context_page.set(page)  # pyright: ignore[reportArgumentType]

    def navigate(location: str) -> None:
        asyncio.get_running_loop().create_task(result.go(location))

    monkeypatch.setattr(page, "navigate", navigate)
    page.render_views(Root)
    result.session.get_page_patch()
    await result.settle()
    return result


@pytest.fixture
async def opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Shown]:
    """Search opened from the Schedule stand-in with its scope, as a tap would."""
    conference = Conference(data=DATA, source="bundled", version=1)
    shown = await show(tmp_path, monkeypatch, conference)
    try:
        (button,) = shown.find(ft.IconButton)
        await shown.event(button, "click")
        await shown.settle()
        assert shown.views == ["/schedule", "/search"]
        shown.searches.clear()
        yield shown
    finally:
        shown.session.close()
        await shown.settle()
        _context_page.reset(shown.token)


def session_ids(query: str, scope: str = "all") -> list[str]:
    """The session ids ``core.search`` finds, in its order."""
    return [s.id for day in search(INDEX, query, scope).sessions for s in day.sessions]


def _all_text(control: object) -> str:
    """Every ``Text`` value under ``control``, joined by spaces."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, ft.Text):
            found.append(str(node.value))
        for name in ("content", "_b"):
            child = getattr(node, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.BaseControl):
                    walk(item)
        for child in getattr(node, "controls", None) or ():
            walk(child)

    walk(control)
    return " ".join(found)


async def closed(shown: Shown) -> None:
    shown.session.close()
    await shown.settle()
    _context_page.reset(shown.token)


# ------------------------------------------------------------------ the field


async def test_the_field_takes_the_focus_and_never_fixes_words(opened: Shown) -> None:
    text_field = opened.field
    assert text_field.autofocus  # the keyboard is up as search opens (ux.md §4.3)
    assert text_field.keyboard_type == ft.KeyboardType.WEB_SEARCH
    assert text_field.autocorrect is False  # "asyncio", names
    assert text_field.enable_suggestions is False
    assert text_field.value == ""  # a fresh search


async def test_the_field_is_named_by_its_hint_then_by_its_label(opened: Shown) -> None:
    assert opened.field.hint_text == screen.HINTS["sessions"]
    assert opened.node("search.field").label is None  # the hint names it
    await opened.type("typing")
    assert opened.node("search.field").label == screen.LABEL
    assert opened.field.value == "typing"  # controlled: the text stays (D-157)


async def test_the_clear_button_empties_the_field_and_focuses_it(
    opened: Shown,
) -> None:
    await opened.type("typing")
    await opened.pause()
    (clear,) = [b for b in opened.find(ft.IconButton) if b.tooltip == screen.CLEAR]
    await opened.event(clear, "click")
    assert opened.field.value == ""
    assert opened.memory.search_query == ""
    assert opened.has("search.idle")  # at once, without waiting for a pause
    assert [f._i for f in opened.focused] == [opened.field._i]


# ------------------------------------------------------------------ the debounce


async def test_typing_searches_once_the_typing_pauses_not_per_keystroke(
    opened: Shown,
) -> None:
    for text in ("t", "ty", "typ", "typi", "typing"):
        await opened.type(text)
    assert opened.searches == []  # each keystroke restarted the wait
    assert opened.has("search.idle")  # and the list still waits for a word
    assert opened.field.value == "typing"  # while the field kept up

    await opened.pause()
    assert opened.searches == [("typing", "sessions")]
    expected = [
        f"search.session.{semantics_key(i)}" for i in session_ids("typing", "sessions")
    ]
    assert [r for r in opened.results if r.startswith("search.session.")] == expected


async def test_the_keyboard_s_action_key_searches_at_once(opened: Shown) -> None:
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
    chips = {scope: opened.chip(scope) for scope in screen.SCOPE_LABELS}
    assert [chip.label for chip in chips.values()] == [
        "All",
        "Sessions",
        "Speakers",
        "Rooms",
    ]
    assert [scope for scope, chip in chips.items() if chip.selected] == ["sessions"]
    assert all(chip.show_checkmark for chip in chips.values())  # not colour alone


async def test_switching_scope_keeps_the_query_and_searches_at_once(
    opened: Shown,
) -> None:
    await opened.type("grand")
    await opened.pause()
    opened.searches.clear()
    await opened.event(opened.chip("rooms"), "click")
    assert opened.searches == [("grand", "rooms")]
    assert opened.haptics.effects == ["selection_click"]  # a chip toggled (ux.md §4.5)
    assert opened.field.value == "grand"
    assert opened.chip("rooms").selected
    assert not opened.chip("sessions").selected
    assert opened.memory.search_scope == "rooms"
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
    before = {scope: opened.chip(scope).selected for scope in screen.SCOPE_LABELS}
    assert all(opened.chip(scope).on_select is None for scope in before)
    await opened.event(opened.chip("sessions"), "click")
    after = {scope: opened.chip(scope).selected for scope in screen.SCOPE_LABELS}
    assert after == before
    assert [scope for scope, on in after.items() if on] == ["sessions"]
    assert opened.searches == []
    assert opened.haptics.effects == []  # nothing toggled


async def test_the_hint_says_what_the_scope_searches(opened: Shown) -> None:
    assert opened.field.hint_text == "Search sessions"  # the Schedule's scope
    await opened.event(opened.chip("all"), "click")
    assert opened.field.hint_text == "Search sessions, speakers, rooms"
    await opened.event(opened.chip("rooms"), "click")
    assert opened.field.hint_text == "Search rooms"


async def test_an_unknown_scope_opens_on_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conference = Conference(data=DATA, source="bundled", version=1)
    shown = await show(tmp_path, monkeypatch, conference)
    try:
        await shown.go("/search?scope=sponsors")  # a P2 scope, or a typo
        assert shown.chip("all").selected
    finally:
        await closed(shown)


# ------------------------------------------------------------------ results


async def test_results_are_grouped_by_type_then_day_under_headings(
    opened: Shown,
) -> None:
    await opened.event(opened.chip("all"), "click")
    await opened.type("a")
    await opened.pause()
    found = search(INDEX, "a", "all")
    # No counts: the count line above the list says them (D-191).
    expected: list[str] = ["h2:Sessions"]
    for day in found.sessions:
        expected.append(f"h3:{day_heading(day.day)}")
        for session in day.sessions:
            notice = session_rows.is_notice(session, YEAR.conference)
            kind = "notice" if notice else "session"
            expected.append(f"search.{kind}.{semantics_key(session.id)}")
    expected.append("h2:Speakers")
    expected += [f"search.speaker.{semantics_key(s.id)}" for s in found.speakers]
    expected.append("h2:Rooms")
    expected += [f"search.room.{room.slug}" for room in found.rooms]
    listed = [r for r in opened.results if not r.startswith("search.favorite.")]
    assert listed == expected


async def test_a_type_heading_looks_a_step_above_a_day_heading(opened: Shown) -> None:
    """On screen too, "Speakers" must not read as one more day (D-191)."""
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
    assert kinds.count("Divider") == 2
    assert not isinstance(body.controls[0], ft.Divider)
    day_box = cast(ft.Container, headings[first_day].content)
    assert day_box.padding == ft.Padding.only(left=16, top=0, right=16, bottom=8)


async def test_what_was_found_is_said_in_a_polite_live_region(opened: Shown) -> None:
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
    await opened.type("typing")
    await opened.pause()
    first = session_ids("typing", "sessions")[0]
    tap = opened.node(f"search.session.{semantics_key(first)}").parent
    await opened.event(cast(ft.Control, tap), "click")
    assert opened.views == ["/schedule", "/search", f"/search/session/{first}"]


async def test_back_from_a_result_returns_to_the_results_with_the_query(
    opened: Shown,
) -> None:
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


async def test_each_opening_starts_a_new_search_and_back_leaves_for_the_opener(
    opened: Shown,
) -> None:
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deep entry under ``/search`` mounts Search below the top (D-18, D-164)."""
    conference = Conference(data=DATA, source="bundled", version=1)
    shown = await show(tmp_path, monkeypatch, conference)
    try:
        shown.memory.search_query, shown.memory.search_scope = "grand", "rooms"
        await shown.go("/search/room/grand-ballroom-a")
        await shown.go("/search")
        assert shown.field.value == "grand"
        assert shown.chip("rooms").selected
        assert "search.room.grand-ballroom-a" in shown.results
    finally:
        await closed(shown)


async def test_a_star_in_the_results_saves_the_session_and_re_renders_one_row(
    opened: Shown,
) -> None:
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
    await opened.event(opened.chip("rooms"), "click")
    await opened.type("typing")  # sessions, no room
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


async def test_without_data_the_skeleton_then_try_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conference = Conference()
    shown = await show(tmp_path, monkeypatch, conference)
    try:
        await shown.go("/search?scope=all")
        assert shown.has("app.status")
        assert not shown.has("search.no_data")  # the first fetch has not failed yet
        conference.problem = "offline"
        await shown.settle()
        assert shown.has("search.no_data")
    finally:
        await closed(shown)


async def test_one_type_of_results_gets_no_type_heading(opened: Shown) -> None:
    """The count line says "7 sessions": a "Sessions (7)" heading would repeat it."""
    await opened.type("typing")
    await opened.pause()
    headings = [r for r in opened.results if r.startswith("h")]
    days = search(INDEX, "typing", "sessions").sessions
    assert headings == [f"h2:{day_heading(day.day)}" for day in days]


async def test_the_hint_wraps_only_while_it_shows(opened: Shown) -> None:
    """At the largest text a two-line hint kept a blank line under typed text."""
    assert opened.field.hint_max_lines == 2
    await opened.type("typing")
    assert opened.field.hint_max_lines == 1
