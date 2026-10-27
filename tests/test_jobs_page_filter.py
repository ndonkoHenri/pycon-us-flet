"""Tests for the Job listings page's filter (``screens/jobs.py``; SPON-07, #400).

The page runs in ``tests/jobs_view.py``'s harness on the recorded 2026 feed, the
filter's debounce held by ``tests/timers.py``; the matching itself is ``core/jobs.py``'s,
tested in ``tests/test_jobs_search.py``. The cards and the states are
``tests/test_jobs_page.py``'s (#623).
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.prefs import Prefs
from pycon_us.screens import jobs as screen
from pycon_us.state import Conference
from tests import harness, jobs_view
from tests.jobs_view import CARD, DATA, VIEW, YEAR, cards, listing, pause, type_into
from tests.timers import HeldSleeps

show, sleeps, focused = jobs_view.show, jobs_view.sleeps, jobs_view.focused  # fixtures


async def test_the_filter_keeps_the_listings_with_every_word_once_typing_pauses(
    show: Any, sleeps: HeldSleeps
) -> None:
    """SPON-07: "senior python" keeps NVIDIA and marimo, after the 250 ms pause."""
    shown = await show()
    (text_field,) = shown.find(ft.TextField)
    assert text_field.hint_text == screen.FILTER_HINT
    await type_into(shown, "senior python")
    assert len(cards(shown)) == 13  # still typing: the list waits
    assert sleeps.asked[-1] == screen.DEBOUNCE_SECONDS
    await pause(shown, sleeps)
    assert cards(shown) == ["NVIDIA", "marimo"]


async def test_markup_finds_nothing_and_offers_to_clear_the_filter(
    show: Any, sleeps: HeldSleeps, focused: list[ft.TextField]
) -> None:
    """``nofollow`` is in Bloomberg's HTML, not its text: a miss, and Clear filter.

    The button empties the field and the list at once, and puts the focus back in the
    field, since the button goes with the miss (D-182).
    """
    shown = await show()
    await type_into(shown, "nofollow")
    await pause(shown, sleeps)
    assert cards(shown) == []
    assert shown.node("jobs.no_match").live_region
    assert (
        "No roles match \N{LEFT DOUBLE QUOTATION MARK}nofollow"
        "\N{RIGHT DOUBLE QUOTATION MARK}" in shown.texts()
    )
    (button,) = shown.find(ft.FilledTonalButton)
    assert button.content == screen.CLEAR_FILTER
    await shown.click(button)
    assert len(cards(shown)) == 13  # no pause to wait for
    (text_field,) = shown.find(ft.TextField)
    assert text_field.value == ""
    assert [f._i for f in focused] == [text_field._i]


async def test_the_count_is_a_live_region_only_while_the_filter_finds_some(
    show: Any, sleeps: HeldSleeps
) -> None:
    """D-226: "2 listings" read without leaving the field; none unfiltered or on a miss."""
    shown = await show()
    assert shown.nodes("jobs.count") == []
    await type_into(shown, "senior python")
    await pause(shown, sleeps)
    (count,) = shown.nodes("jobs.count")
    assert count.live_region
    assert "2 listings" in shown.texts()
    await type_into(shown, "bloomberg")
    await pause(shown, sleeps)
    assert "1 listing" in shown.texts()
    await type_into(shown, "rust")
    await pause(shown, sleeps)
    assert shown.nodes("jobs.count") == []


def in_list(control: ft.BaseControl) -> bool:
    """Return whether ``control`` is mounted inside a ``ListView``: it scrolls."""
    node = control.parent
    while node is not None and not isinstance(node, ft.ListView):
        node = node.parent
    return node is not None


@pytest.mark.parametrize("large_text", [False, True])
async def test_at_large_text_the_field_and_its_count_scroll_with_the_list(
    show: Any, sleeps: HeldSleeps, large_text: bool
) -> None:
    """Pinned over the list; at large text they head it and scroll away (#649).

    Pinned, the strip, the field and the count took half the screen at the largest
    sizes. In the list or not, the count comes without rebuilding the field (D-243).
    """
    shown = await show(prefs=Prefs(loaded=True, time_above=large_text))
    (text_field,) = shown.find(ft.TextField)
    assert in_list(text_field) is large_text
    await type_into(shown, "senior python")
    await pause(shown, sleeps)
    (count,) = shown.nodes("jobs.count")
    assert in_list(count) is large_text
    (same,) = shown.find(ft.TextField)
    assert same._i == text_field._i


async def test_a_count_change_keeps_the_typed_text_on_the_field(
    show: Any, sleeps: HeldSleeps
) -> None:
    """D-243: the count changes and the field stays, with what was typed last.

    The list catching up after the pause neither rebuilds the field, which would lose
    its focus, nor sends older text over what was typed since.
    """
    shown = await show()
    await type_into(shown, "senior")
    await type_into(shown, "senior python")
    (text_field,) = shown.find(ft.TextField)
    await pause(shown, sleeps)
    assert cards(shown) == ["NVIDIA", "marimo"]
    (same,) = shown.find(ft.TextField)
    # The same field (Flutter keeps its focus) holding what was typed last.
    assert same._i == text_field._i and same.value == "senior python"


@ft.component
def Detail() -> ft.View:
    """A pushed sponsor detail: its path, so a test can tell it shows."""
    return ft.View(route=ft.use_view_path(), controls=[ft.Text(ft.use_view_path())])


async def test_the_filter_survives_a_sponsor_and_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: HeldSleeps
) -> None:
    """The page stays mounted under a sponsor's detail: Back finds the filter as it was."""
    routes = [
        ft.Route(
            path="more/jobs",
            component=screen.Jobs,
            children=[ft.Route(path="sponsor/:slug", component=Detail)],
        )
    ]
    async with harness.showing(
        lambda: ft.Router(routes, manage_views=True),
        screen,
        year=YEAR,
        conference=Conference(data=DATA, source="bundled", version=1),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path=None,  # a real Router, rendered as the page's Views
        route=VIEW,
    ) as shown:
        page = cast(ft.Page, shown.session.page)

        async def go(location: str) -> None:
            page.route = location
            handler: Any = page.on_route_change  # the Router's own handler
            handler(SimpleNamespace(route=location))
            await shown.settle()

        def navigate(location: str) -> None:
            asyncio.get_running_loop().create_task(go(location))

        monkeypatch.setattr(page, "navigate", navigate)
        await type_into(shown, "senior python")
        await pause(shown, sleeps)
        node = shown.node(f"{CARD}{listing('NVIDIA').id}")
        await shown.click(cast(ft.Control, node.parent))
        assert "/more/jobs/sponsor/nvidia" in shown.texts()

        await go(VIEW)  # Back
        (text_field,) = shown.find(ft.TextField)
        assert text_field.value == "senior python"
        assert cards(shown) == ["NVIDIA", "marimo"]
