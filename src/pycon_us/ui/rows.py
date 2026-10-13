"""The rows lists are made of (decisions §M): sessions, notices, time gutters and links.

``SessionRow`` and ``NoticeRow`` are memoised components keyed by session id (D-153):
a list owner builds each session's ``SessionView`` once per feed version
(``use_session_views()``) and hands a row only ``(view, is_favorite, on_toggle,
tokens)``, so a star tap re-renders that one row. A row reads as one phrase, and its
star is a separate stop (D-33). ``TimeGutter`` is the slot's time column (D-158), and
``LinkTile`` a row that opens a page; #83 gives it its external form (ux.md §4.7). P1
adds ``SpeakerRow`` and P2 ``LocationCard`` here (ux.md §3.9).
"""

import re
from collections.abc import Sequence
from typing import cast

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.models import Session
from pycon_us.core.queries import SessionView, session_views
from pycon_us.locations import drill_href
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import Conference
from pycon_us.theme import Tokens
from pycon_us.ui.badges import (
    FavoriteButton,
    ToggleFavorite,
    TrackBadge,
    badge_row,
    badge_specs,
)

NOTICE_GROUP = "logistics"
"""The track group (``conference.toml``) whose sessions are notices: breaks, meals and
announcements get a compact ``NoticeRow`` without a star (D-31, SCHED-04)."""

_NBSP = "\u00a0"
"""A no-break space: "AM" stays on its time's line."""

_NOT_KEY = re.compile(r"[^a-z0-9]+")


def semantics_key(session_id: str) -> str:
    """Return a session id as the key of a semantics identifier (decisions §M).

    A synthetic break id holds spaces and colons (``break-Expo Hall AB-2026-05-15T08:
    00:00-07:00``, D-42), which a UI-test selector would have to match literally; the
    key is lower case, each run of other characters a ``-``:
    ``break-expo-hall-ab-2026-05-15t08-00-00-07-00``. Numeric ids stay as they are.

    Args:
        session_id: The session's id, unchanged everywhere else.
    """
    return _NOT_KEY.sub("-", session_id.lower()).strip("-")


def is_notice(session: Session, info: ConferenceInfo) -> bool:
    """Return whether a session shows as a notice rather than a session row (SCHED-04).

    Year data decides, not a list of names (ux.md §1, principle 9): every track of the
    ``logistics`` group, which in 2026 are ``Break`` and ``Informational``.

    Args:
        session: The session.
        info: The year's facts, with the track registry.
    """
    return info.track(session.track).group == NOTICE_GROUP


def use_session_views(
    conference: Conference, session_ids: Sequence[str], *, use_24h: bool
) -> tuple[SessionView, ...]:
    """Return the row views of some sessions, built once per feed version (D-153).

    A hook for the component that owns a list. The views are new objects only when
    the feed version, the ids or the clock format change, so the memoised rows given
    them skip their bodies on every other render (F34). Ids that are not in the
    feed are left out.

    Args:
        conference: The list owner's ``use_conference()`` store.
        session_ids: The sessions, in the order the list shows them.
        use_24h: Whether the device uses the 24-hour clock
            (``page.media.always_use_24_hour_format``).
    """
    zone = use_services().year.conference.zone
    data = conference.data
    ids = tuple(session_ids)
    return ft.use_memo(
        lambda: session_views(data, ids, zone, use_24h=use_24h) if data else (),
        [conference.version, ids, use_24h],
    )


def spoken_phrase(labels: Sequence[str], view: SessionView) -> str:
    """Return what a screen reader says for a session row: one phrase (D-33).

    "Talk. What's new in typing. 9:25 to 10:10 AM, Room 104A. Ana Lima." (ux.md
    §3.9): the badges, the title, the time and place, then the speakers, each a
    sentence, so TalkBack and VoiceOver pause between them.

    Args:
        labels: The badges' labels, in order (``badge_specs()``).
        view: The session's row view.
    """
    when = f"{view.spoken_when}, {view.place}" if view.place else view.spoken_when
    parts = (", ".join(labels), view.session.name, when, view.speakers)
    return " ".join(_sentence(part) for part in parts if part)


def notice_phrase(label: str, view: SessionView) -> str:
    """Return what a screen reader says for a notice row, as one phrase (D-33).

    "Notice. Registration opens, 7:00 AM." (ux.md §3.9), with the place when there
    is one: "Break. Lunch, 12:00 to 1:00 PM, Expo Hall AB."

    Args:
        label: The notice's track name, e.g. "Notice" or "Break".
        view: The notice's row view.
    """
    place = f", {view.place}" if view.place else ""
    return _sentence(f"{label}. {view.session.name}, {view.spoken_when}{place}")


def _sentence(text: str) -> str:
    """End ``text`` with a full stop unless it already ends a sentence."""
    return text if text.endswith((".", "?", "!", "…")) else f"{text}."


