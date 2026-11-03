"""Tests for ``tools/setup_worktree.sh``: a worktree gets its own Flet clone at the pin (#981).

Each test runs the real script in a sandbox: a main checkout with a small ``.flet-src`` git repo,
a linked worktree of it, its own ``$HOME`` and pub cache, and a stand-in ``uv``.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "setup_worktree.sh"


def _git(cwd: Path, *args: str) -> str:
    """Run git in ``cwd`` and return its output."""
    done = subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


class Sandbox:
    """A main checkout, its worktree and the environment the script runs in."""

    def __init__(self, root: Path) -> None:
        """Build the checkouts, with ``.flet-src`` at a pin committed in ``.flet-ref``."""
        root = root.resolve()
        self.main = root / "main"
        self.main.mkdir()
        flet = self.main / ".flet-src"
        flet.mkdir()
        _git(flet, "init", "-q")
        (flet / "file").write_text("flet\n")
        _git(flet, "add", "file")
        _git(flet, "commit", "-qm", "flet")
        self.pin = _git(flet, "rev-parse", "HEAD")
        (self.main / ".flet-ref").write_text(self.pin + "\n")
        (self.main / ".gitignore").write_text(".flet-src\nbuild\n")
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
        uv.write_text('#!/bin/sh\necho "$*" >> "$UV_LOG"\n')
        uv.chmod(0o755)
        self.env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(home),
            "UV_LOG": str(self.uv_log),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }

    def run(self, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        """Run the script in ``cwd``, by default the worktree."""
        return subprocess.run(
            ["tools/setup_worktree.sh"],
            cwd=cwd or self.tree,
            check=False,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def commit_fvmrc(self, flutter: str) -> None:
        """Make the pin ask for ``flutter``, moving ``.flet-ref`` in both checkouts."""
        flet = self.main / ".flet-src"
        (flet / ".fvmrc").write_text(f'{{\n  "flutter": "{flutter}"\n}}\n')
        _git(flet, "add", ".fvmrc")
        _git(flet, "commit", "-qm", "fvmrc")
        self.pin = _git(flet, "rev-parse", "HEAD")
        (self.main / ".flet-ref").write_text(self.pin + "\n")
        (self.tree / ".flet-ref").write_text(self.pin + "\n")

    def head(self) -> str:
        """Return the HEAD of the worktree's ``.flet-src``."""
        return _git(self.tree / ".flet-src", "rev-parse", "HEAD")


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """Return a fresh sandbox."""
    return Sandbox(tmp_path)


def test_fresh_worktree_gets_everything(sandbox: Sandbox) -> None:
    """A fresh worktree ends with its own clone at the pin, the venv, a pub cache and the hook."""
    done = sandbox.run()
    assert done.returncode == 0, done.stderr
    assert sandbox.head() == sandbox.pin
    assert (sandbox.tree / ".flet-src" / ".git").is_dir()
    assert "sync --locked" in sandbox.uv_log.read_text()
    assert (sandbox.tree / "build" / "pub-cache" / "marker").exists()
    assert _git(sandbox.tree, "config", "core.hooksPath") == ".githooks"


def test_missing_flutter_of_the_pin_is_said(sandbox: Sandbox) -> None:
    """A pin whose Flutter isn't in ``~/flutter`` gets a warning, and the setup still ends well."""
    sandbox.commit_fvmrc("3.47.9")
    done = sandbox.run()
    assert done.returncode == 0, done.stderr
    assert "no ~/flutter/3.47.9" in done.stderr


def test_flutter_of_the_pin_in_home_says_nothing(sandbox: Sandbox) -> None:
    """With the pin's Flutter in ``~/flutter`` there is nothing to warn about."""
    sandbox.commit_fvmrc("3.47.9")
    flutter = Path(sandbox.env["HOME"]) / "flutter" / "3.47.9" / "bin" / "flutter"
    flutter.parent.mkdir(parents=True)
    flutter.write_text("#!/bin/sh\n")
    flutter.chmod(0o755)
    done = sandbox.run()
    assert done.returncode == 0, done.stderr
    assert "~/flutter" not in done.stderr


def test_second_run_changes_nothing(sandbox: Sandbox) -> None:
    """A second run keeps the clone and doesn't nest a pub cache in the first."""
    assert sandbox.run().returncode == 0
    keep = sandbox.tree / ".flet-src" / "kept-by-the-clone"
    keep.write_text("untracked\n")
    assert sandbox.run().returncode == 0
    assert keep.exists()
    assert not (sandbox.tree / "build" / "pub-cache" / ".pub-cache").exists()


def test_link_is_replaced_and_its_target_kept(sandbox: Sandbox) -> None:
    """A link to the main checkout's ``.flet-src`` goes; the main checkout's stays as it was."""
    (sandbox.tree / ".flet-src").symlink_to(sandbox.main / ".flet-src")
    assert sandbox.run().returncode == 0
    assert not (sandbox.tree / ".flet-src").is_symlink()
    assert (sandbox.main / ".flet-src" / "file").exists()


def test_git_file_copy_is_replaced(sandbox: Sandbox) -> None:
    """A pre-D-451 copy, whose ``.git`` is a file, is replaced without running git in it."""
    stale = sandbox.tree / ".flet-src"
    stale.mkdir()
    (stale / ".git").write_text("gitdir: /nowhere\n")
    assert sandbox.run().returncode == 0
    assert (stale / ".git").is_dir()


def test_edited_clone_is_replaced(sandbox: Sandbox) -> None:
    """A clone whose tracked files left the pin is replaced, since its HEAD alone would pass."""
    assert sandbox.run().returncode == 0
    (sandbox.tree / ".flet-src" / "file").write_text("edited\n")
    assert sandbox.run().returncode == 0
    assert (sandbox.tree / ".flet-src" / "file").read_text() == "flet\n"


def test_main_off_the_pin_stops_and_moves_nothing(sandbox: Sandbox) -> None:
    """A main checkout off the pin stops the run, leaves no clone and isn't moved."""
    flet = sandbox.main / ".flet-src"
    (flet / "file").write_text("newer\n")
    _git(flet, "commit", "-qam", "newer")
    moved = _git(flet, "rev-parse", "HEAD")
    done = sandbox.run()
    assert done.returncode == 1
    assert "not the pin" in done.stderr
    assert not (sandbox.tree / ".flet-src").exists()
    assert _git(flet, "rev-parse", "HEAD") == moved


def test_main_checkout_is_checked_not_replaced(sandbox: Sandbox) -> None:
    """In the main checkout an off-pin ``.flet-src`` stops the run and stays in place."""
    flet = sandbox.main / ".flet-src"
    (flet / "file").write_text("edited\n")
    done = sandbox.run(sandbox.main)
    assert done.returncode == 1
    assert (flet / "file").read_text() == "edited\n"
