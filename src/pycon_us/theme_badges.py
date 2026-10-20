"""The badges' colours (D-25, D-174; ux.md §3.4): ``BadgeColors`` and the track palette.

A badge is tonal, a label on a fill of the track's own, or outlined, a label and a
border in one colour on whatever surface it sits on. ``theme.py`` builds each scheme's
badges into its ``Tokens`` from what is here: ``tonal()`` over the palette in light and
dark, and outlines ``HC_BADGE_BORDER`` wide in high contrast (THEME-06, D-285).
``ui/badges.py`` draws them.

Module of its own so that high contrast's tokens leave ``theme.py`` near D-66's 400
lines.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BadgeColors:
    """The colours of one badge (D-25), as ``#RRGGBB``.

    Attributes:
        text: The label's colour.
        fill: The pill's colour; None for an outlined badge, whose label and border
            are both ``text``, on whatever surface the badge sits on.
        border_width: The border's width in dp: 1, or ``HC_BADGE_BORDER`` in high
            contrast (THEME-06).
    """

    text: str
    fill: str | None = None
    border_width: float = 1


HC_BADGE_BORDER = 1.5
"""Every badge's outline in high contrast, in dp (ux.md §3.4)."""

type Pair = tuple[str, str, str, str]
"""A palette entry: light fill, light text, dark fill, dark text."""

# ux.md §3.4: an entry for each key of the track registry (conference.toml), spaces and
# capitals included. Keynotes and plenaries share a pair; breaks and notices share the
# neutral grey, which a key the palette lacks gets too (a new kind in next year's feed).
# The fills sit on one CIELAB lightness (87 light, 29 dark) and chroma (22, less where
# sRGB runs out), about 30 degrees of hue apart, with Summit a quieter slate, so any two
# fills, the En Español pink and the grey included, differ by a CIE76 distance of 10 or
# more and read as different colours; each label is its fill's hue at lightness 27
# (light) or 90 (dark). Tests check both properties.
NEUTRAL: Pair = ("#E6E6E6", "#383838", "#404040", "#E0E0E0")
"""The grey of breaks, notices and a track the palette lacks."""

TRACK_PAIRS: dict[str, Pair] = {
    "Talk": ("#C7DBFE", "#014271", "#2C4666", "#D9E3F5"),
    "Tutorial": ("#FFCDD8", "#6C293E", "#643743", "#F6DCE1"),
    "Keynote": ("#E0D4FD", "#443869", "#483F61", "#E6E0F2"),
    "Plenary": ("#E0D4FD", "#443869", "#483F61", "#E6E0F2"),
    "Lightning-talks": ("#E9D9B0", "#4B3F0A", "#4E4422", "#EAE2CF"),
    "Security": ("#FAD3B5", "#5D3712", "#5B3E26", "#F2DFD1"),
    "Ai": ("#AAE6D8", "#01493E", "#0F4D43", "#CEE8E1"),
    "Charla": ("#ABE2FD", "#03465A", "#034B60", "#CFE6F2"),
    "Poster": ("#FFCFC6", "#6A2D25", "#643932", "#F7DDD8"),
    "Sponsor Presentation": ("#D4DFB5", "#354511", "#3E4826", "#E0E5D2"),
    "Open Space": ("#BDE4C3", "#134925", "#2A4C32", "#D6E7D8"),
    "Summit": ("#BED5E1", "#1E4455", "#3C515B", "#CFE6F3"),
    "Event": ("#A2E6EC", "#03474C", "#024C52", "#CBE8EB"),
    "Break": NEUTRAL,
    "Informational": NEUTRAL,
}
"""Each track key's palette entry (ux.md §3.4)."""

SPANISH: Pair = ("#FFD7F3", "#5E0058", "#5E0058", "#FFD7F3")
"""The "En Español" pair: pink under purple in light, inverted in dark (D-25)."""


def tonal(pair: Pair, *, dark: bool) -> BadgeColors:
    """Return one palette entry's tonal badge in the light or dark scheme."""
    light_fill, light_text, dark_fill, dark_text = pair
    if dark:
        return BadgeColors(text=dark_text, fill=dark_fill)
    return BadgeColors(text=light_text, fill=light_fill)
