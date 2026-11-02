"""What each build ships under whose licence: the Licences page's list and texts (D-296).

Every build carries the app's own code, Python, Flet, Flutter and the Python packages
they pull in, the Roboto font, Material icons and the brand marks; their licences ask
that the build carry their notices. ``COMPONENTS`` lists them by group, in the page's
order, the app and its ``NOTICE`` first. Each names the text file in
``licence_texts/`` that it opens: the component's own licence file, as its package
ships it, or ``apache-2.0.txt`` for one whose licence is Apache 2.0 with no file of its
own. The texts sit next to the code, so ``flet build`` bundles them and they open
offline, as the year data does (F15).

Flutter's per-package list (``NOTICES.Z``) waits on Flet (U51): until then this lists
the direct components. A test keeps every runtime package of ``uv.lock`` here (D-75).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from pycon_us import APP_NAME

TEXTS_DIR = Path(__file__).parent / "licence_texts"
"""Where the licence texts live; ``flet build`` bundles them with the package (F15)."""


@dataclass(frozen=True)
class Component:
    """One thing a build ships, its licence and who holds its copyright."""

    key: str
    """Its segment in ``/more/app/licences/<key>`` and its identifier's last part."""
    name: str
    """What the page calls it."""
    licence: str
    """Its licence's SPDX identifier, which the row shows: ``Apache-2.0``, ``MIT``."""
    copyright: str
    """Its copyright line, as its licence file or project states it."""
    text: str
    """The file in ``licence_texts/`` that holds its full text."""
    package: str | None = None
    """Its name in ``uv.lock`` when it is a Python package, for the coverage test."""


@dataclass(frozen=True)
class Group:
    """A section of the page: its heading and its components, in order."""

    title: str
    components: tuple[Component, ...]


APACHE = "apache-2.0.txt"
"""The Apache License 2.0's text, for the components under it with no file of their own."""

APP = Component(
    "app",
    APP_NAME,
    "Apache-2.0",
    "Copyright 2026 The pycon-us-flet contributors",
    APACHE,
)
"""The app itself, under the same licence as the Ionic app (D-87)."""

NOTICE = Component(
    "notice",
    "Notices",
    "Credits and trademarks",
    "What the app reuses, and whose marks it names",
    "notice.txt",
)
"""The repository's ``NOTICE``, which Apache 2.0 asks a build to carry (D-87)."""


def _package(
    key: str, name: str, licence: str, copyright: str, *, text: str | None = None
) -> Component:
    """Return a Python package's entry: its ``uv.lock`` name is ``key``."""
    return Component(key, name, licence, copyright, text or f"{key}.txt", package=key)


