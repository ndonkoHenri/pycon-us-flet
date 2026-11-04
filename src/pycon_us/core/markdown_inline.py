r"""Markdown's inline layer for `html_md`: escaped text, emphasis, links and code spans.

`html_md` walks the parsed HTML and asks this module for the Markdown each inline
piece becomes; nothing else imports it (D-201). It knows no HTML tree and imports nothing
from `html_md`, so the dependency runs one way. The rules are D-114, D-115 and D-131:

- Text is escaped with numeric character references, never backslashes (D-115), and a
  bare `http(s)` URL becomes an explicit link (D-114).
- An inline run is a list of tokens: Markdown text, `\n` for a hard break, and
  `Emphasis` pairs. Markup goes around tokens with their edge whitespace outside it,
  and an emphasis pair that CommonMark could not read as one loses its markers before
  the run is joined into a paragraph.
"""

import re
import unicodedata
from urllib.parse import quote, urljoin, urlsplit

_LINK_SCHEMES = frozenset({"http", "https", "mailto"})
# HTML's whitespace; a no-break space is text. html_md collapses this same set.
SPACE_CHARS = " \t\n\r\f"
# D-115: characters Markdown, GFM or Flet's LaTeX syntax could read as markup, anywhere.
_SPECIALS = re.compile(r"[\\`*_\[\](<>|~$&:]")
# D-115: block markers that matter only at the start of a line (">" is already escaped).
_LINE_START = re.compile(r"#|[-+=]|\d+[.)]")
URL = re.compile(r"https?://[^\s<>\"]+")
# D-114: sentence punctuation after a URL ends the sentence, not the URL.
URL_TRAILER = re.compile(r"[.,;:!?'\")\]’”]+$")
_DESTINATION_SAFE = ":/?#@!&'*+,;=%~-._"  # everything else is percent-encoded


# Escaping (D-115)


def escape(text: str, *, linkify: bool = True) -> str:
    """Escape text; with `linkify`, bare `http(s)` URLs become explicit links (D-114)."""
    if not linkify:
        return _escape_chars(text)
    parts = []
    done = 0
    for match in URL.finditer(text):
        url = URL_TRAILER.sub("", match.group())
        if url.endswith("://"):  # only punctuation after the scheme: not a URL
            continue
        parts.append(_escape_chars(text[done : match.start()]))
        parts.append(f"[{_escape_chars(url)}]({_destination(url)})")
        done = match.start() + len(url)
    parts.append(_escape_chars(text[done:]))
    return "".join(parts)


def _escape_chars(text: str) -> str:
    return _SPECIALS.sub(lambda match: f"&#{ord(match.group())};", text)


def escape_line_start(line: str) -> str:
    """Escape the last character of a block marker at the start of a line."""
    match = _LINE_START.match(line)
    if not match:
        return line
    end = match.end()
    return f"{line[: end - 1]}&#{ord(line[end - 1])};{line[end:]}"


def _destination(url: str) -> str:
    # JSON can carry a lone surrogate (the escape \ud800), which strict UTF-8 cannot
    # encode; conversion must never raise (D-130), so it is percent-encoded like any byte.
    return quote(url, safe=_DESTINATION_SAFE, errors="surrogatepass")


# Inline tokens


class Emphasis:
    """One emphasis pair; it appears twice in a token list, as its opener then its closer.

    Attributes:
        marker: `**`, `*` or `~~`.
        kept: False once the pair is found unable to flank, so it renders as nothing.
    """

    def __init__(self, marker: str) -> None:
        """Create a pair that is kept until the flanking check drops it.

        Args:
            marker: `**`, `*` or `~~`.
        """
        self.marker = marker
        self.kept = True


type Token = str | Emphasis


def around(inner: list[Token], before: list[Token], after: list[Token]) -> list[Token]:
    """Put markup around inline tokens, leaving their edge whitespace outside it (D-114)."""
    tokens = _merged(inner)
    lead = trail = ""
    if tokens and isinstance(tokens[0], str):
        lead = tokens[0][: len(tokens[0]) - len(tokens[0].lstrip(SPACE_CHARS))]
        tokens[0] = tokens[0][len(lead) :]
    if tokens and isinstance(tokens[-1], str):
        trail = tokens[-1][len(tokens[-1].rstrip(SPACE_CHARS)) :]
        tokens[-1] = tokens[-1][: len(tokens[-1]) - len(trail)]
    tokens = [t for t in tokens if t != ""]
    if not tokens:
        return [lead + trail]
    return [lead, *before, *tokens, *after, trail]


def _merged(tokens: list[Token]) -> list[Token]:
    """Join neighbouring text tokens, so edge whitespace sits in the first and last."""
    merged: list[Token] = []
    for token in tokens:
        if isinstance(token, str) and merged and isinstance(merged[-1], str):
            merged[-1] += token
        elif token != "":
            merged.append(token)
    return merged


def link(inner: list[Token], href: str, site_url: str) -> list[Token]:
    """Wrap a link's text in `[...](url)`, or leave it as text (D-114)."""
    if not href:
        return inner
    try:
        url = urljoin(site_url, href)
        scheme = urlsplit(url).scheme
    except ValueError:  # e.g. "http://[", an invalid IPv6 host: keep the text
        return inner
    if scheme not in _LINK_SCHEMES:
        return inner
    return around(inner, ["["], [f"]({_destination(url)})"])


def code(text: str) -> list[Token]:
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


def paragraph(tokens: list[Token]) -> str:
    r"""Render an inline run as a paragraph; `\n` in it marks a hard break."""
    lines = []
    for raw in _resolve(tokens).split("\n"):
        # Space runs come from blocks inside inline elements; they are never meaningful.
        line = re.sub(" {2,}", " ", raw).strip(SPACE_CHARS)
        if line:
            lines.append(escape_line_start(line))
    return "  \n".join(lines)


def _resolve(tokens: list[Token]) -> str:
    """Render tokens to Markdown, dropping emphasis that CommonMark could not read (D-114).

    An opener must be left-flanking and a closer right-flanking. Emphasis that starts or
    ends with punctuation and touches a letter outside fails that, and would show its
    markers literally. Dropping one pair changes its neighbours' context, so the check
    repeats until nothing changes.
    """
    positions: dict[Emphasis, list[int]] = {}
    for index, token in enumerate(tokens):
        if isinstance(token, Emphasis):
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


def _flanks(tokens: list[Token], index: int, run: str, *, left: bool) -> bool:
    """Whether the marker at `index` is left- (or right-) flanking in CommonMark.

    Neighbouring markers of the same character (`run`) join it in one delimiter run.
    """
    before = _neighbour(tokens, range(index - 1, -1, -1), run, last=True)
    after = _neighbour(tokens, range(index + 1, len(tokens)), run, last=False)
    inside, outside = (after, before) if left else (before, after)
    if inside.isspace():
        return False
    return not _is_punctuation(inside) or outside.isspace() or _is_punctuation(outside)


def _neighbour(tokens: list[Token], indices: range, run: str, *, last: bool) -> str:
    """The first visible character in that direction, past the rest of the run.

    A line edge counts as a space.
    """
    for index in indices:
        token = tokens[index]
        text = token if isinstance(token, str) else token.marker if token.kept else ""
        if text and not (isinstance(token, Emphasis) and text[0] == run):
            return text[-1] if last else text[0]
    return " "


def _is_punctuation(char: str) -> bool:
    # CommonMark counts Unicode punctuation and symbols; an escaped character starts
    # with "&" and ends with ";", so it counts the same as the character itself.
    return unicodedata.category(char)[0] in "PS"
