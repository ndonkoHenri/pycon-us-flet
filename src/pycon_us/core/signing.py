"""Request signing, byte-compatible with Ionic's ``buildRequestAuthHeaders`` (D-52).

Ionic signs a request with the hex SHA-1 (not an HMAC) of
``secret + timestamp + METHOD + path_with_query + body`` joined with no separator, where
the timestamp is ``Math.round(Date.now() / 1000)`` and the body is ``JSON.stringify`` of
the payload. The client and the mock server share this module, so vectors produced by
Ionic's own code (``tests/fixtures/ionic/signing.json``) are what keeps both honest.
"""

import hashlib
import json
import math
from urllib.parse import quote

JS_COMPONENT_SAFE = "!*'()~"
"""What ``encodeURIComponent`` keeps besides letters, digits and ``-_.``."""


def canonical_body(payload: object) -> bytes:
    """Serialise a payload as ``JSON.stringify`` does, as UTF-8.

    Compact, in insertion order, non-ASCII kept as it is. Serialise once and send
    exactly these bytes: the signature covers them.

    Args:
        payload: A JSON-compatible value whose dict keys are strings.

    Returns:
        The body bytes to sign and send.
    """
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def js_round(x: float) -> int:
    """Round as JavaScript's ``Math.round`` does: halves go up, never to even.

    Python's ``round`` rounds 0.5 to the nearest even integer, so ``round(2.5)`` is 2
    where ``Math.round(2.5)`` is 3. ``x - floor(x)`` is exact for any finite float, so
    this avoids the error ``floor(x + 0.5)`` makes just below a half.

    Args:
        x: A finite number.

    Returns:
        The integer JavaScript would give.
    """
    floor = math.floor(x)
    return floor + 1 if x - floor >= 0.5 else floor


def sign(
    secret: str, timestamp: int, method: str, path_with_query: str, body: bytes = b""
) -> str:
    """Compute Ionic's request signature.

    Args:
        secret: The account's API secret (Ionic signs a missing one as ``""``).
        timestamp: Seconds since the epoch, from `js_round`.
        method: The HTTP method, upper case as Ionic sends it.
        path_with_query: The path and query exactly as requested, encoded or not as
            that endpoint's Ionic call encodes it.
        body: The body bytes as sent; empty for a GET.

    Returns:
        The lowercase hex SHA-1 of the parts joined with no separator.
    """
    head = f"{secret}{timestamp}{method}{path_with_query}".encode()
    return hashlib.sha1(head + body).hexdigest()


def auth_headers(
    key: str,
    secret: str,
    now: float,
    method: str,
    path_with_query: str,
    body: bytes = b"",
) -> dict[str, str]:
    """Build the three headers of a signed request, as ``buildRequestAuthHeaders`` does.

    Args:
        key: The account's API key.
        secret: The account's API secret.
        now: The current time in seconds since the epoch (``time.time()``).
        method: The HTTP method, upper case.
        path_with_query: The path and query exactly as requested.
        body: The body bytes as sent; empty for a GET.

    Returns:
        ``X-API-Key``, ``X-API-Signature`` and ``X-API-Timestamp``.
    """
    timestamp = js_round(now)
    return {
        "X-API-Key": key,
        "X-API-Signature": sign(secret, timestamp, method, path_with_query, body),
        "X-API-Timestamp": str(timestamp),
    }


def enc(value: str) -> str:
    """Percent-encode a query value as JavaScript's ``encodeURIComponent`` does.

    Args:
        value: The raw value.

    Returns:
        The value as UTF-8 percent-escapes, except letters, digits and ``-_.!~*'()``.
    """
    return quote(value, safe=JS_COMPONENT_SAFE)
