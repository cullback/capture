# Difficult captures

Case log of pages that broke the pipeline and the fixes they forced.
Each entry names the failure, the diagnosis, and where the fix lives.
dl.acm.org was the page that defeated every fetcher; the fix was the
Wayback Machine fallback, not a stealth browser (see its entry below).

## artofproblemsolving.com (Cloudflare + client-rendered SPA)

The hardest capture so far. Four independent failures on one page:

1. **WAF blocks urllib at the fingerprint level.** Python's urllib got
   403 regardless of headers, while `curl -A capture/0.1` got 200 with
   the same user agent, so the block keys on the TLS/client fingerprint
   rather than headers. Fix: `fetch_html` shells out to curl
   (`capture/__main__.py`).
2. **Cloudflare blocks headless chromium.** single-file's browser got a
   "Sorry, you have been blocked" page. Fix: launch chromium with
   `--disable-blink-features=AutomationControlled` plus a real Chrome
   user-agent string. Two flags sufficed; no stealth library needed.
3. **The raw HTML is an empty shell.** The forum renders client-side,
   so curl's 2.8MB response contained an empty `<title>` and one
   mention of the post topic. Fix: when the raw HTML has no title or
   the converted markdown lands under 150 words, take metadata and
   markdown from the single-file rendered DOM instead.
4. **Math lives in image alt text.** AoPS serves formulas as
   `<img alt="$x^2+y^2=z^2$">`. Fix: `filters/clean.lua` converts any
   image whose alt text looks like TeX into real pandoc math.

Two extraction bugs surfaced on the same page. The page h1 held the
blog name ("Turtle Math") while `<title>` read "Turtle Math : The
Emoji Problem: Part I"; the fix strips an h1 prefix from `<title>` and
keeps the remainder. And single-file stamps its save date into an HTML
comment, which the body-date scan read back as the publish date; the
fix strips comments before scanning.

## bloomberg.com via archive.is (captcha for browsers, not for curl)

Bloomberg paywalls the original, so the capture goes through an
archive.today snapshot. Three findings:

1. **archive.is serves browsers a captcha but plain clients pass.**
   Both single-file's chromium and pandoc's fetcher got Cloudflare
   challenge pages while curl got the full 1.28MB snapshot. Fix: for
   archive hosts, skip the browser entirely, save the curl fetch as
   the artifact, and convert markdown from that file.
2. **The snapshot's identity is wrong.** Naming from the snapshot
   gives domain archive.is and the archive date 2020-09-29 instead of
   the publish date 2015-04-22. Fix: extract the original URL from the
   snapshot's `<link rel="canonical">`, which embeds it
   (`archive.is/<timestamp>/<original-url>`), and derive domain, slug,
   date, and the Hacker News lookup from the original. The frontmatter
   keeps both (`url:` original, `archive:` snapshot).
3. **URL dates outrank page metadata.** The snapshot's own metadata
   carries the archive date, but the Bloomberg URL path carries
   2015-04-22. The extractor now checks URL-path dates first.

This path depends on archive.today continuing to serve plain clients.
If that stops, the fallback is a stealth browser with real cookies.

## Lesser fights

