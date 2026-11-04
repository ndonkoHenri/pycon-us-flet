"""The chip and the buttons on a staff tool's scan screen (ux.md §7.2; D-425, D-433).

A tool's choice (the Lead scanner's sponsor, Door check's session) heads its scan screen
as an outlined chip that reopens the picker (`context_chip()`), which the sync chip
also wears at large text (#752); the tool's own buttons under the field, and the one
that opens the picker while none is chosen, are tonal (`tool_button()`). The pickers
are `ui/staff_picker.py`'s.
"""

import flet as ft

from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.semantics import named


def context_chip(
    *,
    text: str,
    spoken: str,
    icon: ft.IconData | ft.Control,
    identifier: str,
    on_click: ft.ControlEventHandler,
) -> ft.Control:
    """Return the chip that heads a tool's scan screen and reopens its picker.

    One node, a button read as `spoken`. Drawn as M3's outlined assist chip (8 dp
    corners, an `outline_variant` edge, a leading icon) but built from a
    `Container`: Flutter's `Chip` keeps its label on one line, which at the
    largest text cut "Example Corp" to "Example". Its text takes only the room it
    needs (`expand_loose`) and wraps past the width; the chip is at least 48 dp tall,
    its own target (ux.md §9).

    Args:
        text: What it shows, "For: Example Corp".
        spoken: What a screen reader says, "Scanning for Example Corp, change sponsor".
        icon: Its leading icon, drawn in `primary`; or a control in its place (the
            sync chip's own icon or ring at large text, #752).
        identifier: For UI flows, `lead.sponsor_chip`.
        on_click: Opens the picker.
    """
    return ft.Container(
        ft.MergeSemantics(  # the phrase and the tap's action: one node
            content=ft.Container(
                ft.Semantics(
                    label=spoken,
                    identifier=identifier,
                    button=True,
                    exclude_semantics=True,  # the phrase replaces the text
                    content=ft.Row(
                        [
                            icon
                            if isinstance(icon, ft.Control)
                            else ft.Icon(
                                icon,
                                size=18,
                                color=ft.Colors.PRIMARY,
                                apply_text_scaling=True,
                            ),
                            ft.Text(
                                text,
                                theme_style=ft.TextThemeStyle.LABEL_LARGE,
                                expand=True,
                                expand_loose=True,
                            ),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                ),
                ink=True,
                on_click=on_click,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=12, vertical=13),
            )
        ),
        alignment=ft.Alignment.CENTER_LEFT,
    )


def tool_button(
    identifier: str, label: str, icon: ft.IconData, on_click: ft.ControlEventHandler
) -> ft.Control:
    """Return one of a tool's tonal buttons under the field, as wide as its words.

    `ScanScreen` lays the tool's buttons in one wrapping row, so two share a line.

    Args:
        identifier: For UI flows, e.g. `lead.add_note`.
        label: Its words.
        icon: Its leading icon.
        on_click: What it does.
    """
    return ft.Container(
        named(
            identifier,
            ft.FilledTonalButton(
                label,
                icon=icon,
                on_click=on_click,
                style=ft.ButtonStyle(padding=LABEL_PADDING),
                elevation=0,  # M3's tonal button lies flat (D-344)
            ),
        ),
        # Keyed: "Leads (42)" is built here and kept by ScanScreen's own re-renders,
        # so a result's "Add note" landing in its place would otherwise take its id,
        # two buttons with one (U163, #622); differing keys make it a new control.
        key=identifier,
    )
