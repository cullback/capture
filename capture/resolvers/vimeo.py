"""Vimeo videos: archival mkv + info.json via yt-dlp, no markdown."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

from capture.extract import slugify
from capture.resolvers import base
from capture.resolvers.base import Resolution

# Netscape-format cookies, for private or password-protected videos.
VIMEO_COOKIES = Path.home() / ".config" / "capture" / "vimeo-cookies.txt"

# Canonical pages, channel/group/album routes, and embed player URLs.
# Anchored to the host so a wayback snapshot of a vimeo page stays with
# the wayback resolver.
VIMEO_URL = re.compile(
    r"https?://(?:www\.|player\.)?vimeo\.com/"
    r"(?:video/|channels/[\w-]+/|groups/[\w-]+/videos/|album/\d+/video/)?"
    r"(?P<id>\d+)(?:/(?P<hash>\w+))?"
)


def resolve_vimeo(url: str) -> Resolution | None:
    """Video captures are mkv + info.json (the yt-dlp standard), no
    markdown: the info.json carries all metadata and the transcript
    lives in the mkv's embedded subtitles. The same shape youtube
    captures take."""
    player = vimeo_player(url)
    if not player:
        return None
    probe = yt_dlp(["--dump-json", "--skip-download", player])
    if probe.returncode != 0:
        error = probe.stderr.strip()[:300]
        if "401" in error:
            # The uploader restricted off-site embedding, so the player
            # refuses the video to everyone. Referer and app_id do not
            # move it; only an authorized account might.
            raise RuntimeError(
                f"vimeo refuses to embed {player}: the video is embed-restricted. "
                f"Cookies at {VIMEO_COOKIES} may reach it if the account can."
            )
        raise RuntimeError(f"yt-dlp failed for {player}: {error}")
    meta = json.loads(probe.stdout)
    oembed = vimeo_oembed(url)
    # "vimeo.com - <uploader>" as the leading folder segments: sorts
    # under the vimeo.com type prefix, then groups by uploader. The
    # display name ("conner-omalley") reads better than the account id
    # ("user11107993"), which is all a basic account without a vanity
    # URL identifies itself as. A rename splits an uploader's folders,
    # which is the accepted price of legibility.
    user = slugify(oembed.get("author_name") or "") or slugify(
        meta.get("uploader_id") or ""
    )
    return Resolution(
        source=f"https://vimeo.com/{vimeo_id(url)}",
        content=player,
        domain=f"vimeo.com - {user}" if user else None,
        use_browser=False,
        publish=vimeo_upload_date(oembed),
        skip_markdown=True,
        title=meta.get("title"),
        download_media=lambda folder, name: vimeo_download(player, folder, name),
    )


def vimeo_id(url: str) -> str | None:
    """The numeric video id, from any recognized vimeo URL form."""
    match = VIMEO_URL.match(url)
    return match.group("id") if match else None


def vimeo_player(url: str) -> str | None:
    """The embed player URL to download from, or None for non-vimeo URLs.

    yt-dlp reaches vimeo.com/<id> through an OAuth endpoint that
    currently answers 401, while the embed player needs no auth.
    Unlisted videos carry a link hash the player takes as ?h= and
    refuses the video without — spelled as a trailing path segment on
    a shared link, as a query parameter on an embed URL.
    """
    match = VIMEO_URL.match(url)
    if not match:
        return None
    query = re.search(r"[?&]h=(\w+)", url)
    link_hash = match.group("hash") or (query.group(1) if query else None)
    player = f"https://player.vimeo.com/video/{match.group('id')}"
    return f"{player}?h={link_hash}" if link_hash else player


def vimeo_oembed(url: str) -> dict:
    """Vimeo's oEmbed record for a video, or {} when it serves none.

    The download goes through player.vimeo.com, which serves neither an
    upload timestamp nor a readable uploader name — the two things the
    folder name is built from. oEmbed carries both, is public, needs no
    key, and takes the shared URL verbatim, hash and all.
    """
    endpoint = "https://vimeo.com/api/oembed.json?url=" + quote(url, safe="")
    try:
        return json.loads(base.fetch_html(endpoint))
    except base.FetchError:
        # Private, deleted, or region-blocked: no metadata beats wrong.
        return {}


def vimeo_upload_date(oembed: dict) -> str | None:
    """The upload day from an oEmbed record, which dates a video to the
    second ("2022-05-30 11:07:24") where the folder wants a day."""
    upload = (oembed.get("upload_date") or "")[:10]
    return upload if re.fullmatch(r"\d{4}-\d{2}-\d{2}", upload) else None


def yt_dlp(args: list[str]) -> subprocess.CompletedProcess:
    command = ["yt-dlp", "--no-warnings"]
    if VIMEO_COOKIES.exists():
        command += ["--cookies", str(VIMEO_COOKIES)]
    return subprocess.run(command + args, capture_output=True, text=True)


def vimeo_download(player: str, folder: Path, name: str) -> None:
    """Max-quality archival download: one mkv with thumbnail, metadata,
    chapters, subtitles, and the info-json all embedded. No auto-subs
    or sponsorblock — both are youtube-only."""
    result = yt_dlp(
        [
            "-f",
            "bestvideo*+bestaudio/best",
            "--merge-output-format",
            "mkv",
            # Also remux single-format downloads: info-json and other
            # attachments only embed into mkv.
            "--remux-video",
            "mkv",
            "--embed-thumbnail",
            "--embed-metadata",
            "--embed-chapters",
            "--embed-subs",
            "--embed-info-json",
            "--write-info-json",
            "-o",
            str(folder / f"{name}.%(ext)s"),
            player,
        ]
    )
    if result.returncode != 0:
        print(f"video download failed: {result.stderr.strip()[:300]}")
    # Subtitle files were only needed for embedding.
    for stray in folder.glob(f"{name}*.vtt"):
        stray.unlink()
    for stray in folder.glob(f"{name}*.srt"):
        stray.unlink()