GROUPS = (
    Group("This app", (APP, NOTICE)),
    Group(
        "Runtime",
        (
            Component(
                "python",
                "Python",
                "PSF-2.0",
                "Copyright 2001 Python Software Foundation",
                "python.txt",
            ),
            Component(
                "flet",
                "Flet",
                "Apache-2.0",
                "Copyright Appveyor Systems Inc.",
                APACHE,
                package="flet",
            ),
            Component(  # E3 reminders (D-220, #446)
                "flet-notifications",
                "Flet Notifications",
                "Apache-2.0",
                "Copyright Appveyor Systems Inc.",
                APACHE,
                package="flet-notifications",
            ),
            Component(  # permission status and settings (D-61, #446)
                "flet-permission-handler",
                "Flet Permission Handler",
                "Apache-2.0",
                "Copyright Appveyor Systems Inc.",
                APACHE,
                package="flet-permission-handler",
            ),
            Component(  # the mock API key and secret (D-49, #684)
                "flet-secure-storage",
                "Flet Secure Storage",
                "Apache-2.0",
                "Copyright Appveyor Systems Inc.",
                APACHE,
                package="flet-secure-storage",
            ),
            Component(
                "flutter",
                "Flutter",
                "BSD-3-Clause",
                "Copyright 2014 The Flutter Authors",
                "flutter.txt",
            ),
            Component(
                "serious-python",
                "serious_python",
                "Apache-2.0",
                "Copyright Appveyor Systems Inc.",
                APACHE,
            ),
        ),
    ),
    Group(
        "Python packages",
        (
            _package("anyio", "AnyIO", "MIT", "Copyright 2018 Alex Grönholm"),
            _package(
                "certifi",
                "certifi",
                "MPL-2.0",
                "Packaged by Kenneth Reitz, from Mozilla's CA certificates",
            ),
            _package(
                "h11",
                "h11",
                "MIT",
                "Copyright 2016 Nathaniel J. Smith and contributors",
            ),
            _package(
                "httpcore", "HTTP Core", "BSD-3-Clause", "Copyright 2020 Encode OSS Ltd"
            ),
            _package("httpx", "HTTPX", "BSD-3-Clause", "Copyright 2019 Encode OSS Ltd"),
            _package(
                "idna",
                "idna",
                "BSD-3-Clause",
                "Copyright 2013-2026 Kim Davies and contributors",
            ),
            _package(
                "msgpack",
                "MessagePack",
                "Apache-2.0",
                "Copyright 2008-2011 INADA Naoki",
            ),
            _package(
                "oauthlib",
                "OAuthLib",
                "BSD-3-Clause",
                "Copyright The OAuthlib Community",
            ),
            _package("repath", "repath", "MIT", "Copyright 2015 Synacor, Inc."),
            _package("six", "six", "MIT", "Copyright 2010-2024 Benjamin Peterson"),
            _package(
                "typing-extensions",
                "typing_extensions",
                "PSF-2.0",
                "Copyright 2001 Python Software Foundation",
            ),
            _package(
                "tzdata",
                "tzdata",
                "Apache-2.0",
                "Copyright 2020 Paul Ganssle, 2026 Stan Ulbrych",
            ),
        ),
    ),
    Group(
        "Fonts and icons",
        (
            Component(
                "roboto", "Roboto", "Apache-2.0", "Copyright 2011 Google Inc.", APACHE
            ),
            Component(
                "material-icons",
                "Material icons",
                "Apache-2.0",
                "Copyright Google LLC",
                APACHE,
            ),
            Component(
                "simple-icons",
                "Simple Icons",
                "CC0-1.0",
                "The set is CC0, which doesn't mean every icon in it is; "
                "each mark is its owner's trademark",
                "simple-icons.txt",
            ),
        ),
    ),
)
"""The page's sections, in its order: the app and its notices first (#442)."""

COMPONENTS = {c.key: c for group in GROUPS for c in group.components}
"""Every component by key, in the page's order."""


def read_text(component: Component) -> str:
    """Return a component's full licence text, from the files bundled with the app.

    Raises:
        OSError: The file is missing, which a test rules out for every component.
    """
    return (TEXTS_DIR / component.text).read_text(encoding="utf-8")


_OWN_LINE = re.compile(r"\s*(?:[-*•] |#|\d{1,2}\. |\(\w{1,3}\) |[a-z]\) |Copyright )")
"""A line that starts a line of its own: a list item (``* Redistributions``, ``1.``,
``(a)``), a Markdown heading or a copyright line."""

_COLUMNS = re.compile(r"\S {3,}\S")
"""Three spaces or more between words: columns, as in Python's table of releases."""

_RULE = re.compile(r"\s*[=\-*_]{3,}\s*")
"""A line of ``=``, ``-``, ``*`` or ``_`` alone: a heading's underline or a rule."""


@dataclass(frozen=True)
class Paragraph:
    """A block of a licence text, as the screen shows it."""

    text: str
    fixed: bool = False
    """Laid out in columns or under a rule: shown line for line, in a monospace font."""


def paragraphs(text: str) -> list[Paragraph]:
    """Return a licence text as paragraphs that the screen can wrap at any text size.

    Licence files are wrapped by hand near 80 columns, so at 200 % text each of their
    lines breaks again mid-phrase. A paragraph (lines between blank lines) becomes one
    line, its indentation and double spaces dropped, so the text reflows to the screen;
    a line that starts a list item or a copyright line starts a line of its own. A block
    laid out in columns or with a rule under a heading keeps its lines as they are,
    since joining them would garble it.

    Args:
        text: The licence file's text.
    """
    found = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if any(
            _COLUMNS.search(line.strip()) or _RULE.fullmatch(line) for line in lines
        ):
            found.append(Paragraph("\n".join(line.rstrip() for line in lines), True))
            continue
        joined: list[str] = []
        for line in lines:
            line = " ".join(line.split())
            if joined and not _OWN_LINE.match(line):
                joined[-1] = f"{joined[-1]} {line}"
            else:
                joined.append(line)
        found.append(Paragraph("\n".join(joined)))
    return found
