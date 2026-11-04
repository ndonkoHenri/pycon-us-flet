"""Tests for the CoC incident tool's screen, `screens/staff_coc.py` (#759; MASK-01).

The route runs in a real Flet session (`tests/harness.py`) over the mock's own
transport, signed with a seeded account's key, so the directory is what the mock's
`handle()` answers. The tool re-checks its rule on every render (architecture
§12.4); its status line goes loading, "4 attendees" with Reload, "Couldn't load the
attendee list" with Retry, or "Not available" on a 403; offline pauses scanning; a
scan opens the review dialog (its tests: `tests/test_coc_review.py`); and the directory lives in the
screen alone: nothing is stored, and a remount fetches it again (D-56, D-432). The session, the
transport and the `show` fixture are `tests/coc_rig.py`'s.
"""

import asyncio
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us.account import Account
from pycon_us.core.staff_tools import ToolKey
from pycon_us.screens import staff_coc
from pycon_us.screens.staff_coc import (
    LOADING,
    NOT_LOADED,
    OFFLINE,
    TITLE,
)
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from tests import coc_rig
from tests.coc_rig import ATTENDEES, Show, Switch, coc, seeded_mock
from tests.harness import Shown
from tests.scan_rig import enter, panel

show, switch, stored = coc_rig.show, coc_rig.switch, coc_rig.stored


def status(shown: Shown) -> str:
    """What the status line's live region says."""
    node = shown.node("coc.directory")
    assert node.live_region and node.container  # said as it changes (ux.md §9)
    return str(node.label)


def helper(shown: Shown) -> str | None:
    """The badge field's line: why scanning is paused, or None."""
    (field,) = shown.find(ft.TextField)
    return cast(str | None, field.helper)


def button(shown: Shown, identifier: str) -> ft.IconButton | ft.TextButton:
    """The status line's button that `identifier` names."""
    found = shown.node(identifier).content
    assert isinstance(found, ft.IconButton | ft.TextButton)
    return found


@pytest.mark.parametrize(
    ("account", "mock_url"),
    [
        (coc(mask_violation=False), True),
        (coc(mask_violation=False, door_check=True, lead_retrieval=True), True),
        (Account(), True),
        (coc(), False),
    ],
    ids=["no flag", "door and lead only", "signed out", "no mock URL"],
)
async def test_only_a_coc_account_with_a_mock_url_reaches_it(
    show: Show, switch: Switch, account: Account, mock_url: bool
) -> None:
    """Without `mask_violation`, signed out or with no mock URL: "Not available"."""
    shown = await show(account, mock_url=mock_url)
    assert NOT_AVAILABLE in shown.texts()
    assert not shown.nodes("scan.entry")
    assert switch.paths == []  # nothing fetched
    assert shown.memory.staff_tool != ToolKey.COC


async def test_it_loads_then_counts_the_mock_s_attendees(
    show: Show, switch: Switch
) -> None:
    """A ring and "Loading attendee list…", then "4 attendees" with Reload."""
    switch.gate = asyncio.Event()
    shown = await show(settle=False)
    await shown.settle()
    assert shown.titles[-1] == TITLE
    assert status(shown) == LOADING
    assert shown.find(ft.ProgressRing)
    assert not shown.nodes("coc.directory.reload")
    switch.gate.set()
    await shown.settle()
    assert status(shown) == "4 attendees"
    assert not shown.find(ft.ProgressRing)
    reload = button(shown, "coc.directory.reload")
    assert reload.tooltip == "Reload attendee list" and not reload.disabled
    assert helper(shown) is None  # scanning
    assert shown.memory.staff_tool == ToolKey.COC  # Now's card's next tool (D-421)


async def test_a_large_directory_is_counted_with_a_separator(
    show: Show, switch: Switch
) -> None:
    """The mock's `--attendees 3000`: "3,004 attendees"."""
    switch.inner = seeded_mock(attendees=3000)
    shown = await show()
    assert status(shown) == "3,004 attendees"


