"""Named tests for the HTML → Markdown converter (D-114, D-115; DATA-25, SESS-06).

One test per tag of S3's census, per row of its "could change meaning" table and per
boundary of ``docs/testing-and-quality.md`` §3.4. Inputs are small, real-looking HTML;
the feed samples and the whole-feed invariant are in ``test_html_md_feeds.py``, the
search text and the properties in ``test_html_md_text.py``.
"""

import html
from pathlib import Path

import pytest

from pycon_us.core.html_md import to_markdown
from tests.test_core_is_pure import imported_modules

SITE = "https://us.pycon.org/2026/"
PACKAGE = Path(__file__).resolve().parents[1] / "src" / "pycon_us"
INLINE = "pycon_us.core.markdown_inline"
# S3's synthetic line: text Flet's Markdown misreads unless escaped (F27, GFM, markers).
HAZARD = (
    "Tickets cost 5$ or 10$ at the door. Read ( the notes ) and [ the FAQ ] first.\n"
    "1999. A good year | x ~y~ *z* :smile: #tag"
)


def md(value: str) -> str:
    """Convert ``value`` to Markdown, with the 2026 site as the base of its links."""
    return to_markdown(value, SITE)


# Tags of the census (D-114)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<p>One</p>\n<p>Two</p>", "One\n\nTwo"),
        ("<p>Line<br>break</p>", "Line  \nbreak"),
        ("<p>Above</p><hr><p>Below</p>", "Above\n\n---\n\nBelow"),
        ("<h1>A</h1><h2>B</h2><h3>C</h3><h4>D</h4>", "# A\n\n## B\n\n### C\n\n#### D"),
        ("<ul><li>a</li><li>b</li></ul>", "- a\n- b"),
        ("<ol><li>a</li><li>b</li></ol>", "1. a\n2. b"),
        ("<blockquote><p>Quoted</p></blockquote>", "> Quoted"),
        ("<p><strong>bold</strong> <b>b</b></p>", "**bold** **b**"),
        ("<p><em>it</em> <i>i</i></p>", "*it* *i*"),
        ("<p><s>gone</s> <del>d</del> <strike>x</strike></p>", "~~gone~~ ~~d~~ ~~x~~"),
        ("<p>Run <code>uv sync</code></p>", "Run `uv sync`"),
        (
            '<p><a href="https://python.org">Python</a></p>',
            "[Python](https://python.org)",
        ),
    ],
    ids=[
        "p",
        "br",
        "hr",
        "h1-h4",
        "ul",
        "ol",
        "blockquote",
        "strong",
        "em",
        "s",
        "code",
        "a",
    ],
)
def test_census_tag_converts_to_its_markdown(value: str, expected: str) -> None:
    """D-114: each tag of the 2025 and 2026 feeds has one Markdown form."""
    assert md(value) == expected


def test_span_is_unwrapped_and_its_text_stays_in_place() -> None:
    """D-114: the 2025 keynote rows' styled span keeps "Keynote" on the line after the br."""
    value = '<p>Lynn Root<br><span style="font-size: smaller;">Keynote</span></p>'

    assert md(value) == "Lynn Root  \nKeynote"


def test_unknown_tags_are_unwrapped_so_their_text_survives() -> None:
    """D-114: a tag outside the census (a later feed's div, table, sup) loses only its markup."""
    value = "<div><p>E = mc<sup>2</sup></p><table><tr><td>cell</td></tr></table></div>"

    assert md(value) == "E = mc2\n\ncell"


def test_script_and_style_are_dropped_with_their_text() -> None:
    """D-114: their text is not content."""
    assert md("<p>a<script>alert(1)</script><style>p {}</style>b</p>") == "ab"


# What could change meaning (S3's table)


def test_newlines_inside_a_paragraph_collapse_as_in_a_browser() -> None:
    """D-114: hard-wrapped prose reads as on us.pycon.org; only br breaks a line."""
    value = "<p>Computer and Information\nScience at\n  the  university</p>"

    assert md(value) == "Computer and Information Science at the university"


