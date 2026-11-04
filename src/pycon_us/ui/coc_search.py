"""The CoC tool's name search: find an attendee to record an incident for (#761).

ux.md §7.3 (MASK-02, MASK-03; D-439). Not every incident comes with a badge in reach.
"Find by name" opens a full-height sheet over the scan screen
(`ui/coc_search_sheet.py`, the look) that searches the loaded directory with
`core/conduct.py`'s `search()`, 250 ms after typing pauses (D-46). A row's tap
closes the sheet and hands the attendee to the tool, which opens the review dialog
(`ui/coc_review.py`): the same dialog and the same call as a scan (D-430).

`use_find()` is the tool's hook. Each opening carries a token: Flutter reports a
sheet's dismissal after its exit animation, so a late one for an earlier sheet closes
nothing. Clear lands as `use_field_query()`'s does (D-243): keys reported before
Flutter has the empty text are dropped, so a stale query never comes back. **Privacy (D-56, D-72):** the query and the rows live in the hook's state
while the sheet is open, never stored or logged, and go when it closes.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import cast

import flet as ft

from pycon_us.core.conduct import Attendee, Matches, search
from pycon_us.prefs import use_prefs
from pycon_us.services.errors import report_errors
from pycon_us.theme import use_tokens
from pycon_us.ui.coc_search_sheet import Finding, SheetActions, find_sheet
from pycon_us.ui.hooks import use_latest_state

SEARCH_OPEN = "Paused while the search is open"
"""Why scanning is paused while the sheet is open: a HID submit is dropped."""

DEBOUNCE_SECONDS = 0.25
"""The rows follow the text once typing pauses this long (D-46)."""


@dataclass(frozen=True)
class Finder:
    """What the CoC tool gets from `use_find()`.

    Attributes:
        open: Opens the search.
        close: Closes it, forgetting the query: the tool's clear in the background
            (#762).
        is_open: The search is open: the scan screen pauses scanning meanwhile.
    """

    open: Callable[[], None]
    close: Callable[[], None]
    is_open: bool


def use_find(
    *,
    attendees: dict[str, Attendee],
    on_pick: Callable[[Attendee], Awaitable[None]],
) -> Finder:
    """Keep the search while it is open and show its sheet; return what opens it.

    Call it on every render (D-70). The handlers read the search from a ref, since a
    render may not run between two events (#756).

    Args:
        attendees: The loaded directory by access code, in its order.
        on_pick: Called with the attendee tapped, once the sheet has closed.
    """
    prefs = use_prefs()
    tokens = use_tokens()
    finding, latest, set_finding = use_latest_state(cast(Finding | None, None))
    landing = ft.use_ref(False)  # a Clear's empty text is on its way: reports are stale
    overwritten = ft.use_ref(False)  # a stale report came in meanwhile
    opening = finding.opening if finding is not None else None
    clears = finding.clears if finding is not None else 0
    # A fresh field each opening and each Clear: its first render sends "" (D-243).
    ref = ft.use_memo(ft.Ref[ft.TextField], [opening, clears])

    typed = finding.typed if finding is not None else ""

    @report_errors
    async def settle() -> None:
        # Restarted by every keystroke: Flet cancels the wait in progress (F2).
        if opening is None:
            return
        await asyncio.sleep(DEBOUNCE_SECONDS)
        current = latest.current
        if current is not None and current.opening is opening:
            set_finding(replace(current, query=typed))

    ft.use_effect(settle, [opening, typed])

    @report_errors
    def send_empty() -> None:
        current = latest.current
        if current is not None:
            landing.current, overwritten.current = True, False
            set_finding(replace(current, typed="", query="", clears=current.clears + 1))

    @report_errors
    async def land() -> None:
        # use_field_query()'s Clear landing (D-243): Flutter answers the focus once it
        # has the empty text this render sent, so reports until then are stale. The
        # focus also serves D-182: Clear goes away once used.
        if not clears or ref.current is None:
            return
        await ref.current.focus()  # a newer Clear or a close cancels it here
        landing.current = False
        if overwritten.current and ref.current.value:
            send_empty()  # a report after the render left its text on the field

    ft.use_effect(land, [clears])

    @report_errors
    def open_find() -> None:
        if latest.current is None:
            landing.current = False  # a landing the last sheet's close cut short
            set_finding(Finding())

    @report_errors
    def close() -> None:
        set_finding(None)

    @report_errors
    def dismissed(token: object) -> None:
        current = latest.current
        if current is not None and current.opening is token:
            close()  # else a late dismissal of a sheet already closed

    @report_errors
    def changed(e: ft.Event[ft.TextField]) -> None:
        current = latest.current
        if landing.current:
            overwritten.current = True  # Flutter puts the empty text over it
        elif current is not None:
            set_finding(replace(current, typed=e.control.value or ""))

    @report_errors
    async def clear(*_: object) -> None:
        send_empty()

    @report_errors
    async def pick(attendee: Attendee) -> None:
        if latest.current is None:
            return  # a second tap: the sheet is already closing
        set_finding(None)
        await on_pick(attendee)

    query = finding.query if finding is not None else ""
    matches = ft.use_memo(
        lambda: (
            search(tuple(attendees.values()), query)
            if opening is not None
            else Matches((), False)
        ),
        [opening, query, attendees],
    )
    text = ""  # empty on an opening's first render, then what Flutter reported
    if finding is not None and ref.current is not None:
        text = ref.current.value or ""
    ft.use_dialog(
        find_sheet(
            finding,
            matches,
            (ref, text),
            SheetActions(changed, clear, pick, close, dismissed),
            tokens=tokens,
            reduce_motion=prefs.reduce_motion,
        )
        if finding is not None
        else None
    )
    return Finder(open_find, close, finding is not None)
