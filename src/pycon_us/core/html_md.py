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
"""

import re
import unicodedata
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BLOCK_TAGS = frozenset({"p", "ul", "ol", "li", "blockquote", "hr", *_HEADINGS})
_EMPHASIS = {
    **dict.fromkeys(("strong", "b"), "**"),
    **dict.fromkeys(("em", "i"), "*"),
    **dict.fromkeys(("s", "del", "strike"), "~~"),
}
_DROPPED_TAGS = frozenset({"script", "style"})  # their text is not content
_KNOWN_TAGS = _BLOCK_TAGS | _DROPPED_TAGS | {"a", "code", "br", *_EMPHASIS}
_VOID_TAGS = frozenset({"br", "hr"})  # never have children or end tags
_LINK_SCHEMES = frozenset({"http", "https", "mailto"})

_HAS_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_HTML_SPACE = re.compile(r"[ \t\n\r\f]+")  # HTML's whitespace; a no-break space is text
_HTML_SPACE_CHARS = " \t\n\r\f"
# D-115: characters Markdown, GFM or Flet's LaTeX syntax could read as markup, anywhere.
_SPECIALS = re.compile(r"[\\`*_\[\](<>|~$&:]")
# D-115: block markers that matter only at the start of a line (">" is already escaped).
_LINE_START = re.compile(r"#|[-+=]|\d+[.)]")
_URL = re.compile(r"https?://[^\s<>\"]+")
# D-114: sentence punctuation after a URL ends the sentence, not the URL.
_URL_TRAILER = re.compile(r"[.,;:!?'\")\]’”]+$")
_DESTINATION_SAFE = ":/?#@!&'*+,;=%~-._"  # everything else is percent-encoded
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
    what unwrapping means (D-114).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("root", {})
        self._open = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _KNOWN_TAGS:
            return
        element = _Element(tag, {name: value or "" for name, value in attrs})
        self._open[-1].children.append(element)
        if tag not in _VOID_TAGS:
            self._open.append(element)

    def handle_endtag(self, tag: str) -> None:
        # Close the innermost open element with this tag, and any left open inside it.
        for depth in range(len(self._open) - 1, 0, -1):
            if self._open[depth].tag == tag:
                del self._open[depth:]
                return

    def handle_data(self, data: str) -> None:
        self._open[-1].children.append(data)


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
        elif child.tag not in _DROPPED_TAGS:
            parts.append(_text_of(child))
    return "".join(parts)


# Plain text (D-114: 15 of the 24 2026 sprint descriptions)


def _plain_to_markdown(value: str) -> str:
    paragraphs: list[list[str]] = [[]]
    for line in unescape(value).splitlines():
        if line.strip():
            paragraphs[-1].append(_escape_line_start(_escape(line.strip())))
        elif paragraphs[-1]:
            paragraphs.append([])
    return "\n\n".join("  \n".join(lines) for lines in paragraphs if lines)


# Escaping (D-115)


def _escape(text: str, *, linkify: bool = True) -> str:
    """Escape text; with ``linkify``, bare ``http(s)`` URLs become explicit links (D-114)."""
    if not linkify:
        return _escape_chars(text)
    parts = []
    done = 0
    for match in _URL.finditer(text):
        url = _URL_TRAILER.sub("", match.group())
        if url.endswith("://"):  # only punctuation after the scheme: not a URL
            continue
        parts.append(_escape_chars(text[done : match.start()]))
        parts.append(f"[{_escape_chars(url)}]({_destination(url)})")
        done = match.start() + len(url)
    parts.append(_escape_chars(text[done:]))
    return "".join(parts)


def _escape_chars(text: str) -> str:
    return _SPECIALS.sub(lambda match: f"&#{ord(match.group())};", text)


def _escape_line_start(line: str) -> str:
    """Escape the last character of a block marker at the start of a line."""
    match = _LINE_START.match(line)
    if not match:
        return line
    end = match.end()
    return f"{line[: end - 1]}&#{ord(line[end - 1])};{line[end:]}"


def _destination(url: str) -> str:
    return quote(url, safe=_DESTINATION_SAFE)


# Blocks


def _blocks(container: _Element, site_url: str) -> list[str]:
    """Render a container's children as Markdown blocks; inline runs become paragraphs."""
    blocks: list[str] = []
    run: list[_Token] = []

    def end_run() -> None:
        if paragraph := _paragraph(run):
            blocks.append(paragraph)
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
        text = _paragraph(tokens).replace("  \n", " ")
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


def _paragraph(tokens: list[_Token]) -> str:
    r"""Render an inline run as a paragraph; ``\n`` in it marks a hard break."""
    lines = []
    for line in _resolve(tokens).split("\n"):
        # Space runs come from blocks inside inline elements; they are never meaningful.
        line = re.sub(" {2,}", " ", line).strip(_HTML_SPACE_CHARS)
        if line:
            lines.append(_escape_line_start(line))
    return "  \n".join(lines)


# Inline content


class _Emphasis:
    """One emphasis pair; it appears twice in a token list, as its opener then its closer.

    Attributes:
        marker: ``**``, ``*`` or ``~~``.
        kept: False once the pair is found unable to flank, so it renders as nothing.
    """

    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.kept = True


type _Token = str | _Emphasis


