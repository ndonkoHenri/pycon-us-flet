"""S3 census: every markup-bearing field of the 2025 and 2026 feeds, and the prototype's coverage.

Run from the repository root (stdlib only, no network):

    python3 -I docs/spikes/03-html-markdown/census.py

It reads `tests/fixtures/feeds/conference-<year>.json`, prints the census and
the coverage tables used in `docs/spikes/03-html-markdown.md`, and writes the
render samples to `docs/spikes/03-html-markdown/src/samples.json`.
"""

import html
import json
import re
import sys
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from html_md_proto import BLOCK_TAGS, DROPPED_TAGS, INLINE_TAGS, to_markdown

ROOT = HERE.parents[2]
YEARS = (2025, 2026)
SITE_URL = "https://us.pycon.org"
TAG = re.compile(r"</?[a-zA-Z][^>]*>")
ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")
MD_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)")

# (year, field, a string only that value contains, what it shows) for the render check.
SAMPLES = [
    (2026, ".schedule[].description", "Dunder Methods", "ol, &amp;"),
    (
        2026,
        ".schedule[].description",
        "Huge thanks to the DAY2",
        "newlines in p, hr, h2, strong",
    ),
    (2026, ".schedule[].description", "Apify", "ol of links"),
    (
        2025,
        ".schedule[].description",
        "keynote-speakers#lynn-root",
        "relative link, br, span",
    ),
    (2025, ".schedule[].description", "file zoos", "h1, h2"),
    (
        2025,
        ".schedule[].description",
        "Creando Bibliotecas de Python con Rust",
        "h1 > strong, Spanish",
    ),
    (2025, ".schedule[].description", "CANCELLED: <s>", "s (strike-through)"),
    (2025, ".schedule[].description", "devops for devops", "hr between paragraphs"),
    (2025, ".schedule[].description", "len([x for x in arr", "code with [ ] and %"),
    (
        2025,
        ".schedule[].description",
        "<h4>Contenido principal:</h4>",
        "h4, ul > li > strong",
    ),
    (2025, ".schedule[].description", "&lt;head&gt;", "code with &lt; &gt;"),
    (2026, ".schedule[].speakers[].bio", "<blockquote>", "blockquote"),
    (
        2026,
        ".job-listings[].description_html",
        "Compensation:",
        "h2, strong, $ amounts, bare URL",
    ),
    (2026, ".job-listings[].description_html", "Base Salary Range", "$ range, lists"),
    (
        2026,
        ".job-listings[].description_html",
        "bloomberg",
        "ul > li > p > a with target, rel, class",
    ),
    (2026, ".conference.content.social-media", "", "nested ul, code handles"),
    (2026, ".conference.content.venues-hours", "", "h2, h3, ul"),
    (2026, ".conference.content.code-of-conduct", "", "mailto link"),
    (2026, ".posters[].speakers[].bio", "Who am I?", "h1 + ul in a bio"),
    (2026, ".posters[].description_html", "&mdash;", "&mdash;, bare URL"),
    (2026, ".sprints[].description_html", "Arcade is", "plain text with paragraphs"),
    (
        2025,
        ".schedule[].sessions[].description",
        "python-chess",
        "br-separated pseudo-list",
    ),
]
# Text Flet's Markdown would misread without escaping (LaTeX, GFM, block markers).
HAZARD = "Tickets cost 5$ or 10$ at the door. Read ( the notes ) and [ the FAQ ] first.\n1999. A good year | x ~y~ *z* :smile: #tag"


def walk(value: object, path: str = "") -> object:
    """Yield (path, string) for every string in the feed; list indices become `[]`."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for child in value:
            yield from walk(child, f"{path}[]")
    elif isinstance(value, str):
        yield path, value


def field_of(path: str) -> str:
    """Name the six content blocks individually and sponsor levels together."""
    return re.sub(r"\.sponsors\.[^.\[]+\[\]", ".sponsors.<level>[]", path)


class _Census(HTMLParser):
    """Counts tags, attributes and entities of one field value."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.tags: Counter[str] = Counter()
        self.attrs: Counter[str] = Counter()
        self.entities: Counter[str] = Counter()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags[tag] += 1
        for name, value in attrs:
            shown = f"={value}" if name != "href" else ""
            self.attrs[f"{tag}@{name}{shown}"] += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_entityref(self, name: str) -> None:
        self.entities[f"&{name};"] += 1

    def handle_charref(self, name: str) -> None:
        self.entities[f"&#{name};"] += 1


class _TextOf(HTMLParser):
    """The text a browser would show, as words."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_text(value: str) -> str:
    """The HTML's visible characters, whitespace removed (plain text counts as text)."""
    if not TAG.search(value):
        return "".join(html.unescape(value).split())
    parser = _TextOf()
    parser.feed(value)
    parser.close()
    return "".join("".join(parser.parts).split())


