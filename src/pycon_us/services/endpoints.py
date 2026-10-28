"""The private API's calls as Ionic's ``pycon-api.ts`` makes them (D-52, D-53, API-12).

Each ``Endpoint`` constant is one call: its method, path, timeout and whether it is signed
or enveloped; ``ENDPOINTS`` lists every call the app makes, which
``tests/test_api_endpoints.py`` checks against ``tools/mock_api/README.md`` and the mock's
routes. The query builders encode each query exactly as Ionic did, since the signature
covers it byte for byte. ``services/api.py``'s ``ApiClient.request`` sends them.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from pycon_us.core.signing import enc


@dataclass(frozen=True)
class Endpoint:
    """One call of the private API, as Ionic's ``pycon-api.ts`` makes it.

    Attributes:
        name: The call's name in ``tools/mock_api/README.md``.
        method: The HTTP method, upper case.
        path: The path under ``/<year>/api/v1/``; each ``{}`` is one path segment that
            ``ApiClient.request`` fills from its arguments.
        timeout: Ionic's timeout in seconds (here for connect, each read and the pool).
        signed: Whether the request carries the ``X-API-*`` headers; only
            ``authenticate`` doesn't.
        enveloped: Whether a reply is ``{"code", "data"}`` and the caller wants the
            ``data``; Ionic reads every other reply bare.
    """

    name: str
    method: str
    path: str
    timeout: float
    signed: bool = True
    enveloped: bool = False


AUTHENTICATE = Endpoint("authenticate", "POST", "authenticate/", 3, signed=False)
CHECK_FEATURES = Endpoint("check_features", "GET", "user/check_features/", 2)
READ_MOBILE_STATE = Endpoint("mobile_state", "GET", "user/mobile_state/", 2)
WRITE_MOBILE_STATE = Endpoint("mobile_state", "PATCH", "user/mobile_state/", 2)
REDEEMABLE = Endpoint("redeemable", "GET", "check_in/redeemable/", 2)
INVENTORY = Endpoint(
    "inventory", "GET", "check_in/attendees_by_product_with_quantity/{}/", 20
)
FETCH_PRODUCTS = Endpoint("fetch_products", "GET", "check_in/fetch_products/", 10)
REDEEM = Endpoint("redeem", "POST", "check_in/redeem_products/", 10)
COC_ATTENDEES = Endpoint(
    "coc_attendees", "GET", "mask_violations/attendees/", 15, enveloped=True
)
COC_SCAN = Endpoint("coc_capture", "GET", "mask_violations/capture/", 5, enveloped=True)
COC_REPORT = Endpoint(
    "coc_capture", "POST", "mask_violations/capture/", 5, enveloped=True
)
LEAD_SPONSORS = Endpoint("lead_sponsors", "GET", "lead_retrieval/sponsors/", 5)
LEAD_CAPTURE = Endpoint(
    "lead_capture", "GET", "lead_retrieval/capture/", 2, enveloped=True
)
LEAD_NOTE = Endpoint("lead_note", "POST", "lead_retrieval/{}/note/", 2)

ENDPOINTS = (
    AUTHENTICATE, CHECK_FEATURES, READ_MOBILE_STATE, WRITE_MOBILE_STATE, REDEEMABLE,
    INVENTORY, FETCH_PRODUCTS, REDEEM, COC_ATTENDEES, COC_SCAN, COC_REPORT,
    LEAD_SPONSORS, LEAD_CAPTURE, LEAD_NOTE,
)  # fmt: skip
"""Every call the app makes. Ionic's ``attendees_by_product/<id>/`` is never called, so
it is not ported (API-05)."""


def fetch_products_query(code: str, ids: Iterable[int | str], *, door: bool) -> str:
    """Build ``fetch_products``' query as Ionic does, encoding nothing (153, 169).

    Args:
        code: The attendee's access code, interpolated raw.
        ids: The door's product ids, or the swag page's category ids.
        door: True for the door (``product_pk_list``, ``door_check_mode``), False for
            swag pickup (``category_pk_list``, ``redemption_mode``).

    Returns:
        The query, without its ``?``.
    """
    name, mode = (
        ("product_pk_list", "door_check_mode")
        if door
        else ("category_pk_list", "redemption_mode")
    )
    joined = ",".join(str(i) for i in ids)
    return f"attendee_access_code={code}&{name}={joined}&mode={mode}"


def coc_capture_query(code: str) -> str:
    """Build the Code of Conduct scan's query, encoded as Ionic does (224).

    Args:
        code: The attendee's access code.

    Returns:
        The query, without its ``?``.
    """
    return f"attendee_access_code={enc(code)}"


def lead_capture_query(code: str, validator: str, sponsor_id: str | None = None) -> str:
    """Build the lead capture's query, every value encoded as Ionic does (298-301).

    Args:
        code: The attendee's access code.
        validator: The badge's validator.
        sponsor_id: The sponsor a staff member scans for, or None from a sponsor's own
            account, which sends none.

    Returns:
        The query, without its ``?``.
    """
    query = f"attendee_access_code={enc(code)}&badge_validator={enc(validator)}"
    return query if sponsor_id is None else f"{query}&sponsor_id={enc(sponsor_id)}"
