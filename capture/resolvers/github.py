"""GitHub blob, gist, wiki, and repository URLs."""

import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urljoin

from capture.resolvers import base
from capture.resolvers.base import Resolution


def resolve_github(url: str) -> Resolution | None:
    """The markdown body comes straight from the raw file; the browser
    still archives the rendered page."""
    if wiki := github_wiki(url):
        return resolve_wiki(url, wiki)
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
        # An explicit frontmatter title beats a guess from the body or
        # the file name.
        title=gh.get("title") or markdown_heading(gh["markdown"]) or gh["name"],
    )


def source_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """A static-site source file's own metadata, and the body without it.

    Zola and Hugo fence TOML in `+++`, Jekyll fences YAML in `---`, and
    the block holds the title and date the author wrote. Neither the
    file name nor git history is a substitute: claytonwramsey/www stores
    "Blowing up my compile times for dubious benefits" of 2023-06-19 in
    content/blog/fiddler-const-magic.md, whose first commit is the 2025
    date the site moved into that repo.
    """
    fences = {"+++": r"^\+\+\+\s*$", "---": r"^---\s*$"}
    for opener, pattern in fences.items():
        if not text.startswith(opener):
            continue
        end = re.search(pattern, text[len(opener) :], re.M)
        if not end:
            return {}, text
        block = text[len(opener) : len(opener) + end.start()]
        body = text[len(opener) + end.end() :].lstrip("\n")
        fields = {}
        for line in block.splitlines():
            key, sep, value = line.partition("=" if opener == "+++" else ":")
            if not sep:
                continue
            fields[key.strip().lower()] = value.strip().strip('"').strip("'")
        return fields, body
    return {}, text


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

    Returns None when the shortcut is unavailable, which sends the URL
    to the default resolver rather than failing the capture: the gists
    API answers 502 for karpathy/8627fe00 while the gist itself serves
    fine, and a page we can archive beats an error we cannot.
    """
    blob = re.search(
        r"github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+\.(?:md|markdown))$", url, re.I
    )
    if blob:
        owner, repo, ref, path = blob.groups()
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
        try:
            text = base.fetch_html(raw_url)
        except base.FetchError:
            return None
        # Rebase relative image links onto the raw host.
        text = re.sub(
            r"(!\[[^\]]*\]\()(?!https?://|#|data:)([^)\s]+)",
            lambda m: m.group(1) + urljoin(raw_url, m.group(2)),
            text,
        )
        # The author's own metadata outranks the path and git history,
        # and its fence is not part of the prose.
        fields, text = source_frontmatter(text)
        publish = None
        if stamp := re.match(r"(\d{4}-\d{2}-\d{2})", fields.get("date", "")):
            publish = stamp.group(1)
        if not publish:
            if match := re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", f"/{path}"):
                year, month, day = (int(g) for g in match.groups())
                if 1 <= month <= 12 and 1 <= day <= 31:
                    publish = f"{year}-{month:02d}-{day:02d}"
        if not publish:
            publish = first_commit_date(owner, repo, path)
        return {
            "markdown": text,
            "publish": publish,
            "title": fields.get("title"),
            "name": Path(path).stem,
            "domain": f"github.com - {owner}",
        }
    gist = re.search(r"gist\.github\.com/([^/]+)/([a-f0-9]+)", url)
    if gist:
        user, gist_id = gist.groups()
        try:
            api = json.loads(base.fetch_html(f"https://api.github.com/gists/{gist_id}"))
        except (base.FetchError, ValueError):
            return None
        for filename, info in api.get("files", {}).items():
            if filename.lower().endswith((".md", ".markdown")):
                return {
                    "markdown": info["content"],
                    "publish": (api.get("created_at") or "")[:10] or None,
                    "name": Path(filename).stem,
                    "domain": f"gist.github.com - {user}",
                }
    return None


# Reserved wiki routes: pages of GitHub's own UI, not content.
WIKI_ROUTES = ("_new", "_edit", "_history", "_pages", "_compare", "_access")


def github_wiki(url: str) -> dict | None:
    """Raw markdown and metadata for a GitHub wiki page.

    A wiki IS a git repo (`<repo>.wiki.git`) whose pages are the source
    markdown; the rendered page only wraps that in repo chrome, so there
    is nothing in the HTML worth keeping.
    """
    match = re.search(
        r"github\.com/([^/?#]+)/([^/?#]+?)(?:\.wiki)?/wiki(?:/([^/?#]+))?/?(?:[?#].*)?$",
        url,
    )
    if not match:
        return None
    owner, repo, page = match.group(1), match.group(2), unquote(match.group(3) or "")
    # A bare /wiki serves the Home page, same as GitHub's own redirect.
    page = page or "Home"
    if page in WIKI_ROUTES:
        return None
    # `?` in a page name ("What-Is-Similarity?") would start a query string.
    raw_url = f"https://raw.githubusercontent.com/wiki/{owner}/{repo}/{quote(page)}.md"
    text = base.fetch_html(raw_url)
    # Rebase relative links (wiki uploads live at the wiki repo root).
    text = re.sub(
        r"(!\[[^\]]*\]\()(?!https?://|#|data:)([^)\s]+)",
        lambda m: m.group(1) + urljoin(raw_url, m.group(2)),
        text,
    )
    return {
        "markdown": text,
        "publish": wiki_first_commit(owner, repo, f"{page}.md"),
        # The file name is the only title a wiki page has: GitHub stores
        # spaces as dashes and renders them back. Taking the document's
        # first heading instead would title stickfigure/blog's posts
        # "Oct 30, 2023" — the date is its h1.
        "title": page.replace("-", " "),
        "domain": f"github.com - {owner}",
    }


def wiki_first_commit(owner: str, repo: str, filename: str) -> str | None:
    """When the page first appeared. The commits API doesn't serve wikis,
    so read the history from the wiki repo itself — in full, since a
    shallow clone would date the page to wherever the cutoff landed."""
    source = f"https://github.com/{owner}/{repo}.wiki.git"
    with tempfile.TemporaryDirectory() as tmp:
        clone = subprocess.run(
            # Bare and blobless: this needs commits and trees, not content.
            ["git", "clone", "--quiet", "--bare", "--filter=blob:none", source, tmp],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            print(f"wiki history unavailable: {clone.stderr.strip()[:200]}")
            return None
        log = subprocess.run(
            ["git", "-C", tmp, "log", "--format=%ad", "--date=short", "--", filename],
            capture_output=True,
            text=True,
        )
    dates = log.stdout.split()
    # The page's visible date is the LAST commit, a modified date.
    return dates[-1] if dates else None


def resolve_wiki(url: str, wiki: dict) -> Resolution:
    return Resolution(
        source=url,
        content=url,
        domain=wiki["domain"],
        use_browser=False,
        publish=wiki["publish"],
        markdown=wiki["markdown"],
        title=wiki["title"],
    )
