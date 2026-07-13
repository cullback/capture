"""Capture a web page as a faithful HTML archive plus clean markdown.

Each capture lands in its own folder:

    data/<domain> - <yyyy-mm-dd> - <slug>/
        <same name>.html   faithful single-file archive
        <same name>.md     pandoc markdown with TeX math preserved
        media/             downloaded images, referenced relatively
"""

import argparse
import calendar
import difflib
import html as html_lib
import json
import re
import shutil
import subprocess
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent

PANDOC_FORMAT = "html+tex_math_dollars+tex_math_single_backslash"

DATE_PATTERNS = [
    r'property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)',
    r'content=["\']([^"\']+)["\'][^>]*property=["\']article:published_time',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'<time[^>]*datetime=["\']([^"\']+)',
]


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


def published_date(url: str, html: str) -> str | None:
    """Publication date from the URL path or page metadata; None when unknown."""
    path = urlparse(url).path
    match = re.search(r"/(\d{4})/(\d{2})/(\d{2})(?:/|$)", path) or re.search(
        r"(\d{4})-(\d{2})-(\d{2})", path
    )
    if match:
        return "-".join(match.groups())
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, html)
        if match and re.match(r"\d{4}-\d{2}-\d{2}", match.group(1)):
            return match.group(1)[:10]
    return body_date(html)


MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | {
    m.lower(): i for i, m in enumerate(calendar.month_abbr) if m
}


def body_date(html: str) -> str | None:
    """First unambiguous date in the page body: ISO, named month, or M/D/YYYY.

    Slash dates are last and assume US month-first order; named months and
    ISO can't be misread. This whole tier is a heuristic destined to be
    replaced by an LLM fallback.
    """
    # Drop comments first: single-file stamps its own save date into one.
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    if match := re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", html):
        return "-".join(match.groups())
    for pattern, order in [
        (r"\b([A-Za-z]{3,9})\.? (\d{1,2}),? (\d{4})\b", (2, 0, 1)),
        (r"\b(\d{1,2}) ([A-Za-z]{3,9})\.? (\d{4})\b", (2, 1, 0)),
        (r">(\d{1,2})/(\d{1,2})/(\d{4})<", (2, 0, 1)),
    ]:
        for match in re.finditer(pattern, html):
            year, month, day = (match.group(i + 1) for i in order)
            month = MONTHS.get(month.lower(), month if month.isdigit() else None)
            if month and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


def page_title(html: str, domain: str = "", url: str = "") -> str:
    """Display title: og:title, then the page h1, then <title>. Empty if none."""

    def extract(pattern: str) -> str:
        if match := re.search(pattern, html):
            return re.sub(r"\s+", " ", html_lib.unescape(match.group(1))).strip()
        return ""

    # Both attribute orders, both quote styles, and property= or name=
    # (eev.ee writes <meta name="og:title">).
    og = (
        extract(r'(?:property|name)=["\']og:title["\'][^>]*content="([^"]+)"')
        or extract(r"(?:property|name)=[\"']og:title[\"'][^>]*content='([^']+)'")
        or extract(r'content="([^"]+)"[^>]*(?:property|name)=["\']og:title["\']')
        or extract(r"content='([^']+)'[^>]*(?:property|name)=[\"']og:title[\"']")
    )

    def clean(fragment: str) -> str:
        text = html_lib.unescape(re.sub(r"<[^>]+>", "", fragment))
        return re.sub(r"\s+", " ", text).strip()

    # Prefer a heading class-marked as the post title: WordPress puts a
    # site-title h1 earlier in the DOM, and Obsidian Publish uses an h2
    # (publish-article-heading) with no h1 at all.
    headings = re.findall(r"<h([12])([^>]*)>(.*?)</h\1>", html, re.S)
    h1 = next(
        (
            clean(body)
            for _, attrs, body in headings
            if re.search(r"(entry|post|article|page|publish)[-_](title|heading)", attrs)
        ),
        "",
    ) or next((clean(body) for level, _, body in headings if level == "1"), "")
    doc = extract(r"<title[^>]*>([^<]+)</title>")
    # An h1 linking to the site root is a masthead; its text is the
    # site's display name, which may differ from the domain (eli.li's
    # masthead reads "« Oatmeal", and the site prefixes titles with it).
    masthead = next(
        (
            clean(body)
            for level, _, body in headings
            if level == "1"
            and re.search(r'href=["\'](?:/|https?://[^"\'/]+/?)["\']', body)
        ),
        "",
    )
    if h1 and (compact(h1) in compact(domain) or compact(h1) == compact(masthead)):
        # The h1 is the site name, not the post title.
        h1 = ""
    og = strip_site_prefix(og, masthead)
    doc = strip_site_prefix(doc, masthead)
    # When <title> wraps the h1 ("Section : Post" or "Post · Section"),
    # decide which piece is the real title. The URL slug is the
    # strongest signal (game-loop.html says the h1 "Game Loop" is the
    # title; AoPS's slug matches the remainder, not its blog-name h1);
    # fall back to length, since post titles run longer than site and
    # section names.
    if h1 and doc != h1:
        if doc.startswith(h1):
            rest = doc[len(h1) :].strip(" :-–—|·")
        elif doc.endswith(h1):
            rest = doc[: -len(h1)].strip(" :-–—|·")
        else:
            rest = ""
        if rest:
            segments = [s for s in urlparse(url).path.split("/") if s]
            segment = slugify(segments[-1]) if segments else ""
            if slug_affinity(rest, segment) and not slug_affinity(h1, segment):
                h1 = rest
            elif not slug_affinity(h1, segment) and len(rest) > len(h1):
                h1 = rest
    for candidate in (og, h1, doc):
        if candidate and (title := strip_site_suffix(candidate, domain)):
            return title
    return ""


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def slug_affinity(text: str, segment: str) -> bool:
    """Whether text plausibly generated the URL slug segment.

    Gated similarity rather than containment, so truncated slugs still
    match ("many-hard-leetcode-problems-are-easy-constraint" vs the full
    title). Below the threshold the signal contributes nothing.
    """
    if not text or not segment:
        return False
    slug = slugify(text)
    if slug in segment:
        return True
    return difflib.SequenceMatcher(None, slug, segment).ratio() >= 0.6


