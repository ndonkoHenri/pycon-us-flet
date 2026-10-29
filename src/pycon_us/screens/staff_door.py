"""Door check (``/more/staff/door``): the shared scan screen, for a session chosen first.

A mount of ``ui/scan_screen.py``'s ``ScanScreen`` (D-416; DOOR-01, DOOR-02; #764). It
re-checks ``may_open(DOOR)`` with a signed-in account and a mock URL on every render
(architecture §12.4), else "Not available for this account", so a deep link cannot
bypass it. It is mounted at ``/now/staff/door`` too and records itself as the last tool
opened (D-421); More's row and Now's card open it, with the outbox's counts (#766).

What it checks in for is chosen on ``door_session.py``'s picker, pushed at
``…/staff/door/session``, as the Lead scanner's sponsor (D-425, D-433). The choice
(``STAFF_DOOR_SESSION``) is read as the screen opens and again whenever the location
changes, so it is current when the picker goes back; until that read lands, scanning
waits, so no badge is checked against the previous session's list. With none, the picker opens by
itself once per visit and scanning is paused ("Choose a session to start checking in")
with a "Choose session" button; with one, a chip "Async in depth · Wed 1:30 PM"
(``door.session_chip``) heads the screen and reopens the picker.

Once a session is chosen, its attendee list loads (``door_preload.py``, DOOR-03):
scanning is paused with "Loading attendee list… 2 of 5", then the line under the chip
says "Ready, works offline · 3 attendees", or "Badges will be checked online" with
Retry, and scanning starts. A scan is ``door_check.check_in()``: decided on the device,
queued as a ``door`` row of this visit (a uuid made on mount) and synced in the
background (DOOR-04, DOOR-07, D-441). Under the chip, "42 checked in"
(``door_headcount.py``) counts the account's check-ins for the session on this device,
from the outbox (DOOR-06, D-442).
"""

from dataclasses import dataclass
from functools import partial
from uuid import uuid4

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.door_sessions import SEPARATOR, DoorChoice
from pycon_us.core.staff_tools import TOOLS, ToolKey, may_open
from pycon_us.door_check import NOT_CHECKED_IN, check_in
from pycon_us.door_choice import read_door_session
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.screens import door_session
from pycon_us.screens.door_headcount import headcount_line, use_headcount
from pycon_us.screens.door_preload import (
    LOADING,
    Preload,
    status_line,
    status_words,
    use_preload,
)
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.staff import use_staff
from pycon_us.ui.scan_screen import NotAvailable, ScanScreen
from pycon_us.ui.staff_picker import Reading, context_chip, tool_button

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.DOOR)
"""The app bar's title, "Door check", as the staff entry points name it."""

NO_SESSION = "Choose a session to start checking in"
"""Why scanning is paused with no session chosen (DOOR-02)."""


@dataclass(frozen=True)
class Read:
    """The door's staff key as ``DoorTool`` last read it.

    Attributes:
        owner: The account it was read for; another's never stands (D-423).
        location: The route location it was read at; until the read at the current
            one lands, the choice may be stale, so scanning waits.
        choice: The session, or sessions, chosen, or None.
    """

    owner: str
    location: str
    choice: DoorChoice | None


@ft.component
def DoorCheck() -> ft.Control:
    """Door check, or its "Not available" state for an account it refuses."""
    prefs = use_prefs()
    account = use_account()
    memory = use_services().memory
    allowed = (
        prefs.private_api_enabled
        and account.signed_in
        and may_open(ToolKey.DOOR, account.role_flags)
    )
    if not allowed:
        return NotAvailable(title=TITLE)
    memory.staff_tool = ToolKey.DOOR  # plain: Now's card reads it when it renders
    return DoorTool(owner=account.owner)


