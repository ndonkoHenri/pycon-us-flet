"""The Account page's Sign out: its button and its confirmation (SHELL-13, AUTH-11).

``sign_out_button()`` is disabled with a ring while Sign out first tries to send My
schedule's unsent changes (``FavoritesSync.flush()``, D-411); ``sign_out_dialog()``
then asks, naming what stays and, when the try failed, what has not reached the
account. Apart from ``account.py`` so that the page stays under about 400 lines (D-66),
as Developer's confirmations are in ``developer_ui.py``. With unsynced staff rows the
dialog asks "3 scans haven't synced. Sign out anyway?" and offers Sync now (D-414).
"""

from collections.abc import Callable
from typing import Any

import flet as ft

from pycon_us.ui.buttons import ICON_PADDING, busy_label
from pycon_us.ui.queue_rows import sync_button
from pycon_us.ui.semantics import named

SIGN_OUT_TITLE = "Sign out?"
SIGN_OUT_BODY = "Your saved sessions stay on this device."
UNSYNCED = "Your latest changes to My schedule haven't reached your account yet."
"""The dialog's extra line when the try before it could not send them (D-411)."""

SCANS_STAY = (
    "They stay on this device and sync when you sign in again with this account."
)
"""The unsynced variant's first line: sign-out never deletes a row (D-414)."""

SIGNED_OUT = "Signed out"
SIGNED_OUT_PARTLY = "Signed out, but some sign-in data couldn't be deleted."
"""The SnackBar when a removal failed (D-120): the next start clears what is left."""


def sign_out_button(
    *, syncing: bool, on_click: ft.ControlEventHandler[ft.OutlinedButton]
) -> ft.Control:
    """Return Sign out: disabled with a ring while it tries to send My schedule first."""
    return named(
        "account.sign_out",
        ft.OutlinedButton(
            content=busy_label("Syncing My schedule…")
            if syncing
            else ft.Text("Sign out"),
            icon=None if syncing else ft.Icons.LOGOUT,
            on_click=on_click,
            disabled=syncing,
            style=ft.ButtonStyle(padding=ICON_PADDING),
        ),
    )


def scans_line(count: int) -> str:
    """Return the unsynced variant's title, e.g. "3 scans haven't synced. Sign out anyway?"."""
    scans = "1 scan hasn't" if count == 1 else f"{count} scans haven't"
    return f"{scans} synced. Sign out anyway?"


def sign_out_dialog(
    *,
    synced: bool,
    unsynced: int = 0,
    syncing: bool = False,
    blocked: str | None = None,
    on_confirm: Callable[[], Any],
    on_cancel: Callable[[], Any],
    on_sync_now: Callable[[], Any],
) -> ft.AlertDialog:
    """Return the sign-out confirmation, naming what stays and what didn't sync.

    Modal, so only its buttons or Back close it (Back cancels, D-208), and scrollable,
    so its words and buttons stay reachable at 200 % text. With unsynced staff rows it
    asks "3 scans haven't synced. Sign out anyway?", says they stay, offers Sync now
    and signs out with "Sign out anyway (3 unsynced)", in ``error``; once Sync now has
    sent them, it is the plain dialog again (D-414). Both variants add D-411's line
    when My schedule didn't reach the account.

    Args:
        synced: Whether My schedule reached the account before it opened (D-411).
        unsynced: The account's pending and failed staff rows, as ``Staff`` counts
            them now.
        syncing: A sync pass runs: Sync now is disabled with a ring.
        blocked: Why Sync now can't send (``queue_sheet.sync_blocked()``), said under
            it, or None.
        on_confirm: Signs out.
        on_cancel: Closes it; also called when Back dismisses it.
        on_sync_now: Sends the rows, keeping the dialog open.
    """
    lines = [SIGN_OUT_BODY] if synced else [SIGN_OUT_BODY, UNSYNCED]
    title, confirm = SIGN_OUT_TITLE, "Sign out"
    extra: list[ft.Control] = []
    if unsynced:
        title, confirm = scans_line(unsynced), f"Sign out anyway ({unsynced} unsynced)"
        lines.insert(0, SCANS_STAY)
        if blocked is not None:
            lines.append(blocked)
        extra.append(
            sync_button(
                busy=syncing,
                disabled=blocked is not None,
                on_click=on_sync_now,
                identifier="account.sign_out.sync_now",
            )
        )
    return ft.AlertDialog(
        modal=True,
        scrollable=True,
        icon=ft.Icon(ft.Icons.LOGOUT),
        title=ft.Text(title),
        content=ft.Column(
            [
                *(
                    ft.Text(
                        line,
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                    for line in lines
                ),
                *extra,
            ],
            tight=True,
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        ),
        actions=[
            named(
                "account.sign_out.cancel", ft.TextButton("Cancel", on_click=on_cancel)
            ),
            named(
                "account.sign_out.confirm",
                ft.TextButton(
                    confirm,
                    on_click=on_confirm,
                    style=ft.ButtonStyle(color=ft.Colors.ERROR) if unsynced else None,
                ),
            ),
        ],
        on_dismiss=on_cancel,
    )
