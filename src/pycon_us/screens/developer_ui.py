"""The Developer screen's drawing: its fields and its confirmations.

``option_field()`` is one option's text field, the fake clock's or the feed URL's; and
``confirmation()`` and ``staff_confirmation()`` return the ``AlertDialog`` the Data
section shows before an action that deletes something, naming what is lost (D-29), with
how many staff records have not synced (D-414). What the actions do is
``developer_data.py``'s and ``developer_staff.py``'s; apart so that each module stays
under about 400 lines (D-66).
The action rows and the outcome line are ``ui/actions.py``'s, which Settings' Data
section (#422) and About this app (#443) share.
"""

from collections.abc import Callable
from typing import Any, Literal

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.timefmt import day_label, local_date
from pycon_us.services.outbox_db import Counts
from pycon_us.staff_data import unsynced
from pycon_us.ui.actions import padded
from pycon_us.ui.semantics import named

type Asking = Literal["clear", "reset"] | None
"""Which confirmation is open: Clear cached feed's, Reset app's, or none."""


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
    developer = "Developer options: the fake clock, the feed URL and the mock API URL"
    if packaged:
        developer += ", and Developer locks again"
    return (
        "Your settings: Appearance and the schedule's filters",
        f"Your saved sessions in My schedule: {saved or 'none'}",
        "The cached schedule: the app shows the bundled one until it refreshes",
        "Schedule changes: what recent refreshes changed",
        developer,
    )


LOSS_ICONS = (
    ft.Icons.SETTINGS_OUTLINED,
    ft.Icons.STAR_BORDER,
    ft.Icons.EVENT_NOTE_OUTLINED,
    ft.Icons.HISTORY,
    ft.Icons.DEVELOPER_MODE_OUTLINED,
)
"""A decorative icon for each of ``reset_losses()``' lines, in order."""


def records(counts: Counts) -> str:
    """Return the staff records by state, e.g. "12 synced, 3 not synced yet"."""
    return f"{counts.synced} synced, {unsynced(counts)} not synced yet"


def delete_unsynced(count: int) -> str:
    """Return the confirm button's words with unsynced records: "Delete 3 … too"."""
    return f"Delete {count} unsynced record{'' if count == 1 else 's'} too"


UNREADABLE = "Couldn't read the staff records on this device, so they stay."
"""What a confirmation says when the outbox can't be read: no count, no deletion."""


def staff_confirmation(
    counts: Counts | None,
    *,
    on_confirm: Callable[[], Any],
    on_cancel: Callable[[], Any],
) -> ft.AlertDialog:
    """Return Clear staff data's confirmation, naming what is lost (DEV-03, D-414).

    With unsynced records, the button says "Delete 3 unsynced records too", in
    ``error`` as every destructive action's; when they can't be counted, it is
    disabled: no path deletes a row without naming how many.

    Args:
        counts: Every account's records by status; None when they can't be read.
        on_confirm: Clears the staff data.
        on_cancel: Closes the dialog; also called when Back dismisses it.
    """
    waiting = 0 if counts is None else unsynced(counts)
    rows = UNREADABLE if counts is None else f"The staff records: {records(counts)}"
    if waiting:
        rows += ". The ones not synced never reach the server"
    return _dialog(
        "developer.clear_staff_data",
        ft.Icons.FOLDER_DELETE_OUTLINED,
        "Clear staff data?",
        [
            _body(
                "This deletes the staff tools' data on this device, every account's:"
            ),
            _loss(ft.Icons.CLOUD_OUTLINED, rows),
            _loss(ft.Icons.VERIFIED_USER_OUTLINED, "The scanner consent"),
            _loss(ft.Icons.STOREFRONT_OUTLINED, "The sponsor chosen to scan for"),
        ],
        confirm=delete_unsynced(waiting) if waiting else "Clear",
        on_confirm=on_confirm,
        on_cancel=on_cancel,
        disabled=counts is None,
    )


