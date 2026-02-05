"""Markdown utility functions for capture pipeline."""

import re
import unicodedata
from datetime import date

import yaml


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe ASCII slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def strip_frontmatter(markdown: str) -> tuple[dict, str]:
    """Remove YAML frontmatter and return (frontmatter_dict, content)."""
    if not markdown.startswith("---"):
        return {}, markdown

    parts = markdown.split("---", 2)
    if len(parts) < 3:
        return {}, markdown

    frontmatter = yaml.safe_load(parts[1]) or {}
    content = parts[2].lstrip("\n")
    return frontmatter, content


def add_frontmatter(
    markdown: str,
    metadata: dict,
    domain: str,
    url: str,
    capture_date: str | None = None,
    hackernews: str | None = None,
) -> str:
    """Add YAML frontmatter to markdown."""
    lines = [
        "---",
        f'title: "{metadata["title"]}"',
        f"domain: {domain}",
        f"url: {url}",
    ]
    if hackernews:
        lines.append(f"hackernews: {hackernews}")
    lines.append(f"capture_date: {capture_date or date.today()}")
    if metadata.get("publish_date"):
        lines.append(f"publish_date: {metadata['publish_date']}")
    if metadata.get("tags"):
        lines.append("tags:")
        for tag in metadata["tags"]:
            lines.append(f"  - {tag}")
    lines.append("---")
    lines.append("")

    return "\n".join(lines) + markdown
