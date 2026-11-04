"""A sponsor credit's row: "Wi-Fi provided by Temporal" (D-37, INFO-09, MAP-10, D-337).

Sponsors who provide something are credited where it is: on the Wi-Fi page, and on
Venue & hours' Quiet room card and Help & safety's Quiet room line. The year data names
each sponsor by its slug (`content.toml`'s `[sponsor_credits]`), which the tests
and the snapshot tool check against the feed; Ionic guessed it from a substring of the
name. The row is a `LinkTile` with the sponsor's logo that pushes its detail,
`…/sponsor/<slug>`, over the page, so Back returns there (D-17), read as one phrase
("Wi-Fi provided by Temporal, Partner sponsor, button"). A sponsor the current feed
lacks, or no feed yet, hides the row: a credit without its sponsor's page would lead
nowhere.
"""

import flet as ft

from pycon_us.core.models import Sponsor
from pycon_us.core.sponsors import sponsor_by_slug
from pycon_us.locations import drill_href
from pycon_us.state import use_conference
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.rows import LinkTile
from pycon_us.year_info import SponsorCredit

LOGO = 40
"""The logo tile's size, in dp: a row's leading control, as a sprint project's is."""


def credit_words(what: str, sponsor: Sponsor) -> str:
    """Return the row's title: "Wi-Fi provided by Temporal".

    Args:
        what: What the sponsor provides, in sentence case: "Wi-Fi", "Quiet room".
        sponsor: The sponsor.
    """
    return f"{what} provided by {sponsor.name}"


@ft.component
def SponsorCreditTile(
    credit: SponsorCredit | None, what: str, identifier: str
) -> ft.Control:
    """Return the credit's row, or an empty control when there is nothing to credit.

    Args:
        credit: The year's credit for this place; None when the year has none.
        what: What the sponsor provides, in sentence case: "Wi-Fi".
        identifier: The row's semantics identifier: `wifi.sponsor`.
    """
    data = use_conference().data
    view_path = ft.use_view_path()
    sponsor = (
        None if credit is None or data is None else sponsor_by_slug(data, credit.slug)
    )
    if sponsor is None:
        return ft.Container()  # takes no room and is no node
    return LinkTile(
        credit_words(what, sponsor),
        drill_href(view_path, "sponsor", sponsor.slug),
        icon=logo_tile(sponsor.name, sponsor.logo_url, size=LOGO),
        subtitle=f"{sponsor.level} sponsor",
        identifier=identifier,
    )
