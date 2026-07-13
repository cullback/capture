"""The capture pipeline: resolve, archive, convert, describe.

Each capture lands in its own folder:

    data/<domain> - <yyyy-mm-dd> - <slug>/
        <same name>.html   faithful single-file archive
        <same name>.md     markdown with TeX math preserved
        <same name>.pdf    canonical PDF, for sources that have one
        media/             downloaded images, referenced relatively
"""

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from capture.extract import (
    normalize,
    page_slug,
    page_title,
    published_date,
    slugify,
)
from capture.resolvers import Resolution, arxiv_id, hackernews_url, resolve

REPO_ROOT = Path(__file__).resolve().parent.parent

PANDOC_FORMAT = "html+tex_math_dollars+tex_math_single_backslash"


def capture(url: str) -> Path:
    resolution = resolve(url)
    domain = urlparse(resolution.source).netloc.removeprefix("www.")

    # single-file archives to a scratch path, since the folder name may
    # depend on metadata that only exists after rendering.
    scratch = None
    if resolution.use_browser:
        scratch = REPO_ROOT / "data" / ".capture.html"
        single_file(resolution.content, scratch)
        artifact_html = scratch.read_text()
    else:
        artifact_html = resolution.html

    # Client-rendered pages (e.g. AoPS, Obsidian Publish) serve a shell:
    # take metadata from the rendered DOM when the raw HTML carries no
    # title signal beyond the <title> tag.
    informative = page_title(resolution.html, domain, resolution.source) and re.search(
        r"<h1[\s>]|og:title", resolution.html
    )
    meta_html = resolution.html if informative else artifact_html
    title = resolution.title or page_title(meta_html, domain, resolution.source)
    publish = resolution.publish or published_date(resolution.source, meta_html)
    name_date = publish or date.today().isoformat()
    slug = slugify(title) or page_slug(resolution.source, meta_html)
    name = f"{domain} - {name_date} - {slug}"
    folder = REPO_ROOT / "data" / name
    folder.mkdir(parents=True, exist_ok=True)

    artifact = folder / f"{name}.html"
    if scratch:
        scratch.replace(artifact)
    else:
        artifact.write_text(artifact_html)

    if resolution.pdf_url:
        subprocess.run(
            [
                "curl",
                "-sL",
                "--max-time",
                "300",
                "-o",
                str(folder / f"{name}.pdf"),
                resolution.pdf_url,
            ],
            check=False,
        )

    # Prefer converting from the URL so relative image paths resolve; fall
    # back to the local artifact when the direct fetch fails or the raw
    # HTML had no real content. Ready-made markdown skips conversion.
    markdown = folder / f"{name}.md"
    if resolution.markdown is not None:
        markdown.write_text(resolution.markdown)
    elif (
        not resolution.use_browser
        or not pandoc(resolution.content, markdown.name, folder)
        or thin(markdown)
    ):
        pandoc(artifact.name, markdown.name, folder)

    markdown.write_text(frontmatter(resolution, title, publish) + markdown.read_text())
    format_markdown(markdown)
    return folder


def frontmatter(resolution: Resolution, title: str, publish: str | None) -> str:
    domain = urlparse(resolution.source).netloc.removeprefix("www.")
    lines = [
        "---",
        f"title: {json.dumps(title or 'Untitled')}",
        f"domain: {domain}",
        f"url: {resolution.source}",
    ]
    if resolution.archive:
        lines.append(f"archive: {resolution.archive}")
    if hn := hackernews_url(resolution.source):
        lines.append(f"hackernews: {hn}")
    lines.append(f"capture_date: {date.today().isoformat()}")
    if publish:
        # Omitted when no publish date was found: the folder falls back
        # to the capture date, and absence here records that honestly.
        lines.append(f"publish_date: {publish}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def single_file(url: str, output: Path) -> None:
    subprocess.run(
        [
            "single-file",
            "--browser-executable-path",
            shutil.which("chromium") or "chromium",
            # Look like a human browser: Cloudflare blocks headless
            # chromium's default fingerprint (e.g. on AoPS).
            "--browser-args",
            json.dumps(
                [
                    "--disable-blink-features=AutomationControlled",
                    "--user-agent=Mozilla/5.0 (X11; Linux x86_64)"
                    " AppleWebKit/537.36 (KHTML, like Gecko)"
                    " Chrome/145.0.0.0 Safari/537.36",
                ]
            ),
            "--filename-conflict-action",
            "overwrite",
            url,
            str(output),
        ],
        check=True,
    )


def pandoc(source: str, output: str, cwd: Path) -> bool:
    """Convert HTML (a URL or a file relative to cwd) to markdown."""
    result = subprocess.run(
        [
            "pandoc",
            "-f",
            PANDOC_FORMAT,
            "-t",
            "gfm-raw_html",
            "--wrap=none",
            f"--lua-filter={REPO_ROOT / 'filters' / 'clean.lua'}",
            "--extract-media=media",
            source,
            "-o",
            output,
        ],
        cwd=cwd,
    )
    return result.returncode == 0


def thin(markdown: Path) -> bool:
    return not markdown.exists() or len(markdown.read_text().split()) < 150


def format_markdown(markdown: Path) -> None:
    # Via stdin with a path outside data/, since dprint.json excludes
    # data/ to keep repo-wide `just format` off the captures.
    result = subprocess.run(
        ["dprint", "fmt", "--stdin", "capture.md"],
        input=markdown.read_text(),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode == 0 and result.stdout:
        markdown.write_text(result.stdout)


def existing_capture(url: str) -> Path | None:
    """The folder already holding this URL, matched via frontmatter."""
    target = normalize(url)
    if aid := arxiv_id(url):
        target = normalize(f"https://arxiv.org/abs/{aid}")
    for markdown in sorted((REPO_ROOT / "data").glob("*/*.md")):
        header = markdown.read_text(errors="replace")[:600]
        for line in header.splitlines():
            key, _, value = line.partition(": ")
            if key in ("url", "archive") and normalize(value.strip()) == target:
                return markdown.parent
    return None
