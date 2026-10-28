"""The ``Account`` store: who is signed in to the mock API, and with which roles (P3).

Sign-in, the role flags, favourites sync and the staff outbox all read this one store
(D-54, D-69). Its writes are awaited before it says so: ``sign_in`` saves the key, the
secret and the account before ``signed_in`` turns True, and ``sign_out`` removes them
before it turns False, so nothing reads a state that a relaunch would not find
(STORE-04, AUTH-02; Ionic flipped "logged in" first). ``restore`` is strict: signed in
only when the ``pycon.account`` preference and both secrets are there, and any part
without the rest is cleared (STORE-03).

The account stays when Developer's mock API URL is cleared or changed (D-398): with no
URL nothing private shows or is sent (D-51), and with one it reappears.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import flet as ft

from pycon_us.services.api import AUTHENTICATE, ApiClient, ApiError, NetworkError
from pycon_us.services.credentials import CredentialStorage, Secrets
from pycon_us.services.storage import ACCOUNT, SERVICE_ERRORS, Storage

logger = logging.getLogger(__name__)

FLAGS = {
    "lead_retrieval": "lead_retrieval",
    "door_check_in": "door_check",
    "mask_violation": "mask_violation",
    "is_speaker": "is_speaker",
}
"""Each role flag's name in the API's ``features`` and its field in the store."""


class SignIn(StrEnum):
    """How a sign-in ended; the Sign in screen says each in its own words (#685)."""

    SIGNED_IN = "signed_in"
    """Signed in, with everything saved."""
    BUSY = "busy"
    """Another sign-in is under way; this one sent nothing."""
    WRONG_CREDENTIALS = "wrong_credentials"
    """The server refused the email and password (401 or 403)."""
    OFFLINE = "offline"
    """No answer: no connection or no server at the mock URL."""
    TIMEOUT = "timeout"
    """The server did not answer in time (3 s)."""
    SERVER_ERROR = "server_error"
    """Another error status, or a reply that is not an account."""
    NOT_SAVED = "not_saved"
    """Signed in on the server, but the account could not be saved (D-120)."""


@dataclass(frozen=True)
class Profile:
    """What ``pycon.account`` keeps: the account without its key and secret.

    Attributes:
        email: The account's email, as the server sent it.
        nickname: The name the app greets the user by.
        features: The role flags by their API name; an absent one is False.
    """

    email: str
    nickname: str
    features: dict[str, bool]

    @classmethod
    def parse(cls, value: object) -> Profile | None:
        """Read a stored or received account, or None when it isn't one.

        Args:
            value: ``pycon.account``'s JSON object, or ``authenticate``'s reply.

        Returns:
            The profile; flags that are absent or not booleans read as False
            (STORE-05).
        """
        if not isinstance(value, dict):
            return None
        email, nickname = value.get("email"), value.get("nickname")
        features = value.get("features")
        if not (isinstance(email, str) and email and isinstance(nickname, str)):
            return None
        if not isinstance(features, dict):
            return None
        return cls(
            email, nickname, {name: features.get(name) is True for name in FLAGS}
        )

    def stored(self) -> dict[str, Any]:
        """Return the JSON object ``pycon.account`` holds."""
        return {
            "email": self.email,
            "nickname": self.nickname,
            "features": self.features,
        }


def _secrets_of(reply: object) -> tuple[str, str] | None:
    """Return ``authenticate``'s key and secret, or None when either is missing."""
    if not isinstance(reply, dict):
        return None
    api_key, api_secret = reply.get("key"), reply.get("secret")
    if (
        isinstance(api_key, str)
        and api_key
        and isinstance(api_secret, str)
        and api_secret
    ):
        return api_key, api_secret
    return None


# eq=False: a store is one object, compared by identity (F5), as Favorites.
@ft.observable
@dataclass(eq=False)
class Account:
    """The mock account this device is signed in to, if any (architecture §6.1).

    Attributes:
        restored: Whether ``restore`` has run; until then ``signed_in`` means nothing.
        signed_in: Whether an account and both secrets are saved and in effect.
        signing_in: Whether a sign-in is under way: the screen's progress and the
            single flight (AUTH-02).
        email: The signed-in account's email, else empty.
        nickname: The signed-in account's nickname, else empty.
        lead_retrieval: May capture leads for a sponsor.
        door_check: May check attendees in at the door, hand out swag and capture
            leads for a sponsor (``door_check_in``).
        mask_violation: May record Code of Conduct reports.
        is_speaker: Is a speaker.
        error: How the last sign-in failed, None after a success or a sign-out.
    """

    restored: bool = False
    signed_in: bool = False
    signing_in: bool = False
    email: str = ""
    nickname: str = ""
    lead_retrieval: bool = False
    door_check: bool = False
    mask_violation: bool = False
    is_speaker: bool = False
    error: SignIn | None = None
    # Never shown, so never notified: what the client signs with (D-52).
    _secrets: Secrets = (None, None)

    @property
    def owner(self) -> str:
        """Who owns what this device records, e.g. a staff scan: the email, lower-cased."""
        return self.email.lower()

    def credentials(self) -> Secrets:
        """Return the key and the secret the ``ApiClient`` signs with; Nones signed out.

        ``Services.private_api`` reads it on every request (``api.Credentials``).
        """
        return self._secrets if self.signed_in else (None, None)

    async def restore(self, storage: Storage, credentials: CredentialStorage) -> None:
        """Sign in again from what is saved, at the start, before the boot gate opens.

        Only local reads. Signed in only when ``pycon.account`` and both secrets are
        there (STORE-03); any part without the rest is removed, e.g. the keychain
        items iOS keeps after an uninstall that took the preferences. A read that
        fails leaves the user signed out for the session and removes nothing, since
        it says nothing about what is stored (D-120).

        Args:
            storage: Where ``pycon.account`` is.
            credentials: Where the key and the secret are.
        """
        try:
            await self._restore(storage, credentials)
        finally:
            self.restored = True

    async def _restore(self, storage: Storage, credentials: CredentialStorage) -> None:
        try:
            stored = await storage.read(ACCOUNT)
        except SERVICE_ERRORS:
            logger.warning("Could not read %s; signed out", ACCOUNT.key, exc_info=True)
            return
        secrets = await credentials.read()
        if secrets is None:  # logged by CredentialStorage
            logger.warning("Could not read the credentials; signed out")
            return
        profile = Profile.parse(stored)
        api_key, api_secret = secrets
        if profile is not None and api_key and api_secret:
            self._apply(profile, (api_key, api_secret))
            logger.info("Signed in from the saved account")
            return
        if stored or api_key or api_secret:
            logger.warning("Clearing a partial sign-in: signed out")
            await credentials.remove()
            await storage.remove(ACCOUNT)

    async def sign_in(
        self,
        api: ApiClient,
        storage: Storage,
        credentials: CredentialStorage,
        email: str,
        password: str,
    ) -> SignIn:
        """Sign in with ``authenticate``, and save the account before saying so.

        One at a time (AUTH-02): a call while one is under way sends nothing. On
        success the key, the secret and ``pycon.account`` are written first, and
        only then do the fields change and ``signed_in`` turn True (STORE-04). A
        write that fails removes what was written and leaves the user signed out.

        Args:
            api: ``Services.api``, the client on the mock URL.
            storage: Where ``pycon.account`` goes.
            credentials: Where the key and the secret go.
            email: What the user typed.
            password: What the user typed; never stored or logged.

        Returns:
            How it ended; every failure but ``BUSY`` is also kept in ``error``.

        Raises:
            PermissionError: The client's URL is the PSF's (D-51), which the
                Developer field refuses, so a misconfiguration.
        """
        if self.signing_in:
            return SignIn.BUSY
        self.signing_in = True
        self.error = None
        try:
            outcome = await self._sign_in(api, storage, credentials, email, password)
        finally:
            self.signing_in = False
        if outcome is not SignIn.SIGNED_IN:
            self.error = outcome
        logger.info("Sign-in: %s", outcome)
        return outcome

    async def _sign_in(
        self,
        api: ApiClient,
        storage: Storage,
        credentials: CredentialStorage,
        email: str,
        password: str,
    ) -> SignIn:
        try:
            reply = await api.request(
                AUTHENTICATE, payload={"email": email.strip(), "password": password}
            )
        except NetworkError as error:
            return SignIn.TIMEOUT if error.timed_out else SignIn.OFFLINE
        except ApiError as error:
            return SignIn.WRONG_CREDENTIALS if error.is_auth else SignIn.SERVER_ERROR
        profile, secrets = Profile.parse(reply), _secrets_of(reply)
        if profile is None or secrets is None:
            return SignIn.SERVER_ERROR
        saved = await credentials.write(*secrets) and await storage.set(
            ACCOUNT, profile.stored()
        )
        if not saved:  # logged by the storage; nothing partial stays (STORE-03)
            await credentials.remove()
            await storage.remove(ACCOUNT)
            self._clear()  # whoever was signed in before is gone from storage too
            return SignIn.NOT_SAVED
        self._apply(profile, secrets)
        return SignIn.SIGNED_IN

    async def sign_out(self, storage: Storage, credentials: CredentialStorage) -> bool:
        """Remove the key, the secret and ``pycon.account``, then sign out.

        Every removal is awaited before the store changes. Favourites stay (D-48).

        Args:
            storage: Where ``pycon.account`` is.
            credentials: Where the key and the secret are.

        Returns:
            Whether everything was removed; on False (logged) the session is signed
            out all the same, and a part left behind is cleared at the next start.
        """
        removed = await credentials.remove()
        removed = await storage.remove(ACCOUNT) and removed
        self._clear()
        logger.info("Signed out")
        return removed

    async def reset(self, credentials: CredentialStorage) -> bool:
        """Sign out as after a fresh install, for Reset app (DEV-05, D-198).

        ``Storage.clear_prefs()`` has removed ``pycon.account`` already; this removes
        the key and the secret, which are not preferences, then clears the fields.

        Args:
            credentials: Where the key and the secret are.

        Returns:
            Whether they were removed; a failure is logged.
        """
        removed = await credentials.remove()
        self._clear()
        return removed

    def _apply(self, profile: Profile, secrets: Secrets) -> None:
        """Take the account in; ``signed_in`` last, once everything it covers is set."""
        self._secrets = secrets
        self.email = profile.email
        self.nickname = profile.nickname
        for name, attribute in FLAGS.items():
            setattr(self, attribute, profile.features[name])
        self.error = None
        self.signed_in = True

    def _clear(self) -> None:
        """Forget the account; ``signed_in`` first, so nothing reads a half-cleared one."""
        self.signed_in = False
        self._secrets = (None, None)
        self.email = ""
        self.nickname = ""
        for attribute in FLAGS.values():
            setattr(self, attribute, False)
        self.error = None


AccountCtx: ft.ContextProvider[Account | None] = ft.create_context(None)
"""Provides the session's ``Account``; ``App`` writes the provider out (D-69)."""


def use_account() -> Account:
    """Return the ``Account`` store and re-render the caller when it changes (F3).

    Raises:
        RuntimeError: No ``AccountCtx`` provider is above the calling component.
    """
    store = ft.use_context(AccountCtx)
    if store is None:
        raise RuntimeError("use_account() needs an AccountCtx provider above it")
    return store
