"""The speaker rows lists are made of: `SpeakerRow`, `SpeakerTile` and the avatar.

`SpeakerRow` is a speaker with their first session (SPKR-01), `SpeakerTile` a speaker
in a session's Speakers section (SESS-07). The row that opens a link is
`ui.link_tile`'s, `LocationCard` is `ui.location_card`'s (#389); the session and
notice rows are in `ui.session_rows` (D-184), the time gutter in `ui.time_gutter`
(D-200).
"""

from typing import Any

import flet as ft

from pycon_us.core.models import Speaker
from pycon_us.core.speakers import SpeakerEntry, initials
from pycon_us.locations import drill_href
from pycon_us.services.errors import report_errors
from pycon_us.ui.semantics import named, semantics_key
from pycon_us.year_keynotes import KeynoteSpeaker

AVATAR_RADIUS = 24
"""A speaker row's avatar, in dp: a 48 dp circle (ux.md §3.9)."""

SPEAKER_TILE_HEIGHT = 2 * AVATAR_RADIUS + 16
"""A `SpeakerTile`'s least height, in dp: the avatar with 8 dp above and below."""


def speaker_avatar(
    speaker: Speaker | KeynoteSpeaker,
    *,
    radius: int = AVATAR_RADIUS,
    initials_style: ft.TextThemeStyle | None = None,
) -> ft.CircleAvatar:
    """Return a speaker's avatar, 48 dp unless told otherwise: the photo over the initials.

    The initials show while the photo loads, offline and when the feed has none, in
    `primary_container` with its `on_` pair, a contrast the theme's test checks.
    Flutter draws them without the text scale, so they always fit the circle.
    Decorative for screen readers: the row or the heading beside it says the name.

    Args:
        speaker: The directory speaker, or a keynote's person (D-217).
        radius: The circle's radius in dp: a row's 24, or the speaker page's 48.
        initials_style: The initials' type, for a larger circle; None keeps the
            avatar's own (`TITLE_MEDIUM`), which suits 48 dp.
    """
    letters = initials(speaker.name)
    # A theme style brings the text theme's colour, so the pair is named again.
    text = (
        ft.Text(letters)
        if initials_style is None
        else ft.Text(
            letters, theme_style=initials_style, color=ft.Colors.ON_PRIMARY_CONTAINER
        )
    )
    return ft.CircleAvatar(
        content=text,
        foreground_image_src=speaker.photo_url or None,
        bgcolor=ft.Colors.PRIMARY_CONTAINER,
        color=ft.Colors.ON_PRIMARY_CONTAINER,
        radius=radius,
    )


def SpeakerTile(speaker: Speaker, target: str, *, identifier: str) -> ft.Control:
    """Return a speaker in a session's Speakers section (SESS-07): avatar, name, chevron.

    Built as an in-app `LinkTile` is, so it sits with the page's other rows that push
    (the room tile): a Material `ListTile`, its chevron saying that a tap opens the
    speaker's page, and one node for screen readers, the name as a button; the
    avatar's initials stay out of it. At least 64 dp tall, Material's 8 dp above and
    below the 48 dp avatar: the default 56 dp left stacked avatars 8 dp apart, which
    read as one column (D-197). No subtitle: the speaker's page, one
    tap away, has the bio and their sessions (D-197).

    Args:
        speaker: The directory speaker.
        target: Their page, `drill_href(view_path, "speaker", speaker.id)`, so Back
            returns to the session (D-17).
        identifier: The row's semantics identifier, e.g. `session.speaker.<key>`.
    """
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(target)

    tile = ft.ListTile(
        # Excluded: the name is the row's label, and the initials would be read first.
        leading=ft.Semantics(exclude_semantics=True, content=speaker_avatar(speaker)),
        title=speaker.name,
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        on_click=go,
        title_alignment=ft.ListTileTitleAlignment.TITLE_HEIGHT,
        min_height=SPEAKER_TILE_HEIGHT,
    )
    return named(identifier, tile)


def more_label(more: int) -> str:
    """Return the line a speaker row adds under its first session: "+1 more".

    Args:
        more: How many other sessions the speaker has; at least 1.
    """
    return f"+{more}\N{NO-BREAK SPACE}more"


def speaker_phrase(entry: SpeakerEntry) -> str:
    """Return what a screen reader says for a speaker row: one phrase (D-33).

    "Ana Lima, speaking: Typing deep dive" (ux.md §3.9), with "and 1 more session"
    when there are more, and the name alone for a speaker without a session.

    Args:
        entry: The speaker's entry (`core.speakers.directory()`).
    """
    name = entry.speaker.name
    if entry.first_session is None:
        return name
    phrase = f"{name}, speaking: {entry.first_session.name}"
    if entry.more:
        sessions = "session" if entry.more == 1 else "sessions"
        phrase = f"{phrase}, and {entry.more} more {sessions}"
    return phrase


def SpeakerRow(entry: SpeakerEntry, *, screen: str) -> ft.Control:
    """Return a speaker in a list (SPKR-01): avatar, name and first session.

    A memoised component keyed by the speaker id, as session rows are (D-153): given
    the same entry it skips its body, so a filter keystroke re-renders no row that
    stays. A tap pushes the speaker's detail on top of the current View (D-17).

    The avatar is the feed's photo over the speaker's initials, which show while the
    photo loads, offline and when there is none, in `primary_container`. The row
    reads as one phrase for screen readers (`speaker_phrase()`), a button; nothing
    has a fixed height but the avatar, so it grows with the text.

    Args:
        entry: The speaker's entry, equal on every render while it is unchanged.
        screen: The screen's name in the row's semantics identifier,
            `<screen>.speaker.<key>` (decisions §M, `semantics_key()`).
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _SpeakerRow(entry, screen=screen, key=entry.speaker.id)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _SpeakerRow(entry: SpeakerEntry, *, screen: str) -> ft.Control:
    """The body of `SpeakerRow`; it runs only when its entry changes (F34)."""
    view_path = ft.use_view_path()
    page = ft.context.page
    speaker = entry.speaker

    @report_errors
    def go() -> None:
        page.navigate(drill_href(view_path, "speaker", speaker.id))

    lines: list[ft.Control] = [
        ft.Text(speaker.name, theme_style=ft.TextThemeStyle.TITLE_MEDIUM)
    ]
    if entry.first_session is not None:
        # Two lines at most: at large text a long title would make the row a page;
        # the speaker's own page has it in full, and the phrase says it whole.
        lines.append(
            _supporting(
                entry.first_session.name,
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
            )
        )
    if entry.more:
        # A line of its own, so a long title never cuts it.
        lines.append(_supporting(more_label(entry.more)))
    avatar = speaker_avatar(speaker)
    text = ft.Semantics(
        label=speaker_phrase(entry),
        identifier=f"{screen}.speaker.{semantics_key(speaker.id)}",
        button=True,  # it opens the speaker: "…, button" (D-33)
        # The phrase replaces the texts and the initials, which would be read too.
        exclude_semantics=True,
        content=ft.Row(
            [avatar, ft.Column(lines, spacing=2, expand=True)],
            spacing=16,
            # Beside the name at any text size, not the middle of a wrapped title.
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    )
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            text,
            ink=True,
            on_click=go,
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        )
    )


def _supporting(text: str, **cut: Any) -> ft.Text:
    """Return a speaker row's supporting line, in the variant colour.

    Args:
        text: The line.
        **cut: `max_lines` and `overflow`, for a line that may be cut short.
    """
    return ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
        **cut,
    )
