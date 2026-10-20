"""Tests for the keynotes' year data and its checks (``year_keynotes.py``; #104, D-217).

SESS-08, SPKR-04: the keynotes and panels are ``content.toml`` entries keyed by the
feed's session id, and the loader refuses one the year's snapshot lacks. The other
loader rules are in ``tests/test_config.py``; the snapshot tool's check in
``tests/test_update_snapshot.py``.
"""

import re
import shutil
from pathlib import Path

import pytest

from pycon_us import config
from pycon_us.config import YearDataError, load_year
from pycon_us.core.timeline import track_sessions
from pycon_us.year_keynotes import Keynote, check_keynote_sessions, keynote_of
from pycon_us.year_tracks import HUB_PAGES, KEYNOTE_TRACKS
from tests.feeds import processed

PACKAGE = Path(config.__file__).parent

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the bundled year data."""
    shutil.copytree(config.DATA_DIR, tmp_path, dirs_exist_ok=True)
    return tmp_path


def edit(path: Path, old: str, new: str) -> None:
    """Replace the first ``old`` in ``path`` with ``new``; ``old`` must be there."""
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


@pytest.mark.parametrize("year", YEARS)
def test_every_years_keynotes_name_sessions_of_its_snapshot(year: int) -> None:
    """D-217: the year data and the feed it ships with are checked together."""
    load_year(year, check_sessions=True)


def test_2026_has_its_four_keynotes_and_two_panels() -> None:
    """2026 has four keynotes and two panels, covering the feed's keynotes."""
    keynotes = load_year(2026).content.keynotes
    assert [(k.session_id, k.kind) for k in keynotes] == [
        ("153", "keynote"),
        ("164", "panel"),
        ("165", "keynote"),
        ("176", "keynote"),
        ("182", "keynote"),
        ("183", "panel"),
    ]
    # Every keynote of the feed has its people, so no card shows a bare name.
    feed_keynotes = {
        s.id for day in track_sessions(processed(2026), "Keynote") for s in day.sessions
    }
    assert feed_keynotes <= {k.session_id for k in keynotes}
    together = keynote_of(keynotes, "182")
    assert together is not None
    assert [p.name for p in together.speakers] == ["Rachell Calhoun", "Tim Schilling"]


def test_2026_keynote_people_have_a_role_and_a_small_photo() -> None:
    """The site's 165 px copies: its originals weigh up to 5.7 MB (D-217)."""
    for keynote in load_year(2026).content.keynotes:
        for person in keynote.speakers:
            assert person.role
            assert re.search(r"\.max-165x165\.(jpg|png)$", person.photo_url), person


def test_the_copy_is_in_the_apps_voice() -> None:
    """ux.md §4.9: US English, no exclamation marks."""
    keynotes = load_year(2026).content.keynotes
    words = [k.title for k in keynotes] + [k.abstract for k in keynotes]
    words += [p.bio for k in keynotes for p in k.speakers]
    assert not any("!" in text for text in words)
    assert not any(re.search(r"organis|specialis|programme", t) for t in words)


def test_a_year_may_have_no_keynotes() -> None:
    """2025 keeps only what its recorded feed needs; any session has no entry."""
    content = load_year(2025).content
    assert content.keynotes == ()
    assert keynote_of(content.keynotes, "49") is None


def test_no_keynote_text_is_left_in_code() -> None:
    """SESS-08: one data source, not Ionic's two copies matched by substring."""
    names = {p.name for k in load_year(2026).content.keynotes for p in k.speakers} | {
        k.title for k in load_year(2026).content.keynotes if k.title
    }
    for module in PACKAGE.rglob("*.py"):
        code = module.read_text(encoding="utf-8")
        found = [name for name in names if name in code]
        assert not found, f"{module.relative_to(PACKAGE)}: {found}"


# ------------------------------------------------------------------ the loader's rules


def test_the_loader_refuses_a_session_id_the_snapshot_lacks(data_dir: Path) -> None:
    """A keynote's session id the snapshot lacks is refused, naming the entry."""
    edit(data_dir / "2026" / "content.toml", 'session_id = "153"', 'session_id = "999"')
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir, check_sessions=True)
    assert str(error.value) == (
        "2026/content.toml: keynotes[0].session_id: '999' is not a session of the "
        "year's feed"
    )


