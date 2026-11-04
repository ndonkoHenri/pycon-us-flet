"""The storage service over memory, for its two test modules (#623).

`test_storage.py` (the key table, preferences and clearing them) and
`test_storage_cache.py` (the data directory and the feed cache) run the 2026 storage
service over the in-memory SharedPreferences from `tests/fakes.py`, with its files in
a temporary directory. A module takes the fixtures by assigning them to its own names,
as `docs/testing-and-quality.md` §3.1 says.
"""

from pathlib import Path

import pytest

from pycon_us.services.storage import Storage
from tests.fakes import MemoryPrefs


@pytest.fixture
def prefs() -> MemoryPrefs:
    """An empty in-memory SharedPreferences."""
    return MemoryPrefs()


@pytest.fixture
def store(prefs: MemoryPrefs, tmp_path: Path) -> Storage:
    """The 2026 storage service over `prefs`, with its files in `tmp_path`."""
    return Storage(prefs=prefs, directory=tmp_path, year=2026)
