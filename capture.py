#!/usr/bin/env python3
"""Capture websites as markdown with proper math, tables, and images."""

import argparse
import json
import os
import re
import shutil
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

SCRIPT_DIR = Path(__file__).parent
PROMPTS_DIR = SCRIPT_DIR / "prompts"
LLM_SCRIPT = Path.home() / "repos/dotfiles/scripts/llm.py"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


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


def call_pandoc(html_path: Path, output_dir: Path) -> str:
    """Convert HTML to markdown with Pandoc, extracting images."""
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

    template = load_prompt("merge")
    prompt = template.format(reducto_md=reducto_md, pandoc_md=pandoc_md)

    result = subprocess.run(
        ["python", str(LLM_SCRIPT), prompt],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def extract_metadata(markdown: str) -> dict:
    """Use llm.py to extract metadata from the markdown."""
    print("Extracting metadata...")

    template = load_prompt("metadata")
    prompt = template.format(markdown=markdown[:8000])  # Limit context size
    schema_path = PROMPTS_DIR / "metadata_schema.json"

    result = subprocess.run(
        ["python", str(LLM_SCRIPT), "--schema", str(schema_path), prompt],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe ASCII slug."""
    import unicodedata

    # Normalize unicode and convert to ASCII
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def add_frontmatter(markdown: str, metadata: dict, domain: str, url: str) -> str:
    """Add YAML frontmatter to markdown."""
    from datetime import date

    lines = [
        "---",
        f'title: "{metadata["title"]}"',
        f"domain: {domain}",
        f"url: {url}",
        f"capture_date: {date.today()}",
    ]
    if metadata.get("publish_date"):
        lines.append(f"publish_date: {metadata['publish_date']}")
    if metadata.get("tags"):
        lines.append("tags:")
        for tag in metadata["tags"]:
            lines.append(f"  - {tag}")
    lines.append("---")
    lines.append("")

    return "\n".join(lines) + markdown


def main():
    parser = argparse.ArgumentParser(description="Capture websites as markdown")
    parser.add_argument("url", help="URL to capture")
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output directory (folder will be created inside)",
    )
    parser.add_argument("-b", "--browser", help="Browser executable path")
    parser.add_argument(
        "--no-reducto",
        action="store_true",
        help="Skip Reducto + LLM merge, use pandoc only",
    )
    args = parser.parse_args()

    browser = args.browser or find_browser()
    if not browser:
        sys.exit(f"No browser found. Tried: {', '.join(BROWSER_CANDIDATES)}")

    # Extract domain from URL
    domain = args.url.removeprefix("https://").removeprefix("http://").split("/")[0]

    # Work in a temp folder first
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir) / "capture"
        work_dir.mkdir()

        html_path = work_dir / "page.html"
        md_path = work_dir / "page.md"

        # 1. Capture HTML
        capture_html(args.url, html_path, browser)

        if args.no_reducto:
            # Pandoc only
            pandoc_md = call_pandoc(html_path, work_dir)
            content_md = format_markdown(pandoc_md)
        else:
            # Default: Reducto + Pandoc + LLM merge
            reducto_key = os.environ.get("REDUCTO_API_KEY")
            if not reducto_key:
                sys.exit("Error: REDUCTO_API_KEY environment variable not set")

            # Convert HTML to PDF (in temp)
            pdf_path = Path(tmpdir) / "page.pdf"
            html_to_pdf(html_path, pdf_path, browser)

            # Get markdown from Reducto (math/tables)
            reducto_md = call_reducto(pdf_path, reducto_key)

            # Get markdown from Pandoc (images/links)
            pandoc_md = call_pandoc(html_path, work_dir)

            # Merge with LLM
            merged_md = merge_with_llm(reducto_md, pandoc_md)

            # Format with dprint
            content_md = format_markdown(merged_md)

        # 2. Extract metadata
        metadata = extract_metadata(content_md)

        # 3. Add frontmatter
        final_md = add_frontmatter(content_md, metadata, domain, args.url)
        md_path.write_text(final_md)

        # 4. Determine final folder name
        title_slug = slugify(metadata["title"])
        date_str = metadata.get("publish_date") or "unknown-date"
        folder_name = f"{domain} - {date_str} - {title_slug}"

        # 5. Move to final location
        output_base = Path(args.output)
        output_base.mkdir(parents=True, exist_ok=True)
        final_dir = output_base / folder_name

        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.move(str(work_dir), str(final_dir))

    print(f"Saved to {final_dir}/")


if __name__ == "__main__":
    main()
