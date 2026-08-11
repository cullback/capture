# Capture

A CLI that saves a URL or local PDF as a self-contained archive folder,
holding the content in its most faithful form — a single-file HTML copy for
web pages, the typeset PDF for papers, archival video for YouTube, a git
bundle for repos — plus, for anything textual, a markdown conversion with
YAML frontmatter.

## Usage

```
$ capture https://bernsteinbear.com/blog/toy-fuzzer/
bernsteinbear.com - 2026-02-25 - a-fuzzer-for-the-toy-optimizer
```

That prints the capture folder, created in the current directory (or
wherever `-o` points), which contains:

```
bernsteinbear.com - 2026-02-25 - a-fuzzer-for-the-toy-optimizer/
├── bernsteinbear.com - 2026-02-25 - a-fuzzer-for-the-toy-optimizer.html
├── bernsteinbear.com - 2026-02-25 - a-fuzzer-for-the-toy-optimizer.md
└── media/
```

The flake installs the `capture` command: `nix profile install .` from a
checkout, or ad hoc `nix run . -- <url>`. The corpus lives at
`/vault/media/sites`; capture into it with `-o /vault/media/sites`, or by
running `capture <url>` from that directory.

Folder names follow `<domain> - <date> - <slug>`, ASCII only. The date comes
from the page's publish date and falls back to the capture date when no
publish date exists.

`--name` replaces that derivation, naming the folder and every file inside it,
for callers that already have an identifier and need the output path up front:

```
$ capture ./paper.pdf --name tareen2019 --no-frontmatter -o studies/
studies/tareen2019

studies/tareen2019/
├── tareen2019.pdf
├── tareen2019.md
└── media/
```

`--no-frontmatter` writes the markdown without the YAML block — for pipelines
that read the body as text and take metadata from elsewhere.

