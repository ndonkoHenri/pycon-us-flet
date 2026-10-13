"""The rows lists are made of (decisions §M): ``LinkTile``, ``SpeakerRow``, ``SpeakerTile``.

``LinkTile`` is a row that opens a link, ``SpeakerRow`` a speaker with their first
session (SPKR-01), ``SpeakerTile`` a speaker in a session's Speakers section (SESS-07).
P2 adds ``LocationCard`` here (ux.md §3.9); the session and notice rows are in
``ui.session_rows`` (D-184), the time gutter in ``ui.time_gutter`` (D-200).

``LinkTile`` opens its target by the link rule (INFO-14, ``ui.links``): an in-app page
is pushed and its row ends in ``CHEVRON_RIGHT``; a web page, a profile or a map leaves
the app and its row ends in ``OPEN_IN_NEW``; a phone or email row has a Copy button
beside it.
"""

from collections.abc import Callable
from typing import Any

import flet as ft

from pycon_us.core.models import Speaker
from pycon_us.core.speakers import SpeakerEntry, initials
from pycon_us.locations import drill_href
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.links import (
    COPY_TOOLTIPS,
    OPENS_IN,
    LinkKind,
    copy_contact,
    link_kind,
    open_link,
)
from pycon_us.ui.semantics import named, semantics_key

PLAIN_TOP = 16
"""A row without a subtitle: its leading icon's distance from the top (``TITLE_HEIGHT``)."""

SUBTITLED_TOP = 14
"""A row with a subtitle: its title's and its icons' distance from the top (``_tile``)."""


def LinkTile(
    title: str | ft.Text,
    target: str,
    *,
    icon: ft.IconData | None = None,
    subtitle: str | ft.Control | None = None,
    identifier: str | None = None,
    app: bool = False,
) -> ft.Control:
    """Return a row that opens ``target`` by the link rule: a page or a link.

    A Material ``ListTile``, so it is at least 56 dp tall (72 with a subtitle), more
    than the 48 dp target (D-33), and grows with the text. It is one node for screen
    readers, read as its title and subtitle: a button for a page; a link for anything
    else, whose ``OPEN_IN_NEW`` icon is read as "Opens in browser" (or "Opens in
    another app"). A phone or email row has a Copy button beside it, a stop of its
    own, as a session row's star is (ux.md §3.9).

    An in-app row is built here. An external one needs the session's services when it
    is tapped, so it is a component, which reads them (``use_services()``).

    Args:
        title: The row's text, in sentence case; a phone or email row says what a tap
            does ("Call the Code of Conduct hotline"). A ``Text`` for a title cut at
            some lines, as a session's name is (room detail's "Now in this room").
        target: Where a tap goes: a page (``/more/speakers``), for a detail
            ``drill_href(view_path, ...)`` so Back returns to this row's View, or a URL
            (``link_kind()``).
        icon: A leading icon, outlined (D-27); none for rows of names.
        subtitle: A second line, if any: for a phone or email row, the number or the
            address. A control for lines of their own (the Map's "Now:" line), read
            with the title as one phrase.
        identifier: The row's semantics identifier for UI tests, e.g.
            ``more.speakers`` (decisions §M); a Copy button gets ``<identifier>.copy``.
        app: A web address opens in the app that handles it: a social profile, a map.

    Raises:
        ValueError: ``target`` is not a link the app opens (``link_kind()``).
    """
    kind = link_kind(target, app=app)
    if kind is not LinkKind.PAGE:
        return _ExternalLinkTile(
            title, target, kind, icon=icon, subtitle=subtitle, identifier=identifier
        )
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(target)

    tile = _tile(title, icon, subtitle, ft.Icon(ft.Icons.CHEVRON_RIGHT), go)
    # An identifier without a label of its own joins the merged node (D-166).
    if identifier is not None:
        tile = ft.Semantics(identifier=identifier, content=tile)
    return ft.MergeSemantics(content=tile)


