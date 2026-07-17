"""arxiv papers: HTML rendering for content, abs page for identity."""

import re
import subprocess

from capture.extract import body_date
from capture.resolvers import base
from capture.resolvers.base import Resolution


def resolve_arxiv(url: str) -> Resolution | None:
    """Identity from the abs page; content from the HTML rendering,
    which is generated from the LaTeX source so math survives."""
    aid = arxiv_id(url)
    if not aid:
        return None
    source = f"https://arxiv.org/abs/{aid}"
    html = base.fetch_html(source)
    return Resolution(
        source=source,
        content=arxiv_content_url(aid),
        html=html,
        publish=arxiv_published(html),
        pdf_url=f"https://arxiv.org/pdf/{aid}",
    )


def arxiv_id(url: str) -> str | None:
    match = re.search(
        r"(?:ar5iv\.labs\.arxiv|arxiv)\.org/(?:abs|pdf|html|e-print)/(\d{4}\.\d{4,5})",
        url,
    )
    return match.group(1) if match else None


def arxiv_content_url(aid: str) -> str:
    """The paper's HTML rendering: official when it exists, else ar5iv."""
    official = f"https://arxiv.org/html/{aid}"
    status = subprocess.run(
        ["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}", official],
        capture_output=True,
        text=True,
    ).stdout
    return official if status == "200" else f"https://ar5iv.labs.arxiv.org/html/{aid}"


def arxiv_published(html: str) -> str | None:
    """The v1 submission date from an abs page ("Submitted on 27 Mar 2026")."""
    if match := re.search(r"Submitted on (\d{1,2} [A-Za-z]{3,9},? \d{4})", html):
        return body_date(match.group(1))
    return None
