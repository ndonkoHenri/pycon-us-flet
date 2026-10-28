"""The mock API's Code of Conduct and lead-retrieval endpoints (API-08..API-10).

``mask_violations/*`` and ``lead_retrieval/*`` as ``tools/mock_api/README.md``
describes them, and how each capture semantics counts a repeat (D-57). The role gates
are pinned with the check-in ones in ``tests/test_mock_api_check_in.py``.
"""

import pytest

from tests.mock_calls import Clock, call, state_at
from tools.mock_api.state import (
    COC_DEDUPE,
    Capture,
    Incident,
    Lead,
    LeadNote,
    MockState,
)

ADA = "attendee_access_code=MOCK0001"
ADA_BADGE = f"{ADA}&badge_validator=v4l1d01"
ADA_DATA = {
    "nickname": "ada",
    "full_name": "Ada Example",
    "badge_name": "Ada",
    "email": "ada@example.com",
}


def test_the_coc_directory_lists_every_attendee_in_the_envelope() -> None:
    """``{code, data}`` with each attendee's names and incident count."""
    state = state_at()
    status, body = call(state, "GET", "mask_violations/attendees/", "coc")
    assert status == 200
    assert isinstance(body, dict) and body["code"] == 200
    assert body["data"][2] == {
        "access_code": "MOCK0003",
        "full_name": "Linus Placeholder",
        "nickname": "linus",
        "badge_name": "Linus",
        "violations": 3,
    }
    assert len(body["data"]) == len(state.attendees)


def test_made_up_attendees_follow_the_seeded_four_in_the_directory() -> None:
    """``attendees=3000`` serves 3,004: ``MOCK0005`` onwards, fake, with a spread."""
    state = MockState.from_seed(now=Clock(), attendees=3000)
    status, body = call(state, "GET", "mask_violations/attendees/", "coc")
    assert status == 200 and isinstance(body, dict)
    data = body["data"]
    assert len(data) == len({row["access_code"] for row in data}) == 3004
    assert [row["access_code"] for row in data[3:6]] == [
        "MOCK0004",
        "MOCK0005",
        "MOCK0006",
    ]
    assert data[-1]["access_code"] == "MOCK3004"
    assert {row["violations"] for row in data[4:]} == {0, 1, 2, 3, 5}
    made_up = list(state.attendees.values())[4:]
    assert all(a.email.endswith("@example.com") and not a.products for a in made_up)
    assert state.attendee("MOCK0005", "v4l1d05").full_name  # a badge that scans


def test_the_same_count_makes_the_same_attendees() -> None:
    """Generated, not random: two states with one count serve one directory."""
    first = MockState.from_seed(now=Clock(), attendees=50)
    second = MockState.from_seed(now=Clock(), attendees=50)
    assert first.attendees == second.attendees
    assert len(MockState.from_seed(now=Clock()).attendees) == 4


def test_a_badge_scan_records_an_incident_and_returns_the_count() -> None:
    """The scan GET records one incident and replies ``{code, data}``."""
    state = state_at()
    endpoint = f"mask_violations/capture/?{ADA}"
    assert call(state, "GET", endpoint, "coc") == (
        200,
        {"code": 200, "data": ADA_DATA | {"violations": 1}},
    )
    assert state.incidents == [Incident("MOCK0001", "", False, state.now())]


def test_the_scan_query_is_percent_decoded() -> None:
    """``encodeURIComponent``'s escapes are decoded before the lookup."""
    state = state_at()
    endpoint = "mask_violations/capture/?attendee_access_code=MOCK%30001"
    assert call(state, "GET", endpoint, "coc")[0] == 200


def test_repeated_scans_within_a_minute_count_once_when_idempotent() -> None:
    """Per-frame GETs record one incident per ``COC_DEDUPE`` seconds (D-57)."""
    clock = Clock()
    state = state_at("idempotent", clock)
    endpoint = f"mask_violations/capture/?{ADA}"
    call(state, "GET", endpoint, "coc")
    clock.at += COC_DEDUPE - 1
    assert call(state, "GET", endpoint, "coc")[1] == {
        "code": 200,
        "data": ADA_DATA | {"violations": 1},
    }
    clock.at += 1
    call(state, "GET", endpoint, "coc")
    assert len(state.incidents) == 2


def test_repeated_scans_each_count_when_not_idempotent() -> None:
    """Under non-idempotent capture every scan GET records an incident."""
    state = state_at("non_idempotent")
    for _ in range(3):
        call(state, "GET", f"mask_violations/capture/?{ADA}", "coc")
    assert len(state.incidents) == 3


