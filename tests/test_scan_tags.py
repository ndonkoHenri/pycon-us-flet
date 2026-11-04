"""Tests for a scan result's tags: their words, their chips and their contrast (#767).

`ScanResult.tags` is data (`core/badges.py`); `ui/scan_result.py` draws them as
chips under the name, a warning (an allergy) first and larger, and every chip takes the
card's own colours, so it reads on every fill: the table's, the dimmed neutral one, in
light, dark and high contrast (DOOR-05; ux.md §7.2, §9; D-65, D-306).
"""

import flet as ft
import pytest

from pycon_us.core.badges import ScanOutcome, ScanResult, Tag
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui.scan_result import fill_of, result_panel, tag_colors, tag_row
from tests.test_high_contrast import AAA_TEXT, hc_scheme
from tests.theme_helpers import AA_TEXT, NEUTRAL_RAMP, contrast_ratio, hex_role

ALLERGY = Tag("Allergy: peanuts", warning=True)
VEGETARIAN = Tag("Vegetarian")


def chips(row: ft.Control) -> list[ft.Container]:
    """The chips of `tag_row()`'s row, in order."""
    assert isinstance(row, ft.Container) and isinstance(row.content, ft.Row)
    assert row.content.wrap  # a row that wraps at large text
    found = row.content.controls
    assert all(isinstance(chip, ft.Container) for chip in found)
    return [chip for chip in found if isinstance(chip, ft.Container)]


def parts(chip: ft.Container) -> tuple[ft.Icon, ft.Text]:
    """A chip's icon and its words."""
    assert isinstance(chip.content, ft.Row)
    icon, text = chip.content.controls
    assert isinstance(icon, ft.Icon) and isinstance(text, ft.Text)
    return icon, text


def hex_of(color: ft.ColorValue, *, dark: bool, high_contrast: bool) -> str:
    """A colour as #RRGGBB: a fixed one as is, a scheme role as the theme draws it.

    High contrast sets every role by hand; otherwise the surface roles are Flet's
    neutral ramp (`NEUTRAL_RAMP`), which the scheme leaves unset.
    """
    if not isinstance(color, ft.Colors):
        assert isinstance(color, str) and color.startswith("#")
        return color
    if high_contrast:
        return hex_role(hc_scheme(dark), color.name.lower())
    first, *rest = color.name.lower().split("_")
    return NEUTRAL_RAMP[dark][first + "".join(word.title() for word in rest)]


def test_the_tags_are_said_after_the_name_before_the_details() -> None:
    """One line of tags, each ending with a full stop, between the name and details."""
    result = ScanResult(
        ScanOutcome.ACCEPTED, "Checked in", "Grace", ("Admits 2",), "C", (ALLERGY,)
    )
    assert result.spoken == "Checked in\nGrace\nAllergy: peanuts.\nAdmits 2"
    both = ScanResult(
        ScanOutcome.DUPLICATE, "Already", "Linus", tags=(ALLERGY, VEGETARIAN)
    )
    assert both.spoken == "Already\nLinus\nAllergy: peanuts. Vegetarian."


def test_a_warning_comes_first_larger_and_with_its_icon() -> None:
    """Given after a plain tag, the allergy still leads, with `WARNING_AMBER`."""
    first, second = chips(
        tag_row((VEGETARIAN, ALLERGY), label="#FFFFFF", fill="#146C2E")
    )
    warning_icon, warning_text = parts(first)
    plain_icon, plain_text = parts(second)
    assert (warning_icon.icon, warning_text.value) == (
        ft.Icons.WARNING_AMBER,
        ALLERGY.text,
    )
    assert (plain_icon.icon, plain_text.value) == (
        ft.Icons.RESTAURANT_OUTLINED,
        VEGETARIAN.text,
    )
    assert (warning_icon.size or 0) > (plain_icon.size or 0)
    assert warning_text.theme_style is ft.TextThemeStyle.LABEL_LARGE
    assert plain_text.theme_style is ft.TextThemeStyle.LABEL_MEDIUM


def test_every_chip_has_an_edge_and_wrapping_words() -> None:
    """A 1 dp edge in the label's colour (D-306); the words take the room they need."""
    for chip in chips(tag_row((ALLERGY, VEGETARIAN), label="#1A1A1A", fill="#F2C14E")):
        assert isinstance(chip.border, ft.Border)
        assert (chip.border.top.width, chip.border.top.color) == (1, "#1A1A1A")
        _, text = parts(chip)
        assert text.expand and text.expand_loose


def test_the_panel_draws_the_tags_under_the_name_and_no_tags_draws_none() -> None:
    """The chips sit right after the name; without tags, the card is as before.

    The Lead scanner's results have no tags, so they look exactly as they did.
    """

    def column(result: ScanResult) -> list[ft.Control]:
        """The card's lines: word, name, tags, details."""
        card = result_panel(result, key="1", tokens=LIGHT_TOKENS)
        assert isinstance(card, ft.Container) and isinstance(card.content, ft.Row)
        lines = card.content.controls[1]
        assert isinstance(lines, ft.Column)
        return lines.controls

    tagged = column(
        ScanResult(ScanOutcome.ACCEPTED, "In", "Ada", ("x",), tags=(VEGETARIAN,))
    )
    assert [type(line) for line in tagged] == [ft.Text, ft.Text, ft.Container, ft.Text]
    plain = column(ScanResult(ScanOutcome.ACCEPTED, "In", "Ada", ("x",)))
    assert [type(line) for line in plain] == [ft.Text, ft.Text, ft.Text]


@pytest.mark.parametrize("dimmed", [False, True], ids=["fresh", "dimmed"])
@pytest.mark.parametrize(
    "outcome", [ScanOutcome.ACCEPTED, ScanOutcome.DUPLICATE, ScanOutcome.DENIED]
)
@pytest.mark.parametrize(
    ("dark", "high_contrast"),
    [(False, False), (True, False), (False, True), (True, True)],
    ids=["light", "dark", "hc-light", "hc-dark"],
)
def test_every_tag_reads_on_every_fill(
    outcome: ScanOutcome, dimmed: bool, dark: bool, high_contrast: bool
) -> None:
    """Words on chip, and chip on card: AA, and 7:1 in high contrast (ux.md §9)."""
    least = AAA_TEXT if high_contrast else AA_TEXT
    label, fill = fill_of(outcome, high_contrast=high_contrast, dimmed=dimmed)

    def hex_at(color: ft.ColorValue) -> str:
        """`color` in this theme."""
        return hex_of(color, dark=dark, high_contrast=high_contrast)

    card = hex_at(fill)
    for tag in (ALLERGY, VEGETARIAN):
        text, background = tag_colors(tag, label=label, fill=fill)
        chip = card if background is None else hex_at(background)
        words = hex_at(text)
        assert contrast_ratio(words, chip) >= least, (tag, words, chip)
        edge = hex_at(label)  # the chip's 1 dp edge
        assert contrast_ratio(edge, card) >= least, (tag, edge, card)
