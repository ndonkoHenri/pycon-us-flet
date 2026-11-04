"""The `Account` store: who is signed in to the mock API, and with which roles (P3).

Sign-in, the role flags, favourites sync and the staff outbox all read this one store
(D-54, D-69); `services.favorites_sync` writes `favorites_dirty` (D-406). Its writes are awaited before it says so: `sign_in` saves the key, the
secret and the account before `signed_in` turns True, and `sign_out` removes them
before it turns False, so nothing reads a state that a relaunch would not find
(STORE-04, AUTH-02; Ionic flipped "logged in" first). `restore` is strict: signed in
only when the `pycon.account` preference and both secrets are there, and any part
without the rest is cleared (STORE-03).

Sign-in, sign-out and Reset app take turns on one lock: a sign-out or a reset waits for
a sign-in under way and then removes what it saved, so a late reply never signs the
user back in (D-198). A flag refresh writes under the same lock.

The role flags follow the server: `refresh_flags` asks `check_features` at the
start, on resume and when the Account screen mounts (D-54, API-03), one call at a
time. A refused key makes the account `expired`: still signed in, so what it owns
keeps its owner, but private calls stop until the user signs in again (D-57).

The account stays when Developer's mock API URL is cleared or changed (D-398): with no
URL nothing private shows or is sent (D-51), and with one it reappears.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum

import flet as ft

from pycon_us.account_profile import (
    FLAGS,
    Profile,
    log_unexpected,
    refreshed_flags,
    secrets_of,
)
from pycon_us.services.api import ApiClient, ApiError, NetworkError
from pycon_us.services.credentials import CredentialStorage, Secrets
from pycon_us.services.endpoints import AUTHENTICATE, CHECK_FEATURES
from pycon_us.services.pref_keys import ACCOUNT, STAFF_PREFIX
from pycon_us.services.storage import SERVICE_ERRORS, Storage

logger = logging.getLogger(__name__)


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


# eq=False: a store is one object, compared by identity (F5), as Favorites.
@ft.observable
@dataclass(eq=False)
class Account:
    """The mock account this device is signed in to, if any (architecture §6.1).

    Attributes:
        signed_in: Whether an account and both secrets are saved and in effect.
        signing_in: Whether a sign-in is under way: the screen's progress and the
            single flight (AUTH-02).
        email: The signed-in account's email, else empty.
        nickname: The signed-in account's nickname, else empty.
        lead_retrieval: May capture leads for a sponsor.
        door_check: May check attendees in at the door, hand out swag and capture
            leads for a sponsor (`door_check_in`).
        mask_violation: May record Code of Conduct reports.
        is_speaker: Is a speaker.
        error: How the last sign-in failed, None after a success or a sign-out.
        expired: The server refused the key (`check_features` answered 401 or
            403): still signed in, as the owner of what this device recorded, but
            no private call is made until a sign-in clears it. Not stored: the next
            start's refresh finds it again.
        favorites_dirty: Whether this device's favourites have not reached the
            account yet: an edit or the first sync after sign-in is waiting
            (`services.favorites_sync`, D-406). The Account screen says so (#688).
    """

    signed_in: bool = False
    signing_in: bool = False
    email: str = ""
    nickname: str = ""
    lead_retrieval: bool = False
    door_check: bool = False
    mask_violation: bool = False
    is_speaker: bool = False
    error: SignIn | None = None
    expired: bool = False
    favorites_dirty: bool = False
    # Never shown, so never notified: what the client signs with (D-52).
    _secrets: Secrets = (None, None)
    # One account change at a time: sign-in, sign-out and reset take turns.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    # The flag refresh in flight, if any: at most one (API-03).
    _refresh: asyncio.Task[None] | None = field(default=None, repr=False)
    # The flags in memory failed to save: the next answered refresh saves them (D-120).
    _flags_unsaved: bool = field(default=False, repr=False)

    @property
    def owner(self) -> str:
        """Who owns what this device records, e.g. a staff scan: the email, lower-cased."""
        return self.email.lower()

    @property
    def role_flags(self) -> dict[str, bool]:
        """The staff role flags as `core/staff_tools.py`'s `may_open()` takes them."""
        return {
            "lead_retrieval": self.lead_retrieval,
            "door_check": self.door_check,
            "mask_violation": self.mask_violation,
        }

    def credentials(self) -> Secrets:
        """Return the key and the secret the `ApiClient` signs with; Nones signed out.

        `Services.private_api` reads it on every request (`api.Credentials`).
        """
        return self._secrets if self.signed_in else (None, None)

    async def restore(self, storage: Storage, credentials: CredentialStorage) -> None:
        """Sign in again from what is saved, at the start, before the boot gate opens.

        Only local reads. Signed in only when `pycon.account` and both secrets are
        there (STORE-03); any part without the rest is removed, e.g. the keychain
        items iOS keeps after an uninstall that took the preferences. A read that
        fails leaves the user signed out for the session and removes nothing, since
        it says nothing about what is stored (D-120).

        Args:
            storage: Where `pycon.account` is.
            credentials: Where the key and the secret are.
        """
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
        """Sign in with `authenticate`, and save the account before saying so.

        One at a time (AUTH-02): a call while one is under way sends nothing. On
        success the old `pycon.account` is removed, then the key, the secret and
        the new `pycon.account` are written, and only then do the fields change and
        `signed_in` turn True (STORE-04). So an app killed between the writes never
        leaves one account's profile beside another's secrets: `restore` clears
        secrets without a profile. A write that fails removes what was written and
        leaves the user signed out.

        Args:
            api: `Services.api`, the client on the mock URL.
            storage: Where `pycon.account` goes.
            credentials: Where the key and the secret go.
            email: What the user typed.
            password: What the user typed; never stored or logged.

        Returns:
            How it ended; every failure but `BUSY` is also kept in `error`.

        Raises:
            PermissionError: The client's URL is the PSF's (D-51), which the
                Developer field refuses, so a misconfiguration.
        """
        if self.signing_in:
            return SignIn.BUSY
        self.signing_in = True
        self.error = None
        try:
            async with self._lock:  # a sign-out or reset under way finishes first
                outcome = await self._sign_in(
                    api, storage, credentials, email, password
                )
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
        profile, secrets = Profile.parse(reply), secrets_of(reply)
        if profile is None or secrets is None:
            return SignIn.SERVER_ERROR
        switch = profile.email.lower() != (self.owner if self.signed_in else None)
        # An account switch: no staff choice of someone else's stays (D-414); one
        # left behind refuses the sign-in, which changed nothing else yet.
        if switch and not await storage.clear_prefs(STAFF_PREFIX):  # logged
            return SignIn.NOT_SAVED
        # The old profile goes first, so no secrets are ever stored beside it.
        if not await storage.remove(ACCOUNT):  # logged; nothing was changed
            return SignIn.NOT_SAVED
        self._clear()  # whoever was signed in before is gone from storage
        saved = await credentials.write(*secrets) and await storage.set(
            ACCOUNT, profile.stored()
        )
        if not saved:  # logged by the storage; nothing partial stays (STORE-03)
            await credentials.remove()
            await storage.remove(ACCOUNT)
            return SignIn.NOT_SAVED
        self._apply(profile, secrets)
        return SignIn.SIGNED_IN

    async def sign_out(self, storage: Storage, credentials: CredentialStorage) -> bool:
        """Remove the key, the secret, `pycon.account` and the staff keys; sign out.

        Every removal is awaited before the store changes. A sign-in under way
        finishes first, so what it saves is removed too. Favourites stay (D-48), and
        so do the staff outbox's rows, under their owner (D-414).

        Args:
            storage: Where `pycon.account` is.
            credentials: Where the key and the secret are.

        Returns:
            Whether everything was removed; on False (logged) the session is signed
            out all the same, and a part left behind is cleared at the next start.
        """
        async with self._lock:
            removed = await credentials.remove()
            removed = await storage.remove(ACCOUNT) and removed
            removed = await storage.clear_prefs(STAFF_PREFIX) and removed
            self._clear()
        logger.info("Signed out")
        return removed

    async def reset(self, storage: Storage, credentials: CredentialStorage) -> bool:
        """Sign out as after a fresh install, for Reset app (DEV-05, D-198).

        A sign-out: `Storage.clear_prefs()` has removed `pycon.account` already,
        but a sign-in that was under way may have saved it again since.

        Args:
            storage: Where `pycon.account` is.
            credentials: Where the key and the secret are.

        Returns:
            Whether everything was removed; a failure is logged.
        """
        return await self.sign_out(storage, credentials)

    def refresh_flags(
        self,
        api: ApiClient | None,
        storage: Storage,
        *,
        closed: asyncio.Event | None = None,
    ) -> asyncio.Task[None] | None:
        """Ask `check_features` in the background and take its flags in (D-54, API-03).

        At start, on resume and when the Account screen mounts; nothing waits on it,
        so the boot gate never waits on the network (DATA-35). One call at a time: a
        call while one is in flight returns that one. An absent flag is False and
        `is_speaker` stays as sign-in gave it (STORE-05, AUTH-04). Only a change is
        assigned and saved to `pycon.account`, so the store notifies only then; a
        save that failed is tried again by the next answer (D-120). No
        answer keeps the flags as stored; a refused key (`ApiError.is_auth`) sets
        `expired` and keeps everything else (D-57). Nothing is written for a
        session closed meanwhile, nor when the account signed out or changed while
        the call was out.

        Args:
            api: `Services.api`, None while no mock URL is set.
            storage: Where `pycon.account` is.
            closed: `Services.closed`: a replaced session writes nothing (D-147).

        Returns:
            The refresh in flight, the one already running included, or None when
            there is nothing to ask: signed out, expired or no client.
        """
        if api is None or not self.signed_in or self.expired:
            return None
        if self._refresh is None or self._refresh.done():
            self._refresh = asyncio.create_task(
                self._refresh_flags(api, storage, closed)
            )
            self._refresh.add_done_callback(log_unexpected)
        return self._refresh

    async def _refresh_flags(
        self, api: ApiClient, storage: Storage, closed: asyncio.Event | None
    ) -> None:
        secrets = self._secrets
        flags: dict[str, bool] | None = None
        try:
            flags = refreshed_flags(await api.request(CHECK_FEATURES))
        except NetworkError:
            logger.info("Role flags not refreshed: no answer; kept as stored")
            return
        except ApiError as error:
            if not error.is_auth:
                logger.warning("Role flags not refreshed: %s", error.status)
                return
        else:
            if flags is None:
                logger.warning("Role flags not refreshed: not a features reply")
                return
        async with self._lock:  # a sign-in, sign-out or reset under way goes first
            if closed is not None and closed.is_set():
                return  # its store belongs to a destroyed session (F30)
            # The same tuple, not equal values: a sign-in meanwhile, with the same
            # key or not, gave its own answer, which this older one must not undo.
            if not self.signed_in or self._secrets is not secrets:
                return
            if flags is None:
                logger.warning("The API key was refused: the account needs a sign-in")
                self.expired = True
                return
            await self._save_flags(flags, storage)

    async def _save_flags(self, flags: dict[str, bool], storage: Storage) -> None:
        """Assign and save the refreshed flags, when any changed or the last save failed."""
        changed = {
            FLAGS[name]: on
            for name, on in flags.items()
            if getattr(self, FLAGS[name]) != on
        }
        if not changed and not self._flags_unsaved:
            return
        for attribute, on in changed.items():
            setattr(self, attribute, on)
        features = {name: getattr(self, attribute) for name, attribute in FLAGS.items()}
        profile = Profile(self.email, self.nickname, features)
        # A failure is logged; kept unsaved, the next answer saves it again.
        self._flags_unsaved = not await storage.set(ACCOUNT, profile.stored())
        if not self._flags_unsaved:
            logger.info("Role flags refreshed")

    def _apply(self, profile: Profile, secrets: Secrets) -> None:
        """Take the account in; `signed_in` last, once everything it covers is set."""
        self._secrets = secrets
        self._flags_unsaved = False
        self.email = profile.email
        self.nickname = profile.nickname
        for name, attribute in FLAGS.items():
            setattr(self, attribute, profile.features[name])
        self.error = None
        self.expired = False
        self.signed_in = True

    def _clear(self) -> None:
        """Forget the account; `signed_in` first, so nothing reads a half-cleared one."""
        self.signed_in = False
        self._secrets = (None, None)
        self._flags_unsaved = False
        self.email = ""
        self.nickname = ""
        for attribute in FLAGS.values():
            setattr(self, attribute, False)
        self.error = None
        self.expired = False
        self.favorites_dirty = False


AccountCtx: ft.ContextProvider[Account | None] = ft.create_context(None)
"""Provides the session's `Account`; `App` writes the provider out (D-69)."""


def use_account() -> Account:
    """Return the `Account` store and re-render the caller when it changes (F3).

    Raises:
        RuntimeError: No `AccountCtx` provider is above the calling component.
    """
    store = ft.use_context(AccountCtx)
    if store is None:
        raise RuntimeError("use_account() needs an AccountCtx provider above it")
    return store
