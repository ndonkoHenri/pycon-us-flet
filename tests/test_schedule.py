"""Tests for the Schedule stub without data: skeleton, then "Can't load the schedule" (#83).

``Schedule`` runs outside a renderer, as in ``test_more.py``: its hooks, ``AppScaffold``
and the components it places are replaced, and a fake page is bound as Flet binds a
session's page. P1's real Schedule keeps these states (D-32, ux.md §4.1).
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData
from pycon_us.screens import schedule as screen
from pycon_us.screens import stub
from pycon_us.screens.schedule import Schedule
from tests.fakes import FakePage, bound
from tests.feeds import processed
from tests.trees import descendants, only, texts

SKELETON = ft.Text("skeleton")
"""What the test's ``SkeletonList`` stands in for: the component's own tests check it."""


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def conference() -> SimpleNamespace:
    """The store's fields the screen reads, and a refresh that counts its calls."""
    refreshes: list[str] = []

    async def refresh(*_: Any, **__: Any) -> None:
        refreshes.append("refresh")

    return SimpleNamespace(
        data=None,
        source="none",
        fetched_at=None,
        refreshing=False,
        problem=None,
        refresh=refresh,
        refreshes=refreshes,
    )


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, page: FakePage, conference: SimpleNamespace
) -> Callable[[], list[ft.Control]]:
    """Render ``Schedule`` once and return the rows under the strip and route line."""
    svc = SimpleNamespace(year=load_year(2026), memory=None, storage=None, closed=None)
    monkeypatch.setattr(screen, "use_scroll_to_top", lambda: (ft.Ref(), None))
    monkeypatch.setattr(screen, "use_services", lambda: svc)
    monkeypatch.setattr(screen, "use_conference", lambda: conference)
    monkeypatch.setattr(screen, "search_button", lambda *_: ft.Text("search"))
    monkeypatch.setattr(screen, "SkeletonList", lambda: SKELETON)
    monkeypatch.setattr(screen, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(stub, "StatusStrip", lambda: ft.Text("strip"))
    monkeypatch.setattr(ft, "use_view_path", lambda: "/schedule")
    monkeypatch.setattr(ft, "use_route_params", dict)

    def render() -> list[ft.Control]:
        scaffold = cast(dict[str, Any], inspect.unwrap(Schedule)())
        body = scaffold["body"]
        assert isinstance(body, ft.ListView)
        return list(body.controls)[2:]  # after the strip and the route line

    return render


def test_without_data_the_skeleton_shows_until_the_first_fetch_ends(
    render: Callable[[], list[ft.Control]], conference: SimpleNamespace
) -> None:
    assert render() == [SKELETON]  # the fetch is about to start (NEW-03)
    conference.refreshing = True
    assert render() == [SKELETON]


def test_a_retry_after_a_failed_first_fetch_shows_the_skeleton_again(
    render: Callable[[], list[ft.Control]], conference: SimpleNamespace
) -> None:
    conference.problem, conference.refreshing = "offline", True
    assert render() == [SKELETON]


@pytest.mark.parametrize(
    ("problem", "body"),
    [
        ("offline", "Connect to the internet and try again."),
        ("server", "The schedule couldn't be read. Try again in a few minutes."),
    ],
)
async def test_a_failed_first_fetch_says_so_and_offers_try_again(
    render: Callable[[], list[ft.Control]],
    conference: SimpleNamespace,
    problem: str,
    body: str,
) -> None:
    conference.problem = problem
    (state,) = render()
    assert texts(state) == ["Can't load the schedule", body]
    button = only(state, ft.FilledTonalButton)
    assert button.content == "Try again"
    assert button.on_click is not None
    await cast(Callable[[], Awaitable[None]], button.on_click)()
    assert conference.refreshes == ["refresh"]


def test_with_data_the_stub_shows_its_source_and_days_again(
    render: Callable[[], list[ft.Control]], conference: SimpleNamespace
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
