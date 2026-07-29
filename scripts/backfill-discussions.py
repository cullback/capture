#!/usr/bin/env python3
"""Add the `discussions` frontmatter key to captures made before it existed.

One-off migration. Reads each capture's `url`, searches Hacker News and
Reddit for threads about it, and rewrites the frontmatter — replacing
the older single `hackernews:` key, which held one thread where there
were often several across both sites.

Idempotent and resumable: a capture that already carries `discussions:`
is skipped, so an interrupted run continues where it stopped. Pass
--force to re-query those too, and --dry-run to see the changes without
writing.

    scripts/backfill-discussions.py /vault/media/sites
    scripts/backfill-discussions.py /vault/media/sites --dry-run --limit 20
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.discussions import discussions  # noqa: E402
from capture.pipeline import discussion_lines  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="directory of capture folders")
    parser.add_argument("--dry-run", action="store_true", help="report, don't write")
    parser.add_argument(
        "--force", action="store_true", help="re-query captures already backfilled"
    )
    parser.add_argument("--limit", type=int, help="stop after this many captures")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="parallel lookups (default 4; Arctic Shift is volunteer-run,"
        " so this stays low deliberately)",
    )
    args = parser.parse_args()

    pending = [
        markdown
        for markdown in sorted(args.corpus.glob("*/*.md"))
        if args.force or "\ndiscussions:" not in frontmatter_of(markdown)
    ]
    total = len(pending)
    if args.limit:
        pending = pending[: args.limit]
    print(f"{total} capture(s) to backfill; running {len(pending)}")

    started = time.monotonic()
    counts = {"found": 0, "empty": 0, "skipped": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = pool.map(lambda m: (m, backfill(m, args.dry_run)), pending)
        for done, (markdown, outcome) in enumerate(results, 1):
            counts[outcome] += 1
            if outcome == "found" or done % 25 == 0:
                elapsed = time.monotonic() - started
                rate = done / elapsed if elapsed else 0
                left = (len(pending) - done) / rate if rate else 0
                print(
                    f"  [{done}/{len(pending)}] {outcome:8}"
                    f" {markdown.parent.name[:58]:58}"
                    f" ~{left / 60:.1f}m left"
                )

    elapsed = time.monotonic() - started
    print(
        f"\n{counts['found']} with discussions, {counts['empty']} without,"
        f" {counts['skipped']} skipped (no url) in {elapsed / 60:.1f}m"
    )
    if args.dry_run:
        print("dry run: nothing written")


def frontmatter_of(markdown: Path) -> str:
    head = markdown.read_text(errors="replace")[:4000]
    if not head.startswith("---\n"):
        return ""
    end = head.find("\n---\n", 3)
    return head[: end + 5] if end != -1 else ""


def _value(front: str, key: str) -> str:
    for line in front.splitlines():
        if line.startswith(key):
            return line[len(key) :].strip()
    return ""


def backfill(markdown: Path, dry_run: bool) -> str:
    text = markdown.read_text(errors="replace")
    front = frontmatter_of(markdown)
    url = _value(front, "url: ")
    if not url:
        # Local PDF ingests without --origin have no URL to search on.
        return "skipped"
    # Hacker News and Reddit only. Lobsters is searched by title, and
    # passing one here would mean a search per capture: it starts
    # answering 429 after a few dozen, and a corpus-wide sweep of a
    # small volunteer-run site is not a reasonable thing to do to it.
    # New captures pick lobsters up one query at a time.
    found = discussions(url)
    body = text[len(front) :]
    markdown_text = rewrite(front, found) + body
    if not dry_run:
        markdown.write_text(markdown_text)
    return "found" if found else "empty"


def rewrite(front: str, found: list[str]) -> str:
    """Frontmatter with `discussions` in the slot `hackernews` held, so
    a backfilled capture matches one written fresh by the pipeline."""
    out, placed, in_old_list = [], False, False
    for line in front.splitlines():
        # Drop what this key replaces: the single `hackernews`, and any
        # `discussions` block from an earlier run (--force re-queries).
        if line.startswith("discussions:"):
            in_old_list = True
            continue
        if in_old_list and line.startswith("  - "):
            continue
        in_old_list = False
        if line.startswith("hackernews:"):
            continue
        # The pipeline writes discussions last, before capture_date.
        if line.startswith("capture_date:") and not placed:
            out.extend(discussion_lines(found))
            placed = True
        out.append(line)
    if not placed:
        # No capture_date: fall back to just inside the closing fence.
        out = out[:-1] + discussion_lines(found) + out[-1:]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
