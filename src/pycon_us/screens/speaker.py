"""Speaker detail (``…/speaker/<id>``): who, when they speak, then their bio (SPKR-03).

The intro is the speaker's photo over their initials and their name, the page's
level-1 heading (the app bar's title stays empty, as on session detail, D-186). Then
"when do they speak", before the bio (ux.md §5.7): every session that links them, by
day under level-2 day headings (F40), as ``SessionRow``s with their stars (D-184), each
day one memoised item (``ui.day_groups``, D-153). The rows leave out the speaker the
page names: their speakers line names only the co-speakers, "With Ana Lima", in what
they show and what they say (``session_view(of_speaker=...)``, D-203). Then "About",
the bio as Markdown whose links open by the link rule (``ui.links.feed_markdown``,
D-116, D-197), left out when the feed's bio is only a placeholder dash. A speaker
the feed links to no session (neither recorded feed has one) shows an empty state
where the days would be, as a track page without sessions does (D-199).

A row pushes its session one level down, and the session's speaker tile pushes this
page, so session → speaker → session → room is a stack that Back pops one step at a
time (D-17, SESS-12). An unknown id shows the not-found state under the back arrow,
with the Speakers list as the way out (D-186); without data the page loads and fails
as the other screens do (ux.md §4.1).
"""

import flet as ft

from pycon_us.core.models import Speaker
from pycon_us.core.speakers import has_bio, speaker_sessions
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.day_groups import DayGroup
from pycon_us.ui.favorite import use_favorite_toggle
from pycon_us.ui.links import feed_markdown
from pycon_us.ui.page_title import PageTitle
from pycon_us.ui.rows import speaker_avatar
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.session_rows import changes_of, use_recent_changes, use_session_views
from pycon_us.ui.states import EmptyState, NoDataState, not_found
from pycon_us.ui.widths import READING, sides, use_margin

SCREEN = "speaker"
"""The screen's name in its semantics identifiers (decisions §M)."""

NOT_FOUND = "This speaker isn't in the current schedule"
"""The empty state of an unknown id (ux.md §4.6)."""

NO_SESSIONS = "No sessions in the current schedule"
"""The empty state of a speaker the feed links to no session (ux.md §4.6)."""

PHOTO_RADIUS = 48
"""The intro's avatar, in dp: a 96 dp circle (ux.md §5.7), twice a row's."""


@ft.component
def SpeakerDetail(speaker_id: str) -> ft.View:
    """One speaker: their photo and name, their sessions by day, then their bio.

    Args:
        speaker_id: The speaker id, unquoted (D-42).
    """
    page = ft.context.page
    svc = use_services()
    margin = use_margin(READING)  # its width class (D-305)
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    prefs = use_prefs()
    data = conference.data
    speaker = data.speakers.get(speaker_id) if data else None
    # Once per feed version: the page re-renders on every star tap, and its day items
    # compare these objects (D-153).
    days = ft.use_memo(
        lambda: speaker_sessions(data, speaker_id) if data else (),
        [conference.version, speaker_id],
    )
    ids = ft.use_memo(lambda: [s.id for day in days for s in day.sessions], [days])
    all_views = use_session_views(
        conference,
        ids,
        use_24h=bool(page.media and page.media.always_use_24_hour_format),
        of_speaker=speaker.name if speaker else None,
    )
    views = ft.use_memo(lambda: {v.session.id: v for v in all_views}, [all_views])
    changes = use_recent_changes()

    if data is None:
        no_data = NoDataState(conference, svc, f"{SCREEN}.no_data")
        # No name to show in the page yet: the bar names it, the page's level-1
        # heading, as "Not found" does below (D-211).
        return AppScaffold(
            title="Speaker",
            source=__name__,
            body=ft.ListView([no_data], expand=True, padding=sides(margin)),
        )
    if speaker is None:
        return AppScaffold(
            title="Not found",
            source=__name__,
            body=ft.ListView(
                [
                    not_found(
                        NOT_FOUND,
                        icon=ft.Icons.PERSON_OFF_OUTLINED,
                        action="All speakers",
                        location="/more/speakers",
                        identifier=f"{SCREEN}.not_found",
                    )
                ],
                expand=True,
                padding=sides(margin),
            ),
        )
    items: list[ft.Control] = [intro(speaker, large_text=prefs.time_above)]
    if not days:  # a directory speaker whose sessions left the feed
        items.append(
            EmptyState(
                NO_SESSIONS,
                icon=ft.Icons.EVENT_BUSY_OUTLINED,
                # No button: the app refreshes the feed on its own (D-175).
                body="They show here as soon as the schedule lists them.",
                identifier=f"{SCREEN}.empty",
            )
        )
    # A speaker's sessions can be on different days, and a row says only its time.
    items.extend(
        DayGroup(
            day,
            views,
            favorites.ids & {s.id for s in day.sessions},
            changes_of(changes, (s.id for s in day.sessions)),
            on_toggle,
            tokens,
            screen=SCREEN,
            level=2,
        )
        for day in days
    )
    if has_bio(speaker):  # not the feed's lone "-" for a bio nobody wrote
        items.append(SectionHeader("About", level=2))
        items.append(feed_markdown(speaker.bio_md, svc, identifier=f"{SCREEN}.bio"))
    body = ft.ListView(items, expand=True, padding=sides(margin, bottom=24))
    # The heading below names the page, so the app bar's title stays empty (D-186).
    return AppScaffold(title="", source=__name__, body=body)


def intro(speaker: Speaker, *, large_text: bool) -> ft.Control:
    """Return the page's intro: the speaker's photo over their initials, then the name.

    Centred (ux.md §5.7). The name is the page's heading (level 1, F40), a
    ``PageTitle`` selectable to copy (D-26), where a long name wraps rather than
    being cut as an app bar title is at large text (D-186). The photo is decorative:
    the heading says whose it is.

    Args:
        speaker: The directory speaker.
        large_text: The text is large for the width (``Prefs.time_above``): the
            name steps down (D-328).
    """
    photo = ft.Semantics(
        exclude_semantics=True,  # the initials would be read before the name
        content=speaker_avatar(
            speaker,
            radius=PHOTO_RADIUS,
            initials_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
        ),
    )
    name = PageTitle(
        speaker.name,
        identifier=f"{SCREEN}.title",
        large_text=large_text,
        centred=True,
        selectable=True,
    )
    return ft.Container(
        ft.Column(
            [photo, name],
            spacing=16,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.only(left=16, top=8, right=16, bottom=8),
    )
