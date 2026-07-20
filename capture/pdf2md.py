"""Convert PDFs to markdown via the Datalab Marker API.

Usage: pdf2md [-o DIR] [--name STEM] [--media-dir NAME]
              [--mode fast|balanced|accurate] [--override]
              <file.pdf> [more.pdf ...]

Writes <stem>.md (plus a media directory when the document has
figures) into the output directory, printing each markdown path to
stdout. Refuses PDFs over 30 pages unless --override (or
PDF2MD_OVERRIDE=1, for callers like the capture pipeline), since
Datalab bills per page. Requires DATALAB_API_KEY in the environment
or ~/.config/datalab/key. Stdlib only; curl does the HTTP.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SUBMIT_URL = "https://www.datalab.to/api/v1/marker"
POLL_SECONDS = 10
TIMEOUT_MINUTES = 30
PAGE_LIMIT = 30


def api_key() -> str:
    if key := os.environ.get("DATALAB_API_KEY"):
        return key
    keyfile = Path.home() / ".config" / "datalab" / "key"
    if keyfile.exists():
        return keyfile.read_text().strip()
    sys.exit("DATALAB_API_KEY not set (env var or ~/.config/datalab/key)")


def curl_json(args: list[str], key: str) -> dict:
    result = subprocess.run(
        ["curl", "-s", "--fail-with-body", "-H", f"X-Api-Key: {key}", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"datalab request failed: {result.stdout[:300]}")
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF to markdown via Datalab Marker")
    parser.add_argument("pdfs", type=Path, nargs="+", metavar="pdf")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("."))
    parser.add_argument("--name", help="output stem (default: the pdf's)")
    parser.add_argument("--media-dir", default="images", help="figure dir name")
    parser.add_argument(
        "--mode",
        choices=("fast", "balanced", "accurate"),
        default="accurate",
        help="datalab conversion tier",
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help=f"convert past the {PAGE_LIMIT}-page limit (billed per page)",
    )
    args = parser.parse_args()
    if args.name and len(args.pdfs) > 1:
        parser.error("--name only makes sense with a single pdf")
    key = api_key()
    for pdf in args.pdfs:
        convert(pdf, args, key)


def page_count(pdf: Path) -> int:
    """Best-effort count from the raw bytes: the page tree's /Count when
    visible, else counted page objects. Both can hide inside compressed
    object streams, where this returns 0 (treated as unknown)."""
    data = pdf.read_bytes()
    counts = [int(c) for c in re.findall(rb"/Count\s+(\d+)", data)]
    pages = len(re.findall(rb"/Type\s*/Page\b(?!s)", data))
    return max(counts + [pages], default=0)


def convert(pdf: Path, args: argparse.Namespace, key: str) -> None:
    if not args.override and not os.environ.get("PDF2MD_OVERRIDE"):
        pages = page_count(pdf)
        if pages > PAGE_LIMIT:
            sys.exit(
                f"{pdf.name}: ~{pages} pages exceeds the {PAGE_LIMIT}-page limit"
                " (Datalab bills per page); pass --override to convert anyway"
            )
        if pages == 0:
            print(f"{pdf.name}: page count unknown, proceeding", file=sys.stderr)
    output_dir = args.output_dir
    submitted = curl_json(
        [
            "-F",
            f"file=@{pdf};type=application/pdf",
            "-F",
            "output_format=markdown",
            "-F",
            f"mode={args.mode}",
            SUBMIT_URL,
        ],
        key,
    )
    check_url = submitted.get("request_check_url") or sys.exit(
        f"unexpected submit response: {submitted}"
    )

    print(f"{pdf.name}: submitted, polling every {POLL_SECONDS}s...", file=sys.stderr)
    poll: dict = {}
    for _ in range(TIMEOUT_MINUTES * 60 // POLL_SECONDS):
        time.sleep(POLL_SECONDS)
        poll = curl_json([check_url], key)
        if poll.get("status") == "complete":
            break
    else:
        sys.exit("conversion timed out")
    if poll.get("success") is False or not poll.get("markdown"):
        sys.exit(f"conversion failed: {poll.get('error') or poll.get('status')}")

    markdown = poll["markdown"]
    output_dir.mkdir(parents=True, exist_ok=True)
    images = poll.get("images") or {}
    if images:
        image_dir = output_dir / args.media_dir
        image_dir.mkdir(exist_ok=True)
        for name, encoded in images.items():
            (image_dir / Path(name).name).write_bytes(base64.b64decode(encoded))
            markdown = markdown.replace(
                f"]({name})", f"]({args.media_dir}/{Path(name).name})"
            )
            markdown = markdown.replace(
                f'src="{name}"', f'src="{args.media_dir}/{Path(name).name}"'
            )

    out = output_dir / f"{args.name or pdf.stem}.md"
    out.write_text(markdown)
    # Best-effort formatting; unformatted markdown is still markdown.
    formatted = subprocess.run(
        [
            "dprint",
            "fmt",
            "--config",
            str(Path(__file__).parent / "markdown-fmt.json"),
            "--stdin",
            "md",
        ],
        input=out.read_text(),
        capture_output=True,
        text=True,
    )
    if formatted.returncode == 0 and formatted.stdout:
        out.write_text(formatted.stdout)
    print(out)


if __name__ == "__main__":
    main()
