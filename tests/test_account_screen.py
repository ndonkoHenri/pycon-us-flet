"""Tests for the Account page (AUTH-09, AUTH-10, AUTH-11, SHELL-13; #688, D-411).

The page runs in a real Flet session (``tests/harness.py``) over the seeded mock behind
``tools/mock_api/transport.py``, signed in through the real ``Account`` store, with the
favourites sync's loop running as ``App`` runs it, and a real ``outbox.db`` for the
staff rows sign-out names (D-414). How it looks, the in-app browser and the screen
readers are checked on devices (the PR).
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import AsyncExitStack
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.account import Account, SignIn
from pycon_us.config import YearData, load_year
from pycon_us.core import outbox
from pycon_us.core.outbox import Status
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.prefs import Prefs
from pycon_us.screens import account as account_screen
from pycon_us.screens.account import (
    DISCORD_OFFLINE,
    NO_ACCESS,
    SIGNED_OUT_STATE,
    SYNCED,
    WAITING,
    AccountPage,
    access_of,
)
from pycon_us.screens.account_sign_out import (
    SCANS_STAY,
    SIGN_OUT_BODY,
    SIGN_OUT_TITLE,
    SIGNED_OUT,
    UNSYNCED,
    scans_line,
)
from pycon_us.screens.sign_in import EXPIRED
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.pref_keys import ACCOUNT, THEME
from pycon_us.services.private_api import PrivateApi
from pycon_us.services.storage import Storage
from pycon_us.staff import Staff
from pycon_us.state import Conference
from pycon_us.ui.queue_sheet import sync_blocked
from tests.api_clients import BASE_URL, Recorder
from tests.fakes import MemoryPrefs
from tests.harness import Shown, showing
from tests.mock_calls import state_at
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

VIEW = "/more/account"

DISCORD_URL = "https://example.org/2026/speaker/join_discord/"

YEAR = load_year(2026)
WITH_DISCORD = replace(
    YEAR, conference=replace(YEAR.conference, speaker_discord_url=DISCORD_URL)
)
"""2026 as if its site still had the Discord page, which went with the live site (#824)."""

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
def state() -> MockState:
    """A fresh seeded mock."""
    return state_at()


@pytest.fixture
def recorder(state: MockState) -> Recorder:
    """A transport to ``state`` that keeps every request sent through it."""
    return Recorder(mock_transport(state))


@pytest.fixture
def account() -> Account:
    """A signed-out ``Account`` store, restored, as after a first launch."""
    return Account(restored=True)


@pytest.fixture
def staff() -> Staff:
    """The session's ``Staff`` store, with no counts."""
    return Staff()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[OutboxDb]:
    """Yield the session's outbox, empty, in its own directory; closed afterwards."""
    directory = tmp_path / "outbox"
    directory.mkdir()
    database = OutboxDb(directory)
    yield database
    database.close()


@pytest.fixture
async def show(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account: Account,
    recorder: Recorder,
    staff: Staff,
    db: OutboxDb,
) -> AsyncIterator[Show]:
    """Return a function that renders the page with the mock URL set, signed in.

    The favourites sync's loop runs for the session, as ``App`` runs it, and stops
    with it.
    """
    async with AsyncExitStack() as stack:

        async def render(
            role: str | None = "attendee",
            *,
            year: YearData = WITH_DISCORD,
            **kwargs: object,
        ) -> Shown:
            """Render the page, signed in as the seeded ``role`` (None: signed out)."""
            private_api = PrivateApi(recorder, credentials=account.credentials)
            prefs = Prefs(loaded=True)
            prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            await private_api.connect(BASE_URL, 2026)
            shown = await stack.enter_async_context(
                showing(
                    AccountPage,
                    account_screen,
                    year=year,
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                    prefs=prefs,
                    account=account,
                    private_api=private_api,
                    staff=staff,
                    outbox=db,
                    **kwargs,  # pyright: ignore[reportArgumentType]
                )
            )
            svc = shown.services
            loop = asyncio.create_task(
                svc.favorites_sync.run(
                    svc.private_api, svc.storage, shown.favorites, account, svc.closed
                )
            )
            stack.callback(loop.cancel)
            if role is not None:
                assert svc.api is not None
                outcome = await account.sign_in(
                    svc.api,
                    svc.storage,
                    svc.credentials,
                    f"{role}@example.com",
                    f"mock-{role}",
                )
                assert outcome is SignIn.SIGNED_IN
            await settled(shown)
            return shown

        yield render


async def settled(shown: Shown) -> None:
    """Let the sync's first pull and the page's re-renders run to the end."""
    for _ in range(5):
        await asyncio.sleep(0.02)
        await shown.settle()


def dialog(shown: Shown) -> ft.AlertDialog | None:
    """The open sign-out dialog, if any."""
    found = [
        d
        for d in shown.session.page._dialogs.controls
        if isinstance(d, ft.AlertDialog) and d.open
    ]
    return found[0] if found else None


def dialog_texts(shown: Shown) -> list[str]:
    """The lines of the open dialog's content."""
    found = dialog(shown)
    assert found is not None and isinstance(found.content, ft.Column)
    return [str(t.value) for t in found.content.controls if isinstance(t, ft.Text)]


def button(shown: Shown, identifier: str) -> ft.Control:
    """The button that ``identifier`` names on the page."""
    node = shown.node(identifier)
    assert isinstance(node.content, ft.Control)
    return node.content


def action(shown: Shown, identifier: str) -> ft.Control:
    """The open dialog's button that ``identifier`` names."""
    found = dialog(shown)
    assert found is not None
    for merged in found.actions:
        assert isinstance(merged, ft.MergeSemantics)
        node = merged.content
        if isinstance(node, ft.Semantics) and node.identifier == identifier:
            assert isinstance(node.content, ft.Control)
            return node.content
    raise AssertionError(identifier)


async def tap_sign_out(shown: Shown) -> None:
    """Tap Sign out and let its try to sync, then its dialog, run out."""
    await shown.click(button(shown, "account.sign_out"))
    await settled(shown)


@pytest.mark.parametrize(
    ("role", "chips", "speaker"),
    [
        ("attendee", [], False),
        ("speaker", ["Speaker"], True),
        ("sponsor", ["Lead retrieval"], False),
        ("staff", ["Door check"], False),
        ("coc", ["Code of Conduct"], False),
        (
            "all",
            ["Lead retrieval", "Door check", "Code of Conduct", "Speaker"],
            True,
        ),
    ],
)
async def test_each_seeded_account_shows_its_chips_and_discord_for_speakers(
    show: Show, account: Account, role: str, chips: list[str], speaker: bool
) -> None:
    """Who, the flags that are on as one list, and Speaker Discord only for speakers."""
    shown = await show(role)
    assert account.email in shown.texts()
    assert access_of(account) == chips
    access = shown.node("account.access")
    if chips:
        assert access.label == f"Access: {', '.join(chips)}"
        assert access.exclude_semantics  # one node, not a stop per chip
    else:
        assert NO_ACCESS in shown.texts()
    assert bool(shown.nodes("account.discord")) is speaker


async def test_mounting_refreshes_the_role_flags(
    show: Show, recorder: Recorder, account: Account, tmp_path: Path
) -> None:
    """The page asks ``check_features`` when it mounts (D-403)."""
    private_api = PrivateApi(recorder, credentials=account.credentials)
    await private_api.connect(BASE_URL, 2026)
    assert private_api.client is not None
    elsewhere = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    await account.sign_in(
        private_api.client,
        elsewhere,
        CredentialStorage(secure=None),
        "sponsor@example.com",
        "mock-sponsor",
    )
    recorder.sent.clear()
    await show(None)  # mounts signed in
    paths = [r.url.path for r in recorder.sent]
    assert any(path.endswith("check_features/") for path in paths)


async def test_speaker_discord_opens_the_year_s_page_in_the_in_app_browser(
    show: Show,
) -> None:
    """A public PSF page from the year's data, never an /api/v1 call (D-51, D-411)."""
    shown = await show("speaker")
    await shown.click(button(shown, "account.discord"))
    assert shown.launcher.launched == [(DISCORD_URL, ft.LaunchMode.IN_APP_BROWSER_VIEW)]


async def test_2026_s_speakers_have_no_discord_button_since_its_page_is_gone(
    show: Show,
) -> None:
    """The page went with the live site, so no heading and no dead button (#824)."""
    shown = await show("speaker", year=YEAR)
    assert shown.nodes("account.discord") == []
    assert "Speakers" not in shown.texts()


async def test_offline_speaker_discord_is_disabled_with_the_reason(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no connection the button stays, disabled, and the line says why."""
    monkeypatch.setattr(account_screen, "use_online", lambda svc, *, watch: False)
    shown = await show("speaker")
    assert shown.node("account.discord").disabled
    assert DISCORD_OFFLINE in shown.texts()


async def test_the_sync_line_follows_the_favourites(show: Show) -> None:
    """Up to date once synced; an edit not sent yet says changes are waiting."""
    shown = await show("attendee")
    assert SYNCED in shown.texts()
    shown.services.private_api.client = None  # no client: the edit waits
    await shown.favorites.toggle(shown.storage, "new-1")
    await settled(shown)
    assert WAITING in shown.texts() and shown.nodes("account.sync")


async def test_cancel_closes_the_dialog_and_keeps_the_account(
    show: Show, account: Account
) -> None:
    """Sign out asks first; Cancel changes nothing."""
    shown = await show("attendee")
    await tap_sign_out(shown)
    assert dialog_texts(shown) == [SIGN_OUT_BODY]
    await shown.click(action(shown, "account.sign_out.cancel"))
    assert dialog(shown) is None
    assert account.signed_in and shown.went == []


async def test_confirm_signs_out_keeps_favourites_and_settings_and_goes_to_more(
    show: Show, account: Account
) -> None:
    """Credentials and the account go; favourites and every other pref stay (D-48)."""
    shown = await show("attendee")
    storage = shown.storage
    assert await storage.set(THEME, "dark")
    saved = shown.favorites.ids
    assert saved  # the seeded attendee's, taken in by the first sync
    await tap_sign_out(shown)
    await shown.click(action(shown, "account.sign_out.confirm"))
    assert not account.signed_in
    assert await shown.services.credentials.read() == (None, None)
    assert ACCOUNT.key not in cast(MemoryPrefs, storage.prefs).values
    assert shown.favorites.ids == saved and await storage.get(THEME) == "dark"
    assert shown.went == ["/more"]
    [bar] = shown.snack_bars
    assert isinstance(bar.content, ft.Text) and bar.content.value == SIGNED_OUT


async def test_unsent_changes_are_sent_before_the_dialog(
    show: Show, state: MockState
) -> None:
    """A waiting edit is sent at once, so the dialog has no unsynced line (D-411)."""
    shown = await show("attendee")
    client = shown.services.private_api.client
    shown.services.private_api.client = None  # the loop can't send it
    await shown.favorites.toggle(shown.storage, "new-1")
    await settled(shown)
    shown.services.private_api.client = client
    await tap_sign_out(shown)
    assert dialog_texts(shown) == [SIGN_OUT_BODY]
    assert "new-1" in next(a for a in state.accounts if a.role == "attendee").favorites


async def test_changes_that_could_not_be_sent_are_named_in_the_dialog(
    show: Show, state: MockState, account: Account
) -> None:
    """No answer: the dialog says so, and signing out still works."""
    shown = await show("attendee")
    state.faults.inject("connect", until_cleared=True)
    await shown.favorites.toggle(shown.storage, "new-1")
    await tap_sign_out(shown)
    assert dialog_texts(shown) == [SIGN_OUT_BODY, UNSYNCED]
    await shown.click(action(shown, "account.sign_out.confirm"))
    assert not account.signed_in and "new-1" in shown.favorites.ids


async def test_an_expired_account_offers_to_sign_in_again_under_the_page(
    show: Show, account: Account
) -> None:
    """After a refused key the page says so; "Sign in again" pushes under it."""
    shown = await show("attendee")
    account.expired = True
    await shown.settle()
    assert EXPIRED in shown.texts()
    await shown.click(button(shown, "account.sign_in_again"))
    assert shown.went == ["/more/account/sign-in"]


async def test_signed_out_the_page_shows_a_state(show: Show) -> None:
    """Opened signed out (a remembered location), it says so instead of an account."""
    shown = await show(None)
    assert SIGNED_OUT_STATE in shown.texts()
    assert not shown.nodes("account.sign_out")


# ------------------------------------------------------------------ unsynced staff rows


def seed(db: OutboxDb, owner: str, *statuses: Status) -> None:
    """Store one lead row of ``owner``'s in each of ``statuses``."""
    for number, status in enumerate(statuses):
        code = f"MOCK{number:04}"
        decide = partial(
            outbox.scan_lead,
            owner=owner,
            code=code,
            payload={"badge_validator": "v"},
            sponsor_id=None,
            sponsor_name=None,
            now=1.0,
        )
        enqueued = db.enqueue(code, decide)
        assert enqueued is not None and enqueued.row is not None
        if status is not Status.PENDING:
            assert db.save(replace(enqueued.row, status=status))


def title(shown: Shown) -> str:
    """The open dialog's title."""
    found = dialog(shown)
    assert found is not None and isinstance(found.title, ft.Text)
    return str(found.title.value)


def label(control: ft.Control) -> str:
    """A text button's words."""
    assert isinstance(control, ft.TextButton)
    return str(control.content)


def sync_now(shown: Shown) -> ft.Control:
    """The open dialog's Sync now button."""
    found = dialog(shown)
    assert found is not None and isinstance(found.content, ft.Column)
    for merged in found.content.controls:
        if isinstance(merged, ft.MergeSemantics):
            node = merged.content
            assert isinstance(node, ft.Semantics)
            if node.identifier == "account.sign_out.sync_now":
                assert isinstance(node.content, ft.Control)
                return node.content
    raise AssertionError("no Sync now")


async def test_unsynced_rows_are_named_and_kept_by_signing_out_anyway(
    show: Show, account: Account, db: OutboxDb
) -> None:
    """3 unsynced rows: the dialog says so; signing out anyway keeps them (D-414).

    Pending and failed rows count; synced ones don't.
    """
    shown = await show("sponsor")
    owner = account.owner
    seed(db, owner, Status.PENDING, Status.PENDING, Status.FAILED, Status.SYNCED)
    await tap_sign_out(shown)
    assert title(shown) == scans_line(3) == "3 scans haven't synced. Sign out anyway?"
    assert dialog_texts(shown) == [SCANS_STAY, SIGN_OUT_BODY]
    confirm = action(shown, "account.sign_out.confirm")
    assert label(confirm) == "Sign out anyway (3 unsynced)"
    assert not sync_now(shown).disabled
    await shown.click(confirm)
    assert not account.signed_in
    counts = db.counts(owner)
    assert counts is not None and (counts.pending, counts.failed) == (2, 1)


async def test_sync_now_sends_every_row_and_the_dialog_follows_the_count(
    show: Show, account: Account, db: OutboxDb, staff: Staff
) -> None:
    """Sync now retries the failed rows and kicks the worker; the dialog stays open.

    Once the pass has sent them, it is the plain dialog again.
    """
    shown = await show("sponsor")
    owner = account.owner
    seed(db, owner, Status.PENDING, Status.FAILED)
    await tap_sign_out(shown)
    assert title(shown) == scans_line(2)
    shown.services.sync_wake.clear()
    await shown.click(sync_now(shown))
    await settled(shown)
    assert shown.services.sync_wake.is_set()
    assert [row.status for row in db.rows(owner, tuple(Status)) or []] == [
        Status.PENDING,
        Status.PENDING,
    ]
    assert sync_now(shown).disabled  # asked, until the pass reports
    for row in db.rows(owner, (Status.PENDING,)) or []:  # the pass, as the worker
        assert db.save(outbox.after_success(row, {}))
    staff.update_counts(db.counts(owner))
    await settled(shown)
    assert title(shown) == SIGN_OUT_TITLE
    assert dialog_texts(shown) == [SIGN_OUT_BODY]
    assert label(action(shown, "account.sign_out.confirm")) == "Sign out"


async def test_unsynced_scans_and_my_schedule_are_both_named(
    show: Show, state: MockState, account: Account, db: OutboxDb
) -> None:
    """With no answer, D-411's line joins the scans' (D-414)."""
    shown = await show("sponsor")
    seed(db, account.owner, Status.PENDING)
    state.faults.inject("connect", until_cleared=True)
    await shown.favorites.toggle(shown.storage, "new-1")
    await tap_sign_out(shown)
    assert title(shown) == scans_line(1) == "1 scan hasn't synced. Sign out anyway?"
    assert dialog_texts(shown) == [SCANS_STAY, SIGN_OUT_BODY, UNSYNCED]


async def test_sync_now_says_why_it_can_t_send(
    show: Show, account: Account, db: OutboxDb
) -> None:
    """An expired account has no worker: Sync now is disabled, with the reason."""
    shown = await show("sponsor")
    seed(db, account.owner, Status.PENDING)
    account.expired = True
    await shown.settle()
    await tap_sign_out(shown)
    assert sync_now(shown).disabled
    assert sync_blocked(shown.services, account) in dialog_texts(shown)


async def test_other_accounts_rows_are_not_named(
    show: Show, account: Account, db: OutboxDb
) -> None:
    """Only the signed-in account's rows count: another's wait for its own sign-in."""
    shown = await show("sponsor")
    seed(db, "someone@example.com", Status.PENDING)
    await tap_sign_out(shown)
    assert title(shown) == SIGN_OUT_TITLE


async def test_sync_now_sends_rows_in_a_backoff_at_once(
    show: Show, account: Account, db: OutboxDb
) -> None:
    """A row waiting out a failed send's 60 s backoff is due again on Sync now.

    Found on the Android emulator: the offline pass had put the first row in its
    backoff, so Sync now sent the others and that one waited for the next tick.
    """
    shown = await show("sponsor")
    seed(db, account.owner, Status.PENDING)
    [row] = db.rows(account.owner, (Status.PENDING,)) or []
    assert db.save(outbox.after_network_error(row, time.time()))  # due in 60 s
    await tap_sign_out(shown)
    await shown.click(sync_now(shown))
    [row] = db.rows(account.owner, (Status.PENDING,)) or []
    assert row.next_at <= time.time() and row.tries == 0


async def test_sync_now_as_a_pass_starts_still_kicks_the_next(
    show: Show, account: Account, db: OutboxDb, staff: Staff
) -> None:
    """A pass that started just before the tap read its rows first: a kick follows.

    The tap can land as a tick's pass begins, before the button re-renders as busy.
    """
    shown = await show("sponsor")
    seed(db, account.owner, Status.FAILED)
    await tap_sign_out(shown)
    button = sync_now(shown)  # enabled, as rendered
    staff.syncing = True  # the pass begins; the button hasn't re-rendered yet
    shown.services.sync_wake.clear()
    await shown.click(button)
    assert shown.services.sync_wake.is_set()
    assert [row.status for row in db.rows(account.owner, tuple(Status)) or []] == [
        Status.PENDING
    ]
