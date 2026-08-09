"""Pastebin pastes via the raw endpoint.

A paste is one file, so it captures like a GitHub blob: the raw text is
the body — verbatim when it is markdown, a fenced code block otherwise —
and the browser still archives the rendered page. The raw endpoint has
no metadata at all, so the page is fetched for its fields: title,
author, date, and the declared syntax format.
"""

import re

from capture.resolvers import base
from capture.resolvers.base import Resolution
from capture.resolvers.github import fenced

# Site routes whose first path segment is shaped like an 8-char key.
RESERVED = ("trending", "settings", "messages")

MONTHS = {
    month: number
    for number, month in enumerate(
        "January February March April May June July "
        "August September October November December".split(),
        1,
    )
}


def resolve_pastebin(url: str) -> Resolution | None:
    key = pastebin_key(url)
    if not key:
        return None
    source = f"https://pastebin.com/{key}"
    page = base.fetch_html(source)
    raw = base.fetch_html(f"https://pastebin.com/raw/{key}")
    title = pastebin_title(page)
    fmt = pastebin_format(page)
    # The author's declaration decides what the text is: the markdown
    # format, or a title that names a markdown file. Everything else is
    # code, fenced under its declared language ("text" has none).
    if fmt == "markdown" or title.lower().endswith((".md", ".markdown")):
        markdown = raw if raw.endswith("\n") else raw + "\n"
    else:
        markdown = fenced(raw, "" if fmt == "text" else fmt)
    user = pastebin_user(page)
    return Resolution(
        source=source,
        content=source,
        domain=f"pastebin.com - {user}" if user else "pastebin.com",
        html=page,
        publish=pastebin_date(page),
        markdown=markdown,
        title=title or key,
    )


def pastebin_key(url: str) -> str | None:
    """The 8-character paste key, from the canonical page URL or the
    raw/dl/embed/print/clone variants. Anchored to the pastebin host so
    a wayback snapshot of a paste stays with the wayback resolver."""
    match = re.match(
        r"https?://(?:www\.)?pastebin\.com"
        r"/(?:(?:raw|dl|embed|print|clone)/)?([A-Za-z0-9]{8})(?:[?#]|$)",
        url,
    )
    if not match or match.group(1) in RESERVED:
        return None
    return match.group(1)


def pastebin_title(page: str) -> str:
    """The paste's own title: the h1 of the info block. The <title> tag
    would do, but it appends the site name."""
    match = re.search(r'class="info-top".*?<h1>([^<]*)</h1>', page, re.S)
    return match.group(1).strip() if match else ""


def pastebin_user(page: str) -> str | None:
    """The paste's author, absent for guest pastes (whose username
    block holds bare text, not a profile link)."""
    match = re.search(r'class="username">\s*<a href="/u/([^"/]+)"', page, re.S)
    return match.group(1) if match else None


def pastebin_date(page: str) -> str | None:
    """The paste date, from the full timestamp the date span carries in
    its tooltip ("Tuesday 4th of November 2025 11:21:02 PM CDT") — the
    visible text is an abbreviation."""
    match = re.search(
        r'class="date">\s*<span title="\w+ (\d{1,2})\w{2} of (\w+) (\d{4})',
        page,
        re.S,
    )
    if not match:
        return None
    day, month, year = match.groups()
    if month not in MONTHS:
        return None
    return f"{year}-{MONTHS[month]:02d}-{int(day):02d}"


def pastebin_format(page: str) -> str:
    """The declared syntax format, read from the archive link the page
    labels itself with (href="/archive/python")."""
    match = re.search(r'href="/archive/([\w+-]+)"', page)
    return match.group(1).lower() if match else "text"
