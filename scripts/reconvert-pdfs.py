#!/usr/bin/env python3
"""Re-run the Datalab conversion on captures whose stored PDF converted badly.

The frontmonth.substack.com batch of 2026-02-05 went through an older
conversion path that extracted no figures and dropped roughly a quarter
of the prose: one 43-raster PDF yielded 0 images and 3532 words where
the current pdf2md gives 21 images and 4605. The PDFs themselves are
intact, so this re-converts from disk — no re-download.

Frontmatter is preserved verbatim, so folder names, dates, and the
`discussions` lists survive; only the body and media/ are replaced.
A capture is skipped when its markdown already references figures,
which makes the run resumable.

Each PDF costs one Datalab call, billed per page. --dry-run reports what
would change and calls nothing; --limit N does a few first.

    scripts/reconvert-pdfs.py /vault/media/sites --dry-run
    scripts/reconvert-pdfs.py /vault/media/sites --limit 1
    scripts/reconvert-pdfs.py /vault/media/sites
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.pipeline import format_markdown  # noqa: E402
from capture.resolvers.pdf import child_env  # noqa: E402

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="report, don't convert")
    parser.add_argument("--limit", type=int, help="stop after this many captures")
    parser.add_argument(
        "--prefix", default="", help="only captures whose folder starts with this"
    )
    args = parser.parse_args()

    candidates = [c for c in sorted(find_candidates(args.corpus, args.prefix))]
    print(f"{len(candidates)} capture(s) with figures to recover")
    for folder, pdf, rasters in candidates:
        print(f"  {rasters:3} large rasters unextracted  {folder.name[:60]}")
    if args.dry_run:
        print("\ndry run: no Datalab calls made, nothing written")
        return
    if args.limit:
        candidates = candidates[: args.limit]
        print(f"\nconverting {len(candidates)} (--limit)")

    print()
    ok = failed = 0
    for folder, pdf, _ in candidates:
        try:
            before, after = reconvert(folder, pdf)
            ok += 1
            print(
                f"  {folder.name[:52]:52} {before['words']:>6}w/{before['figs']}f"
                f" -> {after['words']:>6}w/{after['figs']}f"
            )
        except Exception as failure:  # noqa: BLE001 - report and continue
            failed += 1
            print(f"  FAILED {folder.name[:52]}: {failure}")
    print(f"\n{ok} reconverted, {failed} failed")


def find_candidates(corpus: Path, prefix: str) -> list[tuple[Path, Path, int]]:
    """Captures holding a PDF with real figures that never made it out.

    'Real' means at least 300x200: PDFs are full of 1x1 transparency
    spacers, and vector-drawn figures (most papers) never rasterize at
    all, so counting every raster would flag captures that are fine.
    """
    found = []
    for folder in sorted(corpus.iterdir()):
        if not folder.is_dir() or not folder.name.startswith(prefix):
            continue
        pdf = next((p for p in folder.iterdir() if p.suffix == ".pdf"), None)
        markdown = folder / f"{folder.name}.md"
        if not pdf or not markdown.exists():
            continue
        if re.search(r"!\[[^\]]*\]\(media/", markdown.read_text(errors="replace")):
            continue  # already has figures: converted by the current path
        rasters = big_rasters(pdf)
        if rasters:
            found.append((folder, pdf, rasters))
    return found


def big_rasters(pdf: Path) -> int:
    result = subprocess.run(
        ["pdfimages", "-list", str(pdf)], capture_output=True, text=True
    )
    count = 0
    for line in result.stdout.splitlines()[2:]:
        fields = line.split()
        if len(fields) > 4:
            try:
                if int(fields[3]) >= 300 and int(fields[4]) >= 200:
                    count += 1
            except ValueError:
                pass
    return count


def reconvert(folder: Path, pdf: Path) -> tuple[dict, dict]:
    markdown = folder / f"{folder.name}.md"
    text = markdown.read_text(errors="replace")
    front, _, body = text.partition("\n---\n")
    if not body:
        raise RuntimeError("no frontmatter fence")
    before = {"words": len(body.split()), "figs": count_media(folder)}

    out = Path(tempfile.mkdtemp())
    try:
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "capture.pdf2md",
                "-o",
                str(out),
                "--media-dir",
                "media",
                str(pdf),
            ],
            capture_output=True,
            text=True,
            env=child_env(),
        )
        produced = out / f"{pdf.stem}.md"
        if run.returncode != 0 or not produced.exists():
            raise RuntimeError(f"pdf2md failed: {run.stderr.strip()[:160]}")
        converted = produced.read_text()
        # Same rewrite the resolver applies: pdf2md emits bare filenames.
        converted = re.sub(
            r"(!\[[^\]]*\]\()(?!https?://|media/)([^)\s]+)", r"\1media/\2", converted
        )
        media = folder / "media"
        for image in (out / "media").iterdir() if (out / "media").is_dir() else []:
            if image.suffix.lower() in IMAGE_SUFFIXES:
                media.mkdir(exist_ok=True)
                shutil.move(str(image), media / image.name)
        markdown.write_text(f"{front}\n---\n\n{converted.lstrip()}")
        format_markdown(markdown)
    finally:
        shutil.rmtree(out, ignore_errors=True)
    return before, {
        "words": len(markdown.read_text().split()),
        "figs": count_media(folder),
    }


def count_media(folder: Path) -> int:
    media = folder / "media"
    return len(list(media.iterdir())) if media.is_dir() else 0


if __name__ == "__main__":
    main()
