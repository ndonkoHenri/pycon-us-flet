"""Action rows and the line that says how an action ended, said in place (D-29, D-210).

``action_row()`` is a two-line action, a verb and what it touches, as Developer's Data
section (D-198) and Settings' Data section (P2-62) draw them; ``outcome_line()``, in
``padded()``, is the line under a group of buttons that says what was done (an
``Outcome``); ``refreshed()`` is what Refresh now says once its refresh has ended, the
same words on both pages (D-292).
"""

import flet as ft

from pycon_us.feed_refresh import Problem
from pycon_us.theme import Tokens
from pycon_us.ui.semantics import named

type Outcome = tuple[str, bool]
"""What an action did, in words, and whether it went as asked: the line under the rows."""

NO_OUTCOME: Outcome = ("", True)
"""The outcome line's state before an action and after an edit: no words, hidden."""


def action_row(
    identifier: str,
    icon: ft.IconData,
    title: str,
    subtitle: str,
    on_click: ft.ControlEventHandler[ft.ListTile],
    *,
    disabled: bool = False,
    color: ft.ColorValue | None = None,
    trailing: ft.Control | None = None,
    slot: int | None = None,
) -> ft.Control:
    """Return one action: a two-line ``ListTile``, one node named by both lines.

    Its icons and title sit 14 dp from the top at every height, as a ``LinkTile`` with
    a subtitle does (D-188). A disabled row says so to screen readers: its merged node
    takes the tile's ``disabled`` (``named()``, D-214). Its icon and title take the
    disabled colour, but its second line, which says why, stays in
    ``on_surface_variant``: at the disabled 38 % it is too faint to read (ux.md §9).

    Args:
        identifier: For UI flows, e.g. ``developer.reset_app``.
        icon: The leading icon, outlined (D-27).
        title: What a tap does, a verb first.
        subtitle: What it touches, or why the row is disabled.
        on_click: The action.
        disabled: Whether the action is unavailable now.
        color: The icon's and the title's colour: ``ERROR`` for Reset app.
        trailing: A decorative control at the end: Refresh now's ring while it runs.
        slot: The width the icon is centred in, so the title starts where a page's
            other titles do: Settings' 48 dp, a radio's (``RADIO_WIDTH``); None for
            the bare 24 dp icon.
    """
    leading: ft.Control = ft.Icon(icon, color=None if disabled else color)
    if slot is not None:
        leading = ft.Container(leading, width=slot, alignment=ft.Alignment.CENTER)
    return named(
        identifier,
        ft.ListTile(
            leading=leading,
            title=ft.Text(title, color=None if disabled else color),
            subtitle=ft.Text(
                subtitle, color=ft.Colors.ON_SURFACE_VARIANT if disabled else None
            ),
            trailing=trailing,
            on_click=on_click,
            disabled=disabled,
            title_alignment=ft.ListTileTitleAlignment.TOP,
            min_vertical_padding=14,
        ),
    )


def padded(control: ft.Control) -> ft.Container:
    """Return ``control`` with the list's 16 dp sides and 8 dp above and below (ux.md §3.6)."""
    return ft.Container(
        control, padding=ft.Padding.symmetric(horizontal=16, vertical=8)
    )


def outcome_line(text: str, ok: bool, *, tokens: Tokens, slot: int = 24) -> ft.Control:
    """Return the line under a group of buttons: an icon and what was done.

    Laid out as the screen's ``ListTile``s are, the icon in a slot as wide as theirs
    (24 dp, or ``action_row()``'s ``slot``) and the words 16 dp after it, so they
    start in the tiles' text column.

    Args:
        text: What was done, or why not, e.g. "Back to real time and the year's feed."
        ok: Whether it went as asked: a check in ``success``, else a warning in
            ``warning``; the words carry the meaning (ux.md §9).
        tokens: The scheme's tokens.
        slot: The icon's slot: the width of the leading icons above it.
    """
    return padded(
        ft.Row(
            [
                # Decorative: the words carry the meaning (ux.md §9).
                ft.Container(
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE_OUTLINE if ok else ft.Icons.WARNING_AMBER,
                        color=tokens.success if ok else tokens.warning,
                        size=20,
                    ),
                    width=slot,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text(
                    text,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE,
                    expand=True,
                ),
            ],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )


KEPT = "The app keeps the schedule it has."
"""The second half of a failed refresh's line: a refresh never clears the cache (D-32)."""


def refreshed(problem: Problem | None) -> Outcome:
    """Return what Refresh now says once its refresh has ended (D-146).

    A failed refresh says it couldn't refresh, why in a few words, and that the
    schedule on screen stays.

    Args:
        problem: ``Conference.problem`` after it: None when it published the feed.
    """
    if problem is None:
        return ("Schedule updated from the feed.", True)
    if problem == "offline":
        return (f"Couldn't refresh: no answer from the feed. {KEPT}", False)
    return (f"Couldn't refresh: the feed's answer couldn't be used. {KEPT}", False)
