from datetime import UTC, datetime

from threads_to_naver.state import StateStore


def test_state_only_marks_successfully_created_drafts(tmp_path) -> None:
    with StateStore(tmp_path / "state.sqlite3") as state:
        assert state.contains("post-1") is False
        state.mark_drafted(
            "post-1",
            "https://threads.net/post/1",
            datetime(2026, 9, 19, tzinfo=UTC),
            "title",
        )
        assert state.contains("post-1") is True


def test_footer_updates_are_resumable_by_log_number_and_signature(tmp_path) -> None:
    with StateStore(tmp_path / "state.sqlite3") as state:
        assert state.contains_footer("224417546639", "footer-v1") is False
        state.mark_footer_updated("224417546639", "footer-v1")
        assert state.contains_footer("224417546639", "footer-v1") is True
        assert state.contains_footer("224417546639", "footer-v2") is False
