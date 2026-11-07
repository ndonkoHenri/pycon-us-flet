# Licence, asset and trademark review

**Draft for the owner (#846). This records facts for the owner to judge and isn't legal advice.** No agent has judged
what is lawful or contacted anyone. The owner signs it off in a comment on #846, before the repo goes public (#852),
and that outcome becomes a D-number. Contacting anyone (the PSF, GES, the venue, a sponsor, a speaker) is the owner's
alone (D-101).

Checked on 2026-11-02 at `main` `a6899a3b`; the README was read again at `283841e2`, and no asset or bundled data
changed between the two. **Checked again on 2026-11-07 at `main` `e929ca99`:** since then the app icon landed (#863, F3),
the snapshot was refreshed on 2026-11-04 with the same counts (C1) and the phone number still in `open-spaces[17]`
(C5), and `LICENSE`'s appendix line was added to the list (A7). No plan, mark or font changed. Nothing here removes or changes an asset; the table says what could change. `NOTICE` and its
bundled copy `src/pycon_us/licence_texts/notice.txt` were updated in this PR where they were plainly incomplete, and
the Licences page's Simple Icons row where it overstated CC0.

## What most needs the owner's eye

1. **Four floor plans carry an all-rights-reserved notice from GES (B2 to B5).** The print says no part may be
   reproduced without GES's written consent. The Ionic repository's Apache-2.0 licence covers its files as a whole;
   nothing we found says GES agreed to that. This is the main open question.
2. **Removing something later doesn't remove it from history.** The plans have been on `main` since 2026-10-21 (#576,
   #589, #609), and `pr-assets` holds screenshots of those screens (G1). What should not go public has to be dealt with
   before #852.
3. **The expo and job fair plans are full of other organisations' logos (B6, B7),** among them the Python Software
   Foundation logo, PyLadies, Django, and PyCon Africa at the job fair.
4. **The bundled feed has no overall licence and contains a person's phone number (C1, C5).** The feed's `CC BY` label
   appears only on schedule rows, and doesn't say what it covers.
5. **"CC0" was too strong for the brand marks (E1), and some of them have stricter rules (E2, E3).** Simple Icons
   itself says CC0 doesn't mean every icon is CC0; it removed LinkedIn over LinkedIn's guidelines; and the PSF asks for
   permission for a Python logo in changed colours.
6. **The repo and package names still say "pycon" (see Names).**

## Everything bundled or shown

"Repo only" means it isn't in a build, but becomes public with the repo. Every path of
`git ls-files src/assets src/pycon_us/data` is in this table.

### A. Ported from the Ionic app

Source: `https://github.com/PyCon/pycon-us-mobile`. GitHub reports Apache-2.0; `LICENSE` and
`package.json` agree. It has no `NOTICE` file, its `LICENSE` appendix says `Copyright 2015 Drifty Co.`, and nothing in
its `src/` has a copyright line.

| # | What | Where | Licence or status | What we do today | Recommendation |
|---|---|---|---|---|---|
| A1 | Ported logic | `src/pycon_us/core/rules.py`, `core/slugs.py` (its docstring says "copied exactly"), `core/signing.py`, `services/endpoints.py`; smaller rules elsewhere name Ionic in their docstrings | Apache-2.0 | Rewritten in Python and changed. Docstrings name the origin. `LICENSE` is in the repo, and `NOTICE` is in the repo and on the app's Licences page (D-87, D-296) | Keep. `NOTICE` now names these modules and the Drifty line. Owner to judge whether the docstrings are enough for Apache-2.0 §4(b), "prominent notices stating that You changed the files"; if not, add one line to these modules |
| A2 | Room and venue pins, 61 booth rectangles | `src/pycon_us/data/2026/map.toml`; repo only: `docs/spikes/07-floor-plans/src/booths.json` | Apache-2.0 | Credited in `NOTICE` | Keep. If the plans are redrawn (B), these must be measured again |
| A3 | Facts taken from Ionic's pages | `2026/content.toml` (sponsor credits: Temporal for the Wi-Fi, Google for the quiet room), `2026/conference.toml` (speakers' Discord page, directions point), `map.toml` (3D tour link) | Apache-2.0 for the code that holds them; each has a source and check date where it matters | Shown as links and credits | Keep |
| A4 | Reference captures and research | Repo only: `tools/capture_ionic_reference/`, `tests/fixtures/ionic/`, `docs/research/ionic/` | Our drivers, Ionic's output over the feed (speaker names included), and our notes with short code quotes | Tests read the captures; no build has them | Keep; they go public with the repo, as C2 does |
| A5 | Colours | `src/pycon_us/theme.py` (D-22, "the PyCon palette"); the boot and splash purple `#680579`, also in PR #863's icon | Colour values taken from Ionic's theme; Ionic's magenta is darkened | Our theme | Owner to note that the app still looks like the PyCon palette. Change only if the identity decision wants distance |
| A7 | `LICENSE`'s appendix line | `LICENSE` line 190: `Copyright 2015 Drifty Co.` | Copied with Ionic's `LICENSE`, which had filled in the appendix's template line `[yyyy] [name of copyright owner]` | A stranger reads our `LICENSE` as saying Drifty Co. holds this repo's copyright. `NOTICE` already says who holds what (Drifty Co. for the original, the contributors for ours) | Restore the template line, so `LICENSE` is the standard text and `NOTICE` keeps the credits (#847 found it). Or put our own line there. Not changed until the owner signs off |
| A6 | Not taken | Ionic's `appicon.png`, `pycon-us-2026-logo.svg`, `python-logo.png`, `pypi-logo.png`, `splash.png`, `speaker-*` | None of them is in our tree: a listing of tracked images finds only the plans, the marks and one test QR code (G) | Not bundled | Keep it that way |

### B. Floor plans

All seven are in `src/assets/maps/2026/`, made by `tools/encode_plans.py` from Ionic's files, each as `<id>.webp` and
`<id>-thumb.webp`. Each full-size plan was looked at for this review. The thumbnails are the same pictures: shrunk to
their size, each plan differs from its thumbnail by under 1.4 of 255 grey levels on average.

Ionic's repo licence is the only licence we have for these. Each has one version in `main`'s history, already covered
or cropped when added.

| # | Plan | Comes from | What is on it, as seen | Licence or status | What we do today | Recommendation |
|---|---|---|---|---|---|---|
| B1 | `campus.webp`, `campus-thumb.webp` | `floor-plans/campus-map.jpg`, with PyCon US callouts added ("Main Entrance", "Badge Required") | The venue's map with its address, phone and `longbeachcc.com`, and its spaces' wordmarks: The Cove, Terrace, Pacific Ballroom, Promenade Plaza, Top of the Lot, Bogart & Co. No GES block | Apache-2.0 by Ionic's repo; the base looks like the venue's own, and its author isn't named | PyCon US wordmark and the venue's logo painted over; credited | See the plan decision below. `NOTICE` now says the wordmarks left on it are the venue's |
| B2 | `concourse.webp`, `concourse-thumb.webp` | `floor-plans/floor-plan-1.jpg` | GES title block with its copyright notice; organisers' coloured room labels on top | **Conflict:** Apache-2.0 by Ionic's repo; the print says all rights reserved (quoted below) | Bundled and shown with the notice kept; credited | See the plan decision below. Never crop or paint out the notice |
| B3 | `upper.webp`, `upper-thumb.webp` | `floor-plans/floor-plan-2.jpg` | As B2. The large empty box at the top left is in Ionic's file too; we covered nothing | **Conflict**, as B2 | As B2 | As B2 |
| B4 | `arena.webp`, `arena-thumb.webp` | `floor-plans/floor-plan-3.jpg` | As B2. The same block appears smaller, its small print unreadable at this size | **Conflict**, as B2 | As B2 | As B2 |
| B5 | `seaside.webp`, `seaside-thumb.webp` | `floor-plans/floor-plan-4.jpg` | As B2, with the notice legible | **Conflict**, as B2 | As B2 | As B2 |
| B6 | `expo.webp`, `expo-thumb.webp` | `pycon-us-2026-floorplan-nologo.jpg` | The conference's 2026 artwork (mixing console, palm trees) with no designer named. About 60 logo tiles: sponsors such as AWS, Microsoft, Meta, Bloomberg, Capital One. **PSF marks and Python-logo variants:** the Python Software Foundation logo at booth 407, PyLadies 731, and tiles for EuroPython 733, Python Asia 729, Python en Español 735, and PyCon Africa, PyCon Senegambia and Python Mozambique 727. Also Django and Djangonauts 734 | Apache-2.0 by Ionic's repo for the file; the logos are their owners' marks, and the PSF's trademark page names Python's logos and PyLadies | Sun-and-palms mark painted over; credited; each tile opens that sponsor's card | See the logos decision below |
| B7 | `job-fair.webp`, `job-fair-thumb.webp` | `floor-plans/job-fair.jpg` | 20 tiles with logos and names, including Google, Bloomberg, Capital One, SentinelOne, and **PyCon Africa's** logo with its name (T18) | As B6 | Cropped to the floor, without the header and its PyCon US logo; credited | See the logos decision below |

GES's notice, read from the seaside plan:

> Copyright (C) by GES Global Experience Specialists, All Rights Reserved. No part of this publication may be
> reproduced, stored in any retrieval system, or transmitted in any form by any means - electronic, mechanical
> photocopying, recording, or otherwise - without the express written consent of GES Global Experience Specialists.

**The plan decision (B1 to B5), for the owner:**

| Option | What it means | Cost |
|---|---|---|
| 1. Ask | The owner asks the PSF, and GES through it, whether the plans may be reused | Time; an answer may not come |
| 2. Redraw (**recommended unless option 1 gives a clear yes**) | Our own simple schematics of the rooms, under this repo's licence, with no one else's drawing or wordmarks | Five drawings, pins measured again, one more thing to keep accurate each year. Going public would also need the old files out of the history (the owner's call) |
| 3. Keep private | Keep them for internal builds; hold #852 until it's settled | The repo stays private meanwhile |
| 4. Keep and publish | Rely on the Ionic repo's licence and our credit | No work; the conflict stays as quoted above |

**The logos decision (B6, B7), for the owner:** keep them, since they show who is at each booth and `NOTICE` credits
them; or draw our own plan from the booth rectangles and the feed's names, with no logos, which also drops the
conference's artwork. Recommended: redraw if the plan decision goes that way, since the work is shared; otherwise keep
for internal builds, and decide again before anything goes public.

### C. The public feed

Source: `https://us.pycon.org/2026/schedule/conference.json`. Counts are from the bundled file, fetched 2026-10-11.

| # | What | Where | Licence or status | What we do today | Recommendation |
|---|---|---|---|---|---|
| C1 | The feed snapshot: 728 schedule rows, 144 speakers on them, 25 posters, 24 sprints, 123 open spaces, 13 job listings, 105 sponsors | `src/pycon_us/data/2026/conference.json` | **No overall licence.** All 728 schedule rows, breaks included, say `"license": "CC BY"`; no other section does, and the feed doesn't say what the label covers. The app doesn't read it. The site's footer says `© Python Software Foundation`; its keynote page has no reuse terms | Bundled unchanged for the first offline launch (D-38, D-135). `NOTICE` now credits it and says this repo's licence doesn't cover it | Owner to decide: keep it, or fetch it at build time and keep it out of the public repo (needs a change to D-135 and the tests). Recommended: keep it, as the feed is public and offline first depends on it. Treat `CC BY` as unconfirmed |
| C2 | Copies and extracts | Repo only: `tests/fixtures/feeds/conference-2025.json`, `conference-2026.json`, `tests/fixtures/ionic/*/speakers.json`, `tests/fixtures/html_md/samples.json`, `docs/spikes/03-html-markdown/src/samples.json` | As C1 | Test data | Goes with C1's decision |
| C3 | People's words and photos: speaker names and bios, 136 of the 144 with a photo URL, poster authors, sprint submitters' names, talk abstracts | In C1; photos from `pycon-assets.s3.amazonaws.com` | Written by the people themselves, published by the PSF. The feed's `contact` field already says `redacted`. Photos are loaded by URL and not in the repo | Shown on session, speaker, poster and sprint screens | Keep. Owner to decide what to do if someone asks to be removed: the snapshot's text would have to change, which D-135's "unchanged bytes" doesn't allow for |
| C4 | Sponsor logos and descriptions: 105 logos, 14 sponsors marked `mobile_banner`; 13 job listings with logos | In C1; logos from `s3.dualstack.us-east-2.amazonaws.com/pythondotorg-assets` | Sponsors' marks and texts. Loaded by URL, not bundled; offline with no cache the tile shows initials (`ui/logos.py`, D-262) | Sponsors list and detail, Now's spotlight, Job listings, booth cards | Keep; each is shown as the named sponsor's own |
| C5 | **A person's own phone number**, in an open space's description | `open-spaces[17]` of C1 and of `tests/fixtures/feeds/conference-2026.json` | Published by the PSF's feed; the number isn't repeated here on purpose | Shown as the open space's text | Owner to decide before #852. It leaves `main`'s tree only with a changed snapshot and fixture, and stays in history unless that is rewritten |
| C6 | Sprint logos (22), open space images (67), the Wi-Fi name and password | In C1; images from `pycon-assets.s3.amazonaws.com`; Wi-Fi also in `2026/content.toml` (D-280) | As C1. The password is in the public feed | Shown | Keep. The password is 2026's, and goes with the year's data |

### D. Our year data

| # | What | Where | Comes from | Licence or status | What we do today | Recommendation |
|---|---|---|---|---|---|---|
| D1 | Keynote and panel people: 15 photo URLs (14 photos, as one person is on two sessions) and 10 bios | `src/pycon_us/data/2026/content.toml`, `[[keynotes]]` | The [keynote speakers page](https://us.pycon.org/2026/about/keynote-speakers/), checked 2026-10-13 | Bios and abstracts are in our own words, as the file and D-217 say (not compared with the site again here); the site has no reuse terms. Photos are the site's 165 px copies, loaded by URL: not in the repo. One file name (`MNTN_Matt-Lief-Anderson_2856-Edit`) suggests a photographer no page credits | Shown on Keynotes and session detail (D-217). `NOTICE` now says all this | Keep. Owner to decide on asking the PSF if a public release is ever planned. Copying the photos into the repo would need permission, so keep linking |
| D2 | Other copy and links | `2026/content.toml`: Help & safety, Open spaces and Lightning talks pages, venue hours, About the PSF, Social media | The PSF's public pages and the feed, each with a source and check date | Our own words where the file's comments say so; the PSF's mission sentence is quoted from the feed's `about-psf` block | Shown | Keep; check them again each year (D-45) |
| D3 | Event facts and track names | `src/pycon_us/data/2026/conference.toml` | The feed, the site and Ionic | Facts and our own text | Shown | Keep |
| D4 | 2025's data | `src/pycon_us/data/2025/conference.toml`, `src/pycon_us/data/2025/content.toml` | The 2025 feed and site; keynote names, no photos or bios | As D3 | Used by tests; `config.YEAR` shows 2026 | Keep |
| D5 | The data folder's guide | `src/pycon_us/data/README.md` | Ours | Apache-2.0 | Documentation | Keep |

### E. Brand marks

Simple Icons 13.21.0, unmodified, in `src/assets/icons/brands/`, 24 dp and tinted (D-264). Its
`DISCLAIMER.md` at that tag says: "Simple Icons is released
under CC0 - though that doesn't mean to imply that all icons within the project are also CC0", and asks users to "seek
the correct permissions to use the icons relevant to their project". Its data has no `license` for any of our eight.

| # | Mark | Where | Status | What we do today | Recommendation |
|---|---|---|---|---|---|
| E1 | All eight | `src/assets/icons/brands/` | The SVG files are the set's; the marks are their owners'. `NOTICE` used to say all were CC0, and the Licences page's row "public domain"; both now state the limit. D-264, `docs/ux.md` and the feature matrix still say "CC0" of the set | Each beside a link to that brand (D-36) | Keep; the owner's D-number can restate D-264 |
| E2 | Python | `python.svg`, shown on About the PSF and Social media | One-colour mark in `#3776AB`, not the PSF's two-colour logo. The PSF's policy: "Logos that simply change the colors or fonts require permission from the PSF Trademarks Committee" | Beside links to python.org and the Python blog | Replace it with the PSF's own logo file unchanged, or a Material icon, or the owner asks. Recommended: a Material icon, the simplest |
| E3 | LinkedIn | `linkedin.svg`, shown on About the PSF and Social media | Simple Icons removed it in 14.0.0 (`simple-icons/simple-icons#11372`), citing LinkedIn's guidelines that it "generally does not permit" use of its logos, with narrow exceptions | Beside a link to LinkedIn. D-264 pins 13.21.0 because it is the last release with all eight | Replace it with a Material icon. That also lets the set move to a current release |
| E4 | PyPI | `pypi.svg`, shown on About the PSF and Social media | The PSF's trademark page doesn't mention PyPI; Simple Icons lists no guidelines | Beside links to pypi.org and its blog | Keep; owner to note |
| E5 | X, YouTube, Mastodon, Bluesky | `x.svg`, `youtube.svg`, `mastodon.svg`, `bluesky.svg` | Owners' marks. Simple Icons links brand guidelines for all but Bluesky; they weren't read against our use | Beside a link to that brand | Keep; read each guideline before a store release |
| E6 | Discord | `discord.svg` | As E5 | **Bundled but not shown:** its only reference is `ui/brands.py`'s tint table, and the Account page's Discord row uses a Material icon | Remove the file and its entry, since nothing uses it |

### F. Fonts, icons and licence texts

| # | What | Where | Comes from | Licence or status | What we do today | Recommendation |
|---|---|---|---|---|---|---|
| F1 | Roboto 400, 500, 700 | `flutter_packages/roboto_fonts/` | googlefonts/roboto 2.138 | Apache-2.0. The font's own records say `Copyright 2011 Google Inc.`, `Version 2.138`, and the licence; `LICENSE` is beside it | Credited (D-105, D-455) | Keep |
| F2 | Material icons | In Flet and Flutter, not in this repo | Google | Apache-2.0, as `licences.py` says; not checked against a build's files | On the Licences page | Keep |
| F3 | The app icon | `src/assets/icon.svg`, and the options in `docs/icon-options/` (#863, D-452, merged) | Ours: plain shapes, a badge and a star, with no PSF mark | This repo's licence | Purple from A5 | Keep |
| F4 | Licence texts | `src/pycon_us/licence_texts/` (17 files) | Each component's own licence file | As `licences.py` states; a test keeps every runtime package of `uv.lock` listed (D-75, D-296) | Shown offline on the Licences page | Keep |
| F5 | **Gap:** Flutter's and the plugins' per-package notices | In each build, as `NOTICES.Z` | Each Dart package | Flet can't show Flutter's page yet (U51, #371), so the page lists direct components only | Interim shipped in #442 | Keep the interim; before v1.0.0 (#853), compare one build's `NOTICES.Z` with the page. Python's own native libraries weren't checked either |

### G. Repo only

| # | What | Where | Status | Recommendation |
|---|---|---|---|---|
| G1 | Screenshots and recordings | Branch `pr-assets` (#847 counts 1,794 files) | 114 file names mention the expo, plans, keynotes, sponsors or speakers; the images weren't opened for this review. All become public with the repo (D-162); #847 sweeps them for personal data, not for these rights | Include them in the plan and logos decisions: redrawing the plans doesn't remove them from here |
| G2 | Test QR code | `docs/spikes/08-scanner/src/qr.png` | Generated for the spike | Keep |

## Names

The app's name, bundle id and scheme no longer contain "pycon" (D-452, #863: Conf Companion,
`io.github.ndonkohenri.confcompanion`, `confcompanion`). These still do:

| Name | Where | Who sees it |
|---|---|---|
| Repository `ndonkoHenri/pycon-us-flet` | GitHub, `NOTICE`'s and `licences.py`'s copyright line ("The pycon-us-flet contributors") | Everyone, once public; users on the Licences page |
| Local folder `pycon-us` | Checkouts, and absolute paths in some `docs/research` files (#847) | Developers |
| Distribution `pycon-us` | `pyproject.toml`, `uv.lock` | Developers |
| Package `pycon_us` | `src/pycon_us/` (278 tracked files), every import, and the Python folder inside a build | Developers; anyone who unpacks a build |
| Project board "PyCon US Flet" | GitHub | The team |
| Descriptions such as "A conference companion for PyCon US" | `pyproject.toml`, the first line of `NOTICE`, `__init__.py`'s docstring | Developers; users on the Licences page |
| Emulator `pycon_pixel6a_api36` | `docs/`, tools | Developers |
| The event's own name and addresses | "PyCon US 2026", `us.pycon.org`, `#PyConUS`, the SSID `PyConUS26`, in year data and the feed | Users, naming the event (D-36) |

Recommendation: rename the repo before #852, when it costs least, since D-452's stated aim is that no PSF mark leaves
our devices; update the copyright line with it. Rename the package afterwards as a mechanical PR, or leave it, since
only developers see it. Keep the event's own name in the data. Renames are the owner's call, with #15.

**If the repo moves to an organisation** (the owner has said it may move to `flet-dev`): the move is the natural moment
for the rename, since every link changes once either way and GitHub redirects the old address. The copyright line
("The pycon-us-flet contributors") names contributors, not an owner, so it stays right after a move and only follows
a rename. The bundle id `io.github.ndonkohenri.confcompanion` names a person's GitHub Pages domain: it can't change
once a build is in App Store Connect or Play Console (`docs/development.md` §9), so if the app should belong to the
organisation, change it before the first upload (#121), not after. `SOURCE_URL` (D-292) and the View source links
follow the repo's address.

## The PSF's published rules

From the [PSF trademark policy](https://www.python.org/psf/trademarks/) and its
[PyCon policy](https://www.python.org/psf/trademarks/pycon/) (Version 1.0), read on 2026-11-02. These are the policies'
words, not a reading of them:

- "All trademarks are subject to "nominative use rules" that allow use of the trademark to name the trademarked entity
  in a way that is minimal and does not imply a sponsorship relationship with the trademark holder." Saying accurately
  that software is written in Python is always allowed, with the word or the unaltered logos. D-36's "Not an official
  PSF app" and naming the event rest on this kind of use; the owner judges whether that holds.
- "Any commercial use of the PSF trademarks in product or company names must be approved first by the PSF."
- For the Python logos: "These logos should be used in the form provided by the PSF", and "Modifications that modify or
  obscure any part of the shape of the logo will not be approved."
- For websites, brochures and product packaging, unaltered logos: "Non-commercial uses to promote the Python programming
  language are allowed, as are all nominative uses", and "Any other commercial uses require prior written permission
  from PSF."
- "The first or most prominent mention of a Python trademark should be immediately followed by a symbol for registered
  trademark". `NOTICE` and the README don't do this today.
- PyCon: the PSF "claims the term “PyCon” as a trademark worldwide for conference activities", and "Use of the trademark
  is subject to approval by the PSF trademarks committee (write to psf-trademarks at python.org)". The policy doesn't
  discuss apps.

The README's licence section (rewritten in #868) speaks of the names: "We use the names only to say which event and
language this is about; the app's name and icon use no PSF mark." It leaves the logos the app does show (B6, E2) to
`NOTICE`, which lists them. Owner to note.

## What this review didn't check

- The contents of a built APK or IPA: no build was made for this review.
- Each sponsor's, group's or brand's own logo rules, beyond those quoted above.
- Who holds the rights in the artwork of B6 and B7, or in any photo.
- Whether GES, the PSF or the venue have an agreement that covers these plans: nothing public that we looked at says.
- The images in `pr-assets` one by one, or earlier versions of files in PR branches.

## Sign-off

The owner's decisions go in a comment on #846, then into a D-number. Nothing here is decided until then. To answer by
number, each with the recommendation first:

1. **Floor plans B1 to B5:** redraw (unless asking gets a clear yes), ask, keep private, or keep and publish.
2. **Logos on B6 and B7:** redraw with the plans, or keep for internal builds and decide again before anything goes
   public.
3. **Feed C1:** keep the snapshot bundled and credited, or fetch it at build time.
4. **The phone number C5** (and the two emails in the 2025 fixture, #847): blank them in our snapshot and fixtures, or
   leave them as the feed published them. History keeps them either way unless rewritten.
5. **Marks E2 and E3:** Material icons for Python and LinkedIn, or keep. E6: remove the unused Discord file.
6. **`LICENSE` A7:** restore the template line, or put our own line there, or leave it.
7. **Names:** rename the repo before #852 (or with a move to an organisation), and decide whether the bundle id should
   name the organisation before the first upload.
8. **A1:** whether the ported modules' docstrings are the "prominent notices" Apache-2.0 §4(b) asks for, or each gets
   one more line.
