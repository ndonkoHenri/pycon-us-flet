"""Tests for the sponsor picker, ``screens/lead_sponsor.py`` (LEAD-05; API-09, STORE-11).

The page runs in a real Flet session (``tests/harness.py``) over the mock's own
transport, signed with the seeded staff account's key, so the list is what the mock's
``handle()`` answers; a switch takes the transport offline. Its states are loading,
"Couldn't load sponsors" with Retry, "No sponsors available" and the list; a tap saves
the choice and goes back, Cancel leaves it, and only staff who scan for a sponsor reach
it (architecture §12.4).
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us.account import Account
from pycon_us.config import YearData, load_year
from pycon_us.core.lead_sponsors import LeadSponsor, to_stored
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import lead_sponsor
from pycon_us.screens.lead_sponsor import (
    NONE_AVAILABLE,
    NOT_LOADED,
    TITLE,
    SponsorPicker,
)
from pycon_us.services import Services
from pycon_us.services.pref_keys import staff_sponsor
from pycon_us.services.private_api import PrivateApi
from pycon_us.state import Conference
from pycon_us.ui import scan_screen, staff_picker
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from pycon_us.ui.snack_bars import NOT_SAVED
from tests import harness
from tests.api_clients import BASE_URL, Login
from tests.fakes import MemoryPrefs
from tests.harness import Shown, showing
from tests.mock_calls import account as seeded
from tests.mock_calls import state_at
from tests.picker_rig import Switch, search
from tools.mock_api.transport import mock_transport

VIEW = "/more/staff/lead/sponsor"

type Show = Callable[..., Awaitable[Shown]]


def staff(
    *,
    door_check: bool = True,
    lead_retrieval: bool = False,
    mask_violation: bool = False,
) -> Account:
    """A signed-in ``Account`` with only the given flags; door staff by default."""
    return Account(
        restored=True,
        signed_in=True,
        email="staff@example.com",
        door_check=door_check,
        lead_retrieval=lead_retrieval,
        mask_violation=mask_violation,
    )


@pytest.fixture
def switch() -> Switch:
    """The transport every test's sessions share, over a freshly seeded mock."""
    return Switch(mock_transport(state_at()))


@pytest.fixture
async def show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, switch: Switch
) -> AsyncIterator[Show]:
    """Return a function that renders the picker for an account over ``switch``.

    It signs with the seeded staff account's key; ``chosen`` stores a sponsor first,
    as an earlier pick left it, and ``transport`` replaces ``switch``.
    """

    async def focus(_: ft.TextField) -> None:
        """Stand in for the client's focus: nothing to do."""

    monkeypatch.setattr(ft.TextField, "focus", focus)
    stored: dict[str, Any] = {}
    memory_services = harness.memory_services

    def sharing(
        year: YearData, directory: Path, memory: ViewMemory | None = None
    ) -> Services:
        """Return the memory services over the test's one ``stored``."""
        svc = memory_services(year, directory, memory)
        cast(MemoryPrefs, svc.storage.prefs).values = stored
        return svc

    monkeypatch.setattr(harness, "memory_services", sharing)
    who = seeded(state_at(), "staff")
    async with AsyncExitStack() as stack:

        async def render(
            account: Account | None = None,
            *,
            chosen: LeadSponsor | None = None,
            transport: httpx.AsyncBaseTransport | None = None,
        ) -> Shown:
            """Render the page signed in as ``account``, door staff by default."""
            private_api = PrivateApi(
                transport or switch, credentials=Login(who.key, who.secret)
            )
            await private_api.connect(BASE_URL, 2026)
            if chosen is not None:
                stored[staff_sponsor(2026).key] = json.dumps(to_stored(chosen))
            prefs = Prefs(loaded=True)
            prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            shown = await stack.enter_async_context(
                showing(
                    SponsorPicker,
                    scan_screen,
                    staff_picker,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                    prefs=prefs,
                    account=account or staff(),
                    private_api=private_api,
                )
            )
            stack.push_async_callback(private_api.connect, None, 2026)
            return shown

        yield render


def rows(shown: Shown) -> list[str]:
    """Each sponsor row's phrase, sorted: the list's own order is ``parse_sponsors``'."""
    return sorted(
        str(node.label)
        for node in shown.nodes("lead.sponsor.")
        if str(node.identifier).removeprefix("lead.sponsor.").isdigit()
    )


async def tap(shown: Shown, ident: str) -> None:
    """Tap the row of the sponsor whose id is ``ident``."""
    await shown.click(cast(ft.Container, shown.node(f"lead.sponsor.{ident}").parent))


async def test_the_mock_s_sponsors_show_sorted_with_booth_and_choice(
    show: Show,
) -> None:
    """Three rows by name, Quoted Labs unquoted, the saved one read "selected"."""
    shown = await show(chosen=LeadSponsor("1", "Example Corp"))
    assert shown.titles[-1] == TITLE
    assert rows(shown) == [
        "Example Corp, Booth 101, selected",
        "Quoted Labs, Booth 214",
        "Sample Systems",
    ]
    assert shown.nodes("lead.sponsor.search")


