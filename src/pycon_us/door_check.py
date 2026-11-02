"""A door check-in through the outbox, decided on the device (#766; DOOR-04, DOOR-07).

``check_in()`` is Door check's ``on_badge``. The decision is local, against the
preloaded attendee list (``door_preload.py``) and the account's own door rows
(``core/admission.decide()``, STORE-12), so the line keeps moving offline; a badge
outside the list is looked up online (``fetch_attendee_products(door=True)``). An
admission is a ``door`` row (``core/outbox.admit()``, one per check-in), which the
``SyncWorker`` sends as the ``redeem`` POST (D-56, D-407). Unlike the Lead scanner
(D-426) the door doesn't wait for the worker: the person is admitted now, and the sync
chip and the queue sheet say how the row syncs. A reply whose ``errors`` say a product
was already redeemed still syncs the row, and the queue sheet shows it (D-441).
"Checked in" and "Already checked in" carry the attendee's allergy and dietary chips,
from the list or the lookup (``core/admission.tags()``, DOOR-05, #767). An attendee a
lookup found is kept in ``looked_up``, the screen's memory only (D-56), so a rescan of a
badge outside the list still shows them; a row kept from before (a relaunch) asks the
server for the details, and a failed ask shows the code.
"""

import logging
import time
from collections.abc import Callable, Iterable, MutableMapping
from functools import partial

from pycon_us.check_in_api import fetch_attendee_products
from pycon_us.core.admission import Attendee, Inventory, decide, tags
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.check_in import AttendeeProducts, Item, redeem_payload
from pycon_us.core.outbox import Outcome, admit
from pycon_us.services.api import ApiClient, ApiError, NetworkError
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.staff import Staff

logger = logging.getLogger(__name__)

CHECKED_IN = "Checked in"
ALREADY = "Already checked in"
NOT_REGISTERED = "Not registered for this session"
CANT_CHECK = "Can't check this badge"
NOT_CHECKED_IN = "Not checked in"
"""Each outcome's word (ux.md §7.3)."""

SAVED = "Saved. Will sync."
ANOTHER_DEVICE = "Checked in on another device"
NO_CONNECTION = "It isn't in this session's list, and there's no connection."
LOOKUP_FAILED = "It isn't in this session's list, and the lookup failed."
NOT_SAVED = "Couldn't save this check-in on this device."
"""Detail lines: offline, a lookup's answers, a failed save (D-120)."""

NOT_FOUND = 404
"""The lookup's status for an attendee the server doesn't know."""

type Quantities = tuple[tuple[int, int], ...]
"""``(product id, quantity)`` pairs, in the session's order."""


async def check_in(
    db: OutboxDb | None,
    staff: Staff,
    kick: Callable[[], object],
    api: ApiClient | None,
    badge: Badge,
    *,
    owner: str,
    session: str,
    product_ids: Iterable[int],
    inventory: Inventory,
    looked_up: MutableMapping[str, Attendee],
    clock: Callable[[], float] = time.time,
) -> ScanResult:
    """Decide a door scan, queue the admission, and say how it went, at once.

    Args:
        db: The outbox (``Services.outbox``); None says the check-in couldn't be saved.
        staff: The ``Staff`` store: its counts are updated after an admission, and
            ``offline`` adds "Saved. Will sync.".
        kick: Asks the worker for a pass (``Services.kick_sync``).
        api: ``Services.api``, for a badge outside the list; None has no connection.
        badge: The badge scanned; last of the positional arguments, so the screen
            passes a ``functools.partial`` of the others as its ``on_badge``.
        owner: The signed-in account's lower-cased email.
        session: The scan session, the screen visit's id: part of a row's key.
        product_ids: The chosen session's products.
        inventory: The attendee list as loaded.
        looked_up: The attendees the lookup found this visit, by code; a successful
            lookup adds one. Held in memory only, never written anywhere (D-56).
        clock: The time of the scan, epoch seconds as the worker's (D-407).

    Returns:
        The result panel's answer.
    """
    code = badge.code
    kept = None if db is None else db.door_rows(owner, code)
    if db is None or kept is None:  # logged; never read as "no check-ins" (D-120)
        return not_saved(code)
    ids = tuple(dict.fromkeys(product_ids))
    admission = decide(inventory, code, ids, kept)
    attendee = inventory.attendees.get(code) or looked_up.get(code)
    if admission.already:
        if attendee is None:  # off the list, checked in before this visit
            attendee = await details(api, code, ids)
        return already(attendee)
    attendee = attendee or Attendee(code)  # replaced by the lookup's when off the list
    if admission.known:
        quantities = admission.quantities
    else:
        looked = await look_up(api, code, ids)
        if isinstance(looked, ScanResult):
            return looked
        quantities, attendee = looked
        looked_up[code] = attendee
        # Another visit may have admitted the badge while this one awaited the lookup;
        # read again, with no await from here to the enqueue (#784 review).
        kept = db.door_rows(owner, code)
        if kept is None:
            return not_saved(code)
        if decide(inventory, code, ids, kept).already:
            return already(attendee)
    now = clock()
    payload = redeem_payload(
        code, badge.door_validator, now, dict(quantities), swag=False
    )
    decision = partial(
        admit,
        owner=owner,
        code=code,
        product_ids=[pid for pid, _ in quantities],
        session=session,
        payload=payload,
        sponsor_id=None,
        sponsor_name=None,
        now=now,
    )
    enqueued = db.enqueue(code, decision)
    if enqueued is None or enqueued.row is None:  # logged (D-120)
        return not_saved(code)
    if enqueued.outcome is Outcome.ALREADY:  # the same check-in, already queued
        return already(attendee)
    staff.update_counts(db.counts(owner))
    kick()
    return checked_in(attendee, quantities, offline=staff.offline)


