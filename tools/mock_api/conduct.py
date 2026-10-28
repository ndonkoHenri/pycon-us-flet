"""The mock's Code of Conduct endpoints: the directory and incident capture (API-08).

Both need the ``mask_violation`` flag (the legacy name) and reply in the 2019 envelope
``{code, data}``, as Ionic reads them. Incidents are recorded in
``MockState.incidents``; how a repeated badge scan is counted follows ``capture``
(D-57; ``tools/mock_api/README.md``, Unknown).
"""

from tools.mock_api.parse import encoded_query, json_object, text
from tools.mock_api.state import COC_DEDUPE, Attendee, Call, Incident, Refused

COC = "mask_violation"
"""The flag both endpoints need."""


def coc_attendees(call: Call) -> tuple[int, object]:
    """The attendee directory the name search runs over (``pycon-api.ts`` 201-216).

    Returns:
        200 ``{code, data: [{access_code, full_name, nickname, badge_name,
        violations}]}``.
    """
    call.require(COC)
    state = call.state
    data = [
        {
            "access_code": a.access_code,
            "full_name": a.full_name,
            "nickname": a.nickname,
            "badge_name": a.badge_name,
            "violations": state.violations(a),
        }
        for a in state.attendees.values()
    ]
    return 200, {"code": 200, "data": data}


def coc_scan(call: Call) -> tuple[int, object]:
    """Capture an incident from a badge scan: GET with the code encoded (218-252).

    Ionic sends one request per camera frame that sees the badge, with no notes and
    no ``force``.

    Returns:
        200 ``{code, data}`` with the attendee and the incidents now on record.

    Raises:
        Refused: 400 without ``attendee_access_code``; 404 for an unknown attendee.
    """
    call.require(COC)
    code = text(encoded_query(call.query), "attendee_access_code")
    return captured(call, call.state.attendee(code), notes="", force=False)


def coc_report(call: Call) -> tuple[int, object]:
    """Capture an incident from the name search: POST with notes and ``force``.

    Ionic sends ``{"attendee_access_code", "notes"?, "force": true}`` (222-230).

    Returns:
        200 ``{code, data}`` with the attendee and the incidents now on record.

    Raises:
        Refused: 400 for a body that isn't an object, or whose ``notes`` isn't a
            string or ``force`` a boolean; 404 for an unknown attendee.
    """
    call.require(COC)
    payload = json_object(call.body)
    notes = payload.get("notes", "")
    force = payload.get("force", False)
    if not isinstance(notes, str) or not isinstance(force, bool):
        raise Refused(400, "notes must be a string and force a boolean.")
    attendee = call.state.attendee(payload.get("attendee_access_code"))
    return captured(call, attendee, notes=notes, force=force)


def captured(
    call: Call, attendee: Attendee, notes: str, force: bool
) -> tuple[int, object]:
    """Record an incident unless the capture semantics say it is a repeat.

    ``force`` always records. Otherwise an ``idempotent`` mock records at most one
    incident per attendee every ``COC_DEDUPE`` seconds, and a ``non_idempotent`` one
    records every request.

    Args:
        call: The request.
        attendee: The attendee the incident is about.
        notes: The notes, or ``""``.
        force: Whether to record it whatever came before.

    Returns:
        200 ``{code, data: {nickname, full_name, badge_name, email, violations}}``.
    """
    state = call.state
    recent = any(
        i.access_code == attendee.access_code and call.now - i.at < COC_DEDUPE
        for i in state.incidents
    )
    if force or state.capture == "non_idempotent" or not recent:
        state.incidents.append(Incident(attendee.access_code, notes, force, call.now))
    data = {
        "nickname": attendee.nickname,
        "full_name": attendee.full_name,
        "badge_name": attendee.badge_name,
        "email": attendee.email,
        "violations": state.violations(attendee),
    }
    return 200, {"code": 200, "data": data}
