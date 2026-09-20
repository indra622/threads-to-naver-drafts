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
