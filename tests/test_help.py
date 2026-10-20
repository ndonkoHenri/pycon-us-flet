"""Tests for Help & safety (``/more/help``; INFO-07, INFO-11, D-281).

``Help`` runs outside a renderer: its services and ``AppScaffold`` are replaced, and a
fake page is bound as Flet binds a session's page; the contact rows' component body
runs inline over the same services, as ``test_rows.py`` runs it. What TalkBack and
VoiceOver read, and how the card looks at 200 % text, are checked on devices (the PR).
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.screens import help as help_screen
from pycon_us.screens.help import Help, contact_line, help_blocks
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.ui import rows
from pycon_us.ui.info_page import FeedBlock
from pycon_us.year_info import SafetyContact
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)

HOTLINE = SafetyContact(
    label="Call the Code of Conduct hotline",
    kind="tel",
    value="+15625550100",
    source="https://example.org/coc/",
    checked=date(2026, 10, 20),
)
"""A phone contact no year ships (the 2026 hotline is on no public page, D-45)."""


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services over in-memory fakes and the 2026 year data."""
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
def page(svc: Services, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePage]:
    """A ``FakePage`` (iOS) bound, with the contact rows' body inline over ``svc``."""
    monkeypatch.setattr(
        rows, "_ExternalLinkTile", inspect.unwrap(rows._ExternalLinkTile)
    )
    monkeypatch.setattr(rows, "use_services", lambda: svc)
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, page: FakePage
) -> Callable[[Services], dict[str, Any]]:
    """Render ``Help`` once over the given services and return its scaffold's kwargs."""
    monkeypatch.setattr(help_screen, "AppScaffold", lambda **kwargs: kwargs)

    def render(svc: Services) -> dict[str, Any]:
        """``Help``'s body, its services answered with ``svc``."""
        monkeypatch.setattr(help_screen, "use_services", lambda: svc)
        return cast(dict[str, Any], inspect.unwrap(Help)())

    return render


def blocks_of(scaffold: dict[str, Any]) -> list[ft.Control]:
    """Return the items of the scaffold's ``ListView`` body."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    return list(body.controls)


def card_of(block: ft.Control) -> ft.Card:
    """Return the Report a concern ``Card`` inside its gutter."""
    assert isinstance(block, ft.Container)
    card = block.content
    assert isinstance(card, ft.Card)
    return card


def card_items(block: ft.Control) -> list[ft.Control]:
    """Return what the card holds, top to bottom."""
    column = card_of(block).content
    assert isinstance(column, ft.Column)
    return list(column.controls)


def link_node(row: ft.Control) -> ft.Semantics:
    """Return a link row's merged ``Semantics`` node (its identifier and link flag)."""
    if isinstance(row, ft.Row):  # a phone or email row: the link, then Copy
        holder = row.controls[0]
        assert isinstance(holder, ft.Container) and holder.content is not None
        row = holder.content
    assert isinstance(row, ft.MergeSemantics)
    node = row.content
    assert isinstance(node, ft.Semantics)
    return node


def tile_of(row: ft.Control) -> ft.ListTile:
    """Return a row's ``ListTile``."""
    tile = link_node(row).content
    assert isinstance(tile, ft.ListTile)
    return tile


def copy_node(row: ft.Control) -> ft.Semantics:
    """Return the Copy button's named node beside a phone or email row."""
    assert isinstance(row, ft.Row)
    holder = row.controls[1]
    assert isinstance(holder, ft.Container)
    merged = holder.content
    assert isinstance(merged, ft.MergeSemantics)  # one node with its tooltip (D-234)
    node = merged.content
    assert isinstance(node, ft.Semantics)
    return node


async def click(control: ft.Control) -> None:
    """Await a tile's or a button's ``on_click``, as a tap does."""
    handler = getattr(control, "on_click", None)
    assert handler is not None
    await cast(Callable[[], Awaitable[None]], handler)()


def said(page: FakePage) -> list[str]:
    """The SnackBars' texts, in order."""
    texts = []
    for dialog in page.dialogs:
        assert isinstance(dialog, ft.SnackBar) and isinstance(dialog.content, ft.Text)
        texts.append(str(dialog.content.value))
    return texts


def outline(blocks: list[ft.Control]) -> list[str]:
    """The page as headings (``# ``), the card, row identifiers and the summary."""
    result = []
    for block in blocks:
        if isinstance(block, ft.Semantics) and block.header:
            heading = block.content
            assert isinstance(heading, ft.Container)
            assert isinstance(heading.content, ft.Text)
            result.append(f"# {heading.content.value}")
        elif isinstance(block, ft.Container) and isinstance(block.content, ft.Card):
            result.append("card")
        elif isinstance(block, ft.Semantics):
            result.append(str(block.identifier))
        else:
            result.append(str(link_node(block).identifier))
    return result


