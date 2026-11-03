"""Tests for ``tools/pr_shots.sh`` and ``tools/board.sh``, with stand-ins for ``gh`` and ``sips``."""

import os
import subprocess
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
BOARD_OPTIONS = {
    "todo": "876879f0",
    "in-progress": "921d2845",
    "in-review": "0361c618",
    "done": "40195126",
}


class Tools:
    """A ``PATH`` whose ``gh`` records its calls and whose ``sips`` does nothing."""

    def __init__(self, root: Path) -> None:
        """Write the stand-ins under ``root``."""
        self.root = root
        self.calls = root / "gh-calls"
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "sips").write_text("#!/bin/sh\nexit 0\n")
        (bin_dir / "gh").write_text(
            "#!/bin/sh\n"
            'echo "$*" >> "$GH_CALLS"\n'
            'if [ "$3" = PUT ]; then exit "${GH_PUT_STATUS:-0}"; fi\n'
            'case "$*" in\n'
            '  *"?ref=pr-assets"*) [ -n "$GH_BLOB" ] && echo "$GH_BLOB" && exit 0; exit 1 ;;\n'
            "  *html_url*) echo https://example.test/pull/5 ;;\n"
            '  *"item-add"*) echo ITEM ;;\n'
            "esac\n"
        )
        for tool in bin_dir.iterdir():
            tool.chmod(0o755)
        self.path = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"

    def run(
        self, script: str, *args: str, **env: str
    ) -> subprocess.CompletedProcess[str]:
        """Run ``tools/<script>`` with ``args`` and return what it did."""
        return subprocess.run(
            [TOOLS / script, *args],
            check=False,
            env={"PATH": self.path, "GH_CALLS": str(self.calls), **env},
            capture_output=True,
            text=True,
        )

    def called(self) -> str:
        """Return every ``gh`` call so far."""
        return self.calls.read_text() if self.calls.exists() else ""

    def image(self, name: str) -> str:
        """Write an image file called ``name`` and return its path."""
        path = self.root / name
        path.write_bytes(b"png")
        return str(path)


@pytest.fixture
def tools(tmp_path: Path) -> Tools:
    """Return fresh stand-ins."""
    return Tools(tmp_path)


def test_shots_print_the_markdown_for_each_image(tools: Tools) -> None:
    """Each uploaded image prints the line that embeds it from ``pr-assets``."""
    done = tools.run("pr_shots.sh", "5", tools.image("android-light.png"))
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == (
        "![android-light](https://github.com/ndonkoHenri/pycon-us-flet"
        "/blob/pr-assets/5/android-light.png?raw=true)"
    )
    assert "-f branch=pr-assets" in tools.called()


def test_shots_check_every_name_before_any_upload(tools: Tools) -> None:
    """A bad name among good ones uploads nothing, so no half a set is left."""
    good, bad = tools.image("good.png"), tools.image("bad name.png")
    assert tools.run("pr_shots.sh", "5", good, bad).returncode == 1
    assert tools.called() == ""


def test_shots_stop_at_the_first_failed_upload(tools: Tools) -> None:
    """A failed upload ends the run: the next image isn't tried or printed."""
    done = tools.run(
        "pr_shots.sh",
        "5",
        tools.image("a.png"),
        tools.image("b.png"),
        GH_PUT_STATUS="1",
    )
    assert done.returncode != 0
    assert done.stdout == ""
    assert "b.png" not in tools.called()


def test_shots_replace_with_the_blob_sha(tools: Tools) -> None:
    """A file that is already there is replaced by naming its current sha."""
    done = tools.run("pr_shots.sh", "5", tools.image("a.png"), GH_BLOB="abc123")
    assert done.returncode == 0, done.stderr
    assert "-f sha=abc123" in tools.called()


def test_shots_need_a_pr_and_an_image(tools: Tools) -> None:
    """Missing arguments are a usage error, before any call."""
    assert tools.run("pr_shots.sh", "5").returncode == 2
    assert tools.called() == ""


@pytest.mark.parametrize(("status", "option"), BOARD_OPTIONS.items())
def test_board_sets_the_status_by_name(tools: Tools, status: str, option: str) -> None:
    """Each status name sets its option id on the item the number resolved to."""
    done = tools.run("board.sh", "5", status)
    assert done.returncode == 0, done.stderr
    calls = tools.called()
    assert "--url https://example.test/pull/5" in calls
    assert (
        f"--id ITEM --field-id PVTSSF_lAHOBeZJHs4BmmHpzhlOeUE --single-select-option-id {option}"
        in calls
    )


def test_board_refuses_an_unknown_status(tools: Tools) -> None:
    """A status it doesn't know is a usage error, before any call."""
    assert tools.run("board.sh", "5", "doing").returncode == 2
    assert tools.called() == ""
