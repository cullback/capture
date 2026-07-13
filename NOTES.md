# Difficult captures

Case log of pages that broke the pipeline and the fixes they forced.
Each entry names the failure, the diagnosis, and where the fix lives.
When a new page defeats every trick here, that marks the point to
escalate to a stealth browser like zendriver (CDP-based, no webdriver
fingerprint, can carry real profile cookies).

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
  posts would capture only the free preview.
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

## First heuristic defeat: blog.vortan.dev

The ematching post publishes no date at all: none in the page, none in
metadata, no RSS/Atom feed exists, none in the URL. The real date
(April 17, 2025) appears only on the blog index, in a `span.date`
adjacent to the post link. Extracting "the date nearest a link on a
different page" mechanically crosses into guesswork, so the capture
keeps the fallback capture-date. This is the designated trigger case
for the LLM date fallback.

## Current fetcher matrix

| Fetcher                  | Runs JS | Fingerprint                    | Role                                  |
| ------------------------ | ------- | ------------------------------ | ------------------------------------- |
| curl                     | no      | passes every WAF met so far    | identity HTML, archive.today artifact |
| chromium via single-file | yes     | needs de-automation flags      | rendered archive, SPA fallback        |
| pandoc's HTTP client     | no      | weakest; blocked by archive.is | URL conversion, image downloads       |

Every regression above has a matching test in
`tests/test_extraction.py`.
