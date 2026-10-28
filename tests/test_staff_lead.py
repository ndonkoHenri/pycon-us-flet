"""Tests for the Lead scanner route, ``screens/staff_lead.py`` (LEAD-01, LEAD-14; D-416).

The screen runs in a real Flet session (``tests/harness.py``) with an ``Account``
store set as the flags say, and a mock URL set or not (D-51). Its guard re-checks
``may_open`` on every render (architecture §12.4); its parse-only handler reads a
seeded badge and records nothing until #39.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path

import flet as ft
import pytest

from pycon_us.account import Account
from pycon_us.config import load_year
from pycon_us.core.badges import Badge, ScanOutcome
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.prefs import Prefs
from pycon_us.screens.staff_lead import (
    BADGE_READ,
    NOT_RECORDED,
    TITLE,
    LeadScanner,
    badge_read,
)
from pycon_us.state import Conference
from pycon_us.ui import scan_screen
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from tests.api_clients import BASE_URL
from tests.harness import Shown, showing
from tests.mock_calls import state_at
from tools.mock_api.badges import payload

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


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders the Lead scanner for an account and a URL."""

    async def focus(_: ft.TextField) -> None:
        """Stand in for the client's focus: nothing to do."""

    monkeypatch.setattr(ft.TextField, "focus", focus)
    async with AsyncExitStack() as stack:

        async def render(account: Account, *, mock_url: bool = True) -> Shown:
            """Render the route signed in as ``account``, with or without a mock URL."""
            prefs = Prefs(loaded=True)
            if mock_url:
                prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            return await stack.enter_async_context(
                showing(
                    LeadScanner,
                    scan_screen,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                    prefs=prefs,
                    account=account,
                )
            )

        yield render


def is_open(shown: Shown) -> bool:
    """Whether the scan screen shows, rather than "Not available for this account"."""
    scanning = bool(shown.nodes("scan.entry"))
    refused = bool(shown.nodes("staff.not_available"))
    assert scanning != refused
    assert (NOT_AVAILABLE in shown.texts()) is refused
    assert shown.titles[-1] == TITLE
    return scanning


@pytest.mark.parametrize(
    ("flags", "opens"),
    [
        ({}, False),
        ({"lead_retrieval": True}, True),
        ({"door_check": True}, True),
        ({"mask_violation": True}, False),
        ({"lead_retrieval": True, "door_check": True, "mask_violation": True}, True),
    ],
)
async def test_the_route_opens_only_for_the_lead_rule(
    show: Show, flags: dict[str, bool], opens: bool
) -> None:
    """``lead_retrieval or door_check`` opens it; any other account is refused."""
    assert is_open(await show(signed_in(**flags))) is opens


async def test_a_signed_out_session_is_refused(show: Show) -> None:
    """Signed out, a deep link to the scanner shows the state, not the screen."""
    assert not is_open(await show(Account(restored=True)))


async def test_without_a_mock_url_the_route_is_refused(show: Show) -> None:
    """With no mock URL (D-51), even a sponsor's account sees the state."""
    assert not is_open(await show(signed_in(lead_retrieval=True), mock_url=False))


async def test_signing_out_while_open_closes_the_scanner(show: Show) -> None:
    """The rule is re-checked on every render: a sign-out shows the state at once."""
    account = signed_in(lead_retrieval=True)
    shown = await show(account)
    assert is_open(shown)
    account.signed_in = False
    await shown.settle()
    assert not is_open(shown)


async def test_a_seeded_badge_reads_with_both_validators_and_is_not_recorded(
    show: Show,
) -> None:
    """A mock sheet's payload shows "Badge read", the code and both validators."""
    attendee = next(iter(state_at().attendees.values()))
    shown = await show(signed_in(lead_retrieval=True))
    (field,) = shown.find(ft.TextField)
    text = payload(attendee)
    shown.session.apply_patch(field._i, {"value": text})
    await shown.event(field, "change", text)
    await shown.event(field, "submit", text)
    assert str(shown.node("scan.result").label) == "\n".join(
        (
            BADGE_READ,
            attendee.access_code,
            f"Door validator: {attendee.validator}",
            f"Lead validator: {attendee.validator}",
            NOT_RECORDED,
            "Scan 1",
        )
    )


async def test_badge_read_is_accepted_styled_and_names_empty_validators() -> None:
    """The parse-only result is ACCEPTED; an empty validator reads "none"."""
    result = await badge_read(Badge("CODE", "", "last"))
    assert result.outcome is ScanOutcome.ACCEPTED
    assert result.details == (
        "Door validator: none",
        "Lead validator: last",
        NOT_RECORDED,
    )


async def test_opening_the_scanner_makes_it_now_s_card_s_tool(show: Show) -> None:
    """An open scanner is the last tool opened (D-421); a refused one is not."""
    refused = await show(signed_in())
    assert refused.memory.staff_tool == ""
    shown = await show(signed_in(lead_retrieval=True))
    assert shown.memory.staff_tool == "lead"
