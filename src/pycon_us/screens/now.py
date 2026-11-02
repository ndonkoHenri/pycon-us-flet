"""Now (``/now``), the start screen: "what should I do next?" (SCHED-25, SCHED-26; D-14).

From the top (ux.md §5.1): the status header (``now_header``), the status strip, which
refreshes the feed every 15 min while Now shows (D-175), the Scan badges card for an
account with a staff tool (``staff_entry``, D-421) in every season, then by season:

- before the conference, the key dates and "Build your schedule";
- on its days, **Your next session** (``now_card``: ``agenda.next_for_me()``'s saved
  session to go to next, with its star, its countdown and "Show room", and its elapsed
  bar once it is on), the Schedule changes card while changes to saved sessions are
  unseen (``now_changes``, D-255), **Happening now** (the other sessions on, saved
  ones first, each with an elapsed bar), **Up next** (the next slot, ``NowNext.up_next``, but the
  card's session), each folded at peak times after your saved sessions and three
  others (``now_fold``, D-327), and a link to the Schedule;
- on the last evening and the sprint days, the Sprints page; afterwards, the schedule
  to look back at;
- on the conference and sprint days, after the sessions, the quick info buttons
  (``now_quick``: Wi-Fi, Help & safety, Venue & hours, D-338);
- in every season, the sponsor spotlight (``now_spotlight``, D-37, D-298) when a
  sponsor may appear there.

Schedule filters never apply (D-20). The screen recomputes on the minute tick
(``use_minute()``): every 60 s while it is mounted and the app is in the foreground,
and at once on a resume (D-40, D-175), from ``clock.now()``, so the Developer fake clock
drives it (D-187). The sections are ``now_sections``'s; their rows are the memoised
session rows, their views built once per feed version (D-153, D-184), and a row pushes
its session over Now, so Back returns here (D-17). Without data, the skeleton, then "Can't load the schedule" (D-32).
"""

from collections.abc import Mapping
from functools import partial

import flet as ft

from pycon_us import clock
from pycon_us.change_log import use_change_log
from pycon_us.config import ConferenceInfo
from pycon_us.core.agenda import now_next
from pycon_us.core.models import Session
from pycon_us.core.row_views import SessionView
from pycon_us.core.sponsors import pick_spotlight, spotlight_candidates
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.screens.now_changes import changes_card
from pycon_us.screens.now_fold import folded
from pycon_us.screens.now_header import StatusHeader, header_copy
from pycon_us.screens.now_quick import SEASONS, QuickInfo
from pycon_us.screens.now_sections import SCREEN, sections
from pycon_us.screens.now_spotlight import Spotlight
from pycon_us.screens.staff_entry import ScanCard
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.favorite import ToggleFavorite, use_favorite_toggle
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold, search_button
from pycon_us.ui.session_rows import (
    NO_CHANGES,
    Changes,
    NoticeRow,
    SessionRow,
    is_notice,
    use_recent_changes,
    use_session_views,
)
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList
from pycon_us.ui.status_strip import StatusStrip, use_minute
from pycon_us.ui.widths import LIST, sides, use_margin


@ft.component
def Now() -> ft.View:
    """The Now root: where the conference stands, and what to do next."""
    list_ref, scroll_to_top = use_scroll_to_top()
    margin = use_margin(LIST)  # its width class (D-305)
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    conference = use_conference()
    favorites = use_favorites()
    change_log = use_change_log()  # Now's card goes once its changes are seen
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    prefs = use_prefs()
    use_minute()  # recompute every minute while Now shows, and at once on a resume
    info = svc.year.conference
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    # Every session's view, once per feed version: the rows Now shows change with the
    # minute, and a view that stays the same object lets its row skip its body (F34).
    views = use_session_views(
        conference, tuple(data.sessions) if data else (), use_24h=use_24h
    )
    by_id = ft.use_memo(lambda: {v.session.id: v for v in views}, [views])
    changes = use_recent_changes()
    candidates = ft.use_memo(lambda: spotlight_candidates(data) if data else (), [data])
    # The sections the user opened past their fold (now_fold.fold_key(), D-327).
    opened, set_opened = ft.use_state(frozenset[str]())

    @report_errors
    def toggle(key: str) -> None:
        set_opened(opened ^ {key})

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    row = partial(_row, by_id, info, favorites.ids, changes, on_toggle, tokens)
    fold = partial(folded, saved=favorites.ids, opened=opened, toggle=toggle)

    rows: list[ft.Control]
    if data is None and conference.problem is None:
        # The first fetch runs, or is about to (NEW-03); the strip says so.
        rows = [
            StatusStrip(auto_refresh=True),
            ScanCard(),  # staff work needs no schedule
            SkeletonList("Loading schedule"),
        ]
    elif data is None:
        rows = [
            StatusStrip(auto_refresh=True),  # its bar shows a retry
            ScanCard(),
            EmptyState(
                "Can't load the schedule",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                disabled=conference.refreshing,
                identifier=f"{SCREEN}.no_data",
            ),
        ]
    else:
        now = clock.now()
        answer = now_next(data, now)
        copy = header_copy(
            answer,
            now,
            data,
            info,
            use_24h=use_24h,
            device_offset=now.astimezone().utcoffset(),
        )
        rows = [
            StatusHeader(
                info.name, copy, dark=prefs.dark, high_contrast=tokens.high_contrast
            ),
            StatusStrip(auto_refresh=True),
            ScanCard(),  # in every season: staff work before and during (ux §5.1)
            *sections(
                copy.season,
                answer,
                now,
                data,
                info,
                row,
                fold,
                saved=favorites.ids,
                changed=changes_card(
                    change_log,
                    favorites.ids,
                    now,
                    view_path=view_path,
                    year=svc.storage.year,
                ),
                view_path=view_path,
                live=tokens.live,
                use_24h=use_24h,
            ),
        ]
        if copy.season in SEASONS:  # under the sessions, never above them (D-338)
            rows.append(QuickInfo(view_path))
        # One sponsor for the process (D-298): ViewMemory keeps the pick, so a new
        # session after Back on Now (F29) thanks the same one.
        memory = svc.memory
        sponsor = pick_spotlight(candidates, memory.spotlight, memory.rng)
        if sponsor is not None:
            memory.spotlight = sponsor.slug
            rows.append(Spotlight(sponsor, view_path, large_text=prefs.time_above))
    return AppScaffold(
        title="Now",
        source=__name__,
        actions=[search_button(svc.memory, "all")],
        body=ft.ListView(
            rows, expand=True, ref=list_ref, padding=sides(margin, bottom=16)
        ),
        on_retap=scroll_to_top,
    )


def _row(
    by_id: Mapping[str, SessionView],
    info: ConferenceInfo,
    saved: frozenset[str],
    changes: Changes,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    session: Session,
    *,
    screen: str = SCREEN,
    elapsed: int | None = None,
) -> ft.Control:
    """One session's memoised row (D-184): a notice's, or a session's with its star."""
    view = by_id[session.id]
    if is_notice(session, info):  # breaks and notices: no star, no bar (D-31)
        return NoticeRow(
            view,
            tokens,
            screen=screen,
            changed=changes.get(session.id, NO_CHANGES),
        )
    return SessionRow(
        view,
        session.id in saved,
        on_toggle,
        tokens,
        screen=screen,
        elapsed=elapsed,
        changed=changes.get(session.id, NO_CHANGES),
    )
