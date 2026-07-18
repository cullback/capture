"""The capture pipeline: resolve, archive, convert, describe.

Each capture lands in its own folder:

    data/<domain> - <yyyy-mm-dd> - <slug>/
        <same name>.html   faithful single-file archive
        <same name>.md     markdown with TeX math preserved
        <same name>.pdf    canonical PDF, for sources that have one
        media/             downloaded images, referenced relatively
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse

from capture.extract import (
    challenge_page,
    normalize,
    page_slug,
    page_title,
    paywalled,
    published_date,
    slugify,
)
from capture.resolvers import (
    Resolution,
    arxiv_id,
    lesswrong_post,
    reddit_thread,
    resolve,
    wayback_snapshot,
    youtube_id,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

PANDOC_FORMAT = "html+tex_math_dollars+tex_math_single_backslash"


def capture(url: str) -> Path | None:
    resolution = resolve(url)
    if paywalled(resolution.html):
        print(f"skipped: paywalled, only a preview is public — {url}")
        return None
    domain = resolution.domain or urlparse(resolution.source).netloc.removeprefix(
        "www."
    )

    # single-file archives to a temp path outside data/, since the
    # folder name may depend on metadata that only exists after
    # rendering. Some sites stall headless chromium's navigation forever
    # (jaykmody.com) while serving plain fetches fine: degrade to the
    # raw HTML as artifact.
    artifact_html = resolution.html
    if resolution.use_browser and resolution.save_html:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "capture.html"
            if single_file(resolution.content, candidate) and candidate.exists():
                artifact_html = candidate.read_text()
            else:
                print("browser capture failed; archiving the plain fetch instead")
    if (
        not artifact_html
        and resolution.markdown is None
        and not resolution.skip_markdown
    ):
        raise RuntimeError(f"every fetcher failed for {url}")
    if resolution.markdown is None and challenge_page(artifact_html):
        # Bot checks served with HTTP 200 (steamdb) dodge the status
        # check; nothing real was fetched.
        raise RuntimeError(f"bot-check interstitial instead of content for {url}")

    # Client-rendered pages (e.g. AoPS, Obsidian Publish) serve a shell:
    # take metadata from the rendered DOM when the raw HTML carries no
    # title signal beyond the <title> tag.
    informative = page_title(resolution.html, domain, resolution.source) and re.search(
        r"<h1[\s>]|og:title", resolution.html
    )
    meta_html = resolution.html if informative else artifact_html
    title = resolution.title or page_title(meta_html, domain, resolution.source)
    publish = resolution.publish or (
        None if resolution.dateless else published_date(resolution.source, meta_html)
    )
    name_date = publish or resolution.fallback_date or date.today().isoformat()
    slug = slugify(title) or page_slug(resolution.source, meta_html)
    name = f"{domain} - {name_date} - {slug}"
    # Folder and file names stay ASCII: transliterate, then drop the rest.
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    folder = REPO_ROOT / "data" / name
    fresh = not folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return write_capture(resolution, folder, name, artifact_html, title, publish)
    except BaseException:
        # A failed capture leaves nothing behind — but never delete a
        # pre-existing folder during a --force re-capture.
        if fresh:
            shutil.rmtree(folder, ignore_errors=True)
        raise


def write_capture(
    resolution: Resolution,
    folder: Path,
    name: str,
    artifact_html: str,
    title: str,
    publish: str | None,
) -> Path:
    if artifact_html and resolution.save_html:
        (folder / f"{name}.html").write_text(artifact_html)

    if resolution.download_media:
        resolution.download_media(folder, name)

    if resolution.pdf_url:
        subprocess.run(
            [
                "curl",
                "-sL",
                "--max-time",
                "300",
                "-o",
                str(folder / f"{name}.pdf"),
                resolution.pdf_url,
            ],
            check=False,
        )

    # Prefer converting from the URL so relative image paths resolve; fall
    # back to the local artifact when the direct fetch fails or the raw
    # HTML had no real content. Ready-made markdown skips conversion.
    if resolution.skip_markdown:
        return folder

    markdown = folder / f"{name}.md"
    if resolution.markdown is not None:
        markdown.write_text(localize_images(resolution.markdown, folder))
    elif (
        not resolution.use_browser
        or not pandoc(resolution.content, markdown.name, folder)
        or junk_conversion(markdown)
    ):
        # The fallback converts the artifact file; when save_html is off
        # it exists only for the duration of the conversion.
        fallback = folder / f"{name}.html"
        temporary = not fallback.exists() and bool(artifact_html)
        if temporary:
            fallback.write_text(artifact_html)
        pandoc(fallback.name, markdown.name, folder)
        if temporary:
            fallback.unlink()

    markdown.write_text(frontmatter(resolution, title, publish) + markdown.read_text())
    format_markdown(markdown)
    return folder


def frontmatter(resolution: Resolution, title: str, publish: str | None) -> str:
    domain = urlparse(resolution.source).netloc.removeprefix("www.")
    lines = [
        "---",
        f"title: {json.dumps(title or 'Untitled', ensure_ascii=False)}",
        f"domain: {domain}",
        f"url: {resolution.source}",
    ]
    for key, value in resolution.extra.items():
        if value:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    if resolution.archive:
        lines.append(f"archive: {resolution.archive}")
    if hn := hackernews_url(resolution.source):
        lines.append(f"hackernews: {hn}")
    lines.append(f"capture_date: {date.today().isoformat()}")
    if publish:
        # Omitted when no publish date was found: the folder falls back
        # to the capture date, and absence here records that honestly.
        lines.append(f"publish_date: {publish}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def hackernews_url(url: str) -> str | None:
    """Best submission of this URL, via the Algolia search API."""
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


def single_file(url: str, output: Path) -> bool:
    result = subprocess.run(
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
    )
    return result.returncode == 0


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


def localize_images(text: str, folder: Path) -> str:
    """Download remote images referenced by ready-made markdown into
    media/ and rewrite the links, mirroring pandoc's --extract-media
    for the conversion path. Failures keep the remote URL."""

    def fetch(url: str) -> str:
        suffix = Path(urlparse(url).path).suffix
        if not (0 < len(suffix) <= 5 and suffix[1:].isalnum()):
            suffix = ""
        name = hashlib.sha1(url.encode()).hexdigest()[:16] + suffix
        target = folder / "media" / name
        if not target.exists():
            (folder / "media").mkdir(exist_ok=True)
            result = subprocess.run(
                [
                    "curl",
                    "-sL",
                    "--max-time",
                    "120",
                    "-A",
                    "capture/0.1",
                    "-o",
                    str(target),
                    url,
                ],
                capture_output=True,
            )
            if result.returncode != 0 or not target.stat().st_size:
                target.unlink(missing_ok=True)
                return url
        return f"media/{name}"

    text = re.sub(
        r"(!\[[^\]]*\]\()(https?://[^)\s]+)",
        lambda m: m.group(1) + fetch(m.group(2)),
        text,
    )
    return re.sub(
        r'(<img[^>]*\bsrc=")(https?://[^"]+)(")',
        lambda m: m.group(1) + fetch(m.group(2)) + m.group(3),
        text,
    )


def thin(markdown: Path) -> bool:
    return not markdown.exists() or len(markdown.read_text().split()) < 150


def junk_conversion(markdown: Path) -> bool:
    """A conversion that fetched an interstitial rather than the page:
    too short, or wayback's banner menus instead of content."""
    if thin(markdown):
        return True
    return "Expand web menu" in markdown.read_text(errors="replace")[:3000]


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
    if vid := youtube_id(url):
        # Video captures have no markdown; match the id in info.json.
        for info in sorted((REPO_ROOT / "data").glob("*/*.info.json")):
            if f'"id": "{vid}"' in info.read_text(errors="replace"):
                return info.parent
        return None
    target = normalize(url)
    if aid := arxiv_id(url):
        target = normalize(f"https://arxiv.org/abs/{aid}")
    elif thread := reddit_thread(url):
        target = normalize(
            f"https://www.reddit.com/r/{thread[0]}/comments/{thread[1]}/"
        )
    elif snapshot := wayback_snapshot(url):
        target = normalize(snapshot[1])
    elif post := lesswrong_post(url):
        target = normalize(f"https://www.lesswrong.com/posts/{post[0]}/{post[1]}")
    for markdown in sorted((REPO_ROOT / "data").glob("*/*.md")):
        header = markdown.read_text(errors="replace")[:600]
        for line in header.splitlines():
            key, _, value = line.partition(": ")
            if key in ("url", "archive") and normalize(value.strip()) == target:
                return markdown.parent
    return None
