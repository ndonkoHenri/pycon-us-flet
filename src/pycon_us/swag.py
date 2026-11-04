"""Swag pickup's lookup and hand-out (#768, #769; SHIRT-02..04, API-06, API-07).

`look_up()` is Swag pickup's `on_badge`. It asks `fetch_products` in swag mode for
the categories chosen and turns the reply into the result panel's answer: items left
to hand out, everything already picked up, or nothing bought. Swag pickup is online
only (D-56), so nothing is queued: no connection is a denial that says so, and a
reply that can't be used is never shown as "nothing to pick up" (D-120). The result
stays until the next scan (the scan screen keeps it), unlike Ionic's 1 s card.

With items left, `look_up()` hands an `Offer` to the screen's hand-out sheet
(`ui/swag_sheet.py`) and awaits it: the panel then says how the hand-out went, or
keeps "Ready to hand out" when it was cancelled. `hand_out()` sends the `redeem`
once, online; an answer lost or unreadable after the server may have applied it is
"Not confirmed" with the advice to rescan, never a resend: a second POST could hand out
twice under non-idempotent semantics (D-57, D-410).
"""

import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from pycon_us.check_in_api import fetch_attendee_products, redeem
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.check_in import (
    AttendeeProducts,
    Category,
    RedeemReply,
    redeem_payload,
)
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

PARTLY = "Partly handed out"
NOTHING_HANDED_OUT = "Nothing handed out"
NOT_HANDED_OUT = "Not handed out"
NOT_CONFIRMED = "Not confirmed"
"""A hand-out's words besides "Handed out 3 items" (ux.md §7.3)."""

MAY_BE_PICKED_UP = "Items may already be picked up."
NOTHING_RECORDED = "No connection. Nothing was recorded."
RESCAN = "Scan the badge again to see what's left before handing anything out."
"""A hand-out's detail lines: nothing redeemed, no answer, an answer lost (D-410)."""


@dataclass(frozen=True)
class Offer:
    """What a lookup offers to hand out: the sheet's content and the redeem's.

    Attributes:
        badge: The badge scanned: its code and validator go in the `redeem` body.
        scanned_at: When it was scanned, epoch seconds: the body's `scanned_at`.
        products: The attendee and what they bought in the categories chosen.
    """

    badge: Badge
    scanned_at: float
    products: AttendeeProducts

    @property
    def name(self) -> str:
        """The attendee's name, or the code without one."""
        return self.products.name or self.products.code

    @property
    def available(self) -> dict[int, int]:
        """How many of each product are left, by id, in the sheet's order."""
        return {
            item.product_id: item.redeemable
            for _, items in self.products.items_by_category
            for item in items
            if item.redeemable > 0
        }


type OfferHandler = Callable[[Offer], Awaitable[ScanResult | None]]
"""Shows the hand-out sheet; returns how the hand-out went, or None when cancelled."""


async def look_up(
    api: ApiClient | None,
    badge: Badge,
    *,
    categories: Sequence[Category],
    offer: OfferHandler | None = None,
    clock: Callable[[], float] = time.time,
) -> ScanResult:
    """Return what the attendee behind `badge` can still take in `categories`.

    Args:
        api: `Services.api`, signed in with the `door_check_in` flag; None when
            the mock URL has gone, which reads as no connection.
        badge: The badge scanned; its access code is looked up.
        categories: The categories chosen, at least one (the screen pauses without).
        offer: The hand-out sheet, given the items left; None only shows them.
        clock: The time of the scan, epoch seconds, the redeem's `scanned_at`.

    Returns:
        The result panel's answer: the hand-out's outcome, or, cancelled, accepted
        with a line per item left; a duplicate when everything bought is picked up,
        a denial when nothing was bought, the badge is unknown (404), there is no
        connection, or the call failed.
    """
    scanned_at = clock()
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
    result = result_of(products, categories)
    if offer is None or result.outcome is not ScanOutcome.ACCEPTED:
        return result
    handed = await offer(Offer(badge, scanned_at, products))
    return result if handed is None else handed


async def hand_out(
    api: ApiClient | None, offer: Offer, quantities: Mapping[int, int]
) -> ScanResult:
    """Redeem `quantities` for the attendee of `offer` now, once, and say how it went.

    Args:
        api: `Services.api`; None when the mock URL has gone: no connection.
        offer: The lookup's offer: the badge and the scan's time.
        quantities: How many of each product, by id, at least one product.

    Returns:
        The result panel's answer (ux.md §7.3): accepted, partly (a duplicate),
        nothing redeemed, no connection, not confirmed (the answer lost or unreadable,
        D-410) or the server's refusal (all denied).
    """
    badge = offer.badge
    payload = redeem_payload(
        badge.code, badge.door_validator, offer.scanned_at, quantities, swag=True
    )
    try:
        if api is None:  # the URL went meanwhile: nothing was sent
            raise NetworkError("no mock client")
        reply = await redeem(api, payload)
    except NetworkError as error:
        if error.maybe_sent:
            return denied(NOT_CONFIRMED, offer.name, RESCAN, code=badge.code)
        return denied(NOT_HANDED_OUT, offer.name, NOTHING_RECORDED, code=badge.code)
    except ApiError as error:
        if error.unreadable:
            return denied(NOT_CONFIRMED, offer.name, RESCAN, code=badge.code)
        return denied(NOT_HANDED_OUT, offer.name, error.message, code=badge.code)
    return redeemed(reply, offer, quantities)


def redeemed(
    reply: RedeemReply, offer: Offer, quantities: Mapping[int, int]
) -> ScanResult:
    """Return the answer for a `redeem` reply: all, part or nothing handed out.

    Args:
        reply: What the server redeemed and its messages.
        offer: The lookup's offer, for the name and the code.
        quantities: What was asked for, to count the items handed out.
    """
    code = offer.badge.code
    count = sum(quantities.get(i, 0) for i in set(reply.redeemed))
    if not reply.redeemed:
        details = reply.errors or (MAY_BE_PICKED_UP,)
        return ScanResult(
            ScanOutcome.DENIED, NOTHING_HANDED_OUT, offer.name, details, code
        )
    if reply.errors:
        return ScanResult(ScanOutcome.DUPLICATE, PARTLY, offer.name, reply.errors, code)
    word = f"Handed out {items(count)}"
    return ScanResult(ScanOutcome.ACCEPTED, word, offer.name, (), code)


def items(count: int) -> str:
    """Return a count of items as said: "1 item", "3 items"."""
    return f"{count} item" if count == 1 else f"{count} items"


def result_of(products: AttendeeProducts, categories: Sequence[Category]) -> ScanResult:
    """Return the answer for a lookup's reply (ux.md §7.3's Swag pickup).

    Args:
        products: The attendee and what they bought in `categories`.
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


def denied(
    word: str, title: str, detail: str, *, code: str | None = None
) -> ScanResult:
    """Return a denial: its word, the title, one line of detail and the code.

    Args:
        word: The outcome's word.
        title: The name, or the code when there is none.
        detail: The line under it; none when empty.
        code: The access code, when `title` is a name; else `title` is the code.
    """
    lines = (detail,) if detail else ()
    return ScanResult(ScanOutcome.DENIED, word, title, lines, code or title)


def spoken_list(names: Sequence[str]) -> str:
    """Return names as said: "T-Shirt", "T-Shirt or Swag Bag", "A, B or C"."""
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} or {names[-1]}"
