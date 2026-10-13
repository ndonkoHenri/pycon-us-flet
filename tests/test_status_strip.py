"""Tests for the status strip and the minute tick: ``StatusStrip``, ``use_minute()`` (D-200).

The strip's body runs outside a renderer: the hooks it calls (``ft.use_effect``,
``ft.use_state`` and the store hooks) are replaced by ``Hooks``, and a fake page is
bound as Flet binds a session's page. What the strip looks like at 200 % text is
checked on devices (#76's and #87's PRs).
"""


# ------------------------------------------------------------------ StatusStrip

FETCHED = datetime(2026, 5, 12, 10, 42, tzinfo=PACIFIC)  # a Tuesday


@pytest.mark.parametrize(
    ("status", "fetched_at", "line"),
    [
        ("fresh", FETCHED, None),
        ("refreshing", FETCHED, "Updating the schedule…"),
        ("stale", FETCHED, "Updated 9 hours ago"),
        ("stale", None, "No schedule yet"),
        ("offline", FETCHED, "Offline · schedule from Tue, May 12, 10:42 AM"),
        ("problem", FETCHED, "Couldn't update · schedule from Tue, May 12, 10:42 AM"),
        ("offline", None, "Offline · no schedule yet"),
        ("problem", None, "Couldn't update · no schedule yet"),
    ],
)
def test_the_strip_says_why_the_data_is_not_fresh(
    status: Status, fetched_at: datetime | None, line: str | None
) -> None:
    now = FETCHED + timedelta(hours=9, minutes=5)
    assert strip_line(status, fetched_at, now, PACIFIC, use_24h=False) == line


def test_the_strip_writes_times_in_conference_time_and_the_device_format() -> None:
    fetched_utc = FETCHED.astimezone(ZoneInfo("UTC"))
    line = strip_line("offline", fetched_utc, FETCHED, PACIFIC, use_24h=True)
    assert line == "Offline · schedule from Tue, May 12, 10:42"


def render_strip(*, auto_refresh: bool = False) -> ft.Semantics:
    # The body, without @ft.component.
    strip = inspect.unwrap(StatusStrip)(auto_refresh=auto_refresh)
    assert isinstance(strip, ft.Semantics)
    return strip


def icon_of(strip: ft.Semantics) -> ft.Icon:
    """The strip's icon, beside its line."""
    box = cast(ft.Container, strip.content)
    padded = cast(ft.Container, cast(ft.Column, box.content).controls[0])
    line_row = cast(ft.Row, cast(ft.Row, padded.content).controls[0])
    icon = line_row.controls[0]
    assert isinstance(icon, ft.Icon)
    return icon


@dataclass(eq=False)
class StripRenders:
    """Renders the strip at every change of the store, as a subscribed strip does.

    The test keeps it: an observable holds its listeners weakly.
    """

    conference: Conference
    strips: list[ft.Semantics] = field(default_factory=list)

    def __post_init__(self) -> None:
        assert isinstance(self.conference, ft.Observable)
        self.conference.subscribe(self)

    def __call__(self, _sender: object, _name: str | None) -> None:
        self.strips.append(render_strip())


def strip_parts(strip: ft.Semantics) -> tuple[ft.Text, ft.TextButton, ft.ProgressBar]:
    box = strip.content
    assert isinstance(box, ft.Container)
    column = box.content
    assert isinstance(column, ft.Column)
    padded, slot = column.controls
    assert isinstance(slot, ft.Container)
    assert slot.height == 2  # kept while the bar hides: nothing moves (ux.md §3.9)
    progress = slot.content
    assert isinstance(padded, ft.Container)
    assert isinstance(padded.content, ft.Row)
    # Room around a line that wraps at 200 % text (ux.md §3.9).
    assert padded.padding == ft.Padding.only(left=16, top=4, right=8, bottom=4)
    line_row, button = padded.content.controls
    assert isinstance(line_row, ft.Row)
    # The icon tops the line, so a line that wraps keeps it beside its first line.
    assert line_row.vertical_alignment == ft.CrossAxisAlignment.START
    assert padded.content.vertical_alignment == ft.CrossAxisAlignment.CENTER
    icon, text = line_row.controls
    assert isinstance(icon, ft.Icon)
    assert isinstance(text, ft.Text)
    assert isinstance(button, ft.TextButton)
    assert isinstance(progress, ft.ProgressBar)
    return text, button, progress


