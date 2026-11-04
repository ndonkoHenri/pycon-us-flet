"""What a scanned badge says, the per-code scan cooldown and a scan's result (D-65).

A badge's QR code, and what a HID scanner or manual entry types, is `code:validator`
(`tools/mock_api/badges.py` prints it), possibly with more `:` segments.
`parse_badge()` keeps Ionic's rules, which the server expects (architecture §12.5):
the access code is segment 0; Door check and Swag pickup send segment 1 as
`badge_validator`; the Lead scanner sends the **last** segment; CoC sends the code
only. `Cooldown` accepts one result per code every 4 s, since a held code is reported
about 3.6 times a second (D-293). Both are pure: the caller passes the time in.
`parse_badge()` refuses what cannot be a badge, a URL or a contact card from a QR
code that is not one (D-477).
`ScanResult` is what a tool's handler returns for the scan screen's result panel
(LEAD-01, LEAD-09; `ui/scan_screen.py`), data only: the panel picks the colour and
icon from its `ScanOutcome`, and draws its `Tag` list (Door check's dietary needs
and allergy, DOOR-05) as chips.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

from pycon_us.core.lead_sponsors import LeadSponsor

COOLDOWN_SECONDS = 4.0
"""How long a code just accepted is ignored when scanned again (D-65)."""


@dataclass(frozen=True)
class Badge:
    """A parsed badge payload.

    Attributes:
        code: The attendee's access code, segment 0; what CoC sends and storage keys use.
        door_validator: Segment 1, the `badge_validator` Door check and Swag pickup
            send.
        lead_validator: The last segment, the `badge_validator` the Lead scanner sends.
    """

    code: str
    door_validator: str
    lead_validator: str


CODE_SHAPE = re.compile(r"[A-Za-z0-9._~-]+")
"""What an access code is made of: the URL-unreserved characters (D-477). The original
app puts the code unencoded into request paths, queries and storage keys, so the
server's codes survive that; a code outside this set would need a one-line change."""

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
"""A newline or other control character: a contact card or a multi-line text, never a
badge (D-477)."""

QR_FORMATS = frozenset(
    {"begin", "mecard", "matmsg", "wifi", "smsto", "sms", "tel", "mailto", "geo"}
)
"""The first word, in lower case, of the QR contents people scan that are not badges: a
vCard or vCalendar (`BEGIN:`), MeCard, an email, Wi-Fi network (whose password would
become the lead validator), SMS, phone or location. A HID scanner types a contact card
one line per Enter, so its first line has no newline to catch. A short backstop, not a
list of every scheme (D-477)."""


def parse_badge(raw: str) -> Badge | None:
    """Read a badge payload as Ionic's pages split it (LEAD-03), refusing non-badges.

    Args:
        raw: What the scanner or the manual field gave; surrounding whitespace (a HID
            scanner's trailing newline) is ignored.

    Returns:
        The badge, or None when it is not one (the screen says "Not a badge code"): no
        `:`; an access code that is empty, has a character outside `CODE_SHAPE` or
        is one of `QR_FORMATS` (`BEGIN:VCARD`, `WIFI:...`); a control character
        anywhere (a vCard in one text); or `//` right after the first `:` (a URL,
        `https://...`). Empty validators are kept as `""`: the server decides
        about them. A URL scheme such as `otpauth:` still passes: it has a badge's
        shape, and the server answers "not registered" (D-477).
    """
    text = raw.strip()
    code, colon, rest = text.partition(":")
    if not colon or not CODE_SHAPE.fullmatch(code) or code.lower() in QR_FORMATS:
        return None
    if rest.startswith("//") or _CONTROL.search(text):
        return None
    segments = rest.split(":")
    return Badge(code, segments[0], segments[-1])


@dataclass
class Cooldown:
    """One accepted result per code every `seconds`; a different code goes at once.

    Attributes:
        seconds: How long an accepted code is then ignored.
    """

    seconds: float = COOLDOWN_SECONDS
    _accepted: dict[str, float] = field(default_factory=dict, repr=False)

    def accept(self, code: str, now: float) -> bool:
        """Say whether a scan of `code` counts, and remember it when it does.

        Args:
            code: The scanned access code.
            now: The time of the scan in seconds, from a clock that never goes back
                (`time.monotonic()`).

        Returns:
            True when `code` was not accepted in the last `seconds`; a held code is
            so accepted once per `seconds`, from its first scan.
        """
        # Forget codes whose cooldown has passed, so the memory stays a few entries.
        self._accepted = {
            seen: at for seen, at in self._accepted.items() if now - at < self.seconds
        }
        if code in self._accepted:
            return False
        self._accepted[code] = now
        return True


