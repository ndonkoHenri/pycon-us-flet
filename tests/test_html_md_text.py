"""Tests for the converter's search text and its properties (D-46, D-114, D-130).

The text-only form for search, and Hypothesis's check that no visible character is lost
and that no input raises. The named tests per tag and per boundary are
`test_html_md.py`'s; the feed samples are `test_html_md_feeds.py`'s.
"""

import html

from hypothesis import assume, given
from hypothesis import strategies as st

from pycon_us.core.html_md import to_text
from tests.test_html_md import md
from tests.test_html_md_feeds import TAG, html_text, markdown_text

# The text-only form for search (D-46)


def test_search_text_has_no_markup_and_keeps_word_boundaries() -> None:
    """D-46: blocks, items and breaks separate words; links give their text only."""
    value = (
        '<h2>Talk</h2><p>See <a href="/2026/x">the <strong>page</strong></a>'
        "&amp; more</p><ul><li>one</li><li>two</li></ul><p>a<br>b</p>"
    )

    assert to_text(value) == "Talk See the page& more one two a b"


def test_search_text_of_plain_text_decodes_entities_and_collapses_space() -> None:
    """D-46: sprint descriptions search as their text."""
    assert to_text("Join us &amp;\n\n sprint") == "Join us & sprint"


def test_search_text_drops_script_and_style() -> None:
    """D-46: their text is not content, so it must not match a query."""
    assert to_text("<p>a<script>secret()</script> b</p>") == "a b"


# Property


_PLAIN = st.lists(
    st.text()
    | st.sampled_from(["https://a.org/x_y", "$", "( ", "[", "\n\n", "1. ", "#"]),
).map("".join)


@given(_PLAIN)
def test_plain_text_keeps_every_character(text: str) -> None:
    """D-114: whitespace aside, the Markdown of a value with no tag shows exactly its text."""
    assume(not TAG.search(text))  # that is HTML, covered below

    shown = "".join(html.unescape(text).split())
    assert markdown_text(md(text)) == shown
    assert "".join(to_text(text).split()) == shown


_HTML = st.lists(
    st.sampled_from(
        [
            *("<p>", "</p>", "<br>", "<hr>", "<ul>", "<ol>", "<li>", "</li>", "</ul>"),
            *("<h2>", "</h2>", "<blockquote>", "</blockquote>", "<span>", "</span>"),
            *("<em>", "</em>", "<strong>", "</strong>", "<s>", "</s>", "<code>"),
            *("</code>", "<a href='/x'>", "</a>"),  # script and style: named tests
            *(" ", "\n", "x", "(", ")", "$", "*", ":", "`", "1. ", "#", "&amp;"),
            *("https://a.org/b.", "<a href='http://['>"),
        ]
    ),
    min_size=1,
).map(lambda parts: "<p>" + "".join(parts))


@given(_HTML)
def test_html_keeps_every_visible_character(value: str) -> None:
    """D-114: whatever the nesting, the Markdown and search text show the HTML's text."""
    assert markdown_text(md(value)) == html_text(value)
    assert "".join(to_text(value).split()) == html_text(value)


@given(st.text(alphabet=st.sampled_from("<>/=\"' ab&#;:[]") | st.characters()))
def test_any_input_converts_without_raising(text: str) -> None:
    """D-130: conversion runs inside feed processing, so no field value may raise."""
    md(f"<p>{text}")
    md(f'<a href="{text}">{text}</a>')
    to_text(f"<p>{text}")
