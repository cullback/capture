"""Hacker News threads via the Algolia API, comments included.

The item page lays the whole discussion out in nested <table> elements
that pandoc collapses to a single "[TABLE]"; the Algolia API returns the
same thread as structured JSON, so the comments convert cleanly.
"""

import html
import json
import re
from datetime import datetime, timezone

from capture.resolvers import base
from capture.resolvers.base import Resolution

ALGOLIA_ITEM = "https://hn.algolia.com/api/v1/items"


def resolve_hackernews(url: str) -> Resolution | None:
    item_id = hackernews_item(url)
    if not item_id:
        return None
    item = json.loads(base.fetch_html(f"{ALGOLIA_ITEM}/{item_id}"))
    if not item:
        raise RuntimeError(f"Hacker News item {item_id} not found")
    # A permalink to a comment still captures the whole discussion, named
    # and dated by its story.
    if item.get("type") != "story" and item.get("story_id"):
        item = json.loads(base.fetch_html(f"{ALGOLIA_ITEM}/{item['story_id']}"))
    source = f"https://news.ycombinator.com/item?id={item['id']}"
    return Resolution(
        source=source,
        content=source,
        use_browser=False,
        publish=item_date(item) or None,
        title=item.get("title"),
        markdown=hackernews_markdown(item),
        extra={
            "submitter": item.get("author") or "",
            "points": str(item.get("points") or ""),
            "comments": str(count_comments(item)),
            "link": item.get("url") or "",
        },
    )


def hackernews_item(url: str) -> str | None:
    match = re.search(r"news\.ycombinator\.com/item\?id=(\d+)", url)
    return match.group(1) if match else None


def item_date(node: dict) -> str:
    stamp = node.get("created_at_i")
    if not stamp:
        return ""
    return datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()


def count_comments(node: dict) -> int:
    return sum(
        1 + count_comments(child)
        for child in node.get("children", [])
        if child.get("type") == "comment"
    )


def hackernews_markdown(story: dict) -> str:
    lines = [f"# {story.get('title') or 'Hacker News discussion'}", ""]
    if link := story.get("url"):
        lines += [f"Discussion of <{link}>", ""]
    submitter = story.get("author") or "[deleted]"
    header = f"Submitted by {submitter}"
    if created := item_date(story):
        header += f" on {created}"
    if (points := story.get("points")) is not None:
        header += f" — {points} points"
    lines += [header, ""]
    if body := hn_text_to_markdown(story.get("text") or ""):
        lines += [body, ""]
    lines += [f"## Comments ({count_comments(story)})", ""]

    def walk(node: dict, depth: int) -> None:
        for child in node.get("children", []):
            if child.get("type") != "comment":
                continue
            prefix = "> " * depth
            byline = f"**{child.get('author') or '[deleted]'}**"
            if date := item_date(child):
                byline += f" ({date})"
            lines.append(f"{prefix}{byline}")
            lines.append(prefix.rstrip())
            body = hn_text_to_markdown(child.get("text") or "") or "*[deleted]*"
            lines.extend(f"{prefix}{line}" for line in body.splitlines())
            lines.append("")
            walk(child, depth + 1)

    walk(story, 1)
    return "\n".join(lines) + "\n"


def hn_text_to_markdown(text: str) -> str:
    """Convert a Hacker News comment body to markdown. HN bodies are HTML
    fragments: paragraphs as <p>, links as <a>, italics as <i>, code as
    <pre><code>, and every literal character escaped (&#x2F; for /).
    Unescape last, so angle brackets an author typed survive the pass that
    drops leftover tags."""
    if not text:
        return ""
    text = text.replace("<p>", "\n\n")
    text = re.sub(
        r'<a\b[^>]*\bhref="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.S
    )
    text = re.sub(r"</?i>", "*", text)
    text = text.replace("<pre><code>", "\n```\n").replace("</code></pre>", "\n```\n")
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()
