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

say "fetching origin/main"
git -C "$root" fetch -q origin main
base=$(git -C "$root" rev-parse --verify origin/main)

remove_scratch() {
    git -C "$root" worktree remove --force "$1" 2> /dev/null || rm -rf "$1"
}

# Not $TMPDIR: macOS's dirhelper sweeps it daily at 03:35, removing files older than 3 days, and uv's clones keep their
# old timestamps, so a sweep during a gate can take files from its fresh .venv and fail tests falsely.
caches=$HOME/Library/Caches

# A gate killed outright (SIGKILL, power loss) can't clean up, and nothing sweeps this folder. A gate takes minutes, so
# a scratch untouched for a day is dead; a younger one may be another gate's, running now.
while IFS= read -r -d '' dead; do
    say "removing the scratch of a dead gate: $dead"
    remove_scratch "$dead" || say "can't remove $dead"
done < <(find "$caches" -maxdepth 1 -type d -name 'gate.??????' -mmin +1440 -print0)

scratch=$(mktemp -d "$caches/gate.XXXXXX")
cleanup() {
    remove_scratch "$scratch"
    git -C "$root" worktree prune
}
trap cleanup EXIT
trap 'exit 1' INT TERM  # so an interrupted run still removes the scratch worktree

git -C "$root" worktree add -q --detach "$scratch" "$base"

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
