"""The endpoint table, its timeouts and the bytes on the wire, against Ionic (D-52, D-53).

The table must match the contract README (which cites `pycon-api.ts` by line) and the
mock's routes; the queries and signatures must equal those Ionic's own code produced
(`tests/fixtures/ionic/signing.json`).
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from pycon_us.services.api import server_time
from pycon_us.services.endpoints import (
    CHECK_FEATURES,
    ENDPOINTS,
    FETCH_PRODUCTS,
    LEAD_CAPTURE,
    LEAD_NOTE,
    READ_MOBILE_STATE,
    WRITE_MOBILE_STATE,
    Endpoint,
    fetch_products_query,
    lead_capture_query,
)
from tests.api_clients import Login, client_for, replying
from tools.mock_api.handlers import SIGNED

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "tools" / "mock_api" / "README.md"
VECTORS = ROOT / "tests" / "fixtures" / "ionic" / "signing.json"

ROW = re.compile(
    r"^\| `(\w+)`[^|]*\| (GET|POST|PATCH) `([^`?]+)[^|]*\|[^|]*\| (\d+) s \|"
)
"""A row of the README's endpoint table: name, method, path and timeout."""


def readme_endpoints() -> set[tuple[str, str, str, float]]:
    """The README's endpoint rows as (name, method, path, timeout), `<x>` as `{}`."""
    rows = set()
    for line in README.read_text().splitlines():
        if found := ROW.match(line):
            name, method, path, timeout = found.groups()
            rows.add((name, method, re.sub(r"<\w+>", "{}", path), float(timeout)))
    return rows


def test_the_table_matches_the_contract_readme() -> None:
    """Names, methods, paths and Ionic's timeouts equal the README's, but API-05's."""
    ours = {(e.name, e.method, e.path, e.timeout) for e in ENDPOINTS}
    never_called = {
        ("attendees_by_product", "GET", "check_in/attendees_by_product/{}/", 2)
    }
    assert readme_endpoints() == ours | never_called


def test_the_signed_endpoints_are_the_mocks_routes() -> None:
    """Every signed endpoint is a route the mock serves, and the mock serves no more."""
    assert {(e.method, e.path) for e in ENDPOINTS if e.signed} == set(SIGNED)


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: f"{e.method}-{e.name}")
async def test_each_request_carries_its_endpoints_timeout(endpoint: Endpoint) -> None:
    """Connect, read, write and pool all wait the endpoint's Ionic timeout."""
    recorder = replying(200, b'{"data": {}}')
    args = ("1",) * endpoint.path.count("{}")
    await client_for(recorder).request(endpoint, *args)
    timeouts = recorder.sent[0].extensions["timeout"]
    assert timeouts == dict.fromkeys(
        ("connect", "read", "write", "pool"), endpoint.timeout
    )


IONIC_CALLS: dict[str, tuple[Endpoint, tuple[str, ...], str]] = {
    "get-empty-body": (READ_MOBILE_STATE, (), ""),
    "get-query-encoded": (
        LEAD_CAPTURE, (), lead_capture_query("ABC123", "v/a+l=i d&ä!*'()~-_.", "42")
    ),
    "get-query-unencoded": (
        FETCH_PRODUCTS, (), fetch_products_query("ABC123", [1, 2], door=False)
    ),
    "patch-favorites": (WRITE_MOBILE_STATE, (), ""),
    "post-note-non-ascii": (LEAD_NOTE, ("ABC123",), ""),
    "post-escapes": (LEAD_NOTE, ("ABC123",), ""),
    "round-half-even": (READ_MOBILE_STATE, (), ""),
    "null-credentials": (CHECK_FEATURES, (), ""),
}  # fmt: skip
"""Ionic's vectors, by name, as the client's endpoint, path args and query."""


def vector(name: str) -> dict[str, Any]:
    """The Ionic signing case with this name."""
    cases = json.loads(VECTORS.read_text())["cases"]
    return next(case for case in cases if case["name"] == name)


@pytest.mark.parametrize("name", IONIC_CALLS)
async def test_the_client_sends_what_ionic_sent(name: str) -> None:
    """The target, body and the three headers equal Ionic's own for the same call."""
    case = vector(name)
    endpoint, args, query = IONIC_CALLS[name]
    recorder = replying(200, b'{"data": {}}')
    login = Login(case["key"], case["secret"])
    instant = case["now_ms"] / 1000
    client = client_for(recorder, login, year=2027, now=lambda: instant)
    await client.request(endpoint, *args, query=query, payload=case.get("payload"))
    sent = recorder.sent[0]
    assert sent.url.raw_path.decode() == case["path"]
    assert sent.content == case["body"].encode()
    for header, value in case["headers"].items():
        assert sent.headers.get(header) == value


def test_the_door_query_names_products_and_the_door_mode() -> None:
    """The door's `fetch_products` query lists product ids, unencoded, door mode."""
    assert fetch_products_query("ABC123", [10, 11], door=True) == (
        "attendee_access_code=ABC123&product_pk_list=10,11&mode=door_check_mode"
    )


@pytest.mark.parametrize(
    ("date", "seconds"),
    [
        ("Thu, 28 May 2026 20:26:40 GMT", 1_780_000_000.0),
        ("Thu, 28 May 2026 20:26:40 -0000", 1_780_000_000.0),
        ("Thu, 28 May 2026 22:26:40 +0200", 1_780_000_000.0),
        (None, None),
        ("", None),
        ("yesterday", None),
    ],
)
def test_the_servers_time_is_read_from_its_date(
    date: str | None, seconds: float | None
) -> None:
    """A `Date` in any zone gives the same instant; a missing or bad one gives None."""
    assert server_time(date) == seconds
