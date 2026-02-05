"""CLI entrypoint and orchestration for capture pipeline."""

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from capture.convert import (
    BROWSER_CANDIDATES,
    call_pandoc,
    call_reducto,
    capture_html,
    find_browser,
    find_hn_thread,
    format_markdown,
    html_to_pdf,
)
from capture.llm import cleanup_markdown, extract_metadata
from capture.markdown import add_frontmatter, slugify, strip_frontmatter


def main():
    parser = argparse.ArgumentParser(description="Capture websites as markdown")
    parser.add_argument("input", nargs="?", help="URL, PDF, or HTML file to capture")
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory (folder will be created inside)",
    )
    parser.add_argument("-b", "--browser", help="Browser executable path")
    parser.add_argument(
        "--no-reducto",
        action="store_true",
        help="Skip Reducto + LLM merge, use pandoc only",
    )
    parser.add_argument(
        "--retag",
        metavar="FOLDER",
        help="Re-extract tags for an existing capture folder",
    )
    args = parser.parse_args()

    # Handle retag mode
    if args.retag:
        retag(Path(args.retag))
        return

    # Normal capture mode requires input and output
    if not args.input:
        parser.error("input is required for capture mode")
    if not args.output:
        parser.error("-o/--output is required for capture mode")

    # Detect PDF, HTML, or URL
    input_path = Path(args.input)
    is_pdf = input_path.suffix.lower() == ".pdf" and input_path.exists()
    is_html = input_path.suffix.lower() in (".html", ".htm") and input_path.exists()

    if is_pdf:
        capture_pdf(input_path, Path(args.output))
    elif is_html:
        capture_html_file(input_path, Path(args.output), args.browser, args.no_reducto)
    else:
        capture_url(args.input, Path(args.output), args.browser, args.no_reducto)


def capture_pdf(pdf_path: Path, output_base: Path) -> None:
    """Capture a local PDF file as markdown via Reducto."""
    reducto_key = os.environ.get("REDUCTO_API_KEY")
    if not reducto_key:
        sys.exit("Error: REDUCTO_API_KEY environment variable not set")

    source = pdf_path.stem

    work_dir = output_base / "tmp_capture"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Parse PDF with Reducto and clean up
        reducto_md = call_reducto(pdf_path, reducto_key)
        content_md = cleanup_markdown(reducto_md)
        content_md = format_markdown(content_md)

        # 2. Extract metadata
        metadata = extract_metadata(content_md)

        # 3. Determine final folder name
        title_slug = slugify(metadata["title"])
        date_str = metadata.get("publish_date") or "unknown-date"
        folder_name = f"{source} - {date_str} - {title_slug}"

        # 4. Add frontmatter and format
        final_md = add_frontmatter(content_md, metadata, domain=source, url="")
        final_md = format_markdown(final_md)
        (work_dir / f"{folder_name}.md").write_text(final_md)

        # 5. Copy original PDF
        shutil.copy2(pdf_path, work_dir / f"{folder_name}.pdf")

        # 6. Move to final location
        final_dir = output_base / folder_name
        if final_dir.exists():
            shutil.rmtree(final_dir)
        work_dir.rename(final_dir)

        print(f"Saved to {final_dir}/")
    except Exception:
        if work_dir.exists():
            shutil.rmtree(work_dir)
        raise


def extract_singlefile_url(html_path: Path) -> str | None:
    """Extract the original URL from a SingleFile HTML comment."""
    head = html_path.read_text(errors="ignore")[:2000]
    match = re.search(r"url:\s*(https?://\S+)", head)
    if not match:
        return None
    url = match.group(1).split("?")[0].rstrip()
    return url


