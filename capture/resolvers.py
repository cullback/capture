"""Per-source resolution: what to fetch, from where, and what's known upfront.

Each resolver recognizes one kind of URL (arxiv paper, GitHub markdown,
archive.today snapshot) and returns a Resolution describing how to
capture it. Adding an ingestion source (YouTube, Wikipedia, repos)
means adding a resolver here, not a branch in the pipeline.
"""

import json
import re
import subprocess
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from capture.extract import body_date, normalize

# Netscape-format cookies, for age-restricted or member-only videos.
YOUTUBE_COOKIES = Path.home() / ".config" / "capture" / "youtube-cookies.txt"


@dataclass
class Resolution:
    source: str  # identity URL: naming, frontmatter, HN lookup
    content: str  # URL to render and convert
    domain: str | None = None  # folder-name leading segment(s) override
    html: str = ""  # fetched identity page ("" = no HTML artifact)
    use_browser: bool = True  # single-file the content URL
    publish: str | None = None  # publish date, when the source knows it
    archive: str | None = None  # snapshot URL, for archived pages
    markdown: str | None = None  # ready-made body, skipping pandoc
    skip_markdown: bool = False  # media captures describe themselves
    title: str | None = None  # title override
    pdf_url: str | None = None  # extra artifact to download
    extra: dict[str, str] = field(default_factory=dict)  # frontmatter additions
    download_media: Callable[[Path, str], None] | None = None  # (folder, name)


def resolve(url: str) -> Resolution:
    return (
        resolve_arxiv(url)
        or resolve_github(url)
        or resolve_youtube(url)
        or resolve_reddit(url)
        or resolve_default(url)
    )


def fetch_html(url: str) -> str:
    # curl rather than urllib: WAFs (e.g. AoPS) block urllib's client
    # fingerprint no matter what headers it sends.
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "120", "-A", "capture/0.1", url],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def resolve_arxiv(url: str) -> Resolution | None:
    """Identity from the abs page; content from the HTML rendering,
    which is generated from the LaTeX source so math survives."""
    aid = arxiv_id(url)
    if not aid:
        return None
    source = f"https://arxiv.org/abs/{aid}"
    html = fetch_html(source)
    return Resolution(
        source=source,
        content=arxiv_content_url(aid),
        html=html,
        publish=arxiv_published(html),
        pdf_url=f"https://arxiv.org/pdf/{aid}",
    )


def resolve_github(url: str) -> Resolution | None:
    """The markdown body comes straight from the raw file; the browser
    still archives the rendered page."""
    gh = github_markdown(url)
    if not gh:
        return None
    heading = re.search(r"^#\s+(.+)$", gh["markdown"], re.M)
    return Resolution(
        source=url,
        content=url,
        domain=gh["domain"],
        html=fetch_html(url),
        publish=gh["publish"],
        markdown=gh["markdown"],
        title=heading.group(1).strip() if heading else gh["name"],
    )


def youtube_id(url: str) -> str | None:
    match = re.search(
        r"(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|live/)|youtu\.be/)"
        r"([A-Za-z0-9_-]{11})",
        url,
    )
    return match.group(1) if match else None


def yt_dlp(args: list[str]) -> subprocess.CompletedProcess:
    command = ["yt-dlp", "--no-warnings"]
    if YOUTUBE_COOKIES.exists():
        command += ["--cookies", str(YOUTUBE_COOKIES)]
    return subprocess.run(command + args, capture_output=True, text=True)


def resolve_youtube(url: str) -> Resolution | None:
    """Video captures are mkv + info.json (the yt-dlp standard), no
    markdown: the info.json carries all metadata and the transcript
    lives in the mkv's embedded subtitles."""
    vid = youtube_id(url)
    if not vid:
        return None
    source = f"https://www.youtube.com/watch?v={vid}"
    probe = yt_dlp(["--dump-json", "--skip-download", source])
    if probe.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {source}: {probe.stderr.strip()[:300]}")
    meta = json.loads(probe.stdout)
    upload = meta.get("upload_date") or ""
    # "youtube.com - @handle" as the leading folder segments: sorts
    # under the youtube.com type prefix, then groups by channel.
    handle = (meta.get("uploader_id") or "").removeprefix("@").lower()
    handle = re.sub(r"[^a-z0-9._-]", "", handle)  # handles can be non-ASCII
    return Resolution(
        source=source,
        content=source,
        domain=f"youtube.com - @{handle}" if handle else None,
        use_browser=False,
        publish=f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if upload else None,
        skip_markdown=True,
        title=meta.get("title"),
        download_media=lambda folder, name: youtube_download(source, folder, name),
    )


