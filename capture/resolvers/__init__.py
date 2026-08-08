"""Per-source resolution: what to fetch, from where, and what's known upfront.

Each resolver module recognizes one kind of URL (arxiv paper, GitHub
markdown, YouTube video, Reddit thread) and returns a Resolution
describing how to capture it. Adding an ingestion source means adding
a module here and registering it in RESOLVERS — not a branch in the
pipeline.
"""

from capture.resolvers.arxiv import arxiv_id, arxiv_published, resolve_arxiv
from capture.resolvers.base import FetchError, Resolution, fetch_html
from capture.resolvers.default import (
    original_url,
    path_identity_domain,
    resolve_default,
)
from capture.resolvers.codeberg import codeberg_repo, resolve_codeberg
from capture.resolvers.github import github_markdown, github_wiki, resolve_github
from capture.resolvers.hackernews import (
    hackernews_item,
    hackernews_markdown,
    resolve_hackernews,
)
from capture.resolvers.substack import (
    render_comments,
    resolve_substack,
)
from capture.resolvers.reddit import (
    reddit_comments,
    reddit_markdown,
    reddit_thread,
    resolve_reddit,
)
from capture.resolvers.lesswrong import lesswrong_post, resolve_lesswrong
from capture.resolvers.lobsters import (
    lobsters_markdown,
    lobsters_story,
    resolve_lobsters,
)
from capture.resolvers.pdf import resolve_pdf
from capture.resolvers.wayback import (
    resolve_wayback,
    wayback_fallback,
    wayback_snapshot,
)
from capture.resolvers.wikipedia import resolve_wikipedia, wikipedia_article
from capture.resolvers.youtube import resolve_youtube, youtube_id

RESOLVERS = [
    resolve_arxiv,
    resolve_github,
    resolve_codeberg,
    resolve_youtube,
    resolve_hackernews,
    resolve_lobsters,
    resolve_reddit,
    resolve_wayback,
    resolve_lesswrong,
    resolve_wikipedia,
    resolve_substack,
    resolve_pdf,
]


def resolve(url: str) -> Resolution:
    for resolver in RESOLVERS:
        if resolution := resolver(url):
            return resolution
    return resolve_default(url)


__all__ = [
    "RESOLVERS",
    "FetchError",
    "Resolution",
    "arxiv_id",
    "arxiv_published",
    "fetch_html",
    "github_markdown",
    "github_wiki",
    "hackernews_item",
    "hackernews_markdown",
    "original_url",
    "path_identity_domain",
    "reddit_comments",
    "reddit_markdown",
    "reddit_thread",
    "resolve",
    "resolve_arxiv",
    "resolve_default",
    "lesswrong_post",
    "codeberg_repo",
    "resolve_codeberg",
    "resolve_github",
    "resolve_hackernews",
    "lobsters_markdown",
    "lobsters_story",
    "resolve_lesswrong",
    "resolve_lobsters",
    "resolve_pdf",
    "render_comments",
    "resolve_reddit",
    "resolve_substack",
    "resolve_wayback",
    "resolve_wikipedia",
    "resolve_youtube",
    "wayback_fallback",
    "wayback_snapshot",
    "wikipedia_article",
    "youtube_id",
]
