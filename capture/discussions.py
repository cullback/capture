"""Threads discussing a captured URL: Hacker News, Reddit, lobsters.

A page worth keeping is often discussed in several places, and the
discussion is frequently worth as much as the page. The sources are
merged into one list ordered by comment count, so the substantial
thread leads regardless of which site it is on.

Only threads that drew real discussion are kept: a submission with a
couple of drive-by replies records that the URL was posted, not that
it was discussed. Reddit is filtered harder than the others, because
general-interest subreddits repost a good link for years and discuss
the headline rather than the piece.
"""

import json
import re
import subprocess
import urllib.parse

from capture.extract import normalize
from capture.resolvers.base import FetchError, fetch_html

ALGOLIA = "https://hn.algolia.com/api/v1/search"
ARCTIC_SHIFT = "https://arctic-shift.photon-reddit.com/api"
LOBSTERS = "https://lobste.rs"

# Bots mirror the HN front page into these subreddits. Their threads
# are usually too quiet to clear MIN_COMMENTS anyway, but a mirror of a
# popular post can draw a real crowd, and it is still not the
# discussion — it is a copy of the submission that started one.
MIRROR_SUBREDDITS = {
    "hackernews",
    "patient_hackernews",
    "h_n",
    "hypeurls",
    "hackernewsbot",
    "hackernewsupvoted",
    "bprogramming",
    "programmingbot",
}
# General-interest subreddits, which take any link on any subject and
# discuss the headline fact rather than the piece. r/todayilearned
# alone supplied 91 of the corpus's first 308 reddit threads, one
# wikipedia article drawing 25 of them across a decade of reposts.
#
# Size is NOT the test: r/programming (6.7M subscribers) is the corpus's
# best technical source, while r/futurology (21M) and r/todayilearned
# (40M) are repost mills. Topical beats small.
GENERAL_SUBREDDITS = {
    "todayilearned",
    "til",
    "futurology",
    "interestingasfuck",
    "damnthatsinteresting",
    "mildlyinteresting",
    "nottheonion",
    "showerthoughts",
    "explainlikeimfive",
    "askreddit",
    "funny",
    "pics",
    "videos",
    "memes",
    "worldnews",
    "news",
    "all",
    "popular",
}
# More than five: enough replies to be a conversation rather than a
# couple of drive-by remarks under a submission nobody engaged with.
MIN_COMMENTS = 6


def discussions(url: str, title: str = "") -> list[str]:
    """Thread URLs discussing `url`, richest discussion first.

    A source that is down, blocked, or serving junk contributes nothing
    rather than failing the capture built around it. `title` is what
    lobsters is searched by; without it that source is skipped.
    """
    threads = (
        hackernews_threads(url) + reddit_threads(url) + lobsters_threads(url, title)
    )
    # Comments descending, then URL, so equal counts order stably.
    threads.sort(key=lambda t: (-t[1], t[0]))
    # A captured thread is not a discussion OF itself: capturing an HN
    # or reddit page finds that page in its own source.
    seen, ordered = {normalize(url)}, []
    for thread_url, _ in threads:
        if normalize(thread_url) not in seen:
            seen.add(normalize(thread_url))
            ordered.append(thread_url)
    return ordered


def hackernews_threads(url: str) -> list[tuple[str, int]]:
    """Every HN submission of this URL that was discussed, via Algolia.

    A URL is often submitted many times before one lands; the reposts
    that went nowhere are noise, the one that caught fire is the thread.
    """
    query = urllib.parse.quote(url, safe="")
    api = f"{ALGOLIA}?query={query}&restrictSearchableAttributes=url&hitsPerPage=50"
    hits = _get_json(api).get("hits") or []
    threads = []
    for hit in hits:
        # Algolia matches loosely; keep only true hits for this URL.
        if normalize(hit.get("url") or "") != normalize(url):
            continue
        comments = hit.get("num_comments") or 0
        item = hit.get("objectID")
        if comments < MIN_COMMENTS or not item:
            continue
        threads.append((f"https://news.ycombinator.com/item?id={item}", comments))
    return threads


def reddit_threads(url: str) -> list[tuple[str, int]]:
    """Reddit posts of this URL that drew real discussion, via Arctic
    Shift — reddit's own search blocks automated clients.

    One thread per subreddit, the most discussed. A community that
    posted a link twenty times over a decade held one conversation
    worth keeping, not twenty.
    """
    query = urllib.parse.quote(url, safe="")
    api = f"{ARCTIC_SHIFT}/posts/search?url={query}&limit=100"
    posts = _get_json(api).get("data") or []
    best: dict[str, tuple[str, int]] = {}
    for post in posts:
        subreddit = (post.get("subreddit") or "").lower()
        # u_* "subreddits" are user profile pages, not communities.
        if subreddit in MIRROR_SUBREDDITS or subreddit in GENERAL_SUBREDDITS:
            continue
        if subreddit.startswith("u_"):
            continue
        comments = post.get("num_comments") or 0
        if comments < MIN_COMMENTS:
            continue
        permalink = post.get("permalink") or ""
        if not permalink:
            continue
        thread = ("https://www.reddit.com" + permalink, comments)
        if comments > best.get(subreddit, ("", -1))[1]:
            best[subreddit] = thread
    threads = list(best.values())
    return threads


def lobsters_threads(url: str, title: str) -> list[tuple[str, int]]:
    """Lobsters stories linking this URL, found by TITLE.

    Lobsters has no URL lookup: /domains/<domain>.json serves only the
    newest 25 and ignores ?page=, the search index does not cover URLs
    (it cannot find a story by its own link), and the submit form's
    dupe check needs a session. Searching the title does work, so the
    title finds candidates and their `u-url` confirms the match.

    That makes this source lossy but never wrong: measured recall is
    about two thirds, the misses being titles built from words shorter
    than the four characters the index keeps. It costs one search, so
    it belongs in a capture and not in a corpus-wide sweep — lobsters
    starts answering 429 after a few dozen queries.
    """
    if not title:
        return []
    query = urllib.parse.urlencode({"q": title, "what": "stories", "order": "newest"})
    html = _get_html(f"{LOBSTERS}/search?{query}")
    threads = []
    for block in re.split(r'<li id="story_', html)[1:]:
        link = re.search(r'class="u-url"\s+href="([^"]+)"', block)
        if not link or normalize(link.group(1)) != normalize(url):
            continue
        story = re.search(r'href="(/s/[a-z0-9]+)/', block)
        count = re.search(
            r'class="mobile_comments[^"]*"[^>]*>\s*<span>(\d+)</span>', block
        )
        comments = int(count.group(1)) if count else 0
        if not story or comments < MIN_COMMENTS:
            continue
        threads.append((LOBSTERS + story.group(1), comments))
    return threads


def _get_html(page: str) -> str:
    try:
        return fetch_html(page)
    except (FetchError, subprocess.CalledProcessError) as failure:
        print(f"discussion lookup failed: {failure}")
        return ""


def _get_json(api: str) -> dict:
    """Via curl, not urllib: Arctic Shift answers urllib with 403 no
    matter the headers, the same client-fingerprint block that put
    fetch_html on curl in the first place."""
    try:
        return json.loads(fetch_html(api))
    except (FetchError, subprocess.CalledProcessError, ValueError) as failure:
        # Reported, not swallowed: a source that silently returns
        # nothing looks exactly like a page nobody discussed.
        print(f"discussion lookup failed: {failure}")
        return {}
