from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from .models import Media, ThreadPost

API_BASE = "https://graph.threads.net/v1.0"
FIELDS = (
    "id,media_product_type,media_type,media_url,permalink,text,timestamp,shortcode,"
    "is_quote_post,is_reply,children{id,media_type,media_url,thumbnail_url}"
)


class ThreadsAPI:
    def __init__(self, access_token: str, timeout_seconds: int = 30) -> None:
        self._access_token = access_token
        self._timeout_seconds = timeout_seconds

    def get_posts(self, since: datetime, until: datetime) -> list[ThreadPost]:
        params = {
            "fields": FIELDS,
            "since": str(int(since.timestamp())),
            "until": str(int(until.timestamp())),
            "limit": "100",
            "access_token": self._access_token,
        }
        next_url: str | None = f"{API_BASE}/me/threads?{urllib.parse.urlencode(params)}"
        posts: list[ThreadPost] = []
        while next_url:
            payload = self._get_json(next_url)
            posts.extend(self._parse_post(item) for item in payload.get("data", []))
            next_url = payload.get("paging", {}).get("next")
        return sorted(posts, key=lambda post: post.timestamp)

    def _get_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "threads-to-naver/0.1",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds
            ) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(body).get("error", {}).get("message", body)
            except json.JSONDecodeError:
                message = body
            raise RuntimeError(
                f"Threads API returned HTTP {error.code}: {message}"
            ) from error

    @staticmethod
    def _parse_post(raw: dict[str, Any]) -> ThreadPost:
        media_type = str(raw.get("media_type", "TEXT_POST"))
        media: list[Media] = []
        children = raw.get("children", {}).get("data", [])
        if children:
            for item in children:
                url = item.get("media_url")
                if url:
                    media.append(
                        Media(
                            kind=str(item.get("media_type", "IMAGE")),
                            url=str(url),
                            thumbnail_url=item.get("thumbnail_url"),
                        )
                    )
        elif raw.get("media_url"):
            media.append(
                Media(
                    kind=media_type,
                    url=str(raw["media_url"]),
                    thumbnail_url=raw.get("thumbnail_url"),
                )
            )

        timestamp = datetime.fromisoformat(str(raw["timestamp"]))
        repost_types = {"REPOST_FACADE", "REPOST"}
        return ThreadPost(
            id=str(raw["id"]),
            text=str(raw.get("text") or ""),
            timestamp=timestamp,
            permalink=str(raw.get("permalink") or ""),
            media_type=media_type,
            is_reply=bool(raw.get("is_reply", False)),
            is_repost=media_type in repost_types,
            media=tuple(media),
        )
