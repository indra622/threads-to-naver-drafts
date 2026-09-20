from __future__ import annotations

import getpass

import keyring

from .config import KEYRING_SERVICE, KEYRING_USERNAME


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
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
    print("Saved the Threads token in macOS Keychain.")
