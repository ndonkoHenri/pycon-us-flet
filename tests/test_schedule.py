"""Tests for the Schedule stub without data: skeleton, then "Can't load the schedule" (#83).

``Schedule`` runs outside a renderer, as in ``test_more.py``: its hooks, ``AppScaffold``
and the components it places are replaced, and a fake page is bound as Flet binds a
session's page. P1's real Schedule keeps these states (D-32, ux.md §4.1).
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData
from pycon_us.favorites import Favorites
from pycon_us.screens import schedule as screen
from pycon_us.screens import stub
from pycon_us.screens.schedule import Schedule
from pycon_us.state import Conference, Problem
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import states
from tests.fakes import FakePage, bound
from tests.feeds import processed
from tests.trees import descendants, only, texts

PACIFIC = ZoneInfo("America/Los_Angeles")

SKELETON = ft.Text("skeleton")
"""What the test's ``SkeletonList`` stands in for: the component's own tests check it."""


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def refreshes() -> list[str]:
    """One entry per call of the store's ``refresh()``."""
    return []


@pytest.fixture
def conference(monkeypatch: pytest.MonkeyPatch, refreshes: list[str]) -> Conference:
    """A real store, so ``status()`` decides the buttons, with a refresh that counts."""

    async def refresh(*_: Any, **__: Any) -> None:
        refreshes.append("refresh")

    conference = Conference()
    monkeypatch.setattr(conference, "refresh", refresh)
    return conference


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, page: FakePage, conference: Conference
) -> Callable[[], list[ft.Control]]:
    """Render ``Schedule`` once and return the rows under the strip and route line."""
    svc = SimpleNamespace(year=load_year(2026), memory=None, storage=None, closed=None)
    monkeypatch.setattr(screen, "use_scroll_to_top", lambda: (ft.Ref(), None))
    monkeypatch.setattr(screen, "use_services", lambda: svc)
    monkeypatch.setattr(screen, "use_conference", lambda: conference)
    monkeypatch.setattr(screen, "search_button", lambda *_: ft.Text("search"))
    monkeypatch.setattr(states, "SkeletonList", lambda: SKELETON)
    # The sample rows' hooks (#81): the rows themselves are tests/test_session_rows.py's.
    monkeypatch.setattr(screen, "use_favorites", Favorites)
    monkeypatch.setattr(screen, "use_favorite_toggle", lambda favorites: None)
    monkeypatch.setattr(screen, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(screen, "use_session_views", lambda *_, **__: ())
    monkeypatch.setattr(screen, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(stub, "StatusStrip", lambda **_: ft.Text("strip"))
    monkeypatch.setattr(ft, "use_view_path", lambda: "/schedule")
    monkeypatch.setattr(ft, "use_route_params", dict)

    def render() -> list[ft.Control]:
        scaffold = cast(dict[str, Any], inspect.unwrap(Schedule)())
        body = scaffold["body"]
        assert isinstance(body, ft.ListView)
        return list(body.controls)[2:]  # after the strip and the route line

    return render


def test_without_data_the_skeleton_shows_until_the_first_fetch_ends(
    render: Callable[[], list[ft.Control]], conference: Conference
) -> None:
    assert render() == [SKELETON]  # the fetch is about to start (NEW-03)
    conference.refreshing = True
    assert render() == [SKELETON]


def test_a_retry_keeps_the_failed_state_with_its_button_disabled(
    render: Callable[[], list[ft.Control]], conference: Conference
) -> None:
    # The button stays where it was, so a screen reader's focus is not lost.
    conference.problem, conference.refreshing = "offline", True
    conference._asked = True  # the user's retry (D-181)
    (state,) = render()
    assert texts(state)[0] == "Can't load the schedule"
    assert only(state, ft.FilledTonalButton).disabled


def test_try_again_stays_enabled_during_a_quiet_refresh_so_a_tap_joins_it(
    render: Callable[[], list[ft.Control]], conference: Conference
) -> None:
    conference.problem, conference.refreshing = "offline", True  # the 15-min tick
    (state,) = render()
    assert texts(state)[0] == "Can't load the schedule"
    assert not only(state, ft.FilledTonalButton).disabled  # D-181


@pytest.mark.parametrize(("asked", "disabled"), [(False, False), (True, True)])
def test_the_stub_s_refresh_is_disabled_only_while_the_user_s_refresh_runs(
    render: Callable[[], list[ft.Control]],
    conference: Conference,
    asked: bool,
    disabled: bool,
) -> None:
    conference.data, conference.source, conference.problem = (
        processed(2026),
        "bundled",
        "offline",
    )
    conference.refreshing, conference._asked = True, asked  # quiet unless asked
    (refresh,) = (
        button
        for row in render()
        for button in descendants(row)
        if isinstance(button, ft.FilledTonalButton)
    )
    assert refresh.content == "Refresh"
    assert refresh.disabled is disabled  # as the strip's Refresh (D-181)


@pytest.mark.parametrize(
    ("problem", "body"),
    [
        ("offline", "Connect to the internet and try again."),
        ("server", "The schedule couldn't be read. Try again in a few minutes."),
    ],
)
async def test_a_failed_first_fetch_says_so_and_offers_try_again(
    render: Callable[[], list[ft.Control]],
    conference: Conference,
    refreshes: list[str],
    problem: Problem,
    body: str,
) -> None:
    conference.problem = problem
    (state,) = render()
    assert texts(state) == ["Can't load the schedule", body]
    button = only(state, ft.FilledTonalButton)
    assert button.content == "Try again"
    assert not button.disabled
    assert button.on_click is not None
    await cast(Callable[[], Awaitable[None]], button.on_click)()
    assert refreshes == ["refresh"]


def test_with_data_the_stub_shows_its_source_and_days_again(
    render: Callable[[], list[ft.Control]], conference: Conference
) -> None:
    data: ConferenceData = processed(2026)
    conference.data, conference.source, conference.problem = data, "bundled", "offline"
    controls = render()
    assert SKELETON not in controls
    identifiers = [
        node.identifier
        for row in controls
        for node in descendants(row)
        if isinstance(node, ft.Semantics)
    ]
    assert "schedule.source" in identifiers  # never a full-screen error with data
    assert "schedule.no_data" not in identifiers


def test_the_days_mark_today_by_the_clock_so_the_fake_clock_shows(
    render: Callable[[], list[ft.Control]], conference: SimpleNamespace
) -> None:
    conference.data, conference.source = processed(2026), "bundled"

    def marked() -> list[str]:
        return [
            str(row.title)
            for row in render()
            if isinstance(row, ft.ListTile) and str(row.subtitle).endswith("· today")
        ]

    try:
        # The Developer fake clock (D-187); 23:30 in Long Beach is Saturday in UTC.
        clock.start_fake_clock(datetime(2026, 5, 15, 23, 30, tzinfo=PACIFIC))
        assert marked() == ["Fri, May 15"]
        clock.start_fake_clock(datetime(2026, 10, 13, 9, 0, tzinfo=PACIFIC))
        assert marked() == []  # no conference day: nothing is today
    finally:
        clock.start_fake_clock(None)
