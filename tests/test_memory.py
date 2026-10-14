"""Tests for ``ViewMemory``, the process memory of where the user left the app (D-143)."""

from datetime import date

from pycon_us.memory import ViewMemory


def test_view_memory_reset_forgets_every_place() -> None:
    memory = ViewMemory(
        last_location="/more/developer",
        search_base="/schedule",
        jumped_on=date(2026, 5, 15),
        search_query="typing",
        search_scope="speakers",
    )
    offsets = memory.schedule_offsets
    offsets[date(2026, 5, 15)] = 1200.0
    memory.reset()
    assert memory == ViewMemory()
    assert memory.schedule_offsets is not offsets  # a fresh dict, not the old one
