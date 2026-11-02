"""Tests for the Lead scanner route, ``screens/staff_lead.py`` (LEAD-01, LEAD-14; D-416).

The screen runs in a real Flet session (``tests/harness.py``) with an ``Account``
store set as the flags say, and a mock URL set or not (D-51). Its guard re-checks
``may_open`` on every render (architecture §12.4); past it, the account's consent
(LEAD-04, D-423) is asked once, on ``screens/lead_consent.py``'s page; its parse-only
handler queues a seeded badge in the outbox and shows the row's state (D-426; the
capture itself is ``tests/test_lead_capture.py``'s). One test's sessions share
one SharedPreferences, so a second render is a relaunch. Door staff choose the sponsor
they scan for (LEAD-05, LEAD-06): the picker opens once by itself, the screen waits
until one is chosen, then heads it with a "For: ..." chip; a sponsor's account sees none.
"""

from typing import Any, cast

import flet as ft
import pytest
from flet.components.component import Component

from pycon_us import lead_capture
from pycon_us.account import Account
from pycon_us.core import outbox
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.lead_capture import ALREADY, SAVED
from pycon_us.locations import parent_of
from pycon_us.screens import lead_sponsor
from pycon_us.screens.staff_lead import NO_SPONSOR, TITLE
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.pref_keys import SCANNER_CONSENT, STAFF_PREFIX
from pycon_us.ui import scan_screen
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from pycon_us.ui.snack_bars import NOT_SAVED
from tests import harness, lead_rows, lead_screen
from tests.fakes import MemoryPrefs
from tests.harness import Shown
from tests.lead_screen import Show, chip_text, choose, helper, signed_in
from tests.mock_calls import state_at
from tests.scan_rig import enter, panel
from tests.sync_rig import outbox_db
from tools.mock_api.badges import payload

VIEW = lead_screen.VIEW
db = outbox_db
stored, show = lead_screen.stored, lead_screen.show


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


