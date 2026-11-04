"""The sponsor and job-listing invariants of a processed feed (D-77, D-261).

They are part of `tools/feed_invariants.py`'s `INVARIANTS`, which lists them in the
order of testing-and-quality.md §3.3; they live here so that module stays under D-66's
~400 lines as P2 adds sponsor and expo checks (#492).
"""

from collections import Counter
from typing import TYPE_CHECKING

from pycon_us.core.slugs import sponsor_slug

if TYPE_CHECKING:  # feed_invariants imports this module; only the type comes back
    from tools.feed_invariants import ProcessedFeed


def sponsor_slugs_are_unique(feed: ProcessedFeed) -> list[str]:
    """SPON-02: each sponsor's slug is its name's, and no two sponsors share one.

    Sponsors have no id, so a shared slug would route both to the first (D-261).
    """
    problems = []
    slugs: Counter[str] = Counter()
    for level in feed.data.sponsor_levels:
        for sponsor in level.sponsors:
            slugs[sponsor.slug] += 1
            if sponsor.slug != sponsor_slug(sponsor.name):
                problems.append(
                    f"sponsor {sponsor.name!r} has the slug {sponsor.slug!r}"
                )
    for slug, count in slugs.items():
        if count > 1:
            problems.append(f"{count} sponsors share the slug {slug!r}")
    return problems


def sponsor_levels_are_sorted_and_not_empty(feed: ProcessedFeed) -> list[str]:
    """DATA-22: the levels run by their order, each named once, with its own sponsors.

    A level's order is its first sponsor's (D-261), so its other sponsors must share it.
    """
    levels = feed.data.sponsor_levels
    problems = []
    orders = [level.order for level in levels]
    if orders != sorted(orders):
        problems.append("the sponsor levels are not sorted by their order")
    names = Counter(level.name for level in levels)
    if twice := sorted(name for name, count in names.items() if count > 1):
        problems.append(f"sponsor levels listed twice: {', '.join(twice)}")
    for level in levels:
        if not level.sponsors:
            problems.append(f"sponsor level {level.name!r} has no sponsor")
        if strays := [s.name for s in level.sponsors if s.level != level.name]:
            problems.append(f"sponsor level {level.name!r} lists {', '.join(strays)}")
        if others := sorted({s.level_order for s in level.sponsors} - {level.order}):
            problems.append(
                f"sponsor level {level.name!r} also has orders {', '.join(map(str, others))}"
            )
    return problems


def job_listings_name_a_sponsor(feed: ProcessedFeed) -> list[str]:
    """SPON-05: every job listing names a sponsor exactly, as `jobs.listings_of` finds it.

    A listing carries its sponsor's name, not a slug (D-278), so a name the sponsors do
    not have would leave its roles on no sponsor's page.
    """
    names = {s.name for level in feed.data.sponsor_levels for s in level.sponsors}
    return [
        f"job listing {job.id} names no sponsor: {job.sponsor_name!r}"
        for job in feed.data.job_listings
        if job.sponsor_name not in names
    ]
