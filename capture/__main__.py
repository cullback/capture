"""CLI entrypoint and orchestration for capture pipeline."""

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

from capture.convert import (
    BROWSER_CANDIDATES,
    call_pandoc,
    capture_html,
    find_browser,
    find_hn_thread,
    format_markdown,
    html_to_pdf,
)
from capture.llm import generate_markdown
from capture.markdown import slugify, strip_frontmatter


def main():
    parser = argparse.ArgumentParser(description="Capture websites as markdown")
    parser.add_argument("input", nargs="?", help="URL, PDF, or HTML file to capture")
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory (folder will be created inside)",
    )
    parser.add_argument("-b", "--browser", help="Browser executable path")
    parser.add_argument("-d", "--domain", help="Override domain for PDF/HTML captures")
    parser.add_argument("-n", "--name", help="Override output folder name")
    parser.add_argument(
        "--no-images", action="store_true", help="Don't save image files"
    )
    args = parser.parse_args()

    # Capture mode requires input and output
    if not args.input:
        parser.error("input is required for capture mode")
    if not args.output:
        parser.error("-o/--output is required for capture mode")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Detect PDF, HTML, or URL
    input_path = Path(args.input)
    is_pdf = input_path.suffix.lower() == ".pdf" and input_path.exists()
    is_html = input_path.suffix.lower() in (".html", ".htm") and input_path.exists()

    if is_pdf:
        capture_pdf(input_path, output_dir, args.domain, args.name)
        input_path.unlink()
    elif is_html:
        capture_html_file(
            input_path,
            output_dir,
            args.browser,
            args.domain,
            args.name,
            args.no_images,
        )
        input_path.unlink()
    else:
        capture_url(args.input, output_dir, args.browser, args.name, args.no_images)


def capture_pdf(
    pdf_path: Path,
    output_base: Path,
    domain_override: str | None,
    name_override: str | None,
) -> None:
    """Capture a local PDF file as markdown via vision LLM."""
    from datetime import date

    source = (
        domain_override.removeprefix("https://").removeprefix("http://").split("/")[0]
        if domain_override
        else pdf_path.stem
    )

    work_dir = output_base / "tmp_capture"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Generate markdown with LLM (no pandoc for direct PDF)
        capture_date = str(date.today())
        raw_md = generate_markdown(pdf_path, None, source, "", capture_date)
        final_md = format_markdown(raw_md)

        # 2. Extract metadata from generated frontmatter for folder naming
        frontmatter, _ = strip_frontmatter(final_md)
        title_slug = slugify(frontmatter["title"])
        date_str = frontmatter.get("publish_date") or "unknown-date"
        folder_name = name_override or f"{source} - {date_str} - {title_slug}"

        # 3. Save markdown and copy original PDF
        (work_dir / f"{folder_name}.md").write_text(final_md)
        shutil.copy2(pdf_path, work_dir / f"{folder_name}.pdf")

        # 4. Move to final location
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
    html_path: Path,
    output_base: Path,
    browser_arg: str | None,
    domain_override: str | None,
    name_override: str | None,
    no_images: bool,
) -> None:
    """Capture a local HTML file as markdown."""
    from datetime import date

    # Try to extract original URL from SingleFile metadata
    source_url = extract_singlefile_url(html_path) or ""
    if domain_override:
        domain = (
            domain_override.removeprefix("https://")
            .removeprefix("http://")
            .split("/")[0]
        )
    elif source_url:
        domain = (
            source_url.removeprefix("https://").removeprefix("http://").split("/")[0]
        )
    else:
        domain = html_path.stem

    browser = browser_arg or find_browser()
    if not browser:
        sys.exit(f"No browser found. Tried: {', '.join(BROWSER_CANDIDATES)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir) / "capture"
        work_dir.mkdir()

        # Copy HTML into work dir
        work_html = work_dir / "page.html"
        shutil.copy2(html_path, work_html)

        # Convert to PDF and get pandoc markdown
        pdf_path = Path(tmpdir) / "page.pdf"
        html_to_pdf(work_html, pdf_path, browser)
        pandoc_md = call_pandoc(work_html, work_dir, extract_images=not no_images)

        # Look up HN thread
        hn_url = find_hn_thread(source_url) if source_url else None

        # Generate markdown with LLM
        capture_date = str(date.today())
        raw_md = generate_markdown(
            pdf_path, pandoc_md, domain, source_url, capture_date, hn_url
        )
        final_md = format_markdown(raw_md)

        # Extract metadata from generated frontmatter for folder naming
        frontmatter, _ = strip_frontmatter(final_md)
        title_slug = slugify(frontmatter["title"])
        date_str = frontmatter.get("publish_date") or "unknown-date"
        folder_name = name_override or f"{domain} - {date_str} - {title_slug}"

        # Save markdown and rename HTML
        (work_dir / f"{folder_name}.md").write_text(final_md)
        work_html.rename(work_dir / f"{folder_name}.html")

        # Remove images directory if no_images
        if no_images:
            images_dir = work_dir / "images"
            if images_dir.exists():
                shutil.rmtree(images_dir)

        # Move to final location
        output_base.mkdir(parents=True, exist_ok=True)
        final_dir = output_base / folder_name

        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.move(str(work_dir), str(final_dir))

    print(f"Saved to {final_dir}/")


def capture_url(
    url: str,
    output_base: Path,
    browser_arg: str | None,
    name_override: str | None,
    no_images: bool,
) -> None:
    """Capture a URL as markdown."""
    from datetime import date

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

        # 2. Convert to PDF and get pandoc markdown
        pdf_path = Path(tmpdir) / "page.pdf"
        html_to_pdf(html_path, pdf_path, browser)
        pandoc_md = call_pandoc(html_path, work_dir, extract_images=not no_images)

        # 3. Look up HN thread
        hn_url = find_hn_thread(url)

        # 4. Generate markdown with LLM
        capture_date = str(date.today())
        raw_md = generate_markdown(
            pdf_path, pandoc_md, domain, url, capture_date, hn_url
        )
        final_md = format_markdown(raw_md)

        # 5. Extract metadata from generated frontmatter for folder naming
        frontmatter, _ = strip_frontmatter(final_md)
        title_slug = slugify(frontmatter["title"])
        date_str = frontmatter.get("publish_date") or "unknown-date"
        folder_name = name_override or f"{domain} - {date_str} - {title_slug}"

        # 6. Save markdown and rename HTML
        (work_dir / f"{folder_name}.md").write_text(final_md)

        html_path.rename(work_dir / f"{folder_name}.html")

        # 7. Remove images directory if no_images
        if no_images:
            images_dir = work_dir / "images"
            if images_dir.exists():
                shutil.rmtree(images_dir)

        # 8. Move to final location
        output_base.mkdir(parents=True, exist_ok=True)
        final_dir = output_base / folder_name

        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.move(str(work_dir), str(final_dir))

    print(f"Saved to {final_dir}/")


if __name__ == "__main__":
    main()
