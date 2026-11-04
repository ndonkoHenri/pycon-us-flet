"""What the shared rows' two test modules share: services, a bound page and lookups (#623).

`tests/test_rows.py` (in-app rows and speaker tiles) and `tests/test_rows_external.py`
(external rows) take the `svc` and `page` fixtures by assignment (§3.1). The
builders run outside a renderer, with a `FakePage` bound as Flet binds a session's
page; the external form's component body runs unwrapped, over `svc`.
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.ui import link_tile
from tests.fake_page import FakePage, bound
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)

WEB = "https://us.pycon.org/2026/"


PROFILE = "https://fosstodon.org/@pycon"


HOTLINE = "tel:+1-562-662-4082"


EMAIL = "mailto:pycon-coc@python.org?subject=Report"


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services, built before a page is bound, as `App` builds them."""
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
    """A `FakePage` bound, with the external row's body inline over `svc`.

    The external row's component body runs inline: there is no renderer here.
    """
    monkeypatch.setattr(
        link_tile, "_ExternalLinkTile", inspect.unwrap(link_tile._ExternalLinkTile)
    )
    monkeypatch.setattr(link_tile, "use_services", lambda: svc)
    fake = FakePage()
    with bound(fake):
        yield fake


def launcher(svc: Services) -> MemoryLauncher:
    """Return the services' `MemoryLauncher`."""
    return cast(MemoryLauncher, svc.launcher)


def clipboard(svc: Services) -> MemoryClipboard:
    """Return the services' `MemoryClipboard`."""
    return cast(MemoryClipboard, svc.clipboard)


def said(page: FakePage) -> list[str]:
    """The SnackBars' texts, in order."""
    result = []
    for dialog in page.dialogs:
        assert isinstance(dialog, ft.SnackBar)
        assert isinstance(dialog.content, ft.Text)
        result.append(str(dialog.content.value))
    return result


def tile_of(row: ft.Control) -> ft.ListTile:
    """The `ListTile` inside a row's semantics wrappers."""
    if isinstance(row, ft.Row):  # a phone or email row: the link, then Copy
        holder = row.controls[0]
        assert isinstance(holder, ft.Container) and holder.content is not None
        row = holder.content
    assert isinstance(row, ft.MergeSemantics)  # one node for screen readers
    inner = row.content
    if isinstance(inner, ft.Semantics):
        inner = inner.content
    assert isinstance(inner, ft.ListTile)
    return inner


def node_of(row: ft.Control) -> ft.Semantics | None:
    """The `Semantics` that annotates a row's merged node, if any."""
    tile = tile_of(row)
    merged = row if isinstance(row, ft.MergeSemantics) else None
    if isinstance(row, ft.Row):
        holder = row.controls[0]
        assert isinstance(holder, ft.Container)
        merged = holder.content
    assert isinstance(merged, ft.MergeSemantics)
    node = merged.content
    if isinstance(node, ft.Semantics):
        assert node.content is tile
        return node
    return None


def copy_button_of(row: ft.Control) -> ft.IconButton:
    """Return the Copy `IconButton` beside a phone or email row's link."""
    assert isinstance(row, ft.Row)
    holder = row.controls[1]
    assert isinstance(holder, ft.Container)
    button = holder.content
    assert isinstance(button, ft.MergeSemantics)  # one node with its tooltip (D-234)
    button = button.content
    if isinstance(button, ft.Semantics):  # with an identifier (D-214)
        button = button.content
    assert isinstance(button, ft.IconButton)
    return button


def tap(tile: ft.ListTile) -> None:
    """Call a tile's `on_click`, as a tap does."""
    assert tile.on_click is not None
    cast(Callable[[], None], tile.on_click)()


async def tap_async(control: ft.ListTile | ft.IconButton) -> None:
    """Await a tile's or a button's `on_click`, as a tap does."""
    assert control.on_click is not None
    await cast(Callable[[], Awaitable[None]], control.on_click)()
