"""Account (``/more/account``): who is signed in, what the account can do, and sign-out.

ux.md §7.1 (AUTH-09, AUTH-10, AUTH-11, SHELL-13): the initials avatar, the nickname
and the email; "Connected to the local mock server"; the role flags that are on as
read-only chips, read as one list ("No staff tools on this account" without one);
whether My schedule has reached the account (``Account.favorites_dirty``, D-406);
"Speaker Discord" for a speaker, a public PSF page in the in-app browser, disabled
offline with the reason (D-411); and Sign out. Mounting it refreshes the role flags
(D-403); once the server refused the key, it says so with "Sign in again", pushed
under it so a sign-in comes back here.

Sign out first tries once to send My schedule's unsent changes
(``FavoritesSync.flush()``), then asks: "Sign out? Your saved sessions stay on this
device.", with a line when the changes could not be sent (D-411); with the account's
unsynced staff rows, "3 scans haven't synced. Sign out anyway?", with Sync now, and
the rows stay under their owner (D-414). Signing out awaits every removal
(``Account.sign_out``), then returns to More with "Signed out"; the favourites and
every setting stay (D-48). Ionic signed out at once and wiped the local
favourites. It talks only to the local mock (D-51): with no mock URL, or signed out,
the page shows a state instead.
"""

import time

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us.account import Account, use_account
from pycon_us.favorites import use_favorites
from pycon_us.locations import is_top_view, parent_of
from pycon_us.prefs import use_prefs
from pycon_us.screens.account_sign_out import (
    SIGNED_OUT,
    SIGNED_OUT_PARTLY,
    sign_out_button,
    sign_out_dialog,
)
from pycon_us.screens.more import account_avatar
from pycon_us.screens.sign_in import EXPIRED, mock_line
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.staff import use_staff
from pycon_us.staff_data import unsynced
from pycon_us.ui.actions import padded
from pycon_us.ui.buttons import ICON_PADDING
from pycon_us.ui.links import OPENS_IN, LinkKind, external, open_link
from pycon_us.ui.online import use_online
from pycon_us.ui.queue_sheet import kick_once, sync_blocked
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.ui.widths import LIST, sides, use_margin

TITLE = "Account"

ACCESS = (
    ("lead_retrieval", "Lead retrieval", ft.Icons.QR_CODE_SCANNER),
    ("door_check", "Door check", ft.Icons.HOW_TO_REG_OUTLINED),
    ("mask_violation", "Code of Conduct", ft.Icons.SHIELD_OUTLINED),
    ("is_speaker", "Speaker", ft.Icons.RECORD_VOICE_OVER_OUTLINED),
)
"""Each role flag's ``Account`` field, its chip's words and its icon, in chip order."""

NO_ACCESS = "No staff tools on this account"
"""What the Access section says when no flag is on."""

SYNCED = "My schedule sync: up to date"
WAITING = "My schedule sync: changes waiting"
"""Whether the account has this device's saved sessions (D-406). No count: the sync
keeps what the server has as a state, not as a list to compare (D-411)."""

DISCORD = "Speaker Discord"
DISCORD_OFFLINE = "You're offline. Connect to open the Speaker Discord."

SIGNED_OUT_STATE = "You're not signed in"
SIGNED_OUT_STATE_BODY = "Sign in from More to see your account."


def not_asking() -> bool | None:
    """Return None: the sign-out dialog is closed, the page's first state.

    A function, so ``ft.use_state`` keeps the state typed as ``bool | None``.
    """
    return None


