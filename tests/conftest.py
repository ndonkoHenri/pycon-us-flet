"""Shared test fixtures and the hypothesis ci profile (docs/testing-and-quality.md §2)."""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from hypothesis import settings

from pycon_us.ui import focus_back

SNAPSHOTS = Path(__file__).parent / "fixtures" / "snapshots"

# CI runs `pytest --hypothesis-profile=ci` (docs/testing-and-quality.md §3.1, §12).
# Hypothesis's built-in `ci` profile is what a shared runner needs: the same examples on
# every run (so a red build reproduces), no deadline and no `too_slow` health check (runners
# are slow by fits), and the `@reproduce_failure` blob printed. We extend it, inheriting all
# of that, and only raise it to 200 examples per property.
settings.register_profile("ci", settings.get_profile("ci"), max_examples=200)

# Local runs get the `dev` profile: Hypothesis's defaults without the 200 ms deadline per
# example, which a Mac busy with builds and emulators overran in a correctness test
# (now in `test_html_md_text.py`, 268 ms). Speed is measured on devices
# (testing-and-quality.md §8), not by a property's deadline. `--hypothesis-profile=ci`
# still overrides it.
settings.register_profile("dev", settings.get_profile("default"), deadline=None)
settings.load_profile("dev")


def pytest_configure(config: pytest.Config) -> None:
    """Register the `loopback` marker, `no_network`'s one opt-out."""
    config.addinivalue_line(
        "markers",
        "loopback: let httpx reach 127.0.0.1 only, for a server the test runs itself",
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add `--snapshot-update`, which rewrites snapshots instead of comparing."""
    parser.addoption(
        "--snapshot-update",
        action="store_true",
        help="Rewrite snapshot files instead of comparing with them.",
    )


@pytest.fixture(autouse=True)
def quick_focus_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a tapped link or Share stop waiting for a departure at once (D-372).

    No test leaves the app unless it says so (`Presence.leave()`), so a handler that
    opened a link from a button would otherwise wait `LEAVE_WITHIN` (3 s) for nothing.
    """
    monkeypatch.setattr(focus_back, "LEAVE_WITHIN", 0.01)


@pytest.fixture(autouse=True)
def no_network(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[list[str]]:
    """Refuse every real HTTP connection, and fail the test that tried one (#539).

    Tests never touch the network: a request reaches a server only through a test's
    `httpx.MockTransport`. httpx's own transports, which a client without one uses
    (the app's feed refresh), raise `ConnectError` instead of connecting, so the code
    under test takes its offline path, and the test then fails at teardown naming the
    URLs, even when the code swallowed the error. A test marked `loopback` may still
    reach `127.0.0.1`, where it runs a server of its own (the mock's, #666), and
    nothing else. Yields the refused URLs.
    """
    refused: list[str] = []
    loopback = request.node.get_closest_marker("loopback") is not None
    connect = httpx.HTTPTransport.handle_request
    connect_async = httpx.AsyncHTTPTransport.handle_async_request

    def allowed(sent: httpx.Request) -> bool:
        """Whether this request may connect: only a `loopback` test's, to 127.0.0.1."""
        if loopback and sent.url.host == "127.0.0.1":
            return True
        refused.append(str(sent.url))
        return False

    def refuse(
        transport: httpx.HTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        if allowed(request):
            return connect(transport, request)
        raise httpx.ConnectError("tests never open a real connection", request=request)

    async def refuse_async(
        transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        if allowed(request):
            return await connect_async(transport, request)
        raise httpx.ConnectError("tests never open a real connection", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async)
    yield refused
    if refused:
        pytest.fail(
            f"The test tried a real connection to {refused}; use a fake transport"
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

    With `--snapshot-update` it writes `tests/fixtures/snapshots/<name>.json` instead;
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
