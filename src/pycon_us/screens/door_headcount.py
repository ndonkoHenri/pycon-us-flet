"""Door check's headcount: "42 checked in" under the session chip (DOOR-06, D-442).

What it counts is D-442's rule: the signed-in account's check-ins on this device for
the chosen session's products, read from the outbox (``core/admission.headcount()``),
so the distinct codes among its door rows, pending, synced or failed, whose products
overlap the session's. It therefore survives a restart and a trip to another tool,
comes back when the session is chosen again, and never moves on "Already checked in",
which reads the same rows (STORE-12). It is per device: the API has no total.

``use_headcount()`` reads it again whenever the outbox changes (``Staff.revision``,
bumped after each admission and each sync pass). A failed read says so and is never
shown as 0 (D-120). The line is one node, not a live region: the result panel already
says each scan, so the count isn't said after every one (#767).
"""

from collections.abc import Iterable

import flet as ft

from pycon_us.core.admission import headcount
from pycon_us.core.outbox import Status
from pycon_us.services import use_services
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.staff import use_staff

UNAVAILABLE = "Check-in count unavailable"
"""What the line says when the outbox can't be read (D-120)."""


def use_headcount(owner: str, product_ids: Iterable[int]) -> int | None:
    """Return how many attendees this account checked in for the session.

    Call it on every render (D-70); with no session chosen, pass no products.

    Args:
        owner: The signed-in account's lower-cased email.
        product_ids: The chosen session's products.

    Returns:
        The count, or None when the outbox couldn't be read.
    """
    svc = use_services()
    staff = use_staff()
    ids = tuple(dict.fromkeys(product_ids))
    return ft.use_memo(
        lambda: read_headcount(svc.outbox, owner, ids),
        [owner, ids, staff.revision],
    )


def read_headcount(
    db: OutboxDb | None, owner: str, product_ids: tuple[int, ...]
) -> int | None:
    """Read the count from the account's rows: 0 without products, None on a failure.

    Args:
        db: The outbox (``Services.outbox``); None can't be read.
        owner: The account.
        product_ids: The session's products.
    """
    if not product_ids:
        return 0
    rows = None if db is None else db.rows(owner, tuple(Status))
    return None if rows is None else headcount(rows, product_ids)


def headcount_words(count: int | None) -> str:
    """Return what the line shows: "42 checked in", or that the count is unavailable."""
    return UNAVAILABLE if count is None else f"{count:,} checked in"


def headcount_line(count: int | None) -> ft.Control:
    """Return the headcount, large (``DISPLAY_SMALL``), as one node (``door.headcount``).

    Read "42 checked in for this session"; a failed read is a plain line in
    ``error``. The words wrap at large text.

    Args:
        count: The count, or None when it couldn't be read.
    """
    words = headcount_words(count)
    text = (
        ft.Text(
            words,
            theme_style=ft.TextThemeStyle.DISPLAY_SMALL,
            color=ft.Colors.ON_SURFACE,
        )
        if count is not None
        else ft.Text(
            words, theme_style=ft.TextThemeStyle.BODY_MEDIUM, color=ft.Colors.ERROR
        )
    )
    return ft.Semantics(
        identifier="door.headcount",
        container=True,
        label=words if count is None else f"{words} for this session",
        exclude_semantics=True,  # the label says it, once
        content=text,
    )
