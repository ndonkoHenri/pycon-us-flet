"""Tests for the Licences page and its texts (`licences.py`, `screens/licences.py`).

#442 (INFO-03, D-296). The coverage test reads `uv.lock`: every package a phone build
bundles has a row (D-75). The screens run in a real Flet session (`tests/sessions.py`);
how they look, wrap at 200 % and read to screen readers is checked on devices (the PR).
"""

import tomllib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from packaging.markers import Marker

from pycon_us import licences
from pycon_us.config import load_year
from pycon_us.licences import COMPONENTS, GROUPS, TEXTS_DIR, Paragraph, paragraphs
from pycon_us.routes import ROUTES
from pycon_us.screens import licences as screen
from pycon_us.state import Conference
from tests.harness import Shown, showing

ROOT = Path(__file__).parent.parent

PHONES = (
    {"sys_platform": "android", "platform_system": "Android", "python_version": "3.14"},
    {"sys_platform": "ios", "platform_system": "iOS", "python_version": "3.14"},
)
"""The marker environments of the phones' builds: CPython 3.14 (D-82)."""


def runtime_packages(lock: dict[str, Any]) -> set[str]:
    """Return what a phone build bundles: the app's dependencies and theirs, not dev's.

    Walks `uv.lock` from the `pycon-us` package's own dependencies (dev groups are
    elsewhere in the lock), keeping an edge when its marker holds on either phone.
    """
    packages = {p["name"]: p for p in lock["package"]}
    found: set[str] = set()
    todo = ["pycon-us"]
    while todo:
        for dep in packages[todo.pop()].get("dependencies", []):
            marker = dep.get("marker")
            if marker and not any(Marker(marker).evaluate(env) for env in PHONES):
                continue
            if dep["name"] not in found:
                found.add(dep["name"])
                todo.append(dep["name"])
    return found


def missing_rows(lock: dict[str, Any]) -> set[str]:
    """Return the bundled packages that have no row on the page."""
    listed = {c.package for c in COMPONENTS.values() if c.package}
    return runtime_packages(lock) - listed


def read_lock() -> dict[str, Any]:
    """The repository's `uv.lock`, parsed."""
    return tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))


def test_every_bundled_package_has_a_row() -> None:
    """Each package of the phone builds' closure in `uv.lock` is listed (D-75)."""
    bundled = runtime_packages(read_lock())
    assert {"flet", "tzdata", "httpx", "msgpack"} <= bundled  # the walk reaches them
    assert "pytest" not in bundled and "ruff" not in bundled  # dev only
    assert missing_rows(read_lock()) == set()


def test_a_dependency_with_no_row_fails_the_coverage_test() -> None:
    """A new runtime dependency in the lock, with no row, is reported by name."""
    lock = read_lock()
    for package in lock["package"]:
        if package["name"] == "tzdata":
            package["dependencies"] = [{"name": "leftpad"}]
    lock["package"].append({"name": "leftpad", "version": "1.0"})
    assert missing_rows(lock) == {"leftpad"}


def test_a_dependency_only_off_the_phones_needs_no_row() -> None:
    """An edge whose marker holds on neither phone (Emscripten's) bundles nothing."""
    lock = read_lock()
    for package in lock["package"]:
        if package["name"] == "tzdata":
            package["dependencies"] = [
                {"name": "leftpad", "marker": "sys_platform == 'emscripten'"}
            ]
    lock["package"].append({"name": "leftpad", "version": "1.0"})
    assert missing_rows(lock) == set()


def test_every_text_opens_and_every_bundled_file_is_used() -> None:
    """Each component's file is there and holds text; no file is left unlisted."""
    used = {c.text for c in COMPONENTS.values()}
    on_disk = {p.name for p in TEXTS_DIR.iterdir()}
    assert used == on_disk
    for component in COMPONENTS.values():
        assert licences.read_text(component).strip(), component.key


def test_the_bundled_notice_and_apache_texts_match_their_sources() -> None:
    """The page's NOTICE is the repository's, and its Apache text Roboto's own (D-87)."""
    assert (TEXTS_DIR / "notice.txt").read_bytes() == (ROOT / "NOTICE").read_bytes()
    roboto = ROOT / "flutter_packages" / "roboto_fonts" / "LICENSE"
    assert (TEXTS_DIR / licences.APACHE).read_bytes() == roboto.read_bytes()


def test_the_simple_icons_row_says_what_the_notice_says_of_cc0() -> None:
    """The row and `NOTICE`, on one page, both say CC0 doesn't reach every icon (#846)."""
    row = COMPONENTS["simple-icons"].copyright
    notice = " ".join((ROOT / "NOTICE").read_text().split())
    assert "public domain" not in row
    assert "mean every icon in it is" in row
    assert "mean every icon in it is" in notice


def test_the_app_and_its_notice_come_first() -> None:
    """The list opens with the app's licence, then its `NOTICE` (#442)."""
    assert list(COMPONENTS)[:2] == ["app", "notice"]
    assert GROUPS[0].components == (licences.APP, licences.NOTICE)
    assert licences.APP.licence == "Apache-2.0"  # the Ionic app's licence (D-87)


def test_keys_are_unique_url_segments() -> None:
    """Each key is one lowercase segment, used once: the text's location and id."""
    keys = [c.key for group in GROUPS for c in group.components]
    assert len(keys) == len(set(keys))
    for key in keys:
        assert key.replace("-", "").isalnum() and key == key.lower(), key


# ------------------------------------------------------------------ paragraphs


