"""Tests for the change log's feed-pair server and its CLI (#460, D-255).

``PairFeed`` (``tests/ui/feeds.py``) serves a pair's old feed at the active year's feed
path, then the new one once swapped; ``tools/feed_pair.py`` builds the pair from the
recorded feed with named edits and serves it. The server runs on this machine's
loopback, as on a device check, and the tests reach it with ``urllib`` (``fetch()``):
httpx's transports refuse every real connection in the tests (``no_network``), which
guards the app's feed refresh, not a test's own server.
"""

import urllib.request
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError

import pytest

from pycon_us.config import YEAR
from tests.feeds import Edit, pair, recorded
from tests.ui.feeds import PairFeed
from tools import feed_pair

ROOT = Path(__file__).resolve().parents[1]
"""The repository's root, where the Maestro flows are."""
OLD, NEW = b'{"side": "old"}', b'{"side": "new"}'
TALK = "123"
"""A panel on 2026-05-15 at 1:45 PM in Grand Ballroom B: the change-log flow's session."""


@pytest.fixture
def feed() -> Iterator[PairFeed]:
    """A ``PairFeed`` of two small bodies, serving on a free port until the test ends."""
    server = PairFeed(OLD, NEW)
    server.serve()
    yield server
    server.close()


@dataclass(frozen=True)
class Answer:
    """What the server answered: its status, body and content type."""

    status: int
    content: bytes
    content_type: str

    @property
    def text(self) -> str:
        """The body as text."""
        return self.content.decode()


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
"""Opens loopback URLs directly, whatever proxy the environment names."""


def fetch(url: str, *, post: bool = False) -> Answer:
    """GET ``url``, or POST an empty body to it, and return the answer, errors included."""
    request = urllib.request.Request(url, data=b"" if post else None)
    try:
        with OPENER.open(request, timeout=5) as response:
            return Answer(
                response.status, response.read(), response.headers["Content-Type"]
            )
    except HTTPError as error:
        return Answer(error.code, error.read(), error.headers["Content-Type"])


def local(feed: PairFeed, path: str, *, post: bool = False) -> Answer:
    """GET (or POST to) ``path`` on ``feed``, as this machine reaches it."""
    return fetch(f"{feed.control_url}{path}", post=post)


def test_it_serves_the_old_feed_then_the_new_one_once_swapped(feed: PairFeed) -> None:
    """The feed path answers with the old side, the new after ``swap()``, the old after ``reset()``."""
    first = local(feed, feed.feed_path)
    feed.swap()
    second = local(feed, feed.feed_path)
    feed.reset()
    third = local(feed, feed.feed_path)

    assert (first.content, second.content, third.content) == (OLD, NEW, OLD)
    assert first.content_type == "application/json"
    assert feed.requests == 3


def test_its_control_paths_swap_and_reset_and_say_the_side(feed: PairFeed) -> None:
    """``POST /swap`` serves the new feed and ``POST /reset`` the old, each saying which."""
    swapped = local(feed, "/swap", post=True)
    assert (swapped.status, swapped.text, feed.swapped) == (200, "new", True)
    assert local(feed, feed.feed_path).content == NEW

    reset = local(feed, "/reset", post=True)
    assert (reset.status, reset.text, feed.swapped) == (200, "old", False)
    assert feed.requests == 1  # control requests are not feed requests


def test_a_hold_keeps_feed_requests_open_until_released(feed: PairFeed) -> None:
    """``POST /hold`` leaves a feed request unanswered; ``POST /release`` answers it."""
    assert local(feed, "/hold", post=True).status == 200
    with ThreadPoolExecutor(max_workers=1) as pool:
        held = pool.submit(local, feed, feed.feed_path)
        with pytest.raises(FutureTimeout):
            held.result(timeout=0.3)
        assert feed.requests == 0

        assert local(feed, "/release", post=True).status == 200
        assert held.result(timeout=5).content == OLD
    assert feed.requests == 1


def test_a_reset_releases_a_hold(feed: PairFeed) -> None:
    """A flow that ends on a reset leaves nothing held for the next run."""
    feed.hold()
    feed.reset()
    assert local(feed, feed.feed_path).content == OLD


def test_it_serves_the_active_years_feed_path_with_any_query(feed: PairFeed) -> None:
    """The feed is at ``/conference-<year>.json``, the path ``laptop_url()`` names."""
    assert feed.feed_path == f"/conference-{YEAR}.json"
    assert feed.url.endswith(f":{feed.port}{feed.feed_path}")
    assert local(feed, f"{feed.feed_path}?v=2").content == OLD


