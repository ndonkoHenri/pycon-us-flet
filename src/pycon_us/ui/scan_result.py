"""The scan screen's result panel: an outcome in colour, icon and word (LEAD-09; D-65).

ux.md §7.2's table: accepted is white on green with ``CHECK_CIRCLE``, a duplicate dark
on amber with ``HISTORY``, a denial white on red with ``BLOCK``; queued offline and a
code that is not a badge are neutral, with ``CLOUD_UPLOAD_OUTLINED`` and
``ERROR_OUTLINE``; CoC's incident recorded and not recorded are neutral too, with
``TASK_ALT`` and ``REMOVE_CIRCLE_OUTLINE`` (#760: a safety record is never a
check-in's green). The fills are fixed colours, the same in light and dark, each label
at 4.5:1 or better on its fill; high contrast darkens the green and the red for 7:1
(``tests/test_scan_screen.py``). Colour is never the only signal: the word and the
icon say the outcome (ux.md §9). The panel stays until the next scan and dims after
``DIM_AFTER`` seconds: its fill gives way to the neutral one, so a new result stands
out, while its icon and words stay; the line under it says how old it is.

A result's **tags** (Door check's dietary needs and allergy, DOOR-05) are chips under
the name, in a row that wraps: a warning (an allergy) first, larger, with
``WARNING_AMBER`` and the card's colours swapped; the others outlined, with
``RESTAURANT_OUTLINED``. They take the card's own colours, so they read on every fill
at its contrast (#767).
"""

import flet as ft

from pycon_us.core.badges import ScanOutcome, ScanResult, Tag
from pycon_us.core.timefmt import seconds_ago
from pycon_us.theme import Tokens
from pycon_us.theme_hc import hc_border

DIM_AFTER = 5
"""Seconds after which a result dims (ux.md §7.2)."""

FILLS: dict[ScanOutcome, tuple[str, str]] = {
    ScanOutcome.ACCEPTED: ("#FFFFFF", "#146C2E"),
    ScanOutcome.DUPLICATE: ("#1A1A1A", "#F2C14E"),
    ScanOutcome.DENIED: ("#FFFFFF", "#B3261E"),
}
"""Each coloured outcome's (label, fill), ux.md §7.2's table; the others are neutral."""

HC_FILLS: dict[ScanOutcome, tuple[str, str]] = {
    **FILLS,
    ScanOutcome.ACCEPTED: ("#FFFFFF", "#0D5323"),
    ScanOutcome.DENIED: ("#FFFFFF", "#8C1D18"),
}
"""The same in high contrast: the table's green and red give 6.5:1, short of 7:1."""

ICONS: dict[ScanOutcome, ft.IconData] = {
    ScanOutcome.ACCEPTED: ft.Icons.CHECK_CIRCLE,
    ScanOutcome.DUPLICATE: ft.Icons.HISTORY,
    ScanOutcome.DENIED: ft.Icons.BLOCK,
    ScanOutcome.QUEUED: ft.Icons.CLOUD_UPLOAD_OUTLINED,
    ScanOutcome.INVALID: ft.Icons.ERROR_OUTLINE,
    ScanOutcome.RECORDED: ft.Icons.TASK_ALT,
    ScanOutcome.NOT_RECORDED: ft.Icons.REMOVE_CIRCLE_OUTLINE,
}
"""Each outcome's icon (ux.md §7.2)."""

READY = "Ready to scan"
READY_BODY = "Scan a badge, or type its code below."
"""What the panel says before the first scan."""


def fill_of(
    outcome: ScanOutcome, *, high_contrast: bool, dimmed: bool
) -> tuple[ft.ColorValue, ft.ColorValue]:
    """Return a result's (label, fill) colours.

    Args:
        outcome: How the scan ended.
        high_contrast: HC is on screen (``Tokens.high_contrast``).
        dimmed: The result is older than ``DIM_AFTER`` s: neutral, as queued is.
    """
    fills = HC_FILLS if high_contrast else FILLS
    if dimmed or outcome not in fills:
        return ft.Colors.ON_SURFACE, ft.Colors.SURFACE_CONTAINER_HIGHEST
    return fills[outcome]


def icon_color(outcome: ScanOutcome, label: ft.ColorValue) -> ft.ColorValue:
    """Return the icon's colour: the label's, but ``error`` for a code to correct."""
    return ft.Colors.ERROR if outcome is ScanOutcome.INVALID else label


