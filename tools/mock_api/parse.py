"""How the mock reads what a request sends: JSON bodies, queries and ids (D-50).

Each endpoint reads its query the way Ionic builds it: `fetch_products` raw, the CoC
and lead captures percent-decoded (`tools/mock_api/README.md`, Endpoints). Anything
malformed is a 400 in the error envelope.
"""

import json
from collections.abc import Mapping
from urllib.parse import parse_qsl

from tools.mock_api.state import Refused


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
    except ValueError, RecursionError:  # not UTF-8, not JSON, or nested too deep
        payload = None
    if not isinstance(payload, dict):
        raise Refused(400, "The body must be a JSON object.")
    return payload


def raw_query(query: str) -> dict[str, str]:
    """Split a query Ionic sends unencoded (`fetch_products`), decoding nothing.

    Args:
        query: The query as sent.

    Returns:
        Each name's first value, exactly as sent.
    """
    params: dict[str, str] = {}
    for pair in query.split("&"):
        name, _, value = pair.partition("=")
        params.setdefault(name, value)
    return params


def encoded_query(query: str) -> dict[str, str]:
    """Decode a query Ionic builds with `encodeURIComponent` (CoC, lead capture).

    Args:
        query: The query as sent.

    Returns:
        Each name's first value, percent-decoded.
    """
    params: dict[str, str] = {}
    for name, value in parse_qsl(query, keep_blank_values=True):
        params.setdefault(name, value)
    return params


def text(params: Mapping[str, object], name: str) -> str:
    """Read a required string from a query or a body.

    Raises:
        Refused: 400 when it is missing or not a string.
    """
    value = params.get(name)
    if not isinstance(value, str):
        raise Refused(400, f"{name} is required.")
    return value


def ids(value: str, name: str) -> list[int]:
    """Parse a comma-separated list of ids as Ionic joins them (`a,b`).

    Raises:
        Refused: 400 unless every item is a decimal id.
    """
    try:
        # isdigit() first: int() would also take "+1", " 1" and "1_0".
        if all(item.isascii() and item.isdigit() for item in value.split(",")):
            return [int(item) for item in value.split(",")]
    except ValueError:  # past int()'s digit limit
        pass
    raise Refused(400, f"{name} must be a comma-separated list of ids.")