async def test_reload_fetches_the_directory_again(show: Show, switch: Switch) -> None:
    """Reload asks the mock again; the count comes back."""
    shown = await show()
    await shown.click(button(shown, "coc.directory.reload"))
    assert switch.paths.count(ATTENDEES) == 2
    assert status(shown) == "4 attendees"


async def test_no_answer_says_so_and_retry_loads(show: Show, switch: Switch) -> None:
    """Offline at the fetch: "Couldn't load the attendee list"; Retry loads once back."""
    switch.offline = True
    shown = await show()
    assert status(shown) == NOT_LOADED
    switch.offline = False
    await shown.click(button(shown, "coc.directory.retry"))
    assert status(shown) == "4 attendees"


async def test_an_error_answer_is_the_same_failure(show: Show, switch: Switch) -> None:
    """A 500 is said as "Couldn't load the attendee list", with Retry (D-120)."""
    switch.inner = httpx.MockTransport(lambda _: httpx.Response(500, json={}))
    shown = await show()
    assert status(shown) == NOT_LOADED
    assert shown.nodes("coc.directory.retry")


async def test_a_refusal_says_not_available_and_pauses(show: Show) -> None:
    """The mock's 403 (the flag gone on the server): "Not available", no scanning."""
    shown = await show(role="staff")
    assert status(shown) == NOT_AVAILABLE
    assert helper(shown) == NOT_AVAILABLE
    assert not shown.nodes("coc.directory.retry")


async def test_offline_pauses_scanning_and_disables_the_buttons(
    show: Show, switch: Switch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No connection: "CoC capture needs a connection"; Reload and Retry disabled."""
    monkeypatch.setattr(staff_coc, "use_online", lambda svc, *, watch: False)
    shown = await show()
    assert helper(shown) == OFFLINE
    reload = button(shown, "coc.directory.reload")
    assert reload.disabled and OFFLINE in str(reload.tooltip)
    await enter(shown, "MOCK0003:x")
    assert not shown.nodes("scan.result") or "Linus" not in panel(shown)


async def test_offline_retry_is_disabled_with_the_reason(
    show: Show, switch: Switch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a failed fetch offline, Retry is disabled and says why."""
    monkeypatch.setattr(staff_coc, "use_online", lambda svc, *, watch: False)
    switch.offline = True
    shown = await show()
    node = shown.node("coc.directory.retry")
    assert node.disabled  # read as disabled (named(), F42)
    named = node.content
    assert isinstance(named, ft.Semantics)  # a disabled button's tooltip isn't read
    assert named.label == f"Retry. {OFFLINE}" and named.disabled
    assert isinstance(named.content, ft.TextButton) and named.content.disabled


async def test_the_directory_is_dropped_on_leaving_and_never_stored(
    show: Show, switch: Switch, stored: dict[str, Any]
) -> None:
    """Leaving the tool cancels its fetch and drops the directory; re-entry refetches.

    In one session: losing `mask_violation` mid-fetch unmounts the tool and cancels
    the request, so no late answer lands; regaining it fetches the changed mock anew;
    a sign-out drops it again; nothing ever reaches storage (D-432, D-56).
    """
    account = coc()
    switch.gate = asyncio.Event()
    shown = await show(account, settle=False)
    await shown.settle()
    assert status(shown) == LOADING
    account.mask_violation = False  # the flag revoked while the fetch waits
    await shown.settle()
    assert switch.cancelled == 1  # the effect was cancelled: its answer never lands
    assert NOT_AVAILABLE in shown.texts()
    assert not shown.nodes("coc.directory")
    switch.inner = seeded_mock(attendees=3000)  # the server's list changed
    switch.gate.set()
    account.mask_violation = True  # back in the tool: a new mount
    await shown.settle()
    assert status(shown) == "3,004 attendees"
    assert switch.paths.count(ATTENDEES) == 2
    account.signed_in = False  # Account.sign_out() clears the flags too
    await shown.settle()
    assert not shown.nodes("coc.directory")
    account.signed_in = True
    await shown.settle()
    assert status(shown) == "3,004 attendees"
    assert switch.paths.count(ATTENDEES) == 3  # fetched again, not kept
    assert stored == {}
