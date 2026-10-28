"""The staff sync chip: the outbox's state in a few words, which opens the queue sheet.

ux.md §7.2 (LEAD-13, API-10; #694). ``chip_words()`` says the signed-in account's rows
as ``Staff`` holds them: "All synced", "3 pending", "Offline · 3 queued" once the last
pass ended without an answer, "Syncing · 3 pending" while a pass runs, and "1 failed"
beside them while rows wait for "Retry failed". ``SyncChip()`` draws them on a chip
with an icon that matches, never colour alone (ux.md §9): the scan screen (#37) puts it
in its app bar, where a tap opens the queue sheet; Developer › Data's Staff queue row
shows it as its second line, the row being the button there (D-412).
"""

from collections.abc import Callable

import flet as ft

from pycon_us.staff import Staff
from pycon_us.theme import Tokens
from pycon_us.ui.semantics import named

IDENTIFIER = "staff.sync_chip"
"""The chip's semantics identifier, where it is a button of its own (D-33)."""

RING = 16
"""The ring's size while a pass runs: the chip's 18 dp icon, less its stroke."""


def chip_words(staff: Staff) -> str:
    """Return the outbox's state as the chip says it.

    The pending rows are "queued" while offline, as the scan's "Saved. Will sync when
    online." says, and "pending" otherwise; failed rows are counted after them. A pass
    under way is the retry, so it says "Syncing" even after an offline last pass.

    Args:
        staff: The ``Staff`` store.

    Returns:
        E.g. "All synced", "3 pending", "Offline · 3 queued", "Syncing · 3 pending"
        or "3 pending · 1 failed".
    """
    if not staff.pending and not staff.failed:
        return "Syncing…" if staff.syncing else "All synced"
    # ``offline`` stays set until the retry's pass reports, so a running pass wins.
    offline = staff.offline and not staff.syncing
    parts = []
    if staff.pending:
        parts.append(f"{staff.pending} {'queued' if offline else 'pending'}")
    if staff.failed:
        parts.append(f"{staff.failed} failed")
    lead = "Offline" if offline else "Syncing" if staff.syncing else None
    return " · ".join([lead, *parts] if lead else parts)


def chip_icon(staff: Staff, tokens: Tokens) -> ft.Control:
    """Return the chip's icon, decorative: the words carry the state (ux.md §9).

    A small ring while a pass runs (something moves while it runs, ux.md §4); else a
    failed row's error, offline's crossed cloud, a pending row's upload, or a done
    cloud in ``success``.

    Args:
        staff: The ``Staff`` store.
        tokens: The scheme's tokens.
    """
    if staff.syncing:
        return ft.ProgressRing(width=RING, height=RING, stroke_width=2)
    if staff.failed:
        return ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)
    if staff.offline and staff.pending:
        return ft.Icon(ft.Icons.CLOUD_OFF_OUTLINED)
    if staff.pending:
        return ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED)
    return ft.Icon(ft.Icons.CLOUD_DONE_OUTLINED, color=tokens.success)


def SyncChip(
    staff: Staff,
    *,
    tokens: Tokens,
    on_click: Callable[[], object],
    in_row: bool = False,
) -> ft.Control:
    """Return the sync chip: the icon and ``chip_words()``; a tap opens the sheet.

    On its own (the scan screen's app bar) it is a button, one node named by its
    words and carrying ``staff.sync_chip`` (``named()``). Inside a row that opens the
    sheet too (Developer's Staff queue row) it is the row's words alone for a screen
    reader: the row is the button. It keeps its action there all the same, since a
    chip without one is drawn disabled, faded below a readable contrast (seen on the
    iOS simulator, #694).

    Args:
        staff: The ``Staff`` store; the caller re-renders with it (``use_staff()``).
        tokens: The scheme's tokens.
        on_click: Opens the queue sheet, wrapped in ``report_errors`` by the caller.
        in_row: Whether a row around it is the button.
    """
    words = chip_words(staff)
    chip = ft.Chip(
        label=ft.Text(words), leading=chip_icon(staff, tokens), on_click=on_click
    )
    if in_row:
        return ft.Semantics(label=words, exclude_semantics=True, content=chip)
    return named(IDENTIFIER, chip)
