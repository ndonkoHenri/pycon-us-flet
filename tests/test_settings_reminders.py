"""Tests for Settings' Reminders section in D-60's interim (#429, NOTIF-01).

``reminders_section()`` is a plain function of the platform and the build's
capabilities, so it runs without a page. How the section looks and reads is checked on
devices (the PR).
"""

import flet as ft
import pytest

from pycon_us.screens import settings_reminders
from pycon_us.screens.settings import RADIO_WIDTH
from pycon_us.screens.settings_reminders import (
    NOT_AVAILABLE,
    WITH_ALARM,
    reminders_section,
)


def parts_of(
    section: ft.Control | None,
) -> tuple[ft.Semantics, ft.Semantics, ft.ListTile]:
    """Return the section's heading, its row's identifier node and the row's tile."""
    assert isinstance(section, ft.Column)
    heading, row = section.controls
    assert isinstance(heading, ft.Semantics)
    assert isinstance(row, ft.MergeSemantics)  # one node, read as its words (D-214)
    node = row.content
    assert isinstance(node, ft.Semantics)
    assert isinstance(node.content, ft.ListTile)
    return heading, node, node.content


def test_the_interim_is_a_level_2_reminders_heading_over_one_named_row() -> None:
    """The section is a level-2 "Reminders" heading and one row, ``settings.reminders.interim``."""
    heading, node, _ = parts_of(
        reminders_section(ft.PagePlatform.IOS, slot=RADIO_WIDTH)
    )
    assert heading.header and heading.heading_level == 2  # a section (D-211)
    assert isinstance(heading.content, ft.Container)
    assert isinstance(heading.content.content, ft.Text)
    assert heading.content.content.value == "Reminders"
    assert node.identifier == "settings.reminders.interim"


def test_the_interim_row_has_no_control_that_does_nothing() -> None:
    """No switch, no button, no tap: there is nothing to change in this build (D-60)."""
    _, _, tile = parts_of(reminders_section(ft.PagePlatform.ANDROID, slot=RADIO_WIDTH))
    assert tile.trailing is None
    assert tile.on_click is None and not tile.toggle_inputs
    slot = tile.leading
    assert isinstance(slot, ft.Container)
    assert slot.width == RADIO_WIDTH  # its words start where Appearance's titles do
    assert isinstance(slot.content, ft.Icon)
    assert slot.content.icon == ft.Icons.NOTIFICATIONS_OFF_OUTLINED
    assert slot.content.semantics_label is None  # decorative: the words say it


@pytest.mark.parametrize(
    ("platform", "text"),
    [
        (ft.PagePlatform.IOS, WITH_ALARM),
        (ft.PagePlatform.ANDROID, NOT_AVAILABLE),
        (None, NOT_AVAILABLE),
    ],
)
def test_only_ios_promises_the_calendar_alarm(
    platform: ft.PagePlatform | None, text: str
) -> None:
    """On iOS the sentence mentions the export's alarm; Android's import drops it (D-272)."""
    _, _, tile = parts_of(reminders_section(platform, slot=RADIO_WIDTH))
    assert tile.title == text


def test_the_sentences_say_what_ux_9_says() -> None:
    """The copy is ux.md §6.9's, word for word, on each platform."""
    assert NOT_AVAILABLE == (
        "Reminders aren't available in this build. Your next session appears on Now."
    )
    assert WITH_ALARM == (
        "Reminders aren't available in this build. Your next session appears on Now, "
        "and calendar exports include an alarm."
    )


def test_a_build_that_bundles_e3_keeps_the_interim_until_reminders_are_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E3 bundled but nothing scheduling yet (#447): the interim still says so (#677)."""
    monkeypatch.setattr(settings_reminders.capabilities, "REMINDERS", True)
    _, _, tile = parts_of(reminders_section(ft.PagePlatform.ANDROID, slot=RADIO_WIDTH))
    assert tile.title == NOT_AVAILABLE


def test_a_build_with_reminders_gets_no_interim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once reminders are live there is no interim section: its live controls are P2-89's."""
    monkeypatch.setattr(settings_reminders.capabilities, "REMINDERS_LIVE", True)
    assert reminders_section(ft.PagePlatform.IOS, slot=RADIO_WIDTH) is None
