"""Tests for the Wi-Fi page (`screens/wifi.py`; #410, INFO-08, D-280).

The page runs in a real Flet session (`tests/sessions.py`) over the bundled year data,
with and without a feed. How it looks, wraps at 200 % and reads to screen readers is
checked on devices (the PR).
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.screens import wifi as screen
from pycon_us.state import Conference
from pycon_us.ui.buttons import ICON_PADDING
from tests.fakes import MemoryClipboard
from tests.feeds import processed
from tests.harness import Shown, showing
from tests.sessions import text_of

WIFI = load_year(2026).content.wifi
VIEW = "/more/wifi"

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders the Wi-Fi page for a year, over a feed or none."""
    async with AsyncExitStack() as stack:

        async def render(*, year: int = 2026, feed: int | None = None) -> Shown:
            """Render the page with `year`'s data and `feed`'s feed (None: none yet)."""
            conference = (
                Conference()
                if feed is None
                else Conference(data=processed(feed), source="bundled", version=1)
            )
            return await stack.enter_async_context(
                showing(
                    screen.Wifi,
                    screen,
                    year=load_year(year),
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                )
            )

        yield render


def clipboard(page: Shown) -> MemoryClipboard:
    """The in-memory clipboard the page copies to."""
    return cast(MemoryClipboard, page.services.clipboard)


def control_of[T: ft.Control](node: ft.Semantics, kind: type[T]) -> T:
    """The control a `named()` identifier holds: its `Semantics`' content."""
    assert isinstance(node.content, kind)
    return node.content


def snack_texts(page: Shown) -> list[str]:
    """What the page's SnackBars said, in order."""
    return [text_of(bar.content) for bar in page.snack_bars]


async def test_with_no_feed_the_page_shows_both_values_from_the_year_data(
    show: Show,
) -> None:
    """Offline on a fresh install, before any feed: the bundled values show at once."""
    assert WIFI is not None
    page = await show()
    assert page.titles == [screen.TITLE]
    texts = page.texts()
    for label, text in (
        (screen.NETWORK, WIFI.network),
        (screen.PASSWORD, WIFI.password),
    ):
        assert label in texts and text in texts
    assert not page.nodes("wifi.feed") and not page.nodes("wifi.empty")


@pytest.mark.parametrize(
    ("identifier", "label", "key"),
    [("wifi.network", "Network", "network"), ("wifi.password", "Password", "password")],
)
async def test_each_value_is_one_node_that_says_its_label_then_the_value(
    show: Show, identifier: str, label: str, key: str
) -> None:
    """A screen reader hears "Network, PyConUS26": one node, the texts under it unread."""
    assert WIFI is not None
    text = getattr(WIFI, key)
    node = (await show()).node(identifier)
    assert node.label == f"{label}, {text}"
    assert node.container and node.exclude_semantics
    column = cast(ft.Column, node.content)
    title, value = cast(list[ft.Text], column.controls)
    assert title.value == label
    assert value.value == text


async def test_each_value_is_selectable_monospace_title_large_text(show: Show) -> None:
    """INFO-08: the values can be selected by hand, in a font where l, 1 and I differ."""
    page = await show()
    for identifier in ("wifi.network", "wifi.password"):
        value = cast(
            ft.Text, cast(ft.Column, page.node(identifier).content).controls[1]
        )
        assert value.selectable
        assert value.theme_style is ft.TextThemeStyle.TITLE_LARGE
        assert value.style is screen.VALUE_STYLE
    assert screen.VALUE_STYLE.font_family == "monospace"
    assert screen.VALUE_STYLE.font_family_fallback == ["Menlo"]  # iOS has no alias


async def test_copy_network_copies_the_network_and_says_so_once(show: Show) -> None:
    """Copy beside the network puts the network's name on the clipboard: one SnackBar."""
    assert WIFI is not None
    page = await show()
    button = control_of(page.node("wifi.copy_network"), ft.IconButton)
    assert button.tooltip == "Copy network name"  # it says what it copies
    await page.click(button)
    assert clipboard(page).value == WIFI.network
    assert snack_texts(page) == ["Network name copied"]


async def test_copy_password_copies_the_password_and_says_so_once(show: Show) -> None:
    """The "Copy password" button puts the password on the clipboard: one SnackBar."""
    assert WIFI is not None
    page = await show()
    button = control_of(page.node("wifi.copy_password"), ft.FilledButton)
    assert button.content == "Copy password"  # it says what it copies
    assert button.style is not None  # room above and below a label at large text
    assert button.style.padding == ICON_PADDING
    await page.click(button)
    assert clipboard(page).value == WIFI.password
    assert snack_texts(page) == ["Password copied"]


async def test_the_password_has_one_way_to_copy_it(show: Show) -> None:
    """One Copy per value: the network's button and the password's, nothing else."""
    page = await show()
    assert len(page.find(ft.IconButton)) == 1
    assert len(page.find(ft.FilledButton)) == 1


@pytest.mark.parametrize(
    ("identifier", "said"),
    [
        ("wifi.copy_network", "Couldn't copy the network name"),
        ("wifi.copy_password", "Couldn't copy the password"),
    ],
)
async def test_a_failed_copy_says_so_and_logs_no_value(
    show: Show, caplog: pytest.LogCaptureFixture, identifier: str, said: str
) -> None:
    """A clipboard that fails says what was not copied; the log never holds a value."""
    assert WIFI is not None
    page = await show()
    clipboard(page).error = TimeoutError(f"timed out setting {WIFI.password}")
    with caplog.at_level(logging.WARNING):
        await page.click(cast(ft.Control, page.node(identifier).content))
    assert snack_texts(page) == [said]
    assert [r.getMessage() for r in caplog.records] == [f"{said}: TimeoutError"]
    assert WIFI.password not in caplog.text and WIFI.network not in caplog.text


async def test_a_year_without_wifi_data_shows_the_feed_s_block(show: Show) -> None:
    """2025 has no `[wifi]`: over a feed with a `wifi` block, the page shows it."""
    page = await show(year=2025, feed=2026)
    block = page.node("wifi.feed")
    (text,) = page.find(ft.Markdown)
    assert "PyConUS26" in text.value  # the 2026 feed's block, under its node
    assert cast(ft.Container, block.content).content is text
    assert not page.nodes("wifi.network") and not page.nodes("wifi.empty")


async def test_without_wifi_data_or_a_feed_block_the_page_sends_to_the_desk(
    show: Show,
) -> None:
    """2025's own feed has no `wifi` block: the empty state names the way out."""
    page = await show(year=2025, feed=2025)
    texts = page.texts()
    assert screen.NO_WIFI in texts
    assert screen.NO_WIFI_BODY in texts and "information desk" in screen.NO_WIFI_BODY
    assert page.nodes("wifi.empty")
    assert not page.nodes("wifi.feed")
