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


def call_reducto(pdf_path: Path, api_key: str) -> str:
    """Call Reducto API to parse PDF and return markdown."""
    print("Parsing with Reducto...")

    with open(pdf_path, "rb") as f:
        pdf_data = f.read()

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{pdf_path.name}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + pdf_data
        + f"\r\n--{boundary}--\r\n".encode()
    )

    upload_req = urllib.request.Request(
        "https://platform.reducto.ai/upload",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    with urllib.request.urlopen(upload_req, timeout=120) as resp:
        upload_result = json.loads(resp.read().decode())

    file_url = (
        upload_result.get("file_id")
        or upload_result.get("file_url")
        or upload_result.get("url")
    )
    if not file_url:
        raise ValueError(f"No file_id in upload response: {upload_result}")

    parse_data = json.dumps({"document_url": file_url}).encode()
    parse_req = urllib.request.Request(
        "https://platform.reducto.ai/parse",
        data=parse_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(parse_req, timeout=300) as resp:
        result = json.loads(resp.read().decode())

    chunks = result.get("result", {}).get("chunks", [])
    return "\n\n".join(chunk.get("content", "") for chunk in chunks)


def strip_css_data_uris(html_path: Path) -> None:
    """Strip CSS background-image data URIs from HTML.

    Pandoc's --extract-media only handles <img> elements, not CSS background
    images. Large data URIs in CSS (e.g., LQIP placeholders) would otherwise
    end up inline in the markdown output, potentially exceeding LLM token limits.
    """
    html = html_path.read_text(errors="ignore")
    # Replace background-image:url(data:...) with background-image:none
    cleaned = re.sub(
        r"background-image:\s*url\(data:[^)]+\)", "background-image:none", html
    )
    if cleaned != html:
        html_path.write_text(cleaned)


def call_pandoc(html_path: Path, output_dir: Path) -> str:
    """Convert HTML to markdown with Pandoc, extracting images."""
    strip_css_data_uris(html_path)
    print("Converting with Pandoc...")
    cmd = [
        "pandoc",
        "-f",
        "html",
        "-t",
        "markdown",
        "--extract-media",
        "images",
        str(html_path.absolute()),
    ]

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
