"""The mock's check-in endpoints: door check and swag pickup (API-05..API-07, D-57).

Every endpoint here needs the `door_check_in` flag. Replies are bare, as Ionic reads
them (`tools/mock_api/README.md`, Replies); what a redemption applies is recorded in
`MockState.redemptions`.
"""

import re

from tools.mock_api.parse import ids, json_object, raw_query, text
from tools.mock_api.state import Attendee, Call, Product, Redemption, Refused

DOOR = "door_check_in"
"""The flag every check-in endpoint needs."""

REDEEM_KEY = re.compile(r"product-redeem-(\d{1,9})")
"""A redeem payload's `product-redeem-<id>` key."""


def redeemable(call: Call) -> tuple[int, object]:
    """List every category and product (`pycon-api.ts` 103-117).

    The door page keeps the categories whose names don't match `/shirt|swag/i`, the
    swag page the others; the mock sends them all.

    Returns:
        200 `{"redeemable_categories", "redeemable_products"}`, bare.
    """
    call.require(DOOR)
    state = call.state
    return 200, {
        "redeemable_categories": [
            {"id": c.id, "name": c.name} for c in state.categories
        ],
        "redeemable_products": [
            {"id": p.id, "name": p.name, "category": p.category}
            for p in state.products.values()
        ],
    }


def inventory(call: Call) -> tuple[int, object]:
    """List who bought a product, for the door's offline admission (135-149).

    `quantity` is the quantity bought, not what is left: the door admits on it and
    keeps its own "already checked in" record (a mock choice).

    Returns:
        200 with a bare list `[{id (the access code), quantity, name, dietary,
        has_allergy, allergy}]`.

    Raises:
        Refused: 404 for an unknown product.
    """
    call.require(DOOR)
    pid = call.segment
    if not (pid.isascii() and pid.isdigit() and len(pid) < 10):
        raise Refused(404, "Unknown product.")
    product = call.state.product(int(pid))
    return 200, [
        {
            "id": a.access_code,
            "quantity": a.products[product.id],
            "name": a.full_name,
            "dietary": a.dietary,
            "has_allergy": a.has_allergy,
            "allergy": a.allergy,
        }
        for a in call.state.attendees.values()
        if a.products.get(product.id, 0) > 0
    ]


def fetch_products(call: Call) -> tuple[int, object]:
    """What an attendee can still redeem, for swag or the door (151-181).

    The query is parsed as Ionic sends it, not encoded: `attendee_access_code`,
    `mode` and either `category_pk_list` (swag) or `product_pk_list` (door).

    Returns:
        200 with the attendee and `redeemable_products_by_category`, bare; the door
        mode adds `dietary`, `has_allergy` and `allergy`.

    Raises:
        Refused: 400 for a missing parameter or an unknown mode; 404 for an unknown
            attendee, product or category.
    """
    call.require(DOOR)
    state = call.state
    params = raw_query(call.query)
    attendee = state.attendee(text(params, "attendee_access_code"))
    mode = params.get("mode")
    if mode not in ("redemption_mode", "door_check_mode"):
        raise Refused(400, "mode must be redemption_mode or door_check_mode.")
    if "product_pk_list" in params:
        products = [
            state.product(pid)
            for pid in ids(params["product_pk_list"], "product_pk_list")
        ]
    else:
        wanted = ids(text(params, "category_pk_list"), "category_pk_list")
        if not set(wanted) <= {c.id for c in state.categories}:
            raise Refused(404, "Unknown category.")
        products = [p for p in state.products.values() if p.category in wanted]
    by_category = grouped(call, attendee, products)
    reply: dict[str, object] = {
        "attendee_access_code": attendee.access_code,
        "attendee_name": attendee.full_name,
        "attendee_id": attendee.id,
        "has_items_to_redeem": any(
            item["redeemable"] for items in by_category.values() for item in items
        ),
        "redeemable_products_by_category": by_category,
    }
    if mode == "door_check_mode":
        reply |= {
            "dietary": attendee.dietary,
            "has_allergy": attendee.has_allergy,
            "allergy": attendee.allergy,
        }
    return 200, reply


