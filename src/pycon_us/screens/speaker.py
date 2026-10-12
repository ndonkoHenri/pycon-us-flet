"""Speaker detail (``…/speaker/<id>``): a stub until P1 (SPKR-02, SPKR-03).

It lists the speaker's sessions as ``SessionRow``s with their stars, in schedule order,
as P1's detail will (ux.md §5.7): a tap pushes the session, one drill level. An unknown
id shows a not-found state under the back arrow (#90 settles P1's).
"""

import flet as ft

from pycon_us.favorites import use_favorites
from pycon_us.screens.stub import note, stub_body
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.badges import use_favorite_toggle
from pycon_us.ui.rows import SessionRow, use_session_views
from pycon_us.ui.scaffold import AppScaffold

SCREEN = "speaker"
"""The screen's name in its rows' semantics identifiers (decisions §M)."""


@ft.component
def SpeakerDetail(speaker_id: str) -> ft.View:
    """One speaker: their sessions as rows, in schedule order.

    Args:
        speaker_id: The speaker id, unquoted (D-42).
    """
    page = ft.context.page
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    data = conference.data
    speaker = data.speakers.get(speaker_id) if data else None
    sessions = (
        sorted(
            (s for s in data.sessions.values() if speaker_id in s.speaker_ids),
            key=lambda s: s.start,
        )
        if data and speaker
        else []
    )
    views = use_session_views(
        conference,
        [s.id for s in sessions],
        use_24h=bool(page.media and page.media.always_use_24_hour_format),
    )
    if speaker is None:
        return AppScaffold(
            title="Not found",
            body=stub_body(
                [note(f"No speaker {speaker_id!r} in this year's schedule.")]
            ),
        )
    return AppScaffold(
        title=speaker.name,
        body=stub_body(
            [
                SessionRow(
                    view,
                    view.session.id in favorites.ids,
                    on_toggle,
                    tokens,
                    screen=SCREEN,
                )
                for view in views
            ]
        ),
    )
