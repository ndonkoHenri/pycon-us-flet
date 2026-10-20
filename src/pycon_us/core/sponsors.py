"""The sponsor queries (DATA-22, SPON-02, D-261).

Sponsors have no id: a route names one by its slug (``slugs.sponsor_slug``), and
``sponsor_by_slug()`` finds it in the model's levels, which ``feed.process()`` has already
sorted (``ConferenceData.sponsor_levels``).
"""

from pycon_us.core.models import ConferenceData, Sponsor


def sponsor_by_slug(data: ConferenceData, slug: str) -> Sponsor | None:
    """Return the sponsor whose slug is ``slug``, or None when no sponsor has it.

    Two sponsors with one slug would be a feed problem that the weekly check reports
    (``tools/feed_invariants.py``); the first in level order wins, as Ionic's first match
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
