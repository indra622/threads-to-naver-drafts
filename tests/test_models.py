from datetime import UTC, datetime

from threads_to_naver.models import ThreadPost


def post(text: str) -> ThreadPost:
    return ThreadPost(
        id="123",
        text=text,
        timestamp=datetime(2026, 9, 19, 12, 30, tzinfo=UTC),
        permalink="https://threads.net/post/123",
        media_type="TEXT_POST",
    )


def test_title_is_first_nonempty_line_without_rewriting() -> None:
    assert post("\n  원문의 첫 줄  \n둘째 줄").title == "원문의 첫 줄"


def test_title_is_capped_at_100_characters() -> None:
    assert post("가" * 120).title == "가" * 100


def test_empty_post_title_is_deterministic() -> None:
    assert post("").title == "Threads 2026-09-19 12:30 (123)"
