"""Which staff tools an account may open: Ionic's gating, pure (D-16, D-54; SHELL-06, SHELL-11).

Every staff entry point (More's "Staff tools" section, the Now card) and every tool
screen's re-check asks ``staff_entries()`` or ``may_open()``, so the gating is one table,
docs/architecture.md §12.4, pinned by an exhaustive truth-table test. The flags are the
``Account`` store's attribute names; an absent flag is False (SHELL-11: the server may
leave one out).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class ToolKey(StrEnum):
    """A staff tool's key: its route's last segment, ``/more/staff/<key>``."""

    LEAD = "lead"
    DOOR = "door"
    SWAG = "swag"
    COC = "coc"


@dataclass(frozen=True)
class StaffTool:
    """A staff tool as its entry points list it.

    Attributes:
        key: The tool's key.
        title: Its name, as ux.md §2.2 gives it.
        icon: The name of its Material icon in ``ft.Icons`` (``core/`` imports no Flet),
            resolved by the screen with ``getattr(ft.Icons, tool.icon)``.
        route: Its route, ``/more/staff/<key>``.
        purpose: What it is for, More's row's second line (ux.md §2.2).
    """

    key: ToolKey
    title: str
    icon: str
    route: str
    purpose: str

    @property
    def now_route(self) -> str:
        """Its route under Now, ``/now/staff/<key>``: the Scan badges card's (D-421).

        Under Now, so Back from the tool returns to Now, as ``/my-schedule/settings``
        returns to My schedule (D-207's pattern, D-401).
        """
        return f"/now/staff/{self.key}"


TOOLS = tuple(
    StaffTool(key, title, icon, f"/more/staff/{key}", purpose)
    for key, title, icon, purpose in (
        (
            ToolKey.LEAD,
            "Lead scanner",
            "QR_CODE_SCANNER",
            "Capture leads at your booth",
        ),
        (
            ToolKey.DOOR,
            "Door check",
            "HOW_TO_REG_OUTLINED",
            "Check in attendees at the door",
        ),
        (ToolKey.SWAG, "Swag pickup", "REDEEM_OUTLINED", "Hand out swag at pickup"),
        (
            ToolKey.COC,
            "CoC incident",
            "REPORT_OUTLINED",
            "Report a Code of Conduct incident",
        ),
    )
)
"""Every staff tool, in O-7's order: lead, door, swag, CoC."""

BUILT_TOOLS = (ToolKey.LEAD, ToolKey.SWAG, ToolKey.COC)
"""The tools whose screen is in the route table: only they get an entry (D-169).

Each tool's PR adds its key once the tool works (#40 door, #41 swag with #769, #42
CoC with #760), so no row is dead; ``staff_entries()`` stays the whole gating table.
CoC records nothing offline, so it is in no ``QUEUED_TOOLS``.
"""

QUEUED_TOOLS = (ToolKey.LEAD,)
"""The tools whose entry says the outbox's counts ("3 pending", D-421).

The outbox is per account, not per tool, and holds only leads until #40 adds door
rows, so the counts go on the Lead scanner's entry alone.
"""


def _on(flags: Mapping[str, object], name: str) -> bool:
    """Whether a role flag is set: only a real True counts, an absent one is False."""
    return flags.get(name) is True


def may_open(tool: ToolKey, flags: Mapping[str, object]) -> bool:
    """Say whether an account may open a staff tool (architecture §12.4).

    Args:
        tool: The tool's key.
        flags: The account's role flags, ``lead_retrieval``, ``door_check`` and
            ``mask_violation``; absent ones are False.

    Returns:
        Lead scanner: ``lead_retrieval or door_check``; Door check and Swag pickup:
        ``door_check``; CoC incident: ``mask_violation``.
    """
    door = _on(flags, "door_check")
    match tool:
        case ToolKey.LEAD:
            return _on(flags, "lead_retrieval") or door
        case ToolKey.DOOR | ToolKey.SWAG:
            return door
        case ToolKey.COC:
            return _on(flags, "mask_violation")


def staff_entries(flags: Mapping[str, object]) -> tuple[StaffTool, ...]:
    """Return the staff tools an account may open, in O-7's order.

    Args:
        flags: The account's role flags, as ``may_open()`` takes them.

    Returns:
        The tools ``may_open()`` allows; empty when the account has no staff role, and
        then neither the Staff section nor the Now card shows.
    """
    return tuple(tool for tool in TOOLS if may_open(tool.key, flags))


def scans_for_sponsor(flags: Mapping[str, object]) -> bool:
    """Say whether the Lead scanner asks which sponsor to scan for (#39's picker).

    Args:
        flags: The account's role flags, as ``may_open()`` takes them.

    Returns:
        ``door_check and not lead_retrieval``: staff who capture leads on a sponsor's
        behalf; a sponsor's own account scans for itself.
    """
    return _on(flags, "door_check") and not _on(flags, "lead_retrieval")


def built_entries(flags: Mapping[str, object]) -> tuple[StaffTool, ...]:
    """Return the entries More and Now show: ``staff_entries()`` with a screen built.

    Args:
        flags: The account's role flags, as ``may_open()`` takes them.

    Returns:
        The allowed tools in ``BUILT_TOOLS``, in O-7's order; empty when none, and
        then neither the Staff tools section nor the Scan badges card shows.
    """
    return tuple(tool for tool in staff_entries(flags) if tool.key in BUILT_TOOLS)


def card_tool(entries: Sequence[StaffTool], last: str) -> StaffTool | None:
    """Return the tool Now's Scan badges card opens (D-421).

    Args:
        entries: The account's entries, ``built_entries()``.
        last: The key of the last tool opened in this process
            (``ViewMemory.staff_tool``), or empty.

    Returns:
        The last tool opened while the account may still open it, else the first
        entry; None without entries.
    """
    for tool in entries:
        if tool.key == last:
            return tool
    return entries[0] if entries else None


def queue_words(pending: int, failed: int) -> str:
    """Return an entry's outbox counts in words, or empty when nothing waits.

    Args:
        pending: The account's rows waiting to be sent (``Staff.pending``).
        failed: Its rows given up on until "Retry failed" (``Staff.failed``).

    Returns:
        E.g. "3 pending", "1 failed" or "3 pending · 1 failed".
    """
    parts = [f"{pending} pending"] if pending else []
    if failed:
        parts.append(f"{failed} failed")
    return " · ".join(parts)


def starts_on_lead(flags: Mapping[str, object], start_screen: str) -> bool:
    """Say whether the app opens on the Lead scanner for an account (D-16, #689).

    Args:
        flags: The account's role flags, as ``may_open()`` takes them.
        start_screen: The Start screen setting (``Prefs.start_screen``): ``auto``,
            ``now`` or ``lead``.

    Returns:
        ``lead_retrieval`` unless the setting is ``now``: a sponsor lands on the
        scanner by default (#310), door-check-only staff and everyone else on Now.
    """
    return _on(flags, "lead_retrieval") and start_screen != "now"
