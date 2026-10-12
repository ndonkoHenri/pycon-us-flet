"""Sponsor detail (``…/sponsor/<slug>``): a stub until sponsors land in P2 (SPON)."""

import flet as ft

from pycon_us.screens.stub import note, stub_view


@ft.component
def SponsorDetail(sponsor_slug: str) -> ft.View:
    """One sponsor: its slug only, until P2.

    Args:
        sponsor_slug: The sponsor's slug, unquoted.
    """
    return stub_view(
        title="Sponsor", controls=[note(f"Sponsor {sponsor_slug!r} arrives in P2.")]
    )
