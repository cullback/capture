"""Wayback Machine snapshots, resolved to their original identity."""

import json
import re
from urllib.parse import quote

from capture.resolvers import base
from capture.resolvers.base import Resolution
from capture.resolvers.default import path_identity_domain


def resolve_wayback(url: str) -> Resolution | None:
    """Identity (naming, frontmatter, HN lookup) belongs to the original
    URL; content comes from the id_ form of the snapshot, which serves
    the original HTML without the Wayback toolbar. Relative assets
    still resolve through web.archive.org."""
    snapshot = wayback_snapshot(url)
    if not snapshot:
        return None
    timestamp, original = snapshot
    content = f"https://web.archive.org/web/{timestamp}id_/{original}"
    html = base.fetch_html(content)
    if html.startswith("%PDF-"):
        # The snapshot stored a PDF, not a page: capture it as one,
        # under the original URL's identity.
        from capture.resolvers.pdf import pdf_resolution

        if resolution := pdf_resolution(content):
            resolution.source = original
            resolution.archive = f"https://web.archive.org/web/{timestamp}/{original}"
            return resolution
    return Resolution(
        source=original,
        content=content,
        domain=path_identity_domain(original),
        html=html,
        archive=f"https://web.archive.org/web/{timestamp}/{original}",
        # The snapshot date bounds the publish date far better than the
        # capture date, for pages that state no date of their own.
        fallback_date=f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
        if len(timestamp) >= 8
        else None,
    )


def wayback_snapshot(url: str) -> tuple[str, str] | None:
    match = re.search(r"web\.archive\.org/web/(\d{4,14})(?:id_)?/(https?://.+)", url)
    return (match.group(1), match.group(2)) if match else None


def wayback_fallback(url: str) -> str | None:
    """The newest snapshot whose crawl got a real 200, for pages whose
    live fetch yields only a bot check (dl.acm.org PDFs). None when
    the url already is a snapshot, or when no lucky crawl exists."""
    if wayback_snapshot(url):
        return None
    query = (
        "https://web.archive.org/cdx/search/cdx?output=json"
        "&filter=statuscode:200&limit=-1&url=" + quote(url, safe="")
    )
    try:
        rows = json.loads(base.fetch_html(query))
    except Exception:  # best-effort probe; any failure means no fallback
        return None
    if len(rows) < 2:  # first row is the CDX header
        return None
    timestamp = rows[-1][1]
    return f"https://web.archive.org/web/{timestamp}/{url}"
