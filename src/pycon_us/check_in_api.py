"""The check-in calls Door check and Swag pickup send, read by `core/check_in.py` (#763).

Thin: each sends one call through `ApiClient` and reads its reply, and a reply that
can't be read is an `ApiError` (D-120). `redeem()` is for Swag pickup's online
hand-out only: the door's redeem bodies go through the outbox
(`core/outbox_enqueue.admit()`) and the `SyncWorker` sends them (D-56, D-407).
"""

from collections.abc import Iterable

from pycon_us.core.check_in import (
    AttendeeProducts,
    Catalog,
    RedeemReply,
    parse_attendee_products,
    parse_catalog,
    parse_redeem_reply,
)
from pycon_us.services.api import ApiClient, ApiError
from pycon_us.services.endpoints import (
    FETCH_PRODUCTS,
    REDEEM,
    REDEEMABLE,
    fetch_products_query,
)


async def fetch_catalog(api: ApiClient) -> Catalog:
    """Return every redeemable category and product (API-05).

    Args:
        api: `Services.api`, signed in with the `door_check_in` flag.

    Returns:
        The whole catalog; `door_catalog()` and `swag_catalog()` split it.

    Raises:
        NetworkError: No answer arrived.
        ApiError: The mock refused the call, or its reply could not be read.
    """
    reply = await api.request(REDEEMABLE)
    try:
        return parse_catalog(reply)
    except TypeError as error:
        raise ApiError(None, str(error)) from None


async def fetch_attendee_products(
    api: ApiClient, code: str, ids: Iterable[int], *, door: bool
) -> AttendeeProducts:
    """Return what an attendee bought among some products or categories (API-06).

    Args:
        api: `Services.api`, signed in with the `door_check_in` flag.
        code: The attendee's access code.
        ids: The door's product ids, or Swag pickup's category ids.
        door: True for the door's lookup, False for Swag pickup's.

    Returns:
        The attendee and their items.

    Raises:
        NetworkError: No answer arrived.
        ApiError: The mock refused the call (404 for an unknown attendee), or its
            reply could not be read.
    """
    query = fetch_products_query(code, ids, door=door)
    reply = await api.request(FETCH_PRODUCTS, query=query)
    try:
        return parse_attendee_products(reply)
    except TypeError as error:
        raise ApiError(None, str(error)) from None


async def redeem(api: ApiClient, payload: dict[str, object]) -> RedeemReply:
    """Send a `redeem` body now, for Swag pickup's online hand-out (API-07, SHIRT-04).

    Args:
        api: `Services.api`, signed in with the `door_check_in` flag.
        payload: The body, from `redeem_payload(..., swag=True)`.

    Returns:
        What the call redeemed and the server's errors.

    Raises:
        NetworkError: No answer arrived; `maybe_sent` says whether it may have been
            applied all the same (D-410).
        ApiError: The mock refused the call, or its reply could not be read
            (`unreadable`), so it may have been applied all the same.
    """
    reply = await api.request(REDEEM, payload=payload)
    try:
        return parse_redeem_reply(reply)
    except TypeError as error:
        raise ApiError(None, str(error)) from None
