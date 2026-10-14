"""A keynote's or panel's card on the Keynotes page (SPKR-04): ``KeynoteCard``.

One elevated card per session (ux.md §5.11). A keynote's shows each speaker's photo,
name and role, the talk's own title, and the bios cut at four lines with "Read more";
a panel's shows the feed's name of it over its own title, the abstract cut the same way,
and its people as a wrapping row of 64 dp photos with their names. Under a divider, a
time-and-room tile opens the session, beside its star. A keynote the year data has
nothing for yet (``content.toml``, D-217) still gets a card: its name and the tile.
A module of its own, as the Sprints page's card is (D-202), so the page stays short.
"""

import flet as ft

from pycon_us.core.models import Session
from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import day_heading, on_screen
from pycon_us.locations import drill_href
from pycon_us.screens.keynote_people import person_head
from pycon_us.services.errors import report_errors
from pycon_us.ui.badges import FavoriteButton, ToggleFavorite
from pycon_us.ui.rows import speaker_avatar
from pycon_us.ui.semantics import named, semantics_key
from pycon_us.year_keynotes import Keynote, KeynoteSpeaker

SCREEN = "keynotes"
"""The Keynotes page's name in the cards' semantics identifiers (decisions §M)."""

CLAMP_LINES = 4
"""How many lines of a bio or an abstract a card shows before "Read more" (ux.md §5.11)."""

CLAMP_CHARS = 80
"""A text longer than this gets "Read more". About four lines' worth at 200 % text on
a phone: Flet cannot say whether a text was cut (U16), so a shorter threshold would
leave words hidden with no way to read them at large text."""

TALK_TITLE = ft.TextThemeStyle.TITLE_MEDIUM
"""A talk's title on a card, a keynote's or a panel's (D-224). People's names stay in
``TITLE_LARGE``: their words are short. At iOS's largest text a ``TITLE_LARGE`` word of
nine letters ("Community") is wider than the card's 338 dp text column on a 402 dp
phone, and Flutter breaks it inside itself; ``TITLE_MEDIUM`` holds about twelve."""

PANEL_PHOTO = 32
"""A panelist's photo radius in dp: the 64 dp photos of ux.md §5.11."""

PANEL_GAP = 16
"""The gap in dp between two panelists, and between two lines of them: their names
take their own widths, so less would run two names together."""


def clamps(text: str) -> bool:
    """Return whether a card cuts ``text`` at ``CLAMP_LINES`` with "Read more".

    Args:
        text: A bio or an abstract as the card shows it.
    """
    return len(text) > CLAMP_CHARS or "\n" in text


def card_text(keynote: Keynote) -> str:
    """Return the text a card cuts: a keynote's bios, or a panel's abstract.

    A keynote's speakers are its subject, so its card says who they are (the talk's
    abstract is on its detail); a panel's people are many, so its card says what it
    is about.

    Args:
        keynote: The session's keynote data.
    """
    if keynote.kind == "panel":
        return keynote.abstract
    return "\n\n".join(person.bio for person in keynote.speakers if person.bio)


