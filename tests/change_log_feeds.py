"""The ``ChangeLog`` store's fixtures and helpers, for its two test modules (#623).

``test_change_log.py`` (over the cache, and feed URLs) and
``test_change_log_snapshot.py`` (over the bundled snapshot, and ``recent()``) run a
real ``Conference`` refresh over an ``httpx.MockTransport``; the log and the cache live
in a temporary directory, and SharedPreferences is the in-memory fake. A module takes
the fixtures by assigning them to its own names, as ``docs/testing-and-quality.md``
§3.1 says; ``frozen_clock`` is autouse in each module that assigns it.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from pycon_us import clock
from pycon_us.change_log import ChangeLog
from pycon_us.config import YearData, load_year
from pycon_us.favorites import Favorites
from pycon_us.services import changes_file
from pycon_us.services.pref_keys import fetched
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests.fakes import MemoryPrefs
from tests.feeds import Edit

NOW = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)
TALK = 142  # a 2026 talk, in the recorded feed and in the snapshot
OTHER = 51  # another talk, never saved here
TEST_URL = "https://example.test/conference.json"


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    """Freeze ``clock.now()`` at ``NOW`` for the test, then return to real time."""
    clock.set_test_now(NOW)
    yield
    clock.set_test_now(None)


@pytest.fixture(scope="module")
def year() -> YearData:
    """The 2026 year data, loaded once for the module."""
    return load_year(2026)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """A 2026 ``Storage`` in ``tmp_path``, over in-memory SharedPreferences."""
    return Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)


def serving(body: bytes) -> httpx.MockTransport:
    """A transport that answers any feed URL with ``body``."""
    return httpx.MockTransport(lambda request: httpx.Response(200, content=body))


def snapshot_with(year: YearData, *edits: Edit) -> bytes:
    """The bundled 2026 snapshot with ``edits`` applied to a fresh copy of its JSON."""
    doc = json.loads(year.read_snapshot().raw)
    for edit in edits:
        edit(doc)
    return json.dumps(doc).encode()


async def started(
    storage: Storage, year: YearData, saved: frozenset[str] = frozenset()
) -> tuple[Conference, ChangeLog]:
    """Return the stores after a start, as ``bootstrap()`` loads them, with ``saved``."""
    favorites = Favorites(ids=saved)
    log = ChangeLog(_favorites=favorites)
    await log.load(storage, year.conference.zone)
    conference = Conference(_change_log=log)
    await conference.load_local(storage, year)
    return conference, log


def log_file(storage: Storage) -> Path:
    """The year's change log file."""
    return changes_file.changes_path(storage)


async def marker(storage: Storage) -> bool:
    """Return the stored ``pycon.2026.fetched``."""
    return await storage.get(fetched(2026))