@ft.component
def DoorTool(*, owner: str) -> ft.Control:
    """The scan screen, paused until a session is chosen and its list loaded.

    Until the key is read, an empty page under the title; the read takes a moment.
    The list loads in ``use_preload()``, called on every render (D-70); scanning is
    paused while it loads, and its line sits under the session chip.

    Args:
        owner: The signed-in account (``Account.owner``).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    location = ft.use_route_location()  # changes as the picker opens and goes back
    svc = use_services()
    prefs = use_prefs()
    staff = use_staff()
    read, set_read = ft.use_state(not_read)  # None until the first read
    asked = ft.use_ref(False)  # the picker opened by itself: only once per visit
    visit = ft.use_memo(lambda: uuid4().hex, [])  # the scan session of a row's key

    @report_errors
    async def read_key() -> None:
        set_read(Read(owner, location, await read_door_session(svc.storage)))

    ft.use_effect(read_key, [owner, location])
    current = read if read is not None and read.owner == owner else None
    needs_session = current is not None and current.choice is None
    # Back from the picker, the old choice shows until the new read lands; scanning
    # waits, so no badge is checked against the old session's list meanwhile.
    rereading = current is not None and current.location != location

    @report_errors
    def open_picker() -> None:
        page.navigate(f"{view_path}/{door_session.SEGMENT}")

    @report_errors
    def ask() -> None:
        if needs_session and not asked.current and is_top_view(page.route, view_path):
            asked.current = True
            open_picker()

    ft.use_effect(ask, [needs_session])
    choice = current.choice if current is not None else None
    loading = use_preload(owner, choice)
    preload = loading.preload
    count = use_headcount(owner, choice.product_ids if choice is not None else ())

    if current is None:
        return Reading(title=TITLE)
    if current.choice is None:
        return ScanScreen(
            title=TITLE,
            on_badge=no_session,
            paused=NO_SESSION,
            actions=[choose_button(open_picker)],
        )
    on_badge = partial(
        check_in,
        svc.outbox,
        staff,
        svc.kick_sync,
        svc.api,
        owner=owner,
        session=visit,
        product_ids=current.choice.product_ids,
        inventory=preload.inventory,
    )
    return ScanScreen(
        title=TITLE,
        on_badge=on_badge,
        context=ft.Column(
            [
                session_chip(current.choice, open_picker),
                headcount_line(count),
                status_line(
                    preload, on_retry=loading.retry, live=not prefs.announcements
                ),
            ],
            spacing=8,
        ),
        paused=LOADING if rereading else paused_words(preload),
    )


async def no_session(badge: Badge) -> ScanResult:
    """The ``on_badge`` with no session chosen: scanning is paused, so never called.

    Should a submit get through, nobody is checked in and the pause's words say why.
    """
    return ScanResult(
        ScanOutcome.DENIED, NOT_CHECKED_IN, badge.code, (NO_SESSION,), badge.code
    )


def paused_words(preload: Preload) -> str | None:
    """Return why scanning waits for the list ("Loading attendee list…"), or None.

    Args:
        preload: Where the load is.
    """
    return status_words(preload) if preload.loaded is None else None


def session_chip(choice: DoorChoice, on_click: ft.ControlEventHandler) -> ft.Control:
    """Return the "Async in depth · Wed 1:30 PM" chip that heads the scan screen.

    One node, a button read "Checking in for Async in depth, Wed 1:30 PM, change
    session"; it opens the picker.

    Args:
        choice: The session, or sessions, chosen.
        on_click: Opens the picker.
    """
    spoken = choice.label.replace(SEPARATOR, ", ")
    return context_chip(
        text=choice.label,
        spoken=f"Checking in for {spoken}, change session",
        icon=ft.Icons.EVENT_OUTLINED,
        identifier="door.session_chip",
        on_click=on_click,
    )


def choose_button(on_click: ft.ControlEventHandler) -> ft.Control:
    """Return "Choose session", under the paused field while none is chosen."""
    return tool_button(
        "door.session.choose", door_session.TITLE, ft.Icons.EVENT_OUTLINED, on_click
    )


def not_read() -> Read | None:
    """Return None: the key not read yet, ``DoorTool``'s first state (typed)."""
    return None
