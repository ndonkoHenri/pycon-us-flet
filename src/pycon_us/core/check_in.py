"""The check-in API's payloads, read and written for Door check and Swag pickup (#763).

Both tools read the same calls (``tools/mock_api/README.md``): ``redeemable``'s catalog
(API-05), which each splits by category name, Ionic's ``/shirt|swag/i`` (DOOR-01,
SHIRT-01); ``fetch_products``' attendee lookup (API-06); and the ``redeem`` body and its
reply (API-07). Everything here is pure: ``check_in_api.py`` sends the calls, and the
door's redeem bodies go through the outbox as built here (D-56, D-407).

A reply that isn't the documented object is a ``TypeError``, which the fetches turn
into an ``ApiError`` (D-120); a malformed entry inside a good reply is left out, so one
bad row never hides the others. Ids are integers; a decimal string is read as one.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

_SWAG = re.compile("shirt|swag", re.IGNORECASE)
"""Ionic's split: a category whose name matches is Swag pickup's, any other the door's."""


@dataclass(frozen=True)
class Category:
    """A redeemable category: a kind of session for the door, or a kind of swag.

    Attributes:
        id: Its id, what ``fetch_products`` takes in swag mode.
        name: Its name, which says whose it is (``is_swag()``).
    """

    id: int
    name: str


@dataclass(frozen=True)
class Product:
    """A redeemable product: a session at the door, a shirt size or a bag at swag.

    Attributes:
        id: Its id, what the door's ``fetch_products`` and ``redeem`` take.
        name: Its name; a session's starts with its date
            (``door_sessions.product_sort_key()``).
        category: Its category's id.
    """

    id: int
    name: str
    category: int


@dataclass(frozen=True)
class Catalog:
    """The ``redeemable`` reply, read: the categories and their products, as sent.

    Attributes:
        categories: The categories.
        products: The products, each in one of ``categories``.
    """

    categories: tuple[Category, ...]
    products: tuple[Product, ...]


def parse_catalog(reply: object) -> Catalog:
    """Read the ``redeemable`` reply (API-05).

    An entry without a usable id or name, a second entry with an id already read and
    a product whose category isn't listed are left out.

    Args:
        reply: The decoded reply.

    Returns:
        The catalog, in the reply's order.

    Raises:
        TypeError: The reply is not ``{"redeemable_categories": [...],
            "redeemable_products": [...]}``.
    """
    raw_categories = _member(reply, "redeemable_categories", list)
    raw_products = _member(reply, "redeemable_products", list)
    categories: dict[int, Category] = {}
    for entry in raw_categories:
        ident, name = _id_and_name(entry, "id", "name")
        if ident is not None and name and ident not in categories:
            categories[ident] = Category(ident, name)
    products: dict[int, Product] = {}
    for entry in raw_products:
        ident, name = _id_and_name(entry, "id", "name")
        category = _id(entry.get("category")) if isinstance(entry, dict) else None
        if ident is None or not name or ident in products or category not in categories:
            continue
        products[ident] = Product(ident, name, category)
    return Catalog(tuple(categories.values()), tuple(products.values()))


def is_swag(name: str) -> bool:
    """Return whether the category ``name`` is Swag pickup's (``/shirt|swag/i``)."""
    return _SWAG.search(name) is not None


def door_catalog(catalog: Catalog) -> Catalog:
    """Return the catalog's categories that aren't swag, with their products."""
    return _part(catalog, swag=False)


def swag_catalog(catalog: Catalog) -> Catalog:
    """Return the catalog's swag categories, with their products."""
    return _part(catalog, swag=True)


def _part(catalog: Catalog, *, swag: bool) -> Catalog:
    """Return the categories whose ``is_swag()`` is ``swag``, with their products."""
    categories = tuple(c for c in catalog.categories if is_swag(c.name) == swag)
    kept = {c.id for c in categories}
    return Catalog(categories, tuple(p for p in catalog.products if p.category in kept))


@dataclass(frozen=True)
class Item:
    """A product an attendee bought, from ``fetch_products``.

    Attributes:
        product_id: The product's id.
        name: The product's name.
        redeemable: How many are left to redeem.
        purchased: How many were bought.
    """

    product_id: int
    name: str
    redeemable: int
    purchased: int


@dataclass(frozen=True)
class AttendeeProducts:
    """The ``fetch_products`` reply, read: an attendee and what they bought.

    Attributes:
        code: The attendee's access code.
        name: The attendee's name ("" without one).
        attendee_id: The attendee's id, or None without a usable one.
        items_by_category: Each category's name and its items, by name in alphabetical
            order, as Ionic's ``keyvalue`` pipe showed them.
        dietary: The door's dietary note, or None (swag mode sends none).
        has_allergy: The door's allergy flag, or None.
        allergy: The door's allergy note, or None.
    """

    code: str
    name: str
    attendee_id: int | None
    items_by_category: tuple[tuple[str, tuple[Item, ...]], ...]
    dietary: str | None = None
    has_allergy: bool | None = None
    allergy: str | None = None


def parse_attendee_products(reply: object) -> AttendeeProducts:
    """Read the ``fetch_products`` reply, in door or swag mode (API-06).

    An item without a usable id, name or counts is left out, and so is a category
    left without items; the door's fields are None when absent or of the wrong type.

    Args:
        reply: The decoded reply.

    Returns:
        The attendee and their items.

    Raises:
        TypeError: The reply has no ``attendee_access_code`` string or no
            ``redeemable_products_by_category`` object.
    """
    code = _member(reply, "attendee_access_code", str)
    by_category = _member(reply, "redeemable_products_by_category", dict)
    reply = _object(reply)
    groups = ((name, _items(entries)) for name, entries in sorted(by_category.items()))
    name = reply.get("attendee_name")
    has_allergy = reply.get("has_allergy")
    return AttendeeProducts(
        code,
        name if isinstance(name, str) else "",
        _id(reply.get("attendee_id")),
        tuple((name, items) for name, items in groups if items),
        _optional_text(reply.get("dietary")),
        has_allergy if isinstance(has_allergy, bool) else None,
        _optional_text(reply.get("allergy")),
    )


