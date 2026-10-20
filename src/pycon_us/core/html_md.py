r"""Convert the feed's HTML fields to Markdown for ``ft.Markdown``, and to text for search.

The rules are D-114 and D-115 (S3, ``docs/spikes/03-html-markdown.md``; DATA-25, SESS-06):

- A value is parsed with stdlib ``html.parser`` into a small tree, then rendered. Tags
  outside the S3 census are unwrapped (their text stays where it was); ``script`` and
  ``style`` are dropped with their text. Whitespace collapses as in a browser; only
  ``br`` breaks a line.
- A value with no tag is plain text: blank lines separate paragraphs and a single
  newline is a hard break.
- Text is escaped with numeric character references, never backslashes: Flet's
  ``Markdown`` always adds LaTeX syntax (F27), whose ``\(`` and ``\[`` openers a
  backslash escape would create, and GFM reads ``~x~`` and ``:name:``. Code spans are raw.
- Links are joined to the year's site URL, and only ``http``, ``https`` and ``mailto``
  become links. A bare URL in text becomes an explicit link, so GFM's autolinks never
  decide where it ends.

``to_text`` gives the visible text with no markup, for search (D-46).

This module holds the HTML side: the tree, its blocks and the walk over inline elements.
The Markdown they become, escaped text, emphasis, links and code spans, is
``markdown_inline`` (D-201).
"""

import re
from html import unescape
from html.parser import HTMLParser

from pycon_us.core.markdown_inline import (
    SPACE_CHARS,
    Emphasis,
    Token,
    around,
    code,
    escape,
    escape_line_start,
    link,
    paragraph,
)

_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BLOCK_TAGS = frozenset({"p", "ul", "ol", "li", "blockquote", "hr", *_HEADINGS})
_EMPHASIS = {
    **dict.fromkeys(("strong", "b"), "**"),
    **dict.fromkeys(("em", "i"), "*"),
    **dict.fromkeys(("s", "del", "strike"), "~~"),
}
DROPPED_TAGS = frozenset({"script", "style"})  # their text is not content
_KNOWN_TAGS = _BLOCK_TAGS | {"a", "code", "br", *_EMPHASIS}
_VOID_TAGS = frozenset({"br", "hr"})  # never have children or end tags

_HAS_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_HTML_SPACE = re.compile(f"[{SPACE_CHARS}]+")  # the set paragraph() and around() strip
_NESTED_LIST = re.compile(r"- |\d+\. ")  # an escaped paragraph never starts like this


class _Element:
    """An element of the parsed tree: its tag, attributes and children."""

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Element | str] = []


class _TreeBuilder(HTMLParser):
    """Builds an ``_Element`` tree, tolerating unclosed and stray end tags.

    Unknown tags never enter the tree, so their children land in their parent: that is
    what unwrapping means (D-114). ``script`` and ``style`` are skipped with their text.
    An emphasis or code element that directly follows one of the same kind continues it
    (D-131): rendered apart, their markers would touch and show literally (``*a**b*``).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("root", {})
        self._open = [self.root]
        self._dropping: str | None = None  # the script or style element being skipped

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROPPED_TAGS:
            self._dropping = tag
        if tag not in _KNOWN_TAGS:
            return
        parent = self._open[-1]
        previous = parent.children[-1] if parent.children else None
        continues = tag == "code" or tag in _EMPHASIS
        if (
            continues
            and isinstance(previous, _Element)
            and _kind(previous.tag) == _kind(tag)
        ):
            self._open.append(previous)
            return
        element = _Element(tag, {name: value or "" for name, value in attrs})
        parent.children.append(element)
        if tag not in _VOID_TAGS:
            self._open.append(element)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._dropping:
            self._dropping = None
        # Close the innermost open element of this kind, and any left open inside it.
        for depth in range(len(self._open) - 1, 0, -1):
            if _kind(self._open[depth].tag) == _kind(tag):
                del self._open[depth:]
                return

    def handle_data(self, data: str) -> None:
        if self._dropping is None:
            self._open[-1].children.append(data)


def _kind(tag: str) -> str:
    """Tags that render the same are one kind: ``b`` and ``strong`` are both ``**``."""
    return _EMPHASIS.get(tag, tag)


def to_markdown(value: str, site_url: str) -> str:
    """Convert one feed field to Markdown (D-114, D-115).

    Args:
        value: The field: HTML, or plain text when it has no tag.
        site_url: The year's site URL, which relative links are joined to.

    Returns:
        Markdown for ``ft.Markdown(extension_set=GITHUB_WEB)``; empty for an empty field.
    """
    if not _HAS_TAG.search(value):
        return _plain_to_markdown(value)
    return "\n\n".join(_blocks(_parse(value), site_url))


def to_text(value: str) -> str:
    """Return a field's visible text, with no markup, for search (D-46).

    Blocks and line breaks become spaces, so words never join; link targets, ``script``
    and ``style`` are left out. Whitespace runs become one space.

    Args:
        value: The field: HTML, or plain text when it has no tag.

    Returns:
        The text, not yet folded for search.
    """
    text = unescape(value) if not _HAS_TAG.search(value) else _text_of(_parse(value))
    return " ".join(text.split())


def _parse(html: str) -> _Element:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def _text_of(element: _Element) -> str:
    """Return the raw text inside an element, with a space for each block and break."""
    parts = []
    for child in element.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag in _BLOCK_TAGS or child.tag == "br":
            parts.append(f" {_text_of(child)} ")
        else:
            parts.append(_text_of(child))
    return "".join(parts)


# Plain text (D-114: 15 of the 24 2026 sprint descriptions)


def _plain_to_markdown(value: str) -> str:
    paragraphs: list[list[str]] = [[]]
    for line in unescape(value).splitlines():
        if line.strip():
            paragraphs[-1].append(escape_line_start(escape(line.strip())))
        elif paragraphs[-1]:
            paragraphs.append([])
    return "\n\n".join("  \n".join(lines) for lines in paragraphs if lines)


# Blocks


def _blocks(container: _Element, site_url: str) -> list[str]:
    """Render a container's children as Markdown blocks; inline runs become paragraphs."""
    blocks: list[str] = []
    run: list[Token] = []

    def end_run() -> None:
        if text := paragraph(run):
            blocks.append(text)
        run.clear()

    for child in container.children:
        if isinstance(child, _Element) and child.tag in _BLOCK_TAGS:
            end_run()
            blocks.extend(_block(child, site_url))
        else:
            run.extend(_inline(child, site_url))
    end_run()
    return blocks