def test_plain_text_value_keeps_its_paragraphs_and_line_breaks() -> None:
    """D-114, EVT-05: 15 sprint descriptions are plain text; Ionic lost their paragraphs."""
    value = "Arcade is a library.\nIt draws.\n\n\nJoin us &amp; sprint."

    assert md(value) == "Arcade is a library.  \nIt draws.\n\nJoin us &#38; sprint."


def test_strike_through_keeps_a_cancelled_title_struck() -> None:
    """D-114: dropping 2025's <s> would read as if the workshop runs."""
    assert md("<p>CANCELLED: <s>Intro to Sprints</s></p>") == (
        "CANCELLED&#58; ~~Intro to Sprints~~"
    )


def test_hazard_line_is_escaped_with_character_references() -> None:
    """D-115, F27: LaTeX, GFM strike-through, emphasis, tables, emoji and markers stay text."""
    assert md(HAZARD) == (
        "Tickets cost 5&#36; or 10&#36; at the door. "
        "Read &#40; the notes ) and &#91; the FAQ &#93; first.  \n"
        "1999&#46; A good year &#124; x &#126;y&#126; &#42;z&#42; &#58;smile&#58; #tag"
    )


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("# not a heading", "&#35; not a heading"),
        ("- not an item", "&#45; not an item"),
        ("+ not an item", "&#43; not an item"),
        ("=== not a rule", "&#61;== not a rule"),
        ("1999. A year", "1999&#46; A year"),
        ("2) Two", "2&#41; Two"),
        ("> not a quote", "&#62; not a quote"),
    ],
)
def test_block_marker_at_line_start_is_escaped(line: str, expected: str) -> None:
    """D-115: a marker at the start of a line would make a heading, list, rule or quote."""
    assert md(f"<p>{html.escape(line)}</p>") == expected


def test_markdown_inside_code_is_raw() -> None:
    """D-115: code spans are not interpreted, so nothing is escaped inside them."""
    value = "<p><code>len([x for x in arr if x % 2 == 0])</code> <code>&lt;head&gt;</code></p>"

    assert md(value) == "`len([x for x in arr if x % 2 == 0])` `<head>`"


def test_code_with_backticks_gets_a_longer_fence() -> None:
    """D-115: the fence has one backtick more than the longest run inside."""
    assert md("<p><code>a`b</code> <code>``x</code></p>") == "``a`b`` ``` ``x ```"


def test_bare_url_becomes_an_explicit_link_without_its_sentence_punctuation() -> None:
    """D-114: GFM's autolink never decides where a URL ends, and the label is escaped."""
    value = "<p>Apply at https://example.com/jobs/data_eng?id=3&amp;src=pycon.</p>"

    assert md(value) == (
        "Apply at [https&#58;//example.com/jobs/data&#95;eng?id=3&#38;src=pycon]"
        "(https://example.com/jobs/data_eng?id=3&src=pycon)."
    )


@pytest.mark.parametrize(
    ("text", "url"),
    [
        ("(see https://a.org/x)", "https://a.org/x"),
        ('"https://a.org/x",', "https://a.org/x"),
        ("https://a.org/x!?", "https://a.org/x"),
        ("“https://a.org/x”", "https://a.org/x"),
    ],
)
def test_bare_url_ends_before_closing_punctuation(text: str, url: str) -> None:
    """D-114: closing brackets and quotes after a URL belong to the sentence."""
    assert f"]({url})" in md(f"<p>{text}</p>")


def test_scheme_without_a_host_is_not_a_link() -> None:
    """D-131: "http://." is punctuation after a scheme, not a URL."""
    assert md("<p>http://.</p>") == "http&#58;//."


def test_relative_link_is_joined_to_the_site_url() -> None:
    """D-114, SESS-06: 24 hrefs are /2025/... or /2026/... and would open nothing."""
    value = '<p><a href="/2025/about/keynote-speakers#lynn-root">Lynn Root</a></p>'

    assert md(value) == (
        "[Lynn Root](https://us.pycon.org/2025/about/keynote-speakers#lynn-root)"
    )