def test_hand_wrapped_lines_join_into_one_paragraph() -> None:
    """A paragraph wrapped near 80 columns becomes one line, indent and double spaces gone."""
    text = (
        "   Licensed under the Apache License,\n   Version 2.0.  You may\nnot use it.\n"
    )
    assert paragraphs(text) == [
        Paragraph("Licensed under the Apache License, Version 2.0. You may not use it.")
    ]


def test_blank_lines_separate_paragraphs() -> None:
    """Blocks between blank lines stay apart."""
    assert paragraphs("One\nline.\n\n  \nTwo.") == [
        Paragraph("One line."),
        Paragraph("Two."),
    ]


def test_list_items_and_copyright_lines_keep_lines_of_their_own() -> None:
    """A list item or a copyright line starts its own line; its wrap still joins."""
    text = (
        "Copyright (c) 2020, A\nCopyright (c) 2026, B\n\n"
        "1. the right to\n   reproduce;\n2. moral rights;\n(a) You must\n* a bullet"
    )
    assert paragraphs(text) == [
        Paragraph("Copyright (c) 2020, A\nCopyright (c) 2026, B"),
        Paragraph(
            "1. the right to reproduce;\n2. moral rights;\n(a) You must\n* a bullet"
        ),
    ]


def test_columns_and_underlined_headings_keep_their_layout() -> None:
    """A table or a heading over a rule is kept line for line, and marked fixed."""
    table = "    Release         Year\n    0.9.0           1991"
    heading = "A. HISTORY\n=========="
    assert paragraphs(f"{heading}\n\n{table}") == [
        Paragraph(heading, fixed=True),
        Paragraph(table, fixed=True),
    ]


def test_every_bundled_text_keeps_all_its_words() -> None:
    """Reflowing drops whitespace only: every word of every text is still there."""
    for component in COMPONENTS.values():
        text = licences.read_text(component)
        shown = " ".join(p.text for p in paragraphs(text))
        assert shown.split() == text.split(), component.key


# ------------------------------------------------------------------ screens

type Show = Callable[[Callable[[], ft.Control], str], Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders one of the screens at its View path."""
    async with AsyncExitStack() as stack:

        async def render(component: Callable[[], ft.Control], view_path: str) -> Shown:
            """Render `component` as the View at `view_path`."""
            return await stack.enter_async_context(
                showing(
                    component,
                    screen,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=view_path,
                )
            )

        yield render


async def test_the_list_shows_each_section_and_each_component(show: Show) -> None:
    """The sections are level-2 headings; each row says its name, licence, copyright."""
    page = await show(screen.Licences, screen.LOCATION)
    assert page.titles == ["Licences"]
    headings = [n for n in page.find(ft.Semantics) if n.header]
    assert sorted(cast(Any, n).heading_level for n in headings) == [2] * len(GROUPS)
    for component in COMPONENTS.values():
        node = page.node(f"licences.{component.key}")
        tile = cast(ft.ListTile, node.content)
        assert tile.title == component.name
        assert tile.subtitle == f"{component.licence}\n{component.copyright}"


async def test_a_row_opens_its_text_below_the_list(show: Show) -> None:
    """A tap pushes `/more/app/licences/<key>`, so Back returns to the list."""
    page = await show(screen.Licences, screen.LOCATION)
    await page.click(cast(ft.Control, page.node("licences.flet").content))
    assert page.went == ["/more/app/licences/flet"]


def text_page(key: str) -> Callable[[], ft.Control]:
    """The text page for `key`, as its route renders it."""
    return lambda: screen.LicenceText(licence=key)


async def test_a_text_shows_its_licence_then_its_selectable_paragraphs(
    show: Show,
) -> None:
    """The page opens on the licence and copyright, then every block, selectable."""
    component = COMPONENTS["httpx"]
    page = await show(
        text_page("httpx"),
        screen.licence_href(component),
    )
    assert page.titles == ["HTTPX"]
    header = page.node("licence.header")
    assert header.container
    blocks = [t for t in page.find(ft.Text) if t.selectable]
    expected = paragraphs(licences.read_text(component))
    assert sorted(str(t.value) for t in blocks) == sorted(p.text for p in expected)
    texts = page.texts()
    assert "BSD-3-Clause" in texts and component.copyright in texts


async def test_a_table_shows_in_a_monospace_font(show: Show) -> None:
    """Python's table of releases keeps its columns: monospace, unwrapped, scrolling sideways."""
    page = await show(
        text_page("python"),
        "/more/app/licences/python",
    )
    fixed = [t for t in page.find(ft.Text) if t.style is screen.FIXED_STYLE]
    assert any("Release" in str(t.value) for t in fixed)
    assert all(t.selectable and t.no_wrap for t in fixed)
    rows = [r for r in page.find(ft.Row) if r.controls and r.controls[0] in fixed]
    assert rows and all(r.scroll is ft.ScrollMode.AUTO for r in rows)  # sideways


async def test_an_unknown_key_says_so_and_offers_the_list(show: Show) -> None:
    """A key the app doesn't have shows the not-found state, whose button lists all."""
    page = await show(text_page("nope"), "/more/app/licences/nope")
    assert page.titles == ["Not found"]
    assert screen.NOT_FOUND in page.texts()
    assert page.nodes("licence.not_found")


async def test_the_route_opens_the_text_its_location_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real Router at `/more/app/licences/python` shows Python's text.

    The route's param reaches the screen: a `key=` prop would be taken by Flet as
    the component's own key, and the text would never render.
    """
    async with showing(
        lambda: ft.Router(ROUTES, manage_views=True),
        screen,
        year=load_year(2026),
        conference=Conference(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path=None,
        route="/more/app/licences/python",
    ) as page:
        await page.settle()
        assert page.titles[-1] == "Python"
        assert page.nodes("licence.header")
