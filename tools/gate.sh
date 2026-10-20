#!/usr/bin/env bash
# The merge gate (D-273): checks what will land before a merge, while the repo is private and GitHub Actions don't
# run on PRs. It merges the PRs, in the order given, onto the latest origin/main in a scratch worktree, runs the full
# local checks (tools/check.sh) there, and when they pass posts one comment on each PR naming the commits and the
# tree it checked. After the PRs are squash-merged in that order, main's tree must equal the tree printed last;
# otherwise run the full checks again on main (docs/development.md §7).
#
# Usage: tools/gate.sh <pr> [<pr>...]
# Exit status: 0 when the checks passed (and the comments were posted), 1 when they failed or the gate couldn't run
# them, 2 for a usage error. Progress goes to stderr; the gated tree's sha is the only line on stdout.
# GATE_SIGNATURE, when set, ends each comment in a paragraph of its own (agents: `_Written by <agent> (AI agent)._`).
set -euo pipefail

usage() {
    echo "Usage: tools/gate.sh <pr> [<pr>...]  (the PRs in the order they will be merged)"
}

say() {
    echo "gate.sh: $*" >&2
}

if [[ $# -eq 1 && ($1 == -h || $1 == --help) ]]; then
    usage
    exit 0
fi
if [[ $# -eq 0 ]]; then
    usage >&2
    exit 2
fi
for pr in "$@"; do
    if [[ ! $pr =~ ^[1-9][0-9]*$ ]]; then
        say "not a PR number: $pr"
        usage >&2
        exit 2
    fi
done

root=$(git rev-parse --show-toplevel)
flet_src=$root/.flet-src
if [[ ! -d $flet_src ]]; then
    say "$flet_src is missing: the checks need the Flet checkout at the pin (docs/development.md §2.2, §5.8)"
    exit 1
fi

say "fetching origin/main"
git -C "$root" fetch -q origin main
base=$(git -C "$root" rev-parse --verify origin/main)

scratch=$(mktemp -d "${TMPDIR:-/tmp}/gate.XXXXXX")
cleanup() {
    git -C "$root" worktree remove --force "$scratch" 2> /dev/null || rm -rf "$scratch"
    git -C "$root" worktree prune
}
trap cleanup EXIT
trap 'exit 1' INT TERM  # so an interrupted run still removes the scratch worktree

git -C "$root" worktree add -q --detach "$scratch" "$base"

# Its own Flet checkout, an APFS clone where cp supports it, without the wheel build folder (D-219).
say "copying .flet-src"
if ! cp -cRH "$flet_src" "$scratch/.flet-src" 2> /dev/null; then
    rm -rf "$scratch/.flet-src"
    cp -RH "$flet_src" "$scratch/.flet-src"
fi
rm -rf "$scratch/.flet-src/sdk/python/packages/flet/build"

landing="\`main\` $(git -C "$root" rev-parse --short "$base")"
for pr in "$@"; do
    say "merging #$pr"
    if ! git -C "$scratch" fetch -q origin "pull/$pr/head"; then
        say "can't fetch #$pr from origin"
        exit 1
    fi
    head=$(git -C "$scratch" rev-parse --short FETCH_HEAD)
    if ! git -C "$scratch" merge --no-ff --no-edit --no-stat FETCH_HEAD >&2; then
        say "#$pr doesn't merge cleanly onto main and the PRs before it: merge main into its branch first"
        exit 1
    fi
    landing+=" + #$pr@$head"
done
tree=$(git -C "$scratch" rev-parse "HEAD^{tree}")

# The checks run against the Flet copied above; say so when it isn't the pin of the tree that lands.
pin=$(cat "$scratch/.flet-ref")
flet_head=$(git -C "$scratch/.flet-src" rev-parse HEAD 2> /dev/null || echo unknown)
if [[ $flet_head != "$pin" ]]; then
    say "warning: .flet-src is at $flet_head, but the merged .flet-ref is $pin (docs/development.md §2.2)"
fi

if [[ ! -f $scratch/tools/check.sh ]]; then
    say "the merged tree has no tools/check.sh"
    exit 1
fi

log=$(mktemp "${TMPDIR:-/tmp}/gate-log.XXXXXX")
say "running tools/check.sh on $landing (log: $log)"
if ! (cd "$scratch" && env -u VIRTUAL_ENV -u UV_PROJECT_ENVIRONMENT tools/check.sh) > "$log" 2>&1; then
    tail -n 40 "$log" >&2
    say "the checks failed; the full log is $log"
    exit 1
fi
summary=$(grep -E '^[0-9]+ passed' "$log" | tail -n 1 || true)
rm -f "$log"
if [[ -z $summary ]]; then
    summary="passed"  # pytest -q always prints its summary line; this only keeps the comment readable
fi

body="Local checks passed (D-273): $landing → tree \`$(git -C "$scratch" rev-parse --short "$tree")\`;"
body+=" \`ruff check\`, \`ruff format --check\`, \`pyright\`, \`pytest --hypothesis-profile=ci\`: $summary."
if [[ -n ${GATE_SIGNATURE-} ]]; then
    body+=$'\n\n'"$GATE_SIGNATURE"
fi
for pr in "$@"; do
    say "commenting on #$pr"
    (cd "$root" && gh pr comment "$pr" --body "$body" > /dev/null)
done

say "passed"
echo "$tree"
