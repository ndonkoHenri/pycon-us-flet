# S3: Is a stdlib HTML-to-Markdown converter good enough for the feed?

**Spike:** S3 ([#64](https://github.com/ndonkoHenri/pycon-us-flet/issues/64), PLAN §8). **Date:** 2026-10-12, about 2 hours on one Mac.
**Decides:** D-114 (converter scope), D-115 (escaping), D-116 (how converted text is rendered), D-117 (E5 cut; U21 and U22, amends D-98). **Facts:** F27, F28. **Follow-ups:** P0-15 ([#67](https://github.com/ndonkoHenri/pycon-us-flet/issues/67)) builds the converter; comments on [#58](https://github.com/ndonkoHenri/pycon-us-flet/issues/58), [#59](https://github.com/ndonkoHenri/pycon-us-flet/issues/59) and [#91](https://github.com/ndonkoHenri/pycon-us-flet/issues/91).

## Question

Can a small converter on stdlib `html.parser` turn every HTML field of the 2025 and 2026 public feeds into Markdown that `ft.Markdown` renders faithfully on a phone, or do we need an HTML control (E5)?

## Answer: yes, with escaping and a style sheet

- **The markup is small and regular.** Both feeds use 17 tags, 4 attributes that matter (`href` only; `target`, `rel`, `class` and one `style` are presentation) and 4 entities. The prototype handles 16 tags and unwraps the 17th (`span`, 4 uses, all `style="font-size: smaller"`).
- **No character is lost or added.** All 1,389 values of the 19 HTML fields convert. The visible characters of every value match the HTML's (whitespace aside), and no tag, raw `$` or LaTeX opener is left in the output. This is a static check: whether markup renders as intended was checked on the device for 24 samples, and P0-15's tests cover the boundaries (see the review notes below).
- **It renders on Android 16** (`pycon_pixel6a_api36`). 22 feed samples and 2 synthetic ones were shown with `ft.Markdown(selectable=True, extension_set=GITHUB_WEB, on_tap_link=...)` in light and dark and at 200 % text: headings, nested lists, ordered lists with nested bullets, code spans, strike-through, block quotes, rules, hard breaks, bare URLs and links all rendered as intended. A tapped relative link reported its absolute URL with `selectable=True`.
- **Escaping is not optional.** Flet's `Markdown` always adds LaTeX syntax on top of any extension set (F27): `5$ or 10$ `, `( the notes )` and `[ the FAQ ]` rendered as math on the emulator, and GFM turned `~y~` into strike-through and `:smile:` into an emoji. Writing those characters as numeric character references fixed all of them (D-115). No 2025 or 2026 field triggers LaTeX today, but the 2026 job listings already carry `$` amounts.
- **Flet's defaults are not good enough for the app.** Links are `Colors.blue` without an underline (about 3.1:1 on white, and colour is the only cue), headings start at `headlineSmall`, and a custom `md_style_sheet` replaces the theme's text styles instead of merging with them, so text without an explicit colour turns black in dark mode (F28). The app passes one style sheet with explicit colours (D-116).
- **So E5 is not needed** (D-117): HTML that the converter cannot express (tables, images) does not occur in two years of feeds.

## Method

- **Feeds:** `https://us.pycon.org/2025/schedule/conference.json` (543,527 bytes) and `.../2026/...` (822,356 bytes), fetched once with `curl` on 2026-10-12 and committed as `tests/fixtures/feeds/conference-<year>.json` (section M). Public feed only; no `/api/v1`.
- **Reproducer:** [`03-html-markdown/`](03-html-markdown/).
  - `html_md_proto.py` (stdlib only): the converter design from architecture §7.7 plus what S3 found. It parses each value into a small tree and renders it. Plain-text values (no tag) take their own path.
  - `census.py`: walks every string of both feeds (list indices folded to `[]`), counts tags, attributes and entities per field, converts every value of every HTML field, checks the text survives, and writes `src/samples.json`. Run it from the repo root: `python3 -I docs/spikes/03-html-markdown/census.py`.
  - `src/main.py` and `pyproject.toml`: a stub app that shows one sample at a time. AppBar buttons step through the samples, switch Flet's default style sheet for the proposed one, and show the Markdown source. `on_tap_link` prints the URL and shows it in a SnackBar.
- **Text check:** for each value, the HTML's visible characters (through `html.parser`) and the Markdown's visible characters (our syntax removed, character references decoded, code spans kept as is) are compared with all whitespace removed. A dropped word, a stray marker or an undecoded reference shows as a difference; structure (paragraphs, lists) does not.
- **Device:** the S1/S5 reference AVD `pycon_pixel6a_api36` (`emulator-5554`, Android 16, API 36, 1080 × 2400 at 420 dpi). Flet at the pin `15854a0ac`. `uv run flet build apk --arch arm64-v8a` from the reproducer folder (about 90 s), installed with `adb install -r`, driven with `adb shell input tap`, captured with `adb exec-out screencap`. Dark mode by `cmd uimode night yes`, 200 % text by `settings put system font_scale 2.0` (both reset afterwards). The accessibility tree by `uiautomator dump`.
- **Not done:** iOS (the renderer is the same Dart code; the P1 session-detail issue #91 checks it on the simulator); TalkBack's spoken wording for Markdown links (the accessibility pass #109).
- The emulator is shared with other agents: one round of screenshots was taken over by another app and was repeated; every kept screenshot was taken with the stub in the foreground.

## Evidence

### Where the markup is

Every string field of both feeds was scanned. Markup lives in these fields; slot names, open spaces and sponsors are handled elsewhere (below).

| Year | Field | Values | With tags | Plain text | Empty |
|---|---|---|---|---|---|
| 2025 | `conference.content.{about, about-psf, social-media}` | 3 | 3 | 0 | 0 |
| 2025 | `schedule[].description` | 205 | 204 | 0 | 1 |
| 2025 | `schedule[].speakers[].bio` | 155 | 151 | 0 | 4 |
| 2025 | `schedule[].sessions[].description` | 19 | 19 | 0 | 0 |
| 2025 | `schedule[].sessions[].speakers[].bio` | 26 | 26 | 0 | 0 |
| 2026 | `conference.content.{about, about-psf, code-of-conduct, social-media, venues-hours, wifi}` | 6 | 6 | 0 | 0 |
| 2026 | `schedule[].description` | 728 | 214 | 0 | 514 |
| 2026 | `schedule[].speakers[].bio` | 156 | 153 | 0 | 3 |
| 2026 | `posters[].description_html` | 25 | 25 | 0 | 0 |
| 2026 | `posters[].speakers[].bio` | 29 | 29 | 0 | 0 |
| 2026 | `sprints[].description_html` | 24 | 9 | **15** | 0 |
| 2026 | `job-listings[].description_html` | 13 | 13 | 0 | 0 |

- **Slot names** (DATA-08): 12 Markdown links in 2026 and 1 in 2025, plus one 2025 name with HTML: `CANCELLED: <s>Introduction to Sprints Workshop</s>` (its description carries the same `<s>`). The name rules strip Markdown links and unescape entities but not tags, so #59 must strip tags from names too.
- **2025 has no `posters` list:** its 19 posters arrive as `sessions` inside one `poster` slot ("Posters Session"), with their own descriptions and bios. DATA-27 says no feed emits `slot.sessions`; 2025 does, so #58 decides how the 2025 fixture is processed.
- **Open spaces:** Markdown, never HTML (7 links in 2026, 1 in 2025; 13 and 5 use block syntax). They pass through as Markdown, so F27's LaTeX applies to them unescaped (D-115).
- **Sponsors:** plain text, no tags or entities (2025: 13 levels; 2026: 4).

### Tag census (both feeds, HTML fields)

| Tag | Uses | Prototype | Markdown |
|---|---|---|---|
| `p` | 1,783 | handled | paragraph |
| `li` | 481 | handled | `- ` or `N. `, continuation indented by the marker's width |
| `strong` | 270 | handled | `**x**` |
| `a` | 263 | handled | `[x](absolute url)` |
| `code` | 172 | handled | `` `x` `` (longer fence when `x` has backticks) |
| `em` | 154 | handled | `*x*` |
| `ul` | 97 | handled | bullet list |
| `h2` | 35 | handled | `## x` |
| `br` | 25 | handled | hard break (`"  \n"`) |
| `h3` | 25 | handled | `### x` |
| `ol` | 6 | handled | numbered list |
| `h4` | 5 | handled | `#### x` |
| `h1` | 5 | handled | `# x` |
| `span` | 4 | **unwrapped** | its text (all four are `style="font-size: smaller; font-weight: normal;"` around "Keynote" in 2025) |
| `hr` | 4 | handled | `---` |
| `s` | 2 | handled | `~~x~~` (both are the 2025 "CANCELLED" row) |
| `blockquote` | 1 | handled | `> ` |

- **Attributes:** `a@href` 263; `a@target=_blank`, `a@rel=nofollow noopener noreferrer` and `a@class=external` 34 each (all in job listings); `span@style` 4. Only `href` carries meaning; the app opens every link in the in-app browser anyway.
- **Hrefs:** absolute `https` and `http`, 24 relative `/2025/…` or `/2026/…`, and 2 `mailto:`. One href has a stray `]` (`…/company/thepsf]`); it is kept, percent-encoded.
- **Entities:** `&amp;` 62, `&gt;` 5, `&lt;` 1, `&mdash;` 1.
- **Not present:** `img`, `table`, `pre`, `div`, `script`, `style`, `iframe`, `sup`, `sub`, `dl`. Inline `style` only on the four `span`s.

### Converter coverage

| Check | Result |
|---|---|
| Values converted | 1,389 (19 fields; slot names excluded) |
| Characters lost or added (whitespace aside) | **0** |
| Tags left in the Markdown (outside code) | 0 |
| Raw `$`, `\(` or `\[` left (outside code) | 0 |
| Tags unwrapped | `span` (4) |
| Fields whose meaning changes | none, after the decisions below. Without them: newline pseudo-lists, the 15 plain-text sprint descriptions and every `$`, `( … )` or `:name:` would (see next table) |
| Time | 975 values of the 2026 feed in 20 ms on the host (M4) |

### What could change meaning, and what the prototype does

| Case | Seen in | Without care | Prototype (decision) |
|---|---|---|---|
| Newlines inside `<p>`: 179 blocks, e.g. `Company: …\nLocation: …`, `- Python 3.12\n- Docker`, but also hard-wrapped prose (`…Computer and Information\nScience at…`) | descriptions, bios, job listings | Keeping them as breaks makes hard-wrapped prose ragged on a phone | Collapsed as a browser does, so the text reads as it does on us.pycon.org and in the Ionic app (D-114) |
| Plain text in an HTML field, paragraphs separated by blank lines | 15 of 24 sprint descriptions | Ionic rendered it as HTML and lost the paragraphs | Blank lines make paragraphs, single newlines make hard breaks (D-114) |
| `<s>` | 2025 "CANCELLED" row | Dropping the tag reads as if the workshop runs | `~~x~~`, rendered struck through (sample 7) |
| `<span style>` | 2025 keynotes | Smaller "Keynote" label | Plain text on its own line after the `<br>` (sample 4) |
| `$`, `( … )`, `[ … ]` | job listings (`$188,000 – $275,000`), any prose | Rendered as LaTeX (synthetic sample 23) | Numeric character references (D-115, sample 24) |
| `~`, `*`, `_`, `|`, `<`, `>`, `#`, `1.` at line start, `:name:` | prose, code-like text (`data_final_final_v3.csv`) | Strike-through, emphasis, tables, inline HTML, headings, lists, emoji | Numeric character references (D-115) |
| Markdown syntax inside `<code>` | `len([x for x in arr if x % 2 == 0])`, `<head>` | — | Code spans are raw: Markdown does not interpret them, so nothing is escaped inside (sample 9, 11) |
| Bare URLs in text | job listings, poster descriptions | Left raw, a URL's `_`, `$` or `]` could be read as markup, and GFM's autolink decides where it ends | An explicit link labelled with the escaped URL, trailing sentence punctuation left outside (D-114; samples 2, 13, 20; a tap on sample 20's URL reported `https://github.com/NAU-CCL/epymorph`) |
| Relative links | 24 hrefs | Open nothing | Joined to the site URL; only `http`, `https` and `mailto` become links (D-114) |
| Link or emphasis text with edge spaces (`<a> x </a>y`) | none in the feeds | `[x](…)y` reads "xy" | Edge whitespace kept outside the markup (D-114) |
| Emphasis starting or ending with punctuation next to a letter (`a<em>(x)</em>b`) | none in the feeds | CommonMark cannot open or close it, so `*` shows literally | P0-15 drops the markers (D-114) |
| Nested lists inside ordered lists | 2025 descriptions | Architecture §7.7's "two spaces per level" does not nest under `1. ` (CommonMark needs the marker's width, three spaces) | Continuation lines indented by the marker's width (sample 9) |

### Rendering on the emulator

24 samples (`src/samples.json`), each a whole field value: 22 picked to cover every tag, both years and every field type, plus the synthetic hazard line unescaped and escaped. All shown with Flet's default style sheet in light mode; the starred ones also in dark, and with the proposed style sheet.

| # | Field | Shows | Result |
|---|---|---|---|
| 1 | 2026 description | `ol`, `&amp;` | numbered list, `&` |
| 2★ | 2026 description | newlines in `p`, `hr`, `h2`, `strong`, bare URL | collapsed lines, rule, heading, bold, URL as a link |
| 3 | 2026 description | `ol` of links | numbered links |
| 4 | 2025 description | relative link, `br`, `span` | link + "Keynote" on the next line; tap → `https://us.pycon.org/2025/about/keynote-speakers#lynn-root` |
| 5 | 2025 description | `h1`, `h2` | headings |
| 6 | 2025 description | `h1 > strong`, `h3`, `ol` | headings, Spanish text |
| 7 | 2025 description | `s` | struck through |
| 8 | 2025 description | `hr` between paragraphs | rule |
| 9★ | 2025 description | code with `[ ]`, `%`; `ol` with nested `ul` | code spans intact; nested bullets under numbers |
| 10 | 2025 description | `h4`, `ul > li > strong` | |
| 11 | 2025 description | code with `&lt;head&gt;` | `<head>` in a code span |
| 12★ | 2026 bio | `blockquote` | quote block |
| 13 | 2026 job listing | `h2`, `strong`, `$` amounts, bare URL | `$188,000 – $275,000` as text; URL as a link |
| 14 | 2026 job listing | `$` range, lists | |
| 15 | 2026 job listing | `ul > li > p > a` with `target`, `rel`, `class` | tight list of links |
| 16★ | 2026 social-media | nested `ul`, code handles | two-level list |
| 17 | 2026 venues-hours | `h2`, `h3`, `ul` | |
| 18 | 2026 code-of-conduct | `mailto:` link | |
| 19 | 2026 poster bio | `h1` + `ul` in a bio | |
| 20 | 2026 poster | `&mdash;`, bare URL | tap → `https://github.com/NAU-CCL/epymorph` |
| 21 | 2026 sprint | plain text with paragraphs | two paragraphs |
| 22 | 2025 poster (`slot.sessions`) | `br`-separated pseudo-list | first item joins the sentence (as in a browser), the rest on their own lines |
| 23 | synthetic, unescaped | `5$ or 10$`, `( the notes )`, `[ the FAQ ]`, `~y~`, `*z*`, `:smile:` | **math**, strike, italic, emoji |
| 24★ | synthetic, escaped (D-115) | the same | all literal |

- **Default style sheet:** links `Colors.blue` (#2196F3), not underlined: about 3.1:1 on the light surface (below AA for body text) and 5.9:1 on the dark one; headings `headlineSmall` (h1) and `titleLarge` (h2) compete with a screen title; code spans have no background; block quotes have a light grey (dark grey in dark mode) box.
- **Proposed style sheet** (`proposed_style()` in `src/main.py`): links in `PRIMARY`, underlined; body 16 sp at 1.5 line height; h1 22, h2 18, h3/h4 16 sp at weight 500; code on `SURFACE_CONTAINER_HIGHEST`; block quote on the same with an `OUTLINE` bar. Without an explicit `color` on each text style, the body text was **black on the dark surface** (F28); with `ON_SURFACE` named, light and dark both read well (samples 2, 12, 13, 16).
- **200 % text** (sample 9): the Markdown scales with the OS setting and reflows; code spans wrap.
- **Accessibility tree** (sample 4, `uiautomator dump`): each link is its own focusable node, `android.widget.Button`, clickable, named by its text ("Lynn Root"); the text after a hard break is a separate node. So links are reachable and named; whether TalkBack says "link" or "button" is for #109.
- **Selection:** with `selectable=True` a tap on a link still fires `on_tap_link`.

Screenshots (1080 × 2400) are in the session scratchpad (`s3/light-01..24.png`, `dark-09, 12, 16, 24`, the styled variants and `light-09-font200.png`); they are summarised in the PR and not committed.

### Review notes (Codex, read-only, on the PR's diff)

- Emphasis next to punctuation and a letter cannot flank in CommonMark, escaped or not; no feed value has it (checked over both fixtures), and D-114 drops the markers in that case.
- Bare URLs are now explicit links and link text keeps its edge spaces outside the brackets; samples 2, 13 and 20 were rendered again with that build.
- Plain-text values now decode entities (`A &amp; B` → `A & B`).
- Kept as they are: an item that holds only a nested list renders `- - a` with the next item indented by two spaces, which CommonMark reads as a nested list; a `br` inside a heading becomes a space (D-114); a code span with edge spaces loses one space at each edge in the renderer, which hardly shows.
- The text check is static (characters, whitespace aside), so the verdict says what it proves; P0-15's tests add the boundaries (`testing-and-quality.md` §3.4).

## Decisions changed

- **D-114** (amends D-44's converter details and architecture §7.7): the supported tag list, unwrapping, whitespace, plain-text values, list indentation and link rules; the samples become P0-15's fixtures.
- **D-115:** escaping with numeric character references, including LaTeX and emoji triggers; raw code spans; bare URLs as explicit links.
- **D-116** (records for SESS-06, SPKR-03, DATA-23): one app style sheet with explicit colours; Markdown links stay (not `LinkTile`s).
- **D-117** (amends D-98): E5 moves to Cut; U21 (LaTeX opt-in in `ft.Markdown`) and U22 (a style sheet that merges with the theme) join the later candidates.
- **Facts F27, F28** (section N).

## What the next issues must apply

- **P0-15 (#67):** build `core/html_md.py` to D-114 and D-115 (the prototype is the reference; production code is P0-15's), with a text-only form for search that never contains markup. Tests: one per row of the tag census, the "what could change meaning" table and the synthetic hazard line; the inputs are the 22 samples (pick them from the feed fixtures with the same `(year, field, needle)` selectors as `census.py`) and the expected outputs are written into the tests and reviewed. Add an invariant over both fixtures: visible text unchanged and no raw tag, `$` or LaTeX opener outside code. Log the conversion time with `feed processed in N ms`.
- **#59 (names):** strip tags from slot names (the 2025 `<s>` row), keeping the text.
- **#58 (2025 posters):** the 2025 fixture carries posters in `slot.sessions`.
- **#71 (theme) and #91 (session detail):** the style sheet of D-116 lives in `theme.py` and is used by every `Markdown`; check it on the iOS simulator.

## Fallback

- **A new tag appears** in a later feed: it is unwrapped, so its text shows; the weekly feed check (#61) should list tags outside the D-114 set so the converter grows on evidence.
- **A table or image appears:** unwrapping keeps the text. If tables become common, the converter can emit GFM tables (`GITHUB_WEB` has `TableSyntax`); E5 comes back only if HTML that Markdown cannot express becomes common.
- **The LaTeX or style-sheet behaviour changes upstream** (U21, U22): the escaping stays correct either way, and the style sheet's explicit colours stay valid; drop the workaround in its own PR after a pin bump (D-64).
- **Open-space Markdown** cannot be escaped (it is Markdown): if a year's open spaces trigger LaTeX, escape `$`, `( ` and `[ ` in them before rendering, until U21 lands.

---
_Written by Claude Code (AI agent)._
