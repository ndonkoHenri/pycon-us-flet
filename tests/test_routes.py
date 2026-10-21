"""Tests for the route table and the location helpers (SHELL-03, SHELL-04; D-17, D-19).

Locations are matched with the Router's own matcher (``_match_routes`` and
``_split_chain_into_view_levels`` in ``flet/components/router.py``, internal), as S4's
``check_routes.py`` did, so a Flet bump that changes matching fails here first. The
screens themselves are checked on devices (the PR).
"""

import inspect
from collections.abc import Callable
from types import SimpleNamespace
from urllib.parse import unquote

import flet as ft
import pytest
from flet.components.router import _match_routes, _split_chain_into_view_levels
from hypothesis import given
from hypothesis import strategies as st

from pycon_us import routes
from pycon_us.locations import (
    DRILL_KINDS,
    PAGES,
    TAB_ROOTS,
    WELCOME,
    drill_href,
    is_top_view,
    parent_of,
    query_of,
    start_target,
)
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.routes import DRILL, ROUTES, UNKNOWN
from pycon_us.theme import BOOT_COLOR
from tests.fakes import FakePage, bound

type Level = tuple[str, str, dict[str, str]]


def view_levels(location: str) -> list[Level]:
    """Each View the Router stacks for location: its screen, path and own params.

    The Router gives a level the params accumulated up to it, so a drill level's
    ``kind`` and ``ident`` are its own pair's (F6).
    """
    chain = _match_routes(ROUTES, location)
    assert chain is not None, f"no route matches {location}"
    _, entries = _split_chain_into_view_levels(chain)
    levels = []
    for match, _ in entries:
        params: dict[str, str] = {}
        for m in chain[: chain.index(match) + 1]:
            params.update(m.params)
        screen = match.route.component
        assert screen is not None  # a View level always has a component
        levels.append((screen.__name__, match.resolved_path, params))
    return levels


def drill_params(location: str) -> list[tuple[str, str]]:
    """The (kind, unquoted id) each drill level of location sees, in order."""
    return [
        (params["kind"], unquote(params["ident"]))
        for name, _, params in view_levels(location)
        if name == "Drill"
    ]


# ------------------------------------------------------------------ matching


def test_a_drill_chain_builds_one_view_per_level_with_its_own_params() -> None:
    """A chain of drills stacks one View per level, each with its own kind and id."""
    assert view_levels("/schedule/session/42/speaker/17/session/99") == [
        ("Schedule", "/schedule", {}),
        ("Drill", "/schedule/session/42", {"kind": "session", "ident": "42"}),
        (
            "Drill",
            "/schedule/session/42/speaker/17",
            {"kind": "speaker", "ident": "17"},
        ),
        (
            "Drill",
            "/schedule/session/42/speaker/17/session/99",
            {"kind": "session", "ident": "99"},
        ),
    ]


