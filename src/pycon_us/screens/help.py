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
  are, a line each, each followed by its ``LocationCard`` when ``[help]`` names its
  pin (``spot_card()``, INFO-12), which pushes the floor viewer at it; under the
  quiet room the sponsor who provides it, which pushes its detail
  (``SponsorCreditTile``, D-337); then All maps, which opens the Map tab (its Floor
  plans once #391 adds them).
- **Code of Conduct:** its summary in our words, then the full text and how reports
  are handled, both on the PSF's site, in the in-app browser.
- **The app:** Report a problem with the app, last on the page whatever the year has.
  While the repository is private it shares the app's log and diagnostics, as About
  this app's Report a problem does; once ``SOURCE_URL`` is set it opens a new issue in
  the in-app browser (``ReportProblem``, INFO-11, D-88, D-297).

Everything is bundled year data (``[help]``, ``year_info``), so the page works in
airplane mode with no loader. A year without it shows the feed's own
``code-of-conduct`` block, and without that the page's empty state (``InfoBody``,
D-263).
"""

import re
from urllib.parse import urlsplit

import flet as ft

from pycon_us import SOURCE_URL
from pycon_us.screens.about_app import shown_url
from pycon_us.screens.sponsor_credit import SponsorCreditTile
from pycon_us.services import use_services
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import action_row
from pycon_us.ui.info_page import GUTTER, InfoBody
from pycon_us.ui.location_card import spot_card
from pycon_us.ui.rows import SUBTITLED_TOP, LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.share import (
    new_issue_url,
    report_outcome,
    report_subtitle,
    use_problem_report,
)
from pycon_us.ui.states import EmptyState
from pycon_us.year_info import HelpInfo, SafetyContact, SponsorCredit
from pycon_us.year_map import MapData

SCREEN = "help"
"""The screen's name in its semantics identifiers (decisions §M)."""

TITLE = "Help & safety"
"""The page's name: its app bar's title and its More row (ux.md §4.9's spelling)."""

REPORT = "Report a concern"
"""The card's heading."""

ALL_MAPS = "All maps"
"""The row after the places, to the Map tab, where every floor plan is."""

REPORT_PROBLEM = "Report a problem with the app"
"""The last row's title: a problem with this app, not a safety concern."""

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
    blocks = help_blocks(
        content.safety_contacts,
        content.help,
        content.sponsor_credits.quiet_room,
        svc.year.map,
    )
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
            footer=[ReportProblem()],
        ),
    )


@ft.component
def ReportProblem() -> ft.Control:
    """The page's last section: Report a problem with the app, and how it ended.

    A component of its own, as About this app's Help us fix it is, so a share
    re-renders these rows and not the page (``use_problem_report()``).
    """
    report = use_problem_report()
    tokens = use_tokens()
    return ft.Column(
        [
            SectionHeader("The app"),
            report_problem_row(
                SOURCE_URL,
                packaged=report.packaged,
                sharing=report.sharing,
                on_share=report.share,
            ),
            report_outcome(f"{SCREEN}.report_outcome", report.outcome, tokens=tokens),
        ],
        spacing=0,
    )


def report_problem_row(
    source_url: str | None,
    *,
    packaged: bool,
    sharing: bool,
    on_share: ft.ControlEventHandler[ft.ListTile],
) -> ft.Control:
    """Return Report a problem with the app, which switches on ``SOURCE_URL`` (D-88).

    While the repository is private, an action that shares the log and diagnostics
    (``share_console_log()``); once it is public, an external row that opens a new
    issue in the in-app browser and reads "Opens in browser" (INFO-14, D-182). One
    row either way: under stress, one way to report; Share log stays on About this app.

    Args:
        source_url: ``SOURCE_URL``: None while the repository is private.
        packaged: A packaged build, whose share adds ``console.log``.
        sharing: The share sheet is up: the row is disabled until it closes.
        on_share: The row's action while the repository is private.
    """
    identifier = f"{SCREEN}.report_problem"
    if source_url is None:
        return action_row(
            identifier,
            ft.Icons.BUG_REPORT_OUTLINED,
            REPORT_PROBLEM,
            report_subtitle(packaged),
            on_share,
            disabled=sharing,
        )
    issue_url = new_issue_url(source_url)
    return LinkTile(
        REPORT_PROBLEM,
        issue_url,
        icon=ft.Icons.BUG_REPORT_OUTLINED,
        subtitle=shown_url(issue_url),
        identifier=identifier,
    )


def help_blocks(
    contacts: tuple[SafetyContact, ...],
    info: HelpInfo | None,
    quiet_room_credit: SponsorCredit | None = None,
    map_data: MapData | None = None,
) -> list[ft.Control]:
    """Return the page's blocks from its year data, in reading order; none without it.

    Args:
        contacts: The year's safety contacts; the card shows when there is one.
        info: The year's ``[help]`` table, or None; the loader refuses one without a
            contact, so the card always heads it.
        quiet_room_credit: The quiet room's sponsor, credited under its line
            (D-337); None when the year names none.
        map_data: The year's ``map.toml``, for the places' location cards and All
            maps; None or a year without plans shows neither.
    """
    map_data = map_data or MapData()
    blocks: list[ft.Control] = []
    if contacts:
        blocks.append(report_card(contacts, info.in_person if info else None))
    if info is not None:
        blocks += [
            SectionHeader("At the venue"),
            *(
                control
                for key, title, icon in PLACES
                for control in place(title, icon, key, info, map_data)
            ),
            SponsorCreditTile(
                quiet_room_credit, "Quiet room", f"{SCREEN}.quiet_room.sponsor"
            ),
            *(
                [
                    LinkTile(
                        ALL_MAPS,
                        "/map",
                        icon=ft.Icons.MAP_OUTLINED,
                        identifier=f"{SCREEN}.all_maps",
                    )
                ]
                if map_data.plans
                else []
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
    """Return the Report a concern card: a heading, a row per contact, the last line.

    An outlined card whose edge is ``error``, the colour M3 keeps for what is urgent;
    the heading and its icon say it too, so colour is never the only signal (D-33).
    Not one node (``semantic_container=False``, as the Lightning talks card, D-211): a
    screen reader stops on the heading, then on each row and its Copy, then the line.

    Args:
        contacts: The year's safety contacts, in the order they are listed.
        in_person: The line on danger (emergency services first) and on reporting to
            a staff member, or None.
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


def place(
    title: str, icon: ft.IconData, key: str, info: HelpInfo, map_data: MapData
) -> list[ft.Control]:
    """Return a place's row, then its ``LocationCard`` when it has a pin.

    Args:
        title: The place: "Information desk".
        icon: Its row's leading icon.
        key: Its ``HelpInfo`` field (``quiet_room``); its pin is ``<key>_pin``.
        info: The year's ``[help]``.
        map_data: The year's ``map.toml``.
    """
    controls = [place_row(title, getattr(info, key), icon, key)]
    card = spot_card(
        map_data, getattr(info, f"{key}_pin"), identifier=f"{SCREEN}.{key}.location"
    )
    if card is not None:
        # Under its row, in the page's gutter, as room detail's card is.
        controls.append(
            ft.Container(
                card, padding=ft.Padding.only(left=GUTTER, right=GUTTER, bottom=8)
            )
        )
    return controls


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
