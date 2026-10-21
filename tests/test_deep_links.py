"""Deep links land on their target with the root below, cold and warm (P2-79, #439).

A link ``pyconus://app/<path>`` reaches the app as the path (D-21, D-269, F31): cold,
the start route; warm, a route change. These tests start the app's own route table
and screens at a location, or move a running session there, in a real Flet session
(``tests/links.py``), then press Back until the app exits: one View per press, a root
to Now, Now out of the app (D-17, D-142). Unknown ids show their detail's not-found
state over the root (D-186), quoted ids reach their screen whole (D-141), and a query
stays a view option of the top View (architecture §5.6). What the emulator and the
simulator show, the boot gate and Back on Now (F29) among it, is in the PR.
"""

from typing import Any, cast
from urllib.parse import quote

import flet as ft
import pytest

from pycon_us.locations import PAGES, TAB_ROOTS, WELCOME, parent_of
from pycon_us.memory import ViewMemory
from tests import links
from tests.links import DATA, EXIT, Open, Shown

open_at = links.open_at  # the fixture, under this module's name (tests/chrome.py)

QUOTED = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
"""A session id with a space and colons, which a link carries quoted (D-42)."""


def walk_down(location: str, search_base: str = "/now") -> list[str]:
    """Where Back after Back goes from a location, by D-17's rules, to the exit.

    One step up per press (``parent_of()``) to a root, then Now, then out.
    """
    steps = []
    while location.split("?")[0] not in TAB_ROOTS:
        location = parent_of(location, search_base)
        steps.append(location)
    if location != "/now":
        steps.append("/now")
    return [*steps, EXIT]


async def walked(shown: Shown) -> list[str]:
    """Press Back until the app exits; each press must pop exactly one View.

    A root's Back replaces it with Now (one View for one View), so only a pushed
    View's Back shortens the stack.
    """
    steps = []
    for _ in range(12):
        before = shown.views()
        step = await shown.back()
        steps.append(step)
        if step == EXIT:
            return steps
        after = shown.views()
        assert len(after) == max(len(before) - 1, 1), (step, shown.routes())
    raise AssertionError(f"Back never left the app: {steps}")


def title_of(shown: Shown, identifier: str) -> str:
    """The text of the screen's heading with that identifier."""
    node = shown.node(identifier)
    while not isinstance(node, ft.Text):
        node = cast(Any, node).content
    return str(node.value)


# ------------------------------------------------------------------ cold: every page


@pytest.mark.parametrize("location", sorted(PAGES))
async def test_every_page_opens_as_a_start_route_and_back_walks_it_down(
    open_at: Open, location: str
) -> None:
    """Every page, as a cold link's start route, is the top View over its parents.

    Back then pops one View per press to its root, the root goes to Now and Now
    leaves the app. Welcome, a root without the bar, is one View, and Back on it goes
    to Now, as on the other roots (D-321).
    """
    shown = await open_at(location)
    routes = shown.routes()
    if location == WELCOME:
        assert routes == ["/"]  # the roots' shared key (D-142, D-287)
        assert await walked(shown) == ["/now", EXIT]
        return
    if location in TAB_ROOTS:
        assert routes == ["/"]  # one root, the roots' shared key (D-142)
    else:
        assert routes[-1] == location  # the target, on top
        assert routes[0] == "/"  # a root (or Start, under a cold /search) below
    assert await walked(shown) == walk_down(location)


DRILL_BASES = [*TAB_ROOTS, "/more/speakers", "/more/tracks/ai", "/search"]
"""A root or page each link's detail opens over: every tab, two More pages, search."""


@pytest.mark.parametrize("base", DRILL_BASES)
async def test_a_session_link_opens_the_session_over_its_page(
    open_at: Open, base: str
) -> None:
    """``<page>/session/<id>``, its id quoted, shows that session over the page.

    The id reaches its screen whole, and Back walks the stack down one View at a time.
    """
    location = f"{base}/session/{quote(QUOTED, safe='')}"
    shown = await open_at(location)
    assert shown.routes()[-1] == location
    assert title_of(shown, "session.title") == DATA.sessions[QUOTED].name
    assert await walked(shown) == walk_down(location)


async def test_the_issue_s_link_shows_the_session_over_the_schedule(
    open_at: Open,
) -> None:
    """``/schedule/session/31``: the session over Schedule; Back to it, then Now."""
    shown = await open_at("/schedule/session/31")
    assert shown.routes() == ["/", "/schedule/session/31"]
    assert title_of(shown, "session.title") == DATA.sessions["31"].name
    assert await walked(shown) == ["/schedule", "/now", EXIT]