def _open_session(view_path: str, session_id: str) -> ft.ControlEventHandler:
    """Return a tap handler that pushes the session's detail on top of this View."""
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(drill_href(view_path, "session", session_id))

    return go


def SessionRow(
    view: SessionView,
    is_favorite: bool,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    screen: str,
) -> ft.Control:
    """Return a session in any list (SCHED-03): badges, title, time, place, speakers, star.

    A memoised component keyed by the session id (D-153): with stable props it
    re-renders only when its view, its star, the handler or the tokens change, so a
    star tap re-renders this one row. A tap on the text pushes the session's detail
    on top of the current View (D-17).

    The text is one node for screen readers, read as ``spoken_phrase()``; the star is
    its own stop, named and stateful (``FavoriteButton``). Nothing has a fixed height,
    so the row grows with the text: the title wraps to three lines, the rest in full.

    Args:
        view: The session's row view, the same object on every render.
        is_favorite: Whether the session is in My schedule.
        on_toggle: The list's one star handler (``use_favorite_toggle()``).
        tokens: The scheme's tokens (D-150): a memoised row does not read context.
        screen: The screen's name in semantics identifiers: the row's text is
            ``<screen>.session.<key>``, its star ``<screen>.favorite.<key>``, the key
            from ``semantics_key()``.
    """
    # ft.component's typing (its ParamSpec) leaves out the key= its wrapper takes.
    key = view.session.id
    return _SessionRow(
        view,
        is_favorite,
        on_toggle,
        tokens,
        screen=screen,
        key=key,  # pyright: ignore[reportCallIssue]
    )


