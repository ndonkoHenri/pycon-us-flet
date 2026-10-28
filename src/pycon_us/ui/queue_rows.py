"""The queue sheet's parts: its rows, headings, lines and buttons (#694).

``ui/queue_sheet.py`` reads the outbox and lays the sheet out; here is what it is made
of, so each module stays under about 400 lines (D-66): ``row_tile()``, one outbox row
with its icon and word (``core.outbox.status_text()``: Queued, Failed, Confirmed, and
"may be recorded twice" with a warning icon beside it, D-410), its kind and access
code, when it was scanned and a failed row's last error; ``sync_button()`` and
``retry_button()``; ``heading()``, ``note()`` and ``empty_line()``.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import flet as ft

from pycon_us.core.outbox import Kind, Row, Status, status_text
from pycon_us.core.timefmt import ago_label
from pycon_us.theme import Tokens
from pycon_us.ui.buttons import ICON_PADDING, LABEL_PADDING
from pycon_us.ui.semantics import named

SYNC_NOW = "staff.queue.sync_now"
RETRY_FAILED = "staff.queue.retry_failed"

KIND_WORDS = {Kind.LEAD: "Lead", Kind.NOTE: "Lead note", Kind.DOOR: "Check-in"}
"""What each row records, as its title says it."""

EMPTY = "Everything is synced"
"""The sheet's line when none of the account's rows waits."""


def ago(at: float, now: float) -> str:
    """Return how long before ``now`` an epoch time was: "just now", "5 minutes ago"."""
    return ago_label(datetime.fromtimestamp(at, UTC), datetime.fromtimestamp(now, UTC))


def row_tile(row: Row, now: float, tokens: Tokens) -> ft.Control:
    """Return one row: its icon, kind and code, its status and age, its last error.

    One node (ux.md §9), e.g. "Lead · A1B2C3, Failed · 2 minutes ago, Not found".
    The icons are decorative: the words say the state, the flag included. Only the
    access code is shown, never a name or the badge's validator (LEAD-08).

    Args:
        row: An outbox row.
        now: The current time (epoch seconds).
        tokens: The scheme's tokens.
    """
    icon = {
        Status.PENDING: ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED),
        Status.FAILED: ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR),
        Status.SYNCED: ft.Icon(ft.Icons.CLOUD_DONE_OUTLINED, color=tokens.success),
    }[row.status]
    lines: list[ft.Control] = [
        ft.Text(f"{status_text(row)} · {ago(row.created_at, now)}")
    ]
    if row.status is Status.FAILED and row.last_error:
        lines.append(ft.Text(row.last_error, color=ft.Colors.ON_SURFACE_VARIANT))
    flag = ft.Icon(ft.Icons.WARNING_AMBER, color=tokens.warning)
    return named(
        f"staff.queue.row.{row.id}",
        ft.ListTile(
            leading=icon,
            title=ft.Text(f"{KIND_WORDS[row.kind]} · {row.key}"),
            subtitle=ft.Column(lines, spacing=2, tight=True),
            trailing=flag if row.maybe_sent else None,
            # The sheet's 16 dp gutters are the sides.
            content_padding=ft.Padding.symmetric(horizontal=0),
        ),
    )


def heading(text: str, level: int) -> ft.Control:
    """Return a heading of the sheet, a node a screen reader can jump to (D-211).

    Args:
        text: The heading.
        level: 1 for the sheet's title (a page of its own for a screen reader, as the
            filter sheet's), 2 for a section, 3 for an account inside one.
    """
    title = level == 1
    return ft.Semantics(
        header=True,
        heading_level=level,
        content=ft.Container(
            ft.Text(
                text,
                theme_style=ft.TextThemeStyle.TITLE_LARGE
                if title
                else ft.TextThemeStyle.TITLE_SMALL,
                color=None if title else ft.Colors.PRIMARY,
            ),
            padding=ft.Padding.only(top=0 if title else 16, bottom=4),
        ),
    )


def note(text: str, *, identifier: str | None = None) -> ft.Control:
    """Return a line of the sheet in ``BODY_MEDIUM`` and ``on_surface_variant``.

    Args:
        text: The words.
        identifier: For UI flows, e.g. ``staff.queue.blocked``.
    """
    line = ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    if identifier is None:
        return line
    return ft.Semantics(identifier=identifier, content=line)


def sync_button(
    *, busy: bool, disabled: bool, on_click: Callable[[], object]
) -> ft.Control:
    """Return Sync now: disabled with a ring and "Syncing…" while a pass runs.

    The words change with the ring, so a screen reader says the busy state, as Sign
    in's button does; disabled, it takes no second tap.

    Args:
        busy: A pass runs (``Staff.syncing``).
        disabled: It can't send now, or was tapped and its pass hasn't reported.
        on_click: Kicks the worker.
    """
    label: ft.Control = (
        ft.Row(
            [
                ft.ProgressRing(width=16, height=16, stroke_width=2),
                ft.Text("Syncing…"),
            ],
            spacing=8,
            tight=True,
        )
        if busy
        else ft.Text("Sync now")
    )
    return named(
        SYNC_NOW,
        ft.FilledButton(
            content=label,
            on_click=on_click,
            disabled=busy or disabled,
            style=ft.ButtonStyle(padding=LABEL_PADDING),
            elevation=0,  # M3's filled button lies flat (ui/buttons.py)
        ),
    )


def retry_button(on_click: Callable[[], object]) -> ft.Control:
    """Return Retry failed, an outlined button with its icon.

    Args:
        on_click: Makes the failed rows pending again and kicks the worker.
    """
    return named(
        RETRY_FAILED,
        ft.OutlinedButton(
            "Retry failed",
            icon=ft.Icons.REPLAY,
            on_click=on_click,
            style=ft.ButtonStyle(padding=ICON_PADDING),
        ),
    )


def empty_line(tokens: Tokens) -> ft.Control:
    """Return "Everything is synced" beside a done cloud: none of the rows waits.

    Args:
        tokens: The scheme's tokens: the cloud is in ``success``.
    """
    return ft.Semantics(
        identifier="staff.queue.empty",
        content=ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.CLOUD_DONE_OUTLINED, color=tokens.success),
                    ft.Text(
                        EMPTY, theme_style=ft.TextThemeStyle.BODY_LARGE, expand=True
                    ),
                ],
                spacing=16,
            ),
            padding=ft.Padding.symmetric(vertical=16),
        ),
    )
