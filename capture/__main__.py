"""CLI entry point: capture a web page into a destination folder."""

import argparse
import os
import shutil
import sys
from pathlib import Path

from capture.pipeline import capture, existing_capture


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="capture",
        description="Save a page as a faithful HTML archive plus clean markdown.",
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
        "-o",
        "--output",
        type=Path,
        help="destination directory for the capture folder"
        " (default: current directory)",
    )
    args = parser.parse_args()
    destination = (args.output or Path.cwd()).resolve()
    lookup = args.origin or args.url
    if not args.force and (duplicate := existing_capture(lookup, destination)):
        print(f"already captured: {duplicate.name}")
        print("pass -f / --force to re-capture")
        return
    try:
        if folder := corpus_copy(lookup, destination, args.force) or capture(
            args.url, args.origin, destination
        ):
            print(display_path(folder))
    except RuntimeError as error:
        sys.exit(f"capture failed: {error}")


def corpus_copy(lookup: str, destination: Path, force: bool) -> Path | None:
    """The capture already in the CAPTURE_CORPUS archive, copied to the
    destination rather than scraped from the site again."""
    corpus = os.environ.get("CAPTURE_CORPUS")
    if force or not corpus or Path(corpus).resolve() == destination:
        return None
    if existing := existing_capture(lookup, Path(corpus)):
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