def test_any_other_path_is_not_found(feed: PairFeed) -> None:
    """Another path is a 404, read or posted, and swaps nothing."""
    assert local(feed, "/conference-2025.json").status == 404
    assert local(feed, "/swap/now", post=True).status == 404
    assert local(feed, feed.feed_path, post=True).status == 404
    assert not feed.swapped
    assert feed.requests == 0


# ------------------------------------------------------------------ the CLI


def edits(*argv: str) -> list[Edit]:
    """The edits the CLI makes of ``argv``."""
    return feed_pair.edits_of(feed_pair.parser().parse_args(argv))


def test_the_cli_finds_the_change_its_move_makes() -> None:
    """``--move`` moves the slot: the app's diff finds one room change of it."""
    old, new = pair(YEAR, *edits("--move", TALK, "Room 103ABC"))

    assert old == recorded(YEAR)
    (line,) = feed_pair.expected(old, new)
    assert line.startswith("  room of 123: Panel: Fostering better collaboration")


def test_the_flows_pair_moves_a_saved_and_an_unsaved_talk() -> None:
    """The change-log flow's command moves two talks, so both sections show.

    The flow saves 123 and not 142: its move goes under "Affects My schedule", above
    "All changes" and 142's move, which is how the flow checks the order (D-255).
    """
    argv = ("--move", TALK, "Room 103ABC", "--move", "142", "Room 101B")
    old, new = pair(YEAR, *edits(*argv))

    lines = feed_pair.expected(old, new)
    assert [line.split(":")[0].strip() for line in lines] == [
        "room of 123",
        "room of 142",
    ]
    flow = (ROOT / "maestro" / "journeys" / "change_log.yaml").read_text()
    assert 'tools.feed_pair --move 123 "Room 103ABC" --move 142 "Room 101B"' in flow


def test_the_cli_makes_each_named_edit_once_per_flag() -> None:
    """Every flag repeats, and each one makes its own edit: five kinds of change."""
    argv = [
        *("--move", TALK, "Room 103ABC"),
        *("--retime", "142", "2026-05-16T11:00:00-07:00", "2026-05-16T11:30:00-07:00"),
        *("--rename", "142", "A new title"),
        *("--add", "99999", "142", "An added talk"),
        *("--remove", "121"),
    ]
    old, new = pair(YEAR, *edits(*argv))

    kinds = [line.split(" of ")[0].strip() for line in feed_pair.expected(old, new)]
    assert sorted(kinds) == ["added", "removed", "room", "time", "title"]


def test_the_report_gives_each_devices_url_and_the_swap() -> None:
    """The report names the feed URL on each device, the swap command and the flow."""
    lines = "\n".join(feed_pair.report(["  room of 123: A talk"], 8460))

    assert f"http://10.0.2.2:8460/conference-{YEAR}.json" in lines
    assert f"http://127.0.0.1:8460/conference-{YEAR}.json" in lines
    assert "curl -X POST http://127.0.0.1:8460/swap" in lines
    assert "-e CONTROL_URL=http://127.0.0.1:8460" in lines
    assert "maestro/journeys/change_log.yaml" in lines


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--move", "x", "Room 103ABC"],
        ["--move", "999999", "Room 103ABC"],
        ["--remove", "999999"],
    ],
    ids=["no edit", "not a number", "no such slot", "no such slot to remove"],
)
def test_the_cli_refuses_edits_it_cannot_make(argv: list[str]) -> None:
    """No edit, a key that is not a number, or a slot the feed lacks: a usage error."""
    with pytest.raises(SystemExit) as raised:
        feed_pair.main(argv)
    assert raised.value.code == 2


def test_the_cli_serves_nothing_when_the_edits_change_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A move to the slot's own room finds no change: exit 1, and nothing served."""
    assert feed_pair.main(["--move", TALK, "Grand Ballroom B"]) == 1
    assert "finds no change" in capsys.readouterr().err


def test_the_cli_serves_until_interrupted_then_frees_its_port(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """It serves the pair, prints the report, and on Ctrl-C closes and exits 0."""
    served: list[bytes] = []

    def interrupted() -> None:
        """Fetch the served feed as the app would, from the printed URL, then Ctrl-C."""
        url = capsys.readouterr().out.split("iOS simulator:")[1].split()[0]
        served.append(fetch(url).content)
        raise KeyboardInterrupt

    monkeypatch.setattr(feed_pair, "wait", interrupted)

    assert feed_pair.main(["--move", TALK, "Room 103ABC", "--port", "0"]) == 0
    assert served == [recorded(YEAR)]
