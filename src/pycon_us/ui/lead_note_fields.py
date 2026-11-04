"""The lead note sheet's choices: Interest's segmented button, Follow-up's chips (LEAD-10).

ux.md §7.3. Words and an icon for each choice, never an emoji (Ionic's modal used them,
and screen readers read them oddly). `ui/lead_note_sheet.py` lays them out; split
from it at D-66's ~400 lines (#755).
"""

from collections.abc import Callable

import flet as ft

from pycon_us.core.lead_notes import Interest
from pycon_us.services.errors import report_errors
from pycon_us.ui.semantics import named, semantics_key

INTERESTS = {
    Interest.HOT: ("Hot", ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED),
    Interest.WARM: ("Warm", ft.Icons.WB_SUNNY_OUTLINED),
    Interest.COLD: ("Cold", ft.Icons.AC_UNIT),
}
"""Each interest's label and icon: words and a symbol, never an emoji."""

FOLLOW_UP_ICONS = {
    "Send info": ft.Icons.MAIL_OUTLINE,
    "Demo": ft.Icons.SLIDESHOW_OUTLINED,
    "Newsletter": ft.Icons.NEWSPAPER_OUTLINED,
    "Hiring": ft.Icons.WORK_OUTLINE,
    "Partner": ft.Icons.HANDSHAKE_OUTLINED,
}
"""Each follow-up chip's leading icon; Flutter's check mark takes its place once
selected (M3's filter chip)."""

SHEET_COLOR = ft.Colors.SURFACE_CONTAINER_LOW
"""M3's bottom sheet colour, which the unselected chips paint, as the filter sheet's."""


def interest_button(
    interest: Interest | None, on_change: ft.ControlEventHandler[ft.SegmentedButton]
) -> ft.Control:
    """Return Hot · Warm · Cold; none selected allowed, so a second tap clears it.

    Each segment is read as its label, a button and its state; its identifier
    (`lead.note.interest.<value>`) is merged into the segment's node, as the Expo's.
    """
    return ft.SegmentedButton(
        segments=[
            ft.Segment(
                value=value.value,
                icon=icon,
                label=ft.Semantics(
                    identifier=f"lead.note.interest.{value.value}",
                    content=ft.Text(label),
                ),
            )
            for value, (label, icon) in INTERESTS.items()
        ],
        selected=[] if interest is None else [interest.value],
        allow_empty_selection=True,
        on_change=on_change,
    )


def follow_up_chip(
    label: str, selected: bool, on_toggle: Callable[[str, bool], object]
) -> ft.Control:
    """Return a follow-up's filter chip: its icon, or the check mark once selected.

    One node with its identifier (`lead.note.follow_up.<key>`), read with its
    label and whether it is selected (Flutter's chip says it).
    """

    @report_errors
    def selected_now(e: ft.Event[ft.Chip]) -> None:
        # Flutter flips the chip and sends its new state before the event (chip.dart).
        on_toggle(label, bool(e.control.selected))

    return named(
        f"lead.note.follow_up.{semantics_key(label)}",
        ft.Chip(
            label=label,
            # Selected, Flutter's check mark alone: over the icon it read as a box.
            leading=None
            if selected
            else ft.Icon(FOLLOW_UP_ICONS[label], size=18, apply_text_scaling=True),
            selected=selected,
            show_checkmark=True,
            bgcolor=SHEET_COLOR,  # a chip paints `surface` otherwise (filter sheet)
            on_select=selected_now,
        ),
    )