@ft.memo
@ft.component
def _SessionRow(
    view: SessionView,
    is_favorite: bool,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    screen: str,
) -> ft.Control:
    """The body of ``SessionRow``; it runs only when the props change (F34)."""
    view_path = ft.use_view_path()
    info = use_services().year.conference  # a plain value: subscribes to nothing
    session = view.session
    specs = badge_specs(session, info, tokens)

    @report_errors
    async def star() -> None:
        await on_toggle(session.id)

    lines: list[ft.Control] = []
    if specs:
        lines.append(badge_row([TrackBadge(label, colors) for label, colors in specs]))
    lines.append(
        ft.Text(
            session.name,
            theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
            max_lines=3,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
    )
    lines.append(_meta(view))
    if view.speakers:
        lines.append(_secondary(view.speakers))
    key = semantics_key(session.id)
    text = ft.Semantics(
        label=spoken_phrase([label for label, _ in specs], view),
        identifier=f"{screen}.session.{key}",
        button=True,  # it opens the session: "…, button" (D-33)
        # The phrase replaces the texts, which would otherwise be read again after it.
        exclude_semantics=True,
        content=ft.Column(lines, spacing=4),
    )
    return ft.Row(
        [
            ft.MergeSemantics(  # the phrase and the tap's action: one node
                expand=True,
                content=ft.Container(
                    text,
                    ink=True,
                    on_click=_open_session(view_path, session.id),
                    padding=ft.Padding.only(left=16, top=12, right=4, bottom=12),
                ),
            ),
            ft.Container(
                FavoriteButton(
                    is_favorite,
                    star,
                    color=tokens.favorite,
                    identifier=f"{screen}.favorite.{key}",
                ),
                padding=ft.Padding.only(top=4, right=4),
            ),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def NoticeRow(view: SessionView, *, screen: str) -> ft.Control:
    """Return a break, meal or announcement (SCHED-04): a compact tile without a star.

    Memoised like ``SessionRow`` and keyed by the session id. Its icon is its
    track's, from the year data (a cup for breaks, an info sign for notices). It
    opens the session's detail only when there is something to read there (a
    description); otherwise it is not a button. It is its own node for screen
    readers, read as ``notice_phrase()``, and a button when it opens: without its own
    merge, a notice's text joined the slot's heading in TalkBack's tree (S2).

    Args:
        view: The notice's row view, the same object on every render.
        screen: The screen's name in its semantics identifier,
            ``<screen>.notice.<key>`` (``semantics_key()``).
    """
    # As in SessionRow: the key= is real, its type is not.
    return _NoticeRow(view, screen=screen, key=view.session.id)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _NoticeRow(view: SessionView, *, screen: str) -> ft.Control:
    """The body of ``NoticeRow``; it runs only when the props change (F34)."""
    view_path = ft.use_view_path()
    info = use_services().year.conference
    session = view.session
    track = info.track(session.track)
    tappable = bool(session.description)
    content = ft.Semantics(
        label=notice_phrase(track.short, view),
        identifier=f"{screen}.notice.{semantics_key(session.id)}",
        button=tappable,
        exclude_semantics=True,
        content=ft.Row(
            controls=[
                ft.Icon(
                    # A name the year data checks (test_config.py).
                    cast(ft.IconData, getattr(ft.Icons, track.icon)),
                    size=20,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Column(
                    [
                        ft.Text(
                            session.name, theme_style=ft.TextThemeStyle.TITLE_SMALL
                        ),
                        _meta(view, style=ft.TextThemeStyle.BODY_SMALL),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    )
    return ft.MergeSemantics(
        content=ft.Container(
            content,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=12,  # a card's shape (ux.md §3.6)
            # The title starts 12 dp down, on the gutter's and a SessionRow's line.
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            margin=ft.Margin.symmetric(horizontal=16, vertical=4),
            ink=tappable,
            on_click=_open_session(view_path, session.id) if tappable else None,
        )
    )


def TimeGutter(label: str) -> ft.Control:
    """Return a slot's time column (D-31, D-158): "9:25" over "AM", left of its rows.

    It has no fixed width: an invisible "10:00" / "AM" under the time sets it, so it
    grows with the text, is the same for every slot, and the rows beside it keep one
    left edge; a fixed 64 dp broke "7:30" over two lines at 200 % text (S2). It is a
    heading, so screen readers move slot by slot, and reads once, as ``label``.

    Args:
        label: The slot's start from ``timefmt.time_label()``: "9:25 AM", or "09:25"
            on a 24-hour clock, which needs no second line.
    """
    time, _, meridiem = label.partition(" ")

    # Roboto's digits are tabular (D-26), so "10:00" is as wide as any time.
    widest = _gutter_lines(
        "10:00" if meridiem else "00:00", "AM" if meridiem else "", 0
    )
    return ft.Semantics(
        header=True,
        label=label,
        exclude_semantics=True,  # else it reads "9:25 AM, 9:25, AM"
        content=ft.Container(
            ft.Stack([widest, _gutter_lines(time, meridiem)]),
            padding=ft.Padding.only(left=16, top=12, right=8),
        ),
    )


def _gutter_lines(time: str, meridiem: str, opacity: float = 1.0) -> ft.Control:
    """Return the gutter's time over its AM or PM, if any."""
    controls: list[ft.Control] = [
        ft.Text(time, theme_style=ft.TextThemeStyle.TITLE_SMALL)
    ]
    if meridiem:
        controls.append(
            ft.Text(
                meridiem,
                theme_style=ft.TextThemeStyle.LABEL_SMALL,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return ft.Column(controls, spacing=0, opacity=opacity)


def _meta(
    view: SessionView, *, style: ft.TextThemeStyle = ft.TextThemeStyle.BODY_MEDIUM
) -> ft.Control:
    """Return a row's time and place line: "9:25–10:10 AM · Room 104A".

    The time and the place are two texts in a wrapping row, so at large text a place
    that does not fit after the time moves to the next line whole, and the "·" ends
    the time's line rather than starting one; only a place wider than the row wraps
    inside itself. A no-break space keeps "AM" on its time's line.

    Args:
        view: The session's row view.
        style: The line's type style; a notice's is smaller.
    """
    when = view.when.replace(" ", _NBSP)
    if not view.place:
        return _secondary(when, style=style)
    return ft.Row(
        [
            _secondary(f"{when}{_NBSP}·", style=style),
            _secondary(view.place, style=style),
        ],
        wrap=True,
        spacing=4,  # a space's width at 100 %
        run_spacing=0,
    )


def _secondary(
    text: str, *, style: ft.TextThemeStyle = ft.TextThemeStyle.BODY_MEDIUM
) -> ft.Text:
    """Return a row's supporting text: its time, place or speakers, in the variant colour."""
    return ft.Text(text, theme_style=style, color=ft.Colors.ON_SURFACE_VARIANT)


def LinkTile(
    title: str,
    location: str,
    *,
    icon: ft.IconData | None = None,
    subtitle: str | None = None,
    identifier: str | None = None,
) -> ft.Control:
    """Return a row that pushes an in-app page: a title and a trailing chevron.

    A Material ``ListTile``, so it is at least 56 dp tall (72 with a subtitle), more
    than the 48 dp target (D-33), and grows with the text. ``CHEVRON_RIGHT`` marks an
    in-app page (ux.md §3.7). The row is one node for screen readers, read as its title
    and subtitle, a button; the icons are decorative.

    Args:
        title: The row's text, in sentence case.
        location: Where a tap goes: a page (``/more/speakers``) or, for a detail,
            ``drill_href(view_path, ...)``, so Back returns to this row's View.
        icon: A leading icon, outlined (D-27); none for rows of names.
        subtitle: A second line, if any.
        identifier: The node's semantics identifier for UI tests, e.g.
            ``more.speakers`` (decisions §M).
    """
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(location)

    tile: ft.Control = ft.ListTile(
        leading=ft.Icon(icon) if icon is not None else None,
        title=title,
        subtitle=subtitle,
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        on_click=go,
    )
    # An identifier without a label of its own joins the merged node (D-166).
    if identifier is not None:
        tile = ft.Semantics(identifier=identifier, content=tile)
    return ft.MergeSemantics(content=tile)
