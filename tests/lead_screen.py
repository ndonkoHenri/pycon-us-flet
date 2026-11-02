"""The Lead scanner's test rig: the route rendered for an account, its preferences shared.

Shared by ``tests/test_staff_lead.py`` and ``tests/test_lead_note_sheet.py``: ``show``
renders ``screens/staff_lead.py``'s ``LeadScanner`` in a real Flet session
(``tests/harness.py``) signed in as an ``Account``, with a mock URL set or not (D-51),
and its sessions share one SharedPreferences (``stored``), so a second render is a
relaunch. A test module takes the fixtures with ``stored, show = lead_screen.stored,
lead_screen.show``. It reads the sponsor's chip and the field's pause too.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.account import Account
from pycon_us.config import YearData, load_year
from pycon_us.core.lead_sponsors import LeadSponsor, to_stored
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import lead_consent
from pycon_us.screens.staff_lead import LeadScanner
from pycon_us.services import Services
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.pref_keys import SCANNER_CONSENT, STAFF_SPONSOR
from pycon_us.state import Conference
from pycon_us.ui import scan_screen, staff_picker
from tests import harness
from tests.api_clients import BASE_URL
from tests.fakes import MemoryPrefs
from tests.harness import Shown, showing

VIEW = "/more/staff/lead"
type Show = Callable[..., Awaitable[Shown]]


def signed_in(
    *,
    lead_retrieval: bool = False,
    door_check: bool = False,
    mask_violation: bool = False,
) -> Account:
    """A restored, signed-in ``Account`` with only the given role flags on."""
    return Account(
        restored=True,
        signed_in=True,
        email="a@example.com",
        lead_retrieval=lead_retrieval,
        door_check=door_check,
        mask_violation=mask_violation,
    )


def choose(stored: dict[str, Any], sponsor: LeadSponsor) -> None:
    """Store ``sponsor`` as the chosen one, as the picker saves it."""
    stored[STAFF_SPONSOR.key] = json.dumps(to_stored(sponsor))


def chip_text(shown: Shown) -> str | None:
    """What the "For: ..." chip shows, or None without the chip."""
    nodes = shown.nodes("lead.sponsor_chip")
    if not nodes:
        return None
    (node,) = nodes
    row = node.content
    assert isinstance(row, ft.Row)
    (text,) = [c for c in row.controls if isinstance(c, ft.Text)]
    return str(text.value)


def helper(shown: Shown) -> str | None:
    """The scan field's helper line: why scanning is paused, or None."""
    (field,) = shown.find(ft.TextField)
    return cast(str | None, field.helper)


@pytest.fixture
def stored() -> dict[str, Any]:
    """The SharedPreferences values every session of a test shares, as a device's."""
    return {}


@pytest.fixture
async def show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stored: dict[str, Any]
) -> AsyncIterator[Show]:
    """Return a function that renders the Lead scanner for an account and a URL.

    Its sessions keep their preferences in ``stored``; ``consent`` stores the
    account's consent first, as an earlier visit left it.
    """

    async def focus(_: ft.TextField) -> None:
        """Stand in for the client's focus: nothing to do."""

    monkeypatch.setattr(ft.TextField, "focus", focus)
    memory_services = harness.memory_services

    def sharing(
        year: YearData, directory: Path, memory: ViewMemory | None = None
    ) -> Services:
        """Return the memory services over the test's one ``stored``."""
        svc = memory_services(year, directory, memory)
        cast(MemoryPrefs, svc.storage.prefs).values = stored
        return svc

    monkeypatch.setattr(harness, "memory_services", sharing)
    async with AsyncExitStack() as stack:

        async def render(
            account: Account,
            *,
            mock_url: bool = True,
            consent: bool = True,
            outbox: OutboxDb | None = None,
        ) -> Shown:
            """Render the route signed in as ``account``, with or without a mock URL.

            ``outbox`` is the services' outbox, where a scan is queued; none by default.
            """
            if consent:
                stored[SCANNER_CONSENT.key] = True
            prefs = Prefs(loaded=True)
            if mock_url:
                prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            return await stack.enter_async_context(
                showing(
                    LeadScanner,
                    lead_consent,
                    scan_screen,
                    staff_picker,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                    prefs=prefs,
                    account=account,
                    outbox=outbox,
                )
            )

        yield render
