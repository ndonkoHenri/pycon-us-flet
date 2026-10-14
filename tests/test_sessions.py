"""Tests for the screen harness itself: ``tests/sessions.py``'s ``showing()`` (#253).

A test may open several screens at once (the Tracks tests do, through an
``AsyncExitStack``). What each one records, its row bodies (D-153) and its titles, and
the View path it reads, must be its own: a second screen must not chain its records
through the first one's (#287's review).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from types import ModuleType

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.favorites import use_favorites
from pycon_us.state import Conference
from tests.feeds import processed
from tests.row_sessions import LIST, TALK, Owner
from tests.sessions import Shown, showing

YEAR = load_year(2026)

probe = ModuleType("probe")
"""A screen's module, whose ``AppScaffold`` ``showing()`` replaces."""


def AppScaffold(**_: object) -> ft.Control:
    """The probe's own scaffold, which no test reaches."""
    raise AssertionError("showing() replaces it")


probe.AppScaffold = AppScaffold  # pyright: ignore[reportAttributeAccessIssue]


@ft.component
def Screen(title: str) -> ft.Control:
    """A screen as the app writes one: a scaffold over memoised rows, at its View path.

    It subscribes to the favorites, so a star tap re-renders it and its scaffold.
    """
    saved = len(use_favorites().ids)
    return probe.AppScaffold(
        title=f"{title} at {ft.use_view_path()}, {saved} saved", body=Owner(LIST)
    )


type Open = Callable[[str], Awaitable[Shown]]


@pytest.fixture
async def open_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Open]:
    """Return open(name): a ``Screen(name)`` at ``/<name>``, open until the test ends."""
    async with AsyncExitStack() as stack:

        async def open_(name: str) -> Shown:
            (tmp_path / name).mkdir()
            return await stack.enter_async_context(
                showing(
                    lambda: Screen(name),
                    probe,
                    year=YEAR,
                    conference=Conference(
                        data=processed(2026), source="bundled", version=1
                    ),
                    tmp_path=tmp_path / name,
                    monkeypatch=monkeypatch,
                    view_path=f"/{name}",
                )
            )

        yield open_


async def tap_star(shown: Shown, session_id: str) -> None:
    star = shown.node(f"test.favorite.{session_id}").content
    assert isinstance(star, ft.IconButton)
    await shown.click(star)


async def test_each_open_screen_counts_only_its_own_row_bodies(
    open_screen: Open,
) -> None:
    first = await open_screen("first")
    second = await open_screen("second")
    assert sorted(first.rows) == sorted(LIST)
    assert sorted(second.rows) == sorted(LIST)

    first.rows.clear()
    second.rows.clear()
    await tap_star(second, TALK)
    assert (first.rows, second.rows) == ([], [TALK])

    second.rows.clear()
    await tap_star(first, TALK)
    assert (first.rows, second.rows) == ([TALK], [])


async def test_each_open_screen_has_its_own_titles_and_view_path(
    open_screen: Open,
) -> None:
    first = await open_screen("first")
    second = await open_screen("second")
    assert first.titles == ["first at /first, 0 saved"]
    assert second.titles == ["second at /second, 0 saved"]

    await tap_star(first, TALK)
    assert first.titles == ["first at /first, 0 saved", "first at /first, 1 saved"]
    assert second.titles == ["second at /second, 0 saved"]
