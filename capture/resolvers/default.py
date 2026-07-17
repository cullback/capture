"""Plain pages, archive.today snapshots, and path-identity platforms."""

import re
from urllib.parse import urlparse

from capture.resolvers import base
from capture.resolvers.base import Resolution

ARCHIVE_HOSTS = {"archive.is", "archive.ph", "archive.today", "archive.md"}

# Platforms hosting many authors under one domain, with the author or
# publication as the first path segment: fold it into the folder name
# the way youtube does with @handles.
PATH_IDENTITY_HOSTS = {"medium.com", "buttondown.com"}


def resolve_default(url: str) -> Resolution:
    """Plain pages, plus archive.today snapshots resolved to their
    original identity. Archive.today challenges browsers with a
    captcha, so the plain fetch is the best artifact we can get there."""
    try:
        html = base.fetch_html(url)
    except base.FetchError as error:
        if not error.refused:
            raise  # 404s and server errors stay fatal (miraheze)
        # Sites that refuse plain clients may serve real browsers
        # (quarter--mile.com 429s curl): let the browser supply
        # everything, including metadata.
        return Resolution(source=url, content=url)
    source = original_url(url, html)
    return Resolution(
        source=source,
        content=url,
        domain=path_identity_domain(source),
        html=html,
        archive=url if source != url else None,
        use_browser=source == url,
    )


def original_url(url: str, html: str) -> str:
    """The archived page's source URL, for archive.today snapshots."""
    if urlparse(url).netloc.removeprefix("www.") not in ARCHIVE_HOSTS:
        return url
    match = re.search(
        r'rel="canonical" href="https?://archive\.\w+/[^"/]+/(https?://[^"]+)"', html
    )
    return match.group(1) if match else url


def path_identity_domain(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.removeprefix("www.")
    segments = [s for s in parsed.path.split("/") if s]
    if host in PATH_IDENTITY_HOSTS and len(segments) >= 2:
        return f"{host} - {segments[0]}"
    return None