@pytest.mark.parametrize(
    ("location", "screens"),
    [
        ("/", ["Start"]),
        ("/welcome", ["Welcome"]),
        ("/now", ["Now"]),
        ("/schedule", ["Schedule"]),
        ("/my-schedule", ["MySchedule"]),
        ("/map", ["Map"]),
        ("/more", ["More"]),
        ("/more/speakers", ["More", "Speakers"]),
        ("/more/tracks", ["More", "Tracks"]),
        ("/more/tracks/python", ["More", "Tracks", "TrackPage"]),
        ("/more/lightning-talks", ["More", "LightningTalks"]),
        ("/more/open-spaces", ["More", "OpenSpaces"]),
        ("/more/sprints", ["More", "Sprints"]),
        # The hub's rows open the same pages over the hub (D-207), not TrackPage.
        ("/more/tracks/sprints", ["More", "Tracks", "Sprints"]),
        ("/more/tracks/lightning-talks", ["More", "Tracks", "LightningTalks"]),
        ("/more/tracks/open-spaces", ["More", "Tracks", "OpenSpaces"]),
        ("/more/tracks/keynotes", ["More", "Tracks", "Keynotes"]),
        (
            "/more/tracks/open-spaces/session/42",
            ["More", "Tracks", "OpenSpaces", "Drill"],
        ),
        ("/more/sponsors", ["More", "Sponsors"]),
        ("/more/sponsors/sponsor/bloomberg", ["More", "Sponsors", "Drill"]),
        ("/more/jobs", ["More", "Jobs"]),
        ("/more/jobs/sponsor/bloomberg", ["More", "Jobs", "Drill"]),
        ("/more/settings", ["More", "Settings"]),
        ("/more/app", ["More", "AboutApp"]),
        ("/more/app/licences", ["More", "AboutApp", "Licences"]),
        ("/more/app/licences/flet", ["More", "AboutApp", "Licences", "LicencePage"]),
        ("/more/developer", ["More", "Developer"]),
        ("/more/social", ["More", "Social"]),
        ("/more/about", ["More", "AboutPycon"]),
        # Its rows open the same pages over it (D-207's pattern).
        ("/more/about/help", ["More", "AboutPycon", "Help"]),
        ("/more/about/venue", ["More", "AboutPycon", "Venue"]),
        ("/search", ["Search"]),
        ("/search/speaker/17/session/42", ["Search", "Drill", "Drill"]),
        (
            "/more/speakers/speaker/17/session/42",
            ["More", "Speakers", "Drill", "Drill"],
        ),
        ("/more/tracks/python/session/42", ["More", "Tracks", "TrackPage", "Drill"]),
        ("/map/room/hall-a/plan/expo", ["Map", "Drill", "Drill"]),
        ("/now/sponsor/acme", ["Now", "Drill"]),
    ],
)
def test_every_route_shape_stacks_its_screens(
    location: str, screens: list[str]
) -> None:
    """Each route shape stacks the screens it names, from the tab root up."""
    assert [name for name, _, _ in view_levels(location)] == screens


@pytest.mark.parametrize(
    ("location", "levels"),
    [
        (
            "/now/session/42/speaker/17/session/99/room/room-102a",
            [
                ("session", "42"),
                ("speaker", "17"),
                ("session", "99"),
                ("room", "room-102a"),
            ],
        ),
        (
            "/now/session/poster%20detail%2B1/speaker/%C3%A7~31/session/7",
            [("session", "poster detail+1"), ("speaker", "ç~31"), ("session", "7")],
        ),
        (
            "/schedule/session/break--2026-05-13T12%3A30%3A00-07%3A00",
            [("session", "break--2026-05-13T12:30:00-07:00")],
        ),
        ("/more/tracks/session/42", [("session", "42")]),  # a drill, not a track
        ("/search/speaker/17/session/42", [("speaker", "17"), ("session", "42")]),
    ],
)
def test_each_drill_level_reads_its_own_pair(
    location: str, levels: list[tuple[str, str]]
) -> None:
    """Each drill level reads its own kind and unquoted id, whatever came before."""
    assert drill_params(location) == levels


@pytest.mark.parametrize(
    "location",
    [
        "/nope",
        "/now/bogus/1",
        "/now/session",
        "/now/session/42/nope",
        "/more/staff/lead",
        "/more/tracks/python/x",
        "/search/nope",
        "/welcome/session/42",  # Welcome has no drill: nothing opens over it
        "/schedule/x",
    ],
)
def test_an_unknown_location_is_one_not_found_view(location: str) -> None:
    """A location no page or drill matches is the catch-all's one View (D-270).

    Nothing below it: Back on it goes to Now, never out of the app.
    """
    assert view_levels(location) == [("NotFound", location, {"unknown": location[1:]})]


def test_the_catch_all_is_the_table_s_last_route() -> None:
    """The catch-all comes last: the Router tries routes in order, and it takes any."""
    assert ROUTES[-1] is UNKNOWN
    assert UNKNOWN.component is routes.NotFound
    assert UNKNOWN not in ROUTES[:-1]


