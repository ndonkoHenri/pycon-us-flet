"""Tests for the route table (SHELL-03, SHELL-04; D-17, D-19).

Locations are matched with the Router's own matcher (``tests/route_levels.py``), as
S4's ``check_routes.py`` did, so a Flet bump that changes matching fails here first.
The location helpers are tested in ``test_routes_locations.py``; the screens
themselves are checked on devices (the PR).
"""

import inspect

import flet as ft
import pytest

from pycon_us import routes
from pycon_us.locations import (
    DRILL_KINDS,
    PAGES,
    TAB_ROOTS,
    WELCOME,
    drill_href,
)
from pycon_us.routes import DRILL, ROUTES, UNKNOWN
from tests.route_levels import drill_params, view_levels

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
