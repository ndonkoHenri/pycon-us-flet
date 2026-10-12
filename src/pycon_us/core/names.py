"""Ionic's title cleaning: names, their room suffix and their flags (DATA-08..10).

The feed's slot names carry more than a title: a Markdown link, a ``(Room)`` suffix, a
"Keynote — " prefix, ", pre-registration required" and ", En Español". ``clean_title``
takes them apart with the one regex table below, in Ionic's order.
"""

import html
import re
from dataclasses import dataclass

# The regex table, as Ionic wrote it (conference-data.ts, processData).
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")  # [text](url) → text
_TAG = re.compile(r"</?[A-Za-z][^<>]*>")  # <s>text</s> → text; "<3" stays (D-114)
_TRAILING_ROOM = re.compile(r"\s*\(([^)]+)\)\s*$")  # "Closing (Arena)" → room "Arena"
_TYPING = re.compile(r"typing", re.IGNORECASE)  # the one summit open to all
_SPANISH = re.compile(r"en espa[ñn]ol", re.IGNORECASE)
_SPANISH_SUFFIX = re.compile(r",?\s*en espa[ñn]ol", re.IGNORECASE)
_TRACK_PREFIX_TAIL = r"\s*[—:\-–]\s*"  # after the kind: "Keynote — ", "Keynote: "

PRE_REGISTRATION = ", pre-registration"
"""The phrase that flags a session needing registration, and where its name is cut."""

PLENARY_KINDS = ("plenary", "keynote", "lightning-talks", "event")
"""Kinds whose name may end with their room, and start with their kind (DATA-08)."""


@dataclass(frozen=True)
class Title:
    """A slot name taken apart (DATA-08..10).

    Attributes:
        name: The title to show.
        room: The ``(Room)`` that ended a plenary-like name; empty when there was none.
        pre_registered: Whether attending needs registration (DATA-09).
        spanish: Whether it is given in Spanish (DATA-10).
    """

    name: str
    room: str
    pre_registered: bool
    spanish: bool


def plain_text(name: str) -> str:
    """Return a slot name as text: a Markdown link becomes its text, tags go, entities decode.

    Ionic ran ``markdownToTxt`` on names; the feeds only use links there, plus one
    ``<s>…</s>`` in 2025 (D-114: names strip tags and keep their text).
    """
    text = _TAG.sub("", _MARKDOWN_LINK.sub(r"\1", name))
    return html.unescape(text).strip()


def trailing_room(name: str) -> tuple[str, str]:
    """Split a ``(Room)`` suffix off a name: ``("Lunch", "Hall AB")``, or ``(name, "")``."""
    if match := _TRAILING_ROOM.search(name):
        return name[: match.start()].strip(), match[1]
    return name, ""


def clean_title(name: str, kind: str) -> Title:
    """Take a slot's name apart, in Ionic's order.

    1. Markdown and tags become text (``plain_text``).
    2. Pre-registration: the name holds ``pre-registration`` (and is cut at
       ", pre-registration"), or the slot is a tutorial or a summit other than Typing.
    3. A plenary, keynote, lightning-talks or event name loses its ``(Room)`` suffix and
       its kind as a prefix ("Keynote — Lin Qiao" → "Lin Qiao").
    4. Spanish: a ``charla``, or "en español" (with or without the tilde, any case) in the
       name, which is cut from it.

    Args:
        name: The name as the feed gives it.
        kind: The slot's kind as the feed gives it.

    Returns:
        The title, the room its name named and its flags.
    """
    text = plain_text(name)
    pre_registered = (
        "pre-registration" in text
        or kind == "tutorial"
        or (kind == "summit" and not _TYPING.search(text))
    )
    if pre_registered:
        text = text.split(PRE_REGISTRATION)[0]
    room = ""
    if kind in PLENARY_KINDS:
        text, room = trailing_room(text)
        prefix = "[- ]".join(re.escape(part) for part in kind.split("-"))
        text = re.sub(
            f"^{prefix}{_TRACK_PREFIX_TAIL}", "", text, flags=re.IGNORECASE
        ).strip()
    spanish = kind == "charla" or bool(_SPANISH.search(text))
    text = _SPANISH_SUFFIX.sub("", text, count=1).strip()
    return Title(text, room, pre_registered, spanish)
