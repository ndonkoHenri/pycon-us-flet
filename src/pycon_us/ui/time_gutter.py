"""The time column of a list's slots: ``TimeGutter`` and ``TimeSlot`` (D-31, D-158).

``TimeGutter`` is a slot's start, "9:25" over "AM", left of its rows, and ``TimeSlot``
a slot, the gutter beside its ``SessionRow``s and ``NoticeRow``s (``ui.session_rows``;
D-200).
"""

from collections.abc import Sequence

import flet as ft


def TimeGutter(label: str) -> ft.Control:
    """Return a slot's time column (D-31, D-158): "9:25" over "AM", left of its rows.

    It has no fixed width: an invisible "10:00" / "AM" under the time sets it, so it
    grows with the text, is the same for every slot, and the rows beside it keep one
    left edge; a fixed 64 dp broke "7:30" over two lines at 200 % text (S2). It is a
    heading, so screen readers move slot by slot, and reads once, as ``label``.

    Args:
        label: The slot's start from ``timefmt.time_label()``: "9:25 AM", or "09:25"
            on a 24-hour clock, which needs no second line.
    """
    time, _, meridiem = label.partition(" ")

    # Roboto's digits are tabular (D-26), so "10:00" is as wide as any time.
    widest = _gutter_lines(
        "10:00" if meridiem else "00:00", "AM" if meridiem else "", 0
    )
    return ft.Semantics(
        header=True,
        label=label,
        exclude_semantics=True,  # else it reads "9:25 AM, 9:25, AM"
        content=ft.Container(
            ft.Stack([widest, _gutter_lines(time, meridiem)]),
            padding=ft.Padding.only(left=16, top=12, right=8),
        ),
    )


def TimeSlot(label: str, rows: Sequence[ft.Control], *, divider: bool) -> ft.Control:
    """Return one time slot of a list (D-31): the ``TimeGutter`` beside the slot's rows.

    Args:
        label: The slot's start, for ``TimeGutter``.
        rows: Its ``SessionRow``s and ``NoticeRow``s, in schedule order.
        divider: Draw a 1 dp divider above it: every slot of a day but the first.
    """
    slot = ft.Row(
        [TimeGutter(label), ft.Column(list(rows), spacing=0, expand=True)],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    return ft.Column([ft.Divider(height=1), slot], spacing=0) if divider else slot


def _gutter_lines(time: str, meridiem: str, opacity: float = 1.0) -> ft.Control:
    """Return the gutter's time over its AM or PM, if any."""
    controls: list[ft.Control] = [
        ft.Text(time, theme_style=ft.TextThemeStyle.TITLE_SMALL)
    ]
    if meridiem:
        controls.append(
            ft.Text(
                meridiem,
                theme_style=ft.TextThemeStyle.LABEL_SMALL,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return ft.Column(controls, spacing=0, opacity=opacity)
