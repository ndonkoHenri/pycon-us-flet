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

# One run at a time on this Mac: a merge moves main, which voids a gate running beside it. Not in $TMPDIR, which macOS
# sweeps. A lock whose holder is gone doesn't count; a run killed outright can't remove its own.
lock=${MERGE_LOCK:-$HOME/Library/Caches/pycon-merge.lock}
mkdir -p "$(dirname "$lock")"
until mkdir "$lock" 2> /dev/null; do
    holder=$(cat "$lock/pid" 2> /dev/null || true)
    if [[ -n $holder ]] && ! kill -0 "$holder" 2> /dev/null; then
        say "removing the lock of a dead run ($holder)"
        rm -rf "$lock"
        continue
    fi
    say "waiting for another run (${holder:-starting})"
    sleep 10
done
echo $$ > "$lock/pid"
trap 'rm -rf "$lock"' EXIT

if ! tree=$("$(dirname "$0")/gate.sh" "$@"); then
    say "the gate failed: nothing merged"
    exit 1
fi

for pr in "$@"; do
    # The state decides, not gh's status: --delete-branch fails after the merge when the branch is checked out here.
    gh pr merge "$pr" --squash --delete-branch || say "gh pr merge $pr said no; checking its state"
    state=$(gh pr view "$pr" --json state --jq .state)
    if [[ $state != MERGED ]]; then
        say "#$pr is $state, not merged: the PRs after it were left alone"
        exit 3
    fi
    say "#$pr merged"
done

git fetch -q origin main
if [[ $(git rev-parse 'FETCH_HEAD^{tree}') != "$tree" ]]; then
    say "main's tree differs from the gated tree (main moved?): run tools/check.sh on main"
    exit 3
fi
say "main's tree is the gated tree"
