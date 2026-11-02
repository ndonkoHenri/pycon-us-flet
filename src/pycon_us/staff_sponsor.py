"""The sponsor door staff scan for: the list from the mock, the choice in storage (#740).

``fetch_sponsors()`` asks ``lead_sponsors`` each time the picker opens: the list is
never kept, since it is needed only to change sponsor (LEAD-05). The choice is
``staff_sponsor()``, a staff key of the year (D-414, D-466), so a sign-out, a sign-in as
another account and Clear staff data remove it with no code of their own; it is in no
store, and the Lead scanner reads it as it opens, as it does the consent (D-423, D-425).
"""

from pycon_us.core.lead_sponsors import (
    LeadSponsor,
    from_stored,
    parse_sponsors,
    to_stored,
)
from pycon_us.services.api import ApiClient, ApiError
from pycon_us.services.endpoints import LEAD_SPONSORS
from pycon_us.services.pref_keys import staff_sponsor
from pycon_us.services.storage import Storage


async def fetch_sponsors(api: ApiClient) -> tuple[LeadSponsor, ...]:
    """Return the sponsors the signed-in staff account can scan for (API-09).

    Args:
        api: ``Services.api``, signed in.

    Returns:
        The sponsors, sorted by name (``parse_sponsors()``).

    Raises:
        NetworkError: No answer arrived.
        ApiError: The mock refused the call, or its reply could not be read or has
            no sponsors list.
    """
    reply = await api.request(LEAD_SPONSORS)
    try:
        return parse_sponsors(reply)
    except TypeError as error:
        raise ApiError(None, str(error)) from None


async def read_sponsor(storage: Storage) -> LeadSponsor | None:
    """Return the sponsor chosen on this device, or None (a failed read is None, D-120).

    Args:
        storage: The session's storage.
    """
    return from_stored(await storage.get(staff_sponsor(storage.year)))


async def save_sponsor(storage: Storage, sponsor: LeadSponsor) -> bool:
    """Save the sponsor chosen; return whether it was saved (a failure is logged).

    Args:
        storage: The session's storage.
        sponsor: The sponsor chosen in the picker.
    """
    return await storage.set(staff_sponsor(storage.year), to_stored(sponsor))
