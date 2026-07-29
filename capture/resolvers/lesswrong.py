"""LessWrong posts via GreaterWrong, the lightweight HTML frontend.

lesswrong.com is a React app whose server rendering carries misleading
dates (curation timestamps); greaterwrong.com serves the same content
as clean static HTML with the true post date and comments included.
"""

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from capture.extract import page_title
from capture.resolvers import base
from capture.resolvers.base import Resolution

# Kept in step with pipeline.PANDOC_FORMAT; duplicated rather than imported
# because pipeline imports this package (importing back would be circular).
PANDOC_FORMAT = "html+tex_math_dollars+tex_math_single_backslash"


def resolve_lesswrong(url: str) -> Resolution | None:
    if wiki := lesswrong_wiki(url):
        # Wiki pages: no single author, no publish date (they evolve),
        # and greaterwrong titles them "Name tag".
        html = base.fetch_html(f"https://www.greaterwrong.com/tag/{wiki}")
        title = page_title(html, "lesswrong.com")
        return Resolution(
            source=f"https://www.lesswrong.com/w/{wiki}",
            content=f"https://www.greaterwrong.com/tag/{wiki}",
            html=html,
            title=re.sub(r"\s+tag$", "", title) if title else None,
            dateless=True,
        )
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
        markdown=greaterwrong_markdown(html),
        extra={"author": author},
    )


def greaterwrong_markdown(html: str) -> str | None:
    """Convert a GreaterWrong post page to markdown with the comment thread
    intact, or None to let the pipeline fall back to its own conversion.

    Two GreaterWrong quirks make the default URL conversion lose comments:
    pandoc's HTML reader discards everything after a closing </main>, and
    GreaterWrong renders the comment thread there, so <main> is demoted to
    a plain <div>. Image and link targets are site-relative
    (/proxy-assets/..., /users/...); make them absolute so the pipeline can
    localize images and the links stay live outside the site.
    """
    html = re.sub(r"<main\b[^>]*>", "<div>", html).replace("</main>", "</div>")
    html = re.sub(
        r"(\b(?:href|src)=)(['\"])(/(?!/)[^'\"]*)\2",
        lambda m: f'{m.group(1)}"https://www.greaterwrong.com{m.group(3)}"',
        html,
    )
    filter_path = Path(__file__).resolve().parent.parent / "filters" / "clean.lua"
    try:
        result = subprocess.run(
            [
                "pandoc",
                "-f",
                PANDOC_FORMAT,
                "-t",
                "gfm-raw_html",
                "--wrap=none",
                f"--lua-filter={filter_path}",
                "-o",
                "-",
            ],
            input=html.encode(),
            stdout=subprocess.PIPE,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.decode()


def lesswrong_post(url: str) -> tuple[str, str] | None:
    match = re.search(
        r"(?:lesswrong\.com|greaterwrong\.com|alignmentforum\.org)"
        r"/posts/([A-Za-z0-9]+)/([^/?#]+)",
        url,
    )
    return (match.group(1), match.group(2)) if match else None


def lesswrong_wiki(url: str) -> str | None:
    match = re.search(r"(?:lesswrong\.com|greaterwrong\.com)/(?:w|tag)/([^/?#]+)", url)
    return match.group(1) if match else None


def author_slug(author: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", author.lower())).strip("-")