def confirmation(
    asking: Asking,
    *,
    saved: int,
    packaged: bool,
    snapshot_day: str,
    staff: Counts | None = None,
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
        staff: Every account's staff records, for Reset app's list (D-414): none
            listed while there are none; None when they can't be read.
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
    lines = [_loss(icon, text) for icon, text in zip(LOSS_ICONS, losses, strict=True)]
    waiting = 0 if staff is None else unsynced(staff)
    if staff is None:
        lines.append(_loss(ft.Icons.CLOUD_OUTLINED, UNREADABLE))
    elif waiting or staff.synced:
        lines.append(_loss(ft.Icons.CLOUD_OUTLINED, f"Staff records: {records(staff)}"))
    return _dialog(
        "developer.reset_app",
        ft.Icons.RESTART_ALT,
        "Reset the app?",
        [
            _body(
                "This deletes what the app keeps on this device and starts it as if "
                "it were just installed:"
            ),
            *lines,
        ],
        icon_color=ft.Colors.ERROR,  # as the row that opens it
        confirm=delete_unsynced(waiting) if waiting else "Reset app",
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
    disabled: bool = False,
) -> ft.AlertDialog:
    """A destructive action's confirmation: Cancel, then the action, in ``error``.

    The icon is the row's, in the row's colour when it has one (``error`` for Reset
    app), else the dialog's default (``secondary``). ``disabled`` greys the action
    out: what it would delete couldn't be named.
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
                    disabled=disabled,
                    style=None if disabled else ft.ButtonStyle(color=ft.Colors.ERROR),
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
            # One BODY_MEDIUM line tall at every text size (D-373).
            ft.Icon(
                icon,
                size=20,
                apply_text_scaling=True,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
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


def option_field(
    identifier: str,
    value: str,
    *,
    label: str,
    hint: str,
    helper: str,
    error: str,
    keyboard: ft.KeyboardType,
    on_change: ft.ControlEventHandler[ft.TextField],
    suffix: ft.Control | None = None,
    reveal_below: int = 20,
) -> ft.Control:
    """Return one option's text field, found by flows through ``identifier``.

    Controlled (D-157): ``value`` comes from the state ``on_change`` sets. The value
    and the error (``""`` when the text parses) wrap to three lines at large text, and
    the helper as far as it needs (``helper_text()``). The text is taken as typed, with
    no autocorrect or suggestions (a date, a URL). ``max_lines`` without ``multiline``,
    which would swap ``keyboard`` for the multiline keyboard, whose Return types a line
    break.

    The identifier is merged into the field's node (D-190), except around a field
    with a ``suffix``: a merge takes in every descendant, and the clock's picker would
    stop being a button of its own (D-189). That field keeps a bare identifier, an
    empty node of its own, until Flet's ``Semantics`` stops forcing ``enabled`` (U34,
    D-214).

    ``reveal_below`` is how much of the list under the field's text stays in sight when
    the field takes the focus and the keyboard shrinks the screen (Flutter's
    ``scrollPadding``; 20 dp by default, as Flutter's).
    """
    text_field = ft.TextField(
        value=value,
        max_lines=3,
        label=label,
        hint_text=hint,
        hint_max_lines=1,  # else a long hint (the feed URL) heightens the field
        helper=helper_text(helper),
        error=error or None,
        error_max_lines=3,
        keyboard_type=keyboard,
        autocorrect=False,
        enable_suggestions=False,
        on_change=on_change,
        suffix_icon=suffix,
        scroll_padding=ft.Padding.only(left=20, top=20, right=20, bottom=reveal_below),
    )
    if suffix is None:
        return padded(named(identifier, text_field))
    return padded(ft.Semantics(identifier=identifier, content=text_field))


def helper_text(text: str) -> ft.Text:
    """Return a field's helper as a ``Text``, so it wraps to every line it needs (#280).

    A string helper is cut at ``helper_max_lines`` with an ellipsis, and Flutter has no
    "no limit": null means one line. Three lines cut the fake clock's at the largest
    text, losing "Empty for real time.", the way back. A ``Text`` helper is drawn as
    given, without the field's helper style, so it takes Material's own: ``BODY_SMALL``
    in ``on_surface_variant``.
    """
    return ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_SMALL,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )


def said(done: str, saved: bool) -> tuple[str, bool]:
    """Return the outcome line's state after Apply or Reset: what was done, and whether it lasts.

    Args:
        done: What was done, e.g. "Back to real time and the year's feed."
        saved: Whether ``Prefs.save`` saved it; if not, it ends with the app (D-120),
            which the line says, beside a warning icon.
    """
    if not saved:
        done += " Couldn't save your change: it ends when you close the app."
    return done, saved
