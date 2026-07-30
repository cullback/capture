"""Lobsters threads via the story JSON, comments included.

`/s/<short_id>.json` returns the story and every comment in one
response, each carrying an explicit `depth`, so the thread renders
without walking a tree — unlike Hacker News, whose nesting has to be
reconstructed from children.

The rendered page would not do: lobsters lays comments out in nested
markup that converts poorly, and a "text post" (a story with no outbound
url, like an Ask) keeps its body in `description` rather than the page.
"""

import html
import json
import re

from capture.resolvers import base
from capture.resolvers.base import Resolution

LOBSTERS = "https://lobste.rs"


def resolve_lobsters(url: str) -> Resolution | None:
    short_id = lobsters_story(url)
    if not short_id:
        return None
    story = json.loads(base.fetch_html(f"{LOBSTERS}/s/{short_id}.json"))
    if not story.get("title"):
        raise RuntimeError(f"lobsters story {short_id} not found")
    source = f"{LOBSTERS}/s/{short_id}"
    extra = {
        "submitter": (story.get("submitter_user") or ""),
        "score": str(story.get("score") or ""),
        "comments": str(story.get("comment_count") or ""),
        "link": story.get("url") or "",
    }
    if tags := story.get("tags"):
        extra["tags"] = ", ".join(tags)
    return Resolution(
        source=source,
        content=source,
        use_browser=False,
        publish=(story.get("created_at") or "")[:10] or None,
        title=story.get("title"),
        markdown=lobsters_markdown(story),
        extra=extra,
    )


def lobsters_story(url: str) -> str | None:
    """The short id from a story URL, with or without its slug."""
    match = re.search(r"lobste\.rs/s/([a-z0-9]{6})", url)
    return match.group(1) if match else None


def lobsters_markdown(story: dict) -> str:
    lines = [f"# {story.get('title')}", ""]
    if link := story.get("url"):
        lines += [f"Discussion of <{link}>", ""]
    header = f"Submitted by {story.get('submitter_user') or '[deleted]'}"
    if created := (story.get("created_at") or "")[:10]:
        header += f" on {created}"
    if (score := story.get("score")) is not None:
        header += f" — {score} points"
    lines += [header, ""]
    # An Ask/text post keeps its body here; a link post leaves it empty.
    if body := comment_to_markdown(story.get("description") or ""):
        lines += [body, ""]
    comments = [c for c in story.get("comments") or [] if not c.get("is_deleted")]
    lines += [f"## Comments ({story.get('comment_count') or len(comments)})", ""]
    for comment in comments:
        # depth is 0-based on the wire; one blockquote level per step in.
        prefix = "> " * (comment.get("depth", 0) + 1)
        byline = f"**{comment.get('commenting_user') or '[deleted]'}**"
        stamp = (comment.get("created_at") or "")[:10]
        score = comment.get("score")
        if stamp:
            byline += f" ({stamp}" + (f", {score} points)" if score else ")")
        elif score:
            byline += f" ({score} points)"
        lines.append(f"{prefix}{byline}")
        lines.append(prefix.rstrip())
        text = comment_to_markdown(comment.get("comment") or "") or "*[deleted]*"
        lines.extend(f"{prefix}{line}".rstrip() for line in text.splitlines())
        lines.append("")
    return "\n".join(lines) + "\n"


def comment_to_markdown(fragment: str) -> str:
    """A lobsters body is an HTML fragment: paragraphs, links, emphasis,
    code, quotes and lists. Unescape last, so angle brackets an author
    typed survive the pass that strips leftover tags."""
    if not fragment:
        return ""
    text = fragment
    text = re.sub(
        r"<pre><code>(.*?)</code></pre>", r"\n```\n\1\n```\n", text, flags=re.S
    )
    text = re.sub(
        r'<a\b[^>]*\bhref="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.S
    )
    text = re.sub(r"</?(?:em|i)>", "*", text)
    text = re.sub(r"</?(?:strong|b)>", "**", text)
    text = re.sub(r"</?code>", "`", text)
    text = re.sub(r"<li>", "\n- ", text)
    text = re.sub(r"<blockquote>\s*", "\n> ", text)
    text = re.sub(r"</p>\s*<p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return html.unescape(text).strip()
