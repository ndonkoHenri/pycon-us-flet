"""The lines a session row is made of (D-227).

The time-and-place line, supporting text, the overlap warning and the elapsed bar:
plain builders, with no hooks, which ``ui.session_rows``'s ``SessionRow`` and
``NoticeRow`` stack under a row's title (ux.md §3.9, D-184). What a row says to a
screen reader is ``core.row_views``'s phrases, not these lines (D-200).
"""

from collections.abc import Sequence

import flet as ft

from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import on_screen

_NBSP = "\u00a0"
"""A no-break space: the "·" stays on its time's line."""

TRACK = ft.Colors.with_opacity(0.16, ft.Colors.ON_SURFACE)
"""The elapsed bar's track: a tint of the text, so it shows on every surface, the
next-session card's included (about 1.4:1), and the ``live`` fill reads 3.7:1 or more
on it."""


def meta(
    view: SessionView, *, style: ft.TextThemeStyle = ft.TextThemeStyle.BODY_MEDIUM
) -> ft.Control:
    """Return a row's time and place line: "9:25–10:10 AM · Room 104A".

    The time and the place are two texts in a wrapping row, so at large text a place
    that does not fit after the time moves to the next line whole, and the "·" ends
    the time's line rather than starting one; only a place wider than the row wraps
    inside itself. The time keeps "AM" on its line and breaks only after its dash
    (``timefmt.on_screen()``, D-229).

    Args:
        view: The session's row view.
        style: The line's type style; a notice's is smaller.
    """
    when = on_screen(view.when)
    if not view.place:
        return secondary(when, style=style)
    return ft.Row(
        [
            secondary(f"{when}{_NBSP}·", style=style),
            secondary(view.place, style=style),
        ],
        wrap=True,
        spacing=4,  # a space's width at 100 %
        run_spacing=0,
    )


def secondary(
    text: str, *, style: ft.TextThemeStyle = ft.TextThemeStyle.BODY_MEDIUM
) -> ft.Text:
    """Return a row's supporting text: its time, place or speakers, in the variant colour."""
    return ft.Text(text, theme_style=style, color=ft.Colors.ON_SURFACE_VARIANT)


def overlap_line(names: Sequence[str], color: str) -> ft.Control:
    """Return a row's overlap warning: ``WARNING_AMBER`` beside its lines (ux.md §3.7).

    "Overlaps with “Typing deep dive”", cut at three lines as a title is (§3.6), then
    "and 2 more" on a line of its own, so the cut never hides the count (D-188's "Now:"
    line). Both in ``Tokens.warning``, which reads at 4.5:1 or better on every surface
    (§3.3). The icon is one line tall, scaled with the text, and tops the text, so it
    is beside its first line at every size (D-373).
    """
    first, *rest = names
    texts: list[ft.Control] = [
        ft.Text(
            f"Overlaps with “{first}”",
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
            color=color,
            max_lines=3,
            overflow=ft.TextOverflow.ELLIPSIS,  # the phrase says it in full
        )
    ]
    if rest:
        more = f"and {len(rest)}\N{NO-BREAK SPACE}more"
        texts.append(
            ft.Text(more, theme_style=ft.TextThemeStyle.BODY_MEDIUM, color=color)
        )
    return ft.Row(
        [
            # One BODY_MEDIUM line tall at every text size (D-373): it tops the
            # row, so it stays level with the first line however far the text grows.
            ft.Icon(
                ft.Icons.WARNING_AMBER, size=20, apply_text_scaling=True, color=color
            ),
            ft.Column(texts, spacing=0, expand=True),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def elapsed_bar(elapsed: int, color: str) -> ft.Control:
    """A row's elapsed bar (ux.md §3.9); it stays under reduced motion (D-173).

    M3's current bar (``year_2023=False``): a gap after the fill, then the track, and
    a stop dot at its end in ``on_surface_variant`` (4.5:1 or more on every surface),
    which marks where 100 % is, as M3 asks of a track under 3:1 (WCAG 1.4.11).
    """
    return ft.Container(
        ft.ProgressBar(
            value=elapsed / 100,
            bar_height=3,
            color=color,
            bgcolor=TRACK,
            border_radius=3,
            year_2023=False,
            stop_indicator_color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        padding=ft.Padding.only(top=4),  # 8 dp under the text, with the column's 4
    )
