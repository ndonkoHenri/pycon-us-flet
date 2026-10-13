"""Tests for the not-found states of the detail stubs and the Router's ``NotFound`` (#83).

Session and room detail's own states are tested with their screens
(``test_session.py``, #90; ``test_room.py``, #101).

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
from pycon_us.favorites import Favorites
from pycon_us.screens import speaker
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
            speaker,
            "SpeakerDetail",
            "This speaker isn't in the current schedule",
            "All speakers",
            "/more/speakers",
            "speaker.not_found",
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
    if hasattr(module, "use_session_views"):  # the stubs' session rows (#81)
        monkeypatch.setattr(
            module,
            "use_services",
            lambda: SimpleNamespace(
                year=SimpleNamespace(conference=SimpleNamespace(zone=None))
            ),
        )
        monkeypatch.setattr(module, "use_favorites", Favorites)
        monkeypatch.setattr(module, "use_favorite_toggle", lambda favorites: None)
        monkeypatch.setattr(module, "use_tokens", lambda: None)
        monkeypatch.setattr(module, "use_session_views", lambda *_, **__: ())
        monkeypatch.setattr(
            module, "use_conference", lambda: SimpleNamespace(data=empty, version=0)
        )
        monkeypatch.setattr(ft, "use_memo", lambda fn, deps: fn())
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
