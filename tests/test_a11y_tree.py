"""Tests for `tools/a11y_tree.py`, which prints Android's accessibility tree with headings (#257).

No device: the More screen's dump in `fixtures/a11y_tree/more.xml` was recorded with the
tool on an Android emulator, and `am instrument`'s output is written out here.
"""

from pathlib import Path

import pytest

from tools.a11y_tree import DumpError, deep_link, parse, render, result_xml

MORE = (Path(__file__).parent / "fixtures" / "a11y_tree" / "more.xml").read_text()
"""The tool's XML for the More screen, recorded on an emulator."""

SMALL = (
    "<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">"
    '<node class="android.widget.FrameLayout" text="" content-desc="" resource-id="">'
    '<node class="android.view.View" heading="true" resource-id="more.title" content-desc="More"'
    ' text="" focusable="true" enabled="true"/>'
    '<node class="android.widget.Button" heading="false" resource-id="" content-desc="Two&#10;lines"'
    ' text="Two" enabled="false" clickable="true" state-description="On" hint="Opens"'
    ' visible-to-user="false" bounds="[0,0][10,10]"/>'
    "</node></hierarchy>"
)
"""A hand-written dump: a root, a heading, and a disabled button with every extra."""


def test_the_recorded_more_screen_lists_its_headings():
    """The More screen's headings are its title and the sections on screen, in order (D-211).

    The sections below the fold are not in the tree: Flutter leaves out what is off screen.
    """
    headings = [n.label for n in parse(MORE) if n.heading]
    assert headings == ["More", "Programme", "Expo & sponsors", "At the venue"]


def test_the_recorded_headings_carry_their_identifier():
    """`--headings` prints `HEADING` and the identifier, so a check names the node it means."""
    lines = render(parse(MORE), headings=True).splitlines()
    assert len(lines) == 4
    assert all(" HEADING " in line for line in lines)
    assert any("#more.title" in line for line in lines)


def test_a_label_with_a_newline_is_read_back():
    """A tab's two-line label survives the one-line XML (`&#10;`) and prints on one line."""
    tab = next(n for n in parse(MORE) if n.ident == "app.nav.more")
    assert tab.label == "More\nTab 5 of 5"
    assert '"More\\nTab 5 of 5"' in render([tab])
    assert "selected" in tab.flags


def test_a_node_reads_as_one_line_with_its_states():
    """Class, `HEADING`, `#identifier`, the label and the states are one line per node."""
    root, title, button = parse(SMALL)
    assert (root.depth, title.depth) == (0, 1)
    assert render([title]) == '  View HEADING #more.title "More" [focusable]'
    assert render([button], bounds=True) == (
        '  Button "Two\\nlines" text="Two" state="On" hint="Opens"'
        " [clickable, disabled, offscreen] [0,0][10,10]"
    )


def test_the_tree_is_indented_by_depth():
    """Each level indents its nodes two spaces, so the nesting shows."""
    assert [line[:4] for line in render(parse(SMALL)).splitlines()] == [
        "Fram",
        "  Vi",
        "  Bu",
    ]


def test_the_xml_is_read_from_the_result_bundle():
    """`am instrument -w -r` prints the bundle's `xml` key on one line; that line is the dump."""
    output = f"INSTRUMENTATION_RESULT: xml={SMALL}\nINSTRUMENTATION_CODE: -1\n"
    assert result_xml(output) == SMALL


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (
            "INSTRUMENTATION_RESULT: error=IllegalStateException: no active window\n",
            "no active window",
        ),
        (
            "INSTRUMENTATION_FAILED: io.github.ndonkohenri.a11ytree/.A11yTree\n",
            "INSTRUMENTATION_FAILED",
        ),
        ("", "printed nothing"),
    ],
)
def test_a_run_without_a_tree_says_why(output, message):
    """A failed run raises with the instrumentation's error, or am's own output, never an empty tree."""
    with pytest.raises(DumpError, match=message):
        result_xml(output)


def test_a_route_opens_through_the_app_deep_link():
    """`--route` becomes the D-269 link `<scheme>://<host>/<route path>`, with or without a leading slash.

    The scheme can still be renamed (D-452), so the test reads the scheme and host from the link.
    """
    scheme, rest = deep_link("/more").split("://")
    host, path = rest.split("/", 1)
    assert (bool(scheme), bool(host), path) == (True, True, "more")
    assert deep_link("schedule") == f"{scheme}://{host}/schedule"
