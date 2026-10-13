"""Tests for the not-found states of the detail stubs and the Router's ``NotFound`` (#83).

They run outside a renderer, with a fake page bound as Flet binds a session's page and
the hooks replaced. Every empty state names a way out (ux.md §4.6): the thing's list,
or Now for a location the app does not have.
"""

import inspect
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import routes
from pycon_us.screens import room, session, speaker
from tests.fakes import FakePage, bound
from tests.trees import descendants, only, texts


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


def tap(button: ft.FilledTonalButton) -> None:
    assert button.on_click is not None
    cast(Callable[[], None], button.on_click)()


@pytest.mark.parametrize(
    ("module", "screen", "title", "action", "location", "identifier"),
    [
        (
            session,
            "SessionDetail",
            "This session isn't in the current schedule",
            "Open schedule",
            "/schedule",
            "session.not_found",
        ),
        (
            speaker,
            "SpeakerDetail",
            "This speaker isn't in the current schedule",
            "All speakers",
            "/more/speakers",
            "speaker.not_found",
        ),
        (
            room,
            "RoomDetail",
            "This room isn't in the current schedule",
            "All rooms",
            "/map",
            "room.not_found",
        ),
    ],
)
def test_an_unknown_id_names_the_thing_and_offers_its_list(
    monkeypatch: pytest.MonkeyPatch,
    page: FakePage,
    module: Any,
    screen: str,
    title: str,
    action: str,
    location: str,
    identifier: str,
) -> None:
    monkeypatch.setattr(ft, "use_view_path", lambda: "/now/x/bogus")
    monkeypatch.setattr(ft, "use_route_params", dict)
    monkeypatch.setattr(module, "AppScaffold", lambda **kwargs: kwargs)
    empty = SimpleNamespace(sessions={}, speakers={}, rooms={})
    monkeypatch.setattr(module, "use_conference", lambda: SimpleNamespace(data=empty))
    if module is session:  # its badges read the year's tracks and the tokens (#181)
        monkeypatch.setattr(
            module,
            "use_services",
            lambda: SimpleNamespace(year=SimpleNamespace(conference=None)),
        )
        monkeypatch.setattr(module, "use_tokens", lambda: None)
    scaffold = cast(dict[str, Any], inspect.unwrap(getattr(module, screen))("bogus"))
    assert scaffold["title"] == "Not found"
    state = scaffold["body"].controls[-1]
    assert texts(state) == [title]
    assert identifier in [
        node.identifier for node in descendants(state) if isinstance(node, ft.Semantics)
    ]
    button = only(state, ft.FilledTonalButton)
    assert button.content == action
    tap(button)
    assert page.navigated == [location]


def test_an_unknown_location_says_where_it_was_and_offers_now(page: FakePage) -> None:
    page.route = "/welcome"
    area = routes.NotFound.__wrapped__()  # type: ignore[attr-defined]
    assert isinstance(area, ft.SafeArea)
    assert texts(area) == ["Page not found", "Nothing in the app is at /welcome."]
    button = only(area, ft.FilledTonalButton)
    assert button.content == "Go to Now"
    tap(button)
    assert page.navigated == ["/now"]
