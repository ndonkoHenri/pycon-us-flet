"""The services, page and lookups the link rule's two test modules share (#623).

``test_links.py`` (the rule, opening and Copy) and ``test_links_feed.py`` (feed texts,
D-197) take the fixtures by assigning them to their own names
(``svc, page = link_rule.svc, link_rule.page``), as ``tests/chrome.py``'s are; the
helpers run with a fake page bound as Flet binds a session's page and the in-memory
launcher and clipboard (``tests/fakes.py``).
"""

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)

WEB = "https://us.pycon.org/2026/"
PROFILE = "https://fosstodon.org/@pycon"
HOTLINE = "tel:+1-562-662-4082"
EMAIL = "mailto:pycon-coc@python.org?subject=Report"
ADDRESS = "pycon-coc@python.org"


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services, with an in-memory launcher and clipboard."""
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
    """A fake page, bound as Flet binds a session's page, until the test ends.

    It is built after the services: a Flet service built while a page is bound registers
    with it.
    """
    fake = FakePage()
    with bound(fake):
        yield fake


def launcher(svc: Services) -> MemoryLauncher:
    """The services' in-memory launcher."""
    return cast(MemoryLauncher, svc.launcher)


def clipboard(svc: Services) -> MemoryClipboard:
    """The services' in-memory clipboard."""
    return cast(MemoryClipboard, svc.clipboard)


def said(page: FakePage) -> list[str]:
    """The SnackBars' texts, in order."""
    result = []
    for dialog in page.dialogs:
        assert isinstance(dialog, ft.SnackBar)
        assert isinstance(dialog.content, ft.Text)
        result.append(str(dialog.content.value))
    return result
