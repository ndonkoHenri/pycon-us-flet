"""Shared test fixtures (docs/testing-and-quality.md §2)."""

import time

import pytest


@pytest.fixture(params=["America/Los_Angeles", "Pacific/Kiritimati"])
def machine_tz(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Run the test with the process time zone set to each value in turn (D-43).

    The two zones are 22 hours apart, so code that leans on the machine's zone instead of
    the conference's fails in at least one of them.
    """
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    yield request.param
    monkeypatch.undo()
    time.tzset()
