"""Which staff tools an account may open: Ionic's gating, pure (D-16, D-54; SHELL-06, SHELL-11).

Every staff entry point (More's "Staff tools" section, the Now card) and every tool
screen's re-check asks ``staff_entries()`` or ``may_open()``, so the gating is one table,
docs/architecture.md §12.4, pinned by an exhaustive truth-table test. The flags are the
``Account`` store's attribute names; an absent flag is False (SHELL-11: the server may
leave one out).
"""

from collections.abc import Mapping
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
    """

    key: ToolKey
    title: str
    icon: str
    route: str


TOOLS = tuple(
    StaffTool(key, title, icon, f"/more/staff/{key}")
    for key, title, icon in (
        (ToolKey.LEAD, "Lead scanner", "QR_CODE_SCANNER"),
        (ToolKey.DOOR, "Door check", "HOW_TO_REG_OUTLINED"),
        (ToolKey.SWAG, "Swag pickup", "REDEEM_OUTLINED"),
        (ToolKey.COC, "CoC incident", "REPORT_OUTLINED"),
    )
)
"""Every staff tool, in O-7's order: lead, door, swag, CoC."""


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
