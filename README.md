# capture

Capture web pages, PDFs, and HTML files as clean, well-structured markdown with automatic metadata extraction.

## Installation

```sh
nix profile install github:cullback/capture
```

## Usage

```
capture [-h] [-o OUTPUT] [-b BROWSER] [-d DOMAIN] [-n NAME] [--no-images] [input]

positional arguments:
  input                 URL, PDF, or HTML file to capture

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output directory (folder will be created inside)
  -b BROWSER, --browser BROWSER
                        Browser executable path
  -d DOMAIN, --domain DOMAIN
                        Override domain for PDF/HTML captures
  -n NAME, --name NAME  Override output folder name
  --no-images           Don't save image files
```

Output is a folder like `example.com - 2024-01-01 - article-title/` containing the markdown, the original HTML or PDF, and any extracted images.

## How it works

1. **Capture** the page as HTML (single-file + headless Chromium)
2. **Convert** to PDF for visual layout, extract links/images via Pandoc
3. **Generate** clean markdown with a vision LLM, applying cleanup rules (hyphenation reflow, LaTeX normalization, layout linearization, artifact removal)
4. **Extract metadata** (title, date, tags) using a curated tag taxonomy
5. **Format** with dprint and write YAML frontmatter

For PDFs and HTML files, the pipeline adapts: PDFs skip the browser capture; HTML files from SingleFile automatically recover the original URL from embedded metadata.
