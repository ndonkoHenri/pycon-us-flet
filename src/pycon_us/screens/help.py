"""Help & safety (``/more/help``): one place to look under stress (INFO-07, INFO-11).

Ionic had two pages, Code of Conduct and Help, that repeated the same report rows
after their reading. This page merges them (ux.md §6.7, D-281), and its first content
is what someone in trouble needs:

- **Report a concern**, an outlined card with an ``error`` edge: a row per safety
  contact from the year's data (``[[safety_contacts]]``, D-45), its title what a tap
  does and its subtitle the number or the address, read together as one phrase, with
  Copy beside it (``copy_contact()``): ``tel:`` opens nothing on an iPad or a
  simulator. Then the year's line on reporting in person to any staff member.
- **At the venue:** where the information desk, lost and found and the quiet room
  are, a line each (P2-58 adds their location cards).
- **Code of Conduct:** its summary in our words, then the full text and how reports
  are handled, both on the PSF's site, in the in-app browser.

Everything is bundled year data (``[help]``, ``year_info``), so the page works in
airplane mode with no loader. A year without it shows the feed's own
``code-of-conduct`` block, and without that the page's empty state (``InfoBody``,
D-263).
"""

import re
from urllib.parse import urlsplit

import flet as ft

from pycon_us.services import use_services
from pycon_us.ui.info_page import GUTTER, InfoBody
from pycon_us.ui.rows import SUBTITLED_TOP, LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.year_info import HelpInfo, SafetyContact

SCREEN = "help"
"""The screen's name in its semantics identifiers (decisions §M)."""

TITLE = "Help & safety"
"""The page's name: its app bar's title and its More row (ux.md §4.9's spelling)."""

REPORT = "Report a concern"
"""The card's heading."""

CONTACT_ICONS = {
    "tel": ft.Icons.CALL_OUTLINED,
    "mailto": ft.Icons.MAIL_OUTLINE,
    "https": ft.Icons.LANGUAGE,
}
"""Each kind of contact's leading icon, outlined (D-27)."""

PLACES = (
    ("info_desk", "Information desk", ft.Icons.SUPPORT_AGENT_OUTLINED),
    ("lost_and_found", "Lost & found", ft.Icons.INVENTORY_2_OUTLINED),
    ("quiet_room", "Quiet room", ft.Icons.SELF_IMPROVEMENT_OUTLINED),
)
"""The places the page names, in order: ``HelpInfo``'s field, the row's title, its icon."""

_NANP = re.compile(r"\+1(\d{3})(\d{3})(\d{4})")
"""A North American number in E.164, in its three groups."""


@ft.component
def Help() -> ft.View:
    """The Help & safety page: Report a concern first, then the venue and the CoC."""
    svc = use_services()
    content = svc.year.content
    blocks = help_blocks(content.safety_contacts, content.help)
    return AppScaffold(
        title=TITLE,
        body=InfoBody(
            blocks,
            block="code-of-conduct",
            screen=SCREEN,
            empty=EmptyState(
                "No safety details yet",
                icon=ft.Icons.HEALTH_AND_SAFETY_OUTLINED,
                # No button: at the venue, people are the way out.
                body="At the conference, any staff member can help you report a concern.",
                identifier=f"{SCREEN}.empty",
            ),
        ),
    )


def help_blocks(
    contacts: tuple[SafetyContact, ...], info: HelpInfo | None
) -> list[ft.Control]:
    """Return the page's blocks from its year data, in reading order; none without it.

    Args:
        contacts: The year's safety contacts; the card shows when there is one.
        info: The year's ``[help]`` table, or None.
    """
    blocks: list[ft.Control] = []
    if contacts:
        blocks.append(report_card(contacts, info.in_person if info else None))
    if info is not None:
        blocks += [
            SectionHeader("At the venue"),
            *(
                place_row(title, getattr(info, key), icon, key)
                for key, title, icon in PLACES
            ),
            SectionHeader("Code of Conduct"),
            ft.Semantics(
                identifier=f"{SCREEN}.coc_summary",
                container=True,
                content=ft.Container(
                    ft.Text(
                        info.coc_summary,
                        theme_style=ft.TextThemeStyle.BODY_LARGE,
                        selectable=True,
                    ),
                    padding=ft.Padding.only(left=GUTTER, right=GUTTER, bottom=8),
                ),
            ),
            LinkTile(
                "Read the Code of Conduct",
                info.coc_url,
                icon=ft.Icons.GAVEL_OUTLINED,
                subtitle=urlsplit(info.coc_url).hostname,
                identifier=f"{SCREEN}.coc",
            ),
            LinkTile(
                "How reports are handled",
                info.procedures_url,
                icon=ft.Icons.POLICY_OUTLINED,
                subtitle=urlsplit(info.procedures_url).hostname,
                identifier=f"{SCREEN}.procedures",
            ),
        ]
    return blocks


