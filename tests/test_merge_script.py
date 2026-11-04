"""Tests for `tools/merge.sh`: a merge happens only on the gate's own success (#974).

Each test runs the real script in a sandbox, a git repo with an `origin`, beside a stand-in
`gate.sh`, with a stand-in `gh` first on `PATH` that records its calls.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

MERGE = Path(__file__).resolve().parent.parent / "tools" / "merge.sh"


def _git(cwd: Path, *args: str) -> str:
    """Run git in `cwd` with an identity of its own (a runner has none), and return its output."""
    done = subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


class Sandbox:
    """A clone with the script beside a stand-in gate, and a stand-in `gh`."""

    def __init__(self, root: Path) -> None:
        """Make the origin, the clone and the folder `gh` and its call log live in."""
        self.root = root
        self.calls = root / "gh-calls"
        self.lock = root / "lock"
        self.states = root / "states"
        origin = root / "origin.git"
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", origin], check=True
        )
        self.repo = root / "repo"
        subprocess.run(["git", "clone", "-q", origin, self.repo], check=True)
        (self.repo / "file").write_text("one\n")
        _git(self.repo, "add", "file")
        _git(self.repo, "commit", "-qm", "one")
        _git(self.repo, "push", "-q", "origin", "HEAD:main")
        (self.repo / "tools").mkdir()
        shutil.copy(MERGE, self.repo / "tools" / "merge.sh")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            'echo "$*" >> "$GH_CALLS"\n'
            'if [ "$2" = merge ]; then exit "${GH_MERGE_STATUS:-0}"; fi\n'
            'if [ "$5" = headRefOid ]; then echo head-of-$3; exit 0; fi\n'
            'cat "$GH_STATE"\n'
        )
        gh.chmod(0o755)
        self.states.write_text("MERGED\n")
        self.env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(root),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GH_CALLS": str(self.calls),
            "GH_STATE": str(self.states),
            "MERGE_LOCK": str(self.lock),
        }

    def gate(self, status: int, tree: str = "") -> None:
        """Write the stand-in gate: it prints `tree` and exits with `status`."""
        path = self.repo / "tools" / "gate.sh"
        path.write_text(f"#!/bin/sh\necho {tree}\nexit {status}\n")
        path.chmod(0o755)

    def main_tree(self) -> str:
        """Return the tree of origin's main."""
        _git(self.repo, "fetch", "-q", "origin", "main")
        return _git(self.repo, "rev-parse", "FETCH_HEAD^{tree}")

    def run(
        self, *prs: str, timeout: float = 30, **env: str
    ) -> subprocess.CompletedProcess[str]:
        """Run the script on `prs`, with `env` over the sandbox's environment."""
        return subprocess.run(
            ["tools/merge.sh", *prs],
            check=False,
            cwd=self.repo,
            env=self.env | env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def merges(self) -> list[str]:
        """Return the PRs `gh pr merge` was called on, in order."""
        if not self.calls.exists():
            return []
        return [
            line.split()[2]
            for line in self.calls.read_text().splitlines()
            if line.startswith("pr merge")
        ]


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """Return a fresh sandbox."""
    return Sandbox(tmp_path)


def test_failed_gate_merges_nothing(sandbox: Sandbox) -> None:
    """A gate that exits 1 ends the run with 1, and `gh pr merge` is never called."""
    sandbox.gate(1)
    done = sandbox.run("7")
    assert done.returncode == 1
    assert sandbox.merges() == []
    assert "nothing merged" in done.stderr


def test_passed_gate_merges_in_order(sandbox: Sandbox) -> None:
    """A gate that passes merges each PR in the order given, and the matching tree exits 0."""
    sandbox.gate(0, sandbox.main_tree())
    done = sandbox.run("7", "8")
    assert done.returncode == 0, done.stderr
    assert sandbox.merges() == ["7", "8"]


def test_state_decides_when_gh_fails_after_merging(sandbox: Sandbox) -> None:
    """`gh` failing on the local branch isn't a failure when the PR's state is MERGED."""
    sandbox.gate(0, sandbox.main_tree())
    done = sandbox.run("7", GH_MERGE_STATUS="1")
    assert done.returncode == 0, done.stderr


def test_unmerged_pr_stops_the_rest(sandbox: Sandbox) -> None:
    """A PR still open exits 3, and the PRs after it are left alone."""
    sandbox.gate(0, sandbox.main_tree())
    sandbox.states.write_text("OPEN\n")
    done = sandbox.run("7", "8", GH_MERGE_STATUS="1")
    assert done.returncode == 3
    assert sandbox.merges() == ["7"]


def test_other_tree_says_to_check_main(sandbox: Sandbox) -> None:
    """Main's tree differing from the gated tree exits 3 and names `tools/check.sh`."""
    sandbox.gate(0, "0" * 40)
    done = sandbox.run("7")
    assert done.returncode == 3
    assert "tools/check.sh" in done.stderr


def test_merge_names_the_head_read_before_the_gate(sandbox: Sandbox) -> None:
    """Each merge is tied to its PR's head, so a later push can't land ungated."""
    sandbox.gate(0, sandbox.main_tree())
    assert sandbox.run("7").returncode == 0
    assert "--match-head-commit head-of-7" in sandbox.calls.read_text()


def test_gate_with_no_tree_merges_nothing(sandbox: Sandbox) -> None:
    """A gate that exits 0 but names no tree isn't a pass."""
    sandbox.gate(0)
    assert sandbox.run("7").returncode == 1
    assert sandbox.merges() == []


def test_bad_pr_number_is_a_usage_error(sandbox: Sandbox) -> None:
    """A PR that isn't a number exits 2 before the lock and the gate."""
    sandbox.gate(0, sandbox.main_tree())
    assert sandbox.run("foo").returncode == 2
    assert not sandbox.lock.is_symlink()


def test_dead_runs_lock_is_taken(sandbox: Sandbox) -> None:
    """A lock left by a process that is gone doesn't block, and the run removes its own."""
    dead = subprocess.Popen(["true"])
    dead.wait()
    sandbox.lock.symlink_to(str(dead.pid))
    sandbox.gate(1)
    done = sandbox.run("7")
    assert "dead run" in done.stderr
    assert done.returncode == 1
    assert not sandbox.lock.is_symlink()


def test_live_holder_blocks_the_gate(sandbox: Sandbox) -> None:
    """A lock whose holder is alive makes the run wait, without gating or merging."""
    holder = subprocess.Popen(["sleep", "30"])
    try:
        sandbox.lock.symlink_to(str(holder.pid))
        sandbox.gate(0, sandbox.main_tree())
        with pytest.raises(subprocess.TimeoutExpired):
            sandbox.run("7", timeout=2)
        assert sandbox.merges() == []
        assert sandbox.lock.is_symlink()
    finally:
        holder.kill()
        holder.wait()


def test_exit_leaves_another_runs_lock(sandbox: Sandbox) -> None:
    """A run removes only its own lock: one now holding another pid stays."""
    path = sandbox.repo / "tools" / "gate.sh"
    path.write_text(f'#!/bin/sh\nln -sfn 1 "{sandbox.lock}"\nexit 1\n')
    path.chmod(0o755)
    assert sandbox.run("7").returncode == 1
    assert sandbox.lock.is_symlink()


def test_no_arguments_is_a_usage_error(sandbox: Sandbox) -> None:
    """No PR exits 2, as the gate does, before taking the lock."""
    assert sandbox.run().returncode == 2
    assert not sandbox.lock.is_symlink()
