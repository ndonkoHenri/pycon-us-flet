"""Tests for the semantics helpers (``ui/semantics.py``; decisions §M, D-200)."""

from pycon_us.ui.semantics import semantics_key

TALK = "142"
"""A talk: a numeric id."""

COFFEE = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
"""A synthetic break id, with spaces and colons (D-42)."""


def test_a_semantics_key_is_safe_in_a_selector() -> None:
    """Decisions §M: a break's id has spaces and colons; its key has neither."""
    assert semantics_key(COFFEE) == "break-expo-hall-ab-2026-05-15t08-00-00-07-00"
    assert semantics_key("poster-detail-60") == "poster-detail-60"
    assert semantics_key(TALK) == TALK
