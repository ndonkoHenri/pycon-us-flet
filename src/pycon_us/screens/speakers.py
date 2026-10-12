"""Speakers (``/more/speakers``): a stub of the directory until P1 (SPKR-01).

Every speaker, by name folded as search folds it (D-46), each opening its detail.
"""

import flet as ft

from pycon_us.core.queries import fold
from pycon_us.locations import drill_href
from pycon_us.screens.stub import nav_tile, stub_view
from pycon_us.state import use_conference


@ft.component
def Speakers() -> ft.View:
    """The Speakers page: every speaker in the directory, by name."""
    view_path = ft.use_view_path()
    conference = use_conference()
    speakers = conference.data.speakers.values() if conference.data else ()
    return stub_view(
        title="Speakers",
        controls=[
            nav_tile(speaker.name, drill_href(view_path, "speaker", speaker.id))
            for speaker in sorted(speakers, key=lambda speaker: fold(speaker.name))
        ],
    )
