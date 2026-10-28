"""Tests for the info pages' shared body (D-263, INFO-05): ``ui.info_page``.

``InfoBody`` lists a page's blocks from its year data, or hands the page to
``FeedBlock``, which shows the feed's own block or the page's empty state, with no
loader. ``FeedBlock`` runs outside a renderer: its hooks are answered by the test.
"""

import inspect
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.theme_markdown import MARKDOWN_STYLE
from pycon_us.ui import info_page
from pycon_us.ui.info_page import GUTTER, FeedBlock, InfoBody
from pycon_us.ui.states import EmptyState
from pycon_us.ui.widths import READING
from tests.fake_page import FakePage, bound, phone_margin
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed

EMPTY = EmptyState(
    "No Wi-Fi details yet",
    icon=ft.Icons.WIFI_OFF_OUTLINED,
    body="Ask at the information desk.",
    identifier="wifi.empty",
)


@pytest.fixture(scope="module")
def feed_2026() -> ConferenceData:
    """The recorded 2026 feed, processed once for the module: it has a ``wifi`` block."""
    return processed(2026)


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The services with the memory fakes."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def page(svc: Services) -> Iterator[FakePage]:
    """A fake page, bound as Flet binds a session's page, built after the services."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def feed_block(
    monkeypatch: pytest.MonkeyPatch, svc: Services, page: FakePage
) -> Callable[[ConferenceData | None, str], ft.Control]:
    """Render ``FeedBlock`` for the wifi page over a ``Conference`` holding ``data``."""

    def render(data: ConferenceData | None, block: str) -> ft.Control:
        """``FeedBlock``'s body for ``block``, its hooks answered with ``data``."""
        conference = Conference()
        conference.data = data
        monkeypatch.setattr(info_page, "use_services", lambda: svc)
        monkeypatch.setattr(info_page, "use_conference", lambda: conference)
        return inspect.unwrap(FeedBlock)(block, screen="wifi", empty=EMPTY)

    return render


def test_a_page_with_year_data_lists_its_blocks_and_no_feed_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A page's blocks are the body's items, in order, with no feed block among them."""
    monkeypatch.setattr(info_page, "use_margin", phone_margin)
    blocks = [ft.Text("Network"), ft.Text("Password")]
    body = InfoBody(blocks, block="wifi", screen="wifi", empty=EMPTY)
    assert isinstance(body, ft.ListView)
    assert body.expand  # the one list scrolls the whole page
    assert body.controls == blocks


def test_an_info_page_is_capped_at_the_reading_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The body asks for the reading class and puts its margin on the list's sides.

    D-305: in the list's own padding, so the page scrolls from its margins too.
    """
    asked: list[float] = []

    def margin(cap: float) -> float:
        """Record the width class asked for; a tablet's margin for it."""
        asked.append(cap)
        return 283.0

    monkeypatch.setattr(info_page, "use_margin", margin)
    body = InfoBody([ft.Text("Network")], block="wifi", screen="wifi", empty=EMPTY)
    assert asked == [READING]
    assert body.padding == ft.Padding.only(left=283, top=8, right=283, bottom=GUTTER)


def test_a_page_without_year_data_hands_its_body_to_the_feed_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without blocks, the body's one item is ``FeedBlock`` for the page's feed block."""
    monkeypatch.setattr(info_page, "use_margin", phone_margin)
    with Renderer().with_context():  # what calling a component needs, as in a render
        body = InfoBody([], block="wifi", screen="wifi", empty=EMPTY)
    (item,) = body.controls
    assert isinstance(item, ft.Component)
    assert item.fn is inspect.unwrap(FeedBlock)
    assert item.args == ("wifi",)
    assert item.kwargs == {"screen": "wifi", "empty": EMPTY}


def test_the_feed_block_is_the_feed_s_markdown_in_the_gutter(
    feed_block: Callable[[ConferenceData | None, str], ft.Control],
    feed_2026: ConferenceData,
) -> None:
    """The fallback is the feed's block as the app's selectable, linked Markdown, 16 dp in."""
    node = feed_block(feed_2026, "wifi")
    assert isinstance(node, ft.Semantics) and node.identifier == "wifi.feed"
    inset = node.content
    assert isinstance(inset, ft.Container)
    assert inset.padding == ft.Padding.symmetric(horizontal=GUTTER)
    text = inset.content
    assert isinstance(text, ft.Markdown)
    assert text.value == feed_2026.content_md["wifi"]
    assert "PyConUS26" in text.value  # the network the 2026 feed names
    assert text.selectable and text.md_style_sheet is MARKDOWN_STYLE  # D-116
    assert text.on_tap_link is not None  # links open by D-197's rule (feed_markdown())


@pytest.mark.parametrize("blank", ["", "  \n"])
def test_a_blank_feed_block_is_no_block(
    feed_block: Callable[[ConferenceData | None, str], ft.Control],
    feed_2026: ConferenceData,
    blank: str,
) -> None:
    """A block that holds no text shows the page's empty state, not an empty page."""
    data = replace(feed_2026, content_md={**feed_2026.content_md, "wifi": blank})
    assert feed_block(data, "wifi") is EMPTY


def test_a_feed_without_the_block_shows_the_page_s_empty_state(
    feed_block: Callable[[ConferenceData | None, str], ft.Control],
) -> None:
    """2025's feed has no ``wifi`` block: the page shows its empty state."""
    assert feed_block(processed(2025), "wifi") is EMPTY


def test_without_a_feed_the_page_shows_its_empty_state_not_a_loader(
    feed_block: Callable[[ConferenceData | None, str], ft.Control],
) -> None:
    """With no feed on the device yet, the empty state shows at once: no skeleton."""
    assert feed_block(None, "wifi") is EMPTY
