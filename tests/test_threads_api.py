from threads_to_naver.threads_api import ThreadsAPI


def test_parse_text_post_with_image() -> None:
    parsed = ThreadsAPI._parse_post(
        {
            "id": "42",
            "text": "원문 그대로",
            "timestamp": "2026-09-19T03:00:00+0000",
            "permalink": "https://threads.net/post/42",
            "media_type": "IMAGE",
            "media_url": "https://example.test/image.jpg",
        }
    )
    assert parsed.text == "원문 그대로"
    assert parsed.media[0].url == "https://example.test/image.jpg"
    assert parsed.is_repost is False


def test_parse_repost_facade() -> None:
    parsed = ThreadsAPI._parse_post(
        {
            "id": "43",
            "timestamp": "2026-09-19T03:00:00Z",
            "media_type": "REPOST_FACADE",
        }
    )
    assert parsed.is_repost is True
