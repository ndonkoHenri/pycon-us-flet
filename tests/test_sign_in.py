"""Tests for the Sign in page and More's profile row (AUTH-01, API-02, SHELL-12, #685).

The page runs in a real Flet session (`tests/harness.py`) over the seeded mock behind
`tools/mock_api/transport.py`, so each sign-in goes through the real client and the
`Account` store. Typing is what Flutter reports: the field's value, then (for typing,
not for autofill) a change event. How the page looks, autofill and the screen readers
are checked on devices (the PR).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import cast

import flet as ft
import httpx
import pytest

from pycon_us.account import Account, SignIn
from pycon_us.config import load_year
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.locations import LEAD_SCANNER
from pycon_us.prefs import Prefs
from pycon_us.screens import more, sign_in
from pycon_us.screens.sign_in import ERRORS, EXPIRED, INTRO, UNAVAILABLE, SignInPage
from pycon_us.services.private_api import PrivateApi
from pycon_us.state import Conference
from tests.api_clients import BASE_URL, Recorder, replying
from tests.harness import Shown, showing
from tests.mock_calls import account as seeded
from tests.mock_calls import state_at
from tools.mock_api.faults import Fault
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

VIEW = "/more/sign-in"

ROLES = ("attendee", "speaker", "sponsor", "staff", "coc", "all")
"""Every seeded account (`tests/fixtures/mock/seed.json`)."""

LEADS = ("sponsor", "all")
"""The seeded accounts with `lead_retrieval`: a sign-in lands on the scanner (D-16)."""

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
def state() -> MockState:
    """A fresh seeded mock."""
    return state_at()


@pytest.fixture
def recorder(state: MockState) -> Recorder:
    """A transport to `state` that keeps every request sent through it."""
    return Recorder(mock_transport(state))


@pytest.fixture
def account() -> Account:
    """A signed-out `Account` store, as after a first launch."""
    return Account()


@pytest.fixture
async def show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account: Account
) -> AsyncIterator[Show]:
    """Return a function that renders a screen with or without a mock URL set."""
    async with AsyncExitStack() as stack:

        async def render(
            transport: httpx.AsyncBaseTransport | None,
            *,
            screen: Callable[[], ft.Control] = SignInPage,
            view_path: str = VIEW,
            prefs: Prefs | None = None,
        ) -> Shown:
            """Render `screen`; a transport sets the mock URL, None leaves it unset."""
            private_api = PrivateApi(transport, credentials=account.credentials)
            if prefs is None:
                prefs = Prefs(loaded=True)
            if transport is not None:
                prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
                await private_api.connect(BASE_URL, 2026)
            return await stack.enter_async_context(
                showing(
                    screen,
                    sign_in,
                    more,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=view_path,
                    route=view_path,
                    prefs=prefs,
                    account=account,
                    private_api=private_api,
                )
            )

        yield render


def field(shown: Shown, label: str) -> ft.TextField:
    """The mounted field with this label: "Email" or "Password"."""
    (found,) = [f for f in shown.find(ft.TextField) if f.label == label]
    return found


async def type_into(shown: Shown, label: str, text: str) -> None:
    """Type into a field as Flutter reports it: the value, then the change event."""
    text_field = field(shown, label)
    shown.session.apply_patch(text_field._i, {"value": text})
    await shown.event(text_field, "change", text)


def submit(shown: Shown) -> ft.FilledButton:
    """The mounted Sign in button."""
    (button,) = shown.find(ft.FilledButton)
    return button


async def sign_in_as(shown: Shown, email: str, password: str) -> None:
    """Type the email and the password, then tap Sign in."""
    await type_into(shown, "Email", email)
    await type_into(shown, "Password", password)
    await shown.click(submit(shown))


def error_line(shown: Shown) -> str:
    """What the error line says; "" while it is hidden."""
    node = shown.node("sign_in.error")
    assert node.live_region  # announced as it changes (ux.md §9)
    if not node.visible:
        return ""
    texts = [t.value for t in shown.find(ft.Text) if t.value in ERRORS.values()]
    return str(texts[0]) if texts else ""


async def test_without_a_mock_url_there_is_no_form_only_a_state(show: Show) -> None:
    """D-51: no mock URL, no form; the page says sign-in isn't available, and why."""
    shown = await show(None)
    assert shown.find(ft.TextField) == []
    assert UNAVAILABLE in shown.texts()
    assert shown.nodes("sign_in.unavailable")


async def test_the_form_has_its_identifiers_hints_and_keyboards(
    show: Show, recorder: Recorder
) -> None:
    """The fields autofill as email and password, and every part has its identifier."""
    shown = await show(recorder)
    for identifier in ("email", "password", "submit", "error"):
        assert shown.nodes(f"sign_in.{identifier}"), identifier
    email, password = field(shown, "Email"), field(shown, "Password")
    assert email.keyboard_type is ft.KeyboardType.EMAIL
    assert email.autofill_hints == [ft.AutofillHint.EMAIL]
    # Next on the email, then the password's default Done, which signs in.
    assert email.text_input_action is ft.TextInputAction.NEXT
    assert password.text_input_action is None
    assert password.password
    assert password.autofill_hints == [ft.AutofillHint.PASSWORD]
    (group,) = shown.find(ft.AutofillGroup)
    # Nothing to save before a sign-in: leaving never offers to save the fields.
    assert group.dispose_action is ft.AutofillGroupDisposeAction.CANCEL
    assert error_line(shown) == ""