def strip_site_prefix(title: str, site_name: str) -> str:
    """Drop a leading "Site Name - " segment matching the masthead."""
    if not site_name:
        return title
    for separator in [" - ", " | ", " – ", " — ", " · ", ": "]:
        head, found, tail = title.partition(separator)
        if found and tail and compact(head) == compact(site_name):
            return tail.strip()
    return title


def strip_site_suffix(title: str, domain: str) -> str:
    """Drop a trailing "- Site Name" segment when it matches the domain.

    A match is either containment ("Bloomberg" in bloomberg.com) or the
    tail starting with the domain's label ("Chad Nauseam Home" for
    chadnauseam.com).
    """
    label = compact(domain.split(".")[-2]) if domain.count(".") else ""
    for separator in [" - ", " | ", " – ", " — ", " · "]:
        head, found, tail = title.rpartition(separator)
        if not (found and head and compact(tail)):
            continue
        if compact(tail) in compact(domain) or (
            label and compact(tail).startswith(label)
        ):
            return head.strip()
    return title


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
        return {"markdown": text, "publish": publish, "name": Path(path).stem}
    gist = re.search(r"gist\.github\.com/[^/]+/([a-f0-9]+)", url)
    if gist:
        api = json.loads(fetch_html(f"https://api.github.com/gists/{gist.group(1)}"))
        for filename, info in api.get("files", {}).items():
            if filename.lower().endswith((".md", ".markdown")):
                return {
                    "markdown": info["content"],
                    "publish": (api.get("created_at") or "")[:10] or None,
                    "name": Path(filename).stem,
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


def normalize(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.removeprefix("www.") + parsed.path.rstrip("/")


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
    best = max(matches, key=lambda h: h.get("points") or 0)
    return f"https://news.ycombinator.com/item?id={best['objectID']}"


def frontmatter(
    url: str, title: str, publish: str | None, archive: str | None = None
) -> str:
    domain = urlparse(url).netloc.removeprefix("www.")
    lines = [
        "---",
        f"title: {json.dumps(title or 'Untitled')}",
        f"domain: {domain}",
        f"url: {url}",
    ]
    if archive:
        lines.append(f"archive: {archive}")
    if hn := hackernews_url(url):
        lines.append(f"hackernews: {hn}")
    lines.append(f"capture_date: {date.today().isoformat()}")
    if publish:
        # Omitted when no publish date was found: the folder falls back
        # to the capture date, and absence here records that honestly.
        lines.append(f"publish_date: {publish}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def slugify(text: str) -> str:
    # NFKD + ASCII round-trip transliterates accents: Abrégé -> Abrege
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"['’]", "", text.lower())
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")


def page_slug(url: str, html: str) -> str:
    domain = urlparse(url).netloc.removeprefix("www.")
    if slug := slugify(page_title(html, domain, url)):
        return slug
    segments = [s for s in urlparse(url).path.split("/") if s]
    return slugify(segments[-1]) if segments else "untitled"


def single_file(url: str, output: Path) -> None:
    subprocess.run(
        [
            "single-file",
            "--browser-executable-path",
            shutil.which("chromium") or "chromium",
            # Look like a human browser: Cloudflare blocks headless
            # chromium's default fingerprint (e.g. on AoPS).
            "--browser-args",
            json.dumps(
                [
                    "--disable-blink-features=AutomationControlled",
                    "--user-agent=Mozilla/5.0 (X11; Linux x86_64)"
                    " AppleWebKit/537.36 (KHTML, like Gecko)"
                    " Chrome/145.0.0.0 Safari/537.36",
                ]
            ),
            "--filename-conflict-action",
            "overwrite",
            url,
            str(output),
        ],
        check=True,
    )


def pandoc(source: str, output: str, cwd: Path) -> bool:
    """Convert HTML (a URL or a file relative to cwd) to markdown."""
    result = subprocess.run(
        [
            "pandoc",
            "-f",
            PANDOC_FORMAT,
            "-t",
            "gfm-raw_html",
            "--wrap=none",
            f"--lua-filter={REPO_ROOT / 'filters' / 'clean.lua'}",
            "--extract-media=media",
            source,
            "-o",
            output,
        ],
        cwd=cwd,
    )
    return result.returncode == 0


def thin(markdown: Path) -> bool:
    return not markdown.exists() or len(markdown.read_text().split()) < 150


def format_markdown(markdown: Path) -> None:
    # Via stdin with a path outside data/, since dprint.json excludes
    # data/ to keep repo-wide `just format` off the captures.
    result = subprocess.run(
        ["dprint", "fmt", "--stdin", "capture.md"],
        input=markdown.read_text(),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode == 0 and result.stdout:
        markdown.write_text(result.stdout)


def existing_capture(url: str) -> Path | None:
    """The folder already holding this URL, matched via frontmatter."""
    target = normalize(url)
    if aid := arxiv_id(url):
        target = normalize(f"https://arxiv.org/abs/{aid}")
    for markdown in sorted((REPO_ROOT / "data").glob("*/*.md")):
        header = markdown.read_text(errors="replace")[:600]
        for line in header.splitlines():
            key, _, value = line.partition(": ")
            if key in ("url", "archive") and normalize(value.strip()) == target:
                return markdown.parent
    return None


def capture(url: str) -> Path:
    # Three URLs can differ: `source` is the page's identity (naming,
    # frontmatter, HN lookup), `content` is what gets rendered and
    # converted, and the artifact is what we save.
    publish = archive = github = None
    if aid := arxiv_id(url):
        # Identity from the abs page; content from the HTML rendering,
        # which is generated from the LaTeX source so math survives.
        source = f"https://arxiv.org/abs/{aid}"
        html = fetch_html(source)
        content = arxiv_content_url(aid)
        publish = arxiv_published(html)
        use_browser = True
    elif github := github_markdown(url):
        # The markdown body comes straight from the raw file; the
        # browser still archives the rendered page.
        source = content = url
        html = fetch_html(url)
        publish = github["publish"]
        use_browser = True
    else:
        html = fetch_html(url)
        source = original_url(url, html)
        content = url
        archive = url if source != url else None
        # Archive.today challenges browsers with a captcha, so the plain
        # fetch is the best artifact we can get there.
        use_browser = source == url

    domain = urlparse(source).netloc.removeprefix("www.")
    # single-file archives to a scratch path, since the folder name may
    # depend on metadata that only exists after rendering.
    scratch = None
    if use_browser:
        scratch = REPO_ROOT / "data" / ".capture.html"
        single_file(content, scratch)
        artifact_html = scratch.read_text()
    else:
        artifact_html = html

    # Client-rendered pages (e.g. AoPS, Obsidian Publish) serve a shell:
    # take metadata from the rendered DOM when the raw HTML carries no
    # title signal beyond the <title> tag.
    informative = page_title(html, domain, source) and re.search(
        r"<h1[\s>]|og:title", html
    )
    meta_html = html if informative else artifact_html
    if github:
        # The markdown's own first heading beats GitHub's page chrome.
        heading = re.search(r"^#\s+(.+)$", github["markdown"], re.M)
        title = heading.group(1).strip() if heading else github["name"]
    else:
        title = page_title(meta_html, domain, source)
    publish = publish or published_date(source, meta_html)
    name_date = publish or date.today().isoformat()
    name = f"{domain} - {name_date} - {slugify(title) or page_slug(source, meta_html)}"
    folder = REPO_ROOT / "data" / name
    folder.mkdir(parents=True, exist_ok=True)

    artifact = folder / f"{name}.html"
    if scratch:
        scratch.replace(artifact)
    else:
        artifact.write_text(artifact_html)

    if aid:
        # The typeset PDF is the canonical rendering of a paper: keep it
        # alongside the HTML conversion.
        subprocess.run(
            [
                "curl",
                "-sL",
                "--max-time",
                "300",
                "-o",
                str(folder / f"{name}.pdf"),
                f"https://arxiv.org/pdf/{aid}",
            ],
            check=False,
        )

    # Prefer converting from the URL so relative image paths resolve; fall
    # back to the local artifact when the direct fetch fails or the raw
    # HTML had no real content. GitHub sources skip conversion entirely.
    markdown = folder / f"{name}.md"
    if github:
        markdown.write_text(github["markdown"])
    elif (
        not use_browser or not pandoc(content, markdown.name, folder) or thin(markdown)
    ):
        pandoc(artifact.name, markdown.name, folder)

    markdown.write_text(
        frontmatter(source, title, publish, archive) + markdown.read_text()
    )
    format_markdown(markdown)
    return folder


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="capture",
        description="Save a page as a faithful HTML archive plus clean markdown.",
    )
    parser.add_argument("url", help="page to capture")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="re-capture even when the URL already exists in data/",
    )
    args = parser.parse_args()
    if not args.force and (duplicate := existing_capture(args.url)):
        print(f"already captured: {duplicate.name}")
        print("pass -f / --force to re-capture")
        return
    print(capture(args.url))


if __name__ == "__main__":
    main()
