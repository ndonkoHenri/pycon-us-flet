"""The CoC incident tool (``/more/staff/coc``): the scan screen and its attendee directory.

The shared scan screen (``ui/scan_screen.py``, D-416) headed by the state of the
attendee directory (MASK-01, #759). The route re-checks its rule on every render
(architecture §12.4): an account without ``mask_violation``, a signed-out session or
no mock URL (D-51) sees "Not available for this account". It is mounted at
``/now/staff/coc`` too and records itself as the last tool opened (D-421), and More
and Now list it (``BUILT_TOOLS``, #760).

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

**A scan** opens the review dialog (``ui/coc_review.py``, #760; MASK-04) for the
badge's code with its directory row, or without one: a code the loaded directory
lacks is reviewed all the same (D-434). The handler awaits the dialog, so scanning is
paused while it is open ("Paused while the review is open") and resumes in the field
after it closes; the panel then says "Incident recorded" with the reply's count, or
"Not recorded". Each record's count updates the directory's row.

**Find by name** (``ui/coc_search.py``, #761; MASK-02, D-439) opens the name search
over the loaded directory, disabled with its reason before it has loaded or offline;
scanning is paused while it is open ("Paused while the search is open"). A row's tap
opens the same review, and its result reaches the panel as ``ScanScreen``'s
``posted``, since no badge was scanned.

**Clearing** (#762, MASK-05, O-7): a result clears 15 s after it shows and when the
app goes to the background, which also closes the search with its query; an open
review stays, with its notes (losing a half-written report is worse, and the dialog
shows no email). "Show email" reveals a recorded result's email (``ui/coc_email.py``).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from functools import partial
from typing import Literal

import flet as ft

from pycon_us.account import use_account
from pycon_us.conduct import fetch_directory
from pycon_us.core.badges import Badge, ScanResult
from pycon_us.core.conduct import Attendee
from pycon_us.core.staff_tools import TOOLS, ToolKey
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.api import ApiError, NetworkError
from pycon_us.services.errors import report_errors
from pycon_us.ui.coc_email import email_actions, email_note
from pycon_us.ui.coc_review import use_review
from pycon_us.ui.coc_search import SEARCH_OPEN, use_find
from pycon_us.ui.coc_search_sheet import find_button
from pycon_us.ui.online import use_online
from pycon_us.ui.scan_clear import use_on_background
from pycon_us.ui.scan_result import Posted, post
from pycon_us.ui.scan_screen import (
    NOT_AVAILABLE,
    NotAvailable,
    ScanScreen,
    use_tool_allowed,
)
from pycon_us.ui.semantics import announce, named

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.COC)
"""The app bar's title, "CoC incident", as the staff entry points name it."""

LOADING = "Loading attendee directory…"
NOT_LOADED = "Couldn't load the attendee list"
RETRY = "Retry"
RELOAD = "Reload attendee directory"
OFFLINE = "CoC capture needs a connection"
"""Why scanning is paused, and Retry and Reload disabled, while offline (D-56)."""

REVIEW_OPEN = "Paused while the review is open"
"""Why scanning is paused while the review dialog is open (MASK-04)."""

CLEAR_AFTER = 15
"""Seconds a result stays on the panel once it shows (O-7, MASK-05)."""

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
    allowed = use_tool_allowed(ToolKey.COC)
    account = use_account()
    memory = use_services().memory
    if not allowed:
        return NotAvailable(title=TITLE, source=__name__)
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
            await announce(svc.semantics, words)

    ft.use_effect(say, [words])

    @report_errors
    def again() -> None:
        set_tries(tries + 1)

    @report_errors
    def counted(code: str, incidents: int | None) -> None:
        """Set the directory's row for ``code`` to the count a record answered."""
        if incidents is not None:
            set_directory(lambda last: with_count(last, code, incidents))

    review = use_review(on_recorded=counted)
    posted, set_posted = ft.use_state(not_posted)

    @report_errors
    async def picked(attendee: Attendee) -> None:
        """Review the attendee found by name; its result goes to the panel."""
        result = await review.open(attendee.code, attendee)
        if mounted.current:
            set_posted(lambda last: post(last, result))

    finder = use_find(attendees=current.by_code, on_pick=picked)
    use_on_background(finder.close)  # the query goes too; an open review stays
    revealed, set_revealed = ft.use_state(0)  # whose email shows: a result's serial
    if review.is_open:
        paused = REVIEW_OPEN
    elif finder.is_open:
        paused = SEARCH_OPEN
    elif not online:
        paused = OFFLINE
    elif current.status == "refused":
        paused = NOT_AVAILABLE
    else:
        paused = None
    return ScanScreen(
        title=TITLE,
        source=__name__,
        on_badge=partial(review_badge, review.open, current),
        context=status_line(
            current.status,
            words,
            on_again=again,
            online=online,
            live=not prefs.announcements,
        ),
        actions=[find_button(find_reason(current, words, online), finder.open)],
        paused=paused,
        result_actions=partial(email_actions, revealed=revealed, reveal=set_revealed),
        result_note=partial(email_note, revealed=revealed),
        posted=posted,
        clear_after=CLEAR_AFTER,
        clear_in_background=True,
    )


def not_posted() -> Posted | None:
    """Return None: nothing recorded by name yet (a typed default)."""
    return None


def find_reason(directory: Directory, words: str, online: bool) -> str | None:
    """Return why Find by name is disabled now, or None once it can search.

    Args:
        directory: Where the fetch is: the search needs it loaded.
        words: The status line's words, the reason while it isn't.
        online: Whether the device has a connection (D-56).
    """
    if not online:
        return OFFLINE
    return None if directory.status == "loaded" else words


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


async def review_badge(
    open_review: Callable[[str, Attendee | None], Awaitable[ScanResult]],
    directory: Directory,
    badge: Badge,
) -> ScanResult:
    """The tool's ``on_badge``: open the review for the badge, return how it ended.

    Args:
        open_review: ``use_review()``'s ``open``.
        directory: The directory as the screen holds it: the badge's row, if any.
        badge: The badge scanned or typed.
    """
    return await open_review(badge.code, directory.by_code.get(badge.code))


def with_count(
    directory: Directory | None, code: str, incidents: int
) -> Directory | None:
    """Return ``directory`` with ``code``'s row at the count a record answered.

    A code it lacks stays out: the next Reload brings it (D-432, D-434).

    Args:
        directory: The directory as the screen holds it, or None before a fetch.
        code: The access code the incident was recorded for.
        incidents: The count the reply gave.
    """
    if directory is None or code not in directory.by_code:
        return directory
    by_code = dict(directory.by_code)
    by_code[code] = replace(by_code[code], incidents=incidents)
    return replace(directory, by_code=by_code)


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