def result_panel(
    result: ScanResult | None, *, key: str, tokens: Tokens, dimmed: bool = False
) -> ft.Control:
    """Return the panel's card: icon, word, name or code and details.

    Before the first scan (``result`` None) it says the screen is ready. The card has
    no semantics of its own: the live region around it is one node read as its lines
    (``spoken()``), the icon decorative, so the result is said once, in words.

    Args:
        result: The last scan's result, or None before the first.
        key: The scan's key: a new key is a new card, which ``AnimatedSwitcher``
            brings in; the same key re-renders the card in place (a dimming).
        tokens: The scheme's tokens, for high contrast's edge.
        dimmed: The result is older than ``DIM_AFTER`` s.
    """
    if result is None:
        result = ScanResult(ScanOutcome.QUEUED, READY, details=(READY_BODY,))
        icon = ft.Icons.QR_CODE_SCANNER
    else:
        icon = ICONS[result.outcome]
    label, fill = fill_of(
        result.outcome, high_contrast=tokens.high_contrast, dimmed=dimmed
    )
    lines: list[ft.Control] = [
        ft.Text(
            result.word,
            theme_style=ft.TextThemeStyle.TITLE_LARGE,
            weight=ft.FontWeight.W_600,
            color=label,
        )
    ]
    if result.title:
        lines.append(
            ft.Text(
                result.title,
                theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                color=label,
            )
        )
    if result.tags:
        lines.append(tag_row(result.tags, label=label, fill=fill))
    lines += [
        ft.Text(line, theme_style=ft.TextThemeStyle.BODY_MEDIUM, color=label)
        for line in result.details
    ]
    return ft.Container(
        key=key,
        content=ft.Row(
            [
                ft.Icon(
                    icon,
                    size=32,
                    color=icon_color(result.outcome, label),
                    apply_text_scaling=True,
                ),
                ft.Column(lines, spacing=2, tight=True, expand=True),
            ],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        bgcolor=fill,
        padding=16,
        border_radius=12,
        border=hc_border(tokens.high_contrast),
    )


def tag_colors(
    tag: Tag, *, label: ft.ColorValue, fill: ft.ColorValue
) -> tuple[ft.ColorValue, ft.ColorValue | None]:
    """Return a chip's (text, background) on a card of ``label`` on ``fill``.

    A plain chip is the card's label colour on the card, inside an edge of the same
    colour. A warning swaps them, the fill's colour on a label-coloured chip, so it
    stands out on every fill at the card's own contrast: AA on the table's fills and
    on the neutral one, 7:1 in high contrast.
    """
    return (fill, label) if tag.warning else (label, None)


def tag_chip(tag: Tag, *, label: ft.ColorValue, fill: ft.ColorValue) -> ft.Control:
    """Return one tag as a chip: ``WARNING_AMBER`` and larger for a warning.

    A 1 dp edge in the label's colour sets every chip apart, high contrast included
    (D-306); the words wrap at large text (``expand_loose``). No semantics of its own:
    the panel's label says the tags (``ScanResult.spoken``).
    """
    text, background = tag_colors(tag, label=label, fill=fill)
    if tag.warning:
        icon, size, style = ft.Icons.WARNING_AMBER, 20, ft.TextThemeStyle.LABEL_LARGE
    else:
        icon, size, style = (
            ft.Icons.RESTAURANT_OUTLINED,
            16,
            ft.TextThemeStyle.LABEL_MEDIUM,
        )
    return ft.Container(
        ft.Row(
            [
                ft.Icon(icon, size=size, color=text, apply_text_scaling=True),
                ft.Text(
                    tag.text,
                    theme_style=style,
                    weight=ft.FontWeight.W_700 if tag.warning else None,
                    color=text,
                    expand=True,
                    expand_loose=True,
                ),
            ],
            spacing=6,
            tight=True,
        ),
        bgcolor=background,
        border=ft.Border.all(1, label),
        border_radius=8,
        padding=ft.Padding.symmetric(
            horizontal=10 if tag.warning else 8, vertical=6 if tag.warning else 4
        ),
    )


def tag_row(
    tags: tuple[Tag, ...], *, label: ft.ColorValue, fill: ft.ColorValue
) -> ft.Control:
    """Return a result's tags as a wrapping row of chips, warnings first (DOOR-05).

    Args:
        tags: The result's tags.
        label: The card's text colour.
        fill: The card's fill.
    """
    ordered = sorted(tags, key=lambda tag: not tag.warning)  # stable: keeps the rest
    return ft.Container(
        ft.Row(
            [tag_chip(tag, label=label, fill=fill) for tag in ordered],
            wrap=True,
            spacing=8,
            run_spacing=8,
        ),
        padding=ft.Padding.only(top=6, bottom=4),
    )


def spoken(result: ScanResult | None, serial: int = 0) -> str:
    """Return the panel's words in reading order, for the live region that holds it.

    A result ends with its count, "Scan 2": a live region is said only when its
    label changes, so the same result twice in a row is said twice.

    Args:
        result: The result on the panel, or None before the first scan.
        serial: The result's count on this screen.
    """
    if result is None:
        return f"{READY}\n{READY_BODY}"
    return f"{result.spoken}\nScan {serial}"


def age_line(seconds: float) -> ft.Control:
    """Return how long ago the shown result came, "Read 12 seconds ago".

    Outside the live region: it changes every second, and only the result is said.

    Args:
        seconds: The result's age.
    """
    # A node of its own: else its column takes the text, and a screen reader read
    # the age before the result (seen on the iOS simulator, #723).
    return ft.Semantics(
        container=True,
        content=ft.Text(
            f"Read {seconds_ago(seconds)}",
            theme_style=ft.TextThemeStyle.BODY_SMALL,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
    )
