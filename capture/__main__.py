"""CLI entry point: capture a web page into a destination folder."""

import argparse
import shutil
import sys
from pathlib import Path

from capture.pipeline import bookmark, capture, existing_capture


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="capture",
        description="Save a URL or local PDF as a self-contained archive folder:\n"
        "the content in its most faithful form (single-file HTML for pages,\n"
        "the typeset PDF for papers, archival video for YouTube, a git bundle\n"
        "for repos) plus a markdown conversion with YAML frontmatter.",
        epilog="environment:\n"
        "  DATALAB_API_KEY  Datalab Marker key for PDF-to-markdown conversion\n"
        "                   (default: read from ~/.config/datalab/key)\n"
        "\n"
        "examples:\n"
        "  capture https://example.com/post -o ~/notes\n"
        "  capture https://example.com/post -o ~/notes --corpus ~/archive\n"
        "  capture ./paper.pdf --origin https://publisher.example/paper\n"
        "  capture https://arxiv.org/abs/2512.25070 --long-pdf   # 48 pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="page URL, or a local PDF path to ingest")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="re-capture even when the URL already exists at the destination",
    )
    parser.add_argument(
        "--origin",
        help="original URL for provenance and dedup when ingesting a local file",
    )
    parser.add_argument(
        "--url",
        dest="bookmark",
        action="store_true",
        help="bookmark only: fetch just enough to name the folder, then save"
        " a .url shortcut instead of archiving the page",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="destination directory for the capture folder"
        " (default: current directory)",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        help="main archive directory; captures already there are copied to"
        " the destination instead of re-scraped",
    )
    parser.add_argument(
        "--long-pdf",
        action="store_true",
        help="convert a PDF past the 30-page limit (Datalab bills per page)",
    )
    args = parser.parse_args()
    if args.long_pdf:
        from capture.resolvers import pdf

        pdf.LONG_PDF = True
    destination = (args.output or Path.cwd()).resolve()
    lookup = args.origin or args.url
    if not args.force and (duplicate := existing_capture(lookup, destination)):
        print(f"already captured: {duplicate.name}")
        print("pass -f / --force to re-capture")
        return
    try:
        if args.bookmark:
            print(display_path(bookmark(args.url, args.origin, destination)))
        elif folder := corpus_copy(lookup, destination, args.corpus, args.force) or (
            capture(args.url, args.origin, destination)
        ):
            print(display_path(folder))
    except RuntimeError as error:
        sys.exit(f"capture failed: {error}")


def corpus_copy(
    lookup: str, destination: Path, corpus: Path | None, force: bool
) -> Path | None:
    """The capture already in the --corpus archive, copied to the
    destination rather than scraped from the site again."""
    if force or not corpus or corpus.resolve() == destination:
        return None
    if existing := existing_capture(lookup, corpus):
        folder = Path(
            shutil.copytree(existing, destination / existing.name, dirs_exist_ok=True)
        )
        print(f"copied from corpus: {existing.name}")
        return folder
    return None


def display_path(folder: Path) -> str:
    """Relative when the capture landed under the working directory."""
    try:
        return str(folder.relative_to(Path.cwd()))
    except ValueError:
        return str(folder)


if __name__ == "__main__":
    main()