def KeynoteCard(
    session: Session,
    keynote: Keynote | None,
    view: SessionView,
    *,
    saved: bool,
    on_toggle: ToggleFavorite,
    star_color: str,
) -> ft.Control:
    """Return one keynote's or panel's card, a memoised component keyed by its session.

    Given the same props it skips its body (D-153, F34), so a star tap re-renders one
    card. Its "Read more" state is its own.

    Args:
        session: The session, the same object for one feed version.
        keynote: Its year data; None for a keynote the year data lacks.
        view: Its row view (``use_session_views()``): the time range, the place.
        saved: Whether it is in My schedule.
        on_toggle: The page's star handler (``use_favorite_toggle()``).
        star_color: The filled star's colour, ``Tokens.favorite``.
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _KeynoteCard(
        session,
        keynote,
        view,
        saved=saved,
        on_toggle=on_toggle,
        star_color=star_color,
        key=session.id,  # pyright: ignore[reportCallIssue]
    )


@ft.memo
@ft.component
def _KeynoteCard(
    session: Session,
    keynote: Keynote | None,
    view: SessionView,
    *,
    saved: bool,
    on_toggle: ToggleFavorite,
    star_color: str,
) -> ft.Control:
    """The body of ``KeynoteCard``; it runs only when its props or "Read more" change."""
    expanded, set_expanded = ft.use_state(False)
    key = semantics_key(session.id)
    body: list[ft.Control] = _head(session, keynote, key)
    text = card_text(keynote) if keynote is not None else ""
    long = clamps(text)
    if text:
        body.append(
            ft.Text(
                text,
                # As a description's text (ux.md §3.6) and the Sprints page's cards.
                theme_style=ft.TextThemeStyle.BODY_LARGE,
                max_lines=CLAMP_LINES if long and not expanded else None,
                overflow=ft.TextOverflow.ELLIPSIS
                if long and not expanded
                else ft.TextOverflow.CLIP,
            )
        )
    panel = keynote is not None and keynote.kind == "panel"
    controls: list[ft.Control] = [
        ft.Container(
            ft.Column(body, spacing=12),
            padding=ft.Padding.only(
                # A little air between a cut text and its "Read more".
                left=16,
                top=16,
                right=16,
                bottom=4 if long else 0 if panel else 16,
            ),
        )
    ]
    if long:

        @report_errors
        def toggle() -> None:
            set_expanded(not expanded)

        word = "Show less" if expanded else "Read more"
        # What the text it opens is about: a keynote's bios, its people, whom the
        # feed's name of it names; a panel's abstract, the panel.
        about = (
            session.name
            if keynote is None or keynote.kind == "keynote" or not keynote.title
            else keynote.title
        )
        controls.append(
            ft.Container(
                named(
                    f"{SCREEN}.more.{key}",
                    ft.Semantics(
                        expanded=expanded,  # said "collapsed" or "expanded"
                        content=ft.TextButton(
                            content=ft.Text(
                                word,
                                # The visible words first (WCAG 2.5.3), then whose.
                                semantics_label=f"{word} about {about}",
                            ),
                            on_click=toggle,
                            # Material scales a text button's side padding down as
                            # text grows (12 dp to 4); pinned, the label stays on the
                            # text's edge at every size.
                            style=ft.ButtonStyle(
                                padding=ft.Padding.symmetric(horizontal=12, vertical=8)
                            ),
                        ),
                    ),
                ),
                # The button's label sits 12 dp in: 4 + 12 lines it up with the text.
                padding=ft.Padding.only(left=4, bottom=4),
                alignment=ft.Alignment.CENTER_LEFT,
            )
        )
    if keynote is not None and panel:  # under the text "Read more" opens
        controls.append(
            ft.Container(
                _panelists(keynote.speakers),
                padding=ft.Padding.only(
                    left=16, top=4 if long else 12, right=16, bottom=16
                ),
            )
        )
    controls += [
        ft.Divider(height=1),
        _when_and_where(session, view, saved, on_toggle, star_color, key),
    ]
    return ft.Card(
        ft.Column(
            controls, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        ),
        variant=ft.CardVariant.ELEVATED,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the tile's ink stays inside
        # Not one node: each part reads in its order, the names as headings.
        semantic_container=False,
        margin=ft.Margin.symmetric(horizontal=16, vertical=8),
    )


def _head(session: Session, keynote: Keynote | None, key: str) -> list[ft.Control]:
    """The card's head: a keynote's people, or a panel's names; a level-2 heading."""
    if keynote is not None and keynote.kind == "keynote":
        head: list[ft.Control] = [
            person_head(
                person,
                radius=48,  # the 96 dp photo of ux.md §5.11
                name_style=ft.TextThemeStyle.TITLE_LARGE,
                initials_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                heading_level=2,
                identifier=f"{SCREEN}.name.{key}.{number}",
                stacked=True,
            )
            for number, person in enumerate(keynote.speakers)
        ]
        if keynote.title:
            head.append(ft.Text(keynote.title, theme_style=TALK_TITLE))
        return head
    title = keynote.title if keynote is not None and keynote.title else session.name
    head = []
    if title != session.name:  # the feed's name of the panel, over its own title
        head.append(
            ft.Text(
                session.name,
                theme_style=ft.TextThemeStyle.LABEL_LARGE,
                color=ft.Colors.PRIMARY,
            )
        )
    head.append(
        ft.Semantics(
            header=True,
            heading_level=2,
            identifier=f"{SCREEN}.name.{key}.0",
            # A talk's title, so in a keynote's talk title's type (D-224): a long
            # title's words at TITLE_LARGE outgrew the card at the largest text,
            # "Comm" / "unity", where a name's short ones fit.
            content=ft.Text(title, theme_style=TALK_TITLE),
        )
    )
    return [ft.Column(head, spacing=4)]


def _panelists(people: tuple[KeynoteSpeaker, ...]) -> ft.Control:
    """A panel's people: a wrapping row of 64 dp photos, each over the person's name.

    Each name takes its own width, from the photo's edge, so it breaks only between
    words, and only when it is wider than the card: in a fixed width, the largest
    text broke a long surname inside the word.
    """
    return ft.Row(
        [
            ft.MergeSemantics(  # one stop per person, read as the name
                content=ft.Column(
                    [
                        ft.Semantics(
                            exclude_semantics=True,
                            content=speaker_avatar(
                                person,
                                radius=PANEL_PHOTO,
                                initials_style=ft.TextThemeStyle.TITLE_LARGE,
                            ),
                        ),
                        ft.Text(person.name, theme_style=ft.TextThemeStyle.BODY_SMALL),
                    ],
                    spacing=4,
                    # The first photo on the text's edge, as the names under them.
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                )
            )
            for person in people
        ],
        wrap=True,
        spacing=PANEL_GAP,
        run_spacing=PANEL_GAP,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def _when_and_where(
    session: Session,
    view: SessionView,
    saved: bool,
    on_toggle: ToggleFavorite,
    star_color: str,
    key: str,
) -> ft.Control:
    """The time-and-room tile, which opens the session, beside its star.

    The day over the time and the place, a line each (as session detail's time
    tile, D-186), the range breaking only after its dash, when it is wider than its
    line (at the largest text, beside the star; D-224); one phrase for screen readers,
    "Friday, May 15, 9:45 to 10:30 AM, Pacific Ballroom - Arena", and the star a
    stop of its own beside it.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    target = drill_href(view_path, "session", session.id)

    @report_errors
    def go() -> None:
        page.navigate(target)

    @report_errors
    async def star() -> None:
        await on_toggle(session.id)

    lines: list[ft.Control] = [
        ft.Text(on_screen(view.when), semantics_label=view.spoken_when)
    ]
    if view.place:
        lines.append(ft.Text(view.place))
    tile = ft.ListTile(
        leading=ft.Icon(ft.Icons.SCHEDULE),
        title=ft.Text(day_heading(session.day)),
        subtitle=ft.Column(lines, spacing=0),
        title_alignment=ft.ListTileTitleAlignment.TITLE_HEIGHT,
        on_click=go,
    )
    return ft.Row(
        [
            ft.Container(
                named(f"{SCREEN}.session.{key}", tile),
                expand=True,
            ),
            ft.Container(
                FavoriteButton(
                    saved,
                    star,
                    color=star_color,
                    identifier=f"{SCREEN}.favorite.{key}",
                ),
                padding=ft.Padding.only(right=4),
            ),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
