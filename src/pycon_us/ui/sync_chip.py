"""The staff sync chip: the outbox's state in a few words, which opens the queue sheet.

ux.md §7.2 (LEAD-13, API-10; #694). ``chip_words()`` says the signed-in account's rows
as ``Staff`` holds them: "All synced", "3 pending", "Offline · 3 queued" once the last
pass ended without an answer, "Syncing · 3 pending" while a pass runs, and "1 failed"
beside them while rows wait for "Retry failed". ``SyncChip()`` draws them on a chip
with an icon that matches, never colour alone (ux.md §9): the scan screen (#37) puts it
in its app bar, where a tap opens the queue sheet; Developer › Data's Staff queue row
shows it as its second line, the row being the button there (D-412). At large text the
scan screen puts it at the top of its body instead, drawn as the context chip, whose
words wrap (#752): Flutter's ``Chip`` keeps one line at a fixed height and clipped them.
"""

from collections.abc import Callable

import flet as ft

from pycon_us.staff import Staff
from pycon_us.theme import Tokens
from pycon_us.ui.semantics import named
from pycon_us.ui.staff_picker import context_chip

IDENTIFIER = "staff.sync_chip"
"""The chip's semantics identifier, where it is a button of its own (D-33)."""

ICON = 18
"""The chip's icon size, M3's for a chip."""

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
    cloud in ``success``. The icons are 18 dp and grow with the text, as the context
    chip's, which draws them at large text; a ``Chip`` sizes them so anyway.

    Args:
        staff: The ``Staff`` store.
        tokens: The scheme's tokens.
    """
    if staff.syncing:
        return ft.ProgressRing(width=RING, height=RING, stroke_width=2)
    if staff.failed:
        icon, color = ft.Icons.ERROR_OUTLINE, ft.Colors.ERROR
    elif staff.offline and staff.pending:
        icon, color = ft.Icons.CLOUD_OFF_OUTLINED, None
    elif staff.pending:
        icon, color = ft.Icons.CLOUD_UPLOAD_OUTLINED, None
    else:
        icon, color = ft.Icons.CLOUD_DONE_OUTLINED, tokens.success
    return ft.Icon(icon, color=color, size=ICON, apply_text_scaling=True)


def SyncChip(
    staff: Staff,
    *,
    tokens: Tokens,
    on_click: Callable[[], object],
    in_row: bool = False,
    large_text: bool = False,
) -> ft.Control:
    """Return the sync chip: the icon and ``chip_words()``; a tap opens the sheet.

    On its own (the scan screen's app bar) it is a button, one node named by its
    words and carrying ``staff.sync_chip`` (``named()``). At large text it is the same
    node drawn as the context chip (``context_chip()``), whose words wrap: a ``Chip``
    keeps one line at a fixed height, which clipped "All synced" at iOS's largest
    size (#752). Inside a row that opens the
    sheet too (Developer's Staff queue row) it is the row's words alone for a screen
    reader: the row is the button. It keeps its action there all the same, since a
    chip without one is drawn disabled, faded below a readable contrast (seen on the
    iOS simulator, #694).

    Args:
        staff: The ``Staff`` store; the caller re-renders with it (``use_staff()``).
        tokens: The scheme's tokens.
        on_click: Opens the queue sheet, wrapped in ``report_errors`` by the caller.
        in_row: Whether a row around it is the button.
        large_text: The text is large for the width (``Prefs.time_above``): the
            scan screen then puts the chip in its body, where it can wrap.
    """
    words = chip_words(staff)
    if large_text and not in_row:
        return context_chip(
            text=words,
            spoken=words,
            icon=chip_icon(staff, tokens),
            identifier=IDENTIFIER,
            on_click=lambda _: on_click(),
        )
    chip = ft.Chip(
        label=ft.Text(words), leading=chip_icon(staff, tokens), on_click=on_click
    )
    if in_row:
        return ft.Semantics(label=words, exclude_semantics=True, content=chip)
    return named(IDENTIFIER, chip)
