"""The staff queue sheet: the outbox's unsynced rows, "Sync now" and "Retry failed".

ux.md §7.2 (LEAD-12, LEAD-13, API-10; #694). Failures must be visible, with Retry (P3
exit criterion 2): Ionic's pull-to-refresh synced only pending scans, never failed ones.

- ``read_queue()`` reads what the sheet lists from ``outbox-<year>.db``: the account's pending
  and failed rows, newest first, its latest confirmed rows, and, where the host asks
  (Developer, D-412), other accounts' unsynced rows, which wait for their own sign-in
  (architecture §12.1).
- ``queue_sheet()`` lays it out in a modal ``BottomSheet`` with a drag handle and a
  Close button: the
  state in words (``sync_chip.chip_words()``, a live region); **Sync now**, which kicks
  the worker and is disabled with a ring while a pass runs; **Retry failed**, only
  while rows have failed; the rows (``queue_rows.row_tile()``), or "Everything is
  synced"; the confirmed rows in a fold; other accounts' rows under their own heading.
- ``use_queue_sheet()`` is the hook a host calls: it keeps the sheet's state, shows it
  through ``ft.use_dialog`` and returns what opens it and whether it is open. The scan
  screen opens it from the sync chip and pauses scanning while it is open (#724),
  Developer › Data from its Staff queue row, with other accounts' rows (D-412, D-420).
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us.account import Account, use_account
from pycon_us.core.outbox import Row, Status
from pycon_us.prefs import use_prefs
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.sync import sync_target
from pycon_us.staff import Staff, use_staff
from pycon_us.theme import Tokens, use_tokens
from pycon_us.theme_hc import hc_sheet_shape
from pycon_us.ui.fold import FoldTile, expand_style
from pycon_us.ui.queue_rows import (
    ago,
    empty_line,
    heading,
    note,
    retry_button,
    row_tile,
    sync_button,
    title_row,
)
from pycon_us.ui.sync_chip import chip_words

CONFIRMED_SHOWN = 20
"""How many of the latest confirmed rows the fold lists."""

UNREADABLE = "Couldn't read the queue on this device."
"""The sheet's line when the outbox could not be read (D-120): never "Everything is
synced", which would be a guess."""


@dataclass(frozen=True)
class Queue:
    """What the sheet lists, as ``read_queue()`` found it.

    Attributes:
        mine: The account's pending and failed rows, newest first.
        confirmed: Its latest synced rows, newest first, at most ``CONFIRMED_SHOWN``.
        others: Other accounts' pending and failed rows, by owner, newest first.
        readable: Whether every read went through (D-120).
    """

    mine: tuple[Row, ...] = ()
    confirmed: tuple[Row, ...] = ()
    others: tuple[tuple[str, tuple[Row, ...]], ...] = ()
    readable: bool = True


def _newest(rows: Sequence[Row] | None) -> tuple[Row, ...]:
    """Return rows newest first; ``OutboxDb.rows()`` gives them oldest first."""
    return tuple(reversed(rows or ()))


def read_queue(db: OutboxDb, owner: str | None, *, others: bool) -> Queue:
    """Read what the sheet lists from the outbox.

    Args:
        db: The outbox.
        owner: The signed-in account's lower-cased email, or None signed out.
        others: Whether to list other accounts' unsynced rows too (Developer).

    Returns:
        The rows; ``readable`` is False when a read failed (logged by ``OutboxDb``).
    """
    unsynced = (Status.PENDING, Status.FAILED)
    mine = db.rows(owner, unsynced) if owner else []
    confirmed = db.rows(owner, (Status.SYNCED,)) if owner else []
    reads = [mine, confirmed]
    owners = db.owners_with_unsynced() if others else []
    others_rows: list[tuple[str, tuple[Row, ...]]] = []
    for other in owners or []:
        if other != owner:
            rows = db.rows(other, unsynced)
            reads.append(rows)
            others_rows.append((other, _newest(rows)))
    return Queue(
        mine=_newest(mine),
        confirmed=_newest(confirmed)[:CONFIRMED_SHOWN],
        others=tuple(others_rows),
        readable=owners is not None and all(rows is not None for rows in reads),
    )


