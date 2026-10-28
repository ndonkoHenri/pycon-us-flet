"""The Account page's Sign out: its button and its confirmation (SHELL-13, AUTH-11).

``sign_out_button()`` is disabled with a ring while Sign out first tries to send My
schedule's unsent changes (``FavoritesSync.flush()``, D-411); ``sign_out_dialog()``
then asks, naming what stays and, when the try failed, what has not reached the
account. Apart from ``account.py`` so that the page stays under about 400 lines (D-66),
as Developer's confirmations are in ``developer_ui.py``. The variant with unsynced
staff rows, "3 scans haven't synced", is #38's.
"""

from collections.abc import Callable
from typing import Any

import flet as ft

from pycon_us.ui.buttons import ICON_PADDING
from pycon_us.ui.semantics import named

SIGN_OUT_TITLE = "Sign out?"
SIGN_OUT_BODY = "Your saved sessions stay on this device."
UNSYNCED = "Your latest changes to My schedule haven't reached your account yet."
"""The dialog's extra line when the try before it could not send them (D-411)."""

SIGNED_OUT = "Signed out"
SIGNED_OUT_PARTLY = "Signed out, but some sign-in data couldn't be deleted."
"""The SnackBar when a removal failed (D-120): the next start clears what is left."""


def sign_out_button(
    *, syncing: bool, on_click: ft.ControlEventHandler[ft.OutlinedButton]
) -> ft.Control:
    """Return Sign out: disabled with a ring while it tries to send My schedule first."""
    label: ft.Control = (
        ft.Row(
            [
                ft.ProgressRing(width=16, height=16, stroke_width=2),
                ft.Text("Syncing My schedule…"),
            ],
            spacing=8,
            tight=True,
        )
        if syncing
        else ft.Text("Sign out")
    )
    return named(
        "account.sign_out",
        ft.OutlinedButton(
            content=label,
            icon=None if syncing else ft.Icons.LOGOUT,
            on_click=on_click,
            disabled=syncing,
            style=ft.ButtonStyle(padding=ICON_PADDING),
        ),
    )


def sign_out_dialog(
    *,
    synced: bool,
    on_confirm: Callable[[], Any],
    on_cancel: Callable[[], Any],
) -> ft.AlertDialog:
    """Return the sign-out confirmation, naming what stays and what didn't sync.

    Modal, so only its buttons or Back close it (Back cancels, D-208), and scrollable,
    so its words and buttons stay reachable at 200 % text.

    Args:
        synced: Whether My schedule reached the account before it opened (D-411).
        on_confirm: Signs out.
        on_cancel: Closes it; also called when Back dismisses it.
    """
    lines = [SIGN_OUT_BODY] if synced else [SIGN_OUT_BODY, UNSYNCED]
    return ft.AlertDialog(
        modal=True,
        scrollable=True,
        icon=ft.Icon(ft.Icons.LOGOUT),
        title=ft.Text(SIGN_OUT_TITLE),
        content=ft.Column(
            [
                ft.Text(
                    line,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
                for line in lines
            ],
            tight=True,
            spacing=12,
        ),
        actions=[
            named(
                "account.sign_out.cancel", ft.TextButton("Cancel", on_click=on_cancel)
            ),
            named(
                "account.sign_out.confirm",
                ft.TextButton("Sign out", on_click=on_confirm),
            ),
        ],
        on_dismiss=on_cancel,
    )