def test_a_forced_report_always_records_its_notes() -> None:
    """The name search's POST with ``force`` records each time, notes included."""
    state = state_at("idempotent")
    report = {
        "attendee_access_code": "MOCK0002",
        "notes": "Hall B, 10:05 ☕",
        "force": True,
    }
    call(state, "POST", "mask_violations/capture/", "coc", report)
    status, body = call(state, "POST", "mask_violations/capture/", "coc", report)
    assert status == 200
    assert isinstance(body, dict) and body["data"]["violations"] == 3  # one seeded
    assert [i.notes for i in state.incidents] == ["Hall B, 10:05 ☕"] * 2
    assert all(i.forced for i in state.incidents)


def test_an_unforced_report_without_notes_dedupes_like_a_scan() -> None:
    """A POST without ``force`` follows the scan's semantics; ``notes`` is optional."""
    state = state_at("idempotent")
    report = {"attendee_access_code": "MOCK0002"}
    call(state, "POST", "mask_violations/capture/", "coc", report)
    call(state, "POST", "mask_violations/capture/", "coc", report)
    assert len(state.incidents) == 1


@pytest.mark.parametrize(
    ("method", "endpoint", "payload", "status"),
    [
        ("GET", "mask_violations/capture/", None, 400),
        ("GET", "mask_violations/capture/?attendee_access_code=NOPE", None, 404),
        ("POST", "mask_violations/capture/", {"attendee_access_code": "NOPE"}, 404),
        ("POST", "mask_violations/capture/", {"attendee_access_code": 1}, 404),
        ("POST", "mask_violations/capture/", [1], 400),
        (
            "POST",
            "mask_violations/capture/",
            {"attendee_access_code": "MOCK0001", "force": 1},
            400,
        ),
        (
            "POST",
            "mask_violations/capture/",
            {"attendee_access_code": "MOCK0001", "notes": 1},
            400,
        ),
    ],
)
def test_a_bad_coc_capture_is_refused_and_records_nothing(
    method: str, endpoint: str, payload: object, status: int
) -> None:
    """A missing or unknown code or a malformed body records no incident."""
    state = state_at()
    reply_status, body = call(state, method, endpoint, "coc", payload)
    assert reply_status == status
    assert isinstance(body, dict) and body.keys() == {"code", "error"}
    assert state.incidents == []


def test_the_sponsor_list_is_bare_with_one_name_json_quoted() -> None:
    """Sponsors as Ionic reads them; a missing booth or logo is left out."""
    status, body = call(state_at(), "GET", "lead_retrieval/sponsors/", "staff")
    assert (status, body) == (
        200,
        {
            "sponsors": [
                {
                    "id": 1,
                    "name": "Example Corp",
                    "booth_number": "101",
                    "logo_url": "https://example.com/logos/example-corp.png",
                },
                {"id": 2, "name": '"Quoted Labs"', "booth_number": "214"},
                {"id": 3, "name": "Sample Systems"},
            ]
        },
    )


def test_a_sponsor_captures_a_lead_for_its_own_sponsor() -> None:
    """No ``sponsor_id``: the lead goes to the account's sponsor; ``{code, data}``."""
    state = state_at()
    assert call(state, "GET", f"lead_retrieval/capture/?{ADA_BADGE}", "sponsor") == (
        200,
        {"code": 200, "data": {"first_name": "Ada"}},
    )
    assert state.leads == [Lead(1, "MOCK0001", state.now())]


def test_staff_capture_a_lead_on_behalf_of_the_sponsor_they_name() -> None:
    """Door staff send ``sponsor_id`` (a string, as Ionic stores it)."""
    state = state_at()
    endpoint = f"lead_retrieval/capture/?{ADA_BADGE}&sponsor_id=2"
    assert call(state, "GET", endpoint, "staff")[0] == 200
    assert [lead.sponsor_id for lead in state.leads] == [2]


@pytest.mark.parametrize(
    ("role", "query", "status"),
    [
        ("staff", ADA_BADGE, 400),  # staff must name a sponsor
        ("sponsor", f"{ADA_BADGE}&sponsor_id=2", 403),  # not its own
        ("sponsor", f"{ADA_BADGE}&sponsor_id=1", 200),  # its own is fine
        ("staff", f"{ADA_BADGE}&sponsor_id=9", 404),
        ("staff", f"{ADA_BADGE}&sponsor_id=x", 400),
        ("sponsor", f"{ADA}&badge_validator=wrong", 404),
        ("sponsor", f"{ADA}&badge_validator=", 404),
        ("sponsor", "attendee_access_code=NOPE&badge_validator=v4l1d01", 404),
        ("sponsor", ADA, 400),
        ("sponsor", "badge_validator=v4l1d01", 400),
    ],
)
def test_lead_capture_checks_the_badge_and_the_sponsor(
    role: str, query: str, status: int
) -> None:
    """A wrong badge, a missing or foreign sponsor is refused in the envelope."""
    state = state_at()
    reply_status, body = call(state, "GET", f"lead_retrieval/capture/?{query}", role)
    assert reply_status == status
    assert isinstance(body, dict) and "code" in body
    assert len(state.leads) == (status == 200)


