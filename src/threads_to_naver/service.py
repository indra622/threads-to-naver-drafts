from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from .config import Config
from .media import download_media
from .naver import NaverDraftWriter
from .secrets import (
    get_threads_token,
    get_threads_token_saved_at,
    save_threads_token,
)
from .state import StateStore
from .threads_api import ThreadsAPI


def run(
    config: Config,
    target_date: date,
    dry_run: bool = False,
    latest_only: bool = False,
) -> int:
    config.ensure_directories()
    if latest_only:
        end = datetime.now(config.timezone) - timedelta(seconds=5)
        start = end - timedelta(days=30)
    else:
        start = datetime.combine(target_date, time.min, config.timezone)
        end = start + timedelta(days=1)
    token = get_threads_token()
    api = ThreadsAPI(token)
    posts = api.get_posts(start, end)
    _refresh_token_if_due(api, token)
    posts = [
        post
        for post in posts
        if (config.include_replies or not post.is_reply)
        and (config.include_reposts or not post.is_repost)
    ]
    posts = posts[-1:] if latest_only else posts[: config.max_posts_per_run]

    with StateStore(config.state_db) as state:
        pending = [post for post in posts if not state.contains(post.id)]
        if dry_run:
            _write_dry_run(config, target_date, pending)
            print(f"Dry run: {len(pending)} pending post(s); no Naver browser opened.")
            return len(pending)

        if not pending:
            print("No new Threads posts to draft.")
            return 0

        created = 0
        with NaverDraftWriter(config) as writer:
            for post in pending:
                media_dir = config.artifacts_dir / "media" / post.id
                media_paths = download_media(post, media_dir) if post.media else []
                writer.create_draft(post, media_paths)
                state.mark_drafted(post.id, post.permalink, post.timestamp, post.title)
                created += 1
                print(f"Drafted Threads post {post.id}: {post.title}")
        return created


def _write_dry_run(config: Config, target_date: date, posts: list) -> Path:
    path = config.artifacts_dir / f"dry-run-{target_date.isoformat()}.json"
    payload = [
        {
            "id": post.id,
            "title": post.title,
            "text": post.text,
            "timestamp": post.timestamp.isoformat(),
            "permalink": post.permalink,
            "media": [media.url for media in post.media],
        }
        for post in posts
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _refresh_token_if_due(api: ThreadsAPI, token: str) -> None:
    saved_at = get_threads_token_saved_at()
    now = datetime.now(UTC)
    if saved_at is None:
        save_threads_token(token, now)
        return
    if now - saved_at < timedelta(days=1):
        return
    save_threads_token(api.refresh_long_lived_token(), now)
