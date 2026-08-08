"""Codeberg repository URLs, through the Forgejo API."""

import json
import re

from capture.resolvers import base
from capture.resolvers.base import Resolution
from capture.resolvers.github import bundle_repo, rebase_images, repo_readme

# Forgejo UI routes that occupy the first path segment.
RESERVED = ("explore", "user", "org", "api", "admin", "notifications", "avatars")


def resolve_codeberg(url: str) -> Resolution | None:
    """README as the markdown; the source as a git bundle — the same
    shape as a GitHub repo capture. Deeper paths (files, issues) fall
    through to the default page archive."""
    repo = codeberg_repo(url)
    if not repo:
        return None
    owner, name = repo
    source = f"https://codeberg.org/{owner}/{name}"
    meta = json.loads(
        base.fetch_html(f"https://codeberg.org/api/v1/repos/{owner}/{name}")
    )
    branch = meta.get("default_branch", "main")
    readme_url, readme = repo_readme(f"{source}/raw/branch/{branch}")
    if readme_url:
        readme = rebase_images(readme, readme_url)
    else:
        readme = f"# {owner}/{name}\n\n(no README)\n"
    extra = {"description": meta.get("description") or ""}
    if language := meta.get("language"):
        extra["language"] = language
    if stars := meta.get("stars_count"):
        extra["stars"] = str(stars)
    return Resolution(
        source=source,
        content=source,
        domain=f"codeberg.org - {owner}",
        use_browser=False,
        publish=(meta.get("created_at") or "")[:10] or None,
        markdown=readme,
        title=name,
        extra=extra,
        download_media=lambda folder, capture_name: bundle_repo(
            source, folder, capture_name
        ),
    )


def codeberg_repo(url: str) -> tuple[str, str] | None:
    """Owner and name for a repository ROOT url; deeper paths (files,
    issues, releases) are not repo captures."""
    match = re.search(
        r"codeberg\.org/([^/?#]+)/([^/?#]+?)(?:\.git)?/?(?:[?#].*)?$", url
    )
    if not match or match.group(1) in RESERVED:
        return None
    return match.group(1), match.group(2)
