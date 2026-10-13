"""The Developer screen's confirmations: Clear cached feed's and Reset app's (D-195).

``confirmation()`` returns the ``AlertDialog`` the Data section (``developer_data.py``)
shows before an action that deletes something, naming what is lost (D-29), or None
while none is open. Apart so that each module stays under about 400 lines (D-66).
"""

from collections.abc import Callable
from typing import Any, Literal

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.timefmt import day_label, local_date
from pycon_us.ui.semantics import named

type Asking = Literal["clear", "reset"] | None
"""Which confirmation is open: Clear cached feed's, Reset app's, or none."""


def none_open() -> Asking:
    """Return None: no confirmation open, the Data section's first state.

    A function, so ``ft.use_state`` keeps the state typed as ``Asking``.
    """
    return None


NBSP = "\u00a0"
"""A non-breaking space: the dialog never wraps a date in its middle."""


def snapshot_day(info: ConferenceInfo) -> str:
    """Return the day the bundled snapshot was fetched, e.g. "Mon, Oct 12", or "" if none.

    Its spaces are ``NBSP``, so the dialog never wraps it as "(Sun, Oct" / "11)".
    """
    captured = info.snapshot_captured_at
    if captured is None:
        return ""
    return day_label(local_date(captured, info.zone)).replace(" ", NBSP)


def reset_losses(saved: int, *, packaged: bool) -> tuple[str, ...]:
    """Return what Reset app deletes, one item per line of its confirmation (D-29).

    Args:
        saved: How many sessions are saved in My schedule this year.
        packaged: A packaged build, where Developer locks again; elsewhere it is
            always available (D-73).
    """
    developer = "Developer options: the fake clock and the feed URL"
    if packaged:
        developer += ", and Developer locks again"
    return (
        "Your settings: Appearance and the schedule's filters",
        f"Your saved sessions in My schedule: {saved or 'none'}",
        "The cached schedule: the app shows the bundled one until it refreshes",
        developer,
    )


LOSS_ICONS = (
    ft.Icons.SETTINGS_OUTLINED,
    ft.Icons.STAR_BORDER,
    ft.Icons.EVENT_NOTE_OUTLINED,
    ft.Icons.DEVELOPER_MODE_OUTLINED,
)
"""A decorative icon for each of ``reset_losses()``' lines, in order."""


def confirmation(
    asking: Asking,
    *,
    saved: int,
    packaged: bool,
    snapshot_day: str,
    on_confirm: Callable[[], Any],
    on_cancel: Callable[[], Any],
) -> ft.AlertDialog | None:
    """Return the confirmation that ``asking`` names, or None while none is open.

    An ``AlertDialog`` before something destructive, naming what is lost (D-29): modal,
    so only its buttons or Back close it (Back cancels), and scrollable, so its words
    and buttons stay reachable at 200 % text.

    Args:
        asking: Which confirmation: ``"clear"``, ``"reset"`` or None.
        saved: How many sessions are saved in My schedule, for Reset app's list.
        packaged: A packaged build, where Reset app locks Developer again.
        snapshot_day: The day the bundled snapshot was fetched; "" if unknown.
        on_confirm: Runs the action.
        on_cancel: Closes the dialog; also called when Back dismisses it.
    """
    if asking is None:
        return None
    if asking == "clear":
        bundled = f"the schedule bundled with the app ({snapshot_day})"
        if not snapshot_day:
            bundled = "the schedule bundled with the app"
        return _dialog(
            "developer.clear_cache",
            ft.Icons.DELETE_OUTLINE,
            "Clear the cached schedule?",
            [
                _body(
                    "This deletes the schedule saved by the last refresh. You keep "
                    "seeing it until you close the app; the next start shows "
                    f"{bundled} until a refresh saves a new copy."
                )
            ],
            confirm="Clear",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )
    losses = reset_losses(saved, packaged=packaged)
    return _dialog(
        "developer.reset_app",
        ft.Icons.RESTART_ALT,
        "Reset the app?",
        [
            _body(
                "This deletes what the app keeps on this device and starts it as if "
                "it were just installed:"
            ),
            *(_loss(icon, text) for icon, text in zip(LOSS_ICONS, losses, strict=True)),
        ],
        icon_color=ft.Colors.ERROR,  # as the row that opens it
        confirm="Reset app",
        on_confirm=on_confirm,
        on_cancel=on_cancel,
    )


def _dialog(
    identifier: str,
    icon: ft.IconData,
    title: str,
    content: list[ft.Control],
    *,
    icon_color: ft.ColorValue | None = None,
    confirm: str,
    on_confirm: Callable[[], Any],
    on_cancel: Callable[[], Any],
) -> ft.AlertDialog:
    """A destructive action's confirmation: Cancel, then the action, in ``error``.

    The icon is the row's, in the row's colour when it has one (``error`` for Reset
    app), else the dialog's default (``secondary``).
    """
    return ft.AlertDialog(
        modal=True,
        scrollable=True,
        icon=ft.Icon(icon, color=icon_color),
        title=ft.Text(title),
        content=ft.Column(content, tight=True, spacing=12),
        actions=[
            named(f"{identifier}.cancel", ft.TextButton("Cancel", on_click=on_cancel)),
            named(
                f"{identifier}.confirm",
                ft.TextButton(
                    confirm,
                    on_click=on_confirm,
                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                ),
            ),
        ],
        on_dismiss=on_cancel,
    )


def _body(text: str) -> ft.Text:
    return ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )


def _loss(icon: ft.IconData, text: str) -> ft.Control:
    """One line of what is lost: a decorative icon beside the words, top-aligned."""
    return ft.Row(
        [
            ft.Icon(icon, size=20, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(
                text,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE,
                expand=True,
            ),
        ],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
