"""The mock API's pure request handler: routing, envelopes, signing, accounts (D-50).

``handle`` takes a request as plain values and returns a reply as plain values: it does
no I/O and reads the time only from ``MockState.now`` (plus its ``skew``), so the tests
drive it directly or through ``transport.py``, and the LAN server wraps the same
function. This module holds the routing, the envelopes, the signature check, the
``revoked`` fault and the account endpoints; the staff endpoints live in
``check_in.py``, ``conduct.py`` and ``leads.py``, and the state in ``state.py``
(contract in ``README.md``).
"""

import hmac
from collections.abc import Callable, Mapping
from email.utils import formatdate

from pycon_us.core.signing import canonical_body, sign
from tools.mock_api import check_in, conduct, leads
from tools.mock_api.parse import json_object
from tools.mock_api.state import Account, Call, MockState, Refused

WINDOW = 600
"""Seconds a signed request's timestamp may be from the mock's clock (2019's value)."""

FLAGS = ("lead_retrieval", "door_check_in", "mask_violation")
"""The flags ``check_features`` returns; ``is_speaker`` only comes with ``authenticate``."""

type Reply = tuple[int, dict[str, str], bytes]
"""A reply: the status, the headers and the body bytes."""

type Handler = Callable[[Call], tuple[int, object]]
"""A signed endpoint: the checked request in, the status and the payload out."""


def handle(
    state: MockState,
    method: str,
    raw_path: str,
    headers: Mapping[str, str],
    body: bytes,
) -> Reply:
    """Answer one request to the mock API.

    Args:
        state: The mock's state; endpoints that write change it.
        method: The HTTP method as sent.
        raw_path: The request target (path and query) exactly as sent, undecoded.
        headers: The request headers, in any letter case.
        body: The body bytes exactly as sent.

    Returns:
        The status, the headers (``Content-Type`` and a ``Date`` from the mock's clock,
        ``state.now`` plus ``state.skew``, which the client learns skew from, D-53) and
        the JSON body.
    """
    now = state.now() + state.skew
    try:
        status, payload = route(state, now, method, raw_path, headers, body)
    except Refused as refused:
        status, payload = refused.status, refused.body
    reply_headers = {
        "Content-Type": "application/json",
        "Date": formatdate(now, usegmt=True),
    }
    return status, reply_headers, canonical_body(payload)


def route(
    state: MockState,
    now: float,
    method: str,
    raw_path: str,
    headers: Mapping[str, str],
    body: bytes,
) -> tuple[int, object]:
    """Find the endpoint for a request, check its signature, and run it.

    The route is checked first, so an unknown route is 404 whatever its headers.

    Args:
        state: The mock's state.
        now: The time of this request, ``state.now()`` plus ``state.skew``.
        method: The HTTP method as sent.
        raw_path: The request target exactly as sent.
        headers: The request headers.
        body: The body bytes as sent.

    Returns:
        The status and the reply payload.

    Raises:
        Refused: The route is unknown (404), the signature check failed (401 or 403),
            or the endpoint refused the request.
    """
    prefix = f"/{state.year}/api/v1/"
    path, _, query = raw_path.partition("?")
    endpoint = path.removeprefix(prefix) if path.startswith(prefix) else None
    if (method, endpoint) == ("POST", "authenticate/"):
        return authenticate(state, body)
    found = find(method, endpoint)
    if found is None:
        raise Refused(404, f"No route for {method} {path}.")
    handler, segment = found
    account = verify(state, now, method, raw_path, headers, body)
    return handler(Call(state, account, now, query, segment, body))


def find(method: str, endpoint: str | None) -> tuple[Handler, str] | None:
    """Match a request to a signed route, ``{}`` standing for one non-empty segment.

    Args:
        method: The HTTP method as sent.
        endpoint: The path under ``/<year>/api/v1/``, or None outside it.

    Returns:
        The endpoint and the segment ``{}`` matched (``""`` if none), or None.
    """
    if endpoint is None:
        return None
    parts = endpoint.split("/")
    for (verb, pattern), handler in SIGNED.items():
        shape = pattern.split("/")
        if verb != method or len(shape) != len(parts):
            continue
        segment = ""
        for want, got in zip(shape, parts, strict=True):
            if want == "{}" and got:
                segment = got
            elif want != got:
                break
        else:
            return handler, segment
    return None