def known_locations() -> list[str]:
    """Every page, and a drill of each kind on every page, quoted ids included."""
    return [
        *sorted(PAGES),
        *(
            drill_href(drill_href(page, kind, "a/b ç"), "session", "42")
            for page in sorted(PAGES - {WELCOME})  # the one page without a drill
            for kind in DRILL_KINDS
        ),
        "/more/tracks/python",  # the slug route
        "/more/app/licences/flet",  # the key route
        "/more/tracks/python/room/hall-a",
    ]


@pytest.mark.parametrize("location", known_locations())
def test_the_catch_all_matches_no_page_and_no_drill(location: str) -> None:
    """Every page and every drill still opens its own screens, never ``NotFound``."""
    screens = [name for name, _, _ in view_levels(location)]
    assert "NotFound" not in screens


def test_the_drill_takes_every_kind_and_nothing_else() -> None:
    """The drill's path accepts exactly the drill kinds, each matched in order."""
    assert DRILL.path == ":kind(session|speaker|room|sponsor|plan|changes)/:ident"
    assert [kind for kind, _ in drill_params(f"/now/{'/1/'.join(DRILL_KINDS)}/1")] == [
        *DRILL_KINDS
    ]


DRILL_SCREENS = {
    "session": ("SessionDetail", "session_id"),
    "speaker": ("SpeakerDetail", "speaker_id"),
    "room": ("RoomDetail", "room_slug"),
    "sponsor": ("SponsorDetail", "sponsor_slug"),
    "plan": ("PlanViewer", "plan_id"),
    "changes": ("ScheduleChanges", "year"),
}


def drill_screen(monkeypatch: pytest.MonkeyPatch, kind: str) -> object:
    """What ``Drill``'s body returns for a level of kind with the quoted id ``a%2Fb``.

    The body runs without a renderer: the params hook and the screens are stand-ins,
    each screen returning its own name and keyword arguments.
    """
    params = {"kind": kind, "ident": "a%2Fb"}
    monkeypatch.setattr(ft, "use_route_params", lambda: params)
    for name, _ in DRILL_SCREENS.values():
        monkeypatch.setattr(routes, name, lambda _name=name, **kw: (_name, kw))
    return inspect.unwrap(routes.Drill)()  # the body, without @ft.component


