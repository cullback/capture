"""Shared resolver primitives: the Resolution contract and the fetcher."""

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Resolution:
    source: str  # identity URL: naming, frontmatter, HN lookup
    content: str  # URL to render and convert
    domain: str | None = None  # folder-name leading segment(s) override
    html: str = ""  # fetched identity page ("" = no HTML artifact)
    use_browser: bool = True  # single-file the content URL
    publish: str | None = None  # publish date, when the source knows it
    archive: str | None = None  # snapshot URL, for archived pages
    markdown: str | None = None  # ready-made body, skipping pandoc
    skip_markdown: bool = False  # media captures describe themselves
    title: str | None = None  # title override
    pdf_url: str | None = None  # extra artifact to download
    extra: dict[str, str] = field(default_factory=dict)  # frontmatter additions
    download_media: Callable[[Path, str], None] | None = None  # (folder, name)


def fetch_html(url: str) -> str:
    # curl rather than urllib: WAFs (e.g. AoPS) block urllib's client
    # fingerprint no matter what headers it sends.
    result = subprocess.run(
        [
            "curl",
            "-sL",
            "--max-time",
            "120",
            "-A",
            "capture/0.1",
            url,
            "-w",
            "\n%{http_code}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    body, _, status = result.stdout.rpartition("\n")
    if status.startswith(("4", "5")):
        # Error pages (404s, block pages) must not be archived as content.
        raise RuntimeError(f"HTTP {status} for {url}")
    return body
