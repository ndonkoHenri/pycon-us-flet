"""The queue sheet's parts: its rows, headings, lines and buttons (#694).

`ui/queue_sheet.py` reads the outbox and lays the sheet out; here is what it is made
of, so each module stays under about 400 lines (D-66): `row_tile()`, one outbox row
with its icon and word (`core.outbox.status_text()`: Queued, Failed, Confirmed, and
"may be recorded twice" with a warning icon beside it, D-410), its kind and access
code, when it was scanned, the sponsor of a staff account's lead or note (D-459) and a
failed row's last error (`status_icon()`, the leads list's too, #743); a check-in the server answered with `errors` reads "Confirmed ·
Already redeemed", flagged too, with the server's messages (D-441); `sync_button()` and `retry_button()`; `title_row()` with
Close, `heading()`, `note()` and `empty_line()`.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import flet as ft

from pycon_us.core.admission import redeem_errors
from pycon_us.core.lead_views import for_line
from pycon_us.core.outbox import Kind, Row, Status, status_text
from pycon_us.core.timefmt import ago_label
from pycon_us.theme import Tokens
from pycon_us.ui.buttons import ICON_PADDING, LABEL_PADDING, busy_label
from pycon_us.ui.semantics import named

SYNC_NOW = "staff.queue.sync_now"
RETRY_FAILED = "staff.queue.retry_failed"
CLOSE = "staff.queue.close"

KIND_WORDS = {Kind.LEAD: "Lead", Kind.NOTE: "Lead note", Kind.DOOR: "Check-in"}
"""What each row records, as its title says it."""

ALREADY_REDEEMED = "Already redeemed"
"""What a synced check-in's status adds when the server's reply had errors (D-441)."""

EMPTY = "Everything is synced"
"""The sheet's line when none of the account's rows waits."""


def ago(at: float, now: float) -> str:
    """Return how long before `now` an epoch time was: "just now", "5 minutes ago"."""
    return ago_label(datetime.fromtimestamp(at, UTC), datetime.fromtimestamp(now, UTC))


def status_icon(status: Status, tokens: Tokens) -> ft.Icon:
    """Return a status's icon, decorative beside its words: queued, failed or confirmed.

    Args:
        status: The row's status.
        tokens: The scheme's tokens: a confirmed row's cloud is in `success`.
    """
    match status:
        case Status.PENDING:
            return ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED)
        case Status.FAILED:
            return ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.ERROR)
        case Status.SYNCED:
            return ft.Icon(ft.Icons.CLOUD_DONE_OUTLINED, color=tokens.success)


def row_tile(row: Row, now: float, tokens: Tokens) -> ft.Control:
    """Return one row: its icon, kind and code, its status, age, sponsor and last error.

    One node (ux.md §9), e.g. "Lead · A1B2C3, Failed · 2 minutes ago, For Example Corp,
    Not found", so two sponsors' leads on one attendee are told apart (D-459). The
    icons are decorative: the words say the state, the flag included. Only the access
    code is shown, never a name or the badge's validator (LEAD-08).

    Args:
        row: An outbox row.
        now: The current time (epoch seconds).
        tokens: The scheme's tokens.
    """
    icon = status_icon(row.status, tokens)
    refused = redeem_errors(row)  # the person is in; resending can't change it
    status = f"{status_text(row)} · {ALREADY_REDEEMED}" if refused else status_text(row)
    lines: list[ft.Control] = [ft.Text(f"{status} · {ago(row.created_at, now)}")]
    if row.sponsor_name:
        words = for_line(row.sponsor_name)
        lines.append(ft.Text(words, color=ft.Colors.ON_SURFACE_VARIANT))
    reason = "; ".join(refused) if refused else row.last_error
    if reason and (refused or row.status is Status.FAILED):
        lines.append(ft.Text(reason, color=ft.Colors.ON_SURFACE_VARIANT))
    flag = ft.Icon(ft.Icons.WARNING_AMBER, color=tokens.warning)
    return named(
        f"staff.queue.row.{row.id}",
        ft.ListTile(
            leading=icon,
            title=ft.Text(f"{KIND_WORDS[row.kind]} · {row.key}"),
            subtitle=ft.Column(lines, spacing=2, tight=True),
            trailing=flag if row.maybe_sent or refused else None,
            # The sheet's 16 dp gutters are the sides.
            content_padding=ft.Padding.symmetric(horizontal=0),
        ),
    )


def title_row(
    on_close: Callable[[], object],
    *,
    title: str = "Sync queue",
    identifier: str = CLOSE,
) -> ft.Control:
    """Return the sheet's title, "Sync queue", with a Close button at its end.

    The sheet is as tall as the screen, so no scrim is left to tap, and iOS has no
    Back key: Close is the way out besides dragging the handle (seen on the iOS
    simulator, #694). Its tooltip names it, merged into its node (`named()`). The
    CoC name search's sheet has the same head (#761).

    Args:
        on_close: Closes the sheet.
        title: The sheet's level-1 heading.
        identifier: The Close button's identifier.
    """
    return ft.Row(
        [
            ft.Container(heading(title, 1), expand=True),
            named(
                identifier,
                ft.IconButton(ft.Icons.CLOSE, tooltip="Close", on_click=on_close),
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.START,
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
    """Return a line of the sheet in `BODY_MEDIUM` and `on_surface_variant`.

    Args:
        text: The words.
        identifier: For UI flows, e.g. `staff.queue.blocked`.
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
    *,
    busy: bool,
    disabled: bool,
    on_click: Callable[[], object],
    identifier: str = SYNC_NOW,
) -> ft.Control:
    """Return Sync now: disabled with a ring and "Syncing…" while a pass runs.

    The words change with the ring, so a screen reader says the busy state, as Sign
    in's button does; disabled, it takes no second tap.

    Args:
        busy: A pass runs (`Staff.syncing`).
        disabled: It can't send now, or was tapped and its pass hasn't reported.
        on_click: Kicks the worker.
        identifier: Its identifier: the sheet's, or sign-out's dialog's (D-414).
    """
    return named(
        identifier,
        ft.FilledButton(
            content=busy_label("Syncing…") if busy else ft.Text("Sync now"),
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
        tokens: The scheme's tokens: the cloud is in `success`.
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
