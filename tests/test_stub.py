"""Tests for ``NotFound``, the View of an unknown location (#83, #385; D-270).

The details' own not-found states are tested with their screens (``test_session.py``,
#90; ``test_room.py``, #101; ``test_speaker.py``, #99; ``test_tracks.py``, #102).
``AppScaffold``'s Back rules for it are tested in ``test_scaffold.py``, and that the
table's catch-all reaches it only for a location nothing else matches in
``test_routes.py``.

It runs outside a renderer, with ``tests/chrome.py``'s hooks and fake page. Every
empty state names a way out (ux.md §4.6): for a location the app does not have, Now.
"""

import inspect
from collections.abc import Callable
from typing import cast

import flet as ft

from pycon_us import routes
from pycon_us.services import Services
from tests import chrome
from tests.chrome import app_bar, body_of
from tests.fakes import FakePage, Hooks
from tests.trees import descendants, only, texts

# The harness's fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference, hooks = (
    chrome.year,
    chrome.svc,
    chrome.page,
    chrome.conference,
    chrome.hooks,
)


def not_found_at(hooks: Hooks, page: FakePage, location: str) -> ft.View:
    """Build ``NotFound``'s View as the Router does for an unknown location."""
    hooks.view_path = location
    page.route = location
    return inspect.unwrap(routes.NotFound)()


def tap(button: ft.FilledTonalButton) -> None:
    """Call a button's ``on_click``, as a tap does."""
    assert button.on_click is not None
    cast(Callable[[], None], button.on_click)()


def test_an_unknown_location_says_so_without_naming_it_and_offers_now(
    hooks: Hooks, page: FakePage
) -> None:
    """The page says what happened, never echoes the path, and Go to Now goes to Now."""
    view = not_found_at(hooks, page, "/welcome/secret-path")
    body = body_of(view)
    assert texts(body) == [
        "Page not found",
        "This link doesn't open anything in this app.",
    ]
    shown = texts(view) + texts(app_bar(view))
    assert shown and not any("secret-path" in text for text in shown)
    button = only(body, ft.FilledTonalButton)
    assert button.content == "Go to Now"
    tap(button)
    assert page.navigated == ["/now"]


def test_the_state_is_a_live_heading_under_the_page_s_title(
    hooks: Hooks, page: FakePage
) -> None:
    """The bar says "Not found" (level 1); the state's title is a level-2 heading."""
    view = not_found_at(hooks, page, "/nope")
    title = app_bar(view).title
    assert isinstance(title, ft.Semantics) and title.heading_level == 1
    assert isinstance(title.content, ft.Text) and title.content.value == "Not found"
    nodes = [n for n in descendants(body_of(view)) if isinstance(n, ft.Semantics)]
    assert [(n.heading_level, texts(n)) for n in nodes if n.header] == [
        (2, ["Page not found"])
    ]
    live = [n for n in nodes if n.identifier == "app.not_found"]
    assert len(live) == 1 and live[0].live_region is True


def test_an_unknown_location_is_never_where_a_new_session_returns(
    hooks: Hooks, page: FakePage, svc: Services
) -> None:
    """A new session in the process goes back to the last real page, not here (D-143)."""
    svc.memory.last_location = "/schedule/session/42"
    view = not_found_at(hooks, page, "/nope")
    assert view.can_pop is False  # AppScaffold(unknown=True): Back goes to Now
    assert svc.memory.last_location == "/schedule/session/42"
