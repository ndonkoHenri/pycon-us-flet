r"""S3 prototype: convert the feed's HTML fields to Markdown for `ft.Markdown`.

A spike reproducer, not app code: P0-15 (#67) writes `pycon_us/core/html_md.py`
from the verdict in `docs/spikes/03-html-markdown.md`. Stdlib only.

The design follows architecture §7.7 with what S3 found:
- the HTML is parsed into a small tree, then rendered; unknown tags are
  unwrapped, so their text survives;
- text is escaped with numeric character references, because Flet's Markdown
  always enables LaTeX (`$...$`, `( ... )`, `[ ... ]`) on top of the
  extension set, backslash escapes collide with `\(` and `\[`, and GFM
  turns `:name:` into emoji;
- bare `http(s)` URLs in text become explicit links, so nothing is left raw;
- a field with no tags is plain text (entities decoded): blank lines make
  paragraphs and single newlines make line breaks.
"""

import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, urljoin

BLOCK_TAGS = {
    "p",
    "ul",
    "ol",
    "li",
    "blockquote",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}
INLINE_TAGS = {"a", "strong", "b", "em", "i", "code", "s", "del", "strike", "br"}
DROPPED_TAGS = {"script", "style"}  # their text is not content
VOID_TAGS = {"br", "hr", "img", "wbr"}
LINK_SCHEMES = ("http://", "https://", "mailto:")

# Characters Markdown, GFM or Flet's LaTeX syntax could read as markup, anywhere in a line.
_INLINE_SPECIALS = re.compile(r"[\\`*_\[\](<>|~$&:]")
# Block markers that only matter at the start of a line.
_LINE_START = re.compile(r"^(#|>|[-+=]|\d+[.)])")
_URL = re.compile(r"https?://[^\s<>\"]+")
_URL_TRAILER = re.compile(
    r"[.,;:!?\'\")\]]+$"
)  # punctuation that ends a sentence, not the URL
_HTML_SPACE = re.compile(r"[ \t\n\r\f]+")
_HAS_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


class Node:
    """An element of the parsed tree: a tag, its attributes and its children."""

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        """Create an element with no children."""
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node | str] = []


class _TreeBuilder(HTMLParser):
    """Builds a `Node` tree; tolerates unclosed and stray end tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for depth in range(len(self.stack) - 1, 0, -1):
            if self.stack[depth].tag == tag:
                del self.stack[depth:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def escape(text: str, linkify: bool = True) -> str:
    """Escape text for Markdown; with `linkify`, bare URLs become links."""
    if not linkify:
        return _escape_chars(text)
    parts = []
    last = 0
    for match in _URL.finditer(text):
        url = _URL_TRAILER.sub("", match.group(0))
        parts.append(_escape_chars(text[last : match.start()]))
        parts.append(f"[{_escape_chars(url)}]({_destination(url)})")
        last = match.start() + len(url)
    parts.append(_escape_chars(text[last:]))
    return "".join(parts)


def _destination(url: str) -> str:
    return quote(url, safe=":/?#@!&'*+,;=%~-._")


def _escape_chars(text: str) -> str:
    return _INLINE_SPECIALS.sub(lambda m: f"&#{ord(m.group(0))};", text)


def _escape_line_start(line: str) -> str:
    match = _LINE_START.match(line)
    if not match:
        return line
    marker = match.group(1)
    return line[: len(marker) - 1] + f"&#{ord(marker[-1])};" + line[len(marker) :]


def _inline(node: Node | str, base_url: str, in_link: bool = False) -> str:
    r"""Render inline content; `\n` marks a hard line break."""
    if isinstance(node, str):
        return escape(_HTML_SPACE.sub(" ", node), linkify=not in_link)
    if node.tag in DROPPED_TAGS:
        return ""
    if node.tag == "br":
        return "\n"
    if node.tag == "code":
        return _code_span(_HTML_SPACE.sub(" ", _text_of(node)))
    in_link = in_link or node.tag == "a"  # links cannot nest
    inner = "".join(_inline(child, base_url, in_link) for child in node.children)
    if node.tag in ("strong", "b"):
        return _wrap(inner, "**")
    if node.tag in ("em", "i"):
        return _wrap(inner, "*")
    if node.tag in ("s", "del", "strike"):
        return _wrap(inner, "~~")
    if node.tag == "a":
        return _link(inner, node.attrs.get("href", ""), base_url)
    return inner  # unknown inline tag (span, ...) or a block tag inside inline content


def _wrap(inner: str, marker: str) -> str:
    """Wrap with an emphasis marker, keeping edge whitespace outside it."""
    return _around(inner, marker, marker)


def _link(inner: str, href: str, base_url: str) -> str:
    url = urljoin(base_url, href.strip())
    if not url.startswith(LINK_SCHEMES):
        return inner
    return _around(inner, "[", f"]({_destination(url)})")


def _around(inner: str, before: str, after: str) -> str:
    """Put markup around the text, leaving its edge whitespace outside."""
    core = inner.strip()
    if not core:
        return inner
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()) :]
    return f"{lead}{before}{core}{after}{trail}"


def _code_span(text: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _text_of(node: Node | str) -> str:
    if isinstance(node, str):
        return node
    return "".join(_text_of(child) for child in node.children)


def _paragraph(inline: str) -> str:
    lines = [line.strip() for line in inline.split("\n")]
    lines = [_escape_line_start(line) for line in lines if line]
    return "  \n".join(lines)


def _blocks(node: Node, base_url: str) -> list[str]:
    """Render a container's children as Markdown blocks."""
    blocks: list[str] = []
    run: list[str] = []

    def flush() -> None:
        text = _paragraph("".join(run))
        if text:
            blocks.append(text)
        run.clear()

    for child in _unwrapped(node.children):
        if isinstance(child, Node) and child.tag in BLOCK_TAGS:
            flush()
            blocks.extend(_block(child, base_url))
        else:
            run.append(_inline(child, base_url))
    flush()
    return blocks


