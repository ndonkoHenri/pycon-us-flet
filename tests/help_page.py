"""Help & safety's fixtures and lookups, for its two test modules (#623).

`test_help.py` (the page: the Report a concern card, the places and the contacts)
and `test_help_report.py` (Report a problem with the app) run `Help` and
`ReportProblem` outside a renderer: their services and `AppScaffold` are replaced,
and a fake page is bound as Flet binds a session's page; the contact rows' component
body runs inline over the same services, as `test_rows.py` runs it. A module takes
the fixtures by assigning them to its own names, as `docs/testing-and-quality.md`
§3.1 says.
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.screens import help as help_screen
from pycon_us.screens.help import Help
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.ui import info_page, link_tile
from pycon_us.year_info import SafetyContact
from tests.fake_page import FakePage, bound, phone_margin
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)

HOTLINE = SafetyContact(
    label="Call the Code of Conduct hotline",
    kind="tel",
    value="+15625550100",
    source="https://example.org/coc/",
    checked=date(2026, 10, 20),
)
"""A phone contact no year ships (the 2026 hotline is on no public page, D-45)."""

REPORT_PROBLEM_SECTION = ft.Container()
"""What `ReportProblem` renders as in the page's tests: its own tests are in
`test_help_report.py`."""


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
    """A `FakePage` (iOS) bound, with the contact rows' body inline over `svc`."""
    monkeypatch.setattr(
        link_tile, "_ExternalLinkTile", inspect.unwrap(link_tile._ExternalLinkTile)
    )
    monkeypatch.setattr(link_tile, "use_services", lambda: svc)
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, page: FakePage
) -> Callable[[Services], dict[str, Any]]:
    """Render `Help` once over the given services and return its scaffold's kwargs."""
    monkeypatch.setattr(help_screen, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(help_screen, "ReportProblem", lambda: REPORT_PROBLEM_SECTION)
    # The credit is a component of its own, tested in test_sponsor_credit.py: here a
    # node that says where it stands and whose sponsor it names.
    monkeypatch.setattr(
        help_screen,
        "SponsorCreditTile",
        lambda credit, what, identifier: ft.Semantics(
            identifier=identifier, label=f"{what}, {credit.slug if credit else ''}"
        ),
    )
    # The card is a component of its own, tested in test_location_card.py: here a
    # node that says where it stands and which pin it shows, as spot_card finds it.
    monkeypatch.setattr(
        help_screen,
        "spot_card",
        lambda data, key, *, identifier: (
            ft.Semantics(identifier=identifier, label=key)
            if key and data.pin(key)
            else None
        ),
    )
    monkeypatch.setattr(info_page, "use_margin", phone_margin)

    def render(svc: Services) -> dict[str, Any]:
        """`Help`'s body, its services answered with `svc`."""
        monkeypatch.setattr(help_screen, "use_services", lambda: svc)
        return cast(dict[str, Any], inspect.unwrap(Help)())

    return render


def blocks_of(scaffold: dict[str, Any]) -> list[ft.Control]:
    """Return the items of the scaffold's `ListView` body."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    return list(body.controls)


def card_of(block: ft.Control) -> ft.Card:
    """Return the Report a concern `Card` inside its gutter."""
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
    """Return a link row's merged `Semantics` node (its identifier and link flag)."""
    if isinstance(row, ft.Row):  # a phone or email row: the link, then Copy
        holder = row.controls[0]
        assert isinstance(holder, ft.Container) and holder.content is not None
        row = holder.content
    assert isinstance(row, ft.MergeSemantics)
    node = row.content
    assert isinstance(node, ft.Semantics)
    return node


def tile_of(row: ft.Control) -> ft.ListTile:
    """Return a row's `ListTile`."""
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
    """Await a tile's or a button's `on_click`, as a tap does."""
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


def block_named(blocks: list[ft.Control], identifier: str) -> ft.Control:
    """Return the one in-app or plain row whose merged node is `identifier`."""
    (block,) = [
        block
        for block in blocks
        if isinstance(block, ft.MergeSemantics)
        and getattr(block.content, "identifier", None) == identifier
    ]
    return block


def outline(blocks: list[ft.Control]) -> list[str]:
    """The page as headings (`# `), the card, row identifiers and the summary."""
    result = []
    for block in blocks:
        if block is REPORT_PROBLEM_SECTION:
            result.append("report_problem")
        elif isinstance(block, ft.Semantics) and block.header:
            heading = block.content
            assert isinstance(heading, ft.Container)
            assert isinstance(heading.content, ft.Text)
            result.append(f"# {heading.content.value}")
        elif isinstance(block, ft.Container) and isinstance(block.content, ft.Card):
            result.append("card")
        elif isinstance(block, ft.Container) and isinstance(
            block.content, ft.Semantics
        ):  # a place's location card, in the gutter
            result.append(str(block.content.identifier))
        elif isinstance(block, ft.Semantics):
            result.append(str(block.identifier))
        else:
            result.append(str(link_node(block).identifier))
    return result