def sync_blocked(svc: Services, account: Account) -> str | None:
    """Return why "Sync now" can't send, or None while a worker runs (D-407).

    Args:
        svc: The session's services: the client.
        account: The ``Account`` store.
    """
    if sync_target(svc, account) is not None:
        return None
    if svc.api is None:
        return "Set the mock API URL in Developer to sync."
    if account.expired:
        return "Your sign-in has expired. Sign in again to sync."
    return "Sign in to sync."


def summary(staff: Staff, now: float) -> str:
    """Return the line under the sheet's title: the state, and when it last synced.

    E.g. "Offline · 3 queued. Last synced 5 minutes ago." or "All synced."

    Args:
        staff: The ``Staff`` store.
        now: The current time (epoch seconds).
    """
    words = f"{chip_words(staff)}."
    if staff.last_sync_at is not None:
        words += f" Last synced {ago(staff.last_sync_at, now)}."
    return words


@dataclass(frozen=True)
class SheetState:
    """What the sheet shows beside its rows, from the host's state and the stores.

    Attributes:
        staff: The ``Staff`` store.
        now: The current time (epoch seconds).
        blocked: Why Sync now can't send (``sync_blocked()``), or None.
        asked: Sync now was tapped and its pass hasn't reported yet.
        confirmed_open: Whether the confirmed rows' fold is open.
    """

    staff: Staff
    now: float
    blocked: str | None = None
    asked: bool = False
    confirmed_open: bool = False


