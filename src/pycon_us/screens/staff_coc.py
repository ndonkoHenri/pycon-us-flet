"""The CoC incident tool (``/more/staff/coc``): the scan screen and its attendee directory.

The shared scan screen (``ui/scan_screen.py``, D-416) headed by the state of the
attendee directory (MASK-01, #759). The route re-checks its rule on every render
(architecture §12.4): an account without ``mask_violation``, a signed-out session or
no mock URL (D-51) sees "Not available for this account". It is mounted at
``/now/staff/coc`` too and records itself as the last tool opened (D-421); its entry
waits for #760, so More and Now list it only then.

**The directory** is fetched as the screen mounts (``conduct.fetch_directory()``) and
kept in ``CocTool``'s state only: never in a store, never in storage, never in a log
(D-56, D-72). It goes when the screen unmounts (leaving the tool, a sign-out, losing
the flag), and Reload fetches it again (D-432). A status line above the camera area
says where it is: "Loading attendee directory…" with a ring, "2,431 attendees" with
Reload (``coc.directory.reload``), "Couldn't load the attendee list" with Retry
(``coc.directory.retry``), or "Not available for this account" on a 403. The line is
a live region (on iOS, an announcement), so the count and the error are said once.

**Online only** (D-56): while ``use_online()`` says the device is offline, scanning is
paused with "CoC capture needs a connection", and Retry and Reload are disabled with
that reason.

**The scan, for now:** a badge is looked up in the directory and a neutral result
shows the name and the incidents on record, or the code and "Not in the attendee
directory", then "Not recorded yet". Nothing is sent: #760 swaps in recording.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from functools import partial
from typing import Literal

import flet as ft

from pycon_us.account import use_account
from pycon_us.conduct import fetch_directory
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.conduct import Attendee, count_words, display_name
from pycon_us.core.staff_tools import TOOLS, ToolKey, may_open
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.api import ApiError, NetworkError
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.ui.online import use_online
from pycon_us.ui.scan_feedback import ANNOUNCE_WAIT_S
from pycon_us.ui.scan_screen import NOT_AVAILABLE, NotAvailable, ScanScreen
from pycon_us.ui.semantics import named

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.COC)
"""The app bar's title, "CoC incident", as the staff entry points name it."""

LOADING = "Loading attendee directory…"
NOT_LOADED = "Couldn't load the attendee list"
RETRY = "Retry"
RELOAD = "Reload attendee directory"
OFFLINE = "CoC capture needs a connection"
"""Why scanning is paused, and Retry and Reload disabled, while offline (D-56)."""

BADGE_READ = "Badge read"
NOT_RECORDED = "Not recorded yet"
UNKNOWN = "Not in the attendee directory"
NO_DIRECTORY = "Attendee directory not loaded"
"""The interim result's words until #760 records (D-416's "Badge read")."""

FORBIDDEN = 403
"""The mock's answer for an account without ``mask_violation``."""

type Status = Literal["loading", "loaded", "failed", "refused"]


@dataclass(frozen=True)
class Directory:
    """Where the attendee directory's fetch is, for the account it was fetched for.

    Attributes:
        owner: The account it was fetched for; another's never stands (D-423's rule).
        status: Loading, loaded, failed (no answer or an error) or refused (a 403).
        by_code: The attendees by access code, once loaded.
    """

    owner: str
    status: Status
    by_code: dict[str, Attendee]


@ft.component
def CocScanner() -> ft.Control:
    """The CoC incident tool, or its "Not available" state for an account it refuses."""
    prefs = use_prefs()
    account = use_account()
    memory = use_services().memory
    allowed = (
        prefs.private_api_enabled
        and account.signed_in
        and may_open(ToolKey.COC, account.role_flags)
    )
    if not allowed:
        return NotAvailable(title=TITLE)
    memory.staff_tool = ToolKey.COC  # plain: Now's card reads it when it renders
    return CocTool(owner=account.owner)