- **Substack**: works. Server-rendered with JSON-LD dates. Long list
  posts split into multiple `<ol>` blocks, so numbering restarts
  mid-post on the live page too; the markdown mirrors the site. About
  30 lines of subscribe/share chrome leak into the markdown. Paywalled
  posts (Substack's only_paid audience marker) are detected and
  skipped without writing anything: only a preview is public.
- **austinhenley.com**: no date metadata anywhere; the date appears
  only as `<small>8/31/2025</small>` body text, which forced the
  US-slash-date tier of `body_date`. Older posts lack og:title and
  their `<title>` disagrees with the on-page h1, which set the title
  preference order og:title, then h1, then `<title>`.
- **gregorygundersen.com**: KaTeX rendered server-side. Pandoc
  recovers the TeX from the MathML annotations, but display equations
  arrive as inline math; `filters/clean.lua` promotes anything inside
  a `katex-display` span back to display math.
- **JS-mathjax blogs (lilianweng.github.io)**: the rendered DOM
  explodes each equation into spans (9.2MB of markdown from one post).
  The raw curl HTML still holds the original `$$...$$`, which is why
  markdown converts from the raw fetch rather than the rendered DOM.

## Title extraction is a scored candidate set

The ordered rule cascade broke twice from rules interacting (the AoPS
prefix rule misfired on Headlands; the length fallback misfired on
gameprogrammingpatterns), so `extract.page_title` now generates
candidates (og:title in four attribute spellings, class-marked
headings, first h1, `<title>`, wrap remainders) and ranks them by
source priors plus a gated slug-affinity bonus and site-name
penalties. Generation rules only add to the set, so they compose;
conflicts resolve numerically. The rewrite reproduced the cascade's
output on all 109 captured artifacts. Lessons encoded as scores:

- h1s linking to the site root are mastheads, and their text is the
  site's display name, stripped as a title prefix (eli.li bakes
  "Oatmeal - " into og:title).
- Blogger writes `content=` before `property=`, single-quoted; eev.ee
  writes `name="og:title"`.
- Obsidian Publish has no h1; the title is an h2
  (publish-article-heading), and pages expose no dates at all.
- The URL slug arbitrates "Title · Section" vs "Section : Title"
  document titles, via gated `difflib` similarity so truncated slugs
  still match.

## GitHub blobs and gists: skip conversion

Blob URLs ending in .md fetch the raw file: it IS the markdown.
Title from the file's first heading, date from a /YYYY/M/D/ path,
relative images rebased onto raw.githubusercontent.com. Gists go
through the gist API, which also supplies created_at. The browser
still archives the rendered page as the .html artifact.

## Code blocks and formatting

- Pandoc writes code fences only when the block carries a language;
  syntax-highlighter classes ("highlight") get dropped by the gfm
  writer, producing indented blocks. `filters/clean.lua` normalizes:
  junk classes become `text`, and Jekyll/Rouge's language lives on an
  ancestor div (`language-ruby`) that gets pushed down onto the block.
- Captured markdown is dprint-formatted at capture time (via stdin,
  dodging the data/ exclude). The exclude exists because repo-wide
  `just format` once reformatted 67MB of captures and took minutes.

## reddit.com: first full fetch-stack defeat, solved by Arctic Shift

Reddit blocks curl, urllib, and de-automated headless chromium alike
("blocked by network security") — the first site to defeat every
fetcher. Instead of escalating to cookies or a stealth browser, the
resolver uses the Arctic Shift archive (the Pushshift successor):
public JSON with comment bodies already in markdown. Threads render as
score-sorted nested blockquotes; scores reflect archive time, not
live. Pagination needs sort=asc — the API's default ordering
interleaves dates, so a created-time cursor silently skips comments.
No HTML artifact exists for these captures. If Arctic Shift ever goes
the way of Pushshift, this becomes the zendriver/cookies trigger again.

## First heuristic defeat: blog.vortan.dev

The ematching post publishes no date at all: none in the page, none in
metadata, no RSS/Atom feed exists, none in the URL. The real date
(April 17, 2025) appears only on the blog index, in a `span.date`
adjacent to the post link. Extracting "the date nearest a link on a
different page" mechanically crosses into guesswork, so the capture
keeps the fallback capture-date. This is the designated trigger case
for the LLM date fallback.

## Direct PDFs: datalab API via dotfiles pdf2md

PDF URLs resolve to the PDF as the canonical artifact (pdfinfo
metadata for date/author) plus layout-aware markdown. Conversion runs
through the dotfiles `pdf2md` script (Datalab Marker API, GPU-backed,
seconds per paper, DATALAB_API_KEY from ~/.config/datalab/key), with a
local marker_single install as fallback and PDF-only capture as the
floor. Local marker was tried first and worked (~50s/page on CPU,
3.3GB model cache) but cost a 6GB torch venv and two NixOS shims
(LD_LIBRARY_PATH for manylinux wheels; unset PYTHONPATH because
nixpkgs yt-dlp leaks its python3.13 closure — both shims kept in the
flake as they protect any future wheel). PDF titles prefer the
converted document's first heading: pdfinfo Title is often the LaTeX
source filename.

