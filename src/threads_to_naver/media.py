from __future__ import annotations

import mimetypes
import urllib.request
from pathlib import Path

from .models import Media, ThreadPost


def download_media(post: ThreadPost, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for index, item in enumerate(post.media, start=1):
        url = _media_download_url(item)
        request = urllib.request.Request(
            url, headers={"User-Agent": "threads-to-naver/0.1"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            content_type = response.headers.get_content_type()
            suffix = mimetypes.guess_extension(content_type) or _suffix_from_kind(
                item.kind
            )
            path = destination / f"{post.id}-{index}{suffix}"
            path.write_bytes(response.read())
            downloaded.append(path)
    return downloaded


def _media_download_url(item: Media) -> str:
    if item.kind.upper() in {"VIDEO", "REELS"} and item.url:
        return item.url
    return item.url or item.thumbnail_url or ""


def _suffix_from_kind(kind: str) -> str:
    return ".mp4" if kind.upper() in {"VIDEO", "REELS"} else ".jpg"
