"""Tests for what the theme flow finds on Settings, against the app's own (#512).

``maestro/journeys/theme_relaunch.yaml`` and its subflows find More's Settings row,
Appearance's radio rows and the High contrast row by identifier, and match the switch
row's label word for word. Those are written into the YAML, so a renamed identifier or
reworded label would fail only on a device. These checks fail here instead.
"""

import re
from pathlib import Path

import flet as ft

from pycon_us.screens.more import SETTINGS
from pycon_us.screens.settings import (
    APPEARANCE_LABELS,
    FOLLOWS_DEVICE,
    HIGH_CONTRAST,
    appearance,
    high_contrast,
)

MAESTRO = Path(__file__).resolve().parent.parent / "maestro"
FLOW = MAESTRO / "journeys" / "theme_relaunch.yaml"
OPEN = MAESTRO / "subflows" / "theme_settings.yaml"
STATE = MAESTRO / "subflows" / "theme_state.yaml"


def no_op(_: ft.Event) -> None:
    """Stand in for a row's change handler, which these checks never call."""


def identifier(row: ft.Control) -> str:
    """Return the identifier that ``named()`` put on ``row``.

    Args:
        row: A ``MergeSemantics`` around the ``Semantics`` that carries it.
    """
    assert isinstance(row, ft.MergeSemantics)
    assert isinstance(row.content, ft.Semantics)
    return str(row.content.identifier)


def flow_texts() -> str:
    """Return the flow's and its two subflows' YAML, joined."""
    return "\n".join(path.read_text(encoding="utf-8") for path in (FLOW, OPEN, STATE))


def test_the_flow_opens_settings_by_more_s_row_identifier() -> None:
    """D-286: More's row is ``more.settings``, which the subflow taps."""
    assert SETTINGS.identifier == "more.settings"
    assert "id: more.settings\n" in OPEN.read_text(encoding="utf-8")


def test_the_appearance_rows_the_flow_names_are_the_app_s() -> None:
    """D-286: ``settings.appearance.<value>``, with the values the flow passes.

    The flow chooses Dark and System and names them in ``SELECTED`` and ``OTHER``.
    """
    group = appearance("system", no_op)
    assert isinstance(group, ft.RadioGroup)
    column = group.content
    assert isinstance(column, ft.Column)
    ids = {identifier(row) for row in column.controls}
    assert ids == {f"settings.appearance.{value}" for value in APPEARANCE_LABELS}
    text = flow_texts()
    for value in ("system", "dark"):
        assert f"id: settings.appearance.{value}\n" in text
    named = set(re.findall(r"(?:SELECTED|OTHER): (\w+)", text))
    assert named == {"system", "dark"}
    assert named <= set(APPEARANCE_LABELS)


def test_the_switch_row_s_identifier_is_the_app_s() -> None:
    """D-286: the High contrast row is ``settings.high_contrast``."""
    row = high_contrast(False, follows_device=True, on_change=no_op)
    assert identifier(row) == "settings.high_contrast"
    assert "id: settings.high_contrast\n" in flow_texts()


def test_the_switch_row_s_labels_are_the_app_s_words() -> None:
    """D-286: "High contrast", and its subtitle while it follows the device.

    The flow's ``HC_LABEL`` is a whole-label regular expression; the YAML string escapes
    its whitespace class's backslash, so the file holds two.
    """
    labels = set(re.findall(r'HC_LABEL: "([^"]+)"', FLOW.read_text(encoding="utf-8")))
    assert labels == {HIGH_CONTRAST, f"{HIGH_CONTRAST}\\\\s+{FOLLOWS_DEVICE}"}
