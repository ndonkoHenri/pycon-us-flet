"""The people on stage at a keynote or panel, and session detail's enrichment (SESS-08).

The feed names a keynote by its speaker and links its description to the site, so a
keynote's or panel's detail adds what the year data says (``content.toml``'s
``[[keynotes]]``, D-214): under Speakers, each person's photo, name and role, then their
bio; under About, the talk's own title over its abstract, which replaces the feed's
link-only description. ``person_head()``, a person's photo beside their name and role,
is the Keynotes page's too (``screens.keynote_card``). A module of its own, so session
detail stays under D-66's 400 lines.
"""

import flet as ft

from pycon_us.services import Services
from pycon_us.ui.links import feed_markdown
from pycon_us.ui.rows import speaker_avatar
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.year_keynotes import Keynote, KeynoteSpeaker


def person_head(
    person: KeynoteSpeaker,
    *,
    radius: int,
    name_style: ft.TextThemeStyle,
    initials_style: ft.TextThemeStyle | None = None,
    heading_level: int | None = None,
    identifier: str | None = None,
) -> ft.Control:
    """Return a person's photo beside their name and role.

    The photo is ``speaker_avatar()``'s (the photo over the initials), decorative: the
    name beside it says who. With a heading level the name is a heading (a Keynotes
    card's, F40) and the role a line of its own; without, name and role are one node,
    as a row in session detail's Speakers section.

    Args:
        person: The person.
        radius: The photo's radius in dp: a card's 48, session detail's 24.
        name_style: The name's type: ``TITLE_LARGE`` on a card, ``TITLE_MEDIUM`` in a
            list.
        initials_style: The initials' type, for a larger photo (``speaker_avatar()``).
        heading_level: The name's heading level; None for no heading.
        identifier: The name's node's semantics identifier.
    """
    name: ft.Control = ft.Text(person.name, theme_style=name_style)
    if heading_level is not None:
        name = ft.Semantics(
            header=True,
            heading_level=heading_level,
            identifier=identifier,
            content=name,
        )
    role = ft.Text(
        person.role,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    row = ft.Row(
        [
            ft.Semantics(
                exclude_semantics=True,
                content=speaker_avatar(
                    person, radius=radius, initials_style=initials_style
                ),
            ),
            # Expanded, so at large text the name and role wrap beside the photo.
            ft.Column([name, role], spacing=2, expand=True),
        ],
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    if heading_level is not None:
        return row
    return ft.MergeSemantics(
        content=ft.Semantics(identifier=identifier, content=row),
    )


def keynote_speakers(keynote: Keynote, *, screen: str) -> ft.Control:
    """Return session detail's Speakers section for a keynote or panel (SESS-08).

    Each person's photo, name and role, then their bio when the year data has one, in
    ``BODY_LARGE`` as a detail's text (ux.md §3.6), in full: a detail page cuts nothing.
    No chevron: these people have no page in the app, since the feed links no speaker
    to a keynote.

    Args:
        keynote: The session's keynote data.
        screen: The screen's name in the identifiers: ``<screen>.person.<n>`` and
            ``<screen>.bio.<n>``, numbered in the year data's order.
    """
    title = "Speakers" if keynote.kind == "keynote" else "Panelists"
    blocks: list[ft.Control] = [SectionHeader(title, level=2, top=0)]
    for number, person in enumerate(keynote.speakers):
        parts: list[ft.Control] = [
            person_head(
                person,
                radius=24,
                name_style=ft.TextThemeStyle.TITLE_MEDIUM,
                identifier=f"{screen}.person.{number}",
            )
        ]
        if person.bio:
            parts.append(
                ft.Semantics(
                    identifier=f"{screen}.bio.{number}",
                    container=True,
                    content=ft.Text(
                        person.bio,
                        theme_style=ft.TextThemeStyle.BODY_LARGE,
                        selectable=True,  # long text is selectable (D-26)
                    ),
                )
            )
        blocks.append(
            ft.Container(
                ft.Column(parts, spacing=12),
                # Material's 8 dp above and below a list row's 48 dp avatar (D-197),
                # 16 dp from the screen's sides.
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            )
        )
    return ft.Column(blocks, spacing=4)


def keynote_about(
    keynote: Keynote, description: str, svc: Services, *, screen: str
) -> ft.Control:
    """Return session detail's About section for a keynote or panel (SESS-08).

    The talk's own title in ``TITLE_MEDIUM`` (the feed names a keynote by its speaker),
    then the year data's abstract; a keynote without one keeps the feed's description,
    a link to its entry on the site.

    Args:
        keynote: The session's keynote data.
        description: The feed's description as Markdown (``Session.description_md``).
        svc: The session's services, for the text's links.
        screen: The screen's name in the identifiers: ``<screen>.keynote_title`` and
            ``<screen>.description``.
    """
    parts: list[ft.Control] = [SectionHeader("About", level=2, top=0)]
    if keynote.title:
        parts.append(
            ft.Container(
                ft.Semantics(
                    identifier=f"{screen}.keynote_title",
                    container=True,
                    content=ft.Text(
                        keynote.title,
                        theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                        selectable=True,
                    ),
                ),
                padding=ft.Padding.only(left=16, right=16, bottom=8),
            )
        )
    text = keynote.abstract or description
    if text:
        parts.append(feed_markdown(text, svc, identifier=f"{screen}.description"))
    return ft.Column(parts, spacing=0)
