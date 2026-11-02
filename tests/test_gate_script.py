"""Tests for ``tools/gate.sh``'s sweep of the scratch worktrees that dead gates left (#898).

A gate killed outright can't remove its scratch, and nothing else sweeps ``~/Library/Caches``.
Each test runs the real script in a sandbox: its own ``$HOME``, no git config, and an origin
without the PR asked for, so the gate stops after the sweep, before any check or ``gh`` call.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parent.parent / "tools" / "gate.sh"
HOUR = 3600


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """Return an environment where git and the gate see only the sandbox's ``$HOME``."""
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Gate test",
        "GIT_AUTHOR_EMAIL": "gate@example.com",
        "GIT_COMMITTER_NAME": "Gate test",
        "GIT_COMMITTER_EMAIL": "gate@example.com",
    }


@pytest.fixture
def caches(env: dict[str, str]) -> Path:
    """Return the sandbox's empty ``~/Library/Caches``, where the gate keeps its scratch."""
    path = Path(env["HOME"]) / "Library" / "Caches"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def repo(tmp_path: Path, env: dict[str, str]) -> Path:
    """Return a clone with one commit on ``main``, its origin, and a ``.flet-src`` to copy."""
    origin = tmp_path / "origin.git"
    path = tmp_path / "repo"
    git(tmp_path, env, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, env, "clone", "-q", str(origin), str(path))
    git(path, env, "commit", "-q", "--allow-empty", "-m", "First")
    git(path, env, "push", "-q", "origin", "HEAD:main")
    (path / ".flet-src").mkdir()
    return path


def git(cwd: Path, env: dict[str, str], *args: str) -> str:
    """Run git in ``cwd`` with the sandbox's ``env`` and return its standard output."""
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    ).stdout


def age(path: Path, seconds: int) -> None:
    """Make ``path`` look untouched for ``seconds``, as the gate judges a scratch's age."""
    then = time.time() - seconds
    os.utime(path, (then, then))


def run_gate(repo: Path, env: dict[str, str]) -> None:
    """Run the gate on a PR the origin lacks, and check that it stopped there."""
    result = subprocess.run(
        ["bash", str(GATE), "1"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert "can't fetch #1" in result.stderr, result.stderr


def test_a_worktree_a_dead_gate_left_is_removed_with_its_entry(
    repo: Path, caches: Path, env: dict[str, str]
) -> None:
    """A scratch untouched for over a day goes, and the clone forgets its worktree."""
    dead = caches / "gate.abc123"
    git(repo, env, "worktree", "add", "-q", "--detach", str(dead), "HEAD")
    age(dead, 25 * HOUR)

    run_gate(repo, env)

    assert list(caches.iterdir()) == []  # the gate's own scratch went too
    assert "gate.abc123" not in git(repo, env, "worktree", "list")


def test_a_folder_git_no_longer_knows_is_removed_too(
    repo: Path, caches: Path, env: dict[str, str]
) -> None:
    """A dead scratch that isn't a registered worktree still goes, by ``rm -rf``."""
    dead = caches / "gate.abc123"
    (dead / ".venv").mkdir(parents=True)
    age(dead, 25 * HOUR)

    run_gate(repo, env)

    assert not dead.exists()


def test_a_scratch_younger_than_a_day_stays(
    repo: Path, caches: Path, env: dict[str, str]
) -> None:
    """A younger scratch may be another gate's, running now, so it and its entry stay."""
    live = caches / "gate.abc123"
    git(repo, env, "worktree", "add", "-q", "--detach", str(live), "HEAD")
    age(live, 23 * HOUR)

    run_gate(repo, env)

    assert live.exists()
    assert "gate.abc123" in git(repo, env, "worktree", "list")


def test_another_apps_cache_folder_stays_however_old(
    repo: Path, caches: Path, env: dict[str, str]
) -> None:
    """The folder is shared with every app: only the name ``mktemp`` gives a scratch goes."""
    other = caches / "gate.io"
    other.mkdir()
    age(other, 25 * HOUR)

    run_gate(repo, env)

    assert other.exists()
