"""A conference day's tab: the Schedule's, a room's and the open spaces' (D-192, D-194).

`day_tab()` is a day's one-line tab, read as its full date, today's with a dot;
`TAB_HEIGHT` keeps the largest text in it and `TAB_MS` is a switch's slide.
"""

from datetime import date

import flet as ft

from pycon_us.core.timefmt import day_heading, day_tab_label

TAB_HEIGHT = 56
"""A day tab's height in dp, above Flutter's 46 for a text tab: the tab bar cannot grow
with the text, and Flet cannot read the text scale (U16), so it is sized for the largest
iOS size (about 310 %), where a one-line label's glyphs need about 52 dp."""

TAB_MS = 100
"""How long a day switch made from Python slides (Flet's default for `Tabs`); the
Schedule's and a room's tabs (D-194)."""

TODAY_DOT = 6
"""The diameter of the dot that marks today's tab, in dp (ux.md §5.2)."""


def day_tab(index: int, day: date, *, is_today: bool, screen: str) -> ft.Tab:
    """Return a day's tab: "Fri 15", today with a dot, read "Friday, May 15, today".

    The text's semantics label says the day in full; Flutter's tab bar puts its own
    position label before it and adds the selection, so TalkBack reads "Tab 3 of 7,
    Friday, May 15, today, selected" (D-192). Room detail's tabs are these too (D-194).

    Args:
        index: The tab's position, in its identifier `<screen>.day_tab.<index>`.
        day: The conference-local date.
        is_today: Mark it as today, with a dot and ", today".
        screen: The screen's name in the identifier: `schedule`, `room` or
            `open_spaces`.
    """
    spoken = f"{day_heading(day)}, today" if is_today else day_heading(day)
    label: ft.Control = ft.Text(day_tab_label(day), semantics_label=spoken)
    if is_today:
        # Beside the text, not a Badge over it: a badge's dot covered the last digit.
        dot = ft.Container(
            width=TODAY_DOT,
            height=TODAY_DOT,
            border_radius=TODAY_DOT / 2,
            bgcolor=ft.Colors.PRIMARY,
        )
        # Centred on the label, so it stays beside the digits at every text size.
        label = ft.Row(
            [label, dot],
            spacing=4,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Tab(
        height=TAB_HEIGHT,
        # Unlabelled: Flutter merges the identifier into the tab's node (D-166).
        label=ft.Semantics(identifier=f"{screen}.day_tab.{index}", content=label),
    )
