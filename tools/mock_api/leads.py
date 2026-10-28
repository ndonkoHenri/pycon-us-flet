"""The mock's lead-retrieval endpoints: sponsors, capture and notes (API-09, API-10).

A sponsor's account (``lead_retrieval``) captures leads for its own sponsor and sends
no ``sponsor_id``; a door-staff account (``door_check_in``) scans on behalf of the
sponsor it names. Leads and notes are recorded in ``MockState.leads`` and
``MockState.notes``; a repeated capture follows ``capture`` (D-57).
"""

from urllib.parse import unquote

from tools.mock_api.parse import encoded_query, json_object, text
from tools.mock_api.state import Call, Lead, LeadNote, Refused, Sponsor

LEADS = ("lead_retrieval", "door_check_in")
"""Either flag reaches the lead endpoints, as Ionic's menu does (``map.ts`` 308-320)."""


def lead_sponsors(call: Call) -> tuple[int, object]:
    """The sponsors staff can scan for (``pycon-api.ts`` 254-263; ``map.ts`` 367-419).

    Returns:
        200 ``{"sponsors": [{id, name, booth_number?, logo_url?}]}``, bare; a missing
        booth or logo is left out.
    """
    call.require(*LEADS)
    sponsors = [
        {"id": s.id, "name": s.name}
        | ({"booth_number": s.booth_number} if s.booth_number is not None else {})
        | ({"logo_url": s.logo_url} if s.logo_url is not None else {})
        for s in call.state.sponsors
    ]
    return 200, {"sponsors": sponsors}


def sponsor_for(call: Call, given: object) -> Sponsor:
    """The sponsor a lead goes to: the one named, or the account's own.

    Args:
        call: The request.
        given: The ``sponsor_id`` sent (a string, as Ionic stores it), or None.

    Returns:
        The sponsor.

    Raises:
        Refused: 400 when no sponsor is named and the account has none, or the id
            isn't a decimal id; 403 when an account without ``door_check_in`` names
            another sponsor than its own; 404 for an unknown sponsor.
    """
    account = call.account
    if given is None or given == "":
        if not account.features.get("lead_retrieval") or account.sponsor_id is None:
            raise Refused(400, "sponsor_id is required.")
        sponsor_id = account.sponsor_id
    elif type(given) is int or (
        isinstance(given, str)
        and given.isascii()
        and given.isdigit()
        and len(given) < 10
    ):
        sponsor_id = int(given)
    else:
        raise Refused(400, "sponsor_id must be an id.")
    if sponsor_id != account.sponsor_id and not account.features.get("door_check_in"):
        raise Refused(403, "This account can't capture leads for another sponsor.")
    found = next((s for s in call.state.sponsors if s.id == sponsor_id), None)
    if found is None:
        raise Refused(404, "Unknown sponsor.")
    return found


def lead_capture(call: Call) -> tuple[int, object]:
    """Capture a lead from a badge: GET with an encoded query (273-335).

    The query carries ``attendee_access_code``, ``badge_validator`` (always checked)
    and, for staff, ``sponsor_id``. Under ``idempotent`` capture a sponsor gets one
    lead per attendee and a repeat answers the same; under ``non_idempotent`` every
    request adds a lead row (D-57).

    Returns:
        200 ``{code, data: {first_name}}``.

    Raises:
        Refused: 400 for a missing parameter; 404 for an unknown attendee or sponsor,
            or a wrong validator.
    """
    call.require(*LEADS)
    params = encoded_query(call.query)
    code = text(params, "attendee_access_code")
    attendee = call.state.attendee(code, text(params, "badge_validator"))
    sponsor = sponsor_for(call, params.get("sponsor_id"))
    leads = call.state.leads
    known = any(
        lead.sponsor_id == sponsor.id and lead.access_code == code for lead in leads
    )
    if call.state.capture == "non_idempotent" or not known:
        leads.append(Lead(sponsor.id, code, call.now))
    return 200, {"code": 200, "data": {"first_name": attendee.first_name}}


def lead_note(call: Call) -> tuple[int, object]:
    """Note a captured lead: POST ``lead_retrieval/<code>/note/`` (337-371).

    Ionic puts the access code in the path unencoded; the app encodes it (API-11), so
    the mock decodes that one segment. The body is ``{"accessCode", "note"[,
    "sponsor_id"]}``. Under ``idempotent`` capture a note that repeats the sponsor's
    last note for the lead records nothing; under ``non_idempotent`` every request
    adds a note row (D-57).

    Returns:
        200 ``{code, data: {}}``; Ionic ignores it.

    Raises:
        Refused: 400 for a malformed body, or an ``accessCode`` that isn't the path's;
            404 for an unknown attendee or sponsor, or a lead this sponsor hasn't
            captured.
    """
    call.require(*LEADS)
    code = unquote(call.segment)
    payload = json_object(call.body)
    note = text(payload, "note")
    if payload.get("accessCode") != code:
        raise Refused(400, "accessCode must be the path's access code.")
    call.state.attendee(code)
    sponsor = sponsor_for(call, payload.get("sponsor_id"))
    if not any(
        lead.sponsor_id == sponsor.id and lead.access_code == code
        for lead in call.state.leads
    ):
        raise Refused(404, "No lead for this attendee.")
    notes = call.state.notes
    last = [
        n.note for n in notes if (n.sponsor_id, n.access_code) == (sponsor.id, code)
    ]
    if call.state.capture == "non_idempotent" or last[-1:] != [note]:
        notes.append(LeadNote(sponsor.id, code, note, call.now))
    return 200, {"code": 200, "data": {}}