@pytest.fixture
def fake_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Two days before the conference, so a 25 h old feed is stale (D-32)."""
    now = datetime(2026, 5, 11, 12, 0, tzinfo=PACIFIC)
    monkeypatch.setattr(clock, "now", lambda: now)
    return now


def test_the_strip_is_hidden_while_the_data_is_fresh(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=1)
    strip = render_strip()
    assert strip.visible is False


def test_a_stale_strip_is_a_live_region_with_refresh(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=25)
    strip = render_strip()
    text, button, progress = strip_parts(strip)
    assert strip.visible is True
    assert strip.live_region is True
    assert strip.identifier == "app.status"
    assert text.value == "Updated 1 day ago"
    assert button.disabled is False
    assert button.on_click is not None
    assert progress.visible is False


async def test_while_a_refresh_the_user_asked_for_runs_it_says_so_and_disables_refresh(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    fake_now: datetime,
    network: Network,
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=25)
    tap = press(strip_parts(render_strip())[1])  # Refresh
    await network.arrived.wait()

    strip = render_strip()
    text, button, progress = strip_parts(strip)
    assert strip.visible is True
    assert text.value == "Updating the schedule…"
    assert icon_of(strip).color == ft.Colors.ON_SURFACE_VARIANT
    assert button.disabled is True
    assert progress.visible is True
    assert progress.value is None  # indeterminate
    network.released.set()
    await tap


async def test_an_automatic_refresh_over_fresh_data_keeps_the_strip_hidden(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=1)
    conference.start_refresh_if_due(svc.storage, svc.year)
    await network.arrived.wait()

    assert conference.refreshing
    assert render_strip().visible is False  # nothing appears, nothing moves (D-181)


def looks(strip: ft.Semantics) -> tuple[object, ...]:
    """What a sighted user and a screen reader get from the strip, but its bar."""
    text, button, _ = strip_parts(strip)
    icon = icon_of(strip)
    return strip.visible, icon.icon, icon.color, text.value, button.disabled


async def test_an_automatic_refresh_over_an_offline_strip_shows_only_the_bar(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    conference.fetched_at = datetime(2026, 5, 11, 10, 42, tzinfo=PACIFIC)
    conference.problem = "offline"  # the last refresh got no answer
    network.error = api.NetworkError("ConnectError: still offline")
    offline = looks(render_strip())
    assert offline == (
        True,
        ft.Icons.CLOUD_OFF_OUTLINED,
        DARK_TOKENS.warning,
        "Offline · schedule from Mon, May 11, 10:42 AM",
        False,
    )
    renders = StripRenders(conference)

    task = conference.start_refresh_if_due(svc.storage, svc.year)  # the 15-min tick
    assert task is not None
    await network.arrived.wait()
    during = render_strip()
    network.released.set()
    await task
    after = render_strip()

    # Line, icon and button never changed, so the live region announces nothing new;
    # only the bar came and went, in its fixed slot (D-181).
    assert {looks(strip) for strip in [during, after, *renders.strips]} == {offline}
    assert strip_parts(during)[2].visible is True
    assert strip_parts(after)[2].visible is False
    assert [strip_parts(strip)[2].visible for strip in renders.strips] == [True, False]


async def test_refresh_during_a_quiet_refresh_joins_it_and_says_so_at_once(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=25)
    quiet = conference.start_refresh_if_due(svc.storage, svc.year)
    assert quiet is not None
    await network.arrived.wait()
    strip = render_strip()
    assert strip_parts(strip)[0].value == "Updated 1 day ago"
    renders = StripRenders(conference)

    tap = press(strip_parts(strip)[1])  # Refresh, while the quiet refresh runs
    await asyncio.sleep(0)  # the handler runs up to its wait

    (joined,) = renders.strips  # the tap re-renders the strip at once
    text, button, progress = strip_parts(joined)
    assert text.value == "Updating the schedule…"
    assert button.disabled is True
    assert progress.visible is True
    assert conference._task is quiet
    network.released.set()
    await tap
    assert quiet.done()
    assert network.requests == 1  # one request for both (D-145)


# ------------------------------------------------------------------ the strip's ticks


@dataclass
class Clock:
    """``clock.now()`` for a test, moved by hand."""

    now: datetime

    def move(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def moving_clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock(datetime(2026, 5, 11, 12, 0, 30, tzinfo=PACIFIC))
    monkeypatch.setattr(clock, "now", lambda: fake.now)
    return fake


@dataclass
class Loops:
    """Stands in for ``Services.run_every``: records each loop instead of running it."""

    started: list[tuple[float, Callable[[], object]]] = field(default_factory=list)

    # A bound method set on the class is not bound again: no `self` of Services.
    async def run_every(self, seconds: float, action: Callable[[], object]) -> None:
        self.started.append((seconds, action))


@pytest.fixture
def loops(monkeypatch: pytest.MonkeyPatch) -> Loops:
    fake = Loops()
    monkeypatch.setattr(Services, "run_every", fake.run_every)
    return fake


async def mounted_strip(
    hooks: Hooks, loops: Loops, **kwargs: Any
) -> Callable[[], object]:
    """Render the strip and run its effect as a mount does; return the tick."""
    render_strip(**kwargs)
    setup, _ = hooks.effects[-1]
    await setup()
    ((seconds, tick),) = loops.started
    assert seconds == scaffold.TICK_SECONDS == 60
    return tick


def test_the_ticks_stop_when_the_strip_unmounts(hooks: Hooks, page: FakePage) -> None:
    render_strip(auto_refresh=True)
    (_, dependencies), cleanup = hooks.effects[-1], hooks.cleanups[-1]
    assert dependencies == [True]
    # Flet cancels an effect's task on unmount only when it has a cleanup (F2), and a
    # cleanup returned by a sync setup is lost at the next render (F39).
    assert cleanup is scaffold.stop_ticks


async def test_a_tick_re_renders_the_strip_only_when_the_minute_changed(
    hooks: Hooks, page: FakePage, loops: Loops, moving_clock: Clock
) -> None:
    tick = await mounted_strip(hooks, loops)
    tick()  # at mount: the same minute as the render
    assert hooks.renders == 0
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1


async def test_a_tick_shows_the_strip_once_the_data_turns_stale(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
) -> None:
    conference.fetched_at = moving_clock.now - timedelta(
        hours=23, minutes=59, seconds=30
    )
    tick = await mounted_strip(hooks, loops)
    assert render_strip().visible is False
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1
    strip = render_strip()  # the re-render the tick asked for
    text, _, _ = strip_parts(strip)
    assert strip.visible is True
    assert text.value == "Updated 1 day ago"


async def test_use_minute_re_renders_its_component_only_when_the_minute_changes(
    hooks: Hooks, page: FakePage, loops: Loops, moving_clock: Clock
) -> None:
    """The Map's "Now:" lines keep up on the strip's loop (#100, D-175)."""
    assert scaffold.use_minute() == scaffold.current_minute()
    (setup, dependencies), cleanup = hooks.effects[-1], hooks.cleanups[-1]
    assert dependencies == []
    assert cleanup is scaffold.stop_ticks  # what makes Flet cancel it on unmount (F2)
    await setup()
    ((seconds, tick),) = loops.started
    assert seconds == scaffold.TICK_SECONDS
    tick()  # at mount: the same minute as the render
    assert hooks.renders == 0
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1
    assert hooks.state == scaffold.current_minute()


class Network:
    """Stands in for ``api.fetch_feed``: counts requests, each held until released.

    Released, it answers with an empty body, which ``feed.process`` rejects: a failed
    refresh, which is enough to end it; or it raises ``error`` when one is set.
    """

    def __init__(self) -> None:
        self.requests = 0
        self.arrived = asyncio.Event()
        self.released = asyncio.Event()
        self.error: Exception | None = None

    async def fetch_feed(self, url: str, **_: object) -> bytes:
        self.requests += 1
        self.arrived.set()
        await self.released.wait()
        if self.error is not None:
            raise self.error
        return b""


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[Network]:
    fake = Network()
    monkeypatch.setattr(api, "fetch_feed", fake.fetch_feed)
    yield fake
    fake.released.set()  # a held refresh ends with the test


async def test_on_now_and_schedule_a_tick_starts_a_refresh_when_one_is_due(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
    network: Network,
) -> None:
    tick = await mounted_strip(hooks, loops, auto_refresh=True)
    tick()  # nothing has started in this session yet
    first = conference._task
    assert first is not None
    network.released.set()
    await first
    assert network.requests == 1

    moving_clock.move(timedelta(minutes=14, seconds=59))
    tick()
    assert conference._task is first  # not yet due

    moving_clock.move(timedelta(seconds=1))  # 15 min after it began (D-40)
    tick()
    second = conference._task
    assert second is not None and second is not first
    await second
    assert network.requests == 2


async def test_elsewhere_a_tick_never_refreshes(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
) -> None:
    tick = await mounted_strip(hooks, loops)  # My schedule's strip
    tick()
    moving_clock.move(timedelta(hours=2))
    tick()
    assert conference._task is None


# No screen puts its strip in a stub body any more: Now, the Schedule and My
# schedule each check their own (test_now.py, test_schedule.py,
# test_my_schedule.py; D-40).