def report_card(
    contacts: tuple[SafetyContact, ...], in_person: str | None
) -> ft.Control:
    """Return the Report a concern card: a heading, a row per contact, the staff line.

    An outlined card whose edge is ``error``, the colour M3 keeps for what is urgent;
    the heading and its icon say it too, so colour is never the only signal (D-33).
    Not one node (``semantic_container=False``, as the Lightning talks card, D-211): a
    screen reader stops on the heading, then on each row and its Copy, then the line.

    Args:
        contacts: The year's safety contacts, in the order they are listed.
        in_person: The line on reporting to a staff member, or None.
    """
    heading = ft.Semantics(
        header=True,
        heading_level=2,
        container=True,
        identifier=f"{SCREEN}.report",
        content=ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.REPORT_OUTLINED, color=ft.Colors.ERROR),
                    ft.Text(
                        REPORT, theme_style=ft.TextThemeStyle.TITLE_MEDIUM, expand=True
                    ),
                ],
                spacing=16,  # the text lines up with the rows' titles below
                # Beside the first line when the heading wraps at large text, as the
                # rows' icons are, not beside the middle of the block.
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.only(left=16, top=16, right=16, bottom=4),
        ),
    )
    items: list[ft.Control] = [heading, *(contact_row(c) for c in contacts)]
    if in_person is not None:
        items.append(
            ft.Container(
                ft.Text(
                    in_person,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=ft.Padding.only(left=16, top=4, right=16, bottom=16),
            )
        )
    return ft.Container(
        ft.Card(
            ft.Column(items, spacing=0),
            variant=ft.CardVariant.OUTLINED,
            shape=ft.RoundedRectangleBorder(
                radius=12, side=ft.BorderSide(width=1, color=ft.Colors.ERROR)
            ),
            margin=0,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,  # the rows' ripple stays inside
            semantic_container=False,  # else the card reads as one node (D-211)
        ),
        padding=ft.Padding.only(left=GUTTER, top=8, right=GUTTER, bottom=8),
    )


def contact_row(contact: SafetyContact) -> ft.Control:
    """Return a contact's row: what a tap does over the value, with Copy beside it.

    ``LinkTile``'s external form (D-182): one node read as action plus value ("Email
    the Code of Conduct team, pycon-us-report@python.org"), and for a phone or an
    email a Copy button that is a stop of its own (``help.copy.<kind>``).

    Args:
        contact: The safety contact.
    """
    return LinkTile(
        contact.label,
        contact.target,
        icon=CONTACT_ICONS[contact.kind],
        subtitle=contact_line(contact),
        identifier=f"{SCREEN}.report.{contact.kind}",
        copy_identifier=f"{SCREEN}.copy.{contact.kind}",
    )


def contact_line(contact: SafetyContact) -> str:
    """Return how a contact's value reads under its title.

    A North American number in groups ("+1 562-555-0100"), which a screen reader says
    digit group by digit group rather than as one large number; any other number and
    an address as written; a web page by its host.

    Args:
        contact: The safety contact.
    """
    if contact.kind == "https":
        return urlsplit(contact.value).hostname or contact.value
    if contact.kind == "tel" and (groups := _NANP.fullmatch(contact.value)):
        return "+1 {}-{}-{}".format(*groups.groups())
    return contact.value


def place_row(title: str, line: str, icon: ft.IconData, key: str) -> ft.Control:
    """Return a place's row: its name over the line that says where it is.

    A ``ListTile`` that opens nothing, laid out as a link row with a subtitle is
    (``rows.SUBTITLED_TOP``), so its icon sits beside the name at any text size, and
    one node read as one phrase ("Quiet room, VIP Room A & B, …").

    Args:
        title: The place: "Information desk".
        line: Where it is, from the year's data.
        icon: Its leading icon, outlined.
        key: Its ``HelpInfo`` field, its identifier's key (``help.info_desk``).
    """
    tile = ft.ListTile(
        leading=ft.Icon(icon),
        title=title,
        subtitle=line,
        title_alignment=ft.ListTileTitleAlignment.TOP,
        min_vertical_padding=SUBTITLED_TOP,
    )
    return named(f"{SCREEN}.{key}", tile)
