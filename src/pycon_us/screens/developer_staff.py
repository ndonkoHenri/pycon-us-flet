"""The Developer screen's Staff queue row, which opens the queue sheet (#694, D-412).

Until the scan screen (#37) mounts the sync chip in its app bar, Developer › Data hosts
the queue sheet: a **Staff queue** row (``developer.staff_queue``) whose second line is
the sync chip, showing the signed-in account's rows as ``Staff`` counts them, and how
many rows of other accounts wait; a tap opens the sheet, which lists those too
(architecture §12.1: a previous owner's unsynced rows are "visible in Developer"). The
row shows only while a mock API URL is set, as every staff feature (D-51), so an
install whose staff tools never run never opens ``outbox.db``.
"""

import flet as ft

from pycon_us.account import use_account
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.staff import use_staff
from pycon_us.theme import use_tokens
from pycon_us.ui.queue_sheet import use_queue_sheet
from pycon_us.ui.semantics import named
from pycon_us.ui.sync_chip import SyncChip

IDENTIFIER = "developer.staff_queue"


def others_waiting(db: OutboxDb, owner: str | None) -> int | None:
    """Return how many pending or failed rows other accounts than ``owner`` have.

    Args:
        db: The outbox.
        owner: The signed-in account's lower-cased email, or None signed out.

    Returns:
        The count, or None when the outbox could not be read (logged).
    """
    owners = db.owners_with_unsynced()
    if owners is None:
        return None
    total = 0
    for other in owners:
        if other != owner:
            counts = db.counts(other)
            if counts is None:
                return None
            total += counts.pending + counts.failed
    return total


def others_line(count: int | None) -> str | None:
    """Return the row's line about other accounts' rows, or None when none wait.

    E.g. "2 rows of other accounts waiting", or "Couldn't read the queue." (D-120).
    """
    if count is None:
        return "Couldn't read the queue."
    if not count:
        return None
    rows = "1 row" if count == 1 else f"{count} rows"
    return f"{rows} of other accounts waiting"


@ft.component
def StaffQueue() -> ft.Control:
    """The Staff queue row, or nothing without a mock API URL (D-51).

    One node with its identifier (``named()``): "Staff queue, 3 pending · 1 failed,
    2 rows of other accounts waiting". Signed out, the second line says so instead of
    the chip, which would say "All synced" of nobody's rows.
    """
    prefs = use_prefs()
    svc = use_services()
    staff = use_staff()
    account = use_account()
    tokens = use_tokens()
    open_sheet = use_queue_sheet(others=True)
    shown = prefs.private_api_enabled and svc.outbox is not None
    owner = account.owner if account.signed_in else None
    waiting = ft.use_memo(
        lambda: (
            others_waiting(svc.outbox, owner) if shown and svc.outbox is not None else 0
        ),
        [shown, owner, staff.revision],
    )
    if not shown:
        return ft.Column([], visible=False)
    lines: list[ft.Control] = [
        SyncChip(staff, tokens=tokens, on_click=open_sheet, in_row=True)
        if owner
        else ft.Text("Not signed in")
    ]
    extra = others_line(waiting)
    if extra is not None:
        lines.append(ft.Text(extra))
    return named(
        IDENTIFIER,
        ft.ListTile(
            leading=ft.Icon(ft.Icons.CLOUD_SYNC_OUTLINED),
            title=ft.Text("Staff queue"),
            subtitle=ft.Column(lines, spacing=4, tight=True),
            on_click=open_sheet,
            title_alignment=ft.ListTileTitleAlignment.TOP,
            min_vertical_padding=14,  # as action_row()'s (D-188)
        ),
    )
