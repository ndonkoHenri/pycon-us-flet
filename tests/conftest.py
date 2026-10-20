"""Shared test fixtures and the hypothesis ci profile (docs/testing-and-quality.md §2)."""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from hypothesis import settings

SNAPSHOTS = Path(__file__).parent / "fixtures" / "snapshots"

# CI runs `pytest --hypothesis-profile=ci` (docs/testing-and-quality.md §3.1, §12).
# Hypothesis's built-in `ci` profile is what a shared runner needs: the same examples on
# every run (so a red build reproduces), no deadline and no `too_slow` health check (runners
# are slow by fits), and the `@reproduce_failure` blob printed. We extend it, inheriting all
# of that, and only raise it to 200 examples per property.
settings.register_profile("ci", settings.get_profile("ci"), max_examples=200)

# Local runs get the `dev` profile: Hypothesis's defaults without the 200 ms deadline per
# example, which a Mac busy with builds and emulators overran in a correctness test
# (`test_html_md.py`, 268 ms). Speed is measured on devices (testing-and-quality.md §8),
# not by a property's deadline. `--hypothesis-profile=ci` still overrides it.
settings.register_profile("dev", settings.get_profile("default"), deadline=None)
settings.load_profile("dev")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add ``--snapshot-update``, which rewrites snapshots instead of comparing."""
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        help="Rewrite snapshot files instead of comparing with them.",
    )


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


@pytest.fixture
def snapshot(request: pytest.FixtureRequest) -> Callable[[str, object], None]:
    """Return check(name, data): compare data with a committed JSON snapshot (D-77).

    With ``--snapshot-update`` it writes ``tests/fixtures/snapshots/<name>.json`` instead;
    review the diff before committing it.
    """
    update = request.config.getoption("--snapshot-update")

    def check(name: str, data: object) -> None:
        path = SNAPSHOTS / f"{name}.json"
        text = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        if update:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return
        assert path.exists(), f"No snapshot {path.name}; run with --snapshot-update"
        assert path.read_text(encoding="utf-8") == text, (
            f"{name} changed; review the diff, then run with --snapshot-update"
        )

    return check
