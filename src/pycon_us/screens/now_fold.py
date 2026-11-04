"""How long Now's Happening now and Up next are at peak times (D-327, ux.md §5.1).

At 11:10 AM on Friday of the 2026 feed ten sessions are on, and a slot of open spaces
can hold fifteen: listed whole, the two sections would push Up next and the Schedule
link several screens down. So each section shows your saved sessions, then the first
`SHOWN` others, then "Show all 10 sessions", which shows the rest in place and becomes
"Show fewer sessions". Saved sessions are never folded away.

`ordered()` and `cut()` are pure; `folded()` builds a section's rows and button.
Apart from `now.py` so that the screen stays under about 400 lines (D-66).
"""

from collections.abc import Callable

import flet as ft

from pycon_us.core.models import OPEN_SPACE, Session
from pycon_us.services.errors import report_errors
from pycon_us.ui.fold import toggle_button

SHOWN = 3
"""The rows a folded section shows after your saved sessions."""

HAPPENING = "happening"
UP_NEXT = "up_next"

SPOKEN = {HAPPENING: "happening now", UP_NEXT: "up next"}
"""What a screen reader hears after the button's words, by section."""


def ordered(sessions: tuple[Session, ...], saved: frozenset[str]) -> list[Session]:
    """Return `sessions`, saved ones first, and in each group open spaces last.

    The sort is stable, so the rest is in the slot's order (`schedule_order`).
    Open spaces come last because they are the many small rooms of a slot, and the
    Schedule hides them by default (D-20): the first rows are its talks and keynotes.

    Args:
        sessions: A section's sessions, in the slot's order.
        saved: The ids in My schedule.
    """
    return sorted(sessions, key=lambda s: (s.id not in saved, s.kind == OPEN_SPACE))


def cut(
    sessions: tuple[Session, ...], saved: frozenset[str], *, expanded: bool
) -> tuple[list[Session], bool]:
    """Return the rows a section shows, and whether it has a "Show all" button.

    Folded, it shows the saved sessions and the first `SHOWN` others; it folds only
    when that hides two rows or more, since a button in place of one row saves nothing.

    Args:
        sessions: A section's sessions, in the slot's order.
        saved: The ids in My schedule.
        expanded: Whether the user has shown them all.
    """
    rows = ordered(sessions, saved)
    keep = sum(session.id in saved for session in sessions) + SHOWN
    if len(rows) - keep < 2:
        return rows, False
    return (rows if expanded else rows[:keep]), True


def fold_key(section: str, sessions: tuple[Session, ...]) -> str:
    """Return the key an opened section is kept under: its name and its sessions.

    A new slot is a new key, so a section the user opened folds again when the slot
    changes; a minute keeps it open, and so does a star, since `sessions` are the
    section's whole set: the card's session too, which a star moves in and out.
    """
    return f"{section}:{','.join(sorted(session.id for session in sessions))}"


def folded(
    section: str,
    sessions: tuple[Session, ...],
    saved: frozenset[str],
    row: Callable[[Session], ft.Control],
    opened: frozenset[str],
    toggle: Callable[[str], None],
    *,
    whole: tuple[Session, ...],
) -> list[ft.Control]:
    """Return a section's rows, cut by `cut()`, and its "Show all" button if any.

    Args:
        section: `HAPPENING` or `UP_NEXT`: the identifier's and the label's.
        sessions: The section's rows, in the slot's order: `whole` but the card's.
        saved: The ids in My schedule.
        row: Builds one session's row.
        opened: The keys (`fold_key()`) of the sections the user opened.
        toggle: Opens or folds the section with that key.
        whole: All the section's sessions, the card's included: its key, so that a
            star that moves a session into the card or out of it keeps it open.
    """
    key = fold_key(section, whole)
    expanded = key in opened
    rows, foldable = cut(sessions, saved, expanded=expanded)
    controls: list[ft.Control] = [
        ft.Column([row(session) for session in rows], spacing=0)
    ]
    if foldable:
        word = (
            "Show fewer sessions" if expanded else f"Show all {len(sessions)} sessions"
        )

        @report_errors
        def on_click() -> None:
            toggle(key)

        controls.append(
            toggle_button(
                word,
                expanded,
                on_click,
                f"now.show_all.{section}",
                f"{word} {SPOKEN[section]}",
            )
        )
    return controls