async def look_up(
    api: ApiClient | None, code: str, product_ids: tuple[int, ...]
) -> tuple[Quantities, Attendee] | ScanResult:
    """Ask the server what a badge outside the list can redeem of the session.

    Args:
        api: The client; None answers as no connection would.
        code: The access code.
        product_ids: The session's products.

    Returns:
        What to admit and the attendee with their details, or the result to show
        instead: "Already checked in" when they bought some and none is left, "Not
        registered" when they bought none or the server doesn't know them, "Can't
        check this badge" without an answer.
    """
    try:
        if api is None:
            raise NetworkError("no API client")
        found = await fetch_attendee_products(api, code, product_ids, door=True)
    except NetworkError:
        return ScanResult(ScanOutcome.DENIED, CANT_CHECK, code, (NO_CONNECTION,), code)
    except ApiError as error:
        if error.status == NOT_FOUND:
            return not_registered(code)
        # The status alone: the message is the server's text, which may hold the code.
        logger.warning("door lookup refused: %s", error.status)
        return ScanResult(ScanOutcome.DENIED, CANT_CHECK, code, (LOOKUP_FAILED,), code)
    items = [item for item in items_of(found) if item.product_id in product_ids]
    quantities = tuple((i.product_id, i.redeemable) for i in items if i.redeemable > 0)
    attendee = attendee_of(code, found)
    if quantities:
        return quantities, attendee
    if any(item.purchased > 0 for item in items):
        return already(attendee, (ANOTHER_DEVICE,))
    return not_registered(code)


async def details(
    api: ApiClient | None, code: str, product_ids: tuple[int, ...]
) -> Attendee:
    """Ask the server who a badge outside the list is, for "Already checked in".

    Nothing is admitted or queued: the lookup only names the attendee and their
    chips. Without an answer, the attendee is just the code.
    """
    try:
        if api is None:
            raise NetworkError("no API client")
        found = await fetch_attendee_products(api, code, product_ids, door=True)
    except ApiError, NetworkError:
        return Attendee(code)
    return attendee_of(code, found)


def attendee_of(code: str, found: AttendeeProducts) -> Attendee:
    """Return the attendee a lookup's reply describes, with their details."""
    return Attendee(
        code,
        found.name,
        found.dietary or "",
        found.has_allergy is True,
        found.allergy or "",
    )


def items_of(found: AttendeeProducts) -> list[Item]:
    """Return every item of a lookup's reply, whatever its category."""
    return [item for _, items in found.items_by_category for item in items]


def checked_in(
    attendee: Attendee, quantities: Quantities, *, offline: bool
) -> ScanResult:
    """Return "Checked in" with the name (or the code), "Admits 2" when over one.

    The word stays "Checked in" offline, where "Saved. Will sync." is added: the
    person is admitted either way. The attendee's dietary and allergy chips come
    with it (DOOR-05).
    """
    most = max(quantity for _, quantity in quantities)
    details = (f"Admits {most}",) if most > 1 else ()
    if offline:
        details = (*details, SAVED)
    code = attendee.code
    return ScanResult(
        ScanOutcome.ACCEPTED,
        CHECKED_IN,
        attendee.name or code,
        details,
        code,
        tags(attendee),
    )


def already(attendee: Attendee, details: tuple[str, ...] = ()) -> ScanResult:
    """Return "Already checked in" with the name (or the code) and the chips.

    The allergy still shows on a second pass: it matters every time (DOOR-05).
    """
    code = attendee.code
    title = attendee.name or code
    return ScanResult(
        ScanOutcome.DUPLICATE, ALREADY, title, details, code, tags(attendee)
    )


def not_registered(code: str) -> ScanResult:
    """Return "Not registered for this session" with the code."""
    return ScanResult(ScanOutcome.DENIED, NOT_REGISTERED, code, (), code)


def not_saved(code: str) -> ScanResult:
    """Return "Not checked in": the outbox couldn't be read or written (D-120)."""
    return ScanResult(ScanOutcome.DENIED, NOT_CHECKED_IN, code, (NOT_SAVED,), code)
