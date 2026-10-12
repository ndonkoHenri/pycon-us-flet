"""Tests for the route table and the location helpers (SHELL-03, SHELL-04; D-17, D-19).

Locations are matched with the Router's own matcher (``_match_routes`` and
``_split_chain_into_view_levels`` in ``flet/components/router.py``, internal), as S4's
``check_routes.py`` did, so a Flet bump that changes matching fails here first. The
screens themselves are checked on devices (the PR).
"""

import inspect
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
    drill_href,
    is_top_view,
    parent_of,
    query_of,
    start_target,
)
from pycon_us.routes import DRILL, ROUTES

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
        ("/now", ["Now"]),
        ("/schedule", ["Schedule"]),
        ("/my-schedule", ["MySchedule"]),
        ("/map", ["Map"]),
        ("/more", ["More"]),
        ("/more/speakers", ["More", "Speakers"]),
        ("/more/tracks", ["More", "MorePage"]),
        ("/more/tracks/python", ["More", "MorePage", "Track"]),
        ("/more/app", ["More", "MorePage"]),
        ("/more/developer", ["More", "MorePage"]),
        ("/search", ["Search"]),
        ("/search/speaker/17/session/42", ["Search", "Drill", "Drill"]),
        (
            "/more/speakers/speaker/17/session/42",
            ["More", "Speakers", "Drill", "Drill"],
        ),
        ("/more/tracks/python/session/42", ["More", "MorePage", "Track", "Drill"]),
        ("/map/room/hall-a/plan/expo", ["Map", "Drill", "Drill"]),
        ("/now/sponsor/acme", ["Now", "Drill"]),
    ],
)
def test_every_route_shape_stacks_its_screens(
    location: str, screens: list[str]
) -> None:
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
    assert drill_params(location) == levels


@pytest.mark.parametrize(
    "location",
    ["/now/bogus/1", "/now/session", "/more/staff/lead", "/welcome", "/schedule/x"],
)
def test_an_unknown_location_matches_nothing_so_the_router_shows_not_found(
    location: str,
) -> None:
    assert _match_routes(ROUTES, location) is None


def test_the_drill_takes_every_kind_and_nothing_else() -> None:
    assert DRILL.path == ":kind(session|speaker|room|sponsor|plan)/:ident"
    assert [kind for kind, _ in drill_params(f"/now/{'/1/'.join(DRILL_KINDS)}/1")] == [
        *DRILL_KINDS
    ]


DRILL_SCREENS = {
    "session": ("SessionDetail", "session_id"),
    "speaker": ("SpeakerDetail", "speaker_id"),
    "room": ("RoomDetail", "room_slug"),
    "sponsor": ("SponsorDetail", "sponsor_slug"),
    "plan": ("PlanViewer", "plan_id"),
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
    name, argument = DRILL_SCREENS[kind]
    assert drill_screen(monkeypatch, kind) == (name, {argument: "a/b"})


def test_a_drill_kind_without_a_screen_is_an_error_not_another_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="'poster'"):
        drill_screen(monkeypatch, "poster")


def page_paths(routes: list, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for route in routes:
        if route is DRILL or route.index:
            continue
        path = f"{prefix}/{route.path}"
        paths |= {path, *page_paths(route.children or [], path)}
    return paths


def test_pages_lists_every_page_of_the_route_table_without_a_parameter() -> None:
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
        ("/more/staff/lead", "/more"),  # /more/staff is not a page
        ("/map/room/hall-a/plan/expo", "/map/room/hall-a"),
        ("/now/session/poster%20detail%2B1", "/now"),
        ("/now/session/42?highlight=99", "/now"),  # the query is dropped
        ("/schedule", "/"),
        ("/now", "/"),
    ],
)
def test_back_goes_one_step_up(location: str, parent: str) -> None:
    assert parent_of(location) == parent


def test_back_from_search_results_walks_back_through_search_to_its_opener() -> None:
    base = "/map/room/hall-a?highlight=42"  # the opener, its query kept (D-19)
    result = "/search/speaker/17/session/42"
    assert parent_of(result, base) == "/search/speaker/17"
    assert parent_of("/search/speaker/17", base) == "/search"
    assert parent_of("/search", base) == base
    assert parent_of("/search?scope=rooms", base) == base


# ------------------------------------------------------------------ links


def test_drill_href_quotes_the_whole_id_into_one_segment() -> None:
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
    path = location.split("?")[0].rstrip("/") or "/"
    paths = [view_path for _, view_path, _ in view_levels(path)]
    assert [is_top_view(location, view_path) for view_path in paths] == [
        *[False] * (len(paths) - 1),
        True,
    ]


@pytest.mark.parametrize("below", ["/map", "/schedule/session/42", "/"])
def test_under_the_global_search_only_search_is_the_top_view(below: str) -> None:
    # The Router renders the Views below a global modal at the opener's location, or
    # at "/" (Start) when /search is entered directly; neither is the top View.
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
    assert start_target(last_location, "/schedule/session/42") == target
