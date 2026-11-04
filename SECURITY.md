# Security policy

This is a community project, not the Python Software Foundation's, and it has no public builds yet. Only the latest
commit on `main` is supported.

## Report a vulnerability privately

Please don't open a public issue or pull request for a security problem.

Use GitHub's private vulnerability reporting: on the repository's **Security** tab, choose **Report a vulnerability**.
Your report is shared privately with the repository's maintainers, and with anyone they add to the advisory. We'll
agree with you when to disclose it.

If that button isn't there, open an issue that says only that you have a security report and asks for a private way to
send it. Leave out what the problem is: a maintainer will arrange a private channel.

A good report says what you found, where (a file, a screen or a build), how to reproduce it, and what it could let
someone do.

## What is in scope

- The app's code in this repository, and what it ships with.
- A secret or personal detail that was committed here by mistake.
- The local mock server in `tools/mock_api/`, only when it is used as documented. It is a development tool and isn't
  made to face the internet.

## What is not

- Flet and its extensions: report those to their own projects. If the cause is a dependency that ships in the app,
  tell us too, so we can track it.
- The Python Software Foundation's and the conference's systems. This app doesn't call the PSF's private API, only the
  public conference feed.
- Findings that need a rooted or jailbroken phone, or someone with the unlocked device in hand.

## What to expect

The maintainers are volunteers. We'll answer on the report as soon as we can, tell you whether we agree it's a
problem, and credit you in the fix if you'd like that.
