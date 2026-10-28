"""The ways into the staff tools: More's Staff tools section and Now's Scan badges card.

Staff tools have no tab (D-16): staff reach them from a **Staff tools** section under
More's profile row and a **Scan badges** card on Now (SHELL-06, SHELL-07, SHELL-11;
ux.md §2.2, §5.1 item 4, §7.1). Both list ``built_entries()`` of the ``Account``
store's flags, only while a mock API URL is set and the account is signed in (D-51),
so they come and go live with a sign-in, a sign-out or a flag refresh. The Lead
scanner's entry says the outbox's counts ("3 pending", ``QUEUED_TOOLS``). The card
opens the last tool opened in this process, else the first entry (D-421), under Now,
so Back returns there.
"""

import flet as ft

from pycon_us.account import Account, use_account
from pycon_us.core.staff_tools import (
    QUEUED_TOOLS,
    StaffTool,
    built_entries,
    card_tool,
    queue_words,
)
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.staff import Staff, use_staff
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import SectionHeader

SECTION = "Staff tools"
"""More's section header (ux.md §2.2)."""

SCAN_BADGES = "Scan badges"
"""Now's card's title (ux.md §5.1 item 4)."""

CARD = "now.scan"
"""The card's one node (decisions §M)."""


def entries_of(account: Account, *, mock_url: bool) -> tuple[StaffTool, ...]:
    """Return the tools the entry points list: none signed out or without a mock URL.

    Args:
        account: The session's ``Account`` store.
        mock_url: Whether a mock API URL is set (``Prefs.private_api_enabled``, D-51).
    """
    if not (mock_url and account.signed_in):
        return ()
    return built_entries(account.role_flags)


def counts_of(tool: StaffTool, staff: Staff) -> str:
    """Return a tool's outbox counts in words ("3 pending"), or empty.

    Only a tool of ``QUEUED_TOOLS`` says them: the outbox is per account (D-421).

    Args:
        tool: The tool.
        staff: The ``Staff`` store.
    """
    if tool.key not in QUEUED_TOOLS:
        return ""
    return queue_words(staff.pending, staff.failed)


def line(*parts: str) -> ft.Text:
    """Return a second line of its non-empty parts, each " · " read as a pause.

    Args:
        *parts: The words, e.g. the tool's purpose and its counts.
    """
    words = " · ".join(part for part in parts if part)
    return ft.Text(words, semantics_label=words.replace(" · ", ", "))


def staff_section(
    account: Account, staff: Staff, *, mock_url: bool
) -> list[ft.Control]:
    """Return More's Staff tools section: its header and a row per tool, or nothing.

    Each row is one node (``LinkTile``), ``more.staff.<tool>``, read as its title,
    its purpose and, on the Lead scanner, the outbox's counts.

    Args:
        account: The session's ``Account`` store.
        staff: The ``Staff`` store.
        mock_url: Whether a mock API URL is set (D-51).
    """
    entries = entries_of(account, mock_url=mock_url)
    if not entries:
        return []
    return [
        SectionHeader(SECTION),
        *(
            LinkTile(
                tool.title,
                tool.route,
                icon=getattr(ft.Icons, tool.icon),
                subtitle=line(tool.purpose, counts_of(tool, staff)),
                identifier=f"more.staff.{tool.key}",
            )
            for tool in entries
        ),
    ]


@ft.component
def ScanCard() -> ft.Control:
    """Now's Scan badges card, or nothing for an account without a staff tool.

    A filled card holding one row (``LinkTile``, ``now.scan``): "Scan badges" over
    the tool it opens and its counts, "Lead scanner · 3 pending". A tap pushes the
    tool under Now (``StaffTool.now_route``).
    """
    prefs = use_prefs()
    account = use_account()
    staff = use_staff()
    memory = use_services().memory
    tool = card_tool(
        entries_of(account, mock_url=prefs.private_api_enabled), memory.staff_tool
    )
    if tool is None:
        return ft.Column([], visible=False)
    return ft.Card(
        LinkTile(
            SCAN_BADGES,
            tool.now_route,
            icon=ft.Icons.QR_CODE_SCANNER,
            subtitle=line(tool.title, counts_of(tool, staff)),
            identifier=CARD,
        ),
        variant=ft.CardVariant.FILLED,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the row's ink stays inside
        margin=ft.Margin.only(left=16, top=8, right=16),
    )
