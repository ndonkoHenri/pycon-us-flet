#!/usr/bin/env bash
# Get this checkout ready to test and build: its own Flet checkout at the pin, the venv, its own pub cache and the
# pre-push hook (docs/development.md §5.8; D-219, D-176, D-451). Safe to run again, and after a pin bump.
#
# Usage: tools/setup_worktree.sh
# In a worktree, a .flet-src that is a link, a pre-D-451 copy (a .git file) or off the pin is replaced by a new clone of
# the main checkout's. The main checkout's own .flet-src is only ever read: if it is off the pin, this stops and says so.
set -euo pipefail

say() {
    echo "setup_worktree.sh: $*" >&2
}

root=$(git rev-parse --show-toplevel)
cd "$root"
main=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
pin=$(cat .flet-ref)

# True when .flet-src is a clone of its own at the pin, in its files too: a copy can keep a HEAD its files have left.
at_pin() {
    [[ ! -L .flet-src && -d .flet-src/.git ]] &&
        [[ $(git -C .flet-src rev-parse HEAD 2> /dev/null) == "$pin" ]] &&
        git --no-optional-locks -C .flet-src diff --quiet HEAD
}

if [[ $root == "$(cd "$main" && pwd -P)" ]]; then
    if ! at_pin; then
        say "this is the main checkout and .flet-src isn't a clone at $pin: see docs/development.md §2.2"
        exit 1
    fi
elif ! at_pin; then
    if [[ -e .flet-src || -L .flet-src ]]; then
        say "replacing .flet-src: it isn't a clone at the pin"
        rm -rf .flet-src
    fi
    if [[ ! -d $main/.flet-src/.git || -L $main/.flet-src ]]; then
        say "$main/.flet-src isn't a clone with its own .git folder: see docs/development.md §2.2"
        exit 1
    fi
    say "cloning the main checkout's .flet-src"
    cp -cR "$main/.flet-src" .flet-src
    rm -rf .flet-src/sdk/python/packages/flet/build  # the main checkout's builds left it (§5.8)
    if ! at_pin; then
        say "the main checkout's .flet-src is at $(git -C .flet-src rev-parse HEAD), not the pin $pin."
        say "Whoever merged the bump moves it (docs/development.md §2.2). Not moving it from here."
        rm -rf .flet-src
        exit 1
    fi
fi

uv sync --locked -q

# The test keeps a second run from nesting a copy inside the first (§5.8).
mkdir -p build
if [[ ! -d build/pub-cache ]]; then
    say "cloning the pub cache"
    cp -cR "$HOME/.pub-cache" build/pub-cache
fi

git config core.hooksPath .githooks

say "ready at Flet $(cut -c1-9 .flet-ref). Prefix each build, debug and test command with PUB_CACHE=$root/build/pub-cache"
