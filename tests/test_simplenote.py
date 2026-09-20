from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from threads_to_naver.simplenote import (
    SimplenoteNote,
    _decode_note,
    split_note_content,
)


def test_first_line_becomes_title_and_remaining_text_stays_body() -> None:
    assert split_note_content("제목  \r\n첫 문단\r\n\r\n둘째 문단") == (
        "제목",
        "첫 문단\n\n둘째 문단",
    )


def test_simplenote_item_uses_prefixed_id_and_creation_date() -> None:
    note = SimplenoteNote(
        id="abc",
        content="직접 쓰는 AI교양\n본문",
        tags=("naver",),
        created=datetime(2026, 9, 19, 16, 30, tzinfo=UTC),
    )

    item = note.to_draft_item()

    assert item.id == "simplenote:abc"
    assert item.text == "본문"
    assert item.title_for_timezone(ZoneInfo("Asia/Seoul")) == (
        "직접 쓰는 AI교양 – 2026.09.20"
    )


def test_decode_note_rejects_missing_queue_tag() -> None:
    with pytest.raises(ValueError, match="untagged"):
        _decode_note(
            {
                "id": "abc",
                "content": "제목\n본문",
                "tags": ["other"],
                "deleted": False,
                "created": "2026-09-20T00:00:00.000Z",
                "modified": "2026-09-20T01:00:00.000Z",
            },
            required_tag="naver",
        )


def test_decode_note_falls_back_to_modified_when_created_is_missing() -> None:
    note = _decode_note(
        {
            "id": "abc",
            "content": "제목\n본문",
            "tags": ["naver"],
            "deleted": False,
            "created": None,
            "modified": "2026-09-20T01:00:00.000Z",
        },
        required_tag="naver",
    )

    assert note.created == datetime(2026, 9, 20, 1, tzinfo=UTC)