def youtube_download(source: str, folder: Path, name: str) -> None:
    """Max-quality archival download: one mkv with thumbnail, metadata,
    chapters, subtitles, and the info-json all embedded."""
    result = yt_dlp(
        [
            "-f",
            "bestvideo*+bestaudio/best",
            "--merge-output-format",
            "mkv",
            # Also remux single-format downloads: info-json and other
            # attachments only embed into mkv.
            "--remux-video",
            "mkv",
            "--embed-thumbnail",
            "--embed-metadata",
            "--embed-chapters",
            "--embed-subs",
            "--embed-info-json",
            "--write-info-json",
            "--sub-langs",
            "en,en-orig",
            "--write-auto-subs",
            "--sponsorblock-mark",
            "all",
            "-o",
            str(folder / f"{name}.%(ext)s"),
            source,
        ]
    )
    if result.returncode != 0:
        print(f"video download failed: {result.stderr.strip()[:300]}")
    # Subtitle files were only needed for embedding.
    for stray in folder.glob(f"{name}*.vtt"):
        stray.unlink()
    for stray in folder.glob(f"{name}*.srt"):
        stray.unlink()


ARCTIC_SHIFT = "https://arctic-shift.photon-reddit.com/api"


def reddit_thread(url: str) -> tuple[str, str] | None:
    match = re.search(r"reddit\.com/r/([^/]+)/comments/([a-z0-9]+)", url)
    return (match.group(1).lower(), match.group(2)) if match else None


def resolve_reddit(url: str) -> Resolution | None:
    """Threads come from the Arctic Shift archive (the Pushshift
    successor): reddit blocks curl, urllib, and headless chromium
    outright, and the archive is JSON with bodies already in markdown.
    Scores and comments reflect archive time, not live state."""
    thread = reddit_thread(url)
    if not thread:
        return None
    subreddit, thread_id = thread
    posts = json.loads(fetch_html(f"{ARCTIC_SHIFT}/posts/ids?ids={thread_id}"))["data"]
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
            "comments": str(post.get("num_comments", "")),
        },
    )


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
        page = json.loads(fetch_html(f"{ARCTIC_SHIFT}/comments/search{query}"))["data"]
        if not page:
            break
        by_id.update((c["id"], c) for c in page)
        after = max(int(c["created_utc"]) for c in page)
        if len(page) < 100:
            break
    else:
        print(f"comment cap reached: kept {len(by_id)} comments")
    return list(by_id.values())


def reddit_markdown(post: dict, comments: list[dict]) -> str:
    lines = [
        f"# {post.get('title', '')}",
        "",
        f"by u/{post.get('author', '[deleted]')} in r/{post.get('subreddit', '')}",
        "",
    ]
    if selftext := (post.get("selftext") or "").strip():
        lines += [selftext, ""]
    lines += [f"## Comments ({post.get('num_comments', len(comments))})", ""]
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


# Platforms hosting many authors under one domain, with the author or
# publication as the first path segment: fold it into the folder name
# the way youtube does with @handles.
PATH_IDENTITY_HOSTS = {"medium.com", "buttondown.com"}


