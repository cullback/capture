"""Shared resolver primitives: the Resolution contract and the fetcher."""

import subprocess
import time
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
    save_html: bool = True  # keep the .html artifact (False when the
    # canonical artifact is something else, e.g. a paper's PDF)
    publish: str | None = None  # publish date, when the source knows it
    archive: str | None = None  # snapshot URL, for archived pages
    markdown: str | None = None  # ready-made body, skipping pandoc
    skip_markdown: bool = False  # media captures describe themselves
    title: str | None = None  # title override
    pdf_url: str | None = None  # extra artifact to download
    extra: dict[str, str] = field(default_factory=dict)  # frontmatter additions
    fallback_date: str | None = None  # folder date when no publish date exists
    dateless: bool = False  # wiki-like pages: suppress date detection
    download_media: Callable[[Path, str], None] | None = None  # (folder, name)


def find_tool(name: str) -> str | None:
    """PATH lookup plus ~/.local/bin, which non-interactive shells miss."""
    import shutil

    if found := shutil.which(name):
        return found
    candidate = Path.home() / ".local" / "bin" / name
    return str(candidate) if candidate.exists() else None


def fetch_html(url: str, retry: bool = True) -> str:
    # curl rather than urllib: WAFs (e.g. AoPS) block urllib's client
    # fingerprint no matter what headers it sends.
    result = subprocess.run(
        [
            "curl",
            "-sL",
            # Wayback id_ snapshots replay original responses verbatim,
            # including gzip bodies.
            "--compressed",
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
    )
    body, _, status = result.stdout.decode("utf-8", errors="replace").rpartition("\n")
    if status.startswith("5") and retry:
        # Server errors are often transient (wayback 500s under load).
        time.sleep(3)
        return fetch_html(url, retry=False)
    if status.startswith(("4", "5")):
        # Error pages (404s, block pages) must not be archived as content.
        raise FetchError(int(status), url)
    return body


class FetchError(RuntimeError):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status

    @property
    def refused(self) -> bool:
        """Client rejected (a real browser may still succeed), as opposed
        to content that is missing or a server that is broken."""
        return self.status in (401, 403, 429)