@ft.component
def AccountPage() -> ft.View:
    """The Account page: the account, its access, its sync, Discord and Sign out."""
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    account = use_account()
    favorites = use_favorites()
    staff = use_staff()  # the dialog's count follows each pass (D-414)
    margin = use_margin(LIST)  # its width class (D-305)
    # None while closed, else whether My schedule had synced when it opened.
    asking, set_asking = ft.use_state(not_asking)
    syncing, set_syncing = ft.use_state(False)  # Sign out's try before it asks
    kicked: MutableRef[int | None] = ft.use_ref(None)  # the dialog's Sync now
    _, set_kicked_at = ft.use_state(-1)  # a re-render, so its ring shows at once
    online = use_online(svc, watch=account.is_speaker)

    @report_errors
    async def refresh_flags() -> None:
        account.refresh_flags(svc.api, svc.storage, closed=svc.closed)  # D-403

    ft.use_effect(refresh_flags, [])

    @report_errors
    async def ask() -> None:
        set_syncing(True)
        try:
            synced = await svc.favorites_sync.flush(
                svc.private_api, svc.storage, favorites, account, svc.closed
            )
        finally:
            set_syncing(False)
        if svc.outbox is not None:  # the rows as they are now, not the last pass's
            staff.update_counts(svc.outbox.counts(account.owner))
        set_asking(synced)

    @report_errors
    def sync_now() -> None:
        # Every unsynced row is sent now: the failed ones too, as the dialog counts
        # them, and those in a backoff (D-414).
        if svc.outbox is not None:
            if staff.failed:
                staff.retry_failed(svc.outbox, account.owner, time.time())
            svc.outbox.due_now(account.owner, time.time())
        if kick_once(kicked, staff, svc.kick_sync):
            set_kicked_at(staff.revision)
        else:  # a pass under way read its rows first: the next one, right after it
            svc.kick_sync()

    @report_errors
    def cancel() -> None:
        set_asking(None)

    @report_errors
    async def sign_out() -> None:
        set_asking(None)
        removed = await account.sign_out(svc.storage, svc.credentials)
        page.show_dialog(
            ft.SnackBar(
                ft.Text(SIGNED_OUT if removed else SIGNED_OUT_PARTLY),
                behavior=ft.SnackBarBehavior.FLOATING,
            )
        )
        if is_top_view(page.route, view_path):  # not if Back left it meanwhile
            page.navigate(parent_of(view_path, svc.memory.search_base))

    ft.use_dialog(
        None
        if asking is None
        else sign_out_dialog(
            synced=asking,
            unsynced=unsynced(staff) if account.signed_in else 0,
            syncing=staff.syncing or kicked.current == staff.revision,
            blocked=sync_blocked(svc, account),
            on_confirm=sign_out,
            on_cancel=cancel,
            on_sync_now=sync_now,
        )
    )
    # Hooks first, every render (D-70); then the branch.
    if not (prefs.private_api_enabled and account.signed_in):
        body: list[ft.Control] = [
            EmptyState(
                SIGNED_OUT_STATE,
                icon=ft.Icons.NO_ACCOUNTS_OUTLINED,
                body=SIGNED_OUT_STATE_BODY,
                identifier="account.signed_out",
            )
        ]
    else:
        body = account_body(
            account,
            svc,
            view_path=view_path,
            online=online,
            syncing=syncing,
            on_sign_out=ask,
        )
    return AppScaffold(
        title=TITLE,
        body=ft.ListView(body, expand=True, padding=sides(margin, top=8, bottom=16)),
    )


