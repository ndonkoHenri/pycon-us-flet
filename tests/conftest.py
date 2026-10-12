"""Shared test fixtures (docs/testing-and-quality.md §2)."""

import time
from collections.abc import Iterator

import pytest


@pytest.fixture(params=["America/Los_Angeles", "Pacific/Kiritimati"])
def machine_tz(request: pytest.FixtureRequest) -> Iterator[str]:
    """Run the test with the process time zone set to each value in turn (D-43).

    The two zones are 22 hours apart, so code that leans on the machine's zone instead of
    the conference's fails in at least one of them. Its own MonkeyPatch context restores
    only TZ, never another fixture's patches.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("TZ", request.param)
        time.tzset()
        yield request.param
    time.tzset()
