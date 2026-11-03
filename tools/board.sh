#!/usr/bin/env bash
# Set an issue's or a PR's Status on the "PyCon US Flet" Project, adding it first if it isn't there (D-90, D-94).
# It needs gh's project scope: gh auth refresh -s project.
#
# Usage: tools/board.sh <issue-or-pr> todo|in-progress|in-review|done
#
# The ids are stable. If the Project is ever rebuilt, read them again:
#   gh project view 2 --owner ndonkoHenri --format json --jq .id
#   gh project field-list 2 --owner ndonkoHenri --format json --jq '.fields[] | select(.name == "Status")'
set -euo pipefail

case ${2-} in
    todo) option=876879f0 ;;
    in-progress) option=921d2845 ;;
    in-review) option=0361c618 ;;
    done) option=40195126 ;;
    *)
        echo "Usage: tools/board.sh <issue-or-pr> todo|in-progress|in-review|done" >&2
        exit 2
        ;;
esac
number=$1

# The issues endpoint answers for PRs too, with the right URL for item-add.
url=$(gh api "repos/ndonkoHenri/pycon-us-flet/issues/$number" --jq .html_url)
item=$(gh project item-add 2 --owner ndonkoHenri --format json --jq .id --url "$url")
gh project item-edit --project-id PVT_kwHOBeZJHs4BmmHp --id "$item" \
    --field-id PVTSSF_lAHOBeZJHs4BmmHpzhlOeUE --single-select-option-id "$option" > /dev/null
echo "#$number: $2"
