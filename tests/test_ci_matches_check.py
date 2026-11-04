"""`ci.yml` and `tools/check.sh` run the same checks in the same order (D-273, D-480, D-482).

The merge gate and the pre-push hook run `check.sh`, and CI runs `ci.yml`, so a step that one has and the other lacks
would let a change pass on one and fail on the other.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `-q` is the one difference: check.sh keeps its log short, and a CI log has room.
QUIET = re.compile(r" -q\b")
TRAILING_COMMENT = re.compile(r"\s+#.*$")


def _commands(path: str, prefix: str) -> list[str]:
    """Return the file's `prefix` lines' commands, in order; each must be one `uv` line.

    A `run: |` block or a command that isn't `uv` fails here, rather than go uncompared.
    """
    commands = []
    for line in (ROOT / path).read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{prefix} "):
            command = TRAILING_COMMENT.sub("", stripped.removeprefix(f"{prefix} "))
            assert command.startswith("uv "), f"{path}: not a uv line: {stripped}"
            commands.append(QUIET.sub("", command))
    return commands


def test_ci_runs_the_steps_of_check_sh_in_order() -> None:
    """Every check in `check.sh` is a step of `ci.yml`, in the same order, and no more."""
    assert _commands(".github/workflows/ci.yml", "run:") == _commands(
        "tools/check.sh", "step"
    )


def test_ci_runs_the_hooks_check_sh_runs() -> None:
    """The pre-commit hooks are one of those steps, on every file, in stage `manual`."""
    hooks = [
        command
        for command in _commands("tools/check.sh", "step")
        if "pre-commit run" in command
    ]
    assert len(hooks) == 1
    assert "--all-files --hook-stage manual" in hooks[0]
