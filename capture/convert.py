"""External tool wrappers for capture pipeline."""

import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

BROWSER_CANDIDATES = [
    "chrome",
    "chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
]


def find_browser() -> str | None:
    """Find an available browser."""
    for candidate in BROWSER_CANDIDATES:
        result = subprocess.run(["which", candidate], capture_output=True, check=False)
        if result.returncode == 0:
            return candidate
    return None


def capture_html(url: str, output: Path, browser: str) -> None:
    """Capture webpage as HTML using single-file."""
    print(f"Capturing {url}...")
    subprocess.run(
        ["single-file", "--browser-executable-path", browser, url, str(output)],
        check=True,
    )


def html_to_pdf(html_path: Path, pdf_path: Path, browser: str) -> None:
    """Convert HTML to PDF using headless Chrome."""
    print("Converting to PDF...")
    subprocess.run(
        [
            browser,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            f"--print-to-pdf={pdf_path}",
            str(html_path),
        ],
        check=True,
        capture_output=True,
    )


def strip_css_data_uris(html_path: Path) -> None:
    """Strip CSS data URIs from HTML (fonts, background images, etc).

    Pandoc's --extract-media only handles <img> elements, not CSS data URIs.
    Large embedded fonts, emoji sprite sheets, and LQIP placeholders would
    otherwise end up inline in the markdown output, exceeding LLM token limits.
    """
    html = html_path.read_text(errors="ignore")
    original = html

    # Replace background-image:url(data:...) with background-image:none
    html = re.sub(
        r"background-image:\s*url\(data:[^)]+\)", "background-image:none", html
    )

    # Replace background:url(data:...) shorthand (e.g., emoji sprites)
    html = re.sub(r"background:\s*url\(data:[^)]+\)", "background:none", html)

    # Remove font data URIs: url(data:font/...) or url("data:font/...")
    html = re.sub(r'url\(["\']?data:font/[^)]+\)', "url()", html)

    if html != original:
        html_path.write_text(html)


def call_pandoc(
    html_path: Path, output_dir: Path, *, extract_images: bool = True
) -> str:
    """Convert HTML to markdown with Pandoc, optionally extracting images."""
    strip_css_data_uris(html_path)
    print("Converting with Pandoc...")
    cmd = [
        "pandoc",
        "-f",
        "html",
        "-t",
        "markdown",
    ]
    if extract_images:
        cmd += ["--extract-media", "images"]
    cmd.append(str(html_path.absolute()))

    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, cwd=output_dir
    )
    return result.stdout


def find_hn_thread(url: str) -> str | None:
    """Find the HN thread with the most comments for a given URL."""
    try:
        query = urllib.parse.urlencode(
            {
                "query": url,
                "restrictSearchableAttributes": "url",
                "tags": "story",
            }
        )
        api_url = f"https://hn.algolia.com/api/v1/search?{query}"
        req = urllib.request.Request(api_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        hits = data.get("hits", [])
        if not hits:
            return None
        best = max(hits, key=lambda h: h.get("num_comments", 0))
        return f"https://news.ycombinator.com/item?id={best['objectID']}"
    except Exception:
        return None


def format_markdown(content: str) -> str:
    """Format markdown using dprint."""
    print("Formatting with dprint...")
    result = subprocess.run(
        ["dprint", "fmt", "--stdin", "md"],
        input=content,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"Warning: dprint failed (exit {result.returncode}), skipping formatting")
        return content
    return result.stdout