A blind side-by-side review (LaTeXML/pandoc vs datalab, two papers)
found datalab decisively cleaner AND more complete: LaTeXML dropped
the Attention paper's two main results tables and one paper's central
equation block as [TABLE], letter-split identifiers with \hspace{0pt},
and renumbered bibliographies. Datalab's known failure mode is OCR
corruption of proper nouns (FRACSTRAN for FRACTRAN, misspelled author
emails) and occasional invention (speculative mermaid diagrams for
figures, added diacritics). Equations sampled clean in both. The PDF
in each capture is ground truth for anything load-bearing.

## Silent browser degradation (puppeteer's default executable)

A wikipedia batch produced captures whose HTML artifact was the plain
fetch, with only a "browser capture failed" warning to show for it.
The dotfiles single-file-archive script never passed
`--browser-executable-path`, so puppeteer looked for a binary named
`chrome` — which NixOS doesn't provide — and it had only ever worked
when chromium happened to resolve some other way. The script now
detects chromium/chromium-browser/google-chrome-stable on PATH
(`capture/scripts/single-file-archive`, since moved in from dotfiles).
Corollary: captures must run inside the devShell (`nix develop`) or
the installed flake app, which supply chromium and single-file;
outside them the pipeline degrades rather than fails, so watch for
that warning line in batch output.

## dl.acm.org (Cloudflare that de-automation flags can't pass)

The first page to defeat both fetchers, resolved by the Wayback
Machine rather than a stealth browser. Findings:

1. **curl gets a decoy, not a challenge.** ACM serves curl HTTP 200
   with a 33KB site shell — empty `<title>`, no challenge markers — so
   neither content sniffing nor `challenge_page` fires at resolve
   time. On other requests it 403s. Either way the PDF never arrives.
2. **single-file's chromium gets "Just a moment..."** The
   de-automation flags that pass AoPS's Cloudflare don't pass ACM's.
   This is where the failure finally becomes detectable: the pipeline's
   bot-check gate on the archived artifact.
3. **zendriver would work, but wasn't worth it.** A stealth-browser
   spike did fetch the PDF (the challenge clears invisibly; an in-page
   `fetch()` carrying the clearance cookies returns it — a trick from
   revv2's study downloader). Reverted: it was the project's first
   Python dependency (plus ~8 transitive), for one site, in an
   arms race Cloudflare updates and snapshots don't.
4. **The Wayback Machine already got through.** Its crawler holds real
   200 PDF snapshots between the 403s. Fix, following the
   reddit→Arctic Shift pattern of sidestepping rather than fighting:
   when the bot-check gate would raise, `wayback_fallback` asks the
   CDX API for the newest statuscode-200 snapshot and recaptures
   through it (`capture/resolvers/wayback.py`). The wayback resolver
   now also sniffs `%PDF-` snapshots and routes them through the PDF
   path under the original URL's identity, so the folder is named for
   dl.acm.org and the frontmatter keeps `url:` original plus
   `archive:` snapshot.

The fallback rescues anything wayback crawled successfully, PDF or
HTML. A bot-checked page with no lucky snapshot still fails; the
remaining outs are a manual download (`--origin`) or, if it ever earns
its dependency, zendriver.

## Current fetcher matrix

| Fetcher                  | Runs JS | Fingerprint                    | Role                                  |
| ------------------------ | ------- | ------------------------------ | ------------------------------------- |
| curl                     | no      | passes every WAF except ACM's  | identity HTML, archive.today artifact |
| chromium via single-file | yes     | needs de-automation flags      | rendered archive, SPA fallback        |
| pandoc's HTTP client     | no      | weakest; blocked by archive.is | URL conversion, image downloads       |

When every fetcher loses, the Wayback Machine's own crawl stands in
(`wayback_fallback`), and after that a manual browser download via
`--origin`.

Every regression above has a matching test in
`tests/test_extraction.py`.
