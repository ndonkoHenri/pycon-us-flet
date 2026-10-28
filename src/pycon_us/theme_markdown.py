"""The style sheet of every feed text, ``MARKDOWN_STYLE`` (D-116, D-152, D-197).

``theme.py`` holds the themes and the colour tokens; this sheet is theirs too, but no
theme carries it: a feed text passes it as ``ft.Markdown(md_style_sheet=...)``.
"""

import flet as ft

from pycon_us.theme import FONT_FAMILY

_TEXT = ft.Colors.ON_SURFACE
_HEADING = ft.FontWeight.W_500
_BODY = ft.TextStyle(size=16, height=1.5, color=_TEXT, font_family=FONT_FAMILY)


def _heading(size: int) -> ft.TextStyle:
    """Return a feed heading's style: ``size`` sp, medium weight, the app's font."""
    return ft.TextStyle(
        size=size, weight=_HEADING, color=_TEXT, font_family=FONT_FAMILY
    )


MARKDOWN_STYLE = ft.MarkdownStyleSheet(
    a_text_style=ft.TextStyle(
        color=ft.Colors.PRIMARY,
        decoration=ft.TextDecoration.UNDERLINE,
        decoration_color=ft.Colors.PRIMARY,  # unnamed, it was near-black in dark
        font_family=FONT_FAMILY,
    ),
    del_text_style=ft.TextStyle(
        color=_TEXT,
        decoration=ft.TextDecoration.LINE_THROUGH,
        decoration_color=_TEXT,
        font_family=FONT_FAMILY,
    ),
    p_text_style=_BODY,
    list_bullet_text_style=_BODY,
    blockquote_text_style=_BODY,
    # At most 18 sp: a feed heading sits under its section's "About" (D-197).
    h1_text_style=_heading(18),
    h2_text_style=_heading(16),
    h3_text_style=_heading(16),
    h4_text_style=_heading(16),
    code_text_style=ft.TextStyle(
        size=14,
        color=_TEXT,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        font_family="monospace",  # Android's alias; iOS has no such family
        font_family_fallback=["Menlo"],  # so iOS takes its system monospace font
    ),
    blockquote_decoration=ft.BoxDecoration(
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border(left=ft.BorderSide(4, ft.Colors.OUTLINE)),
    ),
    # Material's divider: Flet's default rule is a 5 dp bar, which read as a heavy
    # block between a description's paragraphs (D-197).
    horizontal_rule_decoration=ft.BoxDecoration(
        border=ft.Border(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT))
    ),
    block_spacing=12,
)
"""The style sheet of every feed text (D-116): pass it as ``ft.Markdown(md_style_sheet=...)``.

A style given here replaces the theme's instead of merging with it (F28), so every text
style names its colour and font family, and every decoration its colour (D-152):
Markdown text does not inherit the theme's font (on iOS it rendered in SF Pro), and an
unnamed decoration colour drew near-black lines on the dark surface. The colours are
scheme roles, resolved against the theme on screen, so this one sheet serves every
scheme. h5 and h6 keep Flet's defaults, which come from the theme's text styles and so
carry its colour and font.
"""
