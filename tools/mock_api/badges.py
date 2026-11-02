"""The printable sheet of mock badges: one HTML page of QR codes (D-50, D-391, LEAD-14).

Each seeded attendee gets one card: a QR code of its badge payload ``code:validator``
(the string Ionic's door, swag and lead pages split on ``:``), its name, and the payload
in text for manual entry. The page is self-contained (inline SVG, no scripts or
external files) and prints from a browser on A4 or Letter. ``segno`` is a dev
dependency: nothing here is bundled into the app. Every name and code is fake.
"""

import argparse
from collections.abc import Iterable, Sequence
from html import escape
from pathlib import Path

import segno

from pycon_us.config import YEAR
from tools.mock_api.state import Attendee, MockState

OUT = Path("build") / "mock-badges.html"
"""Where the sheet goes by default, relative to the working directory (git-ignored)."""

STYLE = """
@page { margin: 12mm; }
body { font-family: system-ui, sans-serif; color: #000; background: #fff; margin: 0; }
h1 { font-size: 14pt; margin: 0 0 2mm; }
p.note { font-size: 9pt; margin: 0 0 4mm; }
main { display: grid; grid-template-columns: repeat(2, 88mm); gap: 4mm; }
section { border: 0.3mm dashed #666; padding: 4mm; text-align: center;
  break-inside: avoid; page-break-inside: avoid; }
section svg { width: 50mm; height: 50mm; display: block; margin: 0 auto 2mm; }
h2 { font-size: 13pt; margin: 0; }
p.code { font: 12pt ui-monospace, monospace; margin: 1mm 0 0; }
""".strip()
"""Two columns of 88 mm cards fit A4's 186 mm and Letter's 192 mm between the margins;
50 mm codes scan from arm's length."""


def payload(attendee: Attendee) -> str:
    """Return the string a badge's QR code holds, ``<access code>:<validator>``."""
    return f"{attendee.access_code}:{attendee.validator}"


def qr_svg(text: str) -> str:
    """Return an inline SVG QR code of ``text`` that scales to its box.

    Args:
        text: What the code holds.

    Returns:
        An ``<svg>`` element with a ``viewBox`` and no size, titled with ``text``; the
        four-module quiet zone the standard asks for is part of it.
    """
    code = segno.make(text, error="m", micro=False)
    return code.svg_inline(border=4, omitsize=True, title=text)


def sheet(year: int, attendees: Iterable[Attendee]) -> str:
    """Return the badge sheet as one HTML page.

    Args:
        year: The conference year the mock serves.
        attendees: The attendees to print, one card each, in order.

    Returns:
        The page's HTML.
    """
    cards = "\n".join(
        f"<section>{qr_svg(payload(attendee))}"
        f"<h2>{escape(attendee.full_name)}</h2>"
        f'<p class="code">{escape(payload(attendee))}</p></section>'
        for attendee in attendees
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Mock badges {year}</title>
<style>
{STYLE}
</style>
</head>
<body>
<h1>Mock PyCon US {year} badges</h1>
<p class="note">Fake attendees of <code>tools/mock_api</code>: these badges work only
against the mock. Scan a code, or type the text under it.</p>
<main>
{cards}
</main>
</body>
</html>
"""


def main(argv: Sequence[str] | None = None) -> None:
    """Write the seeded attendees' badge sheet and say where it is.

    Args:
        argv: The command-line arguments; None reads ``sys.argv``.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tools.mock_api.badges",
        description="Write a printable HTML sheet of the mock's badge QR codes.",
    )
    parser.add_argument("--out", type=Path, default=OUT, help=f"default {OUT}")
    args = parser.parse_args(argv)
    state = MockState.from_seed()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(sheet(YEAR, state.attendees.values()), encoding="utf-8")
    print(f"Wrote {args.out}; open it in a browser and print it (A4 or Letter).")


if __name__ == "__main__":
    main()
