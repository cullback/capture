"""Golden regression tests over the real captured corpus.

Every capture folder in data/ doubles as a frozen real-page fixture:
this test recomputes title and date extraction from the stored HTML
artifact and compares against the committed golden file. Unlike the
unit tests (minimal reproductions of known lessons), this catches
regressions on real-page HTML the unit tests have never seen.

When extraction behavior changes intentionally, regenerate with

    UPDATE_GOLDEN=1 pytest tests/test_corpus.py

and review the golden diff in git: every changed line is a page whose
extraction changed, and the diff must justify itself page by page.

Captures made on other machines (data/ is gitignored) are skipped, so
the test degrades gracefully to whatever corpus is present.
"""

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from capture.extract import page_title, published_date

GOLDEN = Path(__file__).parent / "corpus-golden.jsonl"
DATA = Path(__file__).parent.parent / "data"


def extract(folder: Path) -> dict | None:
    markdown = folder / f"{folder.name}.md"
    artifact = folder / f"{folder.name}.html"
    if not (markdown.exists() and artifact.exists()):
        return None  # media captures have no markdown/html pair
    header = markdown.read_text(errors="replace")[:700]
    url = next(
        (
            line.split(": ", 1)[1]
            for line in header.splitlines()
            if line.startswith("url: ")
        ),
        "",
    )
    html = artifact.read_text(errors="replace")
    domain = urlparse(url).netloc.removeprefix("www.")
    return {
        "folder": folder.name,
        "title": page_title(html, domain, url),
        "publish": published_date(url, html),
    }


def regenerate() -> list[dict]:
    rows = []
    for folder in sorted(DATA.iterdir()):
        if folder.is_dir() and (row := extract(folder)):
            rows.append(row)
    GOLDEN.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return rows


if os.environ.get("UPDATE_GOLDEN"):
    regenerate()


def golden_rows() -> list[dict]:
    if not GOLDEN.exists():
        return []
    return [json.loads(line) for line in GOLDEN.read_text().splitlines()]


@pytest.mark.parametrize("row", golden_rows(), ids=lambda r: r["folder"][:60])
def test_corpus_extraction(row):
    folder = DATA / row["folder"]
    if not folder.is_dir():
        pytest.skip("capture not present on this machine")
    assert extract(folder) == row
