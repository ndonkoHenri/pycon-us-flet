"""Sign in (`/more/sign-in`): the one way into a mock account (AUTH-01, API-02, D-54).

The form of ux.md §7.1: an email and a password in an `AutofillGroup`, so the OS
offers to fill them, and to save them once they signed someone in, never a wrong
password; and "Sign in", disabled with a ring while the request is in flight, so
repeated taps send one request (AUTH-02; `Account.sign_in` is the single flight).
The fields' text is read when the user signs in, from what Flutter last reported, not
from a change event: Ionic's form missed what iOS autofilled. Every failure is said in
its own words on one live-region line under the button, and the fields keep what was
typed. A success goes back to where the user came from, with "Signed in as
<nickname>"; a lead-retrieval account lands on the Lead scanner instead, Back to More,
unless Settings' Start screen says Now (D-16, #689). After the server refused the account's key ("Sign in again" on More), it
says so and starts with the account's email filled in (#686).

It talks only to the local mock (D-51): with no mock API URL set it shows a state that
says sign-in isn't available, never a form.
"""

import flet as ft

from pycon_us.account import SignIn, use_account
from pycon_us.locations import LEAD_SCANNER, is_top_view, lands_on_lead, parent_of
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors, say
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import outcome_line, padded
from pycon_us.ui.buttons import LABEL_PADDING, busy_label
from pycon_us.ui.fields import use_field_query
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.ui.widths import LIST, sides, use_margin

INTRO = "Only needed for sponsor and staff tools, and to sync My schedule."
"""Why anyone would sign in (ux.md §7.1)."""

EXPIRED = "Your sign-in has expired. Sign in again to keep using staff tools and sync."
"""Why to sign in again, once the server refused the account's key (D-57, #686)."""

MOCK_LINE = "Connected to the local mock server"
"""Where the email and password go: never the PSF's server (D-51)."""

ERRORS = {
    SignIn.WRONG_CREDENTIALS: "Email or password is incorrect.",
    SignIn.OFFLINE: "You're offline. Connect and try again.",
    SignIn.TIMEOUT: "The server didn't answer. Try again.",
    SignIn.SERVER_ERROR: "The server couldn't sign you in. Try again later.",
    SignIn.NOT_SAVED: "Couldn't save your sign-in on this device. Try again.",
}
"""What the line under the button says for each failure (D-54, D-120)."""

UNAVAILABLE = "Sign-in isn't available"
"""The page's state with no mock API URL set: no form (D-51)."""

UNAVAILABLE_BODY = (
    "It's on only while the app uses a local mock server, set in Developer options."
)
"""Why, and the one way to turn it on."""

BUTTON_IN_SIGHT = 200
"""How much of the page under a field's text stays in sight when it takes the focus,
in dp: Sign in and the error line under it, at large text too (Flutter's
`scrollPadding`)."""


def signed_in_as(nickname: str, email: str) -> str:
    """Return the SnackBar after a sign-in: "Signed in as <nickname>", else the email."""
    return f"Signed in as {nickname or email}"


