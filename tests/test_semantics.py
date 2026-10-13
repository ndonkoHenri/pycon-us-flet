"""Tests for the semantics helpers (``ui/semantics.py``; decisions §M, D-200)."""

from typing import cast

import flet as ft

from pycon_us.ui.semantics import named, semantics_key

TALK = "142"
"""A talk: a numeric id."""

COFFEE = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
"""A synthetic break id, with spaces and colons (D-42)."""


def test_a_semantics_key_is_safe_in_a_selector() -> None:
    """Decisions §M: a break's id has spaces and colons; its key has neither."""
    assert semantics_key(COFFEE) == "break-expo-hall-ab-2026-05-15t08-00-00-07-00"
    assert semantics_key("poster-detail-60") == "poster-detail-60"
    assert semantics_key(TALK) == TALK


def test_a_named_disabled_button_s_node_says_it_is_disabled() -> None:
    """F42: Flutter's ``enabled`` comes from the ``Semantics``' own ``disabled``."""
    button = ft.IconButton(ft.Icons.SHARE_OUTLINED, disabled=True)
    merged = named("session.share", button, disabled=True)
    assert isinstance(merged, ft.MergeSemantics)
    node = merged.content
    assert isinstance(node, ft.Semantics)
    assert (node.identifier, node.disabled, node.content) == (
        "session.share",
        True,
        button,
    )
    enabled = named("session.share", ft.IconButton(ft.Icons.SHARE_OUTLINED))
    assert not cast(ft.Semantics, cast(ft.MergeSemantics, enabled).content).disabled