def account_body(
    account: Account,
    svc: Services,
    *,
    view_path: str,
    online: bool,
    syncing: bool,
    on_sign_out: ft.ControlEventHandler[ft.OutlinedButton],
) -> list[ft.Control]:
    """Return the signed-in page's rows, top to bottom (ux.md §7.1).

    Args:
        account: The signed-in ``Account``.
        svc: The session's services: the year's Discord page, the launcher.
        view_path: The page's own path, under which "Sign in again" pushes.
        online: Whether the device has a connection, for Speaker Discord.
        syncing: Sign out is trying to send My schedule first.
        on_sign_out: Opens the sign-out dialog.
    """
    page = ft.context.page

    @report_errors
    def sign_in_again() -> None:
        page.navigate(f"{view_path}/sign-in")

    rows: list[ft.Control] = [who(account), padded(mock_line())]
    if account.expired:  # the server refused the key (D-57)
        rows += [
            padded(ft.Text(EXPIRED, theme_style=ft.TextThemeStyle.BODY_LARGE)),
            padded(
                ft.Column(
                    [
                        named(
                            "account.sign_in_again",
                            ft.FilledButton(
                                "Sign in again",
                                on_click=sign_in_again,
                                style=ft.ButtonStyle(padding=ICON_PADDING),
                                icon=ft.Icons.LOGIN,
                                elevation=0,  # with a style (ui.buttons)
                            ),
                        )
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                )
            ),
        ]
    rows += [SectionHeader("Access"), padded(access_chips(account))]
    rows += [SectionHeader("My schedule"), sync_line(account)]
    url = svc.year.conference.speaker_discord_url
    if account.is_speaker and url:
        rows += [SectionHeader("Speakers"), discord(svc, url, online=online)]
    # In a column, not a row: a row lets a button grow past the screen at the
    # largest text, where a column's width makes its label wrap.
    rows.append(
        padded(
            ft.Column(
                [sign_out_button(syncing=syncing, on_click=on_sign_out)],
                horizontal_alignment=ft.CrossAxisAlignment.START,
            )
        )
    )
    return rows


def who(account: Account) -> ft.Control:
    """Return the avatar over the nickname and the email; the avatar is decorative.

    Stacked rather than side by side: beside the avatar, the largest text broke the
    nickname inside its words.
    """
    lines: list[ft.Control] = [
        ft.Text(
            account.nickname or account.email,
            theme_style=ft.TextThemeStyle.TITLE_LARGE,
        )
    ]
    if account.nickname:
        lines.append(
            ft.Text(
                account.email,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return padded(
        ft.Column(
            [
                ft.Semantics(
                    exclude_semantics=True,
                    content=account_avatar(account.nickname, account.email, radius=32),
                ),
                ft.Semantics(
                    identifier="account.who",
                    container=True,
                    content=ft.Column(lines, spacing=2, tight=True),
                ),
            ],
            spacing=12,
            tight=True,
        )
    )


def access_of(account: Account) -> list[str]:
    """Return the chips' words for the flags that are on, in ``ACCESS`` order."""
    return [label for field, label, _ in ACCESS if getattr(account, field)]


def access_chips(account: Account) -> ft.Control:
    """Return the read-only chips, read as one node: "Access: Lead retrieval, Speaker".

    Read-only, so not buttons: one node keeps a screen reader from stopping on each
    chip as on something to tap.
    """
    labels = access_of(account)
    if not labels:
        return named(
            "account.access",
            ft.Text(
                NO_ACCESS,
                theme_style=ft.TextThemeStyle.BODY_LARGE,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        )
    icons = {label: icon for _, label, icon in ACCESS}
    return ft.Semantics(
        identifier="account.access",
        label=f"Access: {', '.join(labels)}",
        exclude_semantics=True,
        content=ft.Row(
            [access_chip(label, icons[label]) for label in labels],
            wrap=True,
            spacing=8,
            run_spacing=8,
        ),
    )


def access_chip(label: str, icon: ft.IconData) -> ft.Control:
    """Return one read-only chip: M3's chip shape, outlined, with its icon.

    Drawn, not an ``ft.Chip``: Flutter shows a chip with no handler as disabled,
    greyed out, and these say what the account can do, in full colour.
    """
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    icon, size=18, color=ft.Colors.PRIMARY, apply_text_scaling=True
                ),
                ft.Text(label, theme_style=ft.TextThemeStyle.LABEL_LARGE),
            ],
            spacing=8,
            tight=True,
        ),
        padding=ft.Padding.only(left=8, top=6, right=16, bottom=6),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=8,
    )


def sync_line(account: Account) -> ft.Control:
    """Return whether My schedule has reached the account, beside its icon."""
    waiting = account.favorites_dirty
    return named(
        "account.sync",
        ft.ListTile(
            leading=ft.Icon(
                ft.Icons.CLOUD_UPLOAD_OUTLINED
                if waiting
                else ft.Icons.CLOUD_DONE_OUTLINED
            ),
            title=ft.Text(WAITING if waiting else SYNCED),
        ),
    )


def discord(svc: Services, url: str, *, online: bool) -> ft.Control:
    """Return Speaker Discord, a link to the PSF's page; offline, disabled with why.

    Args:
        svc: The session's services, for the launcher.
        url: The year's page (``speaker_discord_url``).
        online: Whether the device has a connection.
    """

    @report_errors
    async def go(e: ft.Event[ft.Button]) -> None:
        await open_link(svc, url, opener=e.control)

    button = ft.FilledTonalButton(
        ft.Text(DISCORD, semantics_label=f"{DISCORD}\n{OPENS_IN[LinkKind.WEB]}"),
        icon=ft.Icons.OPEN_IN_NEW,
        on_click=go,
        disabled=not online,
        style=ft.ButtonStyle(padding=ICON_PADDING),
        elevation=0,  # with a style (ui.buttons)
    )
    controls: list[ft.Control] = [external("account.discord", button)]
    if not online:
        controls.append(
            ft.Text(
                DISCORD_OFFLINE,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return padded(
        ft.Column(
            controls,
            spacing=8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )
    )
