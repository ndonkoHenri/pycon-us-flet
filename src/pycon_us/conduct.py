"""The Code of Conduct tool's two calls: the directory and recording an incident (#758).

CoC is online-only and never queues (D-56): ``fetch_directory()`` asks
``coc_attendees`` each time the tool opens and the caller keeps the directory in
memory only; ``record()`` sends one confirmed incident and returns the answer. Every
record is ``COC_REPORT``, the POST with ``force: true``, whether the attendee was
found by name or by a scan (D-430): each is reviewed before it is sent, so the
server's repeat guard must not swallow a second, real incident, and the notes never
go in a URL. ``COC_SCAN``, Ionic's per-frame GET, is not called. Neither call logs
anything: no name, code, notes or email reaches a log (D-72).
"""

from pycon_us.core.conduct import Attendee, Recorded, parse_capture, parse_directory
from pycon_us.services.api import ApiClient, ApiError
from pycon_us.services.endpoints import COC_ATTENDEES, COC_REPORT


async def fetch_directory(api: ApiClient) -> tuple[Attendee, ...]:
    """Return the attendee directory the name search runs over (MASK-01, 15 s).

    Args:
        api: ``Services.api``, signed in with the ``mask_violation`` flag.

    Returns:
        The attendees, sorted by display name (``parse_directory()``).

    Raises:
        NetworkError: No answer arrived.
        ApiError: The mock refused the call (403 without the flag), or its reply
            could not be read or has no attendee list.
    """
    data = await api.request(COC_ATTENDEES)
    try:
        return parse_directory(data)
    except TypeError as error:
        raise ApiError(None, str(error)) from None


async def record(api: ApiClient, code: str, notes: str = "") -> Recorded:
    """Record one incident for an attendee, and return the count now on record (5 s).

    Sends ``{"attendee_access_code", "notes"?, "force": true}`` as Ionic's name path
    did, the notes only when they hold more than whitespace (D-430).

    Args:
        api: ``Services.api``, signed in with the ``mask_violation`` flag.
        code: The attendee's access code.
        notes: What the staff member wrote, or ``""``.

    Returns:
        The attendee the incident went to, with the new count.

    Raises:
        NetworkError: No answer arrived; ``maybe_sent`` says whether the incident may
            have been recorded all the same (D-410).
        ApiError: The mock refused the call (403 without the flag, 404 for an unknown
            code), or its reply could not be read (``unreadable``), so the incident
            may have been recorded all the same.
    """
    payload: dict[str, object] = {"attendee_access_code": code}
    if notes.strip():
        payload["notes"] = notes.strip()
    payload["force"] = True
    data = await api.request(COC_REPORT, payload=payload)
    try:
        return parse_capture(data)
    except TypeError as error:
        raise ApiError(None, str(error)) from None
