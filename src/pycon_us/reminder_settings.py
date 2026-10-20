"""The reminder settings record: what ``Prefs.reminders`` holds (STORE-10, NOTIF-03; D-275).

``pycon.reminders`` is a JSON object merged over the defaults: a key that is missing,
unknown or badly typed never breaks a start, it reads as its default (D-120). Only the
options that work exist: session reminders and the three kinds of conference moment
(D-58), and the primer's answer (D-61); no push categories and no master toggle.
"""

import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, get_args

from pycon_us.services.storage import REMINDERS

logger = logging.getLogger(__name__)

type SessionLead = Literal[0, 5, 10, 15]
"""Minutes before a saved session that its reminder comes; 0 is off (D-58)."""

type PrimerAnswer = Literal["unasked", "accepted", "not_now"]
"""The notification primer's answer (D-61): not shown yet, "Allow", or "Not now"."""

SESSION_LEADS: tuple[SessionLead, ...] = get_args(SessionLead.__value__)
"""The session reminder's leads; the first, off, is the default."""

PRIMER_ANSWERS: tuple[PrimerAnswer, ...] = get_args(PrimerAnswer.__value__)
"""The primer's answers; the first, not asked yet, is the default."""

_BOOLS = (True, False)

_CHOICES: dict[str, tuple[object, ...]] = {
    "session_lead": SESSION_LEADS,
    "lightning": _BOOLS,
    "open_space": _BOOLS,
    "keynote": _BOOLS,
    "primer": PRIMER_ANSWERS,
}
"""Each field's allowed values, which a stored value must match in type too."""


@dataclass(frozen=True)
class ReminderSettings:
    """The reminder settings (``pycon.reminders``), with their defaults (D-275).

    Change one with ``dataclasses.replace()`` and ``Prefs.save(reminders=...)``.

    Attributes:
        session_lead: Minutes before each session in My schedule that its reminder
            comes, or 0 for none. Off until the primer is accepted (D-275).
        lightning: Remind about the lightning-talk sign-ups (a conference moment).
        open_space: Remind about the open-space sign-ups.
        keynote: Remind before the keynotes and panels.
        primer: The notification primer's answer (D-61).

    Raises:
        ValueError: A field is not one of its allowed values (a bool is no lead).
    """

    session_lead: SessionLead = 0
    lightning: bool = True
    open_space: bool = True
    keynote: bool = True
    primer: PrimerAnswer = "unasked"

    def __post_init__(self) -> None:
        """Refuse a value outside its field's set, so a bad record is never saved."""
        for name, choices in _CHOICES.items():
            if not _allowed(getattr(self, name), choices):
                raise ValueError(f"{name} must be one of {choices}")

    @classmethod
    def from_stored(cls, stored: Mapping[str, Any]) -> ReminderSettings:
        """Return the settings a stored record holds, merged over the defaults.

        A missing key reads as its default; so does a key whose value is not one of its
        field's values, and an unknown key is dropped. Both are logged together in one
        line that names the keys, never the values (D-120).

        Args:
            stored: The decoded ``pycon.reminders`` object; ``{}`` when it is absent.
        """
        values: dict[str, Any] = {}
        defaulted: list[str] = []
        for name, choices in _CHOICES.items():
            if name not in stored:
                continue
            if _allowed(stored[name], choices):
                values[name] = stored[name]
            else:
                defaulted.append(name)
        unknown = sorted(str(key) for key in stored if key not in _CHOICES)
        problems = []
        if defaulted:
            problems.append(f"read as their defaults: {', '.join(defaulted)}")
        if unknown:
            problems.append(f"unknown keys dropped: {', '.join(unknown)}")
        if problems:
            logger.warning("Preference %s: %s", REMINDERS.key, "; ".join(problems))
        return cls(**values)

    def wants(self, category: str) -> bool:
        """Return whether the conference moments of ``category`` are on.

        Args:
            category: One of ``year_moments.CATEGORIES``.

        Raises:
            KeyError: ``category`` is not one of them.
        """
        return {
            "lightning": self.lightning,
            "open_space": self.open_space,
            "keynote": self.keynote,
        }[category]

    def to_stored(self) -> dict[str, Any]:
        """Return the record as ``pycon.reminders`` keeps it: every field, by name."""
        return asdict(self)


def _allowed(value: object, choices: tuple[object, ...]) -> bool:
    """Return whether ``value`` is one of ``choices``, of the same type (True is no 1)."""
    return any(type(value) is type(choice) and value == choice for choice in choices)
