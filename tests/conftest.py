from pathlib import Path
from zoneinfo import ZoneInfo

import keyring
import pytest

from threads_to_naver.config import Config


@pytest.fixture(autouse=True)
def isolated_keyring(monkeypatch):
    """Never allow tests to read or write the user's real macOS Keychain."""
    stored = {}
    monkeypatch.setattr(
        keyring,
        "get_password",
        lambda service, username: stored.get((service, username)),
    )
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, username, value: stored.__setitem__((service, username), value),
    )
    return stored


@pytest.fixture
def config(tmp_path: Path) -> Config:
    data_dir = tmp_path / "data"
    return Config(
        project_dir=tmp_path,
        naver_blog_id="",
        timezone=ZoneInfo("Asia/Seoul"),
        headless=True,
        include_replies=False,
        include_reposts=False,
        max_posts_per_run=20,
        naver_write_url="https://blog.naver.com/{blog_id}/postwrite",
        footer_url="",
        footer_image_path=None,
        data_dir=data_dir,
        profile_dir=data_dir / "browser-profile",
        artifacts_dir=tmp_path / "artifacts",
        state_db=data_dir / "state.sqlite3",
        source="threads",
        simplenote_tag="naver",
        simplenote_start_date=None,
        simplenote_provider="local",
        simplenote_store_path=tmp_path / "Simplenote.storedata",
        simplenote_mcp_command=tmp_path / "simplenote-mcp",
        simplenote_scan_limit=100,
        simplenote_max_notes_per_run=2,
    )
