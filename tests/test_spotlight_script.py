"""Tests for `maestro/scripts/spotlight_name.js`, which reads the spotlight's sponsor (#455).

Maestro runs it with `runScript` after `copyTextFrom` on Now's spotlight card; here
Node runs it the same way, in a fresh context with a test's `maestro.copiedText` and
`output`. The phrases are `core.sponsors.thanks()`'s own, so the script and the card
cannot drift apart unnoticed. Skipped where Node is missing.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pycon_us.core.models import Sponsor
from pycon_us.core.sponsors import thanks

SCRIPT = (
    Path(__file__).resolve().parent.parent / "maestro" / "scripts" / "spotlight_name.js"
)
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node runs the flow's script")

HARNESS = """
const fs = require("fs");
const vm = require("vm");
const [file, copied] = process.argv.slice(1);
const context = { output: {}, maestro: { copiedText: copied }, console: { log: () => {} } };
vm.runInNewContext(fs.readFileSync(file, "utf8"), context);
process.stdout.write(JSON.stringify(context.output));
"""


def spotlight_name(copied: str) -> str:
    """Run the script on `copied` as the card's text and return the name it kept."""
    assert NODE is not None
    result = subprocess.run(
        [NODE, "-e", HARNESS, str(SCRIPT), copied],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["spotlightName"]


def sponsor(name: str, level: str) -> Sponsor:
    """Return a sponsor with `name` and `level`, its other fields as the feed's."""
    return Sponsor(
        name=name,
        slug=name.lower().replace(" ", "-"),
        level=level,
        level_order=1,
        logo_url="",
        description="",
        booth=None,
        job_fair_table=None,
        mobile_banner=True,
    )


@pytest.mark.parametrize(
    ("name", "level"),
    [
        ("NVIDIA", "Visionary"),
        ("Anaconda, Inc", "Maintaining"),  # a comma before the article's own
        ("SerpApi", "Associate"),  # "an"
        ("Qube Research & Technologies", "Partner"),
    ],
)
def test_the_name_is_read_from_the_card_s_own_phrase(name: str, level: str) -> None:
    """The script keeps the name of `thanks()`'s phrase, whatever the article."""
    assert spotlight_name(thanks(sponsor(name, level))) == name


def test_special_characters_are_escaped_so_the_name_matches_itself_whole() -> None:
    """Maestro's `text:` is a regular expression: a "." or "(" is escaped."""
    copied = thanks(sponsor("Example (Labs) Inc.", "Partner"))
    assert spotlight_name(copied) == r"Example \(Labs\) Inc\."


def test_another_text_gives_no_name() -> None:
    """A card that says something else leaves the name empty, and the flow fails."""
    assert spotlight_name("Something else") == ""
