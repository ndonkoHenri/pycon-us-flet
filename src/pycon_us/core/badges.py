"""What a scanned badge says, and the per-code scan cooldown (LEAD-03, LEAD-01; D-65).

A badge's QR code, and what a HID scanner or manual entry types, is ``code:validator``
(``tools/mock_api/badges.py`` prints it), possibly with more ``:`` segments.
``parse_badge()`` keeps Ionic's rules, which the server expects (architecture §12.5):
the access code is segment 0; Door check and Swag pickup send segment 1 as
``badge_validator``; the Lead scanner sends the **last** segment; CoC sends the code
only. ``Cooldown`` accepts one result per code every 4 s, since a held code is reported
about 3.6 times a second (D-293). Both are pure: the caller passes the time in.
"""

from dataclasses import dataclass, field

COOLDOWN_SECONDS = 4.0
"""How long a code just accepted is ignored when scanned again (D-65)."""


@dataclass(frozen=True)
class Badge:
    """A parsed badge payload.

    Attributes:
        code: The attendee's access code, segment 0; what CoC sends and storage keys use.
        door_validator: Segment 1, the ``badge_validator`` Door check and Swag pickup
            send.
        lead_validator: The last segment, the ``badge_validator`` the Lead scanner sends.
    """

    code: str
    door_validator: str
    lead_validator: str


def parse_badge(raw: str) -> Badge | None:
    """Read a badge payload as Ionic's pages split it (LEAD-03).

    Args:
        raw: What the scanner or the manual field gave; surrounding whitespace (a HID
            scanner's trailing newline) is ignored.

    Returns:
        The badge, or None when it is not one: no ``:``, or an empty access code (the
        screen says "Not a badge code"). Empty validators are kept as ``""``: the
        server decides about them.
    """
    code, colon, rest = raw.strip().partition(":")
    if not colon or not code:
        return None
    segments = rest.split(":")
    return Badge(code, segments[0], segments[-1])


@dataclass
class Cooldown:
    """One accepted result per code every ``seconds``; a different code goes at once.

    Attributes:
        seconds: How long an accepted code is then ignored.
    """

    seconds: float = COOLDOWN_SECONDS
    _accepted: dict[str, float] = field(default_factory=dict, repr=False)

    def accept(self, code: str, now: float) -> bool:
        """Say whether a scan of ``code`` counts, and remember it when it does.

        Args:
            code: The scanned access code.
            now: The time of the scan in seconds, from a clock that never goes back
                (``time.monotonic()``).

        Returns:
            True when ``code`` was not accepted in the last ``seconds``; a held code is
            so accepted once per ``seconds``, from its first scan.
        """
        # Forget codes whose cooldown has passed, so the memory stays a few entries.
        self._accepted = {
            seen: at for seen, at in self._accepted.items() if now - at < self.seconds
        }
        if code in self._accepted:
            return False
        self._accepted[code] = now
        return True
