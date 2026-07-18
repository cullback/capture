"""LessWrong posts via GreaterWrong, the lightweight HTML frontend.

lesswrong.com is a React app whose server rendering carries misleading
dates (curation timestamps); greaterwrong.com serves the same content
as clean static HTML with the true post date and comments included.
"""

import re
from datetime import datetime, timezone

from capture.resolvers import base
from capture.resolvers.base import Resolution


def resolve_lesswrong(url: str) -> Resolution | None:
    post = lesswrong_post(url)
    if not post:
        return None
    post_id, slug = post
    source = f"https://www.lesswrong.com/posts/{post_id}/{slug}"
    content = f"https://www.greaterwrong.com/posts/{post_id}/{slug}"
    html = base.fetch_html(content)
    author = ""
    if match := re.search(r'<a class="author[^"]*"[^>]*>([^<]+)</a>', html):
        author = match.group(1).strip()
    publish = None
    if match := re.search(r"data-js-date=.?(\d{13})", html):
        stamp = datetime.fromtimestamp(int(match.group(1)) / 1000, timezone.utc)
        publish = stamp.date().isoformat()
    return Resolution(
        source=source,
        content=content,
        domain=f"lesswrong.com - {author_slug(author)}" if author else None,
        html=html,
        publish=publish,
        extra={"author": author},
    )


def lesswrong_post(url: str) -> tuple[str, str] | None:
    match = re.search(
        r"(?:lesswrong\.com|greaterwrong\.com|alignmentforum\.org)"
        r"/posts/([A-Za-z0-9]+)/([^/?#]+)",
        url,
    )
    return (match.group(1), match.group(2)) if match else None


def author_slug(author: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", author.lower())).strip("-")