@pytest.mark.parametrize(
    ("href", "linked"),
    [
        ("mailto:pycon-us@python.org", True),
        ("http://example.com", True),
        ("javascript:alert(1)", False),
        ("ftp://example.com/file", False),
        ("", False),
    ],
)
def test_only_http_https_and_mailto_become_links(href: str, linked: bool) -> None:
    """D-114: anything else stays text, so a tap never opens an unexpected scheme."""
    result = md(f'<p><a href="{href}">here</a></p>')

    assert result.startswith("[here](") is linked
    assert result == "here" or linked


def test_link_without_href_stays_text() -> None:
    """D-131: an anchor with no target is not a link (it would point at the site)."""
    assert md('<p><a name="top">Top</a></p>') == "Top"


def test_link_destination_is_percent_encoded() -> None:
    """D-114: the feed's stray "]" and any space or parenthesis cannot end the destination."""
    value = '<p><a href="https://x.org/a b(c)]">x</a></p>'

    assert md(value) == "[x](https://x.org/a%20b%28c%29%5D)"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('<p><a href="https://x.org/\ud800">x</a></p>', "[x](https://x.org/%ED%A0%80)"),
        (
            "<p>https://x.org/\udfff",
            "[https&#58;//x.org/\udfff](https://x.org/%ED%BF%BF)",
        ),
    ],
)
def test_lone_surrogate_in_a_link_target_is_percent_encoded(
    value: str, expected: str
) -> None:
    """D-130: JSON can carry a lone surrogate; strict UTF-8 would raise on it."""
    assert md(value) == expected


def test_link_edge_whitespace_stays_outside_the_brackets() -> None:
    """D-114: "[x](…)y" would read "xy"."""
    assert md('<p><a href="https://x.org"> Lynn </a>Root</p>') == (
        "[Lynn](https://x.org) Root"
    )


def test_emphasis_edge_whitespace_stays_outside_the_markers() -> None:
    """D-114: "** x**" cannot open, so the markers would show."""
    assert md("<p>a<strong> bold </strong>b</p>") == "a **bold** b"


def test_whitespace_only_emphasis_adds_no_markers() -> None:
    """D-114 boundary: "****" would render as a rule or literal stars."""
    assert md("<p>a<em> </em>b</p>") == "a b"


def test_emphasis_that_cannot_flank_loses_its_markers() -> None:
    """D-114: punctuation inside touching a letter outside would show "*" literally."""
    assert md("<p>a<em>(x)</em>b</p>") == "a&#40;x)b"
    assert md("<p><strong>Company:</strong>Acme</p>") == "Company&#58;Acme"


def test_emphasis_next_to_punctuation_or_space_keeps_its_markers() -> None:
    """D-114: the common "<strong>Company:</strong> Acme" stays bold."""
    assert md("<p><strong>Company:</strong> Acme</p>") == "**Company&#58;** Acme"
    assert md("<p>a <em>(x)</em> b</p>") == "a *&#40;x)* b"


def test_nested_emphasis_is_one_delimiter_run() -> None:
    """D-131: "***x***" opens both, so a letter before it does not drop the strong."""
    assert md("<p>a<strong><em>x</em></strong>b</p>") == "a***x***b"


def test_dropping_an_outer_emphasis_rechecks_the_inner_one() -> None:
    """D-131: without the outer markers the inner one touches the letters too."""
    assert md("<p>a<strong><em>(x)</em></strong>b</p>") == "a&#40;x)b"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<p><em>a</em><em>b</em></p>", "*ab*"),
        ("<p><strong>a</strong><b>b</b> c</p>", "**ab** c"),
        ("<p><s>a</s><del>b</del></p>", "~~ab~~"),
        ("<p><code>a</code><code>b</code></p>", "`ab`"),
        ("<p><code>a</code><script>x</script><code>b</code></p>", "`ab`"),
    ],
    ids=["em", "strong-b", "s-del", "code", "code-across-script"],
)
def test_touching_elements_of_one_kind_render_as_one(value: str, expected: str) -> None:
    """D-131: "*a**b*" and "`a``b`" would show their markers literally."""
    assert md(value) == expected


