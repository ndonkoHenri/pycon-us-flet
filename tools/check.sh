#!/bin/sh
# The local checks (D-273): ci.yml's steps, in the same order, run on this machine. While the repo is private they
# replace GitHub Actions: the pre-push hook runs `tools/check.sh --fast`, agents run the full checks before marking a
# PR ready, and the merge gate (tools/gate.sh) runs them on the PRs merged onto the latest main
# (docs/development.md §7).
#
# Usage: tools/check.sh [--fast]
#   --fast  every step but pytest (what the pre-push hook runs)
# It prints one line per step, so a log shows where it stopped, and exits with the failing step's status
# (2 for a usage error).
set -eu

usage() {
    echo "Usage: tools/check.sh [--fast]"
}

fast=0
case $# in
    0) ;;
    1)
        case $1 in
            --fast) fast=1 ;;
            -h | --help) usage; exit 0 ;;
            *) usage >&2; exit 2 ;;
        esac
        ;;
    *) usage >&2; exit 2 ;;
esac

cd "$(git rev-parse --show-toplevel)"
export UV_LOCKED=1  # every uv command fails if uv.lock does not match pyproject.toml, as in ci.yml

# uv sync needs the Flet checkout at the pin until Flet 1.1.0 is on PyPI (D-81).
if [ ! -d .flet-src ]; then
    echo "check.sh: .flet-src is missing in $PWD: uv sync needs the Flet checkout at the pin (.flet-ref)." >&2
    echo "check.sh: set it up as docs/development.md §2.2 says (a worktree of this repo: §5.8)." >&2
    exit 1
fi

if [ "$fast" = 1 ]; then total=5; else total=6; fi
n=0

step() {
    n=$((n + 1))
    echo "check.sh [$n/$total] $*"
    "$@" || {
        status=$?
        echo "check.sh: failed at step $n/$total: $* (exit $status)" >&2
        exit "$status"
    }
}

step uv sync --locked -q
step uv run ruff check
step uv run ruff format --check
# The hooks of .pre-commit-config.yaml that are not commit-time only (stage `manual`, D-479): file hygiene, YAML and
# TOML syntax, actionlint and the double-backtick guard. A fixer that changes a file fails the step.
step uv run pre-commit run --all-files --hook-stage manual --show-diff-on-failure
step uv run pyright
if [ "$fast" = 0 ]; then
    step uv run pytest -q --hypothesis-profile=ci  # hypothesis's built-in profile, 200 examples via tests/conftest.py
fi
echo "check.sh: all $total steps passed"
