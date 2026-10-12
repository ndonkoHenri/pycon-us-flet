# pr-assets

Screenshots and recordings referenced from pull requests (D-162). This orphan branch never merges into `main`.

- One folder per PR: `<pr-number>/<short-name>.png`.
- Downscale before committing (`sips -Z 1000 file.png`), and keep it to the images the PR needs.
- Embed in a PR comment: `![Android, offline first launch](https://github.com/ndonkoHenri/pycon-us-flet/blob/pr-assets/<pr>/<file>.png?raw=true)`. That works for anyone who can see the repository.
