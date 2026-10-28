"""Tests for the Lead scanner route, ``screens/staff_lead.py`` (LEAD-01, LEAD-14; D-416).

The screen runs in a real Flet session (``tests/harness.py``) with an ``Account``
store set as the flags say, and a mock URL set or not (D-51). Its guard re-checks
``may_open`` on every render (architecture §12.4); past it, the account's consent
(LEAD-04, D-423) is asked once, on ``screens/lead_consent.py``'s page; its parse-only
handler reads a seeded badge and records nothing until #39. One test's sessions share
one SharedPreferences, so a second render is a relaunch.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.account import Account
from pycon_us.config import YearData, load_year
from pycon_us.core.badges import Badge, ScanOutcome
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import lead_consent, staff_lead
from pycon_us.screens.staff_lead import (
    BADGE_READ,
    NOT_RECORDED,
    TITLE,
    LeadScanner,
    badge_read,
)
from pycon_us.services import Services
from pycon_us.services.storage import SCANNER_CONSENT, STAFF_PREFIX
from pycon_us.state import Conference
from pycon_us.ui import scan_screen
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from pycon_us.ui.snack_bars import NOT_SAVED
from tests import harness
from tests.api_clients import BASE_URL
from tests.fakes import MemoryPrefs
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
            account: Account, *, mock_url: bool = True, consent: bool = True
        ) -> Shown:
            """Render the route signed in as ``account``, with or without a mock URL."""
            if consent:
                stored[SCANNER_CONSENT.key] = True
            prefs = Prefs(loaded=True)
            if mock_url:
                prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            return await stack.enter_async_context(
                showing(
                    LeadScanner,
                    staff_lead,
                    lead_consent,
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


# ------------------------------------------------------------------ the consent (LEAD-04)


def asks(shown: Shown) -> bool:
    """Whether the consent page shows, rather than the scan screen (never both)."""
    asking = bool(shown.nodes("lead.consent.check"))
    assert asking != bool(shown.nodes("scan.entry"))
    return asking


def button(shown: Shown, identifier: str) -> ft.Control:
    """The consent page's button under ``identifier``."""
    control = shown.node(identifier).content
    assert isinstance(control, ft.FilledButton | ft.OutlinedButton)
    return control


async def tick(shown: Shown, ticked: bool = True) -> None:
    """Tick (or untick) the consent's checkbox, as Flutter reports a tap on its row."""
    (box,) = shown.find(ft.Checkbox)
    shown.session.apply_patch(box._i, {"value": ticked})
    await shown.event(box, "change", None)


async def give(shown: Shown) -> None:
    """Tick the box and press Continue."""
    await tick(shown)
    await shown.click(button(shown, "lead.consent.continue"))


async def test_the_consent_shows_until_it_is_given_then_the_scan_screen(
    show: Show, stored: dict[str, Any]
) -> None:
    """Continue is disabled until the box is ticked; it saves and shows the scanner."""
    shown = await show(signed_in(lead_retrieval=True), consent=False)
    assert asks(shown)
    # Neither the field nor the result panel: a HID scanner's typing goes nowhere.
    assert not shown.find(ft.TextField) and not shown.nodes("scan.result")
    assert button(shown, "lead.consent.continue").disabled
    assert shown.node("lead.consent.continue").disabled  # said so (D-214)
    await tick(shown)
    assert not button(shown, "lead.consent.continue").disabled
    await tick(shown, False)
    assert button(shown, "lead.consent.continue").disabled
    await give(shown)
    assert not asks(shown)
    assert stored[SCANNER_CONSENT.key] is True
    assert not shown.snack_bars


async def test_a_given_consent_is_remembered_after_a_relaunch(show: Show) -> None:
    """The next session opens straight onto the scan screen."""
    await give(await show(signed_in(lead_retrieval=True), consent=False))
    assert not asks(await show(signed_in(lead_retrieval=True), consent=False))


async def test_cancel_goes_back_to_more_and_saves_nothing(
    show: Show, stored: dict[str, Any]
) -> None:
    """Cancel goes where Back goes (``parent_of``), even with the box ticked."""
    shown = await show(signed_in(lead_retrieval=True), consent=False)
    await tick(shown)
    await shown.click(button(shown, "lead.consent.cancel"))
    assert shown.went == ["/more"]
    assert SCANNER_CONSENT.key not in stored


async def test_the_staff_keys_going_asks_again(show: Show) -> None:
    """A sign-out removes the staff keys (D-414); signed in again, it asks again."""
    account = signed_in(lead_retrieval=True)
    shown = await show(account, consent=False)
    await give(shown)
    account.signed_in = False  # Account.sign_out() clears the staff keys too
    assert await shown.storage.clear_prefs(STAFF_PREFIX)
    await shown.settle()
    assert not is_open(shown)
    account.signed_in = True
    await shown.settle()
    assert asks(shown)


async def test_another_account_is_asked_for_its_own_consent(show: Show) -> None:
    """A switch re-reads the consent: the previous account's never stands for it."""
    account = signed_in(lead_retrieval=True)
    shown = await show(account, consent=False)
    await give(shown)
    assert await shown.storage.clear_prefs(STAFF_PREFIX)  # as a switch's sign-in
    account.email = "b@example.com"
    await shown.settle()
    assert asks(shown)


async def test_an_expired_account_keeps_its_consent(show: Show) -> None:
    """Signing in again as the same account keeps the staff keys (D-414): no new ask."""
    account = signed_in(lead_retrieval=True)
    shown = await show(account, consent=False)
    await give(shown)
    account.expired = True
    await shown.settle()
    assert not asks(shown)


async def test_a_consent_that_can_t_be_saved_scans_and_says_so(
    show: Show, stored: dict[str, Any]
) -> None:
    """The session scans with it (D-120); the SnackBar says the next start asks."""
    shown = await show(signed_in(lead_retrieval=True), consent=False)
    cast(MemoryPrefs, shown.storage.prefs).fail_writes = True
    await give(shown)
    assert not asks(shown)
    assert SCANNER_CONSENT.key not in stored
    (bar,) = shown.snack_bars
    assert isinstance(bar.content, ft.Text) and bar.content.value == NOT_SAVED
