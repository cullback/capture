"""The capture pipeline: resolve, archive, convert, describe.

Each capture lands in its own folder under the destination:

    <domain> - <yyyy-mm-dd> - <slug>/
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
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from capture.discussions import discussions
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
    FetchError,
    Resolution,
    arxiv_id,
    fetch_html,
    lesswrong_post,
    path_identity_domain,
    reddit_thread,
    resolve,
    wayback_fallback,
    wayback_snapshot,
    youtube_id,
)

# Everything the pipeline needs at runtime ships inside the package,
# so an installed capture works the same as a repo checkout.
PACKAGE = Path(__file__).resolve().parent

PANDOC_FORMAT = "html+tex_math_dollars+tex_math_single_backslash"


def capture(
    url: str, origin: str | None = None, destination: Path | None = None
) -> Path | None:
    target = Path(url)
    if target.is_file():
        from capture.resolvers.pdf import resolve_local_pdf

        resolution = resolve_local_pdf(target, origin)
    else:
        resolution = resolve(url)
    if paywalled(resolution.html):
        print(f"skipped: paywalled, only a preview is public — {url}")
        return None
    domain = resolution.domain or urlparse(resolution.source).netloc.removeprefix(
        "www."
    )

    # single-file archives to a temp path outside the destination, since
    # the folder name may depend on metadata that only exists after
    # rendering. When the browser cannot deliver — it has stalled on a
    # site's navigation before — degrade to the raw HTML as artifact and
    # say so in the frontmatter, since such failures have proven
    # temporary: jaykmody.com stalled long enough to earn a mention here
    # and now archives in five seconds.
    artifact_html = resolution.html
    # Whether the .html is a plain fetch rather than a browser archive:
    # true for archive.today, which the resolvers deliberately curl, and
    # for every path below that falls back to the raw document.
    degraded = True
    if resolution.use_browser and resolution.save_html:
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "capture.html"
            if single_file(resolution.content, candidate) and candidate.exists():
                artifact_html = candidate.read_text()
                degraded = False
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
        # check; nothing real was fetched. The Wayback Machine may hold
        # a real copy from a luckier crawl (dl.acm.org PDFs): recapture
        # through the newest snapshot, which keeps the original URL's
        # identity for naming, frontmatter, and dedup.
        #
        # Wayback comes first even when the plain fetch looks fine,
        # because capturing a snapshot runs the browser over it and
        # yields an archive that renders offline, where the plain fetch
        # is a bare document whose styles and images live elsewhere.
        if snapshot := wayback_fallback(url):
            print(f"bot check defeated the archive; capturing {snapshot}")
            return capture(snapshot, destination=destination)
        if resolution.html and not challenge_page(resolution.html):
            # Last resort: only the browser was challenged.
            # randomascii.wordpress.com hands curl the whole article and
            # chromium an interstitial, and a document we can read beats
            # no capture — recorded as `artifact: fetch`.
            print("browser got a bot check; archiving the plain fetch instead")
            artifact_html = resolution.html
            degraded = True
        else:
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
    name = folder_name(
        domain, resolution.source, meta_html, title, publish, resolution.fallback_date
    )
    folder = (destination or Path.cwd()) / name
    fresh = not folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return write_capture(
            resolution, folder, name, artifact_html, title, publish, degraded
        )
    except BaseException:
        # A failed capture leaves nothing behind — but never delete a
        # pre-existing folder during a --force re-capture.
        if fresh:
            shutil.rmtree(folder, ignore_errors=True)
        raise


def folder_name(
    domain: str,
    source: str,
    html: str,
    title: str,
    publish: str | None,
    fallback_date: str | None = None,
) -> str:
    """The `<domain> - <date> - <slug>` capture folder name, kept ASCII by
    transliterating and then dropping whatever will not transliterate."""
    name_date = publish or fallback_date or date.today().isoformat()
    slug = slugify(title) or page_slug(source, html)
    name = f"{domain} - {name_date} - {slug}"
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()


def bookmark(url: str, origin: str | None, destination: Path | None) -> Path:
    """A lightweight capture: one plain fetch to name the folder well, then
    just a .url internet shortcut — no browser, media, or markdown. For
    pages worth recording in the corpus but not worth archiving in full."""
    source = origin or url
    domain = path_identity_domain(source) or urlparse(source).netloc.removeprefix(
        "www."
    )
    try:
        html = fetch_html(url)
    except FetchError:
        # A bookmark records the URL regardless; without the page the
        # folder name falls back to the URL path and today's date.
        html = ""
    title = page_title(html, domain, source)
    publish = published_date(source, html) if html else None
    name = folder_name(domain, source, html, title, publish)
    folder = (destination or Path.cwd()) / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.url").write_text(internet_shortcut(source))
    return folder


def internet_shortcut(url: str) -> str:
    """A Windows .url shortcut. CRLF is the format's canonical line ending;
    the [InternetShortcut] section is what makes it click-to-open."""
    return f"[InternetShortcut]\r\nURL={url}\r\n"


def write_capture(
    resolution: Resolution,
    folder: Path,
    name: str,
    artifact_html: str,
    title: str,
    publish: str | None,
    degraded: bool = False,
) -> Path:
    wrote_html = bool(artifact_html) and resolution.save_html
    if wrote_html:
        (folder / f"{name}.html").write_text(artifact_html)
    # Only an .html we actually wrote can be a plain fetch. A repo's
    # bundle or a paper's PDF has no browser archive to fall short of.
    degraded = degraded and wrote_html

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
    elif resolution.article_html:
        # The source hands over the piece without its page chrome, which
        # beats converting the rendered page and subtracting furniture.
        article = folder / "article.html"
        article.write_text(resolution.article_html)
        pandoc(article.name, markdown.name, folder)
        article.unlink()
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

    body = markdown.read_text()
    if resolution.markdown_suffix:
        # Content the page withholds from its own HTML — substack serves
        # two comments and lazy-loads the rest.
        body = body.rstrip("\n") + "\n" + resolution.markdown_suffix
    markdown.write_text(frontmatter(resolution, title, publish, degraded) + body)
    format_markdown(markdown)
    return folder


def frontmatter(
    resolution: Resolution, title: str, publish: str | None, degraded: bool = False
) -> str:
    domain = urlparse(resolution.source).netloc.removeprefix("www.")
    lines = [
        "---",
        f"title: {json.dumps(title or 'Untitled', ensure_ascii=False)}",
    ]
    if domain:
        lines.append(f"domain: {domain}")
    if resolution.source:
        # Omitted for local ingests without an --origin: no known URL.
        lines.append(f"url: {resolution.source}")
    for key, value in resolution.extra.items():
        if value:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    if resolution.archive:
        lines.append(f"archive: {resolution.archive}")
    if degraded:
        # Said out loud, because it is the difference between an archive
        # that renders offline and a bare document whose styles and
        # images live on a server that may not outlast the capture.
        # Absence means the normal case: a single-file browser archive.
        lines.append("artifact: fetch")
    if resolution.source:
        lines.extend(discussion_lines(discussions(resolution.source, title)))
    lines.append(f"capture_date: {date.today().isoformat()}")
    if publish:
        # Omitted when no publish date was found: the folder falls back
        # to the capture date, and absence here records that honestly.
        lines.append(f"publish_date: {publish}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def discussion_lines(threads: list[str]) -> list[str]:
    """The `discussions` frontmatter block. An empty list is written
    explicitly: it says the sources were searched and found nothing,
    which absence could not distinguish from never having looked."""
    if not threads:
        return ["discussions: []"]
    return ["discussions:"] + [f"  - {thread}" for thread in threads]


def single_file(url: str, output: Path) -> bool:
    # The packaged script is the canonical home of the hardened browser
    # flags. Invoked through fish explicitly: wheels drop execute bits.
    script = PACKAGE / "scripts" / "single-file-archive"
    result = subprocess.run(["fish", str(script), url, str(output)])
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
            f"--lua-filter={PACKAGE / 'filters' / 'clean.lua'}",
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
    # Via stdin against the packaged config, so formatting doesn't
    # depend on whatever dprint.json the working directory carries.
    result = subprocess.run(
        [
            "dprint",
            "fmt",
            "--config",
            str(PACKAGE / "markdown-fmt.json"),
            "--stdin",
            "capture.md",
        ],
        input=markdown.read_text(),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout:
        markdown.write_text(result.stdout)


def existing_capture(url: str, root: Path | None = None) -> Path | None:
    """The folder already holding this URL, matched via frontmatter."""
    root = root or Path.cwd()
    if vid := youtube_id(url):
        # Video captures have no markdown; match the id in info.json.
        for info in sorted(root.glob("*/*.info.json")):
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
    for markdown in sorted(root.glob("*/*.md")):
        header = markdown.read_text(errors="replace")[:600]
        for line in header.splitlines():
            key, _, value = line.partition(": ")
            if key in ("url", "archive") and normalize(value.strip()) == target:
                return markdown.parent
    for shortcut in sorted(root.glob("*/*.url")):
        # Lightweight --url bookmarks carry the URL in the shortcut itself.
        for line in shortcut.read_text(errors="replace").splitlines():
            if line.startswith("URL=") and normalize(line[4:].strip()) == target:
                return shortcut.parent
    return None