async def test_searching_sam_leaves_sample_systems(show: Show) -> None:
    """The search matches the name; a miss says so and offers to clear."""
    shown = await show()
    await search(shown, "sam")
    assert rows(shown) == ["Sample Systems"]
    await search(shown, "214")  # a booth
    assert rows(shown) == ["Quoted Labs, Booth 214"]
    await search(shown, "zzz")
    assert rows(shown) == []
    assert shown.nodes("lead.sponsor.no_match")


async def test_a_tap_saves_the_sponsor_and_goes_back(show: Show) -> None:
    """The choice is stored as ``{id, name, logo_url}``; the page pops to the scanner."""
    shown = await show(chosen=LeadSponsor("1", "Example Corp"))
    await tap(shown, "3")
    assert await shown.storage.get(staff_sponsor(2026)) == {
        "id": "3",
        "name": "Sample Systems",
        "logo_url": None,
    }
    assert shown.went == ["/more/staff/lead"]
    assert not shown.snack_bars


async def test_cancel_goes_back_and_keeps_the_choice(show: Show) -> None:
    """Cancel is Back: the stored sponsor is left as it was."""
    shown = await show(chosen=LeadSponsor("1", "Example Corp"))
    (cancel,) = [b for b in shown.find(ft.IconButton) if b.tooltip == "Cancel"]
    await shown.click(cancel)
    assert shown.went == ["/more/staff/lead"]
    assert (await shown.storage.get(staff_sponsor(2026)))["id"] == "1"


async def test_a_save_that_ends_after_cancel_leaves_the_user_where_they_are(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A held save released after Cancel and a move to More neither navigates nor says."""
    held = asyncio.Event()
    started = asyncio.Event()
    save = lead_sponsor.save_sponsor

    async def slow_save(storage: Any, sponsor: LeadSponsor) -> bool:
        """Save once ``held`` is set, as a slow write would."""
        started.set()
        await held.wait()
        return await save(storage, sponsor)

    monkeypatch.setattr(lead_sponsor, "save_sponsor", slow_save)
    shown = await show()
    picking = asyncio.create_task(tap(shown, "3"))
    await started.wait()
    (cancel,) = [b for b in shown.find(ft.IconButton) if b.tooltip == "Cancel"]
    await shown.click(cancel)
    shown.session.page.route = "/more"  # the user went on to More
    held.set()
    await picking
    assert shown.went == ["/more/staff/lead"]  # Cancel's, and nothing after
    assert not shown.snack_bars


async def test_a_pick_that_can_t_be_saved_stays_and_says_so(show: Show) -> None:
    """The scanner reads storage, so an unsaved pick stays here, with the SnackBar."""
    shown = await show()
    cast(MemoryPrefs, shown.storage.prefs).fail_writes = True
    await tap(shown, "3")
    assert shown.went == []
    (bar,) = shown.snack_bars
    assert isinstance(bar.content, ft.Text) and bar.content.value == NOT_SAVED


async def test_offline_it_says_so_and_retry_loads(show: Show, switch: Switch) -> None:
    """No connection: "Couldn't load sponsors" with Retry, which loads once back."""
    switch.offline = True
    shown = await show()
    assert NOT_LOADED in shown.texts()
    assert not shown.nodes("lead.sponsor.search")
    switch.offline = False
    (retry,) = shown.find(ft.FilledTonalButton)
    await shown.click(retry)
    assert NOT_LOADED not in shown.texts()
    assert len(rows(shown)) == 3


async def test_a_refusal_is_said_as_not_loaded(show: Show) -> None:
    """An error answer (here 500) is the same state as offline (D-120)."""
    transport = httpx.MockTransport(lambda _: httpx.Response(500, json={}))
    shown = await show(transport=transport)
    assert NOT_LOADED in shown.texts()


async def test_an_empty_list_says_none_are_available(show: Show) -> None:
    """``{"sponsors": []}``: "No sponsors available", and no search field."""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"sponsors": []})
    )
    shown = await show(transport=transport)
    assert NONE_AVAILABLE in shown.texts()
    assert not shown.nodes("lead.sponsor.search")


@pytest.mark.parametrize(
    "account",
    [
        staff(door_check=False, lead_retrieval=True),
        staff(lead_retrieval=True),
        staff(door_check=False, mask_violation=True),
        Account(restored=True),
    ],
    ids=["sponsor", "sponsor and door", "coc", "signed out"],
)
async def test_only_staff_who_scan_for_a_sponsor_reach_it(
    show: Show, account: Account
) -> None:
    """A sponsor's own account, others and a signed-out session see "Not available"."""
    shown = await show(account)
    assert NOT_AVAILABLE in shown.texts()
    assert not shown.nodes("lead.sponsor.search")


def test_a_one_line_choice_row_is_a_48_dp_touch_target() -> None:
    """A one-line row, "All sessions", is 48 dp: 12 dp above and below its 24 dp line."""

    async def pick() -> None:
        """Picks nothing: the row's size is what is pinned."""

    row = staff_picker.choice_row(
        identifier="door.session.all",
        phrase="All sessions",
        lines=[ft.Text("All sessions")],
        selected=False,
        on_click=pick,
    )
    container = cast(ft.Container, cast(ft.MergeSemantics, row).content)
    padding = cast(ft.Padding, container.padding)
    assert padding.top + 24 + padding.bottom >= 48
