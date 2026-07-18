"""Direct PDF URLs: the PDF is the canonical artifact.

Metadata comes from pdfinfo; markdown comes from marker (layout-aware
PDF conversion) when it's installed and succeeds, and is omitted
otherwise — a PDF-only capture is still honest.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from capture.resolvers.base import Resolution
from capture.resolvers.github import markdown_heading


def resolve_pdf(url: str) -> Resolution | None:
    if not urlparse(url).path.lower().endswith(".pdf"):
        return None
    holder = tempfile.mkdtemp()
    pdf = Path(holder) / "capture.pdf"
    fetch = subprocess.run(
        ["curl", "-sL", "--max-time", "300", "-A", "capture/0.1", url, "-o", str(pdf)],
        capture_output=True,
    )
    if fetch.returncode != 0 or pdf.read_bytes()[:5] != b"%PDF-":
        return None  # not actually a PDF; let other resolvers try
    info = pdf_info(pdf)
    stem = unquote(Path(urlparse(url).path).stem)
    text, images = marker_markdown(pdf)
    if text:
        # Marker references its extracted figures by bare filename.
        text = re.sub(
            r"(!\[[^\]]*\]\()(?!https?://|media/)([^)\s]+)", r"\1media/\2", text
        )
    return Resolution(
        source=url,
        content=url,
        use_browser=False,
        publish=info.get("date"),
        markdown=text,
        skip_markdown=text is None,
        # The converted document's own heading beats PDF metadata, which
        # often carries the LaTeX source filename.
        title=(text and markdown_heading(text))
        or info.get("title")
        or stem.replace("_", " ").replace("-", " "),
        extra={"author": info.get("author", "")},
        download_media=lambda folder, name: move_artifacts(pdf, images, folder, name),
    )


def move_artifacts(pdf: Path, images: Path | None, folder: Path, name: str) -> None:
    shutil.move(str(pdf), folder / f"{name}.pdf")
    shutil.rmtree(pdf.parent, ignore_errors=True)
    if images and images.is_dir():
        media = folder / "media"
        for file in images.iterdir():
            if file.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                media.mkdir(exist_ok=True)
                shutil.move(str(file), media / file.name)
        shutil.rmtree(images.parent, ignore_errors=True)


def pdf_info(pdf: Path) -> dict:
    result = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip().lower()] = value.strip()
    info = {}
    if title := fields.get("title"):
        info["title"] = title
    if author := fields.get("author"):
        info["author"] = author
    # CreationDate like "Wed Jan  5 12:00:00 2011"
    if match := re.search(
        r"([A-Za-z]{3}) +(\d{1,2}) [\d:]+ [A-Z]* ?(\d{4})",
        fields.get("creationdate", ""),
    ):
        from capture.extract import body_date

        info["date"] = body_date(f"{match.group(1)} {match.group(2)}, {match.group(3)}")
    return info


def marker_markdown(pdf: Path) -> tuple[str | None, Path | None]:
    """Layout-aware conversion when marker is installed; (None, None)
    otherwise (pdftotext scrambles multi-column reading order, so no
    cheap fallback). Returns the markdown and its figure directory."""
    if not shutil.which("marker_single"):
        return None, None
    out = Path(tempfile.mkdtemp())
    result = subprocess.run(
        [
            "marker_single",
            str(pdf),
            "--output_format",
            "markdown",
            "--output_dir",
            str(out),
            "--disable_multiprocessing",
        ],
        capture_output=True,
        text=True,
    )
    produced = sorted(out.rglob("*.md"))
    if result.returncode != 0 or not produced:
        print(f"marker failed: {result.stderr.strip()[:200]}")
        shutil.rmtree(out, ignore_errors=True)
        return None, None
    return produced[0].read_text(), produced[0].parent
