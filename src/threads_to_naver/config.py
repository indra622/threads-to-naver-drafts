from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

APP_NAME = "threads-to-naver"
KEYRING_SERVICE = "threads-to-naver-drafts"
KEYRING_USERNAME = "threads-access-token"


@dataclass(frozen=True)
class Config:
    project_dir: Path
    naver_blog_id: str
    timezone: ZoneInfo
    headless: bool
    include_replies: bool
    include_reposts: bool
    max_posts_per_run: int
    naver_write_url: str
    data_dir: Path
    profile_dir: Path
    artifacts_dir: Path
    state_db: Path

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        project_dir = Path(__file__).resolve().parents[2]
        path = config_path or project_dir / "config.toml"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Copy config.example.toml to config.toml first."
            )
        with path.open("rb") as file:
            raw = tomllib.load(file)

        data_dir = Path.home() / ".local" / "share" / APP_NAME
        return cls(
            project_dir=project_dir,
            naver_blog_id=str(raw.get("naver_blog_id", "")).strip(),
            timezone=ZoneInfo(str(raw.get("timezone", "Asia/Seoul"))),
            headless=bool(raw.get("headless", False)),
            include_replies=bool(raw.get("include_replies", False)),
            include_reposts=bool(raw.get("include_reposts", False)),
            max_posts_per_run=max(1, int(raw.get("max_posts_per_run", 20))),
            naver_write_url=str(
                raw.get(
                    "naver_write_url",
                    "https://blog.naver.com/{blog_id}/postwrite",
                )
            ),
            data_dir=data_dir,
            profile_dir=data_dir / "browser-profile",
            artifacts_dir=project_dir / "artifacts",
            state_db=data_dir / "state.sqlite3",
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
