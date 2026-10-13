"""Tests for the Router's ``NotFound`` (#83).

The details' own not-found states are tested with their screens (``test_session.py``,
#90; ``test_room.py``, #101; ``test_speaker.py``, #99; ``test_tracks.py``, #102).

It runs outside a renderer, with a fake page bound as Flet binds a session's page.
Every empty state names a way out (ux.md §4.6): for a location the app does not have,
Now.
"""

from collections.abc import Callable, Iterator
from typing import cast

import flet as ft
import pytest

from pycon_us import routes
from tests.fakes import FakePage, bound
from tests.trees import only, texts


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


def tap(button: ft.FilledTonalButton) -> None:
    assert button.on_click is not None
    cast(Callable[[], None], button.on_click)()


def test_an_unknown_location_says_where_it_was_and_offers_now(page: FakePage) -> None:
    page.route = "/welcome"
    area = routes.NotFound.__wrapped__()  # type: ignore[attr-defined]
    assert isinstance(area, ft.SafeArea)
    assert texts(area) == ["Page not found", "Nothing in the app is at /welcome."]
    button = only(area, ft.FilledTonalButton)
    assert button.content == "Go to Now"
    tap(button)
    assert page.navigated == ["/now"]
