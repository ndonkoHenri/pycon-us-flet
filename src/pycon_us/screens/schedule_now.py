"""Where now is on the Schedule: today's now line, and what a jump to now left in view.

``screens/schedule.py`` jumps to now (D-155, D-204) and ``screens/schedule_days.py``
lays out the day lists; these are the pieces they share:

- ``NowMark`` and ``NowLine``: today's "Now · 10:42 AM" line, before the first slot still
  to start; a jump lands on it when no slot is on (``NowPlace.target``);
- ``Landing``: where the last jump left today's list, so the "Now" button hides while
  that place is on screen;
- ``spoken_place()``: where a jump the user asked for landed, for a screen reader.
"""

from dataclasses import dataclass
from datetime import date, datetime, tzinfo

import flet as ft

from pycon_us.core.timefmt import time_label
from pycon_us.core.timeline import NOW_KEY, NowPlace, Slot

NOW_LINE = 2
"""The now line's thickness in dp (ux.md §5.2): twice a slot's divider, in ``primary``."""


@dataclass(frozen=True)
class NowMark:
    """Where today's list draws its now line, and the time it says (D-204).

    A value, so a day list given the same mark skips its render (D-153): the index
    moves when a slot starts, the time once a minute.

    Attributes:
        index: The slot the line sits above (``NowPlace.line``); the number of slots
            puts it after the last.
        time: The time it says, e.g. "10:42 AM" (``timefmt.time_label()``).
    """

    index: int
    time: str


def NowLine(time: str) -> ft.Control:
    """Return today's now line: "Now · 10:42 AM" before a 2 dp ``primary`` line (D-204).

    A memoised component keyed by ``NOW_KEY``, so a minute re-renders it alone and a
    slot's start moves it rather than building a new one; its box carries
    ``ScrollKey(NOW_KEY)``, where a jump lands when no slot is on. A screen reader
    hears "Current time 10:42 AM"; not a live region, which would speak every minute.

    Args:
        time: The time it says, e.g. "10:42 AM".
    """
    return _NowLine(time, key=NOW_KEY)  # pyright: ignore[reportCallIssue]  # as SessionRow's


@ft.memo
@ft.component
def _NowLine(time: str) -> ft.Control:
    """The body of ``NowLine``; it runs only when the time changes (F34)."""
    line = ft.Row(
        [
            ft.Text(
                f"Now · {time}",
                theme_style=ft.TextThemeStyle.LABEL_MEDIUM,
                color=ft.Colors.PRIMARY,
            ),
            ft.Container(
                height=NOW_LINE,
                border_radius=NOW_LINE / 2,
                bgcolor=ft.Colors.PRIMARY,
                expand=True,
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return ft.Container(
        ft.Semantics(
            identifier="schedule.now_line",
            label=f"Current time {time}",
            exclude_semantics=True,
            container=True,
            content=line,
        ),
        key=ft.ScrollKey(NOW_KEY),
        padding=ft.Padding.symmetric(horizontal=16, vertical=4),
    )


@dataclass(frozen=True)
class Landing:
    """Where a jump to now left today's list, and what was on screen there (D-204).

    Attributes:
        day: The list's day, today when it jumped.
        place: Where now was among its slots: the place the list showed.
        version: The feed version and
        excluded: the filter its slots were laid out with: either changes the
            heights above the place, so the offset no longer locates it.
        pixels: The list's offset once it landed.
    """

    day: date
    place: NowPlace
    version: int
    excluded: tuple[str, ...]
    pixels: float

    def shows(
        self, day: date, place: NowPlace | None, version: int, excluded: tuple[str, ...]
    ) -> bool:
        """Whether this landing is where now is: the same day, place, feed and filter."""
        return (self.day, self.place, self.version, self.excluded) == (
            day,
            place,
            version,
            excluded,
        )

    def near(self, pixels: float, viewport: float) -> bool:
        """Whether a list scrolled to ``pixels`` still shows the place it landed on.

        Within half a screen of the landing: the place's top is then in the upper half
        of the screen, or less than half a screen above it, where its rows still show.
        """
        return abs(pixels - self.pixels) < viewport / 2


def spoken_place(
    place: NowPlace,
    slots: tuple[Slot, ...],
    at: datetime,
    zone: tzinfo,
    *,
    use_24h: bool,
) -> str:
    """Return where a jump to now landed, as a screen reader hears it after the day.

    "2:00 PM" for the slot that is on; "current time 12:40 PM" for the now line, which
    reads "Current time 12:40 PM" itself.
    """
    if place.on is not None:
        slot = next(slot for slot in slots if slot.key == place.on)
        return time_label(slot.start, zone, use_24h=use_24h)
    return f"current time {time_label(at, zone, use_24h=use_24h)}"
