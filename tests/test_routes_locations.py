"""Tests for the location helpers (SHELL-04; D-17, D-19, D-287).

Back, a drill's link, a location's view options, which View is the top one, and where
a new session starts. The route table itself is tested in ``test_routes.py``; both read
a location's Views with ``tests/route_levels.py``.
"""

import inspect
from collections.abc import Callable
from types import SimpleNamespace

import flet as ft
import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycon_us import routes
from pycon_us.account import Account
from pycon_us.locations import (
    DRILL_KINDS,
    WELCOME,
    drill_href,
    is_top_view,
    launch_target,
    parent_of,
    query_of,
    start_target,
)
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.theme import BOOT_COLOR
from tests.fake_page import FakePage, bound
from tests.route_levels import drill_params, view_levels

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
        ("/now/staff/lead", "/now"),  # from Now's card, to Now (D-421)
        ("/more/staff/door/session", "/more/staff/door"),  # the picker, to the tool
        ("/now/staff/door/session", "/now/staff/door"),
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
    assert parent_of("/search?scope=places", base) == base


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
        ("/search?scope=places", {"scope": "places"}),
        ("/search", {}),
        ("/more/sponsors/sponsor/acme/plan/expo?booth=613", {"booth": "613"}),
        ("/map/plan/level-1?pin=room-102a&booth=", {"pin": "room-102a", "booth": ""}),
        ("/search?scope=all&scope=places", {"scope": "places"}),
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
    assert not is_top_view("/search?scope=places", below)
    assert is_top_view("/search?scope=places", "/search")


# ------------------------------------------------------------------ start


@pytest.mark.parametrize(
    ("last_location", "target"),
    [
        ("", "/now"),
        ("/now", "/now"),
        ("/now/session/42/speaker/17", "/now/session/42/speaker/17"),
        ("/map/room/hall-a?highlight=42", "/map/room/hall-a?highlight=42"),
        ("/search?scope=places", "/schedule/session/42"),  # a modal goes to its opener
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
    ["", "/now", "/now/session/42", "/search?scope=places", "/more/developer"],
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
    monkeypatch.setattr(
        routes,
        "use_services",
        lambda: SimpleNamespace(memory=memory, reminders=None),
    )
    monkeypatch.setattr(routes, "use_prefs", lambda: Prefs(onboarded=onboarded))
    monkeypatch.setattr(routes, "use_account", Account)  # signed out
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


TAP = "/my-schedule/session/142"
"""A session reminder's route, its tap's target (D-396)."""


@pytest.mark.parametrize(
    ("tap", "last_location", "onboarded", "target"),
    [
        (TAP, "/now/session/42", True, TAP),  # the tap wins over where the user was
        ("", "/now/session/42", True, "/now/session/42"),  # no tap: start_target()
        (TAP, "", False, TAP),  # first run: Welcome waits for a plain start
        ("", "", False, WELCOME),
        (TAP, "/search?scope=places", True, TAP),  # over a last location in search
        ("", "/search?scope=places", True, "/schedule/session/42"),
    ],
)
def test_a_reminder_tap_wins_over_every_start_target(
    tap: str, last_location: str, onboarded: bool, target: str
) -> None:
    """A tapped reminder opens its route whatever else the start would pick (D-396).

    Without one, the start goes where ``start_target()`` says: Welcome, the last
    location, or search's opener.
    """
    assert (
        launch_target(tap, last_location, "/schedule/session/42", onboarded=onboarded)
        == target
    )


def test_start_opens_the_held_tap_and_takes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Start`` takes the ``Scheduler``'s held tap and goes there, even on a first run."""
    memory = ViewMemory(last_location="/now/session/42")
    reminders = SimpleNamespace(tapped=TAP)

    def take_tap() -> str:
        """Hand over the held tap once, as ``Scheduler.take_tap()`` does."""
        route, reminders.tapped = reminders.tapped, ""
        return route

    reminders.take_tap = take_tap
    effects: list[Callable[[], None]] = []
    monkeypatch.setattr(
        routes,
        "use_services",
        lambda: SimpleNamespace(memory=memory, reminders=reminders),
    )
    monkeypatch.setattr(routes, "use_prefs", lambda: Prefs(onboarded=False))
    monkeypatch.setattr(routes, "use_account", Account)  # signed out
    monkeypatch.setattr(
        ft, "use_effect", lambda setup, deps=None: effects.append(setup)
    )
    page = FakePage()
    with bound(page):
        inspect.unwrap(routes.Start)()
        (go,) = effects
        go()
    assert page.navigated == [TAP]
    assert reminders.tapped == ""
