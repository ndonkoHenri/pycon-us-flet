"""Tests for the Markdown style sheet: its colours, fonts, headings and rule.

D-116, D-152, D-197. The contrast helpers and `resolved()` are
`tests/test_theme.py`'s.
"""

import dataclasses
import itertools

import flet as ft
import pytest

from pycon_us import theme_markdown
from tests.test_theme import AA_TEXT, contrast_ratio, resolved


def test_every_markdown_text_style_names_a_checked_colour() -> None:
    """Every style the sheet gives names a colour: primary for links, else on-surface.

    The sheet gives at least the link, paragraph, h1 and code styles. F28: a style
    given in the sheet replaces the theme's, so one without a colour is black on the
    dark surface. The colours are roles whose contrast is tested above.
    """
    styles = {
        field.name: getattr(theme_markdown.MARKDOWN_STYLE, field.name)
        for field in dataclasses.fields(ft.MarkdownStyleSheet)
        if field.name.endswith("_text_style")
    }
    given = {name: style for name, style in styles.items() if style is not None}
    assert given.keys() >= {
        "a_text_style",
        "p_text_style",
        "h1_text_style",
        "code_text_style",
    }
    for name, style in given.items():
        expected = ft.Colors.PRIMARY if name == "a_text_style" else ft.Colors.ON_SURFACE
        assert style.color == expected, name


def test_every_markdown_text_style_names_its_font_and_decoration_colour() -> None:
    """Every style the sheet gives names its font, and a decoration takes its colour.

    D-152: Markdown text does not inherit the theme's font (iOS showed SF Pro), and an
    unnamed decoration colour drew near-black lines on the dark surface.
    """
    sheet = theme_markdown.MARKDOWN_STYLE
    for field in dataclasses.fields(ft.MarkdownStyleSheet):
        style = getattr(sheet, field.name)
        if not field.name.endswith("_text_style") or style is None:
            continue
        if field.name == "code_text_style":
            assert style.font_family == "monospace", field.name
            assert style.font_family_fallback == ["Menlo"], field.name
        else:
            assert style.font_family == "packages/roboto_fonts/Roboto", field.name
        if style.decoration is not None:
            assert style.decoration_color == style.color, field.name


def test_markdown_links_are_underlined_and_headings_stay_below_the_section() -> None:
    """Links are underlined, and headings are 18 then 16, below the section's title."""
    sheet = theme_markdown.MARKDOWN_STYLE
    assert sheet.a_text_style is not None
    assert (
        sheet.a_text_style.decoration == ft.TextDecoration.UNDERLINE
    )  # not colour alone (D-33)
    headings = [
        sheet.h1_text_style,
        sheet.h2_text_style,
        sheet.h3_text_style,
        sheet.h4_text_style,
    ]
    # Under a level-2 "About" (D-197): no larger than a row title (TITLE_MEDIUM, 16)
    # past h1, which stays below the screen title (TITLE_LARGE, 22).
    assert [style.size for style in headings if style] == [18, 16, 16, 16]


def test_a_markdown_rule_is_a_one_dp_divider() -> None:
    """D-197: Flet's default rule is a 5 dp bar between a description's paragraphs."""
    decoration = theme_markdown.MARKDOWN_STYLE.horizontal_rule_decoration
    assert decoration is not None and isinstance(decoration.border, ft.Border)
    top = decoration.border.top
    assert (top.width, top.color) == (1, ft.Colors.OUTLINE_VARIANT)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_markdown_text_reads_at_aa_on_every_background_the_sheet_draws(
    dark: bool,
) -> None:
    """Every Markdown text colour reads at AA on the page, code spans and quotes.

    SESS-06: a description's text, links and code on the page, on a code span and in a
    block quote, in both schemes.
    """
    sheet = theme_markdown.MARKDOWN_STYLE
    assert sheet.code_text_style is not None and sheet.blockquote_decoration is not None
    texts = {
        field.name: resolved(style.color, dark)
        for field in dataclasses.fields(ft.MarkdownStyleSheet)
        if field.name.endswith("_text_style")
        and (style := getattr(sheet, field.name)) is not None
    }
    backgrounds = {
        "surface": resolved(ft.Colors.SURFACE, dark),
        "code": resolved(sheet.code_text_style.bgcolor, dark),
        "blockquote": resolved(sheet.blockquote_decoration.bgcolor, dark),
    }
    for (text, color), (where, background) in itertools.product(
        texts.items(), backgrounds.items()
    ):
        ratio = contrast_ratio(background, color)
        assert ratio >= AA_TEXT, (text, where, round(ratio, 2))
