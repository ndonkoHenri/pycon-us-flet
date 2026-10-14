"""Session detail's extras (ux.md §5.5): Share, posters, an open space's image and link.

- **Share** (NEW-06) sends the session's title, when and where in conference time with
  its zone, and its public page when it has one (``row_views.share_text()``), through
  the platform's share sheet (``ui.share``).
- **Posters** (SESS-09): the Posters row of the Schedule stands for the poster session,
  so its detail lists the posters (``timeline.posters()``) as the session rows every
  list uses, with their stars; each pushes its poster's detail on top of this one, so
  Back returns here (D-17).
- **An open space** (SESS-11) shows its image, which the feed links on the conference's
  asset host, and its entry on the site's open-spaces page, a link that leaves the app
  (the link rule, ``ui.links``).

A module of its own, so ``screens/session.py`` stays under about 400 lines (D-66).
"""

from urllib.parse import urlsplit

import flet as ft

from pycon_us.core.models import Session
from pycon_us.core.row_views import share_text
from pycon_us.core.slugs import slugify_room
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens
from pycon_us.ui.badges import ToggleFavorite
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.session_rows import SessionRow, use_session_views
from pycon_us.ui.share import share_text as share_sheet

SCREEN = "session"
"""The screen's name in its semantics identifiers (decisions §M)."""

SHARE_TOOLTIP = "Share session"
"""The Share button's tooltip, which is also its name (D-27)."""

OPEN_SPACE = "open-space"
"""The kind of an open space's session (DATA-05): it has an image and a site entry."""

IMAGE_RATIO = 16 / 9
"""The open-space image's frame: the content's width, and nine sixteenths of it high."""

IMAGE_BLUR = 24
"""How much the frame's copy of the image is blurred, in logical pixels (sigma)."""

IMAGE_SCRIM = 0.3
"""The opacity of the surface colour over the blurred copy, so the image stands out."""

IMAGE_FADE_MS = 250
"""How long a loaded image takes to fade in (ux.md §3.8)."""

IMAGE_ERROR = "Couldn't load the image"
"""What the frame says when the image does not load: offline, or gone from the host."""


def site_title(url: str) -> str:
    """Return a link's words to a session's page: "Open on us.pycon.org" (D-186)."""
    return f"Open on {urlsplit(url).hostname}"


@ft.component
def ShareButton(session: Session) -> ft.Control:
    """The app bar's Share (NEW-06): the share sheet with the session's text.

    Disabled while the sheet is up, so a second tap does not ask for a second sheet.
    Every session has it, a break too: its time and place are worth sending.

    Args:
        session: The session the page shows.
    """
    page = ft.context.page
    svc = use_services()
    sharing, set_sharing = ft.use_state(False)
    info = svc.year.conference

    @report_errors
    async def share() -> None:
        use_24h = bool(page.media and page.media.always_use_24_hour_format)
        text = share_text(session, info.name, info.zone, use_24h=use_24h)
        set_sharing(True)
        try:
            await share_sheet(svc, text, subject=session.name)
        finally:
            set_sharing(False)

    return named(
        f"{SCREEN}.share",
        ft.IconButton(
            ft.Icons.SHARE_OUTLINED,
            tooltip=SHARE_TOOLTIP,
            on_click=share,
            disabled=sharing,
        ),
    )


@ft.component
def Posters(
    row: Session,
    posters: tuple[Session, ...],
    saved: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
) -> ft.Control:
    """The posters of a Posters row's detail (SESS-09), under "Posters (25)".

    Each is a ``SessionRow`` with its star, as on the Posters track page, without what
    the page above already says: the "Poster" badge, the time and the place, which
    every poster shares with the row (DATA-07). The rows are memoised and their views
    built once per feed version, so a star tap re-renders one row (D-153).

    Args:
        row: The Posters row the page shows.
        posters: Its posters (``timeline.posters()``), never empty.
        saved: The saved session ids (``Favorites.ids``).
        on_toggle: The page's one star handler (``use_favorite_toggle()``).
        tokens: The scheme's tokens, for the rows (D-150).
    """
    page = ft.context.page
    info = use_services().year.conference
    views = use_session_views(
        use_conference(),
        [poster.id for poster in posters],
        use_24h=bool(page.media and page.media.always_use_24_hour_format),
        in_room=slugify_room(row.display_location),
    )
    omit = frozenset({info.track_name(row.track)})
    count = len(views)
    header = SectionHeader(
        f"Posters ({count})",
        level=2,
        top=0,
        spoken=f"{count} poster" if count == 1 else f"{count} posters",
    )
    rows = [
        SessionRow(
            view,
            view.session.id in saved,
            on_toggle,
            tokens,
            screen=SCREEN,
            omit=omit,
            show_time=False,
        )
        for view in views
    ]
    return ft.Column([header, *rows], spacing=0)