@ft.component
def SignInPage() -> ft.View:
    """The Sign in page: the form while a mock URL is set, else a state saying why not."""
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    account = use_account()
    tokens = use_tokens()
    margin = use_margin(LIST)  # its width class (D-305)
    # Back to the same account: the email the server refused the key of (#686).
    email = use_field_query(account.email if account.expired else "")
    password = use_field_query()
    error, set_error = ft.use_state("")  # how the last try here failed, said
    # Who was signed in here: the group may offer to save the fields now (COMMIT),
    # and only then does the page go, from the effect, so leaving after a failed try
    # never offers to save a wrong password (CANCEL until then).
    signed_in, set_signed_in = ft.use_state("")

    @report_errors
    async def leave() -> None:
        if not signed_in:
            return
        say(page, signed_in)
        if not is_top_view(page.route, view_path):  # Back left it meanwhile
            return
        if lands_on_lead(prefs, account):  # a sponsor's scanner, over More (D-16)
            page.navigate(LEAD_SCANNER)
        else:
            page.navigate(parent_of(view_path, svc.memory.search_base))

    ft.use_effect(leave, [signed_in])
    # Hooks first, every render (D-70); then the branch.
    if not prefs.private_api_enabled:
        return AppScaffold(
            title="Sign in",
            source=__name__,
            body=ft.ListView(
                [
                    EmptyState(
                        UNAVAILABLE,
                        icon=ft.Icons.NO_ACCOUNTS_OUTLINED,
                        body=UNAVAILABLE_BODY,
                        identifier="sign_in.unavailable",
                    )
                ],
                expand=True,
                padding=sides(margin),
            ),
        )

    @report_errors
    async def to_password() -> None:
        await password.focus()

    @report_errors
    async def sign_in() -> None:
        api = svc.api
        if api is None or account.signing_in:  # cleared meanwhile, or in flight
            return
        # Read now, from what Flutter last reported: autofill included (AUTH-01).
        typed_email = email.ref.current.value if email.ref.current else ""
        typed_password = password.ref.current.value if password.ref.current else ""
        set_error("")
        outcome = await account.sign_in(
            api,
            svc.storage,
            svc.credentials,
            typed_email or "",
            typed_password or "",
        )
        if outcome is SignIn.BUSY:  # another try is in flight; it says its own
            return
        if outcome is not SignIn.SIGNED_IN:
            set_error(ERRORS[outcome])
            return
        set_signed_in(signed_in_as(account.nickname, account.email))  # then leave()

    busy = account.signing_in
    return AppScaffold(
        title="Sign in",
        source=__name__,
        body=ft.ListView(
            [
                padded(
                    ft.Text(
                        EXPIRED if account.expired else INTRO,
                        theme_style=ft.TextThemeStyle.BODY_LARGE,
                    )
                ),
                padded(mock_line()),
                ft.AutofillGroup(
                    dispose_action=(
                        ft.AutofillGroupDisposeAction.COMMIT
                        if signed_in
                        else ft.AutofillGroupDisposeAction.CANCEL
                    ),
                    content=ft.Column(
                        [
                            padded(
                                named(
                                    "sign_in.email",
                                    ft.TextField(
                                        ref=email.ref,
                                        value=email.value,
                                        on_change=email.changed,
                                        # Next, not Done: the password comes
                                        # next. Flutter moves the focus there
                                        # itself; to_password makes sure of it.
                                        text_input_action=ft.TextInputAction.NEXT,
                                        on_submit=to_password,
                                        label="Email",
                                        keyboard_type=ft.KeyboardType.EMAIL,
                                        autofill_hints=[ft.AutofillHint.EMAIL],
                                        autocorrect=False,
                                        enable_suggestions=False,
                                        can_request_focus=email.focusable,
                                        scroll_padding=reveal(),
                                    ),
                                )
                            ),
                            # Not merged: the reveal button inside it stays a
                            # button of its own (D-214).
                            padded(
                                ft.Semantics(
                                    identifier="sign_in.password",
                                    content=ft.TextField(
                                        ref=password.ref,
                                        value=password.value,
                                        on_change=password.changed,
                                        on_submit=sign_in,
                                        label="Password",
                                        password=True,
                                        can_reveal_password=True,
                                        autofill_hints=[ft.AutofillHint.PASSWORD],
                                        autocorrect=False,
                                        enable_suggestions=False,
                                        can_request_focus=password.focusable,
                                        scroll_padding=reveal(),
                                    ),
                                )
                            ),
                        ],
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                ),
                padded(
                    ft.Row(
                        [submit_button(busy=busy, on_click=sign_in)],
                        alignment=ft.MainAxisAlignment.END,
                    )
                ),
                ft.Semantics(
                    identifier="sign_in.error",
                    live_region=True,
                    visible=bool(error),
                    content=outcome_line(error, False, tokens=tokens),
                ),
            ],
            expand=True,
            padding=sides(margin, top=8),
        ),
    )


def reveal() -> ft.Padding:
    """Return a field's `scroll_padding`: Sign in and its error line stay in sight."""
    return ft.Padding.only(left=20, top=20, right=20, bottom=BUTTON_IN_SIGHT)


def mock_line() -> ft.Control:
    """Return "Connected to the local mock server", beside a decorative icon."""
    return ft.Row(
        [
            ft.Icon(
                ft.Icons.LAN_OUTLINED,
                size=20,
                color=ft.Colors.ON_SURFACE_VARIANT,
                apply_text_scaling=True,
            ),
            ft.Text(
                MOCK_LINE,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
                expand=True,
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def submit_button(
    *, busy: bool, on_click: ft.ControlEventHandler[ft.Button]
) -> ft.Control:
    """Return Sign in: disabled with a ring and "Signing in…" while one is in flight.

    The words change with the ring, so a screen reader says the busy state, and the
    disabled button takes no second tap (AUTH-02).

    Args:
        busy: A sign-in is in flight (`Account.signing_in`).
        on_click: Signs in.
    """
    return named(
        "sign_in.submit",
        ft.FilledButton(
            content=busy_label("Signing in…") if busy else ft.Text("Sign in"),
            on_click=on_click,
            disabled=busy,
            style=ft.ButtonStyle(padding=LABEL_PADDING),
            elevation=0,  # as Apply (D-232)
        ),
    )
