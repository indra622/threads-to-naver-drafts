from datetime import datetime, timedelta

from threads_to_naver.service import run


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
