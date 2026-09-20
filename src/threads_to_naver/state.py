from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Self


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                threads_post_id TEXT PRIMARY KEY,
                permalink TEXT NOT NULL,
                source_timestamp TEXT NOT NULL,
                drafted_at TEXT NOT NULL,
                title TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def contains(self, post_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM drafts WHERE threads_post_id = ?", (post_id,)
        ).fetchone()
        return row is not None

    def mark_drafted(
        self, post_id: str, permalink: str, source_timestamp: datetime, title: str
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO drafts (
                threads_post_id, permalink, source_timestamp, drafted_at, title
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                post_id,
                permalink,
                source_timestamp.isoformat(),
                datetime.now(UTC).isoformat(),
                title,
            ),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