def queue_sheet(
    queue: Queue,
    state: SheetState,
    *,
    tokens: Tokens,
    style: ft.Animation,
    on_sync_now: Callable[[], object],
    on_retry_failed: Callable[[], object],
    on_confirmed: Callable[[bool], None],
    on_close: Callable[[], object],
    reduce_motion: bool = False,
) -> ft.BottomSheet:
    """Return the queue sheet (ux.md §7.2): the state, the two actions, the rows.

    Everything scrolls together, so at the largest text the rows keep the sheet.

    Args:
        queue: The rows (``read_queue()``).
        state: The state, the clock and Sync now's.
        tokens: The scheme's tokens; in high contrast a 1 dp edge draws the sheet.
        style: The fold's animation (``expand_style()``).
        on_sync_now: Kicks the worker.
        on_retry_failed: Makes the failed rows pending and kicks the worker.
        on_confirmed: Opens or closes the confirmed rows' fold.
        on_close: Close, and a dismissal: a swipe, Back.
        reduce_motion: The sheet appears without its slide (D-34, D-173).
    """
    staff, now = state.staff, state.now
    actions = [
        sync_button(
            busy=staff.syncing,
            disabled=state.asked or state.blocked is not None,
            on_click=on_sync_now,
        )
    ]
    if staff.failed or any(row.status is Status.FAILED for row in queue.mine):
        actions.append(retry_button(on_retry_failed))
    body: list[ft.Control] = [
        title_row(on_close),
        ft.Semantics(
            identifier="staff.queue.summary",
            live_region=True,  # each pass's outcome is said
            content=ft.Text(
                summary(staff, now), theme_style=ft.TextThemeStyle.BODY_MEDIUM
            ),
        ),
        ft.Container(
            ft.Row(actions, wrap=True, spacing=8, run_spacing=8),
            padding=ft.Padding.symmetric(vertical=8),
        ),
    ]
    if state.blocked is not None:
        body.append(note(state.blocked, identifier="staff.queue.blocked"))
    if not queue.readable:
        body.append(note(UNREADABLE, identifier="staff.queue.unreadable"))
    elif queue.mine:
        body.extend(row_tile(row, now, tokens) for row in queue.mine)
    else:
        body.append(empty_line(tokens))
    if queue.confirmed:
        body.append(
            FoldTile(
                ft.Text(f"Recently confirmed ({len(queue.confirmed)})"),
                [row_tile(row, now, tokens) for row in queue.confirmed],
                expanded=state.confirmed_open,
                on_change=on_confirmed,
                style=style,
                identifier="staff.queue.confirmed",
            )
        )
    if queue.others:
        body.append(heading("Other accounts", 2))
        body.append(note("Their rows sync when that account signs in again."))
        for owner, rows in queue.others:
            body.append(heading(owner, 3))
            body.extend(row_tile(row, now, tokens) for row in rows)
    return ft.BottomSheet(
        ft.Container(  # 16 dp gutters (ux.md §3.6), clear of the home bar
            padding=ft.Padding.only(left=16, right=16, bottom=16),
            content=ft.Column(
                body,
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ),
        show_drag_handle=True,
        scrollable=True,  # up to the screen's height: the rows have room at 200 %
        use_safe_area=True,
        shape=hc_sheet_shape(tokens.high_contrast),
        on_dismiss=lambda _: on_close(),
        # Its slide is motion: none under reduced motion (D-34, D-173).
        animation_style=ft.AnimationStyle.no_animation() if reduce_motion else None,
    )


def kick_once(
    kicked: MutableRef[int | None], staff: Staff, kick: Callable[[], object]
) -> bool:
    """Kick the worker for Sync now, once until its pass has reported (LEAD-12).

    ``kicked`` holds ``Staff.revision`` at the last kick; the pass's report bumps it.
    So a second tap before then, or a tap while a pass runs, sends no second kick,
    even from a render that hasn't disabled the button yet.

    Args:
        kicked: The host's ref: the revision at the last kick, or None.
        staff: The ``Staff`` store.
        kick: Wakes the worker (``Services.kick_sync``).

    Returns:
        Whether it kicked.
    """
    if staff.syncing or kicked.current == staff.revision:
        return False
    kicked.current = staff.revision
    kick()
    return True


@dataclass(frozen=True)
class QueueSheet:
    """What a host gets from ``use_queue_sheet()``.

    Attributes:
        open: Opens the sheet (a chip's or a row's tap).
        is_open: The sheet is open: the scan screen pauses scanning meanwhile.
    """

    open: Callable[[], None]
    is_open: bool


def use_queue_sheet(*, others: bool = False) -> QueueSheet:
    """Keep the queue sheet's state and show it while open; return what opens it.

    Call it on every render (D-70). While open, its rows are read again whenever the
    outbox changes (``Staff.revision``), and the host re-renders with ``Staff``, so
    the sheet follows each pass.

    Args:
        others: List other accounts' unsynced rows too (Developer, D-412).
    """
    svc = use_services()
    staff = use_staff()
    account = use_account()
    prefs = use_prefs()
    tokens = use_tokens()
    is_open, set_open = ft.use_state(False)
    confirmed_open, set_confirmed_open = ft.use_state(False)
    kicked: MutableRef[int | None] = ft.use_ref(None)
    _, set_kicked_at = ft.use_state(-1)  # a re-render, so Sync now disables at once
    owner = account.owner if account.signed_in else None
    queue = ft.use_memo(
        lambda: (
            read_queue(svc.outbox, owner, others=others)
            if is_open and svc.outbox is not None
            else Queue()
        ),
        [is_open, owner, staff.revision, others],
    )

    @report_errors
    def open_sheet() -> None:
        set_open(True)

    @report_errors
    def close_sheet() -> None:
        set_open(False)

    @report_errors
    def sync_now() -> None:
        if owner is not None and svc.outbox is not None:  # no backoff waits (D-414)
            svc.outbox.due_now(owner, time.time())
        if kick_once(kicked, staff, svc.kick_sync):
            set_kicked_at(staff.revision)

    @report_errors
    def retry_failed() -> None:
        if owner is not None and svc.outbox is not None:
            staff.retry_failed(svc.outbox, owner, time.time())
            svc.kick_sync()

    ft.use_dialog(
        queue_sheet(
            queue,
            SheetState(
                staff,
                time.time(),
                blocked=sync_blocked(svc, account),
                asked=kicked.current == staff.revision,
                confirmed_open=confirmed_open,
            ),
            tokens=tokens,
            style=expand_style(prefs),
            on_sync_now=sync_now,
            on_retry_failed=retry_failed,
            on_confirmed=set_confirmed_open,
            on_close=close_sheet,
            reduce_motion=prefs.reduce_motion,
        )
        if is_open
        else None
    )
    return QueueSheet(open_sheet, is_open)
