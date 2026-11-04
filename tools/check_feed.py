"""Check the live public feed with our parser and the feed invariants (D-77, D-84; DEV-08).

The weekly `.github/workflows/feed-check.yml` runs it. By hand, from the repo root:

    uv run python -m tools.check_feed              # config.YEAR
    uv run python -m tools.check_feed 2025 2026    # any years with a data/<year>/ folder

For each year it fetches the `feed_url` of `data/<year>/conference.toml`, processes it
with `feed.process`, the app's own parser, and runs every invariant of
`tools/feed_invariants.py`, the ones the tests run on the recorded feeds. A year fails
when its feed cannot be fetched (a 404 included), does not parse, or breaks an invariant;
a record the parser skips breaks "no session is lost". Keys the recorded feeds
(`tests/fixtures/feeds`) do not have are printed but never fail: the parser ignores them
(testing-and-quality.md §12).

Then it says whether next year's feed is published, at this year's URL with the next year
in it (D-05's pattern). That line never fails the check: a 404, or a redirect (to this
year's feed, say), means "not yet".

It exits with 0 when every checked year passes and 1 otherwise; a failed scheduled run
emails the owner, which is the alert (docs/development.md §7.3).
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from pycon_us.config import DATA_DIR, YEAR, YearDataError, load_year
from pycon_us.core.feed import FeedError
from tools.feed_invariants import INVARIANTS, ProcessedFeed, processed_feed

TIMEOUT = 30.0
"""Seconds to wait for a feed; the 2026 feed is about 800 KB."""

SHOWN_PROBLEMS = 10
"""How many problems of one invariant the report lists; the rest are counted."""

RECORDED_FEEDS = Path(__file__).parents[1] / "tests" / "fixtures" / "feeds"
"""The recorded feeds the parser was written against; their keys are the known ones."""


def check_year(
    year: int,
    data_dir: Path = DATA_DIR,
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[bool, list[str]]:
    """Fetch a year's public feed, process it and run the invariants.

    Args:
        year: The conference year; its feed URL comes from its `conference.toml`.
        data_dir: The folder that holds the year folders.
        transport: The HTTP transport; tests pass an `httpx.MockTransport`.

    Returns:
        Whether the feed passed, and the report's lines.
    """
    try:
        year_data = load_year(year, data_dir)
    except YearDataError as error:
        return False, [f"{year}: FAILED, no usable year data: {error}"]
    url = year_data.conference.feed_url
    lines = [f"{year}: {url}"]
    try:
        response = _get(url, transport)
        response.raise_for_status()
        feed = processed_feed(response.content, year_data)
    except httpx.HTTPStatusError as error:
        return False, [*lines, f"  FAILED, HTTP {error.response.status_code}"]
    except httpx.HTTPError as error:
        return False, [*lines, f"  FAILED, could not fetch it: {error}"]
    except FeedError as error:
        return False, [*lines, f"  FAILED, it does not parse: {error}"]

    data = feed.data
    lines.append(
        f"  {len(feed.raw):,} bytes: {len(data.sessions)} sessions, "
        f"{len(data.speakers)} speakers, {len(data.days)} days, "
        f"{len(data.skipped)} skipped records"
    )
    broken = 0
    for invariant in INVARIANTS:
        if problems := _problems(invariant, feed):
            broken += 1
            lines.append(f"  FAILED: {invariant.__name__.replace('_', ' ')}")
            lines += [f"    {problem}" for problem in problems[:SHOWN_PROBLEMS]]
            if len(problems) > SHOWN_PROBLEMS:
                lines.append(f"    ... and {len(problems) - SHOWN_PROBLEMS} more")
    held = len(INVARIANTS) - broken
    lines.append(f"  {held} of {len(INVARIANTS)} invariants hold")
    new = new_keys(feed.document, _recorded_documents())
    lines.append(
        f"  keys the recorded feeds lack (ignored): {'; '.join(new)}"
        if new
        else "  no key the recorded feeds lack"
    )
    lines.append("  OK" if not broken else "  FAILED")
    return not broken, lines


def next_year_status(
    year: int = YEAR,
    data_dir: Path = DATA_DIR,
    *,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Say whether the feed of the year after `year` is published; never fails.

    Its URL is `year`'s feed URL with the next year in its path (D-05's pattern).

    Returns:
        One line for the report.
    """
    following = year + 1
    try:
        current_url = load_year(year, data_dir).conference.feed_url
    except YearDataError as error:
        return f"{following}: no {year} feed URL to guess its URL from: {error}"
    url = current_url.replace(f"/{year}/", f"/{following}/")
    if url == current_url:
        return f"{following}: no /{year}/ in {current_url} to guess its feed URL from"
    try:
        response = _get(url, transport)
    except httpx.HTTPError as error:
        return f"{following}: could not fetch {url}: {error}"
    if response.history:  # an unpublished year may redirect to this year's feed
        return (
            f"{following}: {url} redirects to {response.url} "
            f"(HTTP {response.history[0].status_code}); not published yet"
        )
    if response.status_code == httpx.codes.NOT_FOUND:
        return f"{following}: not published yet (HTTP 404 at {url})"
    if response.status_code != httpx.codes.OK:
        return f"{following}: HTTP {response.status_code} at {url}"
    try:
        slots = len(json.loads(response.content)["schedule"])
    except (ValueError, KeyError, TypeError, RecursionError) as error:
        return f"{following}: HTTP 200 at {url}, but not a feed: {error!r}"
    return (
        f"{following}: PUBLISHED at {url} with {slots} slots; "
        f"add data/{following}/ and run the check on it"
    )


