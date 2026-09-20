from __future__ import annotations

import getpass
from datetime import UTC, datetime

import keyring

from .config import KEYRING_SAVED_AT_USERNAME, KEYRING_SERVICE, KEYRING_USERNAME


def get_threads_token() -> str:
    token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if not token:
        raise RuntimeError(
            "Threads access token is not in macOS Keychain. Run `threads-to-naver setup-token`."
        )
    return token


def setup_threads_token() -> None:
    token = getpass.getpass("Threads access token (hidden): ").strip()
    if not token:
        raise ValueError("Token was empty; nothing was saved.")
    save_threads_token(token)
    print("Saved the Threads token in macOS Keychain.")


def save_threads_token(token: str, saved_at: datetime | None = None) -> None:
    timestamp = saved_at or datetime.now(UTC)
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
    keyring.set_password(
        KEYRING_SERVICE, KEYRING_SAVED_AT_USERNAME, timestamp.isoformat()
    )


def get_threads_token_saved_at() -> datetime | None:
    raw = keyring.get_password(KEYRING_SERVICE, KEYRING_SAVED_AT_USERNAME)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
