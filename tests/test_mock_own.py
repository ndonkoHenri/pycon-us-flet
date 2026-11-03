"""Tests for ``tools/mock_api/own.py``, with the real server on a real port (#985)."""

import socket
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.mock_api import own


@pytest.fixture
def state(tmp_path: Path) -> Iterator[Path]:
    """Return a folder for one mock's pid and log, and stop that mock afterwards."""
    yield tmp_path
    own.stop(tmp_path)


def _gone(port: int) -> bool:
    """Wait for ``port`` to close and return whether it did."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not own._answers(port):
            return True
        time.sleep(0.1)
    return False


def test_port_is_stable_per_checkout() -> None:
    """One path always gets one port in the range, and another path usually another."""
    first = own.preferred_port(Path("/a/one"))
    assert first == own.preferred_port(Path("/a/one"))
    assert first != own.preferred_port(Path("/a/two"))
    assert own.FIRST_PORT <= first < own.FIRST_PORT + own.PORTS


def test_taken_port_moves_to_the_next(monkeypatch: pytest.MonkeyPatch) -> None:
    """A port another process holds is skipped, whoever holds it."""
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        taken = holder.getsockname()[1]
        monkeypatch.setattr(own, "FIRST_PORT", taken)
        monkeypatch.setattr(own, "preferred_port", lambda root: taken)
        assert own.free_port(Path("/any")) == taken + 1


def test_urls_differ_by_platform() -> None:
    """An emulator reaches this machine at 10.0.2.2, a simulator at localhost."""
    assert own.url(8123, "android") == "http://10.0.2.2:8123"
    assert own.url(8123, "ios") == "http://localhost:8123"


def test_second_start_reuses_the_mock(state: Path) -> None:
    """A repeat start returns the running mock's port, so its state stays."""
    port = own.start(state, [])
    pid = own.running(state)
    assert own.start(state, []) == port
    assert own.running(state) == pid


def test_stop_ends_it_and_says_when_nothing_ran(state: Path) -> None:
    """Stop closes the port; a second stop says nothing was running."""
    port = own.start(state, [])
    assert own.stop(state) is True
    assert _gone(port)
    assert own.stop(state) is False
    assert own.running(state) is None


def test_it_serves_the_mock_and_passes_options(state: Path) -> None:
    """The process answers as the mock, and its banner shows the option it was given."""
    port = own.start(state, ["--skew", "900"])
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/nothing-here", timeout=5)
    assert "900" in (state / "log").read_text()


def test_stale_pid_file_counts_as_gone(state: Path) -> None:
    """A pid file whose process has ended, or that can't be read, isn't a running mock."""
    (state / "pid").write_text("999999 8123\n")
    assert own.running(state) is None
    (state / "pid").write_text("garbage\n")
    assert own.running(state) is None


def test_url_needs_a_running_mock(
    state: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``url`` before ``start`` says what to do rather than printing a dead URL."""
    with pytest.raises(SystemExit, match="start it first"):
        own.main(["url", "ios"], state)
    assert capsys.readouterr().out == ""