@pytest.mark.parametrize("kind", DRILL_KINDS)
def test_each_drill_kind_opens_its_own_screen_with_the_unquoted_id(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Each drill kind opens its own screen, given the id unquoted."""
    name, argument = DRILL_SCREENS[kind]
    assert drill_screen(monkeypatch, kind) == (name, {argument: "a/b"})


def test_the_expo_plan_opens_the_expo_hall(monkeypatch: pytest.MonkeyPatch) -> None:
    """``…/plan/expo`` is ``ExpoPlan``, the expo hall with its booths (EXPO-01)."""
    monkeypatch.setattr(
        ft, "use_route_params", lambda: {"kind": "plan", "ident": "expo"}
    )
    monkeypatch.setattr(routes, "ExpoPlan", lambda: "ExpoPlan")
    assert inspect.unwrap(routes.Drill)() == "ExpoPlan"


def test_a_drill_kind_without_a_screen_is_an_error_not_another_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A drill kind with no screen raises ``ValueError`` naming it."""
    with pytest.raises(ValueError, match="'poster'"):
        drill_screen(monkeypatch, "poster")


def page_paths(routes: list, prefix: str = "") -> set[str]:
    """Return the path of every page under ``routes``, joined to ``prefix``.

    Index routes and the drill are skipped; a path may still hold a parameter.
    """
    paths: set[str] = set()
    for route in routes:
        if route is DRILL or route.index:
            continue
        path = f"{prefix}/{route.path}"
        paths |= {path, *page_paths(route.children or [], path)}
    return paths


def test_pages_lists_every_page_of_the_route_table_without_a_parameter() -> None:
    """``PAGES`` is every route without a parameter, and holds every tab root."""
    assert {path for path in page_paths(ROUTES) if ":" not in path} == PAGES
    assert set(TAB_ROOTS) <= PAGES


# ------------------------------------------------------------------ Back


@pytest.mark.parametrize(
    ("location", "parent"),
    [
        ("/now/session/42/speaker/17", "/now/session/42"),
        ("/now/session/42", "/now"),
        (
            "/schedule/session/42/speaker/17/session/99",
            "/schedule/session/42/speaker/17",
        ),
        ("/more/speakers/speaker/17", "/more/speakers"),
        ("/more/speakers", "/more"),
        ("/more/tracks/python", "/more/tracks"),
        ("/more/tracks/python/session/42", "/more/tracks/python"),
        ("/more/tracks/sprints", "/more/tracks"),  # from the hub, to it (D-207)
        ("/more/tracks/lightning-talks", "/more/tracks"),
        ("/more/tracks/open-spaces", "/more/tracks"),
        ("/more/tracks/sprints/session/42", "/more/tracks/sprints"),
        ("/more/sprints", "/more"),  # from More, to it
        ("/more/lightning-talks", "/more"),
        ("/more/sponsors/sponsor/bloomberg", "/more/sponsors"),  # to the list (D-17)
        ("/more/sponsors", "/more"),
        ("/more/jobs/sponsor/bloomberg", "/more/jobs"),  # Back to the list (#399)
        ("/more/jobs", "/more"),
        ("/more/staff/lead", "/more"),  # /more/staff is not a page
        ("/more/app/licences/flet", "/more/app/licences"),  # a text, to the list
        ("/more/app/licences", "/more/app"),  # the list, to About this app (D-296)
        ("/more/about/help", "/more/about"),  # from About PyCon US, to it (#414)
        ("/more/about/venue", "/more/about"),
        ("/more/about", "/more"),
        ("/map/room/hall-a/plan/expo", "/map/room/hall-a"),
        ("/now/session/poster%20detail%2B1", "/now"),
        ("/now/session/42?highlight=99", "/now"),  # the query is dropped
        ("/schedule", "/"),
        ("/now", "/"),
    ],
)
def test_back_goes_one_step_up(location: str, parent: str) -> None:
    """Back goes one step up: one drill level, a page, or a tab root to Start."""
    assert parent_of(location) == parent


def test_back_from_search_results_walks_back_through_search_to_its_opener() -> None:
    """Back from a search result walks back through Search to its opener, query kept."""
    base = "/map/room/hall-a?highlight=42"  # the opener, its query kept (D-19)
    result = "/search/speaker/17/session/42"
    assert parent_of(result, base) == "/search/speaker/17"
    assert parent_of("/search/speaker/17", base) == "/search"
    assert parent_of("/search", base) == base
    assert parent_of("/search?scope=rooms", base) == base


# ------------------------------------------------------------------ links


def test_drill_href_quotes_the_whole_id_into_one_segment() -> None:
    """``drill_href`` quotes the whole id, slashes included, into one path segment."""
    assert drill_href("/now", "session", "poster detail+1") == (
        "/now/session/poster%20detail%2B1"
    )
    assert drill_href("/now/", "speaker", "a/b") == "/now/speaker/a%2Fb"
    assert drill_href("/more/speakers", "speaker", "ç~31") == (
        "/more/speakers/speaker/%C3%A7~31"
    )


VIEW_PATHS = st.sampled_from(
    ["/now", "/schedule/session/42", "/more/speakers", "/more/tracks/python", "/search"]
)


@given(
    view_path=VIEW_PATHS, kind=st.sampled_from(DRILL_KINDS), ident=st.text(min_size=1)
)
def test_any_id_round_trips_through_its_link_and_back(
    view_path: str, kind: str, ident: str
) -> None:
    """Any id reads back whole from its link, whose parent is the View it came from."""
    location = drill_href(view_path, kind, ident)
    assert drill_params(location)[-1] == (kind, ident)
    assert parent_of(location) == view_path


# ------------------------------------------------------------------ view options


@pytest.mark.parametrize(
    ("location", "options"),
    [
        ("/search?scope=rooms", {"scope": "rooms"}),
        ("/search", {}),
        ("/more/sponsors/sponsor/acme/plan/expo?booth=613", {"booth": "613"}),
        ("/map/plan/level-1?pin=room-102a&booth=", {"pin": "room-102a", "booth": ""}),
        ("/search?scope=all&scope=rooms", {"scope": "rooms"}),
        ("/search?q=caf%C3%A9+tables", {"q": "café tables"}),
    ],
)
def test_query_of_reads_the_view_options(location: str, options: dict) -> None:
    """``query_of`` reads a location's options, unquoted, the last of a repeated key."""
    assert query_of(location) == options


# ------------------------------------------------------------------ top View


@pytest.mark.parametrize(
    "location",
    [
        "/schedule/session/42/speaker/17",
        "/map/room/hall-a?highlight=42",
        "/now/session/poster%20detail%2B1",
        "/more/tracks/python/",
        "/search/speaker/17",
        "/",
    ],
)
def test_only_the_last_view_a_location_builds_is_the_top_one(location: str) -> None:
    """Of the Views a location stacks, only the last is the top one."""
    path = location.split("?")[0].rstrip("/") or "/"
    paths = [view_path for _, view_path, _ in view_levels(path)]
    assert [is_top_view(location, view_path) for view_path in paths] == [
        *[False] * (len(paths) - 1),
        True,
    ]


@pytest.mark.parametrize("below", ["/map", "/schedule/session/42", "/"])
def test_under_the_global_search_only_search_is_the_top_view(below: str) -> None:
    """Under the global Search, only Search is the top View.

    The Router renders the Views below a global modal at the opener's location, or at
    "/" (Start) when /search is entered directly; neither is the top View.
    """
    assert not is_top_view("/search?scope=rooms", below)
    assert is_top_view("/search?scope=rooms", "/search")


# ------------------------------------------------------------------ start


@pytest.mark.parametrize(
    ("last_location", "target"),
    [
        ("", "/now"),
        ("/now", "/now"),
        ("/now/session/42/speaker/17", "/now/session/42/speaker/17"),
        ("/map/room/hall-a?highlight=42", "/map/room/hall-a?highlight=42"),
        ("/search?scope=rooms", "/schedule/session/42"),  # a modal goes to its opener
        ("/search/speaker/17", "/schedule/session/42"),
    ],
)
def test_the_start_route_returns_a_new_session_to_where_the_user_was(
    last_location: str, target: str
) -> None:
    """A new session starts where the user was, or on Now when there is no location.

    A location under Search, a modal, goes to the page Search was opened from.
    """
    assert start_target(last_location, "/schedule/session/42", onboarded=True) == target


@pytest.mark.parametrize(
    "last_location",
    ["", "/now", "/now/session/42", "/search?scope=rooms", "/more/developer"],
)
def test_a_plain_start_opens_welcome_until_it_is_done(last_location: str) -> None:
    """Before Get started, every plain start opens Welcome, wherever the user was (D-287).

    A link's target, opened without Welcome, is remembered all the same: Welcome
    waits for the next plain start, and Reset app, which forgets onboarded, lands
    on it from any page.
    """
    assert (
        start_target(last_location, "/schedule/session/42", onboarded=False) == WELCOME
    )


@pytest.mark.parametrize(
    ("onboarded", "target"), [(False, "/welcome"), (True, "/now/session/42")]
)
def test_start_sends_a_plain_start_to_welcome_until_it_is_done(
    monkeypatch: pytest.MonkeyPatch, onboarded: bool, target: str
) -> None:
    """``Start`` reads ``Prefs.onboarded``: Welcome first, then where the user was."""
    memory = ViewMemory(last_location="/now/session/42")
    effects: list[Callable[[], None]] = []
    monkeypatch.setattr(routes, "use_services", lambda: SimpleNamespace(memory=memory))
    monkeypatch.setattr(routes, "use_prefs", lambda: Prefs(onboarded=onboarded))
    monkeypatch.setattr(
        ft, "use_effect", lambda setup, deps=None: effects.append(setup)
    )
    page = FakePage()
    with bound(page):
        view = inspect.unwrap(routes.Start)()
        assert view.route == "/" and view.bgcolor == BOOT_COLOR
        (go,) = effects
        go()
    assert page.navigated == [target]
