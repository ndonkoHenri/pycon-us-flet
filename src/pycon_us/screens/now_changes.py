"""Now's Schedule changes card: "2 saved sessions changed · Review" (ux.md §5.1 item 6).

NEW-04, D-255. Under Your next session on the conference days, only while the unseen
batches of the last 24 hours change saved sessions (``core.change_views.now_card_text()``:
each session once, additions left out, changes to unsaved sessions never). A tap pushes
Schedule changes on Now (``/now/changes/<year>``), so Back returns here. The card goes
once its batches are seen: 2 s on the list, or Mark all as seen (ux.md §6.4); left
sooner, it stays. Apart from ``now.py`` so that the screen stays under about 400 lines
(D-66).
"""

from collections.abc import Collection
from datetime import datetime

import flet as ft

from pycon_us.change_log import ChangeLog
from pycon_us.core.change_views import now_card_text
from pycon_us.locations import drill_href
from pycon_us.ui.rows import LinkTile

IDENTIFIER = "now.changes"
"""The card's one node (decisions §M)."""

REVIEW = "Review"
"""The card's second line: what a tap does."""


def changes_card(
    change_log: ChangeLog,
    saved: Collection[str],
    now: datetime,
    *,
    view_path: str,
    year: int,
) -> list[ft.Control]:
    """Return the card, or nothing while no unseen change touches a saved session.

    One button node, read "2 saved sessions changed, Review" (``LinkTile``).

    Args:
        change_log: The session's ``ChangeLog``.
        saved: The ids of the saved sessions.
        now: The current instant (aware), ``clock.now()``.
        view_path: Now's View path, which the list is pushed on.
        year: The active conference year: the list's drill id (D-255).
    """
    text = now_card_text(change_log.batches, saved, now)
    if text is None:
        return []
    return [
        ft.Card(
            LinkTile(
                text,
                drill_href(view_path, "changes", str(year)),
                icon=ft.Icons.CHANGE_CIRCLE_OUTLINED,
                subtitle=REVIEW,
                identifier=IDENTIFIER,
            ),
            variant=ft.CardVariant.OUTLINED,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the row's ink stays inside
            margin=ft.Margin.only(left=16, top=8, right=16),
        )
    ]
