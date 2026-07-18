"""GitHub blob, gist, and repository URLs."""

import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urljoin

from capture.resolvers import base
from capture.resolvers.base import Resolution


def resolve_github(url: str) -> Resolution | None:
    """The markdown body comes straight from the raw file; the browser
    still archives the rendered page."""
    if repo := github_repo(url):
        return resolve_repo(*repo)
    gh = github_markdown(url)
    if not gh:
        return None
    return Resolution(
        source=url,
        content=url,
        domain=gh["domain"],
        html=base.fetch_html(url),
        publish=gh["publish"],
        markdown=gh["markdown"],
        title=markdown_heading(gh["markdown"]) or gh["name"],
    )


def markdown_heading(markdown: str) -> str | None:
    """The document's first heading: atx (# Title) or setext (Title
    over === underline, as quchen/articles uses)."""
    if match := re.search(r"^#\s+(.+)$", markdown, re.M):
        return match.group(1).strip()
    if match := re.search(r"^([^\s#>-][^\n]*)\n=+\s*$", markdown, re.M):
        return match.group(1).strip()
    return None


def first_commit_date(owner: str, repo: str, path: str) -> str | None:
    """When the file first appeared: the oldest commit touching it. The
    page's visible date is the LAST commit, a modified date."""
    try:
        commits = json.loads(
            base.fetch_html(
                f"https://api.github.com/repos/{owner}/{repo}/commits"
                f"?path={path}&per_page=100"
            )
        )
    except base.FetchError:
        return None
    if not isinstance(commits, list) or not commits:
        return None
    # With >100 commits this is approximate; article files rarely are.
    oldest = commits[-1]
    return (oldest.get("commit", {}).get("author", {}).get("date") or "")[:10] or None


def github_repo(url: str) -> tuple[str, str] | None:
    """Owner and name for a repository ROOT url; deeper paths (blobs,
    issues, pulls) are not repo captures."""
    match = re.search(
        r"(?<!gist\.)github\.com/([^/?#]+)/([^/?#]+?)(?:\.git)?/?(?:[?#].*)?$", url
    )
    if not match or match.group(1) in ("orgs", "topics", "search", "sponsors"):
        return None
    return match.group(1), match.group(2)


def resolve_repo(owner: str, repo: str) -> Resolution:
    """README as the markdown; the source as a git bundle — one file
    holding the complete history, re-cloneable with git clone."""
    source = f"https://github.com/{owner}/{repo}"
    meta = json.loads(base.fetch_html(f"https://api.github.com/repos/{owner}/{repo}"))
    branch = meta.get("default_branch", "main")
    readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
    try:
        readme = base.fetch_html(readme_url)
        # Rebase relative image links onto the raw host.
        readme = re.sub(
            r"(!\[[^\]]*\]\()(?!https?://|#|data:)([^)\s]+)",
            lambda m: m.group(1) + urljoin(readme_url, m.group(2)),
            readme,
        )
    except base.FetchError:
        readme = f"# {owner}/{repo}\n\n(no README)\n"
    extra = {"description": meta.get("description") or ""}
    if language := meta.get("language"):
        extra["language"] = language
    if stars := meta.get("stargazers_count"):
        extra["stars"] = str(stars)
    return Resolution(
        source=source,
        content=source,
        domain=f"github.com - {owner}",
        use_browser=False,
        publish=(meta.get("created_at") or "")[:10] or None,
        markdown=readme,
        title=repo,
        extra=extra,
        download_media=lambda folder, name: bundle_repo(source, folder, name),
    )


def bundle_repo(source: str, folder: Path, name: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        clone = subprocess.run(
            ["git", "clone", "--quiet", "--mirror", source, f"{tmp}/mirror"],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            print(f"bundle failed: {clone.stderr.strip()[:200]}")
            return
        subprocess.run(
            [
                "git",
                "-C",
                f"{tmp}/mirror",
                "bundle",
                "create",
                str(folder / f"{name}.bundle"),
                "--all",
            ],
            capture_output=True,
        )


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
        text = base.fetch_html(raw_url)
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
        if not publish:
            publish = first_commit_date(owner, repo, path)
        return {
            "markdown": text,
            "publish": publish,
            "name": Path(path).stem,
            "domain": f"github.com - {owner}",
        }
    gist = re.search(r"gist\.github\.com/([^/]+)/([a-f0-9]+)", url)
    if gist:
        user, gist_id = gist.groups()
        api = json.loads(base.fetch_html(f"https://api.github.com/gists/{gist_id}"))
        for filename, info in api.get("files", {}).items():
            if filename.lower().endswith((".md", ".markdown")):
                return {
                    "markdown": info["content"],
                    "publish": (api.get("created_at") or "")[:10] or None,
                    "name": Path(filename).stem,
                    "domain": f"gist.github.com - {user}",
                }
    return None
