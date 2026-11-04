#!/usr/bin/env bash
# Get this checkout ready to test and build: the venv, its own pub cache and the pre-push hook
# (docs/development.md §5.8; D-176). Safe to run again, and after a Flet bump.
#
# Usage: tools/setup_worktree.sh
set -euo pipefail

say() {
    echo "setup_worktree.sh: $*" >&2
}

cd "$(git rev-parse --show-toplevel)"

uv sync --locked -q

# The test keeps a second run from nesting a copy inside the first (§5.8).
mkdir -p build
if [[ ! -d build/pub-cache ]]; then
    say "cloning the pub cache"
    if ! cp -cR "$HOME/.pub-cache" build/pub-cache 2> /dev/null; then  # -c is APFS's; Linux's cp has none
        rm -rf build/pub-cache
        cp -R "$HOME/.pub-cache" build/pub-cache
    fi
fi

git config core.hooksPath .githooks

# Without Flet's exact Flutter in ~/flutter, flet-cli quietly takes any of its minor on PATH (#1006).
read -r flet flutter < <(uv run --locked python -c 'from flet import version as v; print(v.flet_version, v.flutter_version)')
if [[ ! -x $HOME/flutter/$flutter/bin/flutter ]]; then
    say "no ~/flutter/$flutter, so builds may use another Flutter: see docs/development.md §2.2"
fi

say "ready at Flet $flet. Prefix each build, debug and test command with PUB_CACHE=$PWD/build/pub-cache"
