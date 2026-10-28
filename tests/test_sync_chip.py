"""The staff sync chip: its words and icon for each state of the outbox (#694)."""

from typing import Any

import flet as ft
import pytest

from pycon_us.staff import Staff
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui.sync_chip import IDENTIFIER, SyncChip, chip_icon, chip_words


@pytest.mark.parametrize(
    ("state", "words"),
    [
        ({}, "All synced"),
        ({"syncing": True}, "Syncing…"),
        ({"pending": 3}, "3 pending"),
        ({"pending": 3, "offline": True}, "Offline · 3 queued"),
        ({"pending": 3, "syncing": True}, "Syncing · 3 pending"),
        ({"failed": 1}, "1 failed"),
        ({"pending": 3, "failed": 1}, "3 pending · 1 failed"),
        ({"pending": 2, "failed": 1, "offline": True}, "Offline · 2 queued · 1 failed"),
        ({"synced": 40}, "All synced"),
    ],
)
def test_the_chip_says_each_state_in_words(state: dict[str, Any], words: str) -> None:
    """Counts, a pass under way and an offline last pass are words, not colour alone."""
    assert chip_words(Staff(**state)) == words


def test_the_icon_follows_the_state() -> None:
    """A ring while syncing, then failed, offline, pending and done, in that order."""
    assert isinstance(
        chip_icon(Staff(pending=1, syncing=True), LIGHT_TOKENS), ft.ProgressRing
    )
    icons = [
        chip_icon(state, LIGHT_TOKENS)
        for state in (
            Staff(pending=1, failed=1, offline=True),
            Staff(pending=1, offline=True),
            Staff(pending=1),
            Staff(),
        )
    ]
    assert [icon.icon for icon in icons if isinstance(icon, ft.Icon)] == [
        ft.Icons.ERROR_OUTLINE,
        ft.Icons.CLOUD_OFF_OUTLINED,
        ft.Icons.CLOUD_UPLOAD_OUTLINED,
        ft.Icons.CLOUD_DONE_OUTLINED,
    ]
    done = icons[-1]
    assert isinstance(done, ft.Icon) and done.color == LIGHT_TOKENS.success


def test_a_chip_that_opens_the_sheet_is_one_node_with_its_identifier() -> None:
    """With an action, the chip is merged with ``staff.sync_chip`` and taps through."""
    taps: list[int] = []
    control = SyncChip(
        Staff(pending=2), tokens=LIGHT_TOKENS, on_click=lambda: taps.append(1)
    )
    assert isinstance(control, ft.MergeSemantics)
    named = control.content
    assert isinstance(named, ft.Semantics) and named.identifier == IDENTIFIER
    chip = named.content
    assert isinstance(chip, ft.Chip) and isinstance(chip.label, ft.Text)
    assert chip.label.value == "2 pending"
    assert chip.on_click is not None
    chip.on_click()  # pyright: ignore[reportCallIssue]
    assert taps == [1]


def test_a_chip_inside_a_row_is_its_words_alone() -> None:
    """Without an action it says its words and nothing else: no disabled chip to read."""
    control = SyncChip(Staff(failed=1), tokens=LIGHT_TOKENS)
    assert isinstance(control, ft.Semantics)
    assert (control.label, control.exclude_semantics) == ("1 failed", True)
    assert isinstance(control.content, ft.Chip) and control.content.on_click is None
