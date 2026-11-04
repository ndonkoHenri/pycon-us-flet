"""The mock account's API key and secret, in the platform keystore (D-49, P3).

The owner module of `capabilities.SECURE_STORAGE` (architecture §13): a packaged
build keeps `pycon.api_key` and `pycon.api_secret` with `flet-secure-storage`,
the Android Keystore or the iOS keychain, readable after the first unlock and never
synced or moved to another device (Android's Auto Backup leaves its files out, D-472).
Without the extension (the companion app, D-63) they live in memory for the session, so
a restart signs out.

Read, write and remove report a failure as `Storage` does (D-120): logged and
returned, never raised. A log names the key and the error's class only, since a
service error can repeat the call's arguments, the secret among them (D-72).
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pycon_us import capabilities
from pycon_us.services.storage import SERVICE_ERRORS

if TYPE_CHECKING:  # imported only when the build has it (D-63)
    from flet_secure_storage import SecureStorage

logger = logging.getLogger(__name__)

API_KEY = "pycon.api_key"
"""The key `authenticate` returned: the `X-API-Key` header."""

API_SECRET = "pycon.api_secret"
"""The secret `authenticate` returned, which signs every call (D-52)."""

KEYS = (API_KEY, API_SECRET)
"""Both keys, in the order they are written; sign-out removes them all."""

type Secrets = tuple[str | None, str | None]
"""The key and the secret, each None when it is not stored."""


def secure_storage() -> SecureStorage | None:
    """Return the keystore service when the build has the extension, else None.

    The extension is imported only then, so the companion app is never sent a control
    its client may lack (D-63, F14). Build it in the page's context, as `Services`
    does its other services: a Flet service registers with the current page.
    """
    if not capabilities.SECURE_STORAGE:
        return None
    from flet_secure_storage import IOSOptions, KeychainAccessibility, SecureStorage

    # After the first unlock, so a start in the background still reads them; this
    # device only, so a backup restored on another phone carries no credentials.
    return SecureStorage(
        ios_options=IOSOptions(
            accessibility=KeychainAccessibility.FIRST_UNLOCK_THIS_DEVICE
        )
    )


@dataclass(eq=False)
class CredentialStorage:
    """Where the key and the secret are kept: the keystore, or memory without it.

    Attributes:
        secure: The keystore service, or None to keep them in memory for the session.
    """

    secure: SecureStorage | None = field(default_factory=secure_storage)
    _memory: dict[str, str] = field(default_factory=dict, init=False)

    async def read(self) -> Secrets | None:
        """Read the key and the secret.

        Returns:
            Both, each None when absent; or None when the keystore failed (logged),
            which says nothing about what is stored.
        """
        if self.secure is None:
            return self._memory.get(API_KEY), self._memory.get(API_SECRET)
        values: list[str | None] = []
        for key in KEYS:
            try:
                value = await self.secure.get(key)
            except SERVICE_ERRORS as error:
                logger.warning("Could not read %s: %s", key, type(error).__name__)
                return None
            values.append(value if isinstance(value, str) and value else None)
        return values[0], values[1]

    async def write(self, api_key: str, api_secret: str) -> bool:
        """Save the key and the secret.

        Args:
            api_key: The account's API key.
            api_secret: The account's secret.

        Returns:
            Whether both were saved; on a failure (logged) one of them may be, which
            `Account.restore` clears as a partial state.
        """
        if self.secure is None:
            self._memory.update({API_KEY: api_key, API_SECRET: api_secret})
            return True
        for key, value in ((API_KEY, api_key), (API_SECRET, api_secret)):
            try:
                await self.secure.set(key, value)
            except SERVICE_ERRORS as error:
                logger.warning("Could not save %s: %s", key, type(error).__name__)
                return False
        return True

    async def remove(self) -> bool:
        """Remove the key and the secret; each removal is tried, whatever the other did.

        Returns:
            Whether both are gone; a failure is logged.
        """
        if self.secure is None:
            self._memory.clear()
            return True
        removed = True
        for key in KEYS:
            try:
                await self.secure.remove(key)
            except SERVICE_ERRORS as error:
                logger.warning("Could not remove %s: %s", key, type(error).__name__)
                removed = False
        return removed