async def test_a_seeded_badge_is_queued_and_the_repeat_is_already_in_leads(
    show: Show, db: OutboxDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scan is queued for the account; within 4 s the same badge does nothing.

    No worker runs here, so the wait ends with "Saved. Will sync."; once the row is
    synced, the same badge after the cooldown says "Already in your leads" (D-426).
    """
    monkeypatch.setattr(lead_capture, "WAIT_SECONDS", 0.01)
    now = [100.0]
    monkeypatch.setattr(scan_screen, "clock", lambda: now[0])
    attendee = next(iter(state_at().attendees.values()))
    shown = await show(signed_in(lead_retrieval=True), outbox=db)
    await enter(shown, payload(attendee))
    code = attendee.access_code
    assert panel(shown) == f"{SAVED}\n{code}\nScan 1"
    (row,) = db.rows("a@example.com", list(outbox.Status)) or []
    assert (row.key, row.sponsor_id) == (code, None)
    assert row.payload == {"badge_validator": attendee.validator}
    assert db.save(outbox.after_success(row, {"first_name": "Ada"}))
    now[0] += 3.9
    await enter(shown, payload(attendee))  # a held badge: cleared without a word
    assert panel(shown) == f"{SAVED}\n{code}\nScan 1"
    now[0] += 0.2
    await enter(shown, payload(attendee))
    assert panel(shown) == f"{ALREADY}\nAda\n{code}\nScan 2"


async def test_opening_the_scanner_makes_it_now_s_card_s_tool(show: Show) -> None:
    """An open scanner is the last tool opened (D-421); a refused one is not."""
    refused = await show(signed_in())
    assert refused.memory.staff_tool == ""
    shown = await show(signed_in(lead_retrieval=True))
    assert shown.memory.staff_tool == "lead"


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


@pytest.mark.parametrize("flags", [{"lead_retrieval": True}, {"door_check": True}])
async def test_every_component_keeps_its_hooks_from_reading_to_scanning(
    show: Show, monkeypatch: pytest.MonkeyPatch, flags: dict[str, bool]
) -> None:
    """Each render runs all its component's hooks, read to consent to scanner (D-70).

    The stand-in scaffold calls a hook, as the real one does: called from
    ``LeadTool``'s loading branch only, it would leave a hook unused after the read.
    Door staff end on the paused scan screen, with no sponsor chosen yet.
    """
    stand_in = harness._scaffold

    def scaffold(**kwargs: Any) -> ft.Control:
        """Call a hook, as ``AppScaffold`` does, then stand in for it."""
        ft.use_state(0)
        return stand_in(**kwargs)

    renders: list[tuple[str, int, int]] = []
    run_effects = Component._run_render_effects

    def record(component: Component) -> None:
        """Record each render's hooks used and hooks held, then run its effects."""
        state = component._state
        renders.append((component.fn.__name__, state.hook_cursor, len(state.hooks)))
        run_effects(component)

    monkeypatch.setattr(harness, "_scaffold", scaffold)
    monkeypatch.setattr(Component, "_run_render_effects", record)
    shown = await show(signed_in(**flags), consent=False)
    await give(shown)
    assert not asks(shown)
    assert {name for name, *_ in renders} >= {"LeadTool", "LeadConsent", "ScanScreen"}
    assert [render for render in renders if render[1] != render[2]] == []


# ------------------------------------------------------------------ the sponsor (LEAD-05, LEAD-06)

PICKER = f"{VIEW}/{lead_sponsor.SEGMENT}"
EXAMPLE = LeadSponsor("1", "Example Corp")


def chip(shown: Shown) -> ft.Container:
    """The chip's tappable container, around its one node."""
    return cast(ft.Container, shown.node("lead.sponsor_chip").parent)


async def test_staff_without_a_sponsor_get_the_picker_once_and_a_paused_screen(
    show: Show,
) -> None:
    """The picker opens by itself once; the screen says why it waits, with a button."""
    shown = await show(signed_in(door_check=True))
    assert shown.went == [PICKER]
    assert helper(shown) == NO_SPONSOR
    assert chip_text(shown) is None
    await shown.settle()
    assert shown.went == [PICKER]  # once
    await shown.click(cast(ft.Control, shown.node("lead.sponsor.choose").content))
    assert shown.went == [PICKER, PICKER]


async def test_a_chosen_sponsor_shows_as_the_chip_and_scanning_runs(
    show: Show, stored: dict[str, Any]
) -> None:
    """The chip says "For: Example Corp", read as a button to change it; no picker."""
    choose(stored, EXAMPLE)
    shown = await show(signed_in(door_check=True))
    assert shown.went == []
    assert chip_text(shown) == "For: Example Corp"
    node = shown.node("lead.sponsor_chip")
    assert node.label == "Scanning for Example Corp, change sponsor" and node.button
    assert helper(shown) is None
    await shown.click(chip(shown))
    assert shown.went == [PICKER]


async def test_a_staff_scan_is_queued_for_the_sponsor_chosen(
    show: Show,
    stored: dict[str, Any],
    db: OutboxDb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row snapshots the chosen sponsor, its id and name (STORE-11)."""
    monkeypatch.setattr(lead_capture, "WAIT_SECONDS", 0.01)
    choose(stored, EXAMPLE)
    shown = await show(signed_in(door_check=True), outbox=db)
    await enter(shown, "MOCK0001:v4l1d01")
    (row,) = db.rows("a@example.com", list(outbox.Status)) or []
    assert (row.sponsor_id, row.sponsor_name) == (EXAMPLE.id, EXAMPLE.name)


async def test_the_picker_opens_after_the_consent_is_given(show: Show) -> None:
    """Consent first (LEAD-04), then the picker, never over the consent page."""
    shown = await show(signed_in(door_check=True), consent=False)
    assert shown.went == []
    await give(shown)
    assert shown.went == [PICKER]


async def test_back_from_the_picker_shows_the_sponsor_chosen(
    show: Show, stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The keys are read again when the location changes (D-425); Cancel leaves none."""
    location = [PICKER]
    monkeypatch.setattr(ft, "use_route_location", lambda: location[0])
    account = signed_in(door_check=True)
    shown = await show(account)
    location[0] = VIEW  # Cancel: back with nothing chosen
    account.nickname = "Back"  # a render, as the Router's on a location change
    await shown.settle()
    assert helper(shown) == NO_SPONSOR
    assert shown.went == [PICKER]  # not asked again
    location[0] = PICKER
    account.nickname = "Picker"
    await shown.settle()
    choose(stored, EXAMPLE)
    location[0] = VIEW  # a tap: back with Example Corp
    account.nickname = "Chosen"
    await shown.settle()
    assert chip_text(shown) == "For: Example Corp"
    assert helper(shown) is None


async def test_a_consent_given_scans_at_once_for_the_sponsor_read(
    show: Show, stored: dict[str, Any]
) -> None:
    """Giving it is no change of location: nothing is read again, so nothing waits."""
    choose(stored, EXAMPLE)
    shown = await show(signed_in(door_check=True), consent=False)
    await give(shown)
    assert chip_text(shown) == "For: Example Corp"
    assert helper(shown) is None


async def test_a_consent_that_can_t_be_saved_stays_given_at_the_next_read(
    show: Show, stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Storage says no, but the session's answer stands when the keys are read again."""
    location = [VIEW]
    monkeypatch.setattr(ft, "use_route_location", lambda: location[0])
    choose(stored, EXAMPLE)
    account = signed_in(door_check=True)
    shown = await show(account, consent=False)
    cast(MemoryPrefs, shown.storage.prefs).fail_writes = True
    await give(shown)
    location[0] = PICKER
    account.nickname = "Picker"  # a render, as the Router's on a location change
    await shown.settle()
    assert not asks(shown)
    assert helper(shown) is None  # the read has landed: nothing waits for it


async def test_a_sponsor_s_own_account_sees_no_chip_and_no_picker(
    show: Show, stored: dict[str, Any]
) -> None:
    """``lead_retrieval`` scans for its own sponsor: no chip, no pause, no picker."""
    choose(stored, EXAMPLE)  # left by an earlier staff session, say
    for flags in (
        {"lead_retrieval": True},
        {"lead_retrieval": True, "door_check": True},
    ):
        shown = await show(signed_in(**flags))
        assert shown.went == []
        assert chip_text(shown) is None
        assert helper(shown) is None
        assert not shown.nodes("lead.sponsor.choose")


async def test_the_sponsor_goes_with_a_sign_out_and_a_switch(
    show: Show, stored: dict[str, Any]
) -> None:
    """The staff keys' removal (D-414) takes the sponsor; the screen pauses again."""
    choose(stored, EXAMPLE)
    account = signed_in(door_check=True)
    shown = await show(account)
    assert chip_text(shown) is not None
    account.signed_in = False  # Account.sign_out() clears the staff keys too
    assert await shown.storage.clear_prefs(STAFF_PREFIX)
    await shown.settle()
    stored[SCANNER_CONSENT.key] = True  # given again
    account.signed_in = True
    await shown.settle()
    assert chip_text(shown) is None
    assert helper(shown) == NO_SPONSOR
    choose(stored, EXAMPLE)
    assert await shown.storage.clear_prefs(STAFF_PREFIX)  # as a switch's sign-in
    stored[SCANNER_CONSENT.key] = True
    account.email = "b@example.com"
    await shown.settle()
    assert chip_text(shown) is None
    assert helper(shown) == NO_SPONSOR


# ------------------------------------------------------------------ the leads list (#743)


async def test_leads_count_opens_the_list_and_follows_the_outbox(
    show: Show, db: OutboxDb
) -> None:
    """The button counts the account's leads, not notes, and pushes the list (D-428)."""
    lead_rows.add(db, "MOCK0001", 100.0)
    lead_rows.note(db, "MOCK0001", "Notes: hi")
    lead_rows.add(db, "MOCK0002", 200.0, owner="b@example.com")
    shown = await show(signed_in(lead_retrieval=True), outbox=db)
    button = cast(ft.FilledTonalButton, shown.node("lead.leads").content)
    assert button.content == "Leads (1)"
    await shown.click(button)
    assert shown.went == ["/more/staff/lead/leads"]
    assert parent_of("/more/staff/lead/leads") == "/more/staff/lead"
    assert parent_of("/now/staff/lead/leads") == "/now/staff/lead"
