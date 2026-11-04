"""Now's sponsor spotlight: one still card that thanks one sponsor (SHELL-08, SPON-11).

Ionic rotated a sponsor strip above the tab bar every 30 s with no pause (WCAG 2.2.2).
Now shows one card instead (D-37): the sponsor's logo on its white tile and "Thanks to
NVIDIA, a Visionary sponsor", with no timer and no animation. `core.sponsors` picks
the sponsor once for the process (`pick_spotlight()`, D-298); a tap pushes its detail
over Now, `/now/sponsor/<slug>`, so Back returns here (D-17). At large text
(`Prefs.time_above`, D-216) the words go under the tile, the chevron beside it, as a
location card's do: beside the tile and the chevron, they broke inside a word at the
largest sizes, "Maintaini / ng" (#649).
Apart from `now.py` so that the screen stays under about 400 lines (D-66, D-190).
"""

import flet as ft

from pycon_us.core.models import Sponsor
from pycon_us.core.sponsors import thanks
from pycon_us.locations import drill_href
from pycon_us.services.errors import report_errors
from pycon_us.ui.logos import logo_tile

IDENTIFIER = "now.spotlight"
"""The card's one node (ux.md §5.1)."""

PLATE = 56
"""The logo tile's size, in dp: square, as a sprint project's (D-262)."""


def Spotlight(sponsor: Sponsor, view_path: str, *, large_text: bool) -> ft.Control:
    """Return the spotlight card for `sponsor`, a memoised component.

    Given the same sponsor, the same object for one feed version, it skips its body
    (D-153, F34), so Now's minute tick never re-renders it.

    Args:
        sponsor: The sponsor to thank.
        view_path: Now's View path, which the detail is pushed on.
        large_text: The text is large for the width (`Prefs.time_above`): the
            words go under the tile (`spotlight_body()`).
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _Spotlight(sponsor, view_path, large_text, key=sponsor.slug)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _Spotlight(sponsor: Sponsor, view_path: str, large_text: bool) -> ft.Control:
    """The body of `Spotlight`; it runs only when one of its arguments changes."""
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(drill_href(view_path, "sponsor", sponsor.slug))

    words = thanks(sponsor)
    return ft.MergeSemantics(  # the words and the tap's action: one node
        content=ft.Card(
            ft.Container(
                ft.Semantics(
                    label=words,
                    identifier=IDENTIFIER,
                    button=True,  # it opens the sponsor: "…, button" (D-33)
                    exclude_semantics=True,  # the label replaces the text below
                    content=spotlight_body(sponsor, words, large_text=large_text),
                ),
                ink=True,
                on_click=go,
                padding=16,
            ),
            variant=ft.CardVariant.OUTLINED,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the ink stays inside
            margin=ft.Margin.only(left=16, top=16, right=16),
        )
    )


def spotlight_body(sponsor: Sponsor, words: str, *, large_text: bool) -> ft.Control:
    """Return the card's tile, words and chevron: in one row, or the words under them.

    Args:
        sponsor: The sponsor, whose logo or initials the tile shows.
        words: What the card says, `thanks(sponsor)`.
        large_text: The text is large for the width (`Prefs.time_above`, D-216):
            the words take the card's whole width, under the tile and the chevron,
            so they wrap between words, never inside one (#649).
    """
    tile = logo_tile(sponsor.name, sponsor.logo_url, size=PLATE)
    text = ft.Text(words, theme_style=ft.TextThemeStyle.BODY_LARGE)
    chevron = ft.Icon(ft.Icons.CHEVRON_RIGHT)
    if large_text:
        return ft.Column(
            [
                ft.Row(
                    [tile, chevron],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                text,
            ],
            spacing=12,
            tight=True,
        )
    text.expand = True
    return ft.Row(
        [tile, text, chevron],
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
