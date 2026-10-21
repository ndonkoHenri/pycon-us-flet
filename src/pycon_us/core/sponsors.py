"""The sponsor queries (DATA-22, SPON-02, D-261) and Now's spotlight pick (D-37, D-298).

Sponsors have no id: a route names one by its slug (``slugs.sponsor_slug``), and
``sponsor_by_slug()`` finds it in the model's levels, which ``feed.process()`` has already
sorted (``ConferenceData.sponsor_levels``). ``spotlight_candidates()``,
``pick_spotlight()`` and ``thanks()`` choose and word the one sponsor Now thanks.
"""

from random import Random

from pycon_us.core.models import ConferenceData, Sponsor


def sponsor_by_slug(data: ConferenceData, slug: str) -> Sponsor | None:
    """Return the sponsor whose slug is ``slug``, or None when no sponsor has it.

    Two sponsors with one slug would be a feed problem that the weekly check reports
    (``tools/sponsor_invariants.py``); the first in level order wins, as Ionic's first match
    did. A scan of about a hundred sponsors needs no index.

    Args:
        data: The processed feed.
        slug: A sponsor slug, as a route carries it.

    Returns:
        The sponsor, or None.
    """
    return next(
        (
            sponsor
            for level in data.sponsor_levels
            for sponsor in level.sponsors
            if sponsor.slug == slug
        ),
        None,
    )


def spotlight_candidates(data: ConferenceData) -> tuple[Sponsor, ...]:
    """Return the sponsors that may appear in Now's spotlight, in level order (SHELL-08).

    They are the sponsors whose ``mobile_banner`` is set: 14 in 2026, 7 Visionary,
    6 Maintaining and 1 Sustainability (#373).

    Args:
        data: The processed feed.
    """
    return tuple(
        sponsor
        for level in data.sponsor_levels
        for sponsor in level.sponsors
        if sponsor.mobile_banner
    )


def pick_spotlight(
    candidates: tuple[Sponsor, ...], current: str, rng: Random
) -> Sponsor | None:
    """Return the sponsor Now's spotlight shows: the current one, else a random pick.

    The pick holds for the process (D-298): ``current``, the slug picked before, wins
    while it is still a candidate, and a new one is drawn only when it is not (the
    first time, or after a feed that dropped it or its banner).

    Args:
        candidates: ``spotlight_candidates()``'s answer.
        current: The slug picked before in this process; empty for none.
        rng: Where the pick comes from: the process's ``Random``, a seeded one in tests.

    Returns:
        The sponsor, or None when there is no candidate.
    """
    kept = next((s for s in candidates if s.slug == current), None)
    if kept is not None or not candidates:
        return kept
    return rng.choice(candidates)


def thanks(sponsor: Sponsor) -> str:
    """Return the spotlight's words: "Thanks to NVIDIA, a Visionary sponsor".

    The article goes by the level's first letter, "an" before a vowel, which fits
    every level the feed has had ("an Associate sponsor").

    Args:
        sponsor: The sponsor.
    """
    article = "an" if sponsor.level[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
    return f"Thanks to {sponsor.name}, {article} {sponsor.level} sponsor"
