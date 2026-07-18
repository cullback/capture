"""Wikipedia articles via the REST API's clean Parsoid HTML."""

import re
from urllib.parse import unquote

from capture.resolvers import base
from capture.resolvers.base import Resolution


def resolve_wikipedia(url: str) -> Resolution | None:
    """Content from the REST API (chrome-free article HTML); articles
    are wiki pages, so dateless by design. The language edition stays
    in the domain (en.wikipedia.org, de.wikipedia.org)."""
    article = wikipedia_article(url)
    if not article:
        return None
    language, title = article
    source = f"https://{language}.wikipedia.org/wiki/{title}"
    content = f"https://{language}.wikipedia.org/api/rest_v1/page/html/{title}"
    return Resolution(
        source=source,
        content=content,
        html=base.fetch_html(content),
        title=unquote(title).replace("_", " "),
        dateless=True,
    )


def wikipedia_article(url: str) -> tuple[str, str] | None:
    match = re.search(r"([a-z-]+)(?:\.m)?\.wikipedia\.org/wiki/([^#?]+)", url)
    return (match.group(1), match.group(2)) if match else None
