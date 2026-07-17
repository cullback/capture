"""Per-source resolution: what to fetch, from where, and what's known upfront.

Each resolver module recognizes one kind of URL (arxiv paper, GitHub
markdown, YouTube video, Reddit thread) and returns a Resolution
describing how to capture it. Adding an ingestion source means adding
a module here and registering it in RESOLVERS — not a branch in the
pipeline.
"""

from capture.resolvers.arxiv import (
    arxiv_content_url,
    arxiv_id,
    arxiv_published,
    resolve_arxiv,
)
from capture.resolvers.base import Resolution, fetch_html
from capture.resolvers.default import (
    original_url,
    path_identity_domain,
    resolve_default,
)
from capture.resolvers.github import github_markdown, resolve_github
from capture.resolvers.reddit import (
    reddit_comments,
    reddit_markdown,
    reddit_thread,
    resolve_reddit,
)
from capture.resolvers.youtube import resolve_youtube, youtube_id

RESOLVERS = [resolve_arxiv, resolve_github, resolve_youtube, resolve_reddit]


def resolve(url: str) -> Resolution:
    for resolver in RESOLVERS:
        if resolution := resolver(url):
            return resolution
    return resolve_default(url)


__all__ = [
    "RESOLVERS",
    "Resolution",
    "arxiv_content_url",
    "arxiv_id",
    "arxiv_published",
    "fetch_html",
    "github_markdown",
    "original_url",
    "path_identity_domain",
    "reddit_comments",
    "reddit_markdown",
    "reddit_thread",
    "resolve",
    "resolve_arxiv",
    "resolve_default",
    "resolve_github",
    "resolve_reddit",
    "resolve_youtube",
    "youtube_id",
]
