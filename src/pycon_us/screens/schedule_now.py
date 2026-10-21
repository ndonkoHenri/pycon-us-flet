"""Where now is on the Schedule: today's now line, and what a jump to now left in view.

``screens/schedule.py`` jumps to now (D-155, D-204) and ``screens/schedule_days.py``
lays out the day lists; these are the pieces they share:

- ``NowMark`` and ``NowLine``: today's "Now · 10:42 AM" line, before the first slot still
  to start; a jump lands on it when no slot is on (``NowPlace.target``);
- ``Landing``, ``PENDING``, ``InView`` and ``shows_now()``: where the last jump left
  today's list, so the "Now" button hides while the list is near it;
- ``Signals`` and ``jumps_by_itself()``: what the screen's handlers tell its jumps, and
  whether showing a day jumps by itself (today's first display);
- ``spoken_place()``: where a jump the user asked for landed, for a screen reader,
  and ``landing_note()``, which says it to TalkBack (D-241).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, tzinfo

import flet as ft

from pycon_us.core.timefmt import time_label
from pycon_us.core.timeline import NOW_KEY, NowPlace, Slot
from pycon_us.memory import ViewMemory
from pycon_us.services.errors import report_errors
from pycon_us.ui.scrolling import anchored

NOW_LINE = 2
"""The now line's thickness in dp (ux.md §5.2): twice a slot's divider, in ``primary``."""

SAID_S = 5.0
"""How long the landing note keeps its words, in seconds (D-241): long enough for
TalkBack to read them out, short enough that the note is no lasting stop."""


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


def NowLine(
    time: str, day: date, on_measure: Callable[[date, str, float], None]
) -> ft.Control:
    """Return today's now line: "Now · 10:42 AM" before a 2 dp ``primary`` line (D-204).

    A memoised component keyed by ``NOW_KEY``, so a minute re-renders it alone and a
    slot's start moves it rather than building a new one; an anchor above it carries
    ``ScrollKey(NOW_KEY)``, where a jump lands when no slot is on (D-242). A screen reader
    hears "Current time 10:42 AM"; not a live region, which would speak every minute.

    Args:
        time: The time it says, e.g. "10:42 AM".
        day: Today, which it reports its height with.
        on_measure: The Schedule's height handler, a stable callable (D-331).
    """
    return _NowLine(time, day, on_measure, key=NOW_KEY)  # pyright: ignore[reportCallIssue]  # as SessionRow's


@ft.memo
@ft.component
def _NowLine(
    time: str, day: date, on_measure: Callable[[date, str, float], None]
) -> ft.Control:
    """The body of ``NowLine``; it runs only when the time changes (F34)."""

    @report_errors
    def measured(e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        on_measure(day, NOW_KEY, e.height)

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
    box = ft.Container(
        ft.Semantics(
            identifier="schedule.now_line",
            label=f"Current time {time}",
            exclude_semantics=True,
            container=True,
            content=line,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=4),
    )
    # Its node stays while TalkBack is on it (D-242); its height places the list's top
    # among the items (D-331).
    return ft.Container(anchored(NOW_KEY, box), on_size_change=measured)


@dataclass(frozen=True)
class Landing:
    """Where a jump to now left today's list, and what was on screen there (D-204).

    A scroll of the user's own while a jump is waiting ends it as its landing, since a
    scroll end does not say who scrolled (the pinned ``ListView.scroll_to()`` returns
    nothing about where it got to); the next half-screen scroll corrects the button.

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
        """Whether a list scrolled to ``pixels`` is within half a screen of the landing.

        A plain distance, not whether the place is on screen: a scroll offset alone
        does not say where a keyed item sits (a jump near the list's end stops short
        of it), so the place may show in the lower half while the button is back. A
        tap then still moves it, so the button is never a dead control.
        """
        return abs(pixels - self.pixels) < viewport / 2


@dataclass(frozen=True)
class Pending:
    """A jump by itself is on its way to now; ``PENDING`` is the one value."""


PENDING = Pending()
"""What the Schedule knows of today's list while its first jump runs (D-204)."""

type InView = Landing | Pending | None
"""What the "Now" button knows of today's list: where a jump left it; ``PENDING``
while a jump by itself is on its way; None when it is nowhere in particular."""


def shows_now(
    in_view: InView,
    day: date,
    place: NowPlace | None,
    version: int,
    excluded: tuple[str, ...],
) -> bool:
    """Whether today's list is where "Now" goes, so the button hides (D-204).

    ``PENDING`` counts: a first display's jump on a list already in place answers only
    after its tries, and the button must not flash for those seconds.

    Args:
        in_view: What the screen knows of today's list.
        day: Today, the list's day.
        place: Where now is among today's slots, as the screen shows it.
        version: The feed version the slots were laid out from.
        excluded: The filter they were laid out with.
    """
    if isinstance(in_view, Pending):
        return True
    return in_view is not None and in_view.shows(day, place, version, excluded)


@dataclass(eq=False)
class Signals:
    """What the Schedule's handlers tell its jumps; one per mounted screen.

    Attributes:
        ended: Set when the shown list's scroll ends (``jump_to_key()``).
        settled: Set when ``Tabs`` reports a day, which it does once a switch has
            finished sliding, the one asked for from Python included.
        landing: Where the last jump left today's list; each scroll end of that list
            is measured against it.
    """

    ended: asyncio.Event = field(default_factory=asyncio.Event)
    settled: asyncio.Event = field(default_factory=asyncio.Event)
    landing: Landing | None = None


def jumps_by_itself(
    day: date, current: date, today_slots: tuple[Slot, ...], memory: ViewMemory
) -> bool:
    """Whether showing ``day`` jumps to now unasked: today's first display (D-204).

    Once per conference day in the process (``ViewMemory.jumped_on``, D-18), read when
    the day shows, since a jump may have run since the render.
    """
    return day == current and bool(today_slots) and memory.jumped_on != current


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


def landing_note(words: str) -> ft.Control:
    """Return where a jump the user asked for landed, as a polite live region (D-241).

    Flutter reports no announcements on Android (F13), so TalkBack hears the landing
    through this node: each time ``words`` changes to a phrase, the engine sends a
    content change for it, which TalkBack reads without moving its focus off the
    "Now" button. Empty, it has nothing a reader could stop on, so it is only in
    linear navigation while it holds words (``SAID_S``); the same words twice must
    pass through empty to be said again. 1 dp square at the list's top start, under
    the list: a node with no size is dropped from the tree, and the list takes any
    touch there. iOS keeps ``announce_message()``: iOS takes announcements, so
    it is the direct path there (D-241).

    Args:
        words: Where the list went, "Friday, May 15, 2:00 PM"; empty between landings.
    """
    return ft.Container(
        ft.Semantics(
            identifier="schedule.landing",
            label=words,
            live_region=True,
            container=True,
            content=ft.Container(width=1, height=1),
        ),
        left=0,
        top=0,
    )