class ScanOutcome(StrEnum):
    """How a scan ended, which sets the result panel's colour and icon (ux.md §7.2)."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    DENIED = "denied"
    QUEUED = "queued"
    """Saved offline, to sync when online."""
    INVALID = "invalid"
    """Not a badge code: the field is cleared, the panel shows the text (D-473)."""
    RECORDED = "recorded"
    """An incident recorded (CoC, MASK-04): neutral, never a check-in's green."""
    NOT_RECORDED = "not_recorded"
    """A review closed without recording (CoC's Cancel or Back): neutral, silent."""


@dataclass(frozen=True)
class Tag:
    """A short fact about the attendee, a chip under the name: "Vegetarian" (DOOR-05).

    Attributes:
        text: The words on the chip, "Allergy: peanuts".
        warning: Something staff must not miss (an allergy): the chip is larger, comes
            first and carries a warning icon; its words say it, never colour alone.
    """

    text: str
    warning: bool = False


@dataclass(frozen=True)
class ScanResult:
    """What the result panel shows after a scan: the tool's answer, as data.

    Attributes:
        outcome: How the scan ended.
        word: The outcome in words, first and largest: "Checked in", "Badge read".
        title: The attendee's name, or the code when the tool has no name.
        details: Lines under the title and its tags, in order: a reason, validators,
            a note.
        code: The access code the result is about, so a tool can act on it ("Add
            note", #742); empty when there is none (not a badge).
        tags: Chips right under the title, warnings first: Door check's "Allergy:
            peanuts" and "Vegetarian" (DOOR-05); the other tools give none.
        email: The attendee's email, for a tool that reveals it on request (CoC's
            "Show email", MASK-05); empty without one. Never in `spoken` or the
            repr, so neither a live region nor a log line holds it (D-72).
        sponsor: The sponsor a staff account's lead was scanned for, so "Add note" goes
            to that lead whatever is chosen since (D-459); None otherwise.
        entry: The text the screen refused as not a badge, which its "Edit code" gives
            back to the field (D-473); empty for every other result.
    """

    outcome: ScanOutcome
    word: str
    title: str = ""
    details: tuple[str, ...] = ()
    code: str = ""
    tags: tuple[Tag, ...] = ()
    email: str = field(default="", repr=False)
    sponsor: LeadSponsor | None = None
    entry: str = ""

    @property
    def spoken(self) -> str:
        """The panel's words in reading order, one per line, for its live region.

        The tags are one line after the title, as drawn: "Allergy: peanuts. Vegetarian."
        """
        tags = " ".join(f"{tag.text}." for tag in self.tags)
        return "\n".join(
            line for line in (self.word, self.title, tags, *self.details) if line
        )


NOT_A_BADGE = ScanResult(
    ScanOutcome.INVALID, "Not a badge code", details=("Check the code and try again.",)
)
"""The result of an entry `parse_badge()` refuses; the screen adds the text read (D-473)."""

ENTRY_TITLE_MAX = 60
"""The most characters of a refused entry the panel's title holds, and a screen reader
says (#965): about two lines at normal text. `ScanResult.entry` keeps the whole."""


def entry_title(text: str) -> str:
    """Return a refused entry as the panel's title: one line of words, clipped to a cap.

    A URL or a contact card from a HID scan, or a long paste, would otherwise fill the
    panel and be read whole (#965). Whitespace, newlines included, collapses to single
    spaces, and a text over `ENTRY_TITLE_MAX` characters ends in an ellipsis. The cut
    counts code points, so it can split an emoji sequence or a flag: accepted, since
    badge text is mostly ASCII and the whole text is one tap away (`Edit code`).

    Args:
        text: What the field held when it was refused.
    """
    words = " ".join(text.split())
    if len(words) <= ENTRY_TITLE_MAX:
        return words
    return words[:ENTRY_TITLE_MAX].rstrip() + "\u2026"