def test_consecutive_line_breaks_give_one_hard_break() -> None:
    """D-131: a blank line would end the paragraph and split emphasis or links across it."""
    assert md("<p><em>a<br><br>b</em></p>") == "*a  \nb*"


def test_invalid_href_stays_text() -> None:
    """D-131: a malformed href ("http://[" is an invalid IPv6 host) must not stop the feed."""
    assert md('<p><a href="http://[">x</a></p>') == "x"


def test_url_inside_link_text_stays_text() -> None:
    """D-114: links cannot nest, so the label's URL is not linked again."""
    value = '<p><a href="https://x.org">https://y.org</a></p>'

    assert md(value) == "[https&#58;//y.org](https://x.org)"


def test_nested_anchor_is_not_linked_twice() -> None:
    """D-131: the inner anchor's text joins the outer link."""
    value = '<p><a href="https://a.org">see <a href="https://b.org">b</a></a></p>'

    assert md(value) == "[see b](https://a.org)"


def test_list_inside_ordered_item_is_indented_by_the_marker_width() -> None:
    """D-114: CommonMark nests under "1. " only with three spaces (architecture said two)."""
    value = "<ol><li>Setup<ul><li>uv</li><li>Flet</li></ul></li><li>Run</li></ol>"

    assert md(value) == "1. Setup\n   - uv\n   - Flet\n2. Run"


def test_item_with_several_paragraphs_keeps_them_in_the_item() -> None:
    """D-114 boundary: the second paragraph is indented, so it stays in the item."""
    value = "<ul><li><p>First</p><p>Second</p></li><li>Next</li></ul>"

    assert md(value) == "- First\n\n  Second\n- Next"


def test_item_holding_only_a_nested_list() -> None:
    """D-114 boundary (S3 review): "- - a" is a nested list, which is what the HTML says."""
    assert md("<ul><li><ul><li>a</li></ul></li><li>b</li></ul>") == "- - a\n- b"


def test_text_between_list_items_becomes_an_item() -> None:
    """D-131: browsers show text written directly in a list, so it must not be lost."""
    assert md("<ul>Intro<li>a</li>\n<li>b</li></ul>") == "- Intro\n- a\n- b"


def test_line_break_in_a_heading_becomes_a_space() -> None:
    """D-114: Markdown headings are one line."""
    assert md("<h2>Venue<br>and hours</h2>") == "## Venue and hours"


def test_empty_code_adds_nothing() -> None:
    """D-131: an empty span would render as two literal backticks."""
    assert md("<p>a<code></code>b</p>") == "ab"


def test_space_edged_code_keeps_its_spaces_outside_the_span() -> None:
    """D-131: the renderer trims one space at each edge, joining the words around."""
    assert md("<p>run<code> uv sync </code>now</p>") == "run `uv sync` now"


def test_block_inside_an_inline_element_keeps_words_apart() -> None:
    """D-131: a paragraph inside a link becomes link text without joining words."""
    value = '<p>a<a href="https://x.org"><p>b</p><p>c</p></a>d</p>'

    assert md(value) == "a [b c](https://x.org) d"


def test_empty_value_converts_to_empty_markdown() -> None:
    """514 of 728 2026 slot descriptions are empty."""
    assert md("") == ""
    assert md("<p> </p>") == ""


# The module boundary (D-201)


def test_only_html_md_imports_the_inline_layer() -> None:
    """D-201: markdown_inline is html_md's inline layer, imported by nothing else."""
    importers = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if INLINE in imported_modules(path)
    }
    assert importers == {"core/html_md.py"}


def test_inline_layer_imports_nothing_from_the_app() -> None:
    """D-201: the dependency runs one way, so markdown_inline imports no app module."""
    path = PACKAGE / "core" / "markdown_inline.py"
    assert {
        name for name in imported_modules(path) if name.startswith("pycon_us")
    } == set()