def path_identity_domain(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.removeprefix("www.")
    segments = [s for s in parsed.path.split("/") if s]
    if host in PATH_IDENTITY_HOSTS and len(segments) >= 2:
        return f"{host} - {segments[0]}"
    return None


def resolve_default(url: str) -> Resolution:
    """Plain pages, plus archive.today snapshots resolved to their
    original identity. Archive.today challenges browsers with a
    captcha, so the plain fetch is the best artifact we can get there."""
    html = fetch_html(url)
    source = original_url(url, html)
    return Resolution(
        source=source,
        content=url,
        domain=path_identity_domain(source),
        html=html,
        archive=url if source != url else None,
        use_browser=source == url,
    )


def arxiv_id(url: str) -> str | None:
    match = re.search(
        r"(?:ar5iv\.labs\.arxiv|arxiv)\.org/(?:abs|pdf|html|e-print)/(\d{4}\.\d{4,5})",
        url,
    )
    return match.group(1) if match else None


def arxiv_content_url(aid: str) -> str:
    """The paper's HTML rendering: official when it exists, else ar5iv."""
    official = f"https://arxiv.org/html/{aid}"
    status = subprocess.run(
        ["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}", official],
        capture_output=True,
        text=True,
    ).stdout
    return official if status == "200" else f"https://ar5iv.labs.arxiv.org/html/{aid}"


def arxiv_published(html: str) -> str | None:
    """The v1 submission date from an abs page ("Submitted on 27 Mar 2026")."""
    if match := re.search(r"Submitted on (\d{1,2} [A-Za-z]{3,9},? \d{4})", html):
        return body_date(match.group(1))
    return None


def github_markdown(url: str) -> dict | None:
    """Raw markdown and metadata for GitHub blob and gist URLs.

    These files ARE markdown: fetching the raw source beats converting
    GitHub's rendered chrome back into markdown.
    """
    blob = re.search(
        r"github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+\.(?:md|markdown))$", url, re.I
    )
    if blob:
        owner, repo, ref, path = blob.groups()
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
        text = fetch_html(raw_url)
        # Rebase relative image links onto the raw host.
        text = re.sub(
            r"(!\[[^\]]*\]\()(?!https?://|#|data:)([^)\s]+)",
            lambda m: m.group(1) + urljoin(raw_url, m.group(2)),
            text,
        )
        publish = None
        if match := re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", f"/{path}"):
            year, month, day = (int(g) for g in match.groups())
            if 1 <= month <= 12 and 1 <= day <= 31:
                publish = f"{year}-{month:02d}-{day:02d}"
        return {
            "markdown": text,
            "publish": publish,
            "name": Path(path).stem,
            "domain": f"github.com - {owner}",
        }
    gist = re.search(r"gist\.github\.com/([^/]+)/([a-f0-9]+)", url)
    if gist:
        user, gist_id = gist.groups()
        api = json.loads(fetch_html(f"https://api.github.com/gists/{gist_id}"))
        for filename, info in api.get("files", {}).items():
            if filename.lower().endswith((".md", ".markdown")):
                return {
                    "markdown": info["content"],
                    "publish": (api.get("created_at") or "")[:10] or None,
                    "name": Path(filename).stem,
                    "domain": f"gist.github.com - {user}",
                }
    return None


ARCHIVE_HOSTS = {"archive.is", "archive.ph", "archive.today", "archive.md"}


def original_url(url: str, html: str) -> str:
    """The archived page's source URL, for archive.today snapshots."""
    if urlparse(url).netloc.removeprefix("www.") not in ARCHIVE_HOSTS:
        return url
    match = re.search(
        r'rel="canonical" href="https?://archive\.\w+/[^"/]+/(https?://[^"]+)"', html
    )
    return match.group(1) if match else url


def hackernews_url(url: str) -> str | None:
    """Best-scoring HN submission of this URL, via the Algolia search API."""
    api = (
        "https://hn.algolia.com/api/v1/search"
        f"?query={quote(url, safe='')}&restrictSearchableAttributes=url&hitsPerPage=20"
    )
    try:
        with urllib.request.urlopen(api, timeout=10) as response:
            hits = json.load(response)["hits"]
    except OSError:
        return None
    matches = [h for h in hits if normalize(h.get("url") or "") == normalize(url)]
    if not matches:
        return None
    return (
        f"https://news.ycombinator.com/item?id={best_submission(matches)['objectID']}"
    )


def best_submission(matches: list[dict]) -> dict:
    """The submission with the discussion: comments first, points to
    tiebreak. Points measure visibility; comments measure the thread."""
    return max(
        matches,
        key=lambda h: (h.get("num_comments") or 0, h.get("points") or 0),
    )
