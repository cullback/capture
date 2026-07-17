"""GitHub blob and gist URLs: the raw file IS the markdown."""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from capture.resolvers import base
from capture.resolvers.base import Resolution


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
        domain=gh["domain"],
        html=base.fetch_html(url),
        publish=gh["publish"],
        markdown=gh["markdown"],
        title=heading.group(1).strip() if heading else gh["name"],
    )


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
        text = base.fetch_html(raw_url)
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
        return {
            "markdown": text,
            "publish": publish,
            "name": Path(path).stem,
            "domain": f"github.com - {owner}",
        }
    gist = re.search(r"gist\.github\.com/([^/]+)/([a-f0-9]+)", url)
    if gist:
        user, gist_id = gist.groups()
        api = json.loads(base.fetch_html(f"https://api.github.com/gists/{gist_id}"))
        for filename, info in api.get("files", {}).items():
            if filename.lower().endswith((".md", ".markdown")):
                return {
                    "markdown": info["content"],
                    "publish": (api.get("created_at") or "")[:10] or None,
                    "name": Path(filename).stem,
                    "domain": f"gist.github.com - {user}",
                }
    return None