@ft.component
def CocTool(*, owner: str) -> ft.Control:
    """The scan screen, headed by the directory's status line (MASK-01, D-432).

    The directory is fetched on mount and on Retry or Reload, as a coroutine effect
    that Flet cancels on unmount (D-70), and lives in this component's state alone.

    Args:
        owner: The signed-in account (``Account.owner``).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    online = use_online(svc, watch=True)
    directory, set_directory = ft.use_state(not_fetched)
    tries, set_tries = ft.use_state(0)  # Retry and Reload ask again
    mounted = ft.use_ref(True)  # cleared on unmount: a late answer is then dropped

    @report_errors
    def unmount() -> None:
        """Mark the screen gone, so a fetch still running sets nothing."""
        mounted.current = False

    ft.use_effect(lambda: None, [], cleanup=unmount)

    @report_errors
    async def load() -> None:
        set_directory(Directory(owner, "loading", {}))
        try:
            if svc.api is None:  # the URL went meanwhile; the guard follows
                raise NetworkError("no mock client")
            attendees = await fetch_directory(svc.api)
        except ApiError as error:  # nothing logged: CoC stays out of the log (D-72)
            refused = error.status == FORBIDDEN
            fetched = Directory(owner, "refused" if refused else "failed", {})
        except NetworkError:
            fetched = Directory(owner, "failed", {})
        else:
            fetched = Directory(owner, "loaded", {a.code: a for a in attendees})
        if mounted.current:
            set_directory(fetched)

    ft.use_effect(load, [owner, tries])
    current = (
        directory
        if directory is not None and directory.owner == owner
        else Directory(owner, "loading", {})
    )
    words = status_words(current)

    @report_errors
    async def say() -> None:
        # VoiceOver has no live regions: iOS hears the count or the error this way.
        if not (prefs.announcements and current.status != "loading"):
            return
        if mounted.current and is_top_view(page.route, view_path):
            # Sent at once; only the answer, which iOS may never give, is waited for
            # (F276). A failure leaves the line, which shows it all the same.
            with contextlib.suppress(*SERVICE_ERRORS):
                said = svc.semantics.announce_message(words)
                await asyncio.wait_for(said, ANNOUNCE_WAIT_S)

    ft.use_effect(say, [words])

    @report_errors
    def again() -> None:
        set_tries(tries + 1)

    if not online:
        paused = OFFLINE
    elif current.status == "refused":
        paused = NOT_AVAILABLE
    else:
        paused = None
    return ScanScreen(
        title=TITLE,
        on_badge=partial(look_up, current),
        context=status_line(
            current.status,
            words,
            on_again=again,
            online=online,
            live=not prefs.announcements,
        ),
        paused=paused,
    )


def not_fetched() -> Directory | None:
    """Return None: nothing fetched yet, ``CocTool``'s first state (typed)."""
    return None


def status_words(directory: Directory) -> str:
    """Return the status line's words: "Loading attendee directory…", "2,431 attendees".

    Args:
        directory: Where the fetch is.
    """
    match directory.status:
        case "loading":
            return LOADING
        case "loaded":
            count = len(directory.by_code)
            return f"{count:,} attendee" + ("" if count == 1 else "s")
        case "failed":
            return NOT_LOADED
        case "refused":
            return NOT_AVAILABLE


async def look_up(directory: Directory, badge: Badge) -> ScanResult:
    """The interim ``on_badge``: ``neutral_result()`` for the badge's code; sends nothing.

    Args:
        directory: The directory as the screen holds it.
        badge: The badge scanned or typed.
    """
    return neutral_result(badge.code, directory)


def neutral_result(code: str, directory: Directory) -> ScanResult:
    """Return the interim result of a scan: what the directory says, nothing sent.

    Accepted-styled "Badge read", as D-416's parse-only handler was, until #760
    records: the name and the incidents in words for a known code; the code and
    "Not in the attendee directory" for another; the code and "Attendee directory
    not loaded" before it is.

    Args:
        code: The badge's access code.
        directory: The directory as the screen holds it.
    """
    attendee = directory.by_code.get(code)
    if attendee is not None:
        title, first = display_name(attendee), count_words(attendee.incidents)
    elif directory.status == "loaded":
        title, first = code, UNKNOWN
    else:
        title, first = code, NO_DIRECTORY
    return ScanResult(
        ScanOutcome.ACCEPTED, BADGE_READ, title, (first, NOT_RECORDED), code=code
    )


def status_line(
    status: Status,
    words: str,
    *,
    on_again: ft.ControlEventHandler,
    online: bool,
    live: bool,
) -> ft.Control:
    """Return the line above the camera area: the directory's state and its button.

    A ring while loading, Reload once loaded, Retry after a failure, nothing after a
    refusal. The words wrap (200 % text); the buttons are 48 dp and named, and
    offline they are disabled, their name saying why.

    Args:
        status: Where the fetch is.
        words: What the line says (``status_words()``).
        on_again: Fetches the directory again.
        online: Whether the device has a connection.
        live: Whether the words are a live region (not where iOS announces).
    """
    lead: list[ft.Control] = []
    if status == "loading":
        lead.append(
            ft.Container(
                ft.ProgressRing(width=16, height=16, stroke_width=2), padding=4
            )
        )
    text = ft.Semantics(
        identifier="coc.directory",
        container=True,
        live_region=live,
        label=words,
        exclude_semantics=True,  # the label says it, once
        content=ft.Text(
            words,
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        expand=True,
    )
    why = "" if online else f". {OFFLINE}"
    trail: list[ft.Control] = []
    if status == "loaded":
        trail.append(
            named(
                "coc.directory.reload",
                ft.IconButton(
                    ft.Icons.REFRESH,
                    tooltip=RELOAD + why,
                    on_click=on_again,
                    disabled=not online,
                ),
            )
        )
    elif status == "failed":
        retry: ft.Control = ft.TextButton(RETRY, on_click=on_again, disabled=not online)
        if not online:  # a disabled button's tooltip is not read: name it with why
            retry = ft.Semantics(
                label=RETRY + why,
                button=True,
                disabled=True,
                exclude_semantics=True,
                content=retry,
            )
        trail.append(named("coc.directory.retry", retry))
    return ft.Row(
        [*lead, text, *trail],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
