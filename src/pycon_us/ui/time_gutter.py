"""The time column of a list's slots: ``TimeGutter``, ``TimeSlot`` and its probe (D-31).

``TimeGutter`` is a slot's start, "9:25" over "AM", left of its rows (D-158), and
``TimeSlot`` a slot, its time beside its ``SessionRow``s and ``NoticeRow``s
(``ui.session_rows``; D-200). At the largest text sizes the gutter would take so much of
the width that titles and badge labels broke inside a word, so a slot then puts its
time on a line of its own above its rows (``TimeAbove``; D-216). ``GutterProbe``, on
every screen's ``AppScaffold``, measures which applies, since Flet cannot read the text
scale (U16).
"""

from collections.abc import Sequence

import flet as ft

from pycon_us.core.timefmt import on_screen
from pycon_us.layout import is_wide
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.services.errors import report_errors
from pycon_us.ui.navigation import RAIL_WIDTH

MAX_GUTTER_SHARE = 0.2
"""The largest share of a slot's width the gutter may take (D-216): a fifth. Beyond it
the column beside it holds a few words a line, and at the largest sizes not even a
long one, so titles and badge labels broke inside a word. Measured on a phone in
portrait, the gutter takes 15 % at 100 % text and 18 % at iOS's largest standard size,
then 21 % to 34 % across iOS's five Accessibility sizes, and 21 % and 22 % at Android's
180 % and 200 % on a 411 dp phone."""

PADDING = ft.Padding.only(left=16, top=12, right=8)
"""Around the gutter's time: 16 dp from the screen's edge, 12 dp down, on the first
row's title line, and 8 dp from the rows."""


def time_above(gutter_width: float, width: float) -> bool:
    """Return whether a slot's time goes above its rows rather than beside them (D-216).

    It does when the gutter would take more than ``MAX_GUTTER_SHARE`` of the slot's
    width: at a large text size on a phone in portrait, never at the default size,
    and rarely in landscape, where the rows have room beside it.

    Args:
        gutter_width: The gutter's width in dp, padding included (``GutterProbe``).
        width: The width a slot has, the screen's, in dp; 0 while unmeasured,
            which keeps the gutter.
    """
    return width > 0 and gutter_width > MAX_GUTTER_SHARE * width


def slot_width(view_width: float) -> float:
    """Return the width a slot has in a View ``view_width`` dp wide (D-216, D-277).

    The View's own width, less the rail's from 600 dp, where tab roots show it beside
    the body. Pushed Views have no rail, so there a slot has ``RAIL_WIDTH`` more than
    this: one answer for every View errs towards the time above. The rail widens at
    large text, so this is the most a slot beside it can have.

    Args:
        view_width: The View's width in dp, as ``GutterProbe`` measured it.
    """
    return view_width - RAIL_WIDTH if is_wide(view_width) else view_width


def TimeGutter(label: str) -> ft.Control:
    """Return a slot's time column (D-31, D-158): "9:25" over "AM", left of its rows.

    It has no fixed width: an invisible "10:00" / "AM" under the time sets it, so it
    grows with the text, is the same for every slot, and the rows beside it keep one
    left edge; a fixed 64 dp broke "7:30" over two lines at 200 % text (S2). It is a
    level-3 heading, a slot under its day (a level-2 day heading, or the selected day
    tab), so screen readers move slot by slot (D-211), and reads once, as ``label``.

    Args:
        label: The slot's start from ``timefmt.time_label()``: "9:25 AM", or "09:25"
            on a 24-hour clock, which needs no second line.
    """
    time, _, meridiem = label.partition(" ")
    return _heading(
        label,
        ft.Container(
            ft.Stack(
                [_widest(twelve_hour=bool(meridiem)), _gutter_lines(time, meridiem)]
            ),
            padding=PADDING,
        ),
    )


def TimeAbove(label: str) -> ft.Control:
    """Return a slot's time on a line of its own, above its rows (D-216).

    What a slot shows instead of the gutter when the text is too large for one
    (``time_above()``): "9:25 AM" in the gutter's type, from the screen's 16 dp
    margin, and a heading read once, as the gutter. 20 dp above it and the rows' own
    12 dp below: further from the divider or now line over it than from its rows, so
    it reads as their heading.

    Args:
        label: The slot's start from ``timefmt.time_label()``; shown through
            ``timefmt.on_screen()``, so "AM" keeps to its time's line.
    """
    return _heading(
        label,
        ft.Container(
            ft.Text(
                on_screen(label),
                theme_style=ft.TextThemeStyle.TITLE_SMALL,
            ),
            padding=ft.Padding.only(left=16, top=20, right=16),
        ),
    )


