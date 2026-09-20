from datetime import UTC, datetime

from threads_to_naver import secrets


def test_save_token_stores_value_and_timestamp(monkeypatch) -> None:
    stored = {}
    monkeypatch.setattr(
        secrets.keyring,
        "set_password",
        lambda service, username, value: stored.__setitem__((service, username), value),
    )
    timestamp = datetime(2026, 9, 20, tzinfo=UTC)

    secrets.save_threads_token("opaque-token", timestamp)

    assert stored[(secrets.KEYRING_SERVICE, secrets.KEYRING_USERNAME)] == "opaque-token"
    assert (
        stored[(secrets.KEYRING_SERVICE, secrets.KEYRING_SAVED_AT_USERNAME)]
        == timestamp.isoformat()
    )
