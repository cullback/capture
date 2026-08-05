"""Reddit threads via the Arctic Shift archive (Pushshift successor)."""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from capture.resolvers import base
from capture.resolvers.base import Resolution

ARCTIC_SHIFT = "https://arctic-shift.photon-reddit.com/api"


def resolve_reddit(url: str) -> Resolution | None:
    """Threads come from the Arctic Shift archive: reddit blocks curl,
    urllib, and headless chromium outright, and the archive is JSON
    with bodies already in markdown. Scores and comments reflect
    archive time, not live state."""
    thread = reddit_thread(url)
    if not thread:
        return None
    subreddit, thread_id = thread
    posts = json.loads(base.fetch_html(f"{ARCTIC_SHIFT}/posts/ids?ids={thread_id}"))[
        "data"
    ]
    if not posts:
        raise RuntimeError(f"thread {thread_id} not in the Arctic Shift archive")
    post = posts[0]
    comments = reddit_comments(thread_id)
    created = datetime.fromtimestamp(post["created_utc"], timezone.utc)
    source = f"https://www.reddit.com/r/{subreddit}/comments/{thread_id}/"
    return Resolution(
        source=source,
        content=source,
        domain=f"reddit.com - r-{subreddit}",
        use_browser=False,
        publish=created.date().isoformat(),
        markdown=reddit_markdown(post, comments),
        title=post.get("title"),
        extra={
            "subreddit": f"r/{post.get('subreddit', subreddit)}",
            "author": f"u/{post.get('author', '')}",
            "score": str(post.get("score", "")),
            # The post record can be a snapshot from minutes after
            # creation; the comment archive keeps growing past it.
            "comments": str(max(len(comments), post.get("num_comments") or 0)),
        },
    )


def reddit_thread(url: str) -> tuple[str, str] | None:
    match = re.search(r"reddit\.com/r/([^/]+)/comments/([a-z0-9]+)", url)
    return (match.group(1).lower(), match.group(2)) if match else None


def reddit_comments(thread_id: str, max_pages: int = 10) -> list[dict]:
    """All archived comments, paginated by creation-time cursor."""
    by_id: dict[str, dict] = {}
    after = None
    for _ in range(max_pages):
        # sort=asc makes the created-time cursor sound; the default
        # ordering interleaves dates and a max() cursor skips comments.
        query = f"?link_id={thread_id}&limit=100&sort=asc"
        if after is not None:
            query += f"&after={after}"
        page = json.loads(base.fetch_html(f"{ARCTIC_SHIFT}/comments/search{query}"))[
            "data"
        ]
        if not page:
            break
        by_id.update((c["id"], c) for c in page)
        after = max(int(c["created_utc"]) for c in page)
        if len(page) < 100:
            break
    else:
        print(f"comment cap reached: kept {len(by_id)} comments")
    return list(by_id.values())


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def reddit_media(post: dict) -> list[str]:
    """Markdown lines for a link post's target: gallery images under
    their stable i.redd.it names, a single image as an embed (the
    pipeline downloads embeds into media/), any other target as a
    plain link. Self posts carry their content in selftext."""
    if gallery := post.get("gallery_data"):
        metadata = post.get("media_metadata") or {}
        lines = []
        for item in gallery.get("items") or []:
            media_id = item.get("media_id")
            extension = (metadata.get(media_id, {}).get("m") or "").rpartition("/")[2]
            if media_id and extension:
                lines.append(f"![](https://i.redd.it/{media_id}.{extension})")
                if caption := item.get("caption"):
                    lines.append(caption)
        return lines
    url = post.get("url") or ""
    if post.get("is_self") or not url.startswith("http"):
        return []
    if post.get("post_hint") == "image" or url.lower().endswith(IMAGE_EXTENSIONS):
        return [f"![]({url})"]
    return [f"<{url}>"]


def reddit_markdown(post: dict, comments: list[dict]) -> str:
    lines = [
        f"# {post.get('title', '')}",
        "",
        f"by u/{post.get('author', '[deleted]')} in r/{post.get('subreddit', '')}",
        "",
    ]
    for line in reddit_media(post):
        lines += [line, ""]
    selftext = (post.get("selftext") or "").strip()
    if selftext in ("[removed]", "[deleted]") and not post.get("is_self"):
        # A moderation sentinel on a link post is snapshot noise, not a
        # body; on a self post it honestly records a removed body.
        selftext = ""
    if selftext:
        lines += [selftext, ""]
    lines += [f"## Comments ({len(comments)})", ""]
    children: dict[str, list[dict]] = defaultdict(list)
    for comment in comments:
        children[comment.get("parent_id") or ""].append(comment)
    for siblings in children.values():
        siblings.sort(key=lambda c: -(c.get("score") or 0))

    def walk(parent_id: str, depth: int) -> None:
        for comment in children.get(parent_id, []):
            quote_prefix = "> " * depth
            author = comment.get("author") or "[deleted]"
            score = comment.get("score") or 0
            lines.append(f"{quote_prefix}**u/{author}** ({score} points)")
            for line in (comment.get("body") or "").splitlines():
                lines.append(f"{quote_prefix}{line}")
            lines.append("")
            walk(f"t1_{comment['id']}", depth + 1)

    walk(f"t3_{post['id']}", 1)
    return "\n".join(lines) + "\n"