def _block(element: _Element, site_url: str) -> list[str]:
    tag = element.tag
    if tag == "hr":
        return ["---"]
    if tag in ("ul", "ol"):
        return [_list(_items(element), ordered=tag == "ol", site_url=site_url)]
    if tag == "li":  # an item outside a list
        return [_list([element], ordered=False, site_url=site_url)]
    if tag == "blockquote":
        lines = "\n\n".join(_blocks(element, site_url)).split("\n")
        return ["\n".join(f"> {line}" if line else ">" for line in lines)]
    if tag in _HEADINGS:
        tokens = [t for child in element.children for t in _inline(child, site_url)]
        # Markdown headings are one line, so a br becomes a space (D-114).
        text = paragraph(tokens).replace("  \n", " ")
        return [f"{'#' * int(tag[1])} {text}"] if text else []
    return _blocks(element, site_url)  # p


def _items(list_element: _Element) -> list[_Element]:
    """Return a list's items; content between items becomes an item, so its text shows."""
    items: list[_Element] = []
    made: list[_Element] = []  # the items made for content outside any li
    for child in list_element.children:
        if isinstance(child, _Element) and child.tag == "li":
            items.append(child)
            continue
        if not made or items[-1] is not made[-1]:
            made.append(_Element("li", {}))
            items.append(made[-1])
        made[-1].children.append(child)
    # Whitespace between items is not content.
    return [item for item in items if item not in made or _text_of(item).strip()]


def _list(items: list[_Element], *, ordered: bool, site_url: str) -> str:
    """Render list items; continuation lines are indented by the marker's width (D-114)."""
    lines = []
    for number, item in enumerate(items, start=1):
        marker = f"{number}. " if ordered else "- "
        indent = " " * len(marker)
        first, *rest = _item_body(_blocks(item, site_url)).split("\n")
        lines.append(marker + first)
        lines.extend(indent + line if line else "" for line in rest)
    return "\n".join(lines)


def _item_body(blocks: list[str]) -> str:
    """Join an item's blocks: a nested list follows on the next line, a paragraph after a gap."""
    body = ""
    for block in blocks:
        if not body:
            body = block
        elif _NESTED_LIST.match(block):
            body += "\n" + block
        else:
            body += "\n\n" + block
    return body


# Inline content


def _inline(
    node: _Element | str, site_url: str, *, in_link: bool = False
) -> list[Token]:
    r"""Render inline content as tokens: Markdown text, ``\n`` for a break, and emphasis."""
    if isinstance(node, str):
        return [escape(_HTML_SPACE.sub(" ", node), linkify=not in_link)]
    tag = node.tag
    if tag == "br":
        return ["\n"]
    if tag == "code":
        return code(_HTML_SPACE.sub(" ", _text_of(node)))
    inner_in_link = in_link or tag == "a"  # inside a link, URLs and links stay text
    inner = [
        t
        for child in node.children
        for t in _inline(child, site_url, in_link=inner_in_link)
    ]
    if tag in _EMPHASIS:
        emphasis = Emphasis(_EMPHASIS[tag])
        return around(inner, [emphasis], [emphasis])
    if tag == "a" and not in_link:
        return link(inner, node.attrs.get("href", "").strip(), site_url)
    if tag in _BLOCK_TAGS:  # a block inside an inline element: keep words apart
        return [" ", *inner, " "]
    return inner  # a nested a