def capture_html_file(
    html_path: Path, output_base: Path, browser_arg: str | None, no_reducto: bool
) -> None:
    """Capture a local HTML file as markdown."""
    # Try to extract original URL from SingleFile metadata
    source_url = extract_singlefile_url(html_path) or ""
    if source_url:
        domain = (
            source_url.removeprefix("https://").removeprefix("http://").split("/")[0]
        )
    else:
        domain = html_path.stem

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir) / "capture"
        work_dir.mkdir()

        # Copy HTML into work dir
        work_html = work_dir / "page.html"
        shutil.copy2(html_path, work_html)

        if no_reducto:
            pandoc_md = call_pandoc(work_html, work_dir)
            content_md = format_markdown(pandoc_md)
        else:
            reducto_key = os.environ.get("REDUCTO_API_KEY")
            if not reducto_key:
                sys.exit("Error: REDUCTO_API_KEY environment variable not set")

            browser = browser_arg or find_browser()
            if not browser:
                sys.exit(f"No browser found. Tried: {', '.join(BROWSER_CANDIDATES)}")

            pdf_path = Path(tmpdir) / "page.pdf"
            html_to_pdf(work_html, pdf_path, browser)

            reducto_md = call_reducto(pdf_path, reducto_key)
            pandoc_md = call_pandoc(work_html, work_dir)
            merged_md = cleanup_markdown(reducto_md, pandoc_md)
            content_md = format_markdown(merged_md)

        # Extract metadata
        metadata = extract_metadata(content_md)

        # Determine final folder name
        title_slug = slugify(metadata["title"])
        date_str = metadata.get("publish_date") or "unknown-date"
        folder_name = f"{domain} - {date_str} - {title_slug}"

        # Look up HN thread
        hn_url = find_hn_thread(source_url) if source_url else None

        # Add frontmatter, format, and rename files
        final_md = add_frontmatter(
            content_md, metadata, domain=domain, url=source_url, hackernews=hn_url
        )
        final_md = format_markdown(final_md)
        (work_dir / f"{folder_name}.md").write_text(final_md)
        work_html.rename(work_dir / f"{folder_name}.html")

        # Move to final location
        output_base.mkdir(parents=True, exist_ok=True)
        final_dir = output_base / folder_name

        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.move(str(work_dir), str(final_dir))

    print(f"Saved to {final_dir}/")


def capture_url(
    url: str, output_base: Path, browser_arg: str | None, no_reducto: bool
) -> None:
    """Capture a URL as markdown."""
    browser = browser_arg or find_browser()
    if not browser:
        sys.exit(f"No browser found. Tried: {', '.join(BROWSER_CANDIDATES)}")

    domain = url.removeprefix("https://").removeprefix("http://").split("/")[0]

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir) / "capture"
        work_dir.mkdir()

        html_path = work_dir / "page.html"

        # 1. Capture HTML
        capture_html(url, html_path, browser)

        if no_reducto:
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
            merged_md = cleanup_markdown(reducto_md, pandoc_md)

            # Format with dprint
            content_md = format_markdown(merged_md)

        # 2. Extract metadata
        metadata = extract_metadata(content_md)

        # 3. Determine final folder name
        title_slug = slugify(metadata["title"])
        date_str = metadata.get("publish_date") or "unknown-date"
        folder_name = f"{domain} - {date_str} - {title_slug}"

        # 4. Look up HN thread
        hn_url = find_hn_thread(url)

        # 5. Add frontmatter, format, and rename files to match folder
        final_md = add_frontmatter(content_md, metadata, domain, url, hackernews=hn_url)
        final_md = format_markdown(final_md)
        (work_dir / f"{folder_name}.md").write_text(final_md)
        html_path.rename(work_dir / f"{folder_name}.html")

        # 6. Move to final location
        output_base.mkdir(parents=True, exist_ok=True)
        final_dir = output_base / folder_name

        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.move(str(work_dir), str(final_dir))

    print(f"Saved to {final_dir}/")


def retag(folder_path: Path) -> None:
    """Re-extract metadata and update frontmatter for an existing capture."""
    md_files = list(folder_path.glob("*.md"))
    if not md_files:
        sys.exit(f"Error: no .md file found in {folder_path}")
    md_path = md_files[0]

    # Read and strip existing frontmatter
    original = md_path.read_text()
    old_frontmatter, content = strip_frontmatter(original)

    if not old_frontmatter:
        sys.exit("Error: No frontmatter found in file")

    # Re-extract metadata
    metadata = extract_metadata(content)

    # Look up HN thread, preserving existing value on failure
    source_url = old_frontmatter.get("url", "")
    hn_url = find_hn_thread(source_url) if source_url else None
    if not hn_url:
        hn_url = old_frontmatter.get("hackernews")

    # Rebuild with preserved fields
    final_md = add_frontmatter(
        content,
        metadata,
        domain=old_frontmatter.get("domain", "unknown"),
        url=source_url,
        capture_date=str(old_frontmatter.get("capture_date", "")),
        hackernews=hn_url,
    )
    final_md = format_markdown(final_md)
    md_path.write_text(final_md)

    print(f"Updated {md_path}")


if __name__ == "__main__":
    main()
