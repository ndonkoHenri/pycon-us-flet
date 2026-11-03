#!/usr/bin/env bash
# Gate PRs and merge them, only if the gate itself says they passed (D-100, D-273). Never write the gate and the merge
# as `tools/gate.sh <pr> | tail && gh pr merge <pr>`: the pipe's status is tail's, and that merged #868 after a failed
# gate.
#
# Usage: tools/merge.sh <pr> [<pr>...]  (the PRs in merge order; sign the gate's comments with GATE_SIGNATURE)
# Exit status: 0 all merged and main's tree is the gated tree; 1 the gate failed and nothing merged; 2 a usage error;
# 3 a merge didn't happen, or main's tree differs: run tools/check.sh on main (AGENTS.md, Reviews and merging).
set -uo pipefail

say() {
    echo "merge.sh: $*" >&2
}

if [[ $# -eq 0 || $1 == -h || $1 == --help ]]; then
    echo "Usage: tools/merge.sh <pr> [<pr>...]  (the PRs in merge order)"
    [[ $# -eq 0 ]] && exit 2
    exit 0
fi

for pr in "$@"; do
    if [[ ! $pr =~ ^[1-9][0-9]*$ ]]; then
        say "not a PR number: $pr"
        exit 2
    fi
done

# One run at a time on this Mac: a merge moves main, which voids a gate running beside it. Not in $TMPDIR, which macOS
# sweeps. The lock is a symlink to its holder's pid, since making one is atomic and carries the pid with it. A run
# killed outright can't remove its own, so a lock whose holder is gone doesn't count. The rename lets only one waiter
# take a dead lock; one that took a newer holder's lock by a late rename puts it back.
lock=${MERGE_LOCK:-$HOME/Library/Caches/pycon-merge.lock}
mkdir -p "$(dirname "$lock")"
until ln -s "$$" "$lock" 2> /dev/null; do
    holder=$(readlink "$lock" || true)
    if [[ -n $holder ]] && ! kill -0 "$holder" 2> /dev/null; then
        if mv "$lock" "$lock.$$" 2> /dev/null; then
            if [[ $(readlink "$lock.$$") == "$holder" ]]; then
                say "removed the lock of a dead run ($holder)"
                rm -f "$lock.$$"
            else
                mv "$lock.$$" "$lock"
            fi
        fi
        continue
    fi
    say "waiting for another run (${holder:-starting}; lock: $lock)"
    sleep 10
done
trap '[[ $(readlink "$lock") == "$$" ]] && rm -f "$lock"' EXIT

# Read before the gate, so a push during or after it stops the merge instead of landing ungated.
heads=()
for pr in "$@"; do
    head=$(gh pr view "$pr" --json headRefOid --jq .headRefOid)
    if [[ -z $head ]]; then
        say "can't read #$pr's head: nothing merged"
        exit 1
    fi
    heads+=("$head")
done

if ! tree=$("$(dirname "$0")/gate.sh" "$@") || [[ -z $tree ]]; then
    say "the gate failed: nothing merged"
    exit 1
fi

i=0
for pr in "$@"; do
    # The state decides, not gh's status: --delete-branch fails after the merge when the branch is checked out here.
    gh pr merge "$pr" --squash --delete-branch --match-head-commit "${heads[$i]}" ||
        say "gh pr merge $pr said no; checking its state"
    state=$(gh pr view "$pr" --json state --jq .state)
    if [[ $state != MERGED ]]; then
        say "#$pr is ${state:-unknown}, not merged (a new push needs a new gate): the PRs after it were left alone"
        exit 3
    fi
    say "#$pr merged"
    i=$((i + 1))
done

if ! git fetch -q origin main; then
    say "can't fetch main to compare its tree: run tools/check.sh on main"
    exit 3
fi
if [[ $(git rev-parse 'FETCH_HEAD^{tree}') != "$tree" ]]; then
    say "main's tree differs from the gated tree (main moved?): run tools/check.sh on main"
    exit 3
fi
say "main's tree is the gated tree"