@pytest.mark.parametrize(
    ("location", "state"),
    [
        ("/schedule/session/nope", "session.not_found"),
        ("/now/speaker/nope", "speaker.not_found"),
        ("/map/room/nope", "room.not_found"),
        ("/more/tracks/nope", "track.not_found"),
        (f"/schedule/session/{quote('a/b c', safe='')}", "session.not_found"),
    ],
)
async def test_an_unknown_id_shows_its_not_found_state_over_its_root(
    open_at: Open, location: str, state: str
) -> None:
    """An id the feed lacks shows its detail's not-found state, pushed (D-186).

    So Back lands on the page below, never out of the app.
    """
    shown = await open_at(location)
    assert shown.routes()[-1] == location
    assert shown.has(state)
    assert await walked(shown) == walk_down(location)


async def test_an_unknown_path_is_one_view_whose_back_goes_to_now(
    open_at: Open,
) -> None:
    """A path the app lacks is ``NotFound`` alone, and Back goes to Now (D-270)."""
    shown = await open_at("/schedule/nope/31")
    assert shown.routes() == ["/"]
    assert shown.has("app.not_found")
    assert await walked(shown) == ["/now", EXIT]


# ------------------------------------------------------------------ warm


@pytest.mark.parametrize(
    "start",
    [
        "/now",
        "/more/developer",
        "/map/room/grand-ballroom-a",
        "/search?scope=rooms",
        "/schedule/session/31/speaker/32",
        "/nope",
    ],
)
async def test_a_warm_link_builds_the_stack_a_cold_one_does(
    open_at: Open, start: str
) -> None:
    """Wherever the app is, search included, a link builds the target's whole stack.

    The same Views a cold start at the link builds, and the same walk down.
    """
    link = "/more/tracks/ai/session/31"
    shown = await open_at(start)
    await shown.go(link)
    assert shown.routes() == ["/", "/more/tracks", "/more/tracks/ai", link]
    assert title_of(shown, "session.title") == DATA.sessions["31"].name
    assert await walked(shown) == walk_down(link)


async def test_a_link_after_back_on_now_lands_in_the_same_process(
    open_at: Open,
) -> None:
    """After Back on Now (F29), a link starts a new session at its own route.

    The process's ``ViewMemory`` says Now, the last location, but a link never goes
    through ``Start`` (D-143): it opens the target with its root below.
    """
    memory = ViewMemory()
    first = await open_at("/now", memory=memory)
    assert await first.back() == EXIT
    assert memory.last_location == "/now"
    shown = await open_at("/map/room/grand-ballroom-a", memory=memory)
    assert shown.routes() == ["/", "/map/room/grand-ballroom-a"]
    assert shown.has("room.title") or shown.has("room.day_tab.0")
    assert await walked(shown) == ["/map", "/now", EXIT]


# ------------------------------------------------------------------ view options


async def test_a_link_s_query_is_a_view_option_that_back_drops(open_at: Open) -> None:
    """A query reaches the top View only, as an option; Back leaves it behind."""
    shown = await open_at("/search?scope=rooms")
    assert shown.node("search.scope.rooms").content.selected  # pyright: ignore
    assert shown.routes() == ["/", "/search"]  # Start below a cold /search (D-164)
    assert await walked(shown) == ["/now", EXIT]

    shown = await open_at("/schedule/session/31?highlight=31&scope=rooms")
    assert await shown.back() == "/schedule"  # no query on the way down


async def test_a_link_to_search_returns_to_the_page_it_opened_over(
    open_at: Open,
) -> None:
    """A link to search starts an empty search whose Back returns where it landed.

    An earlier search opened from the Schedule left its opener and query in the
    process's memory; the link has no Search button to replace them (D-291).
    """
    memory = ViewMemory(search_base="/schedule", search_query="typing")
    shown = await open_at("/map", memory=memory)
    await shown.go("/search?scope=rooms")
    assert shown.routes() == ["/", "/search"]
    assert shown.find(ft.TextField)[0].value == ""
    assert await walked(shown) == ["/map", "/now", EXIT]


async def test_a_link_to_a_result_under_search_returns_through_search(
    open_at: Open,
) -> None:
    """A link to ``/search/session/<id>`` walks back through search to its page.

    Search, built below the result, keeps the remembered query (D-193).
    """
    memory = ViewMemory(search_base="/schedule", search_query="typing")
    shown = await open_at("/map", memory=memory)
    await shown.go("/search/session/31")
    assert shown.routes() == ["/", "/search", "/search/session/31"]
    assert shown.find(ft.TextField)[0].value == "typing"
    assert await walked(shown) == ["/search", "/map", "/now", EXIT]