def markdown_text(markdown: str) -> str:
    """Our Markdown's visible characters: our syntax removed, references decoded, whitespace removed.

    Outside code spans every raw `*`, `~`, `[` and `#` is ours, because text
    escapes them; code spans show their content as is.
    """
    shown = []
    markdown = re.sub(r"\]\([^)\s]*\)", "]", markdown)  # link destinations
    markdown = re.sub(r"^(#+ |> ?|---$)", "", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"^[ \t]*(- |\d+\. )", "", markdown, flags=re.MULTILINE)
    for i, part in enumerate(re.split(r"(`+)(.*?)\1", markdown)):
        if i % 3 == 1:
            continue  # the fence
        if i % 3 == 2:
            shown.append(part)  # code content
            continue
        shown.append(html.unescape(re.sub(r"[*~\[\]]", "", part)))
    return "".join("".join(shown).split())


def main() -> None:
    """Print the census and write the render samples."""
    feeds = {
        y: json.loads((ROOT / f"tests/fixtures/feeds/conference-{y}.json").read_text())
        for y in YEARS
    }
    stats: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    tags: dict[str, Counter[str]] = defaultdict(Counter)
    attrs: Counter[str] = Counter()
    entities: Counter[str] = Counter()
    lost: list[tuple[int, str, str]] = []
    leftovers: Counter[str] = Counter()
    values: dict[tuple[int, str], list[str]] = defaultdict(list)

    for year, feed in feeds.items():
        for path, value in walk(feed):
            field = field_of(path)
            values[year, field].append(value)
            row = stats[year, field]
            row["strings"] += 1
            has_tag = bool(TAG.search(value))
            row["html"] += has_tag
            row["entities"] += bool(ENTITY.search(value))
            row["md links"] += bool(MD_LINK.search(value))
            if not has_tag:
                continue
            census = _Census()
            census.feed(value)
            census.close()
            for tag, count in census.tags.items():
                tags[tag][f"{year} {field}"] += count
            attrs.update(census.attrs)
            entities.update(census.entities)

    # Slot names are cleaned to plain text by the name rules (DATA-08), not converted.
    html_fields = sorted(
        {k for k, row in stats.items() if row["html"] and k[1] != ".schedule[].name"}
    )
    print(
        "## Fields with markup (strings, with tags, with entities, with Markdown links)"
    )
    for key, row in sorted(stats.items()):
        if row["html"] or row["entities"] or row["md links"]:
            print(f"{key[0]} {key[1]}: {dict(row)}")

    print("\n## Tag census (occurrences; fields)")
    for tag, where in sorted(tags.items(), key=lambda kv: -sum(kv[1].values())):
        handled = (
            "handled" if tag in BLOCK_TAGS | INLINE_TAGS | DROPPED_TAGS else "UNWRAPPED"
        )
        print(f"{tag}: {sum(where.values())} [{handled}] {dict(where)}")
    print("\n## Attributes", attrs.most_common())
    print("\n## Entities", entities.most_common())

    print("\n## HTML fields: values | with tags | plain text | empty")
    for year, field in html_fields:
        vals = values[year, field]
        tagged = sum(bool(TAG.search(v)) for v in vals)
        empty = sum(not v.strip() for v in vals)
        print(
            f"| {year} | `{field}` | {len(vals)} | {tagged} | {len(vals) - tagged - empty} | {empty} |"
        )

    converted = 0
    for year, field in html_fields:
        # Every value of an HTML field, plain-text ones included, goes through the converter.
        for value in values[year, field]:
            markdown = to_markdown(value, SITE_URL)
            converted += 1
            if html_text(value) != markdown_text(markdown):
                lost.append((year, field, value[:80]))
            outside_code = re.sub(r"(`+).*?\1", "", markdown)
            for leftover in re.findall(r"</?[a-zA-Z]+|\$|\\[(\[]", outside_code):
                leftovers[leftover] += 1
    print(f"\n## Converted {converted} values of {len(html_fields)} HTML fields")
    print(f"text changed in {len(lost)}:")
    for item in lost:
        print("  ", item)
    print(
        "raw tags, $ or LaTeX openers left in the Markdown:", dict(leftovers) or "none"
    )

    samples = []
    for year, field, needle, why in SAMPLES:
        (value,) = [v for v in values[year, field] if needle in v]  # exactly one match
        samples.append(
            {
                "year": year,
                "field": field,
                "why": why,
                "html": value,
                "markdown": to_markdown(value, SITE_URL),
            }
        )
    for why, markdown in (
        ("hazard, unescaped", HAZARD),
        ("hazard, escaped", to_markdown(HAZARD, SITE_URL)),
    ):
        samples.append(
            {
                "year": 0,
                "field": "synthetic",
                "why": why,
                "html": HAZARD,
                "markdown": markdown,
            }
        )
    out = HERE / "src" / "samples.json"
    out.write_text(json.dumps(samples, indent=1, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(samples)} samples to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