def open_space_extras(session: Session, *, fade_ms: int) -> list[ft.Control]:
    """Return an open space's image and its site link (SESS-11), as the page's sections.

    Args:
        session: The open space.
        fade_ms: How long the image fades in once loaded (``prefs.motion_ms()``).
    """
    extras: list[ft.Control] = []
    if session.image_url:
        extras.append(_image(session, fade_ms=fade_ms))
    if session.url:  # its entry on the site's open-spaces page, by the link rule
        extras.append(
            LinkTile(
                site_title(session.url),
                session.url,
                icon=ft.Icons.LANGUAGE,
                identifier=f"{SCREEN}.site",
            )
        )
    return extras


def _image(session: Session, *, fade_ms: int) -> ft.Control:
    """The open space's image, scaled down to fit a 16:9 frame the content's width.

    A small image keeps its size, centred, rather than blur at the frame's. Around an
    image of other proportions (a portrait flyer, a screenshot) the frame shows the
    same image again, cropped to fill it and blurred under a scrim, so it is the
    picture's own colours rather than bars of grey (D-206). The frame's fill shows
    while the image loads, and the image fades in over it. No ``placeholder_src``:
    Flet sizes the placeholder with the image's own width and height (F44), which an
    image of unknown size does not have, so it could not fill the frame. When the
    image does not load, the frame says so (``error_content``). Its name for screen
    readers is the session's: the feed has no description of the picture.
    """
    fade = ft.Animation(fade_ms, ft.AnimationCurve.EASE_OUT)
    backdrop = ft.Image(
        session.image_url,
        # No fade: Flet lays a fading image out in a loose Stack, so the copy would
        # keep the image's own proportions instead of covering the frame (F45).
        fit=ft.BoxFit.COVER,
        exclude_from_semantics=True,  # the same picture: the one below names it
        error_content=ft.Container(),  # the image's own error says it once
        left=0,  # left to bottom 0: it fills the frame
        top=0,
        right=0,
        bottom=0,
    )
    scrim = ft.Container(
        blur=ft.Blur(IMAGE_BLUR, IMAGE_BLUR),
        bgcolor=ft.Colors.with_opacity(IMAGE_SCRIM, ft.Colors.SURFACE),
        left=0,
        top=0,
        right=0,
        bottom=0,
    )
    image = ft.Image(
        session.image_url,
        fit=ft.BoxFit.CONTAIN,
        semantics_label=f"Image for “{session.name}”",
        fade_in_animation=fade,
        error_content=_image_error(),
    )
    frame = ft.Container(
        # The Stack takes the frame's size; the image, not positioned, is given at
        # most that size, so it scales down and a small one stays small, centred.
        ft.Stack([backdrop, scrim, image], alignment=ft.Alignment.CENTER),
        aspect_ratio=IMAGE_RATIO,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=12,  # a card's shape (ux.md §3.6)
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )
    return ft.Container(
        named(f"{SCREEN}.image", frame),
        padding=ft.Padding.symmetric(horizontal=16),
    )


def _image_error() -> ft.Control:
    """What the frame shows when the image does not load: an icon beside a line.

    Side by side, so at large text the line grows sideways before it grows down: the
    frame's height is fixed, and two lines fit it at iOS's largest text size.
    """
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.HIDE_IMAGE_OUTLINED, color=ft.Colors.ON_SURFACE_VARIANT
                ),
                ft.Text(
                    IMAGE_ERROR,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    expand=True,
                    expand_loose=True,  # as wide as it needs, so the row stays centred
                ),
            ],
            spacing=12,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=12,
    )
