"""Tests for `tools/setup_worktree.sh`: a worktree gets its venv, pub cache and hook (D-176).

Each test runs the real script in a sandbox: a checkout with a linked worktree, its own `$HOME`
and pub cache, and a stand-in `uv` that says which Flet and Flutter the venv holds.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "setup_worktree.sh"


def _git(cwd: Path, *args: str) -> str:
    """Run git in `cwd` and return its output."""
    done = subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


class Sandbox:
    """A checkout, its worktree and the environment the script runs in."""

    def __init__(self, root: Path) -> None:
        """Build the checkouts, with a stand-in `uv` whose venv holds Flutter 3.47.9."""
        root = root.resolve()
        self.main = root / "main"
        self.main.mkdir()
        (self.main / ".gitignore").write_text("build\n")
        (self.main / "tools").mkdir()
        shutil.copy(SCRIPT, self.main / "tools" / "setup_worktree.sh")
        _git(self.main, "init", "-q")
        _git(self.main, "add", ".")
        _git(self.main, "commit", "-qm", "app")
        self.tree = root / "tree"
        _git(self.main, "worktree", "add", "-q", "--detach", str(self.tree))
        home = root / "home"
        (home / ".pub-cache").mkdir(parents=True)
        (home / ".pub-cache" / "marker").write_text("cache\n")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        self.uv_log = root / "uv-calls"
        uv = bin_dir / "uv"
        uv.write_text(
            '#!/bin/sh\necho "$*" >> "$UV_LOG"\n'
            'case "$1" in run) echo "1.1.0.dev4 3.47.9" ;; esac\n'
        )
        uv.chmod(0o755)
        self.env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(home),
            "UV_LOG": str(self.uv_log),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }

    def run(self, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        """Run the script in `cwd`, by default the worktree."""
        return subprocess.run(
            ["tools/setup_worktree.sh"],
            cwd=cwd or self.tree,
            check=False,
            env=self.env,
            capture_output=True,
            text=True,
        )


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """Return a fresh sandbox."""
    return Sandbox(tmp_path)


def test_fresh_worktree_gets_everything(sandbox: Sandbox) -> None:
    """A fresh worktree ends with the venv, a pub cache of its own and the hook."""
    done = sandbox.run()
    assert done.returncode == 0, done.stderr
    assert "sync --locked -q" in sandbox.uv_log.read_text()
    assert (sandbox.tree / "build" / "pub-cache" / "marker").is_file()
    assert _git(sandbox.tree, "config", "core.hooksPath") == ".githooks"
    assert "ready at Flet 1.1.0.dev4" in done.stderr


def test_no_flet_checkout_is_made_or_needed(sandbox: Sandbox) -> None:
    """The setup ends well with no Flet clone anywhere, and doesn't make one."""
    assert sandbox.run().returncode == 0
    assert not (sandbox.tree / ".flet-src").exists()


def test_a_flet_clone_left_behind_is_left_alone(sandbox: Sandbox) -> None:
    """An optional clone for reading Flet's source isn't touched: it's someone's own."""
    clone = sandbox.tree / ".flet-src" / "file"
    clone.parent.mkdir()
    clone.write_text("reading\n")
    assert sandbox.run().returncode == 0
    assert clone.read_text() == "reading\n"


def test_missing_flutter_is_said(sandbox: Sandbox) -> None:
    """A Flet whose Flutter isn't in `~/flutter` gets a warning, and the setup still ends well."""
    done = sandbox.run()
    assert done.returncode == 0, done.stderr
    assert "no ~/flutter/3.47.9" in done.stderr


def test_flutter_in_home_says_nothing(sandbox: Sandbox) -> None:
    """With Flet's Flutter in `~/flutter` there is nothing to warn about."""
    flutter = Path(sandbox.env["HOME"]) / "flutter" / "3.47.9" / "bin" / "flutter"
    flutter.parent.mkdir(parents=True)
    flutter.write_text("#!/bin/sh\n")
    flutter.chmod(0o755)
    done = sandbox.run()
    assert done.returncode == 0, done.stderr
    assert "~/flutter" not in done.stderr


def test_second_run_changes_nothing(sandbox: Sandbox) -> None:
    """A second run doesn't nest a pub cache in the first."""
    assert sandbox.run().returncode == 0
    done = sandbox.run()
    assert done.returncode == 0, done.stderr
    assert not (sandbox.tree / "build" / "pub-cache" / ".pub-cache").exists()


def test_main_checkout_works_too(sandbox: Sandbox) -> None:
    """The script does the same in the main checkout."""
    done = sandbox.run(sandbox.main)
    assert done.returncode == 0, done.stderr
    assert (sandbox.main / "build" / "pub-cache" / "marker").is_file()