def test_a_repeated_capture_is_one_lead_when_idempotent() -> None:
    """The same capture twice is recorded once and answered the same (D-57)."""
    state = state_at("idempotent")
    endpoint = f"lead_retrieval/capture/?{ADA_BADGE}"
    first = call(state, "GET", endpoint, "sponsor")
    assert call(state, "GET", endpoint, "sponsor") == first
    assert len(state.leads) == 1


def test_a_repeated_capture_is_two_leads_when_not_idempotent() -> None:
    """Under non-idempotent capture every request adds a lead row (D-57)."""
    state = state_at("non_idempotent")
    endpoint = f"lead_retrieval/capture/?{ADA_BADGE}"
    call(state, "GET", endpoint, "sponsor")
    call(state, "GET", endpoint, "sponsor")
    assert [lead.access_code for lead in state.leads] == ["MOCK0001", "MOCK0001"]


def test_a_note_is_recorded_for_a_captured_lead() -> None:
    """The note modal's text is kept against the sponsor's lead."""
    state = state_at()
    call(state, "GET", f"lead_retrieval/capture/?{ADA_BADGE}", "sponsor")
    note = "Interest: hot\nFollow-up: Send info\nNotes: Likes ☕"
    payload = {"accessCode": "MOCK0001", "note": note}
    assert call(state, "POST", "lead_retrieval/MOCK0001/note/", "sponsor", payload) == (
        200,
        {"code": 200, "data": {}},
    )
    assert state.notes == [LeadNote(1, "MOCK0001", note, state.now())]


@pytest.mark.parametrize(
    ("capture", "notes"),
    [("idempotent", ["a", "b"]), ("non_idempotent", ["a", "a", "b"])],
)
def test_a_repeated_note_is_recorded_once_only_when_idempotent(
    capture: Capture, notes: list[str]
) -> None:
    """The resend after a lost reply records nothing under ``idempotent``; an edit does."""
    state = state_at(capture)
    call(state, "GET", f"lead_retrieval/capture/?{ADA_BADGE}", "sponsor")
    for text in ("a", "a", "b"):
        payload = {"accessCode": "MOCK0001", "note": text}
        status, _ = call(
            state, "POST", "lead_retrieval/MOCK0001/note/", "sponsor", payload
        )
        assert status == 200
    assert [n.note for n in state.notes] == notes


def test_staff_note_a_lead_for_the_sponsor_named_and_the_path_is_decoded() -> None:
    """Staff send ``sponsor_id``; the app's encoded path segment is decoded."""
    state = state_at()
    call(state, "GET", f"lead_retrieval/capture/?{ADA_BADGE}&sponsor_id=2", "staff")
    payload = {"accessCode": "MOCK0001", "note": "Notes: hi", "sponsor_id": "2"}
    endpoint = "lead_retrieval/MOCK%30001/note/"
    assert call(state, "POST", endpoint, "staff", payload)[0] == 200
    assert [n.sponsor_id for n in state.notes] == [2]


@pytest.mark.parametrize(
    ("code", "payload", "status"),
    [
        ("MOCK0002", {"accessCode": "MOCK0002", "note": "x"}, 404),  # not captured
        ("NOPE", {"accessCode": "NOPE", "note": "x"}, 404),
        ("MOCK0001", {"accessCode": "MOCK0002", "note": "x"}, 400),
        ("MOCK0001", {"accessCode": "MOCK0001"}, 400),
        ("MOCK0001", {"accessCode": "MOCK0001", "note": "x", "sponsor_id": "3"}, 403),
    ],
)
def test_a_bad_note_is_refused_and_records_nothing(
    code: str, payload: dict[str, object], status: int
) -> None:
    """A note needs its lead, a matching ``accessCode`` and a note string."""
    state = state_at()
    call(state, "GET", f"lead_retrieval/capture/?{ADA_BADGE}", "sponsor")
    endpoint = f"lead_retrieval/{code}/note/"
    assert call(state, "POST", endpoint, "sponsor", payload)[0] == status
    assert state.notes == []
