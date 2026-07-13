"""CLI entry point: capture a web page into data/."""

import argparse

from capture.pipeline import capture, existing_capture


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="capture",
        description="Save a page as a faithful HTML archive plus clean markdown.",
    )
    parser.add_argument("url", help="page to capture")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="re-capture even when the URL already exists in data/",
    )
    args = parser.parse_args()
    if not args.force and (duplicate := existing_capture(args.url)):
        print(f"already captured: {duplicate.name}")
        print("pass -f / --force to re-capture")
        return
    print(capture(args.url))


if __name__ == "__main__":
    main()
