"""Tests for the README's screenshots: what the tool stores, and that the README's images exist."""

import json
import re
from pathlib import Path

from pycon_us.dev_options import DEV_FAKE_NOW, DEV_UNLOCKED
from pycon_us.services.pref_keys import DEV, ONBOARDED, REMINDERS
from tools import readme_shots

ROOT = Path(readme_shots.__file__).resolve().parents[1]
IMAGES = ROOT / "docs" / "images"
MAX_BYTES = 1024 * 1024
"""The images' budget in the tree, in bytes (D-162's 1 MB, for the README's whole set)."""


def test_the_stored_prefs_set_the_clock_and_never_unlock_developer() -> None:
    """More shows no Developer row: the clock is stored with no `unlocked` key."""
    stored = readme_shots.app_prefs()
    assert set(stored) == {f"flutter.{p.key}" for p in (ONBOARDED, REMINDERS, DEV)}
    dev = json.loads(stored[f"flutter.{DEV.key}"])
    assert dev == {DEV_FAKE_NOW: readme_shots.CLOCK_START.isoformat()}
    assert DEV_UNLOCKED not in dev


def test_the_status_bar_follows_the_fake_clock() -> None:
    """The status bar's minute is the fake clock's, which starts at 11:04."""
    assert readme_shots.status_minute(-5) == (11, 4)
    assert readme_shots.status_minute(65) == (11, 5)


def test_a_shot_is_named_for_its_platform_appearance_and_screen() -> None:
    """The flow's `3-session.png` becomes `android-dark-3-session.webp`."""
    name = readme_shots.shot_name("android", "dark", "3-session.png")
    assert name == "android-dark-3-session.webp"


def test_the_flow_takes_the_six_shots_the_tool_expects() -> None:
    """The tool refuses a run with other than six screenshots, so the flow takes six."""
    flow = readme_shots.FLOW.read_text(encoding="utf-8")
    assert len(re.findall(r"^- takeScreenshot: ", flow, re.MULTILINE)) == 6


def test_every_image_the_readme_shows_exists_and_the_folder_stays_small() -> None:
    """A renamed or missing image fails here, not as a broken picture on the front page."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    shown = set(re.findall(r'src="(docs/images/[^"]+)"', readme))
    assert len(shown) == 24  # six screens, two platforms, two appearances
    assert [p for p in shown if not (ROOT / p).is_file()] == []
    assert sum(p.stat().st_size for p in IMAGES.glob("*.webp")) < MAX_BYTES
    assert {p.name for p in IMAGES.glob("*.webp")} == {Path(p).name for p in shown}


def test_every_image_has_alt_text() -> None:
    """A screen reader says what each image shows: no `<img>` of the README lacks `alt`."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    images = re.findall(r"<img [^>]*>", readme)
    assert images
    assert [tag for tag in images if not re.search(r'alt="[^"]{10,}"', tag)] == []
