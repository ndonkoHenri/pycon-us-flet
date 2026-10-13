"""A project's card on the Sprints page (EVT-05): ``ProjectCard`` and ``logo_tile()``.

A card holds one project of the development sprints: its logo on a white tile, or its
initials; its name, a heading for screen readers, and "by <submitter>"; its description,
cut at four lines with "More" when it is long (``core.sprints.cut_short()``), which shows
the whole text as Markdown, its links opening by the feed-link rule (D-197); and
"Project page", the project's site in the in-app browser. A module of its own, as Now's
next-session card is (D-190), so the page stays under D-66's 400 lines.
"""

import flet as ft

from pycon_us.core.models import Sprint
from pycon_us.core.speakers import initials
from pycon_us.core.sprints import cut_short
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import SEED
from pycon_us.ui.links import OPENS_IN, LinkKind, feed_link, feed_markdown, open_link
from pycon_us.ui.semantics import named, semantics_key

SCREEN = "sprints"
"""The Sprints page's name in the cards' semantics identifiers (decisions §M)."""

LOGO = 56
"""A project's logo tile, in dp: square, beside the name and the submitter's two lines."""

LOGO_INK = SEED
"""The initials' colour on the white logo tile in both schemes: 8.6:1 on white."""


def ProjectCard(sprint: Sprint) -> ft.Control:
    """Return one project's card (EVT-05), a memoised component keyed by its id.

    Given the same project it skips its body (D-153, F34), so a filter keystroke
    re-renders no card that stays. Its "More" state is its own.

    Args:
        sprint: The project, the same object for one feed version.
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _ProjectCard(sprint, key=sprint.id)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _ProjectCard(sprint: Sprint) -> ft.Control:
    """The body of ``ProjectCard``; it runs only when its project or "More" changes."""
    svc = use_services()
    expanded, set_expanded = ft.use_state(False)
    key = semantics_key(sprint.id)
    long = cut_short(sprint)
    # The feed's URL as written: "documentdb.io" opens as https://documentdb.io, and
    # one that names no web page leaves the card without a dead button (D-197).
    target = feed_link(sprint.url, svc.year.conference.site_url)

    @report_errors
    def toggle() -> None:
        set_expanded(not expanded)

    @report_errors
    async def open_page() -> None:
        if target is not None:
            await open_link(svc, target)

    lines: list[ft.Control] = [
        ft.Semantics(
            header=True,
            heading_level=3,  # under "Projects": a screen reader goes card by card
            identifier=f"{SCREEN}.project.{key}",
            content=ft.Text(sprint.name, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
        )
    ]
    if sprint.submitter:
        lines.append(
            ft.Text(
                f"by {sprint.submitter}",
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    head = ft.Row(
        [logo_tile(sprint), ft.Column(lines, spacing=2, expand=True)],
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    body: list[ft.Control] = [head]
    if expanded:
        body.append(feed_markdown(sprint.description_md, svc, inset=0))
    elif sprint.description_text:
        body.append(
            ft.Text(
                sprint.description_text,
                # Body text as the whole description's Markdown sets it (D-116), so
                # "More" continues the same text rather than changing its size.
                theme_style=ft.TextThemeStyle.BODY_LARGE,
                style=ft.TextStyle(height=1.5),
                max_lines=4 if long else None,
                overflow=ft.TextOverflow.ELLIPSIS if long else ft.TextOverflow.CLIP,
            )
        )
    actions: list[ft.Control] = []
    if long:
        actions.append(
            named(
                f"{SCREEN}.more.{key}",
                ft.Semantics(
                    expanded=expanded,  # said "collapsed" or "expanded"
                    content=ft.TextButton(
                        content=ft.Text(
                            "Less" if expanded else "More",
                            semantics_label=f"Full description of {sprint.name}",
                        ),
                        on_click=toggle,
                    ),
                ),
            )
        )
    if target is not None:
        actions.append(
            named(
                f"{SCREEN}.project_page.{key}",
                ft.Semantics(
                    link=True,
                    content=ft.TextButton(
                        content=ft.Text(
                            "Project page",
                            semantics_label=(
                                f"{sprint.name} project page\n{OPENS_IN[LinkKind.WEB]}"
                            ),
                        ),
                        icon=ft.Icons.OPEN_IN_NEW,
                        on_click=open_page,
                    ),
                ),
            )
        )
    controls: list[ft.Control] = [
        ft.Container(
            ft.Column(body, spacing=12),
            padding=ft.Padding.only(left=16, top=16, right=16),
        )
    ]
    if actions:
        controls.append(
            ft.Container(
                # More at the start, under the text it opens; Project page at the end.
                # At large text the row wraps and each button moves down whole.
                ft.Row(
                    actions,
                    wrap=True,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                # A text button's label sits 12 dp in: 4 + 12 lines it up with the text.
                padding=ft.Padding.only(left=4, top=4, right=4, bottom=4),
            )
        )
    return ft.Card(
        ft.Column(
            controls,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        variant=ft.CardVariant.OUTLINED,
        # Not one node: as one, TalkBack read "by Nick" and the text before the name,
        # which as a heading is a node of its own; each part reads in its order.
        semantic_container=False,
        margin=ft.Margin.symmetric(horizontal=16, vertical=6),
    )


def logo_tile(sprint: Sprint) -> ft.Control:
    """Return a project's logo on a white tile, or its initials when there is none.

    Logos are made for a white page, so the tile is white in both schemes (as the
    sponsor spotlight's, ux.md §5.1) with a hairline edge. The initials stand in when
    the feed has no logo and when it cannot load (offline, a broken URL), in the brand
    indigo, 8.6:1 on white; a ``CircleAvatar`` holds them because it does not scale its
    text, so they fit the tile at any text size. Decorative for screen readers: the
    name follows.

    Args:
        sprint: The project.
    """
    monogram = ft.CircleAvatar(
        content=ft.Text(initials(sprint.name), weight=ft.FontWeight.W_500),
        bgcolor=ft.Colors.TRANSPARENT,
        color=LOGO_INK,
        radius=LOGO / 2 - 6,
    )
    content: ft.Control = monogram
    if sprint.logo_url:
        content = ft.Image(
            src=sprint.logo_url,
            fit=ft.BoxFit.CONTAIN,
            error_content=monogram,
            exclude_from_semantics=True,
        )
    return ft.Semantics(
        exclude_semantics=True,
        content=ft.Container(
            content,
            width=LOGO,
            height=LOGO,
            padding=6,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=12,
            alignment=ft.Alignment.CENTER,
        ),
    )
