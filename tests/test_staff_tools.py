"""Tests for the staff gating, ``core/staff_tools.py`` (SHELL-06, SHELL-11, AUTH-05; D-54).

The truth table runs over every combination of the three role flags, each also absent,
and compares with architecture §12.4 written out by hand.
"""

from itertools import product

import flet as ft
import pytest

from pycon_us.account_profile import FLAGS
from pycon_us.core.staff_tools import (
    TOOLS,
    ToolKey,
    may_open,
    scans_for_sponsor,
    staff_entries,
)

ABSENT = object()
"""A flag left out of the mapping, as a server may (SHELL-11)."""

LEAD, DOOR, SWAG, COC = ToolKey

TABLE = {
    # (lead_retrieval, door_check, mask_violation): (tools, scans for a sponsor)
    (False, False, False): ((), False),
    (True, False, False): ((LEAD,), False),
    (False, True, False): ((LEAD, DOOR, SWAG), True),
    (True, True, False): ((LEAD, DOOR, SWAG), False),
    (False, False, True): ((COC,), False),
    (True, False, True): ((LEAD, COC), False),
    (False, True, True): ((LEAD, DOOR, SWAG, COC), True),
    (True, True, True): ((LEAD, DOOR, SWAG, COC), False),
}
"""Architecture §12.4 by hand, for every combination of the three flags."""


def flag_cases() -> list[tuple[dict[str, object], tuple[bool, bool, bool]]]:
    """Every flag mapping, each flag True, False or absent, with the booleans it means."""
    names = ("lead_retrieval", "door_check", "mask_violation")
    cases = []
    for values in product((True, False, ABSENT), repeat=3):
        flags = {n: v for n, v in zip(names, values, strict=True) if v is not ABSENT}
        cases.append((flags, tuple(v is True for v in values)))
    return cases


@pytest.mark.parametrize(("flags", "meaning"), flag_cases())
def test_entries_follow_the_gating_table(
    flags: dict[str, object], meaning: tuple[bool, bool, bool]
) -> None:
    """Each of the 27 flag mappings gives §12.4's tools, in order, and sponsor picker."""
    tools, for_sponsor = TABLE[meaning]
    assert tuple(tool.key for tool in staff_entries(flags)) == tools
    assert {key for key in ToolKey if may_open(key, flags)} == set(tools)
    assert scans_for_sponsor(flags) is for_sponsor


def test_only_a_real_true_opens_a_tool() -> None:
    """A truthy non-bool (a string, 1) counts as off, as the stored profile reads it."""
    assert staff_entries({"lead_retrieval": "yes", "door_check": 1}) == ()


def test_the_tools_are_in_o7_order_with_their_routes() -> None:
    """Lead, door, swag, CoC, each routed at ``/more/staff/<key>`` with a real icon."""
    assert [tool.key for tool in TOOLS] == ["lead", "door", "swag", "coc"]
    for tool in TOOLS:
        assert tool.route == f"/more/staff/{tool.key}"
        assert getattr(ft.Icons, tool.icon) is not None
    assert [tool.title for tool in TOOLS] == [
        "Lead scanner",
        "Door check",
        "Swag pickup",
        "CoC incident",
    ]


def test_the_flags_are_the_account_stores() -> None:
    """The gating reads the ``Account`` attributes that the server's flags fill."""
    assert set(FLAGS.values()) >= {"lead_retrieval", "door_check", "mask_violation"}
