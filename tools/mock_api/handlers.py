"""The mock API's state and its pure request handler (D-50; contract in ``README.md``).

``handle`` takes a request as plain values and returns a reply as plain values: it does
no I/O and reads the time only from ``MockState.now``, so the tests drive it directly or
through ``transport.py``, and the LAN server wraps the same function. This module holds
the routing, the envelopes, the signature check and the account endpoints; the staff
endpoints follow in their own issue.
"""

import hmac
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from email.utils import formatdate
from pathlib import Path

from pycon_us.core.signing import canonical_body, sign

SEED = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mock" / "seed.json"
"""The seed every ``MockState`` starts from: fake accounts only."""

WINDOW = 600
"""Seconds a signed request's timestamp may be from the mock's clock (2019's value)."""

FLAGS = ("lead_retrieval", "door_check_in", "mask_violation")
"""The flags ``check_features`` returns; ``is_speaker`` only comes with ``authenticate``."""

type Reply = tuple[int, dict[str, str], bytes]
"""A reply: the status, the headers and the body bytes."""


@dataclass
class Account:
    """A seeded account, with what ``authenticate`` returns and the favourites it syncs.

    Attributes:
        role: What the account is for (``attendee``, ``speaker``, ``sponsor``,
            ``staff``, ``coc`` or ``all``); only the seed and the tests read it.
        email: The sign-in email.
        password: The sign-in password (fake).
        nickname: The name ``authenticate`` returns.
        key: The API key the client sends as ``X-API-Key`` (fake).
        secret: The API secret the client signs with (fake).
        features: The role flags as the server sends them; a flag left out is absent
            from every reply, which the client must read as False.
        favorites: The session ids ``mobile_state`` keeps, always strings (D-42).
        sponsor_id: The sponsor a lead-retrieval account's leads go to, or None.
    """

    role: str
    email: str
    password: str
    nickname: str
    key: str
    secret: str
    features: dict[str, bool]
    favorites: list[str] = field(default_factory=list)
    sponsor_id: int | None = None


@dataclass
class MockState:
    """Everything the mock remembers between requests, in memory.

    Attributes:
        year: The conference year served; requests for another year are 404.
        accounts: The accounts, looked up by email or by API key.
        now: The mock's clock, in seconds since the epoch. Tests inject a fixed one;
            the server can pass a skewed one.
    """

    year: int
    accounts: list[Account]
    now: Callable[[], float] = time.time

    @classmethod
    def from_seed(
        cls, path: Path = SEED, now: Callable[[], float] = time.time
    ) -> MockState:
        """Load a fresh state from a seed file in the README's shape.

        Args:
            path: The seed JSON file.
            now: The clock to use.

        Returns:
            A state that shares nothing with any other.
        """
        seed = json.loads(path.read_text(encoding="utf-8"))
        accounts = [Account(**entry) for entry in seed["accounts"]]
        return cls(year=seed["year"], accounts=accounts, now=now)


class Refused(Exception):
    """A request the mock answers with an error status.

    Attributes:
        status: The HTTP status.
        body: The error body, ``{"code", "error"}`` unless an endpoint says otherwise.
    """

    def __init__(self, status: int, message: str, body: object = None) -> None:
        """Create the refusal.

        Args:
            status: The HTTP status.
            message: What went wrong.
            body: The error body; None gives the 2019 shape ``{"code", "error"}``.
        """
        super().__init__(status, message)
        self.status = status
        self.body = {"code": status, "error": message} if body is None else body


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
        The status, the headers (``Content-Type`` and a ``Date`` from ``state.now``,
        which the client uses to learn clock skew, D-53) and the JSON body.
    """
    now = state.now()
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
        now: The time of this request, from ``state.now``.
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
    path = raw_path.partition("?")[0]
    endpoint = path.removeprefix(prefix) if path.startswith(prefix) else None
    if (method, endpoint) == ("POST", "authenticate/"):
        return authenticate(state, body)
    handler = SIGNED.get((method, endpoint))
    if handler is None:
        raise Refused(404, f"No route for {method} {path}.")
    account = verify(state, now, method, raw_path, headers, body)
    return handler(account, body)


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
        Refused: 401 for a missing or unknown key; 403 for a missing or malformed
            timestamp, one more than ``WINDOW`` seconds from ``now``, or a wrong
            signature.
    """
    lower = {name.lower(): value for name, value in headers.items()}
    key = lower.get("x-api-key")
    account = next((a for a in state.accounts if a.key == key), None)
    if key is None or account is None:
        raise Refused(401, "Unknown API key.")
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


def json_object(body: bytes) -> dict[str, object]:
    """Parse a request body that must be a JSON object.

    Args:
        body: The body bytes as sent.

    Returns:
        The object.

    Raises:
        Refused: 400 when the body is not UTF-8 JSON or not an object.
    """
    try:
        payload = json.loads(body)
    except ValueError:  # UnicodeDecodeError and JSONDecodeError are both ValueErrors
        payload = None
    if not isinstance(payload, dict):
        raise Refused(400, "The body must be a JSON object.")
    return payload


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


def check_features(account: Account, body: bytes) -> tuple[int, object]:
    """Return the account's role flags, absent ones left out (``user-data.ts`` 61-66).

    Args:
        account: The signed-in account.
        body: Unused.

    Returns:
        200 ``{"features": {...}}``, bare.
    """
    flags = {name: on for name, on in account.features.items() if name in FLAGS}
    return 200, {"features": flags}


def read_mobile_state(account: Account, body: bytes) -> tuple[int, object]:
    """Return the account's favourites (``user-data.ts`` 76-85).

    Args:
        account: The signed-in account.
        body: Unused.

    Returns:
        200 ``{"favorites": [...]}``, bare, ids as strings.
    """
    return 200, {"favorites": account.favorites}


def write_mobile_state(account: Account, body: bytes) -> tuple[int, object]:
    """Replace the account's favourites with the list sent (``pycon-api.ts`` 80-101).

    Ids are kept as strings (D-42); integer ids are accepted and stored as their
    decimal strings. Anything else is refused, floats included, so no id depends on
    how a float prints (``1.0`` in Python, ``1`` in JavaScript).

    Args:
        account: The signed-in account.
        body: ``{"favorites": [...]}``.

    Returns:
        200 with the list now stored, bare (Ionic ignores it).

    Raises:
        Refused: 400 unless ``favorites`` is a list of strings and integers, each
            encodable as UTF-8: a JSON escape can carry a lone surrogate, which no
            reply could then serialise.
    """
    favorites = json_object(body).get("favorites")
    if not isinstance(favorites, list) or not all(
        type(item) in (str, int) for item in favorites
    ):
        raise Refused(400, "favorites must be a list of ids.")
    ids = [str(item) for item in favorites]
    try:
        "".join(ids).encode()
    except UnicodeEncodeError:
        raise Refused(400, "favorites must be a list of ids.") from None
    account.favorites = ids
    return 200, {"favorites": account.favorites}


SIGNED: dict[tuple[str, str | None], Callable[[Account, bytes], tuple[int, object]]] = {
    ("GET", "user/check_features/"): check_features,
    ("GET", "user/mobile_state/"): read_mobile_state,
    ("PATCH", "user/mobile_state/"): write_mobile_state,
}
"""The signed endpoints by method and path under ``/<year>/api/v1/``."""
