"""A lead note's structure and its text, as the server and Ionic's records keep it (LEAD-10).

The note sheet edits a ``LeadNote``: how interested the attendee was, what to follow
up with and free text. The outbox sends it as one string (``core/outbox.save_note``,
D-407) in Ionic's format (``composeNote``), so the server and older records still read
it (docs/research/ionic/staff-tools-auth.md §7a): one line each, only when set,

    Interest: warm
    Follow-up: Demo, Hiring
    Notes: Wants a call next week.

``parse()`` reads it back with Ionic's regexes (``parseNote``), case-insensitively; a
note that matches none of them is a legacy free-text note, all of it ``text``.
"""

import re
from dataclasses import dataclass
from enum import StrEnum


class Interest(StrEnum):
    """How interested the attendee was; the value is the note's word."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


FOLLOW_UPS = ("Send info", "Demo", "Newsletter", "Hiring", "Partner")
"""The follow-up labels, in the sheet's order, which is also the note's (Ionic's)."""

INTEREST_RE = re.compile(r"Interest: (hot|warm|cold)", re.IGNORECASE)
FOLLOW_UP_RE = re.compile(r"Follow-up: (.+)", re.IGNORECASE)
NOTES_RE = re.compile(r"Notes: ([\s\S]*)$", re.IGNORECASE)
"""Ionic's ``parseNote`` patterns; ``.`` stops at a line's end, ``[\\s\\S]`` does not."""


@dataclass(frozen=True)
class LeadNote:
    """A lead note's parts.

    Attributes:
        interest: Hot, warm or cold; None when not chosen.
        follow_ups: The chosen labels of ``FOLLOW_UPS``, in that order.
        text: The free text.
    """

    interest: Interest | None = None
    follow_ups: tuple[str, ...] = ()
    text: str = ""


def compose(note: LeadNote) -> str:
    """Return the note's text: the Interest, Follow-up and Notes lines that are set.

    The follow-ups keep ``FOLLOW_UPS``' order and the text is trimmed, as Ionic's
    ``composeNote``. Nothing set gives ``""``, which ``save_note`` ignores.
    """
    lines = []
    if note.interest is not None:
        lines.append(f"Interest: {note.interest.value}")
    follow_ups = [label for label in FOLLOW_UPS if label in note.follow_ups]
    if follow_ups:
        lines.append(f"Follow-up: {', '.join(follow_ups)}")
    if note.text.strip():
        lines.append(f"Notes: {note.text.strip()}")
    return "\n".join(lines)


def parse(text: str) -> LeadNote:
    """Return the parts of a note's text, as Ionic's ``parseNote`` reads it.

    The follow-ups are the known labels among the ``Follow-up:`` line's, matched
    case-insensitively; an unknown one is dropped, as Ionic drops it. Interest and
    Follow-up are looked for only before ``Notes:``, so free text that mentions them
    stays text (Ionic searched the whole note). A text that none of the three
    patterns matches is a legacy note: all of it is the free text.

    Args:
        text: A note as the outbox keeps it (``payload["note"]``).
    """
    notes = NOTES_RE.search(text)
    head = text if notes is None else text[: notes.start()]  # the text is no line
    interest = INTEREST_RE.search(head)
    follow_up = FOLLOW_UP_RE.search(head)
    if interest is None and follow_up is None and notes is None:
        return LeadNote(text=text.strip())
    named = set()
    if follow_up is not None:
        named = {label.strip().lower() for label in follow_up.group(1).split(",")}
    return LeadNote(
        interest=Interest(interest.group(1).lower()) if interest else None,
        follow_ups=tuple(label for label in FOLLOW_UPS if label.lower() in named),
        text=notes.group(1).strip() if notes else "",
    )
