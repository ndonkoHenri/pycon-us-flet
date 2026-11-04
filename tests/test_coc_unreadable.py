"""A CoC record whose reply can't be read, on the CoC tool's review (#874, D-434).

The mock commits the incident, then the reply is replaced: what a server that recorded
it but answered unusably under HTTP 200 looks like. The dialog must say it may be on
record, and nothing may send it again on its own; a real refusal stays a refusal.
`tests/test_coc_review.py` holds the rest of the review, and the helpers used here.
"""

import asyncio

import pytest

from pycon_us.ui.coc_review import MAYBE_RECORDED
from pycon_us.ui.coc_review_dialog import RECORD, RECORD_ANYWAY
from tests import test_coc_review, test_staff_coc
from tests.api_clients import ReplyReplaced, replying
from tests.scan_rig import panel
from tests.test_coc_review import (
    NOTES,
    notes_text,
    problem,
    scan,
    tap,
    texts,
    type_notes,
)
from tests.test_staff_coc import Show, Switch
from tools.mock_api.state import MockState

show, switch, stored = test_staff_coc.show, test_staff_coc.switch, test_staff_coc.stored
mock = test_coc_review.mock

UNREADABLE = [b"<html>ok</html>", b"\xff\xfe", b'{"ok": true}', b'{"code": 200}', b"[]"]
"""Bodies of a committed record's reply under HTTP 200 that say nothing about it."""


@pytest.mark.parametrize("body", UNREADABLE)
async def test_an_unreadable_reply_may_be_recorded_and_cancel_says_not_confirmed(
    show: Show, switch: Switch, mock: MockState, body: bytes
) -> None:
    """The warning and Record anyway, the notes kept, no resend; Cancel "Not confirmed"."""
    shown = await show()
    task = await scan(shown)
    await type_notes(shown, NOTES)
    switch.inner = ReplyReplaced(switch.inner, body)
    await tap(shown, "coc.review.record")
    await shown.settle()
    assert problem(shown) == MAYBE_RECORDED
    assert RECORD_ANYWAY in texts(shown) and RECORD not in texts(shown)
    assert notes_text(shown) == NOTES
    assert len(mock.incidents) == 1  # it landed, and nothing was sent again
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)
    assert len(mock.incidents) == 1
    assert panel(shown).startswith(f"Not confirmed\nGrace Sample\n{MAYBE_RECORDED}")


async def test_record_anyway_after_an_unreadable_reply_is_the_staff_member_s_choice(
    show: Show, switch: Switch, mock: MockState
) -> None:
    """Only the tap sends a second incident, and its readable reply closes the dialog."""
    shown = await show()
    task = await scan(shown)
    committing = switch.inner
    switch.inner = ReplyReplaced(committing, b"<html>ok</html>")
    await tap(shown, "coc.review.record")
    switch.inner = committing
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(task, 2)
    assert len(mock.incidents) == 2
    assert panel(shown).startswith("Incident recorded\nGrace Sample\n3 on record")


@pytest.mark.parametrize(
    ("status", "body", "said"),
    [
        (200, b'{"code": 500, "error": "Boom."}', "Boom."),
        (500, b'{"code": 500, "error": "Boom."}', "Boom."),
        (502, b"<html>bad gateway</html>", "Bad Gateway"),
    ],
    ids=["error-envelope-under-200", "error-status", "error-status-not-json"],
)
async def test_a_refusal_stays_a_refusal(
    show: Show, switch: Switch, mock: MockState, status: int, body: bytes, said: str
) -> None:
    """An error envelope or status: "Not recorded", Record as it was, Cancel the same."""
    shown = await show()
    task = await scan(shown)
    switch.inner = replying(status, body)
    await tap(shown, "coc.review.record")
    assert problem(shown) == f"Not recorded. {said}"
    assert RECORD in texts(shown) and RECORD_ANYWAY not in texts(shown)
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)
    assert mock.incidents == []
    assert panel(shown).startswith("Not recorded\nGrace Sample")
