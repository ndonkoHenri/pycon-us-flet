"""Door check (``/more/staff/door``): the shared scan screen, for a session chosen first.

A mount of ``ui/scan_screen.py``'s ``ScanScreen`` (D-416; DOOR-01, DOOR-02; #764). It
re-checks ``may_open(DOOR)`` with a signed-in account and a mock URL on every render
(architecture §12.4), else "Not available for this account", so a deep link cannot
bypass it. It is mounted at ``/now/staff/door`` too and records itself as the last tool
opened (D-421); the entries in More and Now come with check-in itself (#766), so for now
it is reached by deep link only (D-169).

What it checks in for is chosen on ``door_session.py``'s picker, pushed at
``…/staff/door/session``, as the Lead scanner's sponsor (D-425, D-433). The choice
(``STAFF_DOOR_SESSION``) is read as the screen opens and again whenever the location
changes, so it is current when the picker goes back. With none, the picker opens by
itself once per visit and scanning is paused ("Choose a session to start checking in")
with a "Choose session" button; with one, a chip "Async in depth · Wed 1:30 PM"
(``door.session_chip``) heads the screen and reopens the picker.

Once a session is chosen, its attendee list loads (``door_preload.py``, DOOR-03):
scanning is paused with "Loading attendee list… 2 of 5", then the line under the chip
says "Ready, works offline · 3 attendees", or "Badges will be checked online" with
Retry, and scanning starts. Until admission comes (#766), a scan only says whether the
badge is on the list ("Badge read") and checks nobody in.
"""

from dataclasses import dataclass
from functools import partial

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.admission import Inventory
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.door_sessions import SEPARATOR, DoorChoice
from pycon_us.core.staff_tools import TOOLS, ToolKey, may_open
from pycon_us.door_choice import read_door_session
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.screens import door_session
from pycon_us.screens.door_preload import status_line, status_words, use_preload
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.scan_screen import NotAvailable, ScanScreen
from pycon_us.ui.staff_picker import Reading, context_chip, tool_button

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.DOOR)
"""The app bar's title, "Door check", as the staff entry points name it."""

NO_SESSION = "Choose a session to start checking in"
"""Why scanning is paused with no session chosen (DOOR-02)."""

BADGE_READ = "Badge read"
ON_LIST = "On the attendee list"
NOT_ON_LIST = "Not on the attendee list"
NOT_CHECKED_IN = "Not checked in yet"
"""The interim result's words until admission comes (#766), as CoC's "Badge read"."""


@dataclass(frozen=True)
class Read:
    """The door's staff key as ``DoorTool`` last read it.

    Attributes:
        owner: The account it was read for; another's never stands (D-423).
        choice: The session, or sessions, chosen, or None.
    """

    owner: str
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
    read, set_read = ft.use_state(not_read)  # None until the first read
    asked = ft.use_ref(False)  # the picker opened by itself: only once per visit

    @report_errors
    async def read_key() -> None:
        set_read(Read(owner, await read_door_session(svc.storage)))

    ft.use_effect(read_key, [owner, location])
    current = read if read is not None and read.owner == owner else None
    needs_session = current is not None and current.choice is None

    @report_errors
    def open_picker() -> None:
        page.navigate(f"{view_path}/{door_session.SEGMENT}")

    @report_errors
    def ask() -> None:
        if needs_session and not asked.current and is_top_view(page.route, view_path):
            asked.current = True
            open_picker()

    ft.use_effect(ask, [needs_session])
    loading = use_preload(owner, current.choice if current is not None else None)
    preload = loading.preload

    if current is None:
        return Reading(title=TITLE)
    if current.choice is None:
        return ScanScreen(
            title=TITLE,
            on_badge=partial(look_up, Inventory()),
            paused=NO_SESSION,
            actions=[choose_button(open_picker)],
        )
    return ScanScreen(
        title=TITLE,
        on_badge=partial(look_up, preload.inventory),
        context=ft.Column(
            [
                session_chip(current.choice, open_picker),
                status_line(
                    preload, on_retry=loading.retry, live=not prefs.announcements
                ),
            ],
            spacing=8,
        ),
        paused=status_words(preload) if preload.loaded is None else None,
    )


async def look_up(inventory: Inventory, badge: Badge) -> ScanResult:
    """The interim ``on_badge``: whether the badge is on the list; checks nobody in.

    "Badge read" with the name (or the code) and "On the attendee list", or the code
    and "Not on the attendee list", then "Not checked in yet". #766 swaps in admission.

    Args:
        inventory: The attendee list as loaded.
        badge: The badge scanned or typed.
    """
    attendee = inventory.attendees.get(badge.code)
    if attendee is not None:
        title, first = attendee.name or badge.code, ON_LIST
    else:
        title, first = badge.code, NOT_ON_LIST
    return ScanResult(
        ScanOutcome.ACCEPTED,
        BADGE_READ,
        title,
        (first, NOT_CHECKED_IN),
        code=badge.code,
    )


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
