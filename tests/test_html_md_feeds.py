"""The HTML → Markdown converter on the recorded 2025 and 2026 feeds (D-114, D-115; DATA-25).

The 22 samples are S3's (``docs/spikes/03-html-markdown.md``), selected from the feed
fixtures by year, field and a substring only that value contains. Their expected Markdown
in ``fixtures/html_md/samples.json`` is what S3 rendered correctly on the Android 16
emulator; a change to it is a change of rendering, to be reviewed and checked on a device.

The invariant runs over every value of every HTML field of both feeds: no visible
character is lost or added (whitespace aside), and no raw tag, ``$`` or LaTeX opener is
left outside code. It is static, so the named tests in ``test_html_md.py`` pin the rest.
"""

import html
import json
import re
from collections.abc import Iterator
from functools import cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from pycon_us.config import load_year
from pycon_us.core.html_md import to_markdown, to_text

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = json.loads((FIXTURES / "html_md" / "samples.json").read_text())
TAG = re.compile(r"</?[a-zA-Z][^>]*>")
# The fields that carry HTML in either feed (S3's census). Slot names are cleaned by the
# name rules (DATA-08), and open spaces are Markdown already (DATA-25), so neither is here.
HTML_FIELDS = (
    ".conference.content.*",
    ".schedule[].description",
    ".schedule[].speakers[].bio",
    ".schedule[].sessions[].description",  # 2025's posters (#58)
    ".schedule[].sessions[].speakers[].bio",
    ".posters[].description_html",
    ".posters[].speakers[].bio",
    ".sprints[].description_html",
    ".job-listings[].description_html",
)


@cache
def feed(year: int) -> dict[str, Any]:
    return json.loads((FIXTURES / "feeds" / f"conference-{year}.json").read_text())


def site_url(year: int) -> str:
    return load_year(year).conference.site_url


def values_at(node: object, path: str) -> Iterator[str]:
    """Yield the strings at a census path such as ``.schedule[].speakers[].bio``.

    ``[]`` walks every item of a list and ``*`` every value of an object.
    """
    key, _, rest = path.removeprefix(".").partition(".")
    if not key:
        if isinstance(node, str):
            yield node
        return
    if not isinstance(node, dict):
        return
    if key == "*":
        children = list(node.values())
    elif key.endswith("[]"):
        children = node.get(key.removesuffix("[]")) or []
    else:
        children = [node[key]] if key in node else []
    for child in children:
        yield from values_at(child, rest)


def html_fields(year: int) -> Iterator[str]:
    for path in HTML_FIELDS:
        yield from values_at(feed(year), path)


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_text(value: str) -> str:
    """The HTML's visible characters, whitespace removed; a value with no tag is text."""
    if not TAG.search(value):
        return "".join(html.unescape(value).split())
    parser = _VisibleText()
    parser.feed(value)
    parser.close()
    return "".join("".join(parser.parts).split())


def markdown_text(markdown: str) -> str:
    """Our Markdown's visible characters: our syntax removed, references decoded.

    Outside code spans every raw ``*``, ``~``, ``[`` and ``]`` is ours, because text is
    escaped (D-115); code spans show their content as it is.
    """
    markdown = re.sub(r"\]\([^)\s]*\)", "]", markdown)  # link destinations
    # Quote and list markers, nested ones included, then headings and rules.
    markdown = re.sub(r"^([ \t]*(- |\d+\. |> ?))+", "", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"^[ \t]*(#+ |---$)", "", markdown, flags=re.MULTILINE)
    shown = []
    for index, part in enumerate(re.split(r"(`+)(.*?)\1", markdown)):
        if index % 3 == 2:  # a code span's content
            shown.append(part)
        elif index % 3 == 0:
            shown.append(html.unescape(re.sub(r"[*~\[\]]", "", part)))
    return "".join("".join(shown).split())


def outside_code(markdown: str) -> str:
    return re.sub(r"(`+).*?\1", "", markdown)


@pytest.mark.parametrize(
    "sample", SAMPLES, ids=[f"{s['year']}-{s['shows']}" for s in SAMPLES]
)
def test_feed_sample_converts_to_the_markdown_s3_checked_on_device(
    sample: dict[str, Any],
) -> None:
    """DATA-25, SESS-06: each S3 sample gives the Markdown that rendered as intended."""
    (value,) = [
        v
        for v in values_at(feed(sample["year"]), sample["field"])
        if sample["needle"] in v
    ]

    assert to_markdown(value, site_url(sample["year"])) == sample["markdown"]


def test_samples_cover_every_tag_of_the_census() -> None:
    """D-114: the 22 samples hold all 17 tags of both feeds, so each is device-checked."""
    tags = set()
    for sample in SAMPLES:
        (value,) = [
            v
            for v in values_at(feed(sample["year"]), sample["field"])
            if sample["needle"] in v
        ]
        tags |= {m.lower() for m in re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)", value)}

    assert tags == {
        *("p", "li", "strong", "a", "code", "em", "ul", "h2", "br", "h3", "ol"),
        *("h4", "h1", "span", "hr", "s", "blockquote"),
    }


def test_every_html_field_of_both_feeds_is_counted() -> None:
    """D-114: the invariant below sees all 1,389 values S3 converted, empty ones included."""
    assert sum(1 for year in (2025, 2026) for _ in html_fields(year)) == 1389


@pytest.mark.parametrize("year", [2025, 2026])
def test_no_visible_character_is_lost_or_added_in_any_feed_value(year: int) -> None:
    """D-114 invariant: whitespace aside, the Markdown shows exactly the HTML's text."""
    changed = [
        value[:80]
        for value in html_fields(year)
        if markdown_text(to_markdown(value, site_url(year))) != html_text(value)
    ]

    assert changed == []


@pytest.mark.parametrize("year", [2025, 2026])
def test_no_raw_tag_dollar_or_latex_opener_is_left_outside_code(year: int) -> None:
    """D-115 invariant: nothing outside code spans can start HTML or Flet's LaTeX (F27)."""
    leftovers = [
        leftover
        for value in html_fields(year)
        for leftover in re.findall(
            r"</?[a-zA-Z]+|\$|\\[(\[]",
            outside_code(to_markdown(value, site_url(year))),
        )
    ]

    assert leftovers == []


@pytest.mark.parametrize("year", [2025, 2026])
def test_search_text_of_every_feed_value_is_its_visible_text(year: int) -> None:
    """D-46: the text form keeps every visible character and adds no markup."""
    changed = [
        value[:80]
        for value in html_fields(year)
        if "".join(to_text(value).split()) != html_text(value)
    ]

    assert changed == []