def new_keys(
    document: dict[str, Any], references: Sequence[dict[str, Any]]
) -> list[str]:
    """List the keys of `document` that none of `references` has.

    It compares the top-level sections and the fields of each section's records, one
    level deep: enough to notice that the feed's format has moved.

    Returns:
        One `section: key, key` entry per section with new keys, `(top level)` for
        new sections; empty when there is nothing new.
    """
    known: dict[str, set[str]] = {}
    for reference in references:
        for section, keys in _keys(reference).items():
            known.setdefault(section, set()).update(keys)
    return [
        f"{section or '(top level)'}: {', '.join(sorted(new))}"
        for section, keys in _keys(document).items()
        if (new := keys - known.get(section, set()))
    ]


def main(
    argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None
) -> int:
    """Check the requested years and report on next year's feed.

    Args:
        argv: The command-line arguments; `sys.argv[1:]` when None.
        transport: The HTTP transport; tests pass an `httpx.MockTransport`.

    Returns:
        The exit status: 0 when every checked year passed, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Check the live public feed with our parser and the invariants."
    )
    parser.add_argument(
        "years",
        nargs="*",
        type=int,
        default=[YEAR],
        help=f"years to check, each with a data/<year>/ folder (default: {YEAR})",
    )
    years: list[int] = parser.parse_args(argv).years
    failed = []
    for year in years:
        ok, lines = check_year(year, transport=transport)
        print("\n".join(lines))
        if not ok:
            failed.append(str(year))
    if YEAR + 1 not in years:
        print(next_year_status(transport=transport))
    if failed:
        print(f"Feed check FAILED for {', '.join(failed)}")
        return 1
    print("Feed check passed")
    return 0


def _get(url: str, transport: httpx.BaseTransport | None) -> httpx.Response:
    with httpx.Client(
        transport=transport, timeout=TIMEOUT, follow_redirects=True
    ) as client:
        return client.get(url)


def _problems(
    invariant: Callable[[ProcessedFeed], list[str]], feed: ProcessedFeed
) -> list[str]:
    """Run one invariant; a feed it cannot even read is reported, not raised."""
    try:
        return invariant(feed)
    # The invariants read the raw JSON, which the parser may have skipped parts of.
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        return [f"could not run on this feed: {error!r}"]


def _recorded_documents() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_bytes())
        for path in sorted(RECORDED_FEEDS.glob("conference-*.json"))
    ]


def _keys(document: dict[str, Any]) -> dict[str, set[str]]:
    """The top-level keys under `""`, and each list section's record keys."""
    found = {"": set(document)}
    for section, records in document.items():
        if isinstance(records, list):
            found[section] = {
                key for record in records if isinstance(record, dict) for key in record
            }
    return found


if __name__ == "__main__":
    sys.exit(main())
