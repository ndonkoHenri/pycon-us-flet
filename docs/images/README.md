# README images

The screenshots in the repository's `README.md`: six screens, on Android and iOS, in light and dark, named
`<platform>-<appearance>-<n>-<screen>.webp` and 432 px wide.

## Why they are tracked here

A README on a public repository shows to readers who are signed out, and to forks and clones, so its images live
in the tree, next to the text that uses them and versioned with it. D-162's `pr-assets` branch is for a PR's
screenshots, which are looked at once and then forgotten; these few are the project's front door. Keep the folder
small (about 0.6 MB now) and replace the files rather than adding new ones, so the history doesn't grow with them.

## How they are made

`tools/readme_shots.py` does it, on an emulator and a simulator of your own, from the release APK and the simulator
build of the tree (usage in its docstring). It stores the demo clock (Friday 11:04, 2026), runs
`maestro/demo/readme_shots.yaml` once per appearance and shrinks what it saw. Nothing of the developer's setup shows:
the clock is stored without the Developer unlock, and the status bar is set to a fixed look.

Look at every image before committing it: the feed is public, but a stray notification, a mock URL or a real badge
is not.
