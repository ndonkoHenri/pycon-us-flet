"""A button's padding at every text size (D-344), and its label while it works.

Flutter shrinks such a button's side padding as the text grows: 24 dp at 100 %, 12 at
200 % and 6 at 300 % and over (``ButtonStyleButton.scaledPadding``). At the largest
text the label then nearly touches the pill's rounded ends, so every such button whose
label can grow takes one of these as its ``ButtonStyle(padding=...)``: Material's own
100 % padding, at every size. A text button has no edge to touch, so it keeps
Flutter's default.

A filled or tonal button given a style also needs ``elevation=0``: with a style, Flet
lifts every state, disabled included, to the button's ``elevation`` (1 by default),
and M3's filled and tonal buttons lie flat. An outlined button has no ``elevation``
of its own and stays flat.

``busy_label()`` is what a button says while the work it started is in flight.
"""

import flet as ft

LABEL_PADDING = ft.Padding.symmetric(horizontal=24, vertical=8)
"""A button with only a label: M3's 24 dp sides, and 8 dp above and below.

The 8 dp keep a tall label off the pill's top and bottom; at 100 % the 20 dp label
line and its 16 dp are under Material's 40 dp minimum, so the button keeps its height.
"""

ICON_PADDING = ft.Padding.only(left=16, top=10, right=24, bottom=10)
"""A button with a leading icon: M3's 16 dp before the icon and 24 dp after the label.

The 10 dp above and below keep a tall label off the pill's edges, and keep the
one-line button 40 dp tall at 100 % (the 20 dp icon and its 20 dp).
"""


def busy_label(words: str, *, wrap: bool = False) -> ft.Control:
    """Return a button's label while its work is in flight: a small ring and ``words``.

    The words change with the ring, so a screen reader says the busy state too.

    Args:
        words: What the button is doing: "Signing in…".
        wrap: Let a narrow action put its ring and label on separate lines.
    """
    return ft.Row(
        [ft.ProgressRing(width=16, height=16, stroke_width=2), ft.Text(words)],
        spacing=8,
        tight=True,
        wrap=wrap,
        alignment=ft.MainAxisAlignment.CENTER if wrap else ft.MainAxisAlignment.START,
    )
