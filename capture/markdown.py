"""Markdown utility functions for capture pipeline."""

import re
import unicodedata

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