The `.html` file comes from [SingleFile](https://github.com/gildas-lormeau/single-file-cli)
driven by headless chromium: one file with styles and images inlined, rendering
offline as the page looked. The `.md` file holds the body converted by
[pandoc](https://pandoc.org/) through `capture/filters/clean.lua`, which restores KaTeX
display math to TeX, unwraps single-cell layout tables, and fences code blocks.
[dprint](https://dprint.dev/) formats the result. `media/` holds downloaded
images, referenced relatively.

The markdown opens with frontmatter:

```yaml
---
title: "A fuzzer for the Toy Optimizer"
domain: bernsteinbear.com
url: https://bernsteinbear.com/blog/toy-fuzzer/
capture_date: 2026-07-18
publish_date: 2026-02-25
---
```

`publish_date` gets omitted when unknown, recording that honestly. Other keys
appear when a source supplies them: `author`, `archive` for snapshot captures,
and source-specific extras such as `subreddit`, `score`, `stars`.

`discussions` lists threads about the page, richest first:

```yaml
discussions:
  - https://www.reddit.com/r/MachineLearning/comments/6gwqiw/
  - https://news.ycombinator.com/item?id=34649113
```

Hacker News and Reddit are searched by URL, lobsters by title. Only threads
with more than five comments are kept, one per subreddit, and general-interest
subreddits are excluded — r/todayilearned reposts a good link for a decade and
discusses the headline rather than the piece. An empty `discussions: []` says
the sources were searched and found nothing, which absence could not
distinguish from never having looked.

## Sources

A resolver per source decides what to fetch and from where. Adding a source
means adding a module under `capture/resolvers/` and registering it in
`RESOLVERS`, not adding a branch to the pipeline.

| URL                         | Capture                                                                                                                                                                                                               |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| arxiv abs/pdf/html          | Typeset PDF as the artifact, no `.html`; markdown from Datalab Marker conversion of the PDF; publish date from the abs page.                                                                                          |
| GitHub repo root            | README as the markdown plus a `.bundle` git bundle of the complete history, re-cloneable with `git clone`.                                                                                                            |
| GitHub blob / gist (`.md`)  | Raw markdown fetched directly; publish date from the path or the file's first commit.                                                                                                                                 |
| GitHub wiki page            | Raw markdown from the wiki's own git repo, no `.html`: the rendered page only wraps the source in repo chrome. Title from the page name, publish date from the page's first commit.                                   |
| YouTube                     | Archival mkv via [yt-dlp](https://github.com/yt-dlp/yt-dlp) with thumbnail, chapters, subtitles, and info-json embedded, plus a standalone `.info.json`. No markdown: the transcript lives in the embedded subtitles. |
| Reddit thread               | JSON from the [Arctic Shift](https://arctic-shift.photon-reddit.com/) archive rendered as a nested comment tree, since reddit blocks curl, urllib, and headless chromium outright. Scores reflect archive time.       |
| Wayback snapshot            | Content from the toolbar-free `id_` snapshot; naming, frontmatter, and HN lookup use the original URL; the snapshot date bounds undated pages.                                                                        |
| LessWrong / Alignment Forum | The [GreaterWrong](https://www.greaterwrong.com/) mirror, which serves static HTML with the true post date; lesswrong.com's server rendering carries curation timestamps instead.                                     |
| Substack post               | The article from Substack's own API, free of page chrome, plus the complete comment thread — the rendered page serves two comments and lazy-loads the rest. Detected by page signature, so custom domains work.       |
| Wikipedia                   | Chrome-free Parsoid HTML from the REST API; dateless by design.                                                                                                                                                       |
| PDF URLs                    | Downloaded PDF as the artifact plus Datalab markdown. Content sniffing catches URLs that serve a PDF without `.pdf` in the path.                                                                                      |
| archive.today               | The curl fetch as the artifact, because archive.today serves browsers a captcha. Frontmatter keeps both the original `url` and the `archive` snapshot.                                                                |
| everything else             | curl fetch plus browser archive, converted by pandoc.                                                                                                                                                                 |

## Local PDFs

Some publisher pages resist automation harder than a manual download costs:

```
capture ./paper.pdf --origin https://publisher.example/paper
```

`--origin` supplies provenance: the frontmatter `url`, the domain in the
folder name, and the dedup identity. Without it the capture files under
`pdf` with no `url`.

## Re-capturing

Dedup matches the URL against the frontmatter already at the destination,
after normalizing per-source spellings so any arxiv, youtube, reddit,
wayback, or lesswrong variant finds its canonical capture:

```
$ capture https://bernsteinbear.com/blog/toy-fuzzer/
already captured: bernsteinbear.com - 2026-02-25 - a-fuzzer-for-the-toy-optimizer
pass -f / --force to re-capture
```

## Failure behavior

A failed capture leaves nothing at the destination. The pipeline skips paywalled
pages that only serve a preview and prints why. 4xx/5xx responses and
bot-check interstitials served with HTTP 200 raise instead of archiving the
error page; 5xx responses get one retry after 3 seconds. When a bot check
blocks both curl and the browser archive, the pipeline asks the Wayback
Machine for its newest successful crawl of the URL and captures that
snapshot instead — dl.acm.org PDFs arrive this way, named for the original
URL with the snapshot recorded under `archive`.

## Requirements

The flake builds an installed tool (`nix profile install`, `nix run`) whose
wrapper carries every binary the pipeline shells out to: chromium,
single-file-cli, pandoc, yt-dlp, ffmpeg, poppler-utils, dprint, git, curl,
and fish. For development, the devShell (`nix develop` or direnv) provides
the same set; outside either, the browser archive fails and captures degrade
to the plain curl fetch.

`capture` is the only installed command. The pipeline's helper scripts ship
inside the package and are invoked from it, not from your PATH:

- `capture/scripts/single-file-archive` — SingleFile plus the hardened
  chromium flags that pass Cloudflare's headless detection. The flags live
  there canonically.
- `capture/pdf2md.py` — PDF-to-markdown via the
  [Datalab Marker API](https://www.datalab.to/), reading the key from
  `DATALAB_API_KEY` or `~/.config/datalab/key`. Run it alone with
  `python -m capture.pdf2md` for batch or `--mode fast` conversion without an
  archive folder.

Optional: Netscape-format cookies at `~/.config/capture/youtube-cookies.txt`
for age-restricted or member-only videos.

## Compared to alternatives

[ArchiveBox](https://archivebox.io/) also archives URLs locally, but it
treats every page uniformly. The resolvers here exist because uniform
treatment fails on the pages worth keeping: reddit blocks every automated
client, arxiv's HTML rendering falls short of the typeset PDF, lesswrong
reports wrong dates. The Wayback Machine preserves pages without giving you
a local, greppable copy; capture treats it as a source, not a substitute.
Read-later services store parsed text on someone else's server, which
reintroduces the problem.

## Testing

`just test` runs two suites:

- `tests/test_extraction.py` — unit tests for the metadata heuristics, one
  minimal reproduction per real site that forced a rule.
- `tests/test_corpus.py` — golden regression: re-runs title and date
  extraction over every stored capture in `data/` and compares against
  `tests/corpus-golden.jsonl`. After an intentional change, regenerate with
  `UPDATE_GOLDEN=1 pytest tests/test_corpus.py` and justify the git diff
  page by page.

`pytest -m live` opts into the end-to-end test that hits the network and
runs the browser.

`NOTES.md` keeps the case log of difficult captures: each entry names the
failure, the diagnosis, and where the fix lives.

## Development

`just` lists the recipes: `bootstrap` syncs dependencies, `check` runs
dprint, ruff, pyright, and nixfmt, `format` fixes what it can, and
`capture` runs the CLI from source with `-o data/`.
