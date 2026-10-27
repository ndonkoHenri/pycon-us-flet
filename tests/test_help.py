"""Tests for Help & safety (``/more/help``; INFO-07, INFO-11, D-281).

``Help`` runs outside a renderer over the fixtures and lookups of
``tests/help_page.py``: its services and ``AppScaffold`` are replaced, and a fake page
is bound as Flet binds a session's page; the contact rows' component body runs inline
over the same services, as ``test_rows.py`` runs it. Report a problem with the app is
tested in ``test_help_report.py``. What TalkBack and VoiceOver read, and how the card
looks at 200 % text, are checked on devices (the PR).
"""

import inspect
from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us.screens.help import contact_line, help_blocks
from pycon_us.services import Services
from pycon_us.ui.info_page import FeedBlock
from pycon_us.year_map import MapData
from tests import help_page
from tests.fakes import FakePage, MemoryClipboard, MemoryLauncher
from tests.help_page import (
    HOTLINE,
    REPORT_PROBLEM_SECTION,
    block_named,
    blocks_of,
    card_items,
    card_of,
    click,
    copy_node,
    link_node,
    outline,
    said,
    tile_of,
)

# The harness's fixtures, under this module's names, where pytest looks them up.
svc, page, render = help_page.svc, help_page.page, help_page.render


def test_the_card_comes_first_then_the_venue_then_the_code_of_conduct(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """The page reads the card, the places, the CoC, then the app's row (D-281)."""
    scaffold = render(svc)
    assert scaffold["title"] == "Help & safety"
    assert outline(blocks_of(scaffold)) == [
        "card",
        "# At the venue",
        "help.info_desk",
        "help.info_desk.location",
        "help.lost_and_found",
        "help.lost_and_found.location",
        "help.quiet_room",
        "help.quiet_room.location",
        "help.quiet_room.sponsor",
        "help.all_maps",
        "# Code of Conduct",
        "help.coc_summary",
        "help.coc",
        "help.procedures",
        "report_problem",
    ]


def test_the_quiet_room_s_line_is_followed_by_its_sponsor_s_credit(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """D-337: the credit row under the quiet room names the year's sponsor."""
    (credit,) = [
        block
        for block in blocks_of(render(svc))
        if isinstance(block, ft.Semantics)
        and block.identifier == "help.quiet_room.sponsor"
    ]
    assert credit.label == "Quiet room, google"


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


def test_2026_s_card_has_the_email_row_then_the_danger_and_staff_line(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """2026 lists the report email (no public hotline, D-45), then the last line.

    It says emergency services first when someone is in danger, then reporting in
    person.
    """
    _, row, line = card_items(blocks_of(render(svc))[0])
    node = link_node(row)
    assert node.identifier == "help.report.mailto" and node.link
    tile = tile_of(row)
    # One node read as action plus value.
    assert tile.title == "Email the Code of Conduct team"
    # It may wrap only after its @ or a hyphen, never inside the domain (#642), and
    # a screen reader says it as written.
    assert isinstance(tile.subtitle, ft.Text)
    assert tile.subtitle.value == "pycon-us-report@\u200bpython.org"
    assert tile.subtitle.semantics_label == "pycon-us-report@python.org"
    assert copy_node(row).identifier == "help.copy.mailto"
    assert isinstance(line, ft.Container) and isinstance(line.content, ft.Text)
    assert str(line.content.value).startswith("If someone is in danger, contact local")
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
    tile = tile_of(block_named(blocks_of(render(svc)), "help.quiet_room"))
    assert tile.title == "Quiet room"
    info = svc.year.content.help
    assert info is not None and tile.subtitle == info.quiet_room
    assert tile.on_click is None  # it opens nothing


def test_the_code_of_conduct_links_open_in_the_browser(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """The full text and the procedures are external rows on the PSF's site."""
    blocks = blocks_of(render(svc))
    coc, procedures = blocks[-3:-1]
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
    item, report = blocks_of(scaffold)
    assert report is REPORT_PROBLEM_SECTION  # the app's row ends the page still
    assert isinstance(item, ft.Component)
    assert item.fn is inspect.unwrap(FeedBlock)
    assert item.args == ("code-of-conduct",)
    assert item.kwargs["screen"] == "help"


def test_each_place_s_card_shows_the_pin_help_names(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """INFO-12: the desk, lost and found and the quiet room each show their pin."""
    cards = {
        str(block.content.identifier): block.content.label
        for block in blocks_of(render(svc))
        if isinstance(block, ft.Container) and isinstance(block.content, ft.Semantics)
    }
    assert cards == {
        "help.info_desk.location": "info-desk",
        "help.lost_and_found.location": "lost-and-found",
        "help.quiet_room.location": "quiet-room",
    }


def test_all_maps_opens_the_map_s_floor_plans(
    render: Callable[[Services], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """All maps is an in-app row to the Map's Floor plans tab, where the plans are."""
    tile = tile_of(block_named(blocks_of(render(svc)), "help.all_maps"))
    assert tile.title == "All maps"
    assert tile.on_click is not None
    tile.on_click()  # type: ignore[call-arg]  # an in-app row's tap is sync
    assert page.navigated == ["/map?tab=floor-plans"]


def test_a_year_without_plans_shows_no_card_and_no_all_maps(
    render: Callable[[Services], dict[str, Any]], svc: Services
) -> None:
    """Without ``map.toml`` (2025's case) the places are their lines alone."""
    year = replace(svc.year, map=MapData())
    assert outline(blocks_of(render(replace(svc, year=year))))[2:7] == [
        "help.info_desk",
        "help.lost_and_found",
        "help.quiet_room",
        "help.quiet_room.sponsor",
        "# Code of Conduct",
    ]


def test_contacts_without_help_show_the_card_alone(page: FakePage) -> None:
    """The card needs only the contacts; without ``[help]`` it has no staff line."""
    (block,) = help_blocks((HOTLINE,), None)
    assert len(card_items(block)) == 2  # the heading and the row


@pytest.mark.parametrize(
    ("kind", "value", "line"),
    [
        ("tel", "+15625550100", "+1 562-555-0100"),
        ("tel", "+442071234567", "+442071234567"),
        ("mailto", "a@b.org", "a@\u200bb.org"),
        ("https", "https://example.org/report/", "example.org"),
    ],
)
def test_a_contact_s_line_is_its_value_as_it_reads(
    kind: str, value: str, line: str
) -> None:
    """A North American number in groups, an address with a break after its ``@``.

    Other numbers read as written, a page by its host.
    """
    assert contact_line(replace(HOTLINE, kind=kind, value=value)) == line
