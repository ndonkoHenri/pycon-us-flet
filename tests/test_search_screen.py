"""Tests for the global search screen (``screens/search.py``, #97; NEW-02, D-19, D-193).

The matching is ``core/search.py``'s, tested in ``tests/test_search.py``; here the
screen around it. It runs in a real Flet session under the real Router with
``manage_views``, as the app renders it (``tests/sessions.py``'s ``showing()`` with
``view_path=None``): a small route table with a Schedule stand-in, the global modal
``/search`` and a drill whose detail is a plain View, so a result tap, Back and a fresh
open go through the Router's own view stack (S4, D-141). Navigation is
``page.navigate`` replaced by what Flutter does next: the page's route changes and the
Router hears of it. A keystroke is the field's value patched in and its change event
dispatched, as Flutter sends them (``tests/test_speakers.py``). The debounce's wait is
held until a test ends it (``Shown.pause()``, ``tests/timers.py``), so on a slow host no
search runs between two keystrokes (#270).

How the screen looks, wraps at 200 % text and reads to TalkBack and VoiceOver is
checked on devices (the PR).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.search import SearchResults, first_results, search, search_index
from pycon_us.core.timefmt import day_heading
from pycon_us.locations import parent_of
from pycon_us.screens import search as screen
from pycon_us.screens import search_results
from pycon_us.screens.search_results import FIRST_SESSIONS, FIRST_SPEAKERS
from pycon_us.services import use_services
from pycon_us.state import Conference
from pycon_us.ui import scaffold, session_rows
from pycon_us.ui.semantics import semantics_key
from tests import sessions
from tests.fakes import MemoryHaptics
from tests.feeds import processed
from tests.timers import HeldSleeps

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
    """A known requested scope wins; with none, the memory's; else All."""
    assert screen.scope_of(requested, remembered) == scope


def test_the_summary_names_only_the_types_found_in_words() -> None:
    """The summary counts each type found, in words, and skips the others."""
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
class Shown(sessions.Shown):
    """The harness's ``Shown`` (``tests/sessions.py``) on the app's Views.

    It also records what the search screen asked for: its searches, the focus and its
    sleeps.
    """

    searches: list[tuple[str, str]] = field(default_factory=list)
    """Each ``search(index, query, scope)`` the screen ran, as (query, scope)."""
    focused: list[ft.TextField] = field(default_factory=list)
    """The fields asked to take the focus; no Flutter answers here."""
    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    """The screen's sleeps: the debounce waits until ``pause()`` releases it."""

    @property
    def page(self) -> ft.Page:
        """The session's page."""
        return cast(ft.Page, self.session.page)

    @property
    def haptics(self) -> MemoryHaptics:
        """The ``MemoryHaptics`` of the session's services."""
        return cast(MemoryHaptics, self.services.haptics)

    def live(self) -> list[ft.BaseControl]:
        """The controls on the page now (the index keeps some that left it)."""
        return [c for c in self.session.index.values() if c.page is not None]

    def find[T: ft.BaseControl](self, kind: type[T]) -> list[T]:
        """The controls of ``kind`` on the page now."""
        return [c for c in self.live() if isinstance(c, kind)]

    def node(self, identifier: str) -> ft.Semantics:
        """The one semantics node on the page with ``identifier``."""
        found = [c for c in self.find(ft.Semantics) if c.identifier == identifier]
        assert len(found) == 1, identifier
        return found[0]

    def has(self, identifier: str) -> bool:
        """Whether a semantics node on the page has ``identifier``."""
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
        """The screen's one ``TextField``."""
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

    async def pause(self) -> None:
        """The typing pauses: end the debounce's wait, then let the re-render through."""
        await self.sleeps.release()
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
        await self.event(text_field, "change")

    def chip(self, scope: str) -> ft.Chip:
        """The scope chip for ``scope``."""
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


