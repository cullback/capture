#!/usr/bin/env python3
"""Capture websites as markdown with proper math, tables, and images."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BROWSER_CANDIDATES = [
    "chrome",
    "chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
]

LLM_SCRIPT = Path.home() / "repos/dotfiles/scripts/llm.py"

MERGE_PROMPT = """You are merging two markdown versions of the same webpage.

VERSION A (from Reducto - has accurate math equations and tables):
{reducto_md}

VERSION B (from Pandoc - has image references and hyperlinks):
{pandoc_md}

Create a final merged markdown that:
1. Uses VERSION A's math equations (LaTeX format) and table formatting
2. Inserts image references from VERSION B in the appropriate locations
3. Preserves hyperlinks from VERSION B
4. Preserves the document structure and flow
5. Removes any duplicate content

Output ONLY the merged markdown, no explanations."""


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


def call_pandoc(html_path: Path, images_dir: Path | None) -> str:
    """Convert HTML to markdown with Pandoc, optionally extracting images."""
    print("Converting with Pandoc...")
    cmd = ["pandoc", "-f", "html", "-t", "markdown", str(html_path)]

    if images_dir:
        cmd.extend(["--extract-media", str(images_dir)])

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def format_markdown(content: str) -> str:
    """Format markdown using dprint."""
    print("Formatting with dprint...")
    result = subprocess.run(
        ["dprint", "fmt", "--stdin", "md"],
        input=content,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def merge_with_llm(reducto_md: str, pandoc_md: str) -> str:
    """Use llm.py to merge the two markdown versions."""
    print("Merging with LLM...")

    prompt = MERGE_PROMPT.format(reducto_md=reducto_md, pandoc_md=pandoc_md)

    result = subprocess.run(
        ["python", str(LLM_SCRIPT), prompt],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description="Capture websites as markdown")
    parser.add_argument("url", help="URL to capture")
    parser.add_argument("-o", "--output", help="Output markdown file")
    parser.add_argument("-b", "--browser", help="Browser executable path")
    parser.add_argument(
        "-i", "--extract-images", action="store_true", help="Extract images to folder"
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Simple mode: just pandoc, no Reducto/LLM merge",
    )
    args = parser.parse_args()

    browser = args.browser or find_browser()
    if not browser:
        sys.exit(f"No browser found. Tried: {', '.join(BROWSER_CANDIDATES)}")

    # Determine output paths
    if args.output:
        output_md = Path(args.output)
    else:
        from datetime import date

        url_host = (
            args.url.removeprefix("https://").removeprefix("http://").split("/")[0]
        )
        output_md = Path(f"{url_host} - {date.today()}.md")

    output_base = output_md.with_suffix("")
    html_path = output_base.with_suffix(".html")
    images_dir = Path(str(output_base) + "-images") if args.extract_images else None

    # 1. Capture HTML (keep for reference)
    capture_html(args.url, html_path, browser)

    if args.simple:
        # Simple mode: just pandoc
        pandoc_md = call_pandoc(html_path, images_dir)
        final_md = format_markdown(pandoc_md)
        output_md.write_text(final_md)
    else:
        # Full mode: Reducto + Pandoc + LLM merge
        reducto_key = os.environ.get("REDUCTO_API_KEY")
        if not reducto_key:
            sys.exit("Error: REDUCTO_API_KEY environment variable not set")

        with tempfile.TemporaryDirectory() as tmpdir:
            # 2. Convert HTML to PDF
            pdf_path = Path(tmpdir) / "page.pdf"
            html_to_pdf(html_path, pdf_path, browser)

            # 3. Get markdown from Reducto (math/tables)
            reducto_md = call_reducto(pdf_path, reducto_key)

        # 4. Get markdown from Pandoc (images/links)
        pandoc_md = call_pandoc(html_path, images_dir)

        # 5. Merge with LLM
        merged_md = merge_with_llm(reducto_md, pandoc_md)

        # 6. Format with dprint
        final_md = format_markdown(merged_md)
        output_md.write_text(final_md)

    print(f"Saved to {output_md}")
    if html_path.exists():
        print(f"HTML saved to {html_path}")


if __name__ == "__main__":
    main()
