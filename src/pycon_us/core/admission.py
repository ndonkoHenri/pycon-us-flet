"""Door check's attendee list and, with #766, its admission decision (DOOR-03, DOOR-04).

Before scanning, the door downloads who bought each chosen session
(``attendees_by_product_with_quantity/<id>/``, API-05), so it can admit offline.
``merge()`` folds one product's reply into an ``Inventory``, as Ionic's door page did
(``staff-tools-auth.md`` §4 step 7): quantities are summed per code and product, and an
attendee's details are sticky, so a later row without them keeps the earlier ones. A
malformed row is left out, so one bad row never hides the others; a reply that isn't a
list is a ``TypeError``, which the fetch turns into a failed product (D-120).

The inventory holds names, dietary needs and allergies: it lives in Door check's
component state only and is never written anywhere (D-56). Everything here is pure.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Attendee:
    """An attendee on the door's list, with what the result shows (O-7).

    Attributes:
        code: The access code, the badge's first segment.
        name: The attendee's name, or "".
        dietary: Their dietary needs, or "".
        has_allergy: Whether they have an allergy.
        allergy: The allergy, or "" (unsaid even when ``has_allergy``).
    """

    code: str
    name: str = ""
    dietary: str = ""
    has_allergy: bool = False
    allergy: str = ""


@dataclass(frozen=True)
class Inventory:
    """Who bought the chosen sessions, and how many of each.

    Attributes:
        quantities: Each access code's quantity bought per product id (``quantity`` is
            what was bought, not what is left: the door keeps its own record).
        attendees: Each access code's attendee, with their details.
    """

    quantities: Mapping[str, Mapping[int, int]] = field(default_factory=dict)
    attendees: Mapping[str, Attendee] = field(default_factory=dict)


def merge(inventory: Inventory, product_id: int, reply: object) -> Inventory:
    """Return ``inventory`` with one product's reply folded in (API-05, DOOR-03).

    Each row is ``{id (the access code), quantity, name?, dietary?, has_allergy?,
    allergy?}``. A repeated code adds its quantity to what the product already holds;
    a detail missing from a row, or empty, keeps the one an earlier row gave. A row
    without a non-empty code or a positive integer quantity is left out.

    Args:
        inventory: The list so far; it is not changed.
        product_id: The product the reply is for.
        reply: The decoded reply.

    Returns:
        A new inventory.

    Raises:
        TypeError: The reply isn't a list.
    """
    if not isinstance(reply, list):
        raise TypeError("inventory reply: not a list")
    quantities = {code: dict(each) for code, each in inventory.quantities.items()}
    attendees = dict(inventory.attendees)
    for row in reply:
        read = _row(row)
        if read is None:
            continue
        code, quantity = read
        bought = quantities.setdefault(code, {})
        bought[product_id] = bought.get(product_id, 0) + quantity
        attendees[code] = _details(attendees.get(code, Attendee(code)), row)
    return Inventory(quantities, attendees)


def attendee_count(inventory: Inventory) -> int:
    """Return how many attendees the list holds: "Ready, works offline · 3 attendees"."""
    return len(inventory.quantities)


def _row(row: object) -> tuple[str, int] | None:
    """Return a row's code and quantity, or None for a malformed row."""
    if not isinstance(row, dict):
        return None
    code, quantity = row.get("id"), row.get("quantity")
    if not (isinstance(code, str) and code.strip()):
        return None
    if type(quantity) is not int or quantity < 1:  # a bool or a float isn't one
        return None
    return code.strip(), quantity


def _details(known: Attendee, row: dict[str, object]) -> Attendee:
    """Return ``known`` with the details ``row`` gives; a missing one keeps its own."""
    return Attendee(
        known.code,
        _text(row.get("name")) or known.name,
        _text(row.get("dietary")) or known.dietary,
        row.get("has_allergy") is True or known.has_allergy,
        _text(row.get("allergy")) or known.allergy,
    )


def _text(value: object) -> str:
    """Return a string stripped, else "" (absent, null or not text)."""
    return value.strip() if isinstance(value, str) else ""
