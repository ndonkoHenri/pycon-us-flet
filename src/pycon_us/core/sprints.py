"""The Sprints page's query: the projects in order, the filter and the card's cut.

`projects()` gives the feed's sprint projects in the order the page lists them, by
name as people read it (folded, as D-46 sorts speakers), once per feed version.
`filter_projects()` keeps the projects that hold every word of a filter in their
`search_text`: the folded name, submitter and description text that feed processing
built, never markup (EVT-06, D-46, D-140). `cut_short()` says whether a card shows its
description cut at four lines with "More" (EVT-05), by `needs_more()`, which the Job
listings' long-form listings share.
"""

from pycon_us.core.models import ConferenceData, Sprint
from pycon_us.core.queries import fold, matching

PREVIEW_CHARS = 160
"""The longest description a card shows whole: about four lines on a phone at 100 %.

Flet cannot say whether a text overflows its lines, so the length decides: a longer
one is cut at four lines with "More", a shorter one is never cut, so it shows whole at
any text size (at 200 % it takes more lines rather than losing words).
"""


def projects(data: ConferenceData) -> tuple[Sprint, ...]:
    """Return the sprint projects in the page's order: by folded name, then id.

    Build it once per feed version. The feed lists them by name with upper case first
    (`aio-libs` after `ScanAPI`); folded, `conda` sits between `Cloud Custodian`
    and `CPython`, where a reader looks for it.

    Args:
        data: The processed feed.
    """
    return tuple(
        sorted(data.sprints, key=lambda sprint: (fold(sprint.name), sprint.id))
    )


def filter_projects(listed: tuple[Sprint, ...], query: str) -> tuple[Sprint, ...]:
    """Return the projects a filter keeps: those whose text holds every word (EVT-06).

    The query folds as search's does (D-46), and each word may sit anywhere in the
    project's name, submitter or description text, as a substring. A filter with no
    word to match keeps every project and returns `listed` itself: a blank one, and
    one that folds to nothing (a lone `’`).

    Args:
        listed: The page's projects (`projects()`).
        query: What the user typed in the filter field.

    Returns:
        The projects found, in the page's order.
    """
    return matching(listed, query, lambda sprint: sprint.search_text)


def cut_short(sprint: Sprint) -> bool:
    """Whether a card cuts the description at four lines and offers "More" (EVT-05).

    `needs_more()` on the project's description.

    Args:
        sprint: The project.
    """
    return needs_more(sprint.description_text, sprint.description_md)


def needs_more(text: str, markdown: str) -> bool:
    """Whether a feed text is cut at four lines with "More" that shows its Markdown.

    True for a text longer than `PREVIEW_CHARS`, and for one whose Markdown has a
    line break (paragraphs, a list) or a link, which the flat preview cannot show:
    "More" shows the Markdown, links included. Converted text escapes a literal
    `](` (D-115), so in the Markdown it only ever opens a link. The Sprints cards
    and the Job listings' long-form listings use it (D-202).

    Args:
        text: The text the preview shows (`html_md.to_text`).
        markdown: The same text as Markdown.
    """
    return len(text) > PREVIEW_CHARS or "\n" in markdown or "](" in markdown
