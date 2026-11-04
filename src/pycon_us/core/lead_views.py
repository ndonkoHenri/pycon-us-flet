"""A lead as the leads list shows it, and the list's search and sponsor filter (#743).

LEAD-06, LEAD-08, DATA-31. Pure: `lead_view()` turns an outbox `lead` row into
the lines of its row on `screens/staff_leads.py`'s page: the attendee's first name
from the stored answer, else the access code (a pending lead has no answer, so it
shows only its code, PII-light); its status in `status_text()`'s words (D-410); how
long ago it was scanned; the sponsor it was scanned for (a staff account's snapshot,
STORE-11), so two sponsors' leads on one attendee are two rows (D-459); and whether it
has a note. `filter_leads()` searches the name and the
code and keeps one sponsor's leads by **id**, never by name: Ionic compared names,
which two sponsors whose names differ only by quotes share.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from pycon_us.core.outbox import Row, Status, status_text
from pycon_us.core.queries import fold
from pycon_us.core.timefmt import ago_label


@dataclass(frozen=True)
class LeadView:
    """One lead's row, as words: compared by value, so a memoised row skips a re-render.

    Attributes:
        code: The lead's access code, its key.
        name: The attendee's first name, once the capture's answer has it; else None.
        status: Pending, synced or failed: the row's icon.
        words: The status in words, "Confirmed · may be recorded twice" when flagged.
        flagged: The send may have been recorded twice (D-410): a warning icon.
        ago: When it was scanned, "5 minutes ago".
        sponsor_id: The sponsor it was scanned for; None for a sponsor's own lead.
        sponsor_name: That sponsor's name, shown on a staff account's rows.
        has_note: A note row exists for the lead.
    """

    code: str
    name: str | None
    status: Status
    words: str
    flagged: bool
    ago: str
    sponsor_id: str | None
    sponsor_name: str | None
    has_note: bool

    @property
    def title(self) -> str:
        """Return the row's title: the first name, or the code without one."""
        return self.name or self.code

    @property
    def key(self) -> str:
        """Return what tells the row apart: the code, with a staff lead's sponsor id."""
        return (
            self.code if self.sponsor_id is None else f"{self.code}.{self.sponsor_id}"
        )


def for_line(sponsor_name: str) -> str:
    """Return which sponsor a lead is for, in words: "For Example Corp" (D-459)."""
    return f"For {sponsor_name}"


def first_name(row: Row) -> str | None:
    """Return the first name the capture's answer stored (`{first_name}`), if any."""
    result = row.payload.get("result")
    name = result.get("first_name") if isinstance(result, Mapping) else None
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()


def lead_view(row: Row, has_note: bool, now: float) -> LeadView:
    """Return a lead row's lines.

    Args:
        row: A `lead` row of the outbox.
        has_note: Whether the account has a note row for the lead.
        now: The current time (epoch seconds), for "5 minutes ago".
    """
    return LeadView(
        code=row.key,
        name=first_name(row),
        status=row.status,
        words=status_text(row),
        flagged=row.maybe_sent,
        ago=ago_label(
            datetime.fromtimestamp(row.created_at, UTC),
            datetime.fromtimestamp(now, UTC),
        ),
        sponsor_id=row.sponsor_id,
        sponsor_name=row.sponsor_name,
        has_note=has_note,
    )


def phrase(view: LeadView) -> str:
    """Return what a screen reader says for a row, as one phrase (ux.md §9).

    E.g. "Ada, Confirmed, 5 minutes ago, Example Corp, has a note": the status in
    words, so it is never the icon's colour alone, and the flag as words too.
    """
    parts = [view.title, view.words.replace(" · ", ", "), view.ago]
    if view.sponsor_name:
        parts.append(view.sponsor_name)
    if view.has_note:
        parts.append("has a note")
    return ", ".join(parts)


def filter_leads(
    views: Sequence[LeadView], query: str, sponsor_id: str | None
) -> tuple[LeadView, ...]:
    """Return the leads that match the search and, when given, the sponsor.

    Each word of `query`, folded as search folds (D-46), must be in the name or the
    code, anywhere; a pending lead is found by its code only, as that is all it shows.

    Args:
        views: The leads, in their order (newest first).
        query: What the user typed.
        sponsor_id: Keep only the leads scanned for this sponsor ("Only Example
            Corp", LEAD-06), compared by id; None keeps every sponsor's.

    Returns:
        The leads found, in their order.
    """
    words = fold(query).split()
    return tuple(
        view
        for view in views
        if (sponsor_id is None or view.sponsor_id == sponsor_id)
        and all(word in fold(f"{view.name or ''} {view.code}") for word in words)
    )
