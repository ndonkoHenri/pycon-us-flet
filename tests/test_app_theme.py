"""Tests for the app's theme mode, its services and the boot gate's slots layout.

The fakes are ``tests/app_start.py``'s (D-69, D-147).
"""

import asyncio
import inspect
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us import app
from pycon_us.accessibility import read_accessibility
from pycon_us.app import apply_theme
from pycon_us.layout import Layout
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.services import Services
from pycon_us.ui.time_gutter import GutterProbe
from tests import app_start
from tests.fake_page import FakePage, bound
from tests.fakes import MemorySemantics

semantics, fake_page = (app_start.semantics, app_start.fake_page)


# ------------------------------------------------------------------ theme and services


@pytest.mark.parametrize(
    ("theme", "mode"),
    [
        ("system", ft.ThemeMode.SYSTEM),
        ("light", ft.ThemeMode.LIGHT),
        ("dark", ft.ThemeMode.DARK),
    ],
)
def test_the_theme_mode_follows_the_appearance_setting(
    theme: str, mode: ft.ThemeMode, fake_page: FakePage
) -> None:
    """Each Appearance setting gives its theme mode, over two distinct schemes."""
    apply_theme(cast(ft.Page, fake_page), Prefs(theme=theme))  # type: ignore[arg-type]
    assert fake_page.theme_mode == mode
    assert fake_page.theme is not None and fake_page.dark_theme is not None
    assert fake_page.theme.color_scheme != fake_page.dark_theme.color_scheme


async def test_read_accessibility_counts_either_motion_flag(
    semantics: MemorySemantics,
) -> None:
    """The ``reduce_motion`` flag alone, which iOS reports, turns reduced motion on."""
    prefs = Prefs()
    semantics.features["reduce_motion"] = True  # iOS reports this one (F13)
    await read_accessibility(semantics, prefs)
    assert prefs.reduce_motion


def test_services_are_built_for_the_active_year_in_the_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Services.create`` uses the active year, the data directory and the memory.

    The new services start open, and ``close()`` closes them.
    """
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    memory = ViewMemory()
    svc = Services.create(memory)
    assert svc.storage.directory == tmp_path.absolute()
    assert svc.storage.year == svc.year.conference.year
    assert svc.memory is memory
    assert not svc.closed.is_set()
    svc.close()
    assert svc.closed.is_set()


@pytest.mark.parametrize(
    ("loaded", "measured", "open_"),
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, True),
    ],
)
def test_the_boot_gate_waits_for_the_settings_and_the_slots_layout(
    loaded: bool,
    measured: bool,
    open_: bool,
    fake_page: FakePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boot view stays until the settings load and the slots' layout is measured.

    D-216: the first screen comes only once the slots' layout is known.
    """
    prefs = Prefs(loaded=loaded, time_measured=measured)
    monkeypatch.setattr(ft, "use_memo", lambda *_, **__: object())
    monkeypatch.setattr(ft, "use_state", lambda initial: (prefs, lambda _: None))
    monkeypatch.setattr(ft, "use_effect", lambda *_, **__: None)
    banners: list[bool] = []
    monkeypatch.setattr(
        app, "use_reminder_banner", lambda *_, ready: banners.append(ready)
    )
    # The Review SnackBar has its own tests (tests/test_changes_review.py).
    monkeypatch.setattr(app, "use_review_snack_bar", lambda *_: None)
    monkeypatch.setattr(app, "use_reminder_schedule", lambda *_: None)
    with Renderer().with_context(), bound(fake_page):
        shown = inspect.unwrap(app.App)(ViewMemory())
    assert banners == [open_]  # the slot is there before the gate, shown after it
    booting = (
        isinstance(shown, list)
        and len(shown) == 1
        and isinstance(shown[0], ft.Component)
        and shown[0].fn is inspect.unwrap(app.BootView)
    )
    assert booting is not open_
    if open_:  # the providers end in the Router
        assert isinstance(shown, ft.Component)
        assert shown.fn.__name__ == "Router"


def test_app_seeds_the_layout_from_the_page_width_and_follows_its_resizes(
    fake_page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``App`` gives the Router a ``Layout`` seeded from ``page.width`` that follows resizes.

    D-277: a first screen opened in landscape shows the rail, and a rotation flips it.
    """
    fake_page.width = 900.0
    prefs = Prefs(loaded=True, time_measured=True)
    setups: list[Callable[[], object]] = []
    provided: list[Layout] = []

    def layout_ctx(value: Layout, body: Callable[[], object]) -> object:
        """Record the ``Layout`` handed to the provider, then render its body."""
        provided.append(value)
        return body()

    monkeypatch.setattr(ft, "use_memo", lambda fn, *_, **__: fn())
    monkeypatch.setattr(ft, "use_state", lambda initial: (prefs, lambda _: None))
    monkeypatch.setattr(ft, "use_effect", lambda setup, *_, **__: setups.append(setup))
    monkeypatch.setattr(app, "LayoutCtx", layout_ctx)
    monkeypatch.setattr(app, "apply_theme", lambda *_: None)
    # The reminder Banner has its own tests; here it would read stand-in stores.
    monkeypatch.setattr(app, "use_reminder_banner", lambda *_, **__: None)
    monkeypatch.setattr(app, "use_review_snack_bar", lambda *_: None)
    monkeypatch.setattr(app, "use_reminder_schedule", lambda *_: None)
    monkeypatch.setattr(app, "Services", SimpleNamespace(create=lambda *_: object()))
    with Renderer().with_context(), bound(fake_page):
        shown = inspect.unwrap(app.App)(ViewMemory())
        assert isinstance(shown, ft.Component) and shown.fn.__name__ == "Router"
        (layout,) = provided  # LayoutCtx is in the chain to the Router
        assert layout.wide is True  # seeded before any effect runs
        for setup in setups:
            if not inspect.iscoroutinefunction(setup):
                setup()
        assert fake_page.on_resize is not None
        fake_page.on_resize(SimpleNamespace(width=375.0))
        assert layout.wide is False


async def test_the_boot_view_measures_the_slots_layout_before_the_first_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boot view holds the layout probe and stops waiting for it after a delay.

    D-216: a Schedule opened with the gutter and switched later lost its jump.
    """
    prefs, setups = Prefs(), []
    monkeypatch.setattr(app, "use_prefs", lambda: prefs)
    monkeypatch.setattr(ft, "use_state", lambda initial: (initial, lambda _: None))
    monkeypatch.setattr(ft, "use_effect", lambda setup, *_, **__: setups.append(setup))
    monkeypatch.setattr(app, "RING_DELAY", 0.01)
    with Renderer().with_context():  # what calling a component needs, as in a render
        view = inspect.unwrap(app.BootView)()
    assert isinstance(view, ft.View)
    ring, probe = view.controls
    assert isinstance(ring, ft.ProgressRing)
    assert isinstance(probe, ft.Component)
    assert probe.fn is inspect.unwrap(GutterProbe)
    assert view.spacing == 0  # the 0 dp probe leaves the ring centred
    # Should the probe never answer, the gate stops waiting with the ring.
    (setup,) = setups
    setup()
    assert prefs.time_measured is False
    await asyncio.sleep(0.05)
    assert prefs.time_measured is True
    assert prefs.time_above is False  # the gutter, until a screen's probe answers