def verify(
    state: MockState,
    now: float,
    method: str,
    raw_path: str,
    headers: Mapping[str, str],
    body: bytes,
) -> Account:
    """Check a signed request's key, timestamp and signature (D-52).

    The signature is recomputed over the request target and the body exactly as
    received, so any change to the method, the path, the query (its order included),
    the body bytes or the timestamp makes it differ.

    Args:
        state: The mock's state.
        now: The time of this request.
        method: The HTTP method as sent.
        raw_path: The request target exactly as sent.
        headers: The request headers, in any letter case.
        body: The body bytes as sent.

    Returns:
        The account the key belongs to.

    Raises:
        Refused: 401 for a missing or unknown key, or while the ``revoked`` fault is
            on (D-57); 403 for a missing or malformed
            timestamp, one more than ``WINDOW`` seconds from ``now``, or a wrong
            signature.
    """
    lower = {name.lower(): value for name, value in headers.items()}
    key = lower.get("x-api-key")
    account = next((a for a in state.accounts if a.key == key), None)
    if key is None or account is None:
        raise Refused(401, "Unknown API key.")
    if state.faults.take("revoked"):
        raise Refused(401, "API key revoked.")
    stamp = lower.get("x-api-timestamp", "")
    # Only the digits Ionic sends: "+5", " 5" or "05" would sign as another string.
    try:
        timestamp = int(stamp) if stamp.isascii() and stamp.isdigit() else None
    except ValueError:  # over int()'s digit limit (sys.get_int_max_str_digits)
        timestamp = None
    if timestamp is None or str(timestamp) != stamp:
        raise Refused(403, "Missing or malformed timestamp.")
    # Compared, not subtracted: int - float overflows for an int past float's range.
    if not now - WINDOW <= timestamp <= now + WINDOW:
        raise Refused(403, "Timestamp outside the window.")
    expected = sign(account.secret, timestamp, method, raw_path, body)
    given = lower.get("x-api-signature", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise Refused(403, "Wrong signature.")
    return account


def authenticate(state: MockState, body: bytes) -> tuple[int, object]:
    """Sign in with an email and a password (unsigned; ``login.ts`` 58-67).

    Args:
        state: The mock's state.
        body: ``{"email", "password"}``.

    Returns:
        200 with the account's nickname, email, key, secret and flags, bare.

    Raises:
        Refused: 401 ``{"message"}`` for a wrong email or password, the field Ionic
            shows as "Invalid Auth: <message>"; 400 for a body that is not an object.
    """
    payload = json_object(body)
    for account in state.accounts:
        if (account.email, account.password) == (
            payload.get("email"),
            payload.get("password"),
        ):
            return 200, {
                "nickname": account.nickname,
                "email": account.email,
                "key": account.key,
                "secret": account.secret,
                "features": account.features,
            }
    message = "Invalid email or password."
    raise Refused(401, message, {"message": message})


def check_features(call: Call) -> tuple[int, object]:
    """Return the account's role flags, absent ones left out (``user-data.ts`` 61-66).

    Args:
        call: The signed request.

    Returns:
        200 ``{"features": {...}}``, bare.
    """
    flags = {name: on for name, on in call.account.features.items() if name in FLAGS}
    return 200, {"features": flags}


def read_mobile_state(call: Call) -> tuple[int, object]:
    """Return the account's favourites (``user-data.ts`` 76-85).

    Args:
        call: The signed request.

    Returns:
        200 ``{"favorites": [...]}``, bare, ids as strings.
    """
    return 200, {"favorites": call.account.favorites}


def write_mobile_state(call: Call) -> tuple[int, object]:
    """Replace the account's favourites with the list sent (``pycon-api.ts`` 80-101).

    Ids are kept as strings (D-42); integer ids are accepted and stored as their
    decimal strings. Anything else is refused, floats included, so no id depends on
    how a float prints (``1.0`` in Python, ``1`` in JavaScript).

    Args:
        call: The signed request, its body ``{"favorites": [...]}``.

    Returns:
        200 with the list now stored, bare (Ionic ignores it).

    Raises:
        Refused: 400 unless ``favorites`` is a list of strings and integers, each
            encodable as UTF-8: a JSON escape can carry a lone surrogate, which no
            reply could then serialise.
    """
    favorites = json_object(call.body).get("favorites")
    if not isinstance(favorites, list) or not all(
        type(item) in (str, int) for item in favorites
    ):
        raise Refused(400, "favorites must be a list of ids.")
    ids = [str(item) for item in favorites]
    try:
        "".join(ids).encode()
    except UnicodeEncodeError:
        raise Refused(400, "favorites must be a list of ids.") from None
    call.account.favorites = ids
    return 200, {"favorites": ids}


SIGNED: dict[tuple[str, str], Handler] = {
    ("GET", "user/check_features/"): check_features,
    ("GET", "user/mobile_state/"): read_mobile_state,
    ("PATCH", "user/mobile_state/"): write_mobile_state,
    ("GET", "check_in/redeemable/"): check_in.redeemable,
    ("GET", "check_in/attendees_by_product_with_quantity/{}/"): check_in.inventory,
    ("GET", "check_in/fetch_products/"): check_in.fetch_products,
    ("POST", "check_in/redeem_products/"): check_in.redeem,
    ("GET", "mask_violations/attendees/"): conduct.coc_attendees,
    ("GET", "mask_violations/capture/"): conduct.coc_scan,
    ("POST", "mask_violations/capture/"): conduct.coc_report,
    ("GET", "lead_retrieval/sponsors/"): leads.lead_sponsors,
    ("GET", "lead_retrieval/capture/"): leads.lead_capture,
    ("POST", "lead_retrieval/{}/note/"): leads.lead_note,
}
"""The signed endpoints by method and path under ``/<year>/api/v1/``; ``{}`` matches
one non-empty segment (Ionic's never-called ``attendees_by_product/<id>/`` is not served,
API-05)."""
