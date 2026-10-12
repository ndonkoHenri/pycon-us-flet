"""Read-only questions screens ask of the processed feed (architecture §7.5).

Queries never change the model (SCHED-17): they return new values computed from it.
"""

from datetime import date, timedelta

from pycon_us.core.models import ConferenceData


def days(data: ConferenceData, first_day: date, last_day: date) -> tuple[date, ...]:
    """Return the Schedule's days: every date of the conference, in order (DATA-17).

    The range runs from the conference's first day to its last (the sprints, which the
    feed has no sessions for), and widens to any schedule day outside it, so no session
    is ever without its day. A day's index is its position here, and it never moves while
    the feed and the year stay the same. Filters play no part (Ionic ignored them too).

    Args:
        data: The processed feed.
        first_day: The conference's first day, from ``conference.toml``.
        last_day: The conference's last day, from ``conference.toml``.

    Returns:
        The dates, one per day, oldest first.
    """
    dates = [day.date for day in data.days]
    start, end = min([first_day, *dates]), max([last_day, *dates])
    return tuple(start + timedelta(days=n) for n in range((end - start).days + 1))
