"""Per-source resolution: what to fetch, from where, and what's known upfront.

Each resolver recognizes one kind of URL (arxiv paper, GitHub markdown,
archive.today snapshot) and returns a Resolution describing how to
capture it. Adding an ingestion source (YouTube, Wikipedia, repos)
means adding a resolver here, not a branch in the pipeline.
"""

import json
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from capture.extract import body_date, normalize


@dataclass
class Resolution:
    source: str  # identity URL: naming, frontmatter, HN lookup
    content: str  # URL to render and convert
    html: str  # fetched identity page
    use_browser: bool = True  # single-file the content URL
    publish: str | None = None  # publish date, when the source knows it
    archive: str | None = None  # snapshot URL, for archived pages
    markdown: str | None = None  # ready-made body, skipping pandoc
    title: str | None = None  # title override
    pdf_url: str | None = None  # extra artifact to download


def resolve(url: str) -> Resolution:
    return resolve_arxiv(url) or resolve_github(url) or resolve_default(url)


def fetch_html(url: str) -> str:
    # curl rather than urllib: WAFs (e.g. AoPS) block urllib's client
    # fingerprint no matter what headers it sends.
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "120", "-A", "capture/0.1", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def resolve_arxiv(url: str) -> Resolution | None:
    """Identity from the abs page; content from the HTML rendering,
    which is generated from the LaTeX source so math survives."""
    aid = arxiv_id(url)
    if not aid:
        return None
    source = f"https://arxiv.org/abs/{aid}"
    html = fetch_html(source)
    return Resolution(
        source=source,
        content=arxiv_content_url(aid),
        html=html,
        publish=arxiv_published(html),
        pdf_url=f"https://arxiv.org/pdf/{aid}",
    )


def resolve_github(url: str) -> Resolution | None:
    """The markdown body comes straight from the raw file; the browser
    still archives the rendered page."""
    gh = github_markdown(url)
    if not gh:
        return None
    heading = re.search(r"^#\s+(.+)$", gh["markdown"], re.M)
    return Resolution(
        source=url,
        content=url,
        html=fetch_html(url),
        publish=gh["publish"],
        markdown=gh["markdown"],
        title=heading.group(1).strip() if heading else gh["name"],
    )


def resolve_default(url: str) -> Resolution:
    """Plain pages, plus archive.today snapshots resolved to their
    original identity. Archive.today challenges browsers with a
    captcha, so the plain fetch is the best artifact we can get there."""
    html = fetch_html(url)
    source = original_url(url, html)
    return Resolution(
        source=source,
        content=url,
        html=html,
        archive=url if source != url else None,
        use_browser=source == url,
    )


def arxiv_id(url: str) -> str | None:
    match = re.search(
        r"(?:ar5iv\.labs\.arxiv|arxiv)\.org/(?:abs|pdf|html|e-print)/(\d{4}\.\d{4,5})",
        url,
    )
    return match.group(1) if match else None


def arxiv_content_url(aid: str) -> str:
    """The paper's HTML rendering: official when it exists, else ar5iv."""
    official = f"https://arxiv.org/html/{aid}"
    status = subprocess.run(
        ["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}", official],
        capture_output=True,
        text=True,
    ).stdout
    return official if status == "200" else f"https://ar5iv.labs.arxiv.org/html/{aid}"


def arxiv_published(html: str) -> str | None:
    """The v1 submission date from an abs page ("Submitted on 27 Mar 2026")."""
    if match := re.search(r"Submitted on (\d{1,2} [A-Za-z]{3,9},? \d{4})", html):
        return body_date(match.group(1))
    return None


def github_markdown(url: str) -> dict | None:
    """Raw markdown and metadata for GitHub blob and gist URLs.

    These files ARE markdown: fetching the raw source beats converting
    GitHub's rendered chrome back into markdown.
    """
    blob = re.search(
        r"github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+\.(?:md|markdown))$", url, re.I
    )
    if blob:
        owner, repo, ref, path = blob.groups()
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
        text = fetch_html(raw_url)
        # Rebase relative image links onto the raw host.
        text = re.sub(
            r"(!\[[^\]]*\]\()(?!https?://|#|data:)([^)\s]+)",
            lambda m: m.group(1) + urljoin(raw_url, m.group(2)),
            text,
        )
        publish = None
        if match := re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", f"/{path}"):
            year, month, day = (int(g) for g in match.groups())
            if 1 <= month <= 12 and 1 <= day <= 31:
                publish = f"{year}-{month:02d}-{day:02d}"
        return {"markdown": text, "publish": publish, "name": Path(path).stem}
    gist = re.search(r"gist\.github\.com/[^/]+/([a-f0-9]+)", url)
    if gist:
        api = json.loads(fetch_html(f"https://api.github.com/gists/{gist.group(1)}"))
        for filename, info in api.get("files", {}).items():
            if filename.lower().endswith((".md", ".markdown")):
                return {
                    "markdown": info["content"],
                    "publish": (api.get("created_at") or "")[:10] or None,
                    "name": Path(filename).stem,
                }
    return None


ARCHIVE_HOSTS = {"archive.is", "archive.ph", "archive.today", "archive.md"}


def original_url(url: str, html: str) -> str:
    """The archived page's source URL, for archive.today snapshots."""
    if urlparse(url).netloc.removeprefix("www.") not in ARCHIVE_HOSTS:
        return url
    match = re.search(
        r'rel="canonical" href="https?://archive\.\w+/[^"/]+/(https?://[^"]+)"', html
    )
    return match.group(1) if match else url


def hackernews_url(url: str) -> str | None:
    """Best-scoring HN submission of this URL, via the Algolia search API."""
    api = (
        "https://hn.algolia.com/api/v1/search"
        f"?query={quote(url, safe='')}&restrictSearchableAttributes=url&hitsPerPage=20"
    )
    try:
        with urllib.request.urlopen(api, timeout=10) as response:
            hits = json.load(response)["hits"]
    except OSError:
        return None
    matches = [h for h in hits if normalize(h.get("url") or "") == normalize(url)]
    if not matches:
        return None
    best = max(matches, key=lambda h: h.get("points") or 0)
    return f"https://news.ycombinator.com/item?id={best['objectID']}"
