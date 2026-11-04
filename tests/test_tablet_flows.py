"""Tests for the words the tablet flows match, against the app's own (#461).

The Maestro flows find the rail's destinations by name (`subflows/tab.yaml`: the
rail has no identifiers, D-277) and read About this app's lines by their text. Those
words are written into the YAML, so a renamed tab, a reordered bar or reworded copy
would fail only on a device. These checks fail here instead.
"""

import re
from pathlib import Path

from pycon_us.ui.navigation import TABS
from pycon_us.ui.share import REPORT_NOT_SHARED
from pycon_us.ui.status_strip import SOURCES

ROOT = Path(__file__).resolve().parent.parent
MAESTRO = ROOT / "maestro"
ABOUT_APP = MAESTRO / "journeys" / "about_app.yaml"

TAB_CALL = re.compile(r"^\s+TAB: (\w+)\n\s+NAME: \"([^\"]+)\"$", re.MULTILINE)
"""A `tab.yaml` call's env: the tab's key, then its destination's name."""


def tab_calls() -> list[tuple[Path, str, str]]:
    """Return every flow's `tab.yaml` calls as (file, key, name), in file order."""
    return [
        (path, key, name)
        for path in sorted(MAESTRO.rglob("*.yaml"))
        for key, name in TAB_CALL.findall(path.read_text(encoding="utf-8"))
    ]


def rail_name(key: str) -> str:
    """Return the name a flow gives a destination: its label, then "Tab n of 5"."""
    keys = [tab.key for tab in TABS]
    index = keys.index(key)
    return f"{TABS[index].label}.*Tab {index + 1} of {len(TABS)}"


def test_the_flows_call_tab_yaml_with_names() -> None:
    """The scan finds the calls, so the name check below is not vacuous."""
    keys = {key for _, key, _ in tab_calls()}
    assert keys == {tab.key for tab in TABS}


def test_each_destination_s_name_is_its_label_and_place_in_the_bar() -> None:
    """D-277: a rail destination's name follows `TABS`' labels and order.

    A flow finds it by "<label>.*Tab <n> of 5", as TalkBack and VoiceOver read it.
    """
    for path, key, name in tab_calls():
        assert name == rail_name(key), f"{path.relative_to(ROOT)}: {key}"


def test_about_app_expects_the_report_s_failure_line_word_for_word() -> None:
    """INFO-04, U95: on an iPad the flow reads the line a failed share says."""
    text = ABOUT_APP.read_text(encoding="utf-8")
    # The YAML string escapes the regular expression's "\." as "\\.".
    line = REPORT_NOT_SHARED[0].replace(".", "\\\\.")
    assert f'id: about_app.report_outcome\n          text: "{line}"' in text


def test_about_app_expects_the_schedule_line_s_two_sources() -> None:
    """D-292: the Schedule row's two sources, in `schedule_line()`'s words.

    Offline on Android the bundled data; on iOS, whose launch may reach it, the feed.
    """
    text = ABOUT_APP.read_text(encoding="utf-8")
    sources = f"({SOURCES['bundled']}|{SOURCES['network']})"
    assert f"Schedule\\\\s+{sources}, updated .+" in text


FAILS = "${SHARE_FAILS == 'true'}"
"""The `when: true:` of the branch for a run where the sheet cannot open (U95)."""
OPENS = "${SHARE_FAILS != 'true'}"
"""The `when: true:` of the branch for a run where the sheet opens."""


def share_branch(condition: str) -> str:
    """Return the text of `about_app`'s top-level step whose condition is `condition`.

    Args:
        condition: The branch's `when: true:` expression, `FAILS` or `OPENS`.
    """
    steps = re.split(r"^- ", ABOUT_APP.read_text(encoding="utf-8"), flags=re.MULTILINE)
    found = [step for step in steps if f"      true: {condition}\n" in step]
    assert len(found) == 1, condition
    return found[0]


def test_about_app_accepts_the_failure_line_only_when_the_run_expects_it() -> None:
    """U95: only a `SHARE_FAILS=true` run (an iPad) passes with "Couldn't open…".

    Elsewhere a share error must fail the flow rather than pass as the iPad's outcome.
    """
    assert "assertVisible:\n          id: about_app.report_outcome" in share_branch(
        FAILS
    )
    assert "Couldn't open" not in share_branch(OPENS)


def test_about_app_waits_for_each_platform_s_sheet_before_dismissing_it() -> None:
    """#461: the system's sheet itself comes up, on Android and iOS, before the dismissal.

    A tap that opens nothing, or a failure, then fails instead of passing.
    """
    before, _, _ = share_branch(OPENS).partition("../subflows/dismiss_share.yaml")
    for platform, sheet in (("Android", '".*resolver_list"'), ("iOS", "ShareSheet")):
        wait = (
            rf"platform: {platform}\n.*?extendedWaitUntil:\n\s+visible:\n\s+id: {sheet}"
        )
        assert re.search(wait, before, flags=re.DOTALL), platform


def test_about_app_checks_a_dismissed_sheet_leaves_no_outcome_line() -> None:
    """D-297: a dismissal says nothing; no line, not even a "shared" one, comes under the row."""
    _, _, after = share_branch(OPENS).partition("../subflows/dismiss_share.yaml")
    assert "assertNotVisible:\n          id: about_app.report_outcome\n" in after
