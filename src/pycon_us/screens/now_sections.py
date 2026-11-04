"""Now's sections under the header and the strip, by season (ux.md §5.1, D-190).

`sections()` picks them: the key dates and "Build your schedule" before the
conference; on its days Your next session (`now_card`), the Schedule changes card,
Happening now and Up next, each folded at peak times (`now_fold`, D-327), and the
Schedule link; the Sprints row on the last evening and the sprint days; "Look back at
the schedule" afterwards. Apart from `now.py`, which wires the screen's hooks, so that
the screen stays under about 400 lines (D-66).
"""

from collections.abc import Callable
from datetime import datetime

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.agenda import NowNext, Phase, elapsed_percent, next_for_me
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timefmt import local_date, time_status, today
from pycon_us.core.timeline import Slot
from pycon_us.screens.now_card import Row, next_session, nothing_next
from pycon_us.screens.now_fold import HAPPENING, UP_NEXT
from pycon_us.screens.now_header import (
    Season,
    key_dates,
    spoken,
    sprints_link,
    up_next_when,
)
from pycon_us.services.errors import report_errors
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.semantics import named

type Fold = Callable[..., list[ft.Control]]
"""`now_fold.folded()` with the saved ids and the opened sections given: a section's
rows, folded at peak times, from its name, its sessions, `whole=` and `row=`."""

SCREEN = "now"
"""The screen's name in its semantics identifiers (decisions §M)."""

NOTHING_ON = "Nothing in session right now"
"""Happening now between two slots of a day (ux.md §5.1)."""


def sections(
    current: Season,
    answer: NowNext,
    now: datetime,
    data: ConferenceData,
    info: ConferenceInfo,
    row: Row,
    fold: Fold,
    *,
    saved: frozenset[str],
    changed: list[ft.Control],
    view_path: str,
    live: str,
    use_24h: bool,
) -> list[ft.Control]:
    """Return what Now shows under the header and the strip, in the given season.

    `changed` is the Schedule changes card, if any, shown under Your next session.
    """
    day = today(now, info.zone)
    sections: list[ft.Control] = []
    if current is Season.COUNTDOWN:
        sections += key_dates(info)
        sections.append(_button("Build your schedule", "/schedule", "build_schedule"))
        return sections
    if current is Season.OVER:
        sections.append(
            LinkTile(
                "Look back at the schedule",
                "/schedule",
                icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                identifier=f"{SCREEN}.schedule",
            )
        )
        return sections
    if answer.phase is Phase.AFTER:  # the last evening and the sprint days
        sections.append(sprints_link(info))
        return sections

    upcoming = answer.up_next
    mine = next_for_me(data, saved, now)
    if mine is not None:
        sections += next_session(mine, now, data, row, view_path)
    else:
        has_saved = any(session_id in data.sessions for session_id in saved)
        sections += nothing_next(has_saved, tonight=answer.phase is Phase.AFTER_DAY)
    sections += changed
    # The card already shows your session; when it is all that is on, or all that is
    # next, the card says so, and an empty Happening now would claim nothing is.
    others = _without(answer.happening, mine)
    if answer.phase is Phase.DAY and (others or not answer.happening):
        sections += _happening(others, answer.happening, now, row, fold, live)
    if upcoming is not None and (later := _without(upcoming.sessions, mine)):
        sections += _up_next(upcoming, later, row, fold, now, info, use_24h=use_24h)
    # Only a navigation: the Schedule (#86) opens on today during the conference. With
    # no slot after this one, the rest of today is the slot that is on.
    rest_of_today = upcoming is None or local_date(upcoming.start, info.zone) == day
    label = (
        "See the rest of today in Schedule" if rest_of_today else "Open the schedule"
    )
    sections.append(_button(label, "/schedule", "schedule", text=True))
    return sections


def _without(
    sessions: tuple[Session, ...], mine: Session | None
) -> tuple[Session, ...]:
    """`sessions` but your next session, which the card shows."""
    return tuple(s for s in sessions if mine is None or s.id != mine.id)


def _happening(
    happening: tuple[Session, ...],
    whole: tuple[Session, ...],
    now: datetime,
    row: Row,
    fold: Fold,
    live: str,
) -> list[ft.Control]:
    """Happening now: the sessions on but yours, saved ones first, each with its bar.

    Folded at peak times after the saved ones and three others (`fold`, D-327),
    and kept open by `whole`, every session on, the card's too.
    """
    dot = ft.Container(width=8, height=8, border_radius=4, bgcolor=live)
    header = SectionHeader("Happening now", level=2, leading=dot)
    if not happening:
        return [header, _note(NOTHING_ON, f"{SCREEN}.nothing_on")]

    return [
        header,
        *fold(
            HAPPENING,
            happening,
            whole=whole,
            row=lambda session: row(session, elapsed=elapsed_percent(session, now)),
        ),
    ]


def _up_next(
    slot: Slot,
    sessions: tuple[Session, ...],
    row: Row,
    fold: Fold,
    now: datetime,
    info: ConferenceInfo,
    *,
    use_24h: bool,
) -> list[ft.Control]:
    """Up next: the next slot's start, its countdown on its own day, then its rows.

    `sessions` are the slot's rows but your next session, which the card shows,
    saved ones first and folded at peak times as Happening now's (`fold`, D-327).
    """
    heading = f"Up next · {up_next_when(slot, now, info, use_24h=use_24h)}"
    controls: list[ft.Control] = [
        SectionHeader(heading, level=2, spoken=spoken(heading))
    ]
    # A slot has no end of its own: its start twice says only "Starts in 18 min".
    status = time_status(slot.start, slot.start, now, info.zone)
    if status is not None:
        controls.append(
            ft.Container(
                ft.Text(
                    status.label,
                    semantics_label=status.spoken,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=ft.Padding.only(left=16, right=16),
            )
        )
    controls += fold(UP_NEXT, sessions, whole=slot.sessions, row=row)
    return controls


def _button(label: str, location: str, name: str, *, text: bool = False) -> ft.Control:
    """A button that opens another tab: a tonal one, or a text one (`text`)."""
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(location)

    button: ft.Control
    if text:
        button = ft.TextButton(
            label, icon=ft.Icons.CALENDAR_MONTH_OUTLINED, on_click=go
        )
    else:
        button = ft.FilledTonalButton(
            label,
            on_click=go,
            # Material's 100 % padding at every size (D-344).
            style=ft.ButtonStyle(padding=LABEL_PADDING),
            elevation=0,  # with a style, Flet lifts it to 1 (D-344)
        )
    return ft.Container(
        named(f"{SCREEN}.{name}", button),
        # At the list's start, as its rows' text: a text button's label sits 8 dp
        # inside it, so 8 dp in puts the label 16 dp in.
        padding=ft.Padding.only(left=8 if text else 16, top=8, right=16),
        alignment=ft.Alignment.CENTER_LEFT,
    )


def _note(text: str, identifier: str) -> ft.Control:
    """A line of supporting text in the list's side padding."""
    return ft.Container(
        named(
            identifier,
            ft.Text(
                text,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=4),
    )
