"""Speaker detail (``…/speaker/<id>``): a stub until P1 (SPKR-02, SPKR-03).

It lists the speaker's sessions as ``SessionRow``s with their stars, in schedule order
under a heading per day, as P1's detail will (ux.md §5.7, #99): a tap pushes the
session, one drill level. An unknown id shows a not-found state under the back arrow
(#90 settles P1's).
"""

import flet as ft

from pycon_us.core.models import ConferenceData
from pycon_us.core.row_views import by_day
from pycon_us.core.timefmt import day_heading
from pycon_us.favorites import use_favorites
from pycon_us.screens.stub import not_found, stub_body
from pycon_us.services import use_services
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.badges import use_favorite_toggle
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.session_rows import SessionRow, use_session_views

SCREEN = "speaker"
"""The screen's name in its rows' semantics identifiers (decisions §M)."""


@ft.component
def SpeakerDetail(speaker_id: str) -> ft.View:
    """One speaker: their sessions as rows, by day, in schedule order.

    Args:
        speaker_id: The speaker id, unquoted (D-42).
    """
    page = ft.context.page
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    zone = use_services().year.conference.zone
    data = conference.data
    speaker = data.speakers.get(speaker_id) if data else None
    # Once per feed version: the owner re-renders on every star tap (D-153).
    ids = ft.use_memo(
        lambda: _session_ids(data, speaker_id), [conference.version, speaker_id]
    )
    views = use_session_views(
        conference,
        ids,
        use_24h=bool(page.media and page.media.always_use_24_hour_format),
    )
    if speaker is None:
        return AppScaffold(
            title="Not found",
            body=stub_body(
                [
                    not_found(
                        "This speaker isn't in the current schedule",
                        icon=ft.Icons.PERSON_OFF_OUTLINED,
                        action="All speakers",
                        location="/more/speakers",
                        identifier="speaker.not_found",
                    )
                ]
            ),
        )
    controls: list[ft.Control] = []
    # A speaker's sessions can be on different days, and a row says only its time.
    for day, day_views in by_day(views, zone):
        controls.append(SectionHeader(day_heading(day)))
        controls.extend(
            SessionRow(
                view,
                view.session.id in favorites.ids,
                on_toggle,
                tokens,
                screen=SCREEN,
            )
            for view in day_views
        )
    return AppScaffold(title=speaker.name, body=stub_body(controls))


def _session_ids(data: ConferenceData | None, speaker_id: str) -> tuple[str, ...]:
    """Return the ids of a speaker's sessions, in schedule order."""
    if data is None:
        return ()
    sessions = (s for s in data.sessions.values() if speaker_id in s.speaker_ids)
    return tuple(s.id for s in sorted(sessions, key=lambda s: s.start))