def grouped(
    call: Call, attendee: Attendee, products: list[Product]
) -> dict[str, list[dict[str, object]]]:
    """Group the products an attendee bought by category name, with what is left.

    Args:
        call: The request, for its state.
        attendee: The attendee.
        products: The products to list; those not bought are left out.

    Returns:
        `{"<category name>": [{product_id, product_name, redeemable, purchased}]}`.
    """
    by_category: dict[str, list[dict[str, object]]] = {}
    for product in products:
        purchased = attendee.products.get(product.id, 0)
        if purchased == 0:
            continue
        left = purchased - call.state.redeemed(attendee.access_code, product.id)
        by_category.setdefault(call.state.category_name(product), []).append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "redeemable": left,
                "purchased": purchased,
            }
        )
    return by_category


def redeem(call: Call) -> tuple[int, object]:
    """Redeem products for an attendee, from the door or the swag page (183-199).

    The payload's `product-redeem-<id>` keys name the products (the id as a number
    from the door, as a string from swag) and `product-<id>-quantity` how many. A
    non-empty `badge_validator` is checked; the door omits a missing one and swag
    sends `""`. Under `idempotent` capture, a repeated request (same attendee,
    `scanned_at`, products and quantities) gets its first reply and records nothing,
    and a product already redeemed with the same `scanned_at` is answered as
    redeemed again and recorded once (D-57).

    Returns:
        200 `{"errors": [{message}], "redeemable_products_by_category"}`, bare: the
        products this call redeemed, with what is left of each.

    Raises:
        Refused: 400 for a malformed payload; 404 for an unknown attendee or product,
            or a wrong validator.
    """
    call.require(DOOR)
    state = call.state
    payload = json_object(call.body)
    validator = payload.get("badge_validator", "")
    if not isinstance(validator, str):
        raise Refused(400, "badge_validator must be a string.")
    attendee = state.attendee(payload.get("attendee_access_code"), validator or None)
    scanned_at = text(payload, "scanned_at")
    asked = requested(call, payload)
    key = (attendee.access_code, scanned_at, tuple((p.id, q) for p, q in asked))
    if state.capture == "idempotent" and key in state.redeem_replies:
        return 200, state.redeem_replies[key]
    errors: list[dict[str, str]] = []
    done: list[Product] = []
    for product, quantity in asked:
        repeat = Redemption(attendee.access_code, product.id, quantity, scanned_at)
        if state.capture == "idempotent" and repeat in state.redemptions:
            done.append(product)
            continue
        purchased = attendee.products.get(product.id, 0)
        left = purchased - state.redeemed(attendee.access_code, product.id)
        if purchased == 0:
            errors.append({"message": f"{product.name} was not purchased."})
        elif left == 0:
            errors.append({"message": f"{product.name} was already redeemed."})
        elif quantity > left:
            errors.append({"message": f"{product.name}: only {left} left to redeem."})
        else:
            state.redemptions.append(repeat)
            done.append(product)
    reply = {
        "errors": errors,
        "redeemable_products_by_category": grouped(call, attendee, done),
    }
    if state.capture == "idempotent":
        # The snapshot, not today's inventory: a retry after later redemptions still
        # gets the answer the lost response carried (README, Open questions).
        state.redeem_replies[key] = reply
    return 200, reply


def requested(call: Call, payload: dict[str, object]) -> list[tuple[Product, int]]:
    """Read the products and quantities from a redeem payload, in payload order.

    Args:
        call: The request, for its state.
        payload: The redeem payload.

    Returns:
        Each product with the quantity asked for.

    Raises:
        Refused: 400 when a `product-redeem-<id>` value isn't its id (a number or
            its string) or its quantity isn't a positive integer; 404 for an unknown
            product.
    """
    asked: list[tuple[Product, int]] = []
    for key, value in payload.items():
        match = REDEEM_KEY.fullmatch(key)
        if match is None:
            continue
        pid = match[1]
        quantity = payload.get(f"product-{pid}-quantity")
        if str(value) != pid or type(value) not in (int, str):
            raise Refused(400, "product-redeem-<id> must be its id.")
        if type(quantity) is not int or quantity < 1:
            raise Refused(400, "product-<id>-quantity must be a positive integer.")
        asked.append((call.state.product(int(pid)), quantity))
    return asked
