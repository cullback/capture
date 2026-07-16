"""End-to-end smoke test against a real page.

Slow and network-dependent, so excluded by default; run with
`pytest -m live`.
"""

import pytest

from capture.pipeline import capture

pytestmark = pytest.mark.live


def test_capture_end_to_end():
    folder = capture("https://bernsteinbear.com/blog/toy-fuzzer/")
    assert folder is not None
    assert (
        folder.name == "bernsteinbear.com - 2026-02-25 - a-fuzzer-for-the-toy-optimizer"
    )
    html = folder / f"{folder.name}.html"
    markdown = folder / f"{folder.name}.md"
    assert html.stat().st_size > 10_000
    text = markdown.read_text()
    assert text.startswith("---\n")
    for key in ["title:", "domain:", "url:", "capture_date:", "publish_date:"]:
        assert key in text.split("---")[1]
    assert len(text.split()) > 500
