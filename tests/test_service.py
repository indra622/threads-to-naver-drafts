from dataclasses import replace
from datetime import UTC, datetime, timedelta

from threads_to_naver.models import ThreadPost
from threads_to_naver.naver import TempDraft
from threads_to_naver.service import (
    THREADS_EARLIEST_TIMESTAMP,
    _refresh_token_if_due,
    append_footer_to_temp_drafts,
    backfill,
    run,
)


def test_latest_query_never_uses_a_future_until(config, monkeypatch) -> None:
    now = datetime.now(config.timezone)
    captured = {}

    class FakeAPI:
        def __init__(self, _token: str) -> None:
            pass

        def get_posts(self, since: datetime, until: datetime) -> list:
            captured["since"] = since
            captured["until"] = until
            return []

    monkeypatch.setattr("threads_to_naver.service.get_threads_token", lambda: "token")
    monkeypatch.setattr("threads_to_naver.service.ThreadsAPI", FakeAPI)
    run(config, now.date(), dry_run=True, latest_only=True)

    assert captured["until"] <= datetime.now(config.timezone)
    assert captured["until"] - captured["since"] == timedelta(days=30)


def test_refreshes_token_after_one_day(monkeypatch) -> None:
    now = datetime.now(UTC)
    saved = []

    class FakeAPI:
        def refresh_long_lived_token(self) -> str:
            return "refreshed-token"

    monkeypatch.setattr(
        "threads_to_naver.service.get_threads_token_saved_at",
        lambda: now - timedelta(days=2),
    )
    monkeypatch.setattr(
        "threads_to_naver.service.save_threads_token",
        lambda token, saved_at: saved.append((token, saved_at)),
    )

    _refresh_token_if_due(FakeAPI(), "old-token")

    assert saved[0][0] == "refreshed-token"


def test_does_not_refresh_fresh_token(monkeypatch) -> None:
    now = datetime.now(UTC)

    class FakeAPI:
        def refresh_long_lived_token(self) -> str:
            raise AssertionError("fresh token must not be refreshed")

    monkeypatch.setattr(
        "threads_to_naver.service.get_threads_token_saved_at",
        lambda: now,
    )

    _refresh_token_if_due(FakeAPI(), "fresh-token")


def test_backfill_uses_full_supported_history_oldest_first(
    config, monkeypatch
) -> None:
    captured = {}
    posts = [
        ThreadPost(
            id=str(index),
            text=f"post {index}",
            timestamp=datetime(2023, 7, 6 + index, tzinfo=UTC),
            permalink=f"https://threads.net/post/{index}",
            media_type="TEXT_POST",
        )
        for index in range(3)
    ]

    class FakeAPI:
        def __init__(self, _token: str) -> None:
            pass

        def get_posts(self, since: datetime, until: datetime) -> list:
            captured["since"] = since
            captured["until"] = until
            return posts

    monkeypatch.setattr("threads_to_naver.service.get_threads_token", lambda: "token")
    monkeypatch.setattr("threads_to_naver.service.ThreadsAPI", FakeAPI)

    count = backfill(config, dry_run=True, limit=2)

    assert int(captured["since"].timestamp()) == THREADS_EARLIEST_TIMESTAMP
    assert captured["until"] <= datetime.now(config.timezone)
    assert count == 2


def test_footer_dry_run_lists_pending_without_editing(
    config, monkeypatch, tmp_path
) -> None:
    image = tmp_path / "footer.png"
    image.write_bytes(b"png")
    footer_config = replace(
        config,
        footer_url="https://naver.me/example",
        footer_image_path=image,
    )

    class FakeWriter:
        def __init__(self, _config) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def list_temp_drafts(self) -> list[TempDraft]:
            return [TempDraft("1"), TempDraft("2")]

        def append_footer_to_temp_draft(self, *_args, **_kwargs) -> bool:
            raise AssertionError("dry-run must not edit Naver")

    monkeypatch.setattr("threads_to_naver.service.NaverDraftWriter", FakeWriter)

    assert append_footer_to_temp_drafts(footer_config, dry_run=True) == 2
