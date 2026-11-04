"""The session Door check checks in for: the catalog from the mock, the choice in storage.

`fetch_door_catalog()` asks `redeemable` each time the session picker opens and
keeps the door's part (DOOR-01): the catalog is never kept, as the sponsor list isn't
(D-425). The choice is `staff_door_session()`, a staff key of the year (D-414, D-466),
so a sign-out, a sign-in as another account and Clear staff data remove it with no code
of their own; Door check reads it as it opens and whenever the location changes (D-433).
"""

from pycon_us.check_in_api import fetch_catalog
from pycon_us.core.check_in import Catalog, door_catalog
from pycon_us.core.door_sessions import DoorChoice, from_stored, to_stored
from pycon_us.services.api import ApiClient
from pycon_us.services.pref_keys import staff_door_session
from pycon_us.services.storage import Storage


async def fetch_door_catalog(api: ApiClient) -> Catalog:
    """Return the door's categories and their sessions (API-05, DOOR-01).

    Args:
        api: `Services.api`, signed in with the `door_check_in` flag.

    Returns:
        The categories that aren't swag (`door_catalog()`), with their products.

    Raises:
        NetworkError: No answer arrived.
        ApiError: The mock refused the call, or its reply could not be read.
    """
    return door_catalog(await fetch_catalog(api))


async def read_door_session(storage: Storage) -> DoorChoice | None:
    """Return the choice made on this device, or None (a failed read is None, D-120).

    Args:
        storage: The session's storage.
    """
    return from_stored(await storage.get(staff_door_session(storage.year)))


async def save_door_session(storage: Storage, choice: DoorChoice) -> bool:
    """Save the choice; return whether it was saved (a failure is logged).

    Args:
        storage: The session's storage.
        choice: The session, or sessions, chosen on the picker.
    """
    return await storage.set(staff_door_session(storage.year), to_stored(choice))