def _items(entries: object) -> tuple[Item, ...]:
    """Return a category's usable items, in the reply's order."""
    if not isinstance(entries, list):
        return ()
    items = []
    for entry in entries:
        ident, name = _id_and_name(entry, "product_id", "product_name")
        if ident is None or not name or not isinstance(entry, dict):
            continue
        redeemable, purchased = _count(entry, "redeemable"), _count(entry, "purchased")
        if redeemable is not None and purchased is not None:
            items.append(Item(ident, name, redeemable, purchased))
    return tuple(items)


def redeem_payload(
    code: str,
    validator: str | None,
    scanned_at: float,
    quantities: Mapping[int, int],
    *,
    swag: bool,
) -> dict[str, object]:
    """Build the ``redeem`` body as Ionic's page sends it; its key order is signed (API-07).

    ``attendee_access_code``, ``badge_validator`` and ``scanned_at``, then a
    ``product-redeem-<id>`` and ``product-<id>-quantity`` pair per product. The door
    (``door-check.page.ts`` 177-188) sends each id as a number and leaves out a
    validator a badge without ``:`` lacks (None); swag (``t-shirt-redemption.page.ts``
    153-165) sends each id as a string and ``""`` for a missing validator.

    Args:
        code: The attendee's access code.
        validator: The badge's validator (``Badge.door_validator``), or None.
        scanned_at: When the badge was scanned, in epoch seconds; sent as
            ``Date.toISOString()`` writes it, UTC to the millisecond.
        quantities: How many of each product, by id, in the order to send.
        swag: True for Swag pickup, False for the door.

    Returns:
        The body, for ``canonical_body()`` or an outbox row.

    Raises:
        ValueError: A quantity is not a positive integer, which the server refuses.
    """
    stamp = datetime.fromtimestamp(scanned_at, UTC).isoformat(timespec="milliseconds")
    payload: dict[str, object] = {"attendee_access_code": code}
    if validator is not None or swag:
        payload["badge_validator"] = validator or ""
    payload["scanned_at"] = stamp.replace("+00:00", "Z")
    for product_id, quantity in quantities.items():
        if type(quantity) is not int or quantity < 1:
            raise ValueError(f"product {product_id}: quantity must be positive")
        payload[f"product-redeem-{product_id}"] = (
            str(product_id) if swag else product_id
        )
        payload[f"product-{product_id}-quantity"] = quantity
    return payload


@dataclass(frozen=True)
class RedeemReply:
    """The ``redeem`` reply, read.

    Attributes:
        errors: The server's messages, each a product it didn't redeem (Ionic showed
            them joined by "; " as "Partial redemption: …").
        redeemed: The ids of the products this call redeemed; none means "Nothing was
            redeemed".
    """

    errors: tuple[str, ...]
    redeemed: tuple[int, ...]


def parse_redeem_reply(reply: object) -> RedeemReply:
    """Read the ``redeem`` reply (API-07).

    An error without a non-empty ``message`` and an item without a usable product id
    are left out.

    Args:
        reply: The decoded reply.

    Returns:
        The errors and the products redeemed, in the reply's order.

    Raises:
        TypeError: The reply is not ``{"errors": [...],
            "redeemable_products_by_category": {...}}``.
    """
    errors = _member(reply, "errors", list)
    by_category = _member(reply, "redeemable_products_by_category", dict)
    messages = (e.get("message") for e in errors if isinstance(e, dict))
    redeemed = (
        _id(item.get("product_id"))
        for items in by_category.values()
        if isinstance(items, list)
        for item in items
        if isinstance(item, dict)
    )
    return RedeemReply(
        tuple(m for m in messages if isinstance(m, str) and m.strip()),
        tuple(i for i in redeemed if i is not None),
    )


def _object(reply: object) -> dict[str, object]:
    """Return the reply as an object, or raise ``TypeError`` when it isn't one."""
    if not isinstance(reply, dict):
        raise TypeError("check-in reply: not an object")
    return reply


def _member[T](reply: object, key: str, kind: type[T]) -> T:
    """Return the object ``reply``'s ``key``, or raise ``TypeError`` unless a ``kind``."""
    value = _object(reply).get(key)
    if not isinstance(value, kind):
        raise TypeError(f"check-in reply: no {key} {kind.__name__}")
    return value


def _id_and_name(entry: object, id_key: str, name_key: str) -> tuple[int | None, str]:
    """Return an entry's id (None when unusable) and its stripped name ("" when none)."""
    if not isinstance(entry, dict):
        return None, ""
    name = entry.get(name_key)
    return _id(entry.get(id_key)), name.strip() if isinstance(name, str) else ""


def _id(value: object) -> int | None:
    """Return an id sent as an integer or its decimal string, else None (a bool isn't)."""
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _count(entry: dict[str, object], key: str) -> int | None:
    """Return a non-negative integer count, else None (a bool or a float isn't one)."""
    value = entry.get(key)
    return value if type(value) is int and value >= 0 else None


def _optional_text(value: object) -> str | None:
    """Return a string as it is, else None (the field is absent or not text)."""
    return value if isinstance(value, str) else None