@pytest.mark.parametrize("role", ROLES)
async def test_each_seeded_account_signs_in_and_goes_back_with_a_snack_bar(
    show: Show, recorder: Recorder, state: MockState, account: Account, role: str
) -> None:
    """A success saves the account, says "Signed in as <nickname>" and pops to More.

    A lead-retrieval account lands on the Lead scanner instead, whose Back is More
    (D-16, #689).
    """
    shown = await show(recorder)
    await sign_in_as(shown, f"{role}@example.com", f"mock-{role}")
    assert account.signed_in and account.email == f"{role}@example.com"
    [bar] = shown.snack_bars
    assert isinstance(bar.content, ft.Text)
    assert bar.content.value == f"Signed in as {seeded(state, role).nickname}"
    assert shown.went == [LEAD_SCANNER if role in LEADS else "/more"]


@pytest.mark.parametrize("setting", ["now", "lead"])
async def test_a_sponsor_lands_on_the_scanner_unless_the_setting_says_now(
    show: Show, recorder: Recorder, setting: str
) -> None:
    """Open the app on Now sends the sponsor back where they came from (D-16)."""
    prefs = Prefs(loaded=True, start_screen=setting)  # type: ignore[arg-type]
    shown = await show(recorder, prefs=prefs)
    await sign_in_as(shown, "sponsor@example.com", "mock-sponsor")
    assert shown.went == ["/more" if setting == "now" else LEAD_SCANNER]


async def test_only_a_sign_in_lets_the_os_save_the_credentials(
    show: Show, recorder: Recorder
) -> None:
    """A wrong password leaves the group cancelling; a success commits it, then leaves.

    iOS offered to save a wrong password when the page was left after a failed try.
    """
    shown = await show(recorder)
    await sign_in_as(shown, "all@example.com", "nope")
    (group,) = shown.find(ft.AutofillGroup)
    assert group.dispose_action is ft.AutofillGroupDisposeAction.CANCEL
    await type_into(shown, "Password", "mock-all")
    await shown.click(submit(shown))
    (group,) = shown.find(ft.AutofillGroup)
    assert group.dispose_action is ft.AutofillGroupDisposeAction.COMMIT
    assert shown.went == [LEAD_SCANNER]  # the account has lead_retrieval (D-16)


async def test_autofilled_fields_are_read_when_signing_in(
    show: Show, recorder: Recorder, account: Account
) -> None:
    """Values the OS filled without a change event still sign in (Ionic's iOS bug)."""
    shown = await show(recorder)
    shown.session.apply_patch(field(shown, "Email")._i, {"value": "all@example.com"})
    shown.session.apply_patch(field(shown, "Password")._i, {"value": "mock-all"})
    await shown.click(submit(shown))
    assert account.signed_in


async def test_the_password_s_action_key_signs_in(
    show: Show, recorder: Recorder, account: Account
) -> None:
    """The keyboard's Done on the password field signs in, as the button does."""
    shown = await show(recorder)
    await type_into(shown, "Email", "all@example.com")
    await type_into(shown, "Password", "mock-all")
    await shown.event(field(shown, "Password"), "submit", "mock-all")
    assert account.signed_in


@pytest.mark.parametrize(
    ("fault", "outcome"),
    [
        (None, SignIn.WRONG_CREDENTIALS),
        ("connect", SignIn.OFFLINE),
        ("timeout", SignIn.TIMEOUT),
    ],
)
async def test_each_failure_says_its_own_sentence_and_keeps_the_fields(
    show: Show,
    recorder: Recorder,
    state: MockState,
    account: Account,
    fault: Fault | None,
    outcome: SignIn,
) -> None:
    """A wrong password, no server and no answer in time are each said apart (D-54)."""
    if fault is not None:
        state.faults.inject(fault)
    shown = await show(recorder)
    password = "nope" if fault is None else "mock-all"
    await sign_in_as(shown, "all@example.com", password)
    assert not account.signed_in
    assert error_line(shown) == ERRORS[outcome]
    assert field(shown, "Email").value == "all@example.com"
    assert field(shown, "Password").value == password
    assert shown.went == [] and shown.snack_bars == []


async def test_a_server_error_says_so(show: Show, account: Account) -> None:
    """Another error status is the server's failure, not the user's."""
    shown = await show(replying(500, b'{"message": "Internal error"}'))
    await sign_in_as(shown, "all@example.com", "mock-all")
    assert error_line(shown) == ERRORS[SignIn.SERVER_ERROR]


async def test_the_next_try_clears_the_error_and_can_succeed(
    show: Show, recorder: Recorder, account: Account
) -> None:
    """After a wrong password, the right one signs in; the old error is gone."""
    shown = await show(recorder)
    await sign_in_as(shown, "all@example.com", "nope")
    assert error_line(shown) == ERRORS[SignIn.WRONG_CREDENTIALS]
    await type_into(shown, "Password", "mock-all")
    await shown.click(submit(shown))
    assert account.signed_in and error_line(shown) == ""


