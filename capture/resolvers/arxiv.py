"""arxiv papers: PDF for content and artifact, abs page for identity."""

import re
import subprocess
import tempfile
from pathlib import Path

from capture.extract import body_date
from capture.resolvers import base
from capture.resolvers.base import Resolution
from capture.resolvers.pdf import move_artifacts, pdf_markdown


def resolve_arxiv(url: str) -> Resolution | None:
    """Identity from the abs page; markdown from datalab conversion of
    the typeset PDF (cleaner than the LaTeXML HTML, which carries page
    chrome and equation-table artifacts)."""
    aid = arxiv_id(url)
    if not aid:
        return None
    source = f"https://arxiv.org/abs/{aid}"
    html = base.fetch_html(source)
    pdf = Path(tempfile.mkdtemp()) / "capture.pdf"
    subprocess.run(
        [
            "curl",
            "-sL",
            "--max-time",
            "300",
            "-A",
            "capture/0.1",
            "-o",
            str(pdf),
            f"https://arxiv.org/pdf/{aid}",
        ],
        capture_output=True,
    )
    if not pdf.exists() or pdf.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError(f"could not download the PDF for {source}")
    text, images = pdf_markdown(pdf)
    text = re.sub(r"(!\[[^\]]*\]\()(?!https?://|media/)([^)\s]+)", r"\1media/\2", text)
    return Resolution(
        source=source,
        content=source,
        html=html,
        # The typeset PDF is the canonical artifact; conversions only
        # feed the markdown.
        save_html=False,
        publish=arxiv_published(html),
        markdown=text,
        download_media=lambda folder, name: move_artifacts(pdf, images, folder, name),
    )


def arxiv_id(url: str) -> str | None:
    match = re.search(
        r"(?:ar5iv\.labs\.arxiv|arxiv)\.org/(?:abs|pdf|html|e-print)/(\d{4}\.\d{4,5})",
        url,
    )
    return match.group(1) if match else None


def arxiv_published(html: str) -> str | None:
    """The v1 submission date from an abs page ("Submitted on 27 Mar 2026")."""
    if match := re.search(r"Submitted on (\d{1,2} [A-Za-z]{3,9},? \d{4})", html):
        return body_date(match.group(1))
    return None