def test_the_card_comes_first_then_the_venue_then_the_code_of_conduct(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """After the title, the page reads the card, the places, then the CoC (D-281)."""
    scaffold = render(svc)
    assert scaffold["title"] == "Help & safety"
    assert outline(blocks_of(scaffold)) == [
        "card",
        "# At the venue",
        "help.info_desk",
        "help.lost_and_found",
        "help.quiet_room",
        "# Code of Conduct",
        "help.coc_summary",
        "help.coc",
        "help.procedures",
    ]


def test_the_card_s_first_stop_is_its_level_2_heading(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """A screen reader's first stop after the title is "Report a concern" (F40, D-211)."""
    heading = card_items(blocks_of(render(svc))[0])[0]
    assert isinstance(heading, ft.Semantics)
    assert heading.header and heading.heading_level == 2 and heading.container
    assert heading.identifier == "help.report"
    holder = heading.content
    assert isinstance(holder, ft.Container) and isinstance(holder.content, ft.Row)
    icon, text = holder.content.controls
    assert isinstance(icon, ft.Icon) and icon.semantics_label is None  # decorative
    assert isinstance(text, ft.Text) and text.value == "Report a concern"


def test_the_card_is_outlined_in_error_and_reads_as_its_parts(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """An ``error`` edge, and not one node: the heading, rows and line are stops."""
    card = card_of(blocks_of(render(svc))[0])
    assert card.variant is ft.CardVariant.OUTLINED
    assert isinstance(card.shape, ft.RoundedRectangleBorder)
    assert card.shape.side is not None and card.shape.side.color == ft.Colors.ERROR
    assert card.semantic_container is False  # else one node holds them all (D-211)


def test_2026_s_card_has_the_email_row_then_the_staff_line(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """2026 lists the report email (no public hotline, D-45) and reporting in person."""
    _, row, line = card_items(blocks_of(render(svc))[0])
    node = link_node(row)
    assert node.identifier == "help.report.mailto" and node.link
    tile = tile_of(row)
    # One node read as action plus value.
    assert tile.title == "Email the Code of Conduct team"
    assert tile.subtitle == "pycon-us-report@python.org"
    assert copy_node(row).identifier == "help.copy.mailto"
    assert isinstance(line, ft.Container) and isinstance(line.content, ft.Text)
    assert "staff member" in str(line.content.value)


async def test_the_email_row_copies_its_address(
    render: Callable[[Services], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """Copy puts the address on the clipboard and says so on iOS (D-182)."""
    _, row, _ = card_items(blocks_of(render(svc))[0])
    await click(cast(ft.Control, copy_node(row).content))
    assert cast(MemoryClipboard, svc.clipboard).value == "pycon-us-report@python.org"
    assert said(page) == ["Email address copied"]


async def test_a_phone_row_calls_and_copies_its_number(
    render: Callable[[Services], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """A tap hands ``tel:`` to the phone app; Copy copies the number as stored."""
    year = replace(
        svc.year, content=replace(svc.year.content, safety_contacts=(HOTLINE,))
    )
    _, row, _ = card_items(blocks_of(render(replace(svc, year=year)))[0])
    assert link_node(row).identifier == "help.report.tel"
    assert tile_of(row).subtitle == "+1 562-555-0100"
    await click(tile_of(row))
    launched = cast(MemoryLauncher, svc.launcher).launched
    assert launched == [("tel:+15625550100", ft.LaunchMode.EXTERNAL_APPLICATION)]
    await click(cast(ft.Control, copy_node(row).content))
    assert cast(MemoryClipboard, svc.clipboard).value == "+15625550100"
    assert said(page) == ["Phone number copied"]


async def test_a_call_that_cannot_open_says_so_and_copy_still_works(
    render: Callable[[Services], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """Where ``tel:`` fails (an iPad, a simulator), the row says so; Copy still copies."""
    year = replace(
        svc.year, content=replace(svc.year.content, safety_contacts=(HOTLINE,))
    )
    _, row, _ = card_items(blocks_of(render(replace(svc, year=year)))[0])
    cast(MemoryLauncher, svc.launcher).error = RuntimeError("no app for tel")
    await click(tile_of(row))
    await click(cast(ft.Control, copy_node(row).content))
    assert said(page) == ["Couldn't open the link", "Phone number copied"]
    assert cast(MemoryClipboard, svc.clipboard).value == "+15625550100"


def test_each_place_reads_as_one_phrase(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """A place's row is one merged node: its name, then where it is."""
    block = blocks_of(render(svc))[4]
    tile = tile_of(block)
    assert tile.title == "Quiet room"
    info = svc.year.content.help
    assert info is not None and tile.subtitle == info.quiet_room
    assert tile.on_click is None  # it opens nothing


def test_the_code_of_conduct_links_open_in_the_browser(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """The full text and the procedures are external rows on the PSF's site."""
    blocks = blocks_of(render(svc))
    coc, procedures = blocks[-2:]
    assert tile_of(coc).title == "Read the Code of Conduct"
    assert tile_of(coc).subtitle == "policies.python.org"
    assert isinstance(tile_of(coc).trailing, ft.Icon)  # OPEN_IN_NEW, read aloud
    assert tile_of(procedures).title == "How reports are handled"


def test_without_year_data_the_page_shows_the_feed_s_block(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """A year without the tables hands the page to the feed's ``code-of-conduct``."""
    content = replace(svc.year.content, safety_contacts=(), help=None)
    with Renderer().with_context():  # what calling a component needs, as in a render
        scaffold = render(replace(svc, year=replace(svc.year, content=content)))
    (item,) = blocks_of(scaffold)
    assert isinstance(item, ft.Component)
    assert item.fn is inspect.unwrap(FeedBlock)
    assert item.args == ("code-of-conduct",)
    assert item.kwargs["screen"] == "help"


def test_contacts_without_help_show_the_card_alone(page: FakePage) -> None:
    """The card needs only the contacts; without ``[help]`` it has no staff line."""
    (block,) = help_blocks((HOTLINE,), None)
    assert len(card_items(block)) == 2  # the heading and the row


@pytest.mark.parametrize(
    ("kind", "value", "line"),
    [
        ("tel", "+15625550100", "+1 562-555-0100"),
        ("tel", "+442071234567", "+442071234567"),
        ("mailto", "a@b.org", "a@b.org"),
        ("https", "https://example.org/report/", "example.org"),
    ],
)
def test_a_contact_s_line_is_its_value_as_it_reads(
    kind: str, value: str, line: str
) -> None:
    """A North American number in groups, others as written, a page by its host."""
    assert contact_line(replace(HOTLINE, kind=kind, value=value)) == line