type Render = Callable[[Conference], Awaitable[Shown]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Provide ``show(conference)``: the app's Views at the Schedule stand-in."""

    def counted_search(index: Any, query: str, scope: str = "all") -> SearchResults:
        sessions.current(Shown).searches.append((query, scope))
        return search(index, query, scope)

    async def focus(self: ft.TextField) -> None:
        sessions.current(Shown).focused.append(self)

    monkeypatch.setattr(screen, "search", counted_search)
    monkeypatch.setattr(ft.TextField, "focus", focus)
    sleeps = HeldSleeps()
    monkeypatch.setattr(screen, "asyncio", sleeps)  # the search module's only

    async with AsyncExitStack() as stack:

        async def show(conference: Conference) -> Shown:
            shown = await stack.enter_async_context(
                sessions.showing(
                    lambda: ft.Router(ROUTES, manage_views=True),
                    year=YEAR,
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=None,  # a real Router, rendered as the page's Views
                    route="/schedule",
                    kind=partial(Shown, sleeps=sleeps),
                )
            )

            def navigate(location: str) -> None:
                asyncio.get_running_loop().create_task(shown.go(location))

            monkeypatch.setattr(shown.page, "navigate", navigate)
            return shown

        yield show


@pytest.fixture
async def opened(render: Render) -> Shown:
    """Search opened from the Schedule stand-in with its scope, as a tap would."""
    shown = await render(Conference(data=DATA, source="bundled", version=1))
    (button,) = shown.find(ft.IconButton)
    await shown.event(button, "click")
    await shown.settle()
    assert shown.views == ["/schedule", "/search"]
    shown.searches.clear()
    return shown


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


# ------------------------------------------------------------------ the field


async def test_the_field_takes_the_focus_and_never_fixes_words(opened: Shown) -> None:
    """The field opens empty and focused, with no autocorrect or suggestions."""
    text_field = opened.field
    assert text_field.autofocus  # the keyboard is up as search opens (ux.md §4.3)
    assert text_field.keyboard_type == ft.KeyboardType.WEB_SEARCH
    assert text_field.autocorrect is False  # "asyncio", names
    assert text_field.enable_suggestions is False
    assert text_field.value == ""  # a fresh search


async def test_the_field_is_named_by_its_hint_then_by_its_label(opened: Shown) -> None:
    """The empty field is named by its hint, then by ``LABEL`` once typed in."""
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
    """The keyboard's submit searches at once, without the debounce."""
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
    """The four scope chips show a check, and the opener's alone is selected."""
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
    """A scope chip tap searches the query at once and remembers the scope."""
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
    """The field's hint names what the selected scope searches."""
    assert opened.field.hint_text == "Search sessions"  # the Schedule's scope
    await opened.event(opened.chip("all"), "click")
    assert opened.field.hint_text == "Search sessions, speakers, rooms"
    await opened.event(opened.chip("rooms"), "click")
    assert opened.field.hint_text == "Search rooms"


async def test_an_unknown_scope_opens_on_all(render: Render) -> None:
    """``/search?scope=sponsors`` opens with All selected."""
    conference = Conference(data=DATA, source="bundled", version=1)
    shown = await render(conference)
    await shown.go("/search?scope=sponsors")  # a P2 scope, or a typo
    assert shown.chip("all").selected


# ------------------------------------------------------------------ results


async def test_results_are_grouped_by_type_then_day_under_headings(
    opened: Shown,
) -> None:
    """All lists each type under a heading, and sessions under day headings."""
    await opened.event(opened.chip("all"), "click")
    await opened.type("a")
    await opened.pause()
    found = search(INDEX, "a", "all")
    first = first_results(found, sessions=FIRST_SESSIONS, speakers=FIRST_SPEAKERS)
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
    expected.append("h2:Rooms")
    expected += [f"search.room.{room.slug}" for room in found.rooms]
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
    assert kinds.count("Divider") == 2
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
    shown.memory.search_query, shown.memory.search_scope = "grand", "rooms"
    await shown.go("/search/room/grand-ballroom-a")
    await shown.go("/search")
    assert shown.field.value == "grand"
    assert shown.chip("rooms").selected
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


async def test_the_hint_wraps_only_while_it_shows(opened: Shown) -> None:
    """At the largest text a two-line hint kept a blank line under typed text."""
    assert opened.field.hint_max_lines == 2
    await opened.type("typing")
    assert opened.field.hint_max_lines == 1
