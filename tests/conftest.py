from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from threads_to_naver.config import Config


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
        data_dir=data_dir,
        profile_dir=data_dir / "browser-profile",
        artifacts_dir=tmp_path / "artifacts",
        state_db=data_dir / "state.sqlite3",
    )
