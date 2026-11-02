"""A 2027 made from 2026's data, for the tests of what a rollover does (D-45, #842).

``copy_forward()`` copies ``data/2026`` to a temporary folder twice, as itself and as a
2027 with its May dates and year URLs moved on. The session ids stay the same, which is
D-48's hard case: a 2026 id then names a real 2027 session.
"""

import shutil
from datetime import date
from pathlib import Path

from pycon_us import config

DATES = ("2026-05-", "2027-05-")
"""The dates a year's files hold, as they read in each year."""


def _rewrite(path: Path, *replacements: tuple[str, str]) -> None:
    """Rewrite the file at ``path`` with each pair replaced."""
    text = path.read_text(encoding="utf-8")
    for old, new in replacements:
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def copy_forward(tmp_path: Path, checked: date | None = None) -> Path:
    """Copy 2026 to ``tmp_path`` as 2026 and as a 2027 with its dates a year on.

    Args:
        tmp_path: Where the year folders go.
        checked: The 2027 contacts' check date; None keeps 2026's, as a rollover
            that forgot the check would.

    Returns:
        ``tmp_path``, the ``data_dir`` for ``load_year()``.
    """
    shutil.copytree(config.DATA_DIR / "2026", tmp_path / "2026")
    folder = tmp_path / "2027"
    shutil.copytree(config.DATA_DIR / "2026", folder)
    _rewrite(
        folder / "conference.toml",
        ("year = 2026", "year = 2027"),
        DATES,
        ("/2026/", "/2027/"),
    )
    # The hand-written moments (D-274) and the venue hours (D-282) must fall in their
    # year, so they move with it; so must the snapshot's sessions.
    _rewrite(folder / "content.toml", DATES)
    if checked is not None:
        _rewrite(
            folder / "content.toml",
            ("checked = 2026-10-20", f"checked = {checked.isoformat()}"),
        )
    _rewrite(folder / "conference.json", DATES)
    return tmp_path
