#!/usr/bin/env bash
# Upload a PR's screenshots to the orphan branch pr-assets and print the Markdown that embeds them (D-162, D-168).
# Look at every image first: no tokens, personal data, notifications or real badges. It all stays in history, and the repo is
# public. Each upload is its own commit, and pr-assets is never force-pushed.
#
# Usage: tools/pr_shots.sh <pr> <image.png>...  (file names of letters, digits and -, for their URLs)
# Stops at the first failure. Run it again after one: a file that is already there is replaced, not duplicated.
set -euo pipefail

repo=ndonkoHenri/pycon-us-flet
if [[ $# -lt 2 || ! $1 =~ ^[1-9][0-9]*$ ]]; then
    echo "Usage: tools/pr_shots.sh <pr> <image.png>..." >&2
    exit 2
fi
pr=$1
shift

# All of them before any upload, so a bad name doesn't leave half a set.
for file in "$@"; do
    if [[ ! -f $file ]]; then
        echo "pr_shots.sh: no such file: $file" >&2
        exit 1
    fi
    if [[ ! $(basename "$file") =~ ^[A-Za-z0-9-]+\.png$ ]]; then
        echo "pr_shots.sh: name it with letters, digits and - and end it in .png: $file" >&2
        exit 1
    fi
done

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
for file in "$@"; do
    name=$(basename "$file")
    cp "$file" "$dir/$name"
    sips -Z 1000 "$dir/$name" > /dev/null
    base64 -i "$dir/$name" | tr -d '\n' > "$dir/$name.b64"
    # Replacing a file needs its blob sha. A new file's lookup fails and prints the 404 body, so the output is dropped.
    sha=$(gh api "repos/$repo/contents/$pr/$name?ref=pr-assets" --jq .sha 2> /dev/null) || sha=""
    gh api -X PUT "repos/$repo/contents/$pr/$name" -f branch=pr-assets -f message="Add $name for #$pr" \
        -F content=@"$dir/$name.b64" ${sha:+-f} ${sha:+sha=$sha} --jq .content.path > /dev/null
    echo "![${name%.png}](https://github.com/$repo/blob/pr-assets/$pr/$name?raw=true)"
done
