"""The CoC result's email, hidden until revealed (#762; MASK-05, O-7).

An "Incident recorded" result carries the reply's email (`ScanResult.email`), never
on the panel. Its result action "Show email" (`coc.show_email`) reveals it on a line
of its own under the panel (`ScanScreen`'s `result_note`), above the badge field
and so above the keyboard, outside the panel's live region: a screen reader says it
only when it is focused. The button then reads "Hide email". The reveal belongs to
that result: the next result, or the result's clear, hides it again, and the email
goes with the result. It is never in the panel's words, an identifier or a log (D-72).
"""

from collections.abc import Callable

import flet as ft

from pycon_us.services.errors import report_errors
from pycon_us.ui.scan_result import Shown
from pycon_us.ui.tool_controls import tool_button

SHOW_EMAIL = "Show email"
HIDE_EMAIL = "Hide email"

type Reveal = Callable[[Callable[[int], int]], None]
"""Sets the serial of the result whose email shows (a `use_state` setter)."""


def email_actions(shown: Shown, *, revealed: int, reveal: Reveal) -> list[ft.Control]:
    """Return the result's "Show email" or "Hide email".

    The CoC tool's `result_actions`. A result without an email (not recorded, or a
    reply without one) gets nothing.

    Args:
        shown: The result on the panel.
        revealed: The serial of the result whose email shows, 0 for none.
        reveal: Sets `revealed`; given a function of the latest value (#756).
    """
    email = shown.result.email
    if not email:
        return []
    serial = shown.serial
    showing = revealed == serial

    @report_errors
    def toggle(_: ft.Event[ft.FilledTonalButton]) -> None:
        reveal(lambda last: 0 if last == serial else serial)

    button = tool_button(
        "coc.show_email",
        HIDE_EMAIL if showing else SHOW_EMAIL,
        ft.Icons.VISIBILITY_OFF_OUTLINED if showing else ft.Icons.VISIBILITY_OUTLINED,
        toggle,
    )
    return [button]


def email_note(shown: Shown, *, revealed: int) -> ft.Control | None:
    """Return the revealed email under the panel, or None while it is hidden.

    The CoC tool's `result_note`: one node, said only when focused.

    Args:
        shown: The result on the panel.
        revealed: The serial of the result whose email shows, 0 for none.
    """
    email = shown.result.email
    if not email or revealed != shown.serial:
        return None
    return ft.Container(
        ft.Semantics(
            identifier="coc.email",  # never the address itself (D-72)
            container=True,
            label=f"Email {email}",
            exclude_semantics=True,  # the label says it, once
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.MAIL_OUTLINE,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        apply_text_scaling=True,
                    ),
                    ft.Text(
                        email,
                        theme_style=ft.TextThemeStyle.BODY_LARGE,
                        expand=True,
                    ),
                ],
                spacing=12,
            ),
        ),
        padding=ft.Padding.symmetric(vertical=12),  # a 48 dp row to focus
        key="coc.email",  # apart from the other rows in ScanScreen's list
    )
