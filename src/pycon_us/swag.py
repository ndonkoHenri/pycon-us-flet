"""Swag pickup's lookup: what a badge's attendee can still take (#768; SHIRT-02, API-06).

``look_up()`` is Swag pickup's ``on_badge``. It asks ``fetch_products`` in swag mode for
the categories chosen and turns the reply into the result panel's answer: items left
to hand out, everything already picked up, or nothing bought. Swag pickup is online
only (D-56), so nothing is queued: no connection is a denial that says so, and a
reply that can't be used is never shown as "nothing to pick up" (D-120). The result
stays until the next scan (the scan screen keeps it), unlike Ionic's 1 s card.
"""

from collections.abc import Sequence

from pycon_us.check_in_api import fetch_attendee_products
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.check_in import AttendeeProducts, Category
from pycon_us.services.api import ApiClient, ApiError, NetworkError

READY = "Ready to hand out"
ALREADY = "Already picked up"
NOTHING = "Nothing to pick up"
NOT_FOUND = "Badge not found"
NO_CONNECTION = "No connection"
NOT_CHECKED = "Couldn't check this badge"
"""Each outcome's word (ux.md §7.3)."""

NEEDS_CONNECTION = "Swag pickup needs a connection. Scan again when online."
"""The detail under "No connection": nothing was queued (D-56)."""


async def look_up(
    api: ApiClient | None, badge: Badge, *, categories: Sequence[Category]
) -> ScanResult:
    """Return what the attendee behind ``badge`` can still take in ``categories``.

    Args:
        api: ``Services.api``, signed in with the ``door_check_in`` flag; None when
            the mock URL has gone, which reads as no connection.
        badge: The badge scanned; its access code is looked up.
        categories: The categories chosen, at least one (the screen pauses without).

    Returns:
        The result panel's answer: accepted with a line per item left, a duplicate
        when everything bought is picked up, a denial when nothing was bought, the
        badge is unknown (404), there is no connection, or the call failed.
    """
    try:
        if api is None:  # the URL went meanwhile; the screen's guard follows
            raise NetworkError("no mock client")
        products = await fetch_attendee_products(
            api, badge.code, [c.id for c in categories], door=False
        )
    except NetworkError:
        return denied(NO_CONNECTION, badge.code, NEEDS_CONNECTION)
    except ApiError as error:
        word = NOT_FOUND if error.status == 404 else NOT_CHECKED
        return denied(word, badge.code, error.message)
    return result_of(products, categories)


def result_of(products: AttendeeProducts, categories: Sequence[Category]) -> ScanResult:
    """Return the answer for a lookup's reply (ux.md §7.3's Swag pickup).

    Args:
        products: The attendee and what they bought in ``categories``.
        categories: The categories asked about, named when nothing was bought.
    """
    name = products.name or products.code
    items = [item for _, group in products.items_by_category for item in group]
    left = tuple(f"{i.redeemable}× {i.name}" for i in items if i.redeemable > 0)
    if left:
        return ScanResult(ScanOutcome.ACCEPTED, READY, name, left, products.code)
    if items:
        return ScanResult(ScanOutcome.DUPLICATE, ALREADY, name, (), products.code)
    checked = f"None bought in {spoken_list([c.name for c in categories])}."
    return ScanResult(ScanOutcome.DENIED, NOTHING, name, (checked,), products.code)


def denied(word: str, code: str, detail: str) -> ScanResult:
    """Return a denial about ``code``: its word, the code and one line of detail."""
    return ScanResult(ScanOutcome.DENIED, word, code, (detail,) if detail else (), code)


def spoken_list(names: Sequence[str]) -> str:
    """Return names as said: "T-Shirt", "T-Shirt or Swag Bag", "A, B or C"."""
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} or {names[-1]}"