def test_every_failure_has_its_sentence() -> None:
    """Each way a sign-in can fail, but another one in flight, has words of its own."""
    assert set(ERRORS) == set(SignIn) - {SignIn.SIGNED_IN, SignIn.BUSY}
    assert len(set(ERRORS.values())) == len(ERRORS)


class Held(Recorder):
    """A transport to the mock that holds each request until `release` is set."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Hold requests to `inner`, which answers them once released."""
        super().__init__(inner)
        self.release = asyncio.Event()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request, wait for `release`, then let the mock answer."""
        self.sent.append(request)
        await self.release.wait()
        return await self.inner.handle_async_request(request)


async def test_taps_while_in_flight_send_one_request(
    show: Show, state: MockState, account: Account
) -> None:
    """The button turns busy and disabled, and more taps send nothing (AUTH-02)."""
    held = Held(mock_transport(state))
    shown = await show(held)
    await type_into(shown, "Email", "all@example.com")
    await type_into(shown, "Password", "mock-all")
    button = submit(shown)
    first = asyncio.create_task(shown.click(button))
    await asyncio.sleep(0.05)
    await shown.settle()
    assert submit(shown).disabled
    assert "Signing in…" in shown.texts()
    await shown.click(button)  # a tap the client sent before it saw "disabled"
    await shown.event(field(shown, "Password"), "submit", "mock-all")
    held.release.set()
    await first
    assert len(held.sent) == 1 and account.signed_in


# ------------------------------------------------------------------ More's row


async def test_more_s_profile_row_follows_the_url_and_the_account_live(
    show: Show, recorder: Recorder, account: Account
) -> None:
    """No URL, no row; signed out, "Sign in"; signed in, who, and back (SHELL-12)."""
    prefs = Prefs(loaded=True)
    shown = await show(None, screen=more.More, view_path="/more", prefs=prefs)
    assert not shown.nodes("more.sign_in") and not shown.nodes("more.account")
    prefs.dev = {DEV_MOCK_API_URL: BASE_URL}  # Developer saves a mock URL
    await shown.settle()
    assert shown.nodes("more.sign_in") and not shown.nodes("more.account")
    api = PrivateApi(recorder, credentials=account.credentials)
    await api.connect(BASE_URL, 2026)
    assert api.client is not None
    await account.sign_in(
        api.client,
        shown.storage,
        shown.services.credentials,
        "all@example.com",
        "mock-all",
    )
    await shown.settle()
    assert shown.nodes("more.account") and not shown.nodes("more.sign_in")
    assert "RE" in shown.texts()
    assert ("Robin Everything", "all@example.com") in {
        (tile.title, tile.subtitle) for tile in shown.find(ft.ListTile)
    }
    await account.sign_out(shown.storage, shown.services.credentials)
    await shown.settle()
    assert shown.nodes("more.sign_in") and not shown.nodes("more.account")
    prefs.dev = {}  # cleared: the row goes, the account would stay (D-398)
    await shown.settle()
    assert not shown.nodes("more.sign_in")


async def test_a_revoked_key_turns_the_row_into_sign_in_again_live(
    show: Show, state: MockState, recorder: Recorder, account: Account
) -> None:
    """A refresh refused by the server swaps who is signed in for "Sign in again"."""
    shown = await show(recorder, screen=more.More, view_path="/more")
    api = shown.services.api
    assert api is not None
    await account.sign_in(
        api, shown.storage, shown.services.credentials, "all@example.com", "mock-all"
    )
    state.faults.inject("revoked")
    refresh = account.refresh_flags(api, shown.storage)
    assert refresh is not None
    await refresh
    await shown.settle()
    assert shown.nodes("more.sign_in_again") and not shown.nodes("more.account")


async def test_after_a_revoked_key_sign_in_starts_with_the_email(
    show: Show, recorder: Recorder, account: Account
) -> None:
    """Sign in says why and fills the email in; signing in clears `expired`."""
    account.email, account.signed_in, account.expired = "all@example.com", True, True
    shown = await show(recorder)
    assert field(shown, "Email").value == "all@example.com"
    assert EXPIRED in shown.texts() and INTRO not in shown.texts()
    await type_into(shown, "Password", "mock-all")
    await shown.click(submit(shown))
    assert account.signed_in and not account.expired


async def test_the_reveal_button_is_named_and_says_what_it_will_do(
    show: Show, recorder: Recorder
) -> None:
    """Show password reveals it and becomes Hide password (#837: "Unlabelled" before)."""
    shown = await show(recorder)
    button = cast(ft.IconButton, shown.node("sign_in.reveal").content)
    assert button.tooltip == "Show password"
    assert field(shown, "Password").password
    await shown.click(button)
    button = cast(ft.IconButton, shown.node("sign_in.reveal").content)
    assert button.tooltip == "Hide password"
    assert not field(shown, "Password").password
    await shown.click(button)
    assert field(shown, "Password").password
