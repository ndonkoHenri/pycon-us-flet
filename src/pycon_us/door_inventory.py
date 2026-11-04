"""Door check's attendee list: one `INVENTORY` call per chosen session, awaited (#765).

`load_inventory()` sends the calls together (`asyncio.gather`) and reports each one
that finishes, so the screen can say "Loading attendee list… 2 of 5" and start scanning
only once every call has answered (DOOR-03; Ionic fired them without awaiting). A
product whose call fails is listed in `Loaded.failed` and the others are kept, so the
screen says "Badges will be checked online" with Retry (D-120). Cancelling the load
cancels every call. Nothing is logged or written: the list holds names, dietary needs
and allergies, and stays in the caller's memory (D-56, D-72).
"""

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from pycon_us.core.admission import Inventory, merge
from pycon_us.services.api import ApiClient, ApiError, NetworkError
from pycon_us.services.endpoints import INVENTORY

type OnProgress = Callable[[int, int], None]
"""Told `(done, total)` each time a product's call finishes, failed ones included."""


@dataclass(frozen=True)
class Loaded:
    """The attendee list as the calls left it.

    Attributes:
        inventory: Every product that answered, merged in the order asked.
        failed: The products whose call failed, in the order asked; empty when the
            whole list loaded, so the door works offline.
    """

    inventory: Inventory
    failed: tuple[int, ...]


async def load_inventory(
    api: ApiClient, product_ids: Iterable[int], on_progress: OnProgress
) -> Loaded:
    """Load who bought each product, all at once (API-05, 20 s each).

    Args:
        api: `Services.api`, signed in with the `door_check_in` flag.
        product_ids: The chosen sessions' product ids.
        on_progress: Told `(done, total)` as each call finishes.

    Returns:
        The merged list and the products that failed: no answer, a refusal or a
        reply that can't be read.
    """
    ids = tuple(dict.fromkeys(product_ids))  # a repeated id would count twice
    done = 0

    async def fetch(product_id: int) -> object | None:
        """Return one product's reply, or None when its call failed."""
        nonlocal done
        try:
            reply = await api.request(INVENTORY, product_id)
        except NetworkError, ApiError:
            reply = None
        done += 1
        on_progress(done, len(ids))
        return reply

    replies = await asyncio.gather(*(fetch(pid) for pid in ids))
    inventory, failed = Inventory(), []
    for product_id, reply in zip(ids, replies, strict=True):
        try:
            inventory = merge(inventory, product_id, reply)
        except TypeError:  # no answer (None) or not a list: the product failed
            failed.append(product_id)
    return Loaded(inventory, tuple(failed))