def _inline(
    node: _Element | str, site_url: str, *, in_link: bool = False
) -> list[_Token]:
    r"""Render inline content as tokens: Markdown text, ``\n`` for a break, and emphasis."""
    if isinstance(node, str):
        return [_escape(_HTML_SPACE.sub(" ", node), linkify=not in_link)]
    tag = node.tag
    if tag in _DROPPED_TAGS:
        return []
    if tag == "br":
        return ["\n"]
    if tag == "code":
        return _code(_HTML_SPACE.sub(" ", _text_of(node)))
    inner_in_link = in_link or tag == "a"  # inside a link, URLs and links stay text
    inner = [
        t
        for child in node.children
        for t in _inline(child, site_url, in_link=inner_in_link)
    ]
    if tag in _EMPHASIS:
        emphasis = _Emphasis(_EMPHASIS[tag])
        return _around(inner, [emphasis], [emphasis])
    if tag == "a" and not in_link:
        return _link(inner, node.attrs.get("href", "").strip(), site_url)
    if tag in _BLOCK_TAGS:  # a block inside an inline element: keep words apart
        return [" ", *inner, " "]
    return inner  # a nested a


def _link(inner: list[_Token], href: str, site_url: str) -> list[_Token]:
    """Wrap a link's text in ``[...](url)``, or leave it as text (D-114)."""
    if not href:
        return inner
    url = urljoin(site_url, href)
    if urlsplit(url).scheme not in _LINK_SCHEMES:
        return inner
    return _around(inner, ["["], [f"]({_destination(url)})"])


def _code(text: str) -> list[_Token]:
    """Render a code span, raw, fenced with one backtick more than its longest run (D-115).

    Edge spaces stay outside the span, because the renderer trims one at each edge and the
    words around it would join; a span with no text renders as its spaces.
    """
    core = text.strip(" ")
    if not core:
        return [text]
    fence = "`" * (max((len(run) for run in re.findall("`+", core)), default=0) + 1)
    pad = " " if core.startswith("`") or core.endswith("`") else ""
    lead = text[: len(text) - len(text.lstrip(" "))]
    trail = text[len(text.rstrip(" ")) :]
    return [lead, f"{fence}{pad}{core}{pad}{fence}", trail]


def _around(
    inner: list[_Token], before: list[_Token], after: list[_Token]
) -> list[_Token]:
    """Put markup around inline tokens, leaving their edge whitespace outside it (D-114)."""
    tokens = _merged(inner)
    lead = trail = ""
    if tokens and isinstance(tokens[0], str):
        lead = tokens[0][: len(tokens[0]) - len(tokens[0].lstrip(_HTML_SPACE_CHARS))]
        tokens[0] = tokens[0][len(lead) :]
    if tokens and isinstance(tokens[-1], str):
        trail = tokens[-1][len(tokens[-1].rstrip(_HTML_SPACE_CHARS)) :]
        tokens[-1] = tokens[-1][: len(tokens[-1]) - len(trail)]
    tokens = [t for t in tokens if t != ""]
    if not tokens:
        return [lead + trail]
    return [lead, *before, *tokens, *after, trail]


def _merged(tokens: list[_Token]) -> list[_Token]:
    """Join neighbouring text tokens, so edge whitespace sits in the first and last."""
    merged: list[_Token] = []
    for token in tokens:
        if isinstance(token, str) and merged and isinstance(merged[-1], str):
            merged[-1] += token
        elif token != "":
            merged.append(token)
    return merged


def _resolve(tokens: list[_Token]) -> str:
    """Render tokens to Markdown, dropping emphasis that CommonMark could not read (D-114).

    An opener must be left-flanking and a closer right-flanking. Emphasis that starts or
    ends with punctuation and touches a letter outside fails that, and would show its
    markers literally. Dropping one pair changes its neighbours' context, so the check
    repeats until nothing changes.
    """
    positions: dict[_Emphasis, list[int]] = {}
    for index, token in enumerate(tokens):
        if isinstance(token, _Emphasis):
            positions.setdefault(token, []).append(index)
    changed = True
    while changed:
        changed = False
        for emphasis, (opener, closer) in positions.items():
            run = emphasis.marker[0]
            if emphasis.kept and not (
                _flanks(tokens, opener, run, left=True)
                and _flanks(tokens, closer, run, left=False)
            ):
                emphasis.kept = False
                changed = True
    return "".join(
        t if isinstance(t, str) else t.marker if t.kept else "" for t in tokens
    )


def _flanks(tokens: list[_Token], index: int, run: str, *, left: bool) -> bool:
    """Whether the marker at ``index`` is left- (or right-) flanking in CommonMark.

    Neighbouring markers of the same character (``run``) join it in one delimiter run.
    """
    before = _neighbour(tokens, range(index - 1, -1, -1), run, last=True)
    after = _neighbour(tokens, range(index + 1, len(tokens)), run, last=False)
    inside, outside = (after, before) if left else (before, after)
    if inside.isspace():
        return False
    return not _is_punctuation(inside) or outside.isspace() or _is_punctuation(outside)


def _neighbour(tokens: list[_Token], indices: range, run: str, *, last: bool) -> str:
    """The first visible character in that direction, past the rest of the run.

    A line edge counts as a space.
    """
    for index in indices:
        token = tokens[index]
        text = token if isinstance(token, str) else token.marker if token.kept else ""
        if text and not (isinstance(token, _Emphasis) and text[0] == run):
            return text[-1] if last else text[0]
    return " "


def _is_punctuation(char: str) -> bool:
    # CommonMark counts Unicode punctuation and symbols; an escaped character starts
    # with "&" and ends with ";", so it counts the same as the character itself.
    return unicodedata.category(char)[0] in "PS"
