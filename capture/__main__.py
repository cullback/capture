"""CLI entry point: capture a web page into data/."""

import argparse
import sys

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
        help="re-capture even when the URL already exists in data/",
    )
    parser.add_argument(
        "--origin",
        help="original URL for provenance and dedup when ingesting a local file",
    )
    args = parser.parse_args()
    if not args.force and (duplicate := existing_capture(args.origin or args.url)):
        print(f"already captured: {duplicate.name}")
        print("pass -f / --force to re-capture")
        return
    try:
        if folder := capture(args.url, args.origin):
            print(f"data/{folder.name}")
    except RuntimeError as error:
        sys.exit(f"capture failed: {error}")


if __name__ == "__main__":
    main()