def _unwrapped(children: list[Node | str]) -> list[Node | str]:
    """Replace unknown elements by their children, so their text stays in place."""
    out: list[Node | str] = []
    for child in children:
        if (
            isinstance(child, Node)
            and child.tag not in BLOCK_TAGS | INLINE_TAGS | DROPPED_TAGS
        ):
            out.extend(_unwrapped(child.children))
        else:
            out.append(child)
    return out


def _block(node: Node, base_url: str) -> list[str]:
    tag = node.tag
    if tag == "hr":
        return ["---"]
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        text = _paragraph("".join(_inline(c, base_url) for c in node.children))
        text = text.replace("  \n", " ")
        return [f"{'#' * int(tag[1])} {text}"] if text else []
    if tag in ("ul", "ol"):
        return [_list(node, base_url)]
    if tag == "blockquote":
        inner = "\n\n".join(_blocks(node, base_url))
        return ["\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))]
    if tag == "li":  # a stray li outside a list
        return [_list(Node("ul", {}), base_url, items=[node])]
    return _blocks(node, base_url)  # p


def _list(node: Node, base_url: str, items: list[Node] | None = None) -> str:
    if items is None:
        items = [c for c in node.children if isinstance(c, Node) and c.tag == "li"]
    lines = []
    for number, item in enumerate(items, start=1):
        marker = f"{number}. " if node.tag == "ol" else "- "
        body = _join_item_blocks(_blocks(item, base_url))
        indent = " " * len(marker)
        for i, line in enumerate(body.split("\n")):
            if i == 0:
                lines.append(marker + line)
            else:
                lines.append(indent + line if line else "")
    return "\n".join(lines)


def _join_item_blocks(blocks: list[str]) -> str:
    """Join an item's blocks: paragraphs need a blank line, lists don't."""
    out = ""
    for block in blocks:
        if not out:
            out = block
        elif re.match(
            r"(- |\d+\. )", block
        ):  # a nested list; paragraphs never start so
            out += "\n" + block
        else:
            out += "\n\n" + block
    return out


def _plain(text: str) -> str:
    paragraphs = re.split(r"\n[ \t]*\n+", unescape(text).strip())
    out = []
    for paragraph in paragraphs:
        lines = [
            _escape_line_start(escape(line.strip())) for line in paragraph.split("\n")
        ]
        out.append("  \n".join(line for line in lines if line))
    return "\n\n".join(p for p in out if p)


def to_markdown(html: str, base_url: str) -> str:
    """Convert one feed field to Markdown.

    Args:
        html: the field's value: HTML, or plain text when it has no tags.
        base_url: the site URL relative links resolve against.

    Returns:
        Markdown for `ft.Markdown(extension_set=GITHUB_WEB)`.
    """
    if not _HAS_TAG.search(html):
        return _plain(html)
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return "\n\n".join(_blocks(builder.root, base_url))


def tag_names(html: str) -> set[str]:
    """Return the tags a field uses (for the census)."""
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    names: set[str] = set()

    def visit(node: Node) -> None:
        for child in node.children:
            if isinstance(child, Node):
                names.add(child.tag)
                visit(child)

    visit(builder.root)
    return names
