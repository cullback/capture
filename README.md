# capture

Converts web pages, PDFs, and HTML files into clean, well-structured markdown with automatically extracted metadata. Combines Reducto (for math/tables), Pandoc (for images/links), and an LLM to produce faithful markdown from any source.

## Installation

Requires NixOS with flakes:

```sh
direnv allow   # loads nix shell + venv
just bootstrap # installs Python dependencies
```

You'll also need a `REDUCTO_API_KEY` environment variable (add to `.env`).

## Usage

```sh
# Capture a URL
just run https://example.com/article -o data

# Capture a local PDF
just run paper.pdf -o data

# Capture a local HTML file (e.g. saved with SingleFile)
just run page.html -o data

# Skip Reducto, use Pandoc only
just run https://example.com/article -o data --no-reducto

# Re-extract tags for an existing capture
just run --retag data/example.com-2024-01-01-some-article/
```

Output is a folder like `data/example.com - 2024-01-01 - article-title/` containing the markdown, the original HTML or PDF, and any extracted images.

## How it works

1. **Capture** the page as HTML (`single-file` + headless Chromium)
2. **Convert** to PDF, then extract markdown via Reducto (math, tables) and Pandoc (images, links)
3. **Merge** the two markdown versions with an LLM, applying cleanup rules (hyphenation reflow, LaTeX normalization, layout linearization, artifact removal)
4. **Extract metadata** (title, date, tags) using a curated tag taxonomy
5. **Format** with dprint and write YAML frontmatter

For PDFs and HTML files, the pipeline adapts: PDFs skip the browser capture and get single-source LLM cleanup; HTML files from SingleFile automatically recover the original URL from embedded metadata.

## Features

- **Dual-engine extraction** -- Reducto for precise math/tables, Pandoc for images/links, LLM merges the best of both
- **Automatic metadata** -- title, publish date, and 2-8 topic tags from a curated taxonomy
- **HackerNews lookup** -- finds and links the most-discussed HN thread for each URL
- **Multiple input formats** -- URLs, PDFs, and HTML files (including SingleFile saves with embedded URL recovery)
- **Re-tagging** -- update metadata on existing captures without re-downloading
