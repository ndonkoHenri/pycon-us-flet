"""A detail page's own title, its level-1 heading, which steps down at large text (D-328).

Session, track, speaker and sponsor detail have an empty app bar title once the feed is
in (D-186): the page's own ``PageTitle`` is its level-1 heading (ux.md §5.5).
"""

import flet as ft

PAGE_TITLE = ft.TextThemeStyle.HEADLINE_SMALL
"""A detail page's own title, its level-1 heading in the body (ux.md §3.6, D-186)."""

PAGE_TITLE_AT_LARGE_TEXT = ft.TextThemeStyle.TITLE_MEDIUM
"""The title's type at large text (D-328): a row's title, as large as body text and
heavier, as iOS's own headings near body size at its Accessibility sizes. One step down,
``TITLE_LARGE``, still broke 43 of 2026's 180 session titles inside a word at iOS's
largest size on a 402 dp phone; this breaks 3, which body text breaks too."""


def PageTitle(
    text: str,
    *,
    identifier: str,
    large_text: bool,
    centred: bool = False,
    selectable: bool = False,
) -> ft.Control:
    """Return a detail page's title: its level-1 heading, which steps down at large text.

    Flutter scales every type by the same factor and has no hyphenation, so at iOS's
    Accessibility sizes a long word of a ``HEADLINE_SMALL`` title ("Interoperabilidad")
    was wider than the screen and broke inside itself. At large text, the size at
    which a slot's time leaves the gutter (``Prefs.time_above``, D-216), the title takes
    ``PAGE_TITLE_AT_LARGE_TEXT`` instead (D-328).

    Args:
        text: The title: a session's, a track's, a person's or a sponsor's name.
        identifier: For UI flows, ``<screen>.title``.
        large_text: The text is large for the width (``Prefs.time_above``).
        centred: Centre its lines, under a photo or a logo.
        selectable: Selectable, to copy (D-26).
    """
    return ft.Semantics(
        header=True,
        heading_level=1,
        identifier=identifier,
        content=ft.Text(
            text,
            theme_style=PAGE_TITLE_AT_LARGE_TEXT if large_text else PAGE_TITLE,
            text_align=ft.TextAlign.CENTER if centred else ft.TextAlign.START,
            selectable=selectable,
        ),
    )
