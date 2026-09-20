from dataclasses import replace
from datetime import UTC, datetime, timedelta

from threads_to_naver.models import ThreadPost
from threads_to_naver.naver import TempDraft
from threads_to_naver.service import (
    THREADS_EARLIEST_TIMESTAMP,
    _dated_title_for_body,
    _refresh_token_if_due,
    append_footer_to_temp_drafts,
    backfill,
    retitle_dated_series_temp_drafts,
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


def test_series_retitle_dry_run_counts_exact_titles(config, monkeypatch) -> None:
    class FakeWriter:
        def __init__(self, _config) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

        def list_temp_drafts(self) -> list[TempDraft]:
            return [
                TempDraft("1", "직접 쓰는 AI교양"),
                TempDraft("2", "직접 쓰는 AI교양 – 2026.09.20"),
            ]

    monkeypatch.setattr("threads_to_naver.service.NaverDraftWriter", FakeWriter)

    assert retitle_dated_series_temp_drafts(config, dry_run=True) == 1


def test_dated_title_matches_full_threads_body(config) -> None:
    older = ThreadPost(
        id="1",
        text="직접 쓰는 AI교양\n짧은 내용",
        timestamp=datetime(2026, 9, 18, tzinfo=UTC),
        permalink="https://threads.net/post/1",
        media_type="TEXT_POST",
    )
    target = ThreadPost(
        id="2",
        text="직접 쓰는 AI교양\n더 길고 고유한 본문 내용",
        timestamp=datetime(2026, 9, 19, 16, 30, tzinfo=UTC),
        permalink="https://threads.net/post/2",
        media_type="TEXT_POST",
    )

    assert _dated_title_for_body(
        "직접 쓰는 AI교양\n더 길고 고유한 본문 내용\nhttps://naver.me/example",
        [older, target],
        config,
    ) == "직접 쓰는 AI교양 – 2026.09.20"


def test_dated_title_ignores_configured_footer_inside_source_text(config) -> None:
    target = ThreadPost(
        id="2",
        text="직접 쓰는 AI교양\n앞부분\n원문의마지막문장",
        timestamp=datetime(2026, 9, 19, 16, 30, tzinfo=UTC),
        permalink="https://threads.net/post/2",
        media_type="TEXT_POST",
    )
    footer_config = replace(config, footer_url="https://naver.me/example")

    assert _dated_title_for_body(
        "직접 쓰는 AI교양\n앞부분\n원문의 https://naver.me/example\n마지막문장",
        [target],
        footer_config,
    ) == "직접 쓰는 AI교양 – 2026.09.20"