def slot_layout(label: str, rows: Sequence[ft.Control], *, above: bool) -> ft.Control:
    """Return a slot's time and its rows: beside them in the gutter, or above them.

    Args:
        label: The slot's start, e.g. "9:25 AM" (``timefmt.time_label()``).
        rows: Its ``SessionRow``s and ``NoticeRow``s, in schedule order.
        above: Put the time above the rows (``Prefs.time_above``, D-216), which
            then take the slot's whole width.
    """
    if above:
        # The rows keep a column of their own, as beside the gutter: the slot's
        # tree has the same shape in both layouts.
        return ft.Column(
            [TimeAbove(label), ft.Column(list(rows), spacing=0)], spacing=0
        )
    return ft.Row(
        [TimeGutter(label), ft.Column(list(rows), spacing=0, expand=True)],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def TimeSlot(
    label: str, rows: Sequence[ft.Control], *, divider: bool, above: bool
) -> ft.Control:
    """Return one time slot of a list (D-31): its time beside its rows, or above them.

    Args:
        label: The slot's start, for ``TimeGutter`` or ``TimeAbove``.
        rows: Its ``SessionRow``s and ``NoticeRow``s, in schedule order.
        divider: Draw a 1 dp divider above it: every slot of a day but the first.
        above: Put the time above the rows (``Prefs.time_above``, D-216).
    """
    slot = slot_layout(label, rows, above=above)
    return ft.Column([ft.Divider(height=1), slot], spacing=0) if divider else slot


@ft.component
def GutterProbe() -> ft.Control:
    """Measure whether slots put their time above their rows, into ``Prefs`` (D-216).

    Flet cannot read the OS text scale (U16), so an invisible copy of the widest
    gutter reports its width, and the box around it the screen's, through
    ``on_size_change`` (F51): at mount, after a text size change and after a
    rotation. ``Prefs.time_above`` changes only when ``time_above()``'s answer does,
    so the lists re-render only then. ``AppScaffold`` places it on every screen, so
    the answer is known before a list with slots opens.

    The probe is 0 dp high, under the body in the View's column: it takes no space,
    shows nothing (``opacity=0``) and is left out of the semantics tree. Not laid over
    the body in a ``Stack``: a positioned control with ``on_size_change`` breaks the
    stack's layout (F51).

    It measures the View's width, beside the body's ``SafeArea``, not inside it, and
    from 600 dp takes the rail's width off it (``slot_width()``, D-277). Only in
    landscape on a phone with a notch or a cutout do the SafeArea's side insets make
    a slot narrower than that, by up to about 15 %, and there even the largest gutter
    stays under a fifth of the narrower width (D-216), so the answer is the same.
    """
    prefs = use_prefs()
    # Plain holders: a measurement re-renders nothing; only the answer goes to Prefs.
    widths = ft.use_ref(lambda: {"gutter": 0.0, "body": 0.0})

    @report_errors
    def gutter_measured(e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        _record(prefs, widths.current, "gutter", e.width)

    @report_errors
    def body_measured(e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        _record(prefs, widths.current, "body", e.width)

    gutter = ft.Container(
        _widest(twelve_hour=True),  # "AM" is narrower than "10:00": either clock
        padding=PADDING,
        on_size_change=gutter_measured,
    )
    return ft.Container(
        # In a row, the gutter takes its own width and the row the View's. Flutter
        # leaves a child at opacity 0 out of the semantics tree, as the gutter's own
        # invisible time is.
        ft.Row([gutter]),
        height=0,  # the text still lays out at its own width
        on_size_change=body_measured,
    )


def _record(
    prefs: Prefs, widths: dict[str, float] | None, name: str, width: float
) -> None:
    """Keep a measured width, and set ``Prefs.time_above`` once both are known."""
    assert widths is not None  # the probe's ref, set by its initialiser
    widths[name] = width
    if not (widths["gutter"] and widths["body"]):
        # A probe that has heard of one width only knows nothing yet. Each screen
        # mounts its own, and answering "beside" here flipped every list back to the
        # gutter for a frame or two, under the Schedule's jump to now.
        return
    # An observable notifies only when a value changes, so an unchanged answer
    # re-renders no reader.
    prefs.time_above = time_above(widths["gutter"], slot_width(widths["body"]))
    prefs.time_measured = True  # opens the boot gate, with the loaded settings


def _heading(label: str, content: ft.Control) -> ft.Control:
    """A slot's time as screen readers get it: a heading, read once, as ``label``.

    Level 3: a slot under its day, a level-2 day heading or the selected day tab
    (D-211).
    """
    return ft.Semantics(
        header=True,
        heading_level=3,
        label=label,
        exclude_semantics=True,  # else it reads "9:25 AM, 9:25, AM"
        content=content,
    )


def _widest(*, twelve_hour: bool) -> ft.Control:
    """The gutter's widest time, invisible: it sets the width of every slot's gutter."""
    # Roboto's digits are tabular (D-26), so "10:00" is as wide as any time.
    if twelve_hour:
        return _gutter_lines("10:00", "AM", 0)
    return _gutter_lines("00:00", "", 0)


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