@ft.component
def _ExternalLinkTile(
    title: str | ft.Text,
    target: str,
    kind: LinkKind,
    *,
    icon: ft.IconData | None,
    subtitle: str | ft.Control | None,
    identifier: str | None,
) -> ft.Control:
    """The external form of ``LinkTile``: a link that leaves the app, maybe with Copy."""
    svc = use_services()

    @report_errors
    async def launch() -> None:
        await open_link(svc, target, app=kind is LinkKind.APP)

    @report_errors
    async def copy() -> None:
        await copy_contact(svc, target)

    opens_in = OPENS_IN.get(kind)
    trailing = None
    if opens_in is not None:
        trailing = ft.Icon(ft.Icons.OPEN_IN_NEW, semantics_label=opens_in)
    row = ft.MergeSemantics(
        content=ft.Semantics(
            identifier=identifier,
            link=True,
            content=_tile(title, icon, subtitle, trailing, launch),
        )
    )
    tooltip = COPY_TOOLTIPS.get(kind)
    if tooltip is None:
        return row
    copy_button: ft.Control = ft.IconButton(
        ft.Icons.CONTENT_COPY_OUTLINED, tooltip=tooltip, on_click=copy
    )
    if identifier is not None:
        copy_button = named(f"{identifier}.copy", copy_button)  # one node (D-190)
    return ft.Row(
        [
            ft.Container(row, expand=True),
            # 12 dp from the edge puts the 24 dp icon of the 48 dp button where a
            # ListTile's trailing icon sits, so the column of icons lines up; from the
            # top it sits level with the leading icon (_tile), so at 200 % text it
            # stays beside the first line instead of the block's middle.
            ft.Container(
                copy_button,
                padding=ft.Padding.only(top=icon_top(subtitle) - 12, right=12),
            ),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def _tile(
    title: str | ft.Text,
    icon: ft.IconData | None,
    subtitle: str | ft.Control | None,
    trailing: ft.Control | None,
    on_click: Callable[[], Any],
) -> ft.ListTile:
    """A link row's ``ListTile``, its icons beside the title's first line at any height.

    M3's default centres the icons against the whole block, which at 200 % puts them
    beside the middle of a four-line title, far from the line they belong to. Without a
    subtitle, ``TITLE_HEIGHT`` centres a 56 dp row's icons and keeps them 16 dp from
    the top of a taller one. With a subtitle it would not do: it centres the trailing
    icon of a 72 dp row and moves both icons when the row grows (the Map's "Now:" line
    comes and goes with the minute), while the title moves the other way. So a row with
    a subtitle puts its icons and its title ``SUBTITLED_TOP`` from the top (``TOP``
    and ``min_vertical_padding``): the 24 dp title line and the 24 dp icons share one
    centre, 26 dp down, at every height, and a two-line row stays 72 dp (14 + 24 + 20
    + 14).
    """
    if subtitle is None:
        alignment, padding = ft.ListTileTitleAlignment.TITLE_HEIGHT, None
    else:
        alignment, padding = ft.ListTileTitleAlignment.TOP, SUBTITLED_TOP
    return ft.ListTile(
        leading=ft.Icon(icon) if icon is not None else None,
        title=title,
        subtitle=subtitle,
        trailing=trailing,
        on_click=on_click,
        title_alignment=alignment,
        min_vertical_padding=padding,
    )


def icon_top(subtitle: str | ft.Control | None) -> int:
    """Return how far ``_tile`` puts its leading icon from the row's top, in dp."""
    return PLAIN_TOP if subtitle is None else SUBTITLED_TOP


AVATAR_RADIUS = 24
"""A speaker row's avatar, in dp: a 48 dp circle (ux.md §3.9)."""

SPEAKER_TILE_HEIGHT = 2 * AVATAR_RADIUS + 16
"""A ``SpeakerTile``'s least height, in dp: the avatar with 8 dp above and below."""


def speaker_avatar(
    speaker: Speaker,
    *,
    radius: int = AVATAR_RADIUS,
    initials_style: ft.TextThemeStyle | None = None,
) -> ft.CircleAvatar:
    """Return a speaker's avatar, 48 dp unless told otherwise: the photo over the initials.

    The initials show while the photo loads, offline and when the feed has none, in
    ``primary_container`` with its ``on_`` pair, a contrast the theme's test checks.
    Flutter draws them without the text scale, so they always fit the circle.
    Decorative for screen readers: the row or the heading beside it says the name.

    Args:
        speaker: The directory speaker.
        radius: The circle's radius in dp: a row's 24, or the speaker page's 48.
        initials_style: The initials' type, for a larger circle; None keeps the
            avatar's own (``TITLE_MEDIUM``), which suits 48 dp.
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

    Built as an in-app ``LinkTile`` is, so it sits with the page's other rows that push
    (the room tile): a Material ``ListTile``, its chevron saying that a tap opens the
    speaker's page, and one node for screen readers, the name as a button; the
    avatar's initials stay out of it. At least 64 dp tall, Material's 8 dp above and
    below the 48 dp avatar: the default 56 dp left stacked avatars 8 dp apart, which
    read as one column (D-197). No subtitle: the speaker's page, one
    tap away, has the bio and their sessions (D-197).

    Args:
        speaker: The directory speaker.
        target: Their page, ``drill_href(view_path, "speaker", speaker.id)``, so Back
            returns to the session (D-17).
        identifier: The row's semantics identifier, e.g. ``session.speaker.<key>``.
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
    return ft.MergeSemantics(content=ft.Semantics(identifier=identifier, content=tile))


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
        entry: The speaker's entry (``core.speakers.directory()``).
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
    photo loads, offline and when there is none, in ``primary_container``. The row
    reads as one phrase for screen readers (``speaker_phrase()``), a button; nothing
    has a fixed height but the avatar, so it grows with the text.

    Args:
        entry: The speaker's entry, equal on every render while it is unchanged.
        screen: The screen's name in the row's semantics identifier,
            ``<screen>.speaker.<key>`` (decisions §M, ``semantics_key()``).
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _SpeakerRow(entry, screen=screen, key=entry.speaker.id)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _SpeakerRow(entry: SpeakerEntry, *, screen: str) -> ft.Control:
    """The body of ``SpeakerRow``; it runs only when its entry changes (F34)."""
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
        **cut: ``max_lines`` and ``overflow``, for a line that may be cut short.
    """
    return ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
        **cut,
    )
