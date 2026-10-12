"""Sponsor detail (``…/sponsor/<slug>``): a stub until sponsors land in P2 (SPON)."""

import flet as ft

from pycon_us.screens.stub import note, stub_body
from pycon_us.ui.scaffold import AppScaffold


@ft.component
def SponsorDetail(sponsor_slug: str) -> ft.View:
    """One sponsor: its slug only, until P2.

    Args:
        sponsor_slug: The sponsor's slug, unquoted.
    """
    return AppScaffold(
        title="Sponsor",
        body=stub_body([note(f"Sponsor {sponsor_slug!r} arrives in P2.")]),
    )
