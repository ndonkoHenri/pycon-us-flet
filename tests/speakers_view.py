"""The Speakers list's built cases and harness, for its three test modules (#312).

``test_speakers.py`` (the query), ``test_speakers_screen.py`` (the list and its filter
field) and ``test_speakers_rows.py`` (the rows, the headings and the states) share the
small built cases and the harness here. The screen runs in a real Flet session under the
store providers (``tests/harness.py``'s ``showing()``, which names the Flet internals
it uses): a keystroke is the field's value patched in and its change event dispatched,
as Flutter sends them, and Flet's scheduler re-renders what changed, so a test sees
which row and section bodies ran (D-153). A module takes the fixtures by assigning them
to its own names, as ``docs/testing-and-quality.md`` §3.1 says.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.models import Speaker
from pycon_us.core.speakers import SpeakerEntry, directory
from pycon_us.screens import speakers as screen
from pycon_us.state import Conference
from pycon_us.ui import rows
from pycon_us.ui.rows import speaker_phrase
from tests import harness
from tests.feeds import processed

YEAR = load_year(2026)
ROW = "speakers.speaker."
"""The prefix of a speaker row's semantics identifier."""


def with_speakers(names: list[str], *, sessions: dict[str, list[str]] | None = None):
    """The 2026 feed with only these speakers, whose ids are "0", "1", and so on.

    If ``sessions`` is given, only these sessions too: copies of one 2026 session,
    linked to the speakers named by id.
    """
    base = processed(2026)
    template = next(iter(base.sessions.values()))
    speakers = {str(n): Speaker(str(n), name, "", "") for n, name in enumerate(names)}
    built = {}
    for session_id, speaker_ids in (sessions or {}).items():
        built[session_id] = replace(template, id=session_id, speaker_ids=speaker_ids)
    return replace(base, speakers=speakers, sessions=built or base.sessions)


def names(entries: tuple[SpeakerEntry, ...]) -> list[str]:
    """The speakers' names, in the entries' order."""
    return [entry.speaker.name for entry in entries]


@dataclass
class Shown(harness.Shown):
    """The harness's ``Shown`` (``tests/harness.py``) on the Speakers screen.

    Its rows are speakers: ``rows`` holds the speaker ids whose row bodies ran.
    """

    sections: list[str] = field(default_factory=list)
    """The letters whose section bodies ran, in order."""

    @property
    def text_field(self) -> ft.TextField:
        """The screen's one filter field."""
        (text_field,) = self.find(ft.TextField)
        return text_field

    @property
    def listed(self) -> list[str]:
        """The speaker ids of the rows on screen, in the list's order."""
        (body,) = self.find(ft.ListView)  # the screen's one list
        found: list[str] = []

        def walk(control: object) -> None:
            identifier = getattr(control, "identifier", None)
            if isinstance(control, ft.Semantics) and str(identifier).startswith(ROW):
                found.append(str(identifier).removeprefix(ROW))
            # A component's rendered body is its _b (Flet internals, as above).
            for name in ("content", "_b"):
                child = getattr(control, name, None)
                for item in child if isinstance(child, list) else [child]:
                    if isinstance(item, ft.BaseControl):
                        walk(item)
            for child in getattr(control, "controls", None) or ():
                walk(child)

        walk(body)
        return found

    async def type(self, text: str) -> None:
        """Type into the filter as Flutter reports it: the value, then the event."""
        text_field = self.text_field
        self.session.apply_patch(text_field._i, {"value": text})
        await self.event(text_field, "change", None)


type Render = Callable[[Conference], Awaitable[Shown]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Return a function that shows the Speakers screen over a given ``Conference``.

    Each screen it shows closes when the test ends.
    """
    header = screen.SectionHeader

    def counted_phrase(entry: SpeakerEntry) -> str:
        harness.current(Shown).rows.append(entry.speaker.id)
        return speaker_phrase(entry)

    def counted_header(text: str) -> ft.Control:
        harness.current(Shown).sections.append(text)
        return header(text)

    # Each body calls these once: counting the calls counts the bodies (S2).
    monkeypatch.setattr(rows, "speaker_phrase", counted_phrase)
    monkeypatch.setattr(screen, "SectionHeader", counted_header)

    async with AsyncExitStack() as stack:

        async def show(conference: Conference) -> Shown:
            return await stack.enter_async_context(
                harness.showing(
                    screen.Speakers,
                    screen,
                    year=YEAR,
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="",  # no Router: what ft.use_view_path() says outside one
                    kind=Shown,
                )
            )

        yield show


@pytest.fixture
async def shown(render: Render) -> Shown:
    """The Speakers screen over the recorded 2026 feed."""
    return await render(Conference(data=processed(2026), source="bundled", version=1))


ALL = directory(processed(2026))


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[ft.TextField]:
    """The fields asked to take the focus; the harness has no Flutter to answer."""
    asked: list[ft.TextField] = []

    async def focus(self: ft.TextField) -> None:
        # As the real one, which invokes the method through the field's page.
        assert self.page is not None, "the field is not on the page"
        asked.append(self)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return asked


def _under(control: ft.BaseControl, ancestor: ft.BaseControl) -> bool:
    """Whether ``ancestor`` is ``control`` or one of its parents."""
    node: ft.BaseControl | None = control
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent
    return False