def test_the_loader_refuses_a_session_id_of_another_track(data_dir: Path) -> None:
    """A keynote's session id on the Talk track is refused, naming the track.

    A typo that lands on a talk would put it on the Keynotes page, its speakers replaced
    by the year data's people on its detail.
    """
    edit(data_dir / "2026" / "content.toml", 'session_id = "153"', 'session_id = "142"')
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir, check_sessions=True)
    assert str(error.value) == (
        "2026/content.toml: keynotes[0].session_id: '142' is a Talk session, not a "
        "keynote or a plenary"
    )


def test_the_keynote_tracks_include_the_hubs_keynotes_page() -> None:
    """The Tracks hub's Keynotes page is one of the keynote tracks."""
    assert HUB_PAGES["keynotes"] in KEYNOTE_TRACKS


def test_the_app_loads_without_reading_the_snapshot(data_dir: Path) -> None:
    """Without the session check, the year loads with no snapshot and an unknown id.

    D-38: the app never parses the snapshot to start; a keynote a newer feed drops just
    has no card.
    """
    edit(data_dir / "2026" / "content.toml", 'session_id = "153"', 'session_id = "999"')
    (data_dir / "2026" / "conference.json").unlink()
    assert load_year(2026, data_dir).content.keynotes[0].session_id == "999"


def test_keynotes_without_a_snapshot_to_check_them_are_refused(
    data_dir: Path,
) -> None:
    """The session check refuses keynotes when the year has no snapshot."""
    (data_dir / "2026" / "conference.json").unlink()
    with pytest.raises(YearDataError, match=r"^2026/conference\.json: file not found$"):
        load_year(2026, data_dir, check_sessions=True)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'session_id = "164"',
            'session_id = "153"',
            "2026/content.toml: keynotes[1].session_id: duplicate session '153'",
        ),
        (
            'kind = "panel"',
            'kind = "workshop"',
            (
                "2026/content.toml: keynotes[1].kind: 'workshop' is not one of "
                "('keynote', 'panel')"
            ),
        ),
        (
            'role = "CEO and co-founder, Fireworks AI"',
            'role = " "',
            "2026/content.toml: keynotes[0].speakers[0].role: is empty",
        ),
        (
            (
                'photo_url = "https://pycon-assets.s3.amazonaws.com/2026/media/images/'
                "lin_qiao"
            ),
            (
                'photo_url = "http://pycon-assets.s3.amazonaws.com/2026/media/images/'
                "lin_qiao"
            ),
            (
                "2026/content.toml: keynotes[0].speakers[0].photo_url: expected an "
                "https:// URL with a host"
            ),
        ),
        (
            'name = "Lin Qiao"',
            'name = "Lin Qiao"\nphoto = "lin.jpg"',
            "2026/content.toml: keynotes[0].speakers[0].photo: unknown key",
        ),
        (
            'session_id = "153"',
            "session_id = 153",
            "2026/content.toml: keynotes[0].session_id: expected a string, got 153",
        ),
    ],
)
def test_a_broken_keynote_names_its_entry_and_the_problem(
    data_dir: Path, old: str, new: str, message: str
) -> None:
    """A broken keynote entry is refused with its path and the problem."""
    edit(data_dir / "2026" / "content.toml", old, new)
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value) == message


def test_a_keynote_needs_someone_on_stage(data_dir: Path) -> None:
    """A keynote with an empty speakers list is refused."""
    file = data_dir / "2026" / "content.toml"
    text = file.read_text(encoding="utf-8")
    head = text.split("[[keynotes]]")[0]
    file.write_text(
        head + '[[keynotes]]\nsession_id = "153"\nkind = "keynote"\nspeakers = []\n',
        encoding="utf-8",
    )
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value) == "2026/content.toml: keynotes[0].speakers: is empty"


def test_the_session_check_takes_any_feed() -> None:
    """The snapshot tool checks a new feed with it before writing (D-217)."""
    sessions = processed(2026).sessions
    keynote = Keynote("153", "keynote", ())
    check_keynote_sessions((keynote,), sessions, {"Keynote"}, "x.toml")
    others = {k: s for k, s in sessions.items() if k != "153"}
    with pytest.raises(YearDataError, match=r"^x\.toml: keynotes\[0\]\.session_id"):
        check_keynote_sessions((keynote,), others, {"Keynote"}, "x.toml")
    with pytest.raises(YearDataError, match=r"is a Keynote session"):
        check_keynote_sessions((keynote,), sessions, {"Plenary"}, "x.toml")
