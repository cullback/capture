"""Substack posts: the page as usual, plus the whole comment thread.

Substack server-renders two comments and loads the rest as you scroll,
so an archived page keeps 2 of 122 and ends in "[96 more comments...]".
Across the corpus that lost 1250 comments and kept 58. The JSON API
serves the full tree, already nested, so the comments are appended to
the converted article.

Detection is by page signature rather than hostname: most Substacks
worth reading run on their own domain (construction-physics.com,
noahpinion.blog, astralcodexten.com), and nothing in the URL says
Substack. Every Substack post does live at /p/<slug>, though, so the
path gates the check and the signature confirms it — no extra fetch for
the rest of the web.
"""

import json
import re
import subprocess
from urllib.parse import urlparse

from capture.resolvers import base
from capture.resolvers.base import FetchError, Resolution

# Substack's client bootstrap. Present on custom domains too, and
# absent from everything else.
SIGNATURE = "window._preloads"
SORT = "best_first"


def resolve_substack(url: str) -> Resolution | None:
    slug = post_slug(url)
    if not slug:
        return None
    try:
        html = base.fetch_html(url)
    except FetchError:
        # Let the default resolver decide what a failed fetch means.
        return None
    if SIGNATURE not in html:
        return None
    origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
    post = _get_json(f"{origin}/api/v1/posts/{slug}")
    return Resolution(
        source=url,
        content=url,
        html=html,
        # The API serves the piece alone. Converting the rendered page
        # instead drags in the nav, the subscribe furniture, and the two
        # comments substack does render — which would then repeat
        # verbatim inside the comment section appended below.
        article_html=post.get("body_html") or "",
        markdown_suffix=comment_section(origin, post),
    )


def post_slug(url: str) -> str | None:
    match = re.match(r"^/p/([^/?#]+)/?$", urlparse(url).path)
    return match.group(1) if match else None


def comment_section(origin: str, post: dict) -> str:
    """The post's comments as a nested markdown thread, or "" when the
    post has none or the API declines. Never raises: comments are a
    bonus, and losing them must not cost the capture."""
    post_id = post.get("id")
    if not post_id:
        return ""
    payload = _get_json(
        f"{origin}/api/v1/post/{post_id}/comments?all_comments=true&sort={SORT}"
    )
    comments = payload.get("comments") or []
    if not comments:
        return ""
    return render_comments(comments, post.get("comment_count"))


def render_comments(comments: list[dict], total: int | None = None) -> str:
    """Nested blockquotes by depth, mirroring the reddit renderer so a
    thread reads the same whichever site it came from."""
    counted = total if total is not None else count(comments)
    lines = ["", f"## Comments ({counted})", ""]

    def walk(nodes: list[dict], depth: int) -> None:
        for node in nodes:
            if node.get("deleted"):
                continue
            prefix = "> " * depth
            author = node.get("name") or "[deleted]"
            stamp = (node.get("date") or "")[:10]
            reactions = node.get("reaction_count") or 0
            byline = f"**{author}**"
            if stamp:
                byline += f" ({stamp}"
                byline += f", {reactions} reactions)" if reactions else ")"
            elif reactions:
                byline += f" ({reactions} reactions)"
            lines.append(f"{prefix}{byline}")
            lines.append(prefix.rstrip() if prefix else "")
            for line in (node.get("body") or "").splitlines():
                lines.append(f"{prefix}{line}".rstrip())
            lines.append("")
            walk(node.get("children") or [], depth + 1)

    walk(comments, 1)
    return "\n".join(lines) + "\n"


def count(nodes: list[dict]) -> int:
    return sum(1 + count(node.get("children") or []) for node in nodes)


def _get_json(api: str) -> dict:
    try:
        return json.loads(base.fetch_html(api))
    except (FetchError, subprocess.CalledProcessError, ValueError) as failure:
        print(f"substack api: {failure}")
        return {}
