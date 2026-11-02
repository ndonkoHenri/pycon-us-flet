"""Tests for the CoC tool's two calls, ``conduct.py``, against the mock (#758; API-08).

Each call runs through the real client and the mock's transport, signed in as the
seeded ``coc`` account, so the signature check runs too. Every record is the POST
with ``force: true`` (D-430): it records one incident per call under both capture
semantics (D-57), notes included, and returns the new count. Refusals are
``ApiError``s, a lost reply a ``NetworkError`` that may have been sent (D-410), and
nothing these calls do puts a code, a name, the notes or an email in a log (D-72).
"""

import json
import logging

import pytest

from pycon_us.conduct import fetch_directory, record
from pycon_us.core.conduct import Recorded, display_name
from pycon_us.services.api import ApiError, NetworkError
from tests.api_clients import ReplyReplaced, client_for, replying, signed_in
from tests.mock_calls import Clock, state_at
from tools.mock_api.state import CAPTURES, Capture, Incident, MockState

NOTES = "Hall B, 10:05: no mask ☕"


async def test_the_directory_comes_from_the_mock_sorted() -> None:
    """``fetch_directory`` returns the mock's four attendees, sorted, with counts."""
    client, recorder, _ = await signed_in("coc")
    directory = await fetch_directory(client)
    assert [(display_name(a), a.incidents) for a in directory] == [
        ("Ada Example", 0),
        ("Grace Sample", 1),
        ("Linus Placeholder", 3),
        ("Margaret Test", 0),
    ]
    sent = recorder.sent[-1]
    assert (sent.method, sent.url.path) == (
        "GET",
        "/2026/api/v1/mask_violations/attendees/",
    )


async def test_a_large_mock_directory_is_read_whole() -> None:
    """``MockState.from_seed(attendees=3000)`` serves 3,004 attendees, all read."""
    large = MockState.from_seed(now=Clock(), attendees=3000)
    client, _, _ = await signed_in("coc", large)
    directory = await fetch_directory(client)
    assert len(directory) == 3004
    assert {a.code for a in directory} >= {"MOCK0001", "MOCK0005", "MOCK3004"}


@pytest.mark.parametrize(
    "body",
    [b'{"code": 200, "data": {"attendees": []}}', b'{"code": 200, "data": null}'],
)
async def test_a_directory_reply_without_a_list_is_an_api_error(body: bytes) -> None:
    """A ``data`` that is not a list can't be read: an ``ApiError``, not a crash."""
    with pytest.raises(ApiError):
        await fetch_directory(client_for(replying(200, body)))


@pytest.mark.parametrize("capture", CAPTURES)
async def test_each_record_is_one_forced_incident_under_both_semantics(
    capture: Capture,
) -> None:
    """Two records within the mock's 60 s window are two incidents, with the notes."""
    client, recorder, state = await signed_in("coc", state_at(capture))
    first = await record(client, "MOCK0002", NOTES)
    second = await record(client, "MOCK0002", NOTES)
    assert first == Recorded("Grace Sample", "Grace S.", "grace@example.com", 2)
    assert second.incidents == 3
    now = state.now()
    assert state.incidents == [Incident("MOCK0002", NOTES, True, now)] * 2
    sent = recorder.sent[-1]
    assert (sent.method, sent.url.path, sent.url.query) == (
        "POST",
        "/2026/api/v1/mask_violations/capture/",
        b"",
    )  # the notes and the code never go in a URL
    assert json.loads(sent.content) == {
        "attendee_access_code": "MOCK0002",
        "notes": NOTES,
        "force": True,
    }


@pytest.mark.parametrize("notes", ["", "   \n"])
async def test_blank_notes_are_left_out(notes: str) -> None:
    """Without notes the body is the code and ``force`` only, as Ionic sent it."""
    client, recorder, state = await signed_in("coc")
    recorded = await record(client, "MOCK0001", notes)
    assert recorded.incidents == 1
    assert json.loads(recorder.sent[-1].content) == {
        "attendee_access_code": "MOCK0001",
        "force": True,
    }
    assert [i.notes for i in state.incidents] == [""]


@pytest.mark.parametrize("role", ["staff", "sponsor", "attendee"])
async def test_an_account_without_the_flag_is_refused(role: str) -> None:
    """403 without ``mask_violation``, for either call: nothing is recorded."""
    client, _, state = await signed_in(role)
    with pytest.raises(ApiError) as directory:
        await fetch_directory(client)
    with pytest.raises(ApiError) as recorded:
        await record(client, "MOCK0001", NOTES)
    assert directory.value.status == recorded.value.status == 403
    assert state.incidents == []


async def test_an_unknown_code_is_a_404() -> None:
    """A code the mock doesn't know is an ``ApiError`` 404, and nothing is recorded."""
    client, _, state = await signed_in("coc")
    with pytest.raises(ApiError) as raised:
        await record(client, "NOPE0000", NOTES)
    assert raised.value.status == 404
    assert state.incidents == []


async def test_a_lost_reply_is_a_network_error_that_may_have_been_sent() -> None:
    """The mock records, then the reply is lost: ``maybe_sent`` says so (D-410)."""
    client, _, state = await signed_in("coc")
    state.faults.inject("lost_response")
    with pytest.raises(NetworkError) as raised:
        await record(client, "MOCK0003", NOTES)
    assert raised.value.maybe_sent
    assert [i.access_code for i in state.incidents] == ["MOCK0003"]


async def test_a_record_reply_without_an_attendee_is_an_api_error() -> None:
    """A ``data`` that is not an object can't be read: an ``ApiError``."""
    client = client_for(replying(200, b'{"code": 200, "data": []}'))
    with pytest.raises(ApiError):
        await record(client, "MOCK0001")


@pytest.mark.parametrize(
    "body",
    [
        b"<html>ok</html>",
        b'{"ok": true}',
        b'{"code": 200}',
        b'{"code": 200, "data": []}',
    ],
)
async def test_a_committed_record_with_an_unreadable_reply_says_so(body: bytes) -> None:
    """Whatever made the reply unreadable, the error says it may be on record (#874)."""
    client, recorder, state = await signed_in("coc")
    recorder.inner = ReplyReplaced(recorder.inner, body)
    with pytest.raises(ApiError) as raised:
        await record(client, "MOCK0002", NOTES)
    assert raised.value.unreadable
    assert len(state.incidents) == 1


async def test_no_log_line_holds_a_code_a_name_the_notes_or_an_email(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every logger at DEBUG through both calls, a refusal and a lost reply (D-72)."""
    client, _, state = await signed_in("coc")
    with caplog.at_level(logging.DEBUG):
        await fetch_directory(client)
        await record(client, "MOCK0002", NOTES)
        with pytest.raises(ApiError):
            await record(client, "MOCK9999", NOTES)
        state.faults.inject("lost_response")
        with pytest.raises(NetworkError):
            await record(client, "MOCK0002", NOTES)
    secrets = ["MOCK0", "Grace", "gsample", "grace@", "example.com", "Hall B", "Ada"]
    logged = caplog.text + "".join(str(r.args) for r in caplog.records)
    assert "mask_violations/capture/" in logged  # httpx logs each URL at INFO
    assert [s for s in secrets if s in logged] == []
