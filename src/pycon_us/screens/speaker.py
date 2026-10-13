"""Speaker detail (``…/speaker/<id>``): a stub until P1 (SPKR-02, SPKR-03).

It links to the speaker's sessions, one drill level each. An unknown id shows a
not-found state under the back arrow (#90 settles P1's).
"""

import flet as ft

from pycon_us.locations import drill_href
from pycon_us.screens.stub import nav_tile, not_found, stub_body
from pycon_us.state import use_conference
from pycon_us.ui.scaffold import AppScaffold


@ft.component
def SpeakerDetail(speaker_id: str) -> ft.View:
    """One speaker: links to their sessions, in schedule order.

    Args:
        speaker_id: The speaker id, unquoted (D-42).
    """
    view_path = ft.use_view_path()
    conference = use_conference()
    data = conference.data
    speaker = data.speakers.get(speaker_id) if data else None
    if data is None or speaker is None:
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
    sessions = sorted(
        (s for s in data.sessions.values() if speaker_id in s.speaker_ids),
        key=lambda s: s.start,
    )
    return AppScaffold(
        title=speaker.name,
        body=stub_body(
            [nav_tile(s.name, drill_href(view_path, "session", s.id)) for s in sessions]
        ),
    )
